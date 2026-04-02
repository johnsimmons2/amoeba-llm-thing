"""Model management tools — let agents list, pull, unload, and swap models."""

from __future__ import annotations

import json

from app.tools import Tool


def make_model_tools(mesh: object) -> list[Tool]:
    async def list_models() -> str:
        mm = mesh.model_manager  # type: ignore[attr-defined]
        models = await mm.list_models()
        if not models:
            return "No models available"
        lines = []
        for m in models:
            loaded = " [LOADED]" if m.get("loaded") else ""
            size_mb = m.get("size", 0) // (1024 * 1024)
            lines.append(f"{m['name']} ({size_mb}MB, {m.get('parameter_size', '?')}){loaded}")
        return "\n".join(lines)

    async def pull_model(name: str) -> str:
        mm = mesh.model_manager  # type: ignore[attr-defined]
        return await mm.pull_model(name)

    async def unload_model(name: str) -> str:
        mm = mesh.model_manager  # type: ignore[attr-defined]
        return await mm.unload_model(name)

    async def swap_model(agent_id: str, new_model: str) -> str:
        agents = mesh.agents  # type: ignore[attr-defined]
        if agent_id not in agents:
            return f"Agent {agent_id} not found"
        agent = agents[agent_id]["agent"]
        await agent.swap_model(new_model)
        agents[agent_id]["model"] = new_model
        return f"Agent {agent_id} now using {new_model}"

    return [
        Tool("list_models", "List all available models and which are loaded in memory.", {
            "type": "object",
            "properties": {},
            "required": [],
        }, list_models),
        Tool("pull_model", "Download a model by name (e.g. 'llama3.2', 'mistral', 'codellama').", {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Model name to pull (Ollama model name)"},
            },
            "required": ["name"],
        }, pull_model),
        Tool("unload_model", "Unload a model from GPU/RAM to free resources.", {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Model name to unload"},
            },
            "required": ["name"],
        }, unload_model),
        Tool("swap_model", "Switch an agent to a different model. Context is preserved.", {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent to switch"},
                "new_model": {"type": "string", "description": "New model name"},
            },
            "required": ["agent_id", "new_model"],
        }, swap_model),
    ]
