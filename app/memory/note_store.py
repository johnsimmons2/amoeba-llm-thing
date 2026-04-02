from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "memory.db"


class NoteStore:
    """SQLite-backed shared note store with FTS5 full-text search.

    Agents use this to persist discoveries, observations, and knowledge
    that survive beyond their context window.
    """

    def __init__(self) -> None:
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT    NOT NULL,
                agent_id   TEXT    NOT NULL,
                topic      TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                tags       TEXT    NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_notes_topic    ON notes (topic);
            CREATE INDEX IF NOT EXISTS idx_notes_agent    ON notes (agent_id);
        """)
        # FTS5 virtual table — created separately so we can check existence first
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notes_fts'"
        ).fetchone()
        if not row:
            self._conn.executescript("""
                CREATE VIRTUAL TABLE notes_fts USING fts5(
                    topic, content, tags,
                    content='notes',
                    content_rowid='id'
                );
                -- Keep FTS in sync via triggers
                CREATE TRIGGER notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, topic, content, tags)
                    VALUES (new.id, new.topic, new.content, new.tags);
                END;
                CREATE TRIGGER notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, topic, content, tags)
                    VALUES ('delete', old.id, old.topic, old.content, old.tags);
                END;
                CREATE TRIGGER notes_au AFTER UPDATE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, topic, content, tags)
                    VALUES ('delete', old.id, old.topic, old.content, old.tags);
                    INSERT INTO notes_fts(rowid, topic, content, tags)
                    VALUES (new.id, new.topic, new.content, new.tags);
                END;
            """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, agent_id: str, topic: str, content: str, tags: list[str] | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(tags or [])
        cur = self._conn.execute(
            "INSERT INTO notes (created_at, agent_id, topic, content, tags) VALUES (?,?,?,?,?)",
            (now, agent_id, topic, content, tags_json),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def delete(self, note_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, topic: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search across notes."""
        # Escape special FTS5 characters and append wildcard
        safe_q = query.replace('"', '""')
        fts_query = f'"{safe_q}"*'

        sql = """
            SELECT n.id, n.created_at, n.agent_id, n.topic, n.content, n.tags
            FROM notes_fts f
            JOIN notes n ON n.id = f.rowid
            WHERE notes_fts MATCH ?
        """
        params: list = [fts_query]
        if topic:
            sql += " AND n.topic = ?"
            params.append(topic)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def list_notes(
        self,
        topic: str | None = None,
        agent_id: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        """List recent notes, optionally filtered."""
        sql = "SELECT id, created_at, agent_id, topic, content, tags FROM notes WHERE 1=1"
        params: list = []
        if topic:
            sql += " AND topic = ?"
            params.append(topic)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def get(self, note_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, created_at, agent_id, topic, content, tags FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        return dict(row) if row else None
