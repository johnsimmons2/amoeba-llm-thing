"""Agent context store — persists conversation history to SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "context.db"


class ContextStore:
    """Saves and restores agent conversation history so it survives model swaps and restarts."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS context (
                agent_id  TEXT NOT NULL,
                turn_idx  INTEGER NOT NULL,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                tool_calls TEXT,
                PRIMARY KEY (agent_id, turn_idx)
            );
        """)
        self._conn.commit()

    def save(self, agent_id: str, history: list[dict]) -> None:
        """Replace the full history for an agent."""
        try:
            self._conn.execute("DELETE FROM context WHERE agent_id = ?", (agent_id,))
            for i, turn in enumerate(history):
                self._conn.execute(
                    "INSERT INTO context (agent_id, turn_idx, role, content, tool_calls) VALUES (?,?,?,?,?)",
                    (
                        agent_id,
                        i,
                        turn.get("role", ""),
                        turn.get("content", ""),
                        json.dumps(turn.get("tool_calls")) if "tool_calls" in turn else None,
                    ),
                )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Context save failed for %s: %s", agent_id, exc)

    def load(self, agent_id: str) -> list[dict]:
        """Load saved history for an agent. Returns empty list if none."""
        rows = self._conn.execute(
            "SELECT role, content, tool_calls FROM context WHERE agent_id = ? ORDER BY turn_idx",
            (agent_id,),
        ).fetchall()
        history = []
        for role, content, tc_json in rows:
            turn: dict = {"role": role, "content": content}
            if tc_json:
                turn["tool_calls"] = json.loads(tc_json)
            history.append(turn)
        return history

    def delete(self, agent_id: str) -> None:
        """Remove saved context for an agent."""
        self._conn.execute("DELETE FROM context WHERE agent_id = ?", (agent_id,))
        self._conn.commit()
