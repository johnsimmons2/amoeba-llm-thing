"""Oracle escalation tool — lets agents ask a cloud model for help."""

from __future__ import annotations

from app.tools import Tool


def make_oracle_tools(mesh: object) -> list[Tool]:
    async def ask_oracle(question: str) -> str:
        oracle = mesh.oracle  # type: ignore[attr-defined]
        agent_ids = list(mesh.agents.keys())  # type: ignore[attr-defined]
        # Gather context from the calling agent if possible
        context = None
        if agent_ids:
            first = mesh.agents[agent_ids[0]]["agent"]  # type: ignore[attr-defined]
            context = first.history[-20:] if first.history else None
        return await oracle.ask(question, context)

    async def oracle_status() -> str:
        oracle = mesh.oracle  # type: ignore[attr-defined]
        if not oracle.enabled:
            return "Oracle is not configured. Set ORACLE_API_URL, ORACLE_API_KEY, and ORACLE_MODEL env vars."
        return (
            f"Oracle: enabled\n"
            f"Model: {oracle.model}\n"
            f"Remaining today: {oracle.remaining}/{oracle.daily_limit}"
        )

    return [
        Tool("ask_oracle", "Escalate a question to a more powerful cloud model (rate limited). Use when stuck.", {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question or problem to escalate"},
            },
            "required": ["question"],
        }, ask_oracle),
        Tool("oracle_status", "Check if the oracle is configured and how many requests remain today.", {
            "type": "object",
            "properties": {},
            "required": [],
        }, oracle_status),
    ]
