from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from app.bus import EventBus
from app.agents.base_agent import BaseAgent
from app.models.manager import ModelManager
from app.models.oracle import Oracle
from app.memory.context_store import ContextStore
from app.memory.note_store import NoteStore
from app.tasks import TaskBoard
from app.tools.registry import ToolRegistry
from app.config import ORACLE_API_URL, ORACLE_API_KEY, ORACLE_MODEL, ORACLE_DAILY_LIMIT

logger = logging.getLogger(__name__)

CHANNEL = "agentbus"


class AgentMesh:
    """Manages agent lifecycle. All agents are peers — no orchestrator."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.agents: dict[str, dict] = {}
        self.goal: str = ""
        self._registry = ToolRegistry()
        self.model_manager = ModelManager()
        self.context_store = ContextStore()
        self.note_store = NoteStore()
        self.oracle = Oracle(
            api_url=ORACLE_API_URL,
            api_key=ORACLE_API_KEY,
            model=ORACLE_MODEL,
            daily_limit=ORACLE_DAILY_LIMIT,
        )
        self.task_board = TaskBoard(bus)

    # ------------------------------------------------------------------
    # Spawn / kill
    # ------------------------------------------------------------------

    async def spawn_agent(
        self,
        role: str = "assistant",
        model: str = "llama3.2",
        system_prompt: str = "",
        goal: str = "",
        agent_id: str | None = None,
    ) -> str:
        agent_id = agent_id or f"{role[:8].strip()}-{uuid.uuid4().hex[:6]}"
        tools = self._registry.build_tools(self)

        agent = BaseAgent(
            agent_id=agent_id,
            role=role,
            model=model,
            system_prompt=system_prompt or f"You are a {role} agent.",
            goal=goal or self.goal,
            bus=self.bus,
            model_manager=self.model_manager,
            context_store=self.context_store,
            oracle=self.oracle,
            tools=tools,
            mesh=self,
        )

        task = asyncio.create_task(agent.run(), name=f"agent-{agent_id}")
        self.agents[agent_id] = {
            "agent": agent,
            "task": task,
            "role": role,
            "model": model,
        }

        await self._publish_agent_list()
        logger.info("Spawned %s (role=%s model=%s)", agent_id, role, model)
        return agent_id

    async def kill_agent(self, agent_id: str) -> bool:
        entry = self.agents.pop(agent_id, None)
        if not entry:
            return False
        entry["agent"].stop()
        entry["task"].cancel()
        await self._publish_agent_list()
        logger.info("Killed %s", agent_id)
        return True

    def stop(self) -> None:
        for entry in self.agents.values():
            entry["agent"].stop()
            entry["task"].cancel()

    # ------------------------------------------------------------------
    # Internal tasks
    # ------------------------------------------------------------------

    async def _publish_agent_list(self) -> None:
        agent_list = [
            {
                "agent_id": aid,
                "role": info["role"],
                "model": info["agent"].model,
                "running": not info["task"].done(),
                "activity": info["agent"]._current_activity,
                "mode": "chat" if info["agent"]._paused else "auto",
            }
            for aid, info in self.agents.items()
        ]
        msg = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "mesh",
            "type": "agent_list",
            "content": agent_list,
        })
        await self.bus.publish(CHANNEL, msg)
        self.bus.set("mesh:agents", json.dumps(agent_list))

    async def _bus_listener(self) -> None:
        """Route human messages from the bus into every agent's queue."""
        sub = self.bus.subscribe(CHANNEL)
        try:
            async for raw in sub:
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if data.get("type") == "human":
                    for info in list(self.agents.values()):
                        await info["agent"].message_queue.put(data)
        except asyncio.CancelledError:
            sub.unsubscribe()

    async def _heartbeat(self) -> None:
        """Re-publish agent list periodically for the dashboard."""
        while True:
            await asyncio.sleep(5)
            if self.agents:
                await self._publish_agent_list()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def start(self, startup: dict) -> None:
        self.goal = startup.get("goal", "Explore and be autonomous.")
        logger.info("Mesh started | goal: %s", self.goal[:80])

        asyncio.create_task(self._bus_listener(), name="bus-listener")
        asyncio.create_task(self._heartbeat(), name="heartbeat")

        for cfg in startup.get("agents", []):
            cfg.setdefault("goal", self.goal)
            await self.spawn_agent(**cfg)
