from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.bus import EventBus
from app.models.manager import ModelManager
from app.models.oracle import Oracle
from app.memory.context_store import ContextStore
from app.tools import Tool

logger = logging.getLogger(__name__)

CHANNEL = "agentbus"


class BaseAgent:
    """
    Single autonomous agent. Loops:
      drain messages -> call model -> execute tools -> publish results -> save context
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        model: str,
        system_prompt: str,
        goal: str,
        bus: EventBus,
        model_manager: ModelManager,
        context_store: ContextStore,
        oracle: Oracle,
        tools: list[Tool],
        mesh: Any,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.model = model
        self.system_prompt = system_prompt
        self.goal = goal
        self.bus = bus
        self.model_manager = model_manager
        self.context_store = context_store
        self.oracle = oracle
        self.tools = tools
        self.mesh = mesh

        self.history: list[dict] = []
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self._steps_since_oracle: int = 0
        self._step_count: int = 0
        self._current_activity: str = "idle"
        self._paused: bool = False
        self._chat_event: asyncio.Event = asyncio.Event()
        self._log = logging.getLogger(f"agent.{agent_id}")

    # ------------------------------------------------------------------
    # Bus publishing
    # ------------------------------------------------------------------

    async def publish(self, msg_type: str, content: Any, metadata: dict | None = None) -> None:
        msg = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "role": self.role,
            "type": msg_type,
            "content": content,
            "metadata": metadata or {},
        })
        await self.bus.publish(CHANNEL, msg)

    def stop(self) -> None:
        self.running = False

    # ------------------------------------------------------------------
    # Model interaction
    # ------------------------------------------------------------------

    def _system_message(self) -> str:
        tool_list = "\n".join(f"  - {t.name}: {t.description}" for t in self.tools)

        # Task awareness — only include if there's something relevant
        task_section = ""
        if hasattr(self.mesh, "task_board"):
            current = self.mesh.task_board.agent_current_task(self.agent_id)
            if current:
                task_section += (
                    f"\nACTIVE TASK — finish this before taking new work:\n"
                    f"  [{current['id']}] {current['priority']} | {current['title']}: {current['description']}\n"
                )
            open_tasks = self.mesh.task_board.list_tasks(status="open")
            if open_tasks:
                task_section += "Open tasks:\n"
                for t in open_tasks[:10]:
                    task_section += f"  [{t['id']}] {t['priority']:6s} {t['title']}\n"

        parts = [
            self.system_prompt,
            f"You are {self.agent_id} (role: {self.role}). Goal: {self.goal}",
            f"Tools:\n{tool_list}",
        ]
        if task_section:
            parts.append(task_section)
        parts.append(
            "Rules: Focus on your current task. Use complete_task/fail_task when done. "
            "Delegate via create_task + spawn_agent. Do NOT repeat work you already did — "
            "review your previous messages before acting. "
            "Use save_note to record discoveries, gotchas, and plans so you and other agents "
            "can recall them later. Use search_notes before starting new work. Be concise."
        )
        return "\n\n".join(parts)

    async def _call_model(self) -> dict:
        messages = [{"role": "system", "content": self._system_message()}] + self.history
        tools = [t.to_ollama_schema() for t in self.tools]
        return await self.model_manager.chat(self.model, messages, tools)

    async def _call_model_stream(self):
        """Stream model response, publishing thought_delta chunks in real-time."""
        messages = [{"role": "system", "content": self._system_message()}] + self.history
        tools = [t.to_ollama_schema() for t in self.tools]

        thinking_buf = ""
        content_buf = ""
        thinking_full = ""
        content_full = ""
        tool_calls = []
        last_flush = time.monotonic()
        INTERVAL = 0.3  # publish deltas every 300ms

        async for chunk in self.model_manager.chat_stream(self.model, messages, tools):
            msg = chunk.get("message", {})

            # Accumulate deltas
            t_delta = msg.get("thinking", "")
            c_delta = msg.get("content", "")
            if t_delta:
                thinking_buf += t_delta
                thinking_full += t_delta
            if c_delta:
                content_buf += c_delta
                content_full += c_delta

            # Tool calls come in the final chunk(s)
            tc = msg.get("tool_calls")
            if tc:
                tool_calls.extend(tc)

            # Flush buffered deltas periodically
            now = time.monotonic()
            if now - last_flush >= INTERVAL:
                if thinking_buf:
                    await self.publish("thought_delta", thinking_buf)
                    thinking_buf = ""
                if content_buf:
                    await self.publish("thought_delta", content_buf)
                    content_buf = ""
                last_flush = now

            if chunk.get("done"):
                break

        # Flush any remaining buffer
        if thinking_buf:
            await self.publish("thought_delta", thinking_buf)
        if content_buf:
            await self.publish("thought_delta", content_buf)

        # Signal end of streaming
        await self.publish("thought_end", "")

        return {
            "thinking": thinking_full,
            "content": content_full,
            "tool_calls": tool_calls,
        }

    async def _exec_tool(self, name: str, args: dict) -> str:
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        # Auto-inject agent_id for memory tools
        if name == "save_note" and "agent_id" not in args:
            args["agent_id"] = self.agent_id
        try:
            return str(await tool.call(**args))
        except Exception as exc:
            return f"Error running {name}: {exc}"

    # ------------------------------------------------------------------
    # Message draining
    # ------------------------------------------------------------------

    async def _drain_messages(self) -> None:
        pending: list[dict] = []
        while not self.message_queue.empty():
            pending.append(self.message_queue.get_nowait())
        if not pending:
            return
        combined = "\n".join(
            f"[{m.get('agent_id', '?')}]: {m.get('content', '')}" for m in pending
        )
        self.history.append({
            "role": "user",
            "content": f"Incoming messages:\n{combined}\n\nAcknowledge and continue your work.",
        })

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _context_stats(self) -> dict:
        """Compute context usage stats for debugging."""
        sys_msg = self._system_message()
        total_chars = len(sys_msg)
        role_counts = {}
        tool_call_history = []
        for m in self.history:
            role = m.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
            c = m.get("content", "")
            total_chars += len(c) if isinstance(c, str) else len(str(c))
            # Track recent tool calls for repetition detection
            tc = m.get("tool_calls")
            if tc:
                for t in tc:
                    fn = t.get("function", {})
                    tool_call_history.append(f"{fn.get('name', '?')}({json.dumps(fn.get('arguments', {}), sort_keys=True)})")
        # Rough token estimate: ~4 chars per token for English
        est_tokens = total_chars // 4
        # Detect duplicate tool calls in recent history
        recent_calls = tool_call_history[-20:]
        call_counts = {}
        for c in recent_calls:
            call_counts[c] = call_counts.get(c, 0) + 1
        repeated = {k: v for k, v in call_counts.items() if v > 1}
        return {
            "history_messages": len(self.history),
            "history_max": 60,
            "total_chars": total_chars,
            "est_tokens": est_tokens,
            "roles": role_counts,
            "repeated_calls": repeated,
        }

    async def step(self) -> None:
        self._step_count += 1
        self._current_activity = "thinking"
        await self._drain_messages()

        stats = self._context_stats()
        sys_prompt = self._system_message()
        await self.publish("step_info", {
            "event": "start",
            "step": self._step_count,
            "model": self.model,
            "history_messages": stats["history_messages"],
            "history_max": stats["history_max"],
            "est_tokens": stats["est_tokens"],
            "total_chars": stats["total_chars"],
            "roles": stats["roles"],
            "repeated_calls": stats["repeated_calls"],
            "system_prompt": sys_prompt,
        })

        try:
            result = await self._call_model_stream()
        except httpx.HTTPStatusError as exc:
            self._current_activity = "error"
            await self.publish("error", f"Model HTTP {exc.response.status_code}")
            await asyncio.sleep(15)
            return
        except httpx.RequestError as exc:
            self._current_activity = "error"
            await self.publish("error", f"Model unreachable: {exc}")
            await asyncio.sleep(15)
            return

        thinking = result["thinking"].strip()
        thought = result["content"].strip()
        tool_calls = result["tool_calls"]

        # Publish final thought summaries (for LogStream / persistence)
        if thinking:
            await self.publish("thought", thinking)
        if thought:
            await self.publish("thought", thought)

        # Build assistant content that includes thinking so future steps
        # can see the reasoning behind prior decisions.
        assistant_content = ""
        if thinking:
            assistant_content += f"<thinking>\n{thinking}\n</thinking>\n"
        if thought:
            assistant_content += thought
        assistant_content = assistant_content.strip()

        if tool_calls:
            self.history.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                self._current_activity = f"tool: {name}"
                await self.publish("tool_call", {"tool": name, "args": args})
                result_str = await self._exec_tool(name, args)
                await self.publish("tool_result", {"tool": name, "result": result_str})
                self.history.append({"role": "tool", "content": result_str})
        else:
            if assistant_content:
                self.history.append({"role": "assistant", "content": assistant_content})

        self._current_activity = "idle"

        # Keep context bounded
        if len(self.history) > 60:
            self.history = self.history[-60:]

        # Persist context after every step
        self.context_store.save(self.agent_id, self.history)

        await self.publish("step_info", {
            "event": "end",
            "step": self._step_count,
            "history_messages": len(self.history),
        })

        # Auto-escalation: detect stuck patterns and ask Oracle
        self._steps_since_oracle += 1
        if self._steps_since_oracle >= 6 and self.oracle.enabled and self.oracle.remaining > 0:
            reason = Oracle.detect_stuck(self.history)
            if reason:
                await self._escalate_to_oracle(reason)

    async def _escalate_to_oracle(self, reason: str) -> None:
        """Auto-escalate to cloud model when stuck."""
        self._steps_since_oracle = 0
        prompt = (
            f"I am agent '{self.agent_id}' (role: {self.role}, model: {self.model}).\n"
            f"My goal: {self.goal}\n\n"
            f"I appear to be stuck. Detection reason: {reason}\n\n"
            f"Please analyze my recent history and give me clear, actionable next steps."
        )
        await self.publish("oracle_request", {"reason": reason, "remaining": self.oracle.remaining})
        reply = await self.oracle.ask(prompt, self.history)
        await self.publish("oracle_response", reply)
        self.history.append({
            "role": "user",
            "content": f"[Oracle guidance — from a more capable model]:\n{reply}\n\nApply this advice and continue.",
        })
        self._log.info("Oracle escalation: %s", reason)

    async def swap_model(self, new_model: str) -> None:
        """Switch this agent to a different model. Context is preserved."""
        old = self.model
        self.model = new_model
        self.context_store.save(self.agent_id, self.history)
        await self.publish("model_swap", {"from": old, "to": new_model})
        self._log.info("Swapped model %s -> %s", old, new_model)

    async def _build_boot_context(self) -> str:
        """Build a one-time boot message with environment info so the agent
        doesn't need to call list_dir, check_resources, list_models, etc."""
        parts = ["=== BOOT CONTEXT (do NOT re-discover this info — it's already here) ==="]

        # Directory listing
        try:
            import os
            from app.config import SANDBOX_ROOT
            entries = sorted(os.listdir(SANDBOX_ROOT))
            parts.append(f"Project root contents: {', '.join(entries)}")
        except Exception:
            pass

        # System resources
        try:
            from app.tools.primitive.resources import _get_resources
            res = _get_resources()
            ram = res.get("ram", {})
            disk = res.get("disk", {})
            gpu = res.get("gpu", {})
            parts.append(
                f"Resources: RAM {ram.get('total_mb', '?')}MB total / {ram.get('available_mb', '?')}MB free, "
                f"Disk {disk.get('free_gb', '?')}GB free / {disk.get('total_gb', '?')}GB total, "
                f"GPU: {gpu.get('name', 'unknown')} VRAM {gpu.get('total_mb', '?')}MB"
            )
        except Exception:
            pass

        # Available models
        try:
            models_info = await self.model_manager.list_models()
            if models_info:
                model_lines = []
                for m in models_info:
                    name = m.get("name", "?")
                    size_gb = round(m.get("size", 0) / (1024**3), 1)
                    loaded = " [LOADED]" if m.get("loaded") else ""
                    model_lines.append(f"{name} ({size_gb}GB){loaded}")
                parts.append(f"Available models: {', '.join(model_lines)}")
        except Exception:
            pass

        # Existing notes count
        try:
            note_count = len(self.mesh.note_store.list_notes(limit=100))
            if note_count:
                parts.append(f"You have {note_count} saved notes — call list_notes() to review them before starting.")
            else:
                parts.append("No saved notes yet. Save discoveries with save_note() as you work.")
        except Exception:
            pass

        parts.append("=== END BOOT CONTEXT — proceed with your goal, do NOT repeat these checks ===")
        return "\n".join(parts)

    async def run(self) -> None:
        self.running = True

        # Restore saved context if any (survives restarts / model swaps)
        saved = self.context_store.load(self.agent_id)
        if saved:
            self.history = saved
            self._log.info("Restored %d history turns", len(saved))
        else:
            # Seed first run with environment context so the agent
            # doesn't waste steps on discovery calls.
            boot = await self._build_boot_context()
            if boot:
                self.history.append({"role": "user", "content": boot})

        await self.publish("spawn", {
            "agent_id": self.agent_id,
            "role": self.role,
            "model": self.model,
        })
        self._log.info("Started (role=%s model=%s)", self.role, self.model)

        while self.running:
            try:
                if self._paused:
                    self._current_activity = "paused"
                    await self._chat_event.wait()
                    self._chat_event.clear()
                    if not self.running:
                        break
                await self.step()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error("Step error: %s", exc, exc_info=True)
