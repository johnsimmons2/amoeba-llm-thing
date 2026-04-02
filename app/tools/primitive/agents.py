from __future__ import annotations

from datetime import datetime, timezone

from app.tools import Tool


def make_agent_tools(mesh: object) -> list[Tool]:
    async def spawn_agent(
        role: str,
        system_prompt: str,
        goal: str = "",
        model: str = "llama3.2",
        agent_id: str | None = None,
    ) -> str:
        new_id = await mesh.spawn_agent(  # type: ignore[attr-defined]
            role=role, model=model, system_prompt=system_prompt,
            goal=goal, agent_id=agent_id,
        )
        return f"Spawned agent: {new_id}"

    async def kill_agent(agent_id: str) -> str:
        ok = await mesh.kill_agent(agent_id)  # type: ignore[attr-defined]
        return f"Killed {agent_id}" if ok else f"Agent {agent_id} not found"

    async def list_agents() -> str:
        agents = mesh.agents  # type: ignore[attr-defined]
        if not agents:
            return "No agents running"
        return "\n".join(
            f"{aid}: role={i['role']} model={i['model']} running={not i['task'].done()}"
            for aid, i in agents.items()
        )

    async def send_message(target_agent_id: str, message: str) -> str:
        agents = mesh.agents  # type: ignore[attr-defined]
        if target_agent_id not in agents:
            return f"Agent {target_agent_id} not found"
        msg = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "direct",
            "type": "message",
            "content": message,
        }
        await agents[target_agent_id]["agent"].message_queue.put(msg)
        return f"Message queued for {target_agent_id}"

    async def broadcast_message(message: str) -> str:
        agents = mesh.agents  # type: ignore[attr-defined]
        msg = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "broadcast",
            "type": "message",
            "content": message,
        }
        for info in agents.values():
            await info["agent"].message_queue.put(msg)
        return f"Broadcast sent to {len(agents)} agent(s)"

    return [
        Tool("spawn_agent", "Spawn a new autonomous agent in the mesh.", {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Role label (e.g. researcher, coder)"},
                "system_prompt": {"type": "string", "description": "System prompt for the agent"},
                "goal": {"type": "string", "description": "Specific goal (inherits mesh goal if empty)"},
                "model": {"type": "string", "description": "Ollama model (default: llama3.2)", "default": "llama3.2"},
                "agent_id": {"type": "string", "description": "Custom ID (auto-generated if omitted)"},
            },
            "required": ["role", "system_prompt"],
        }, spawn_agent),
        Tool("kill_agent", "Stop and remove an agent.", {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to kill"},
            },
            "required": ["agent_id"],
        }, kill_agent),
        Tool("list_agents", "List all running agents.", {
            "type": "object",
            "properties": {},
            "required": [],
        }, list_agents),
        Tool("send_message", "Send a direct message to a specific agent.", {
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string", "description": "Target agent ID"},
                "message": {"type": "string", "description": "Message content"},
            },
            "required": ["target_agent_id", "message"],
        }, send_message),
        Tool("broadcast_message", "Broadcast a message to all agents.", {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to broadcast"},
            },
            "required": ["message"],
        }, broadcast_message),
    ]
