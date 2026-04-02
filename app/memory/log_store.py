from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "logs.db"


class LogStore:
    """SQLite-backed log store. Can subscribe to the bus and persist every message."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                agent_id  TEXT,
                type      TEXT,
                content   TEXT,
                metadata  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_logs_agent ON logs (agent_id);
            CREATE INDEX IF NOT EXISTS idx_logs_type  ON logs (type);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, msg: dict) -> None:
        try:
            self._conn.execute(
                "INSERT INTO logs (timestamp, agent_id, type, content, metadata) VALUES (?,?,?,?,?)",
                (
                    msg.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    msg.get("agent_id", ""),
                    msg.get("type", ""),
                    json.dumps(msg.get("content", "")),
                    json.dumps(msg.get("metadata", {})),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Insert failed: %s", exc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        limit: int = 200,
        agent_id: str | None = None,
        msg_type: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if msg_type:
            conditions.append("type = ?")
            params.append(msg_type)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT timestamp, agent_id, type, content, metadata "
            f"FROM logs {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        return [
            {
                "timestamp": r[0],
                "agent_id": r[1],
                "type": r[2],
                "content": json.loads(r[3]),
                "metadata": json.loads(r[4]),
            }
            for r in reversed(rows)
        ]

    # ------------------------------------------------------------------
    # Bus integration
    # ------------------------------------------------------------------

    async def start(self, bus) -> None:
        """Start a background task that persists all bus messages to SQLite."""
        asyncio.create_task(self._persist_loop(bus), name="log-store")
        await asyncio.sleep(0)  # yield so the task subscribes before any messages fly

    async def _persist_loop(self, bus) -> None:
        sub = bus.subscribe("agentbus")
        async for raw in sub:
            try:
                self.insert(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                pass
