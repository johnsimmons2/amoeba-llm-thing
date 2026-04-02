"""Memory tools — let agents persist and retrieve knowledge across sessions."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.config import DATA_DIR
from app.tools import Tool

LOGS_DB = DATA_DIR / "logs.db"


def make_memory_tools(mesh: Any) -> list[Tool]:
    note_store = mesh.note_store

    async def save_note(topic: str, content: str, tags: str = "[]", agent_id: str = "unknown") -> str:
        """Save a note to persistent memory."""
        try:
            tag_list = json.loads(tags) if isinstance(tags, str) else tags
        except (json.JSONDecodeError, TypeError):
            tag_list = []
        nid = note_store.save(agent_id=agent_id, topic=topic, content=content, tags=tag_list)
        return f"Note saved (id={nid}, topic={topic})"

    async def search_notes(query: str, topic: str = "", limit: int = 20) -> str:
        """Search notes using full-text search."""
        results = note_store.search(query=query, topic=topic or None, limit=limit)
        if not results:
            return "No matching notes found."
        lines = []
        for n in results:
            lines.append(f"[{n['id']}] ({n['topic']}) {n['content'][:200]}")
        return "\n".join(lines)

    async def list_notes(topic: str = "", agent_id: str = "", limit: int = 30) -> str:
        """List recent notes, optionally filtered by topic or agent."""
        results = note_store.list_notes(
            topic=topic or None, agent_id=agent_id or None, limit=limit
        )
        if not results:
            return "No notes found."
        lines = []
        for n in results:
            lines.append(f"[{n['id']}] {n['created_at'][:16]} ({n['topic']}) {n['content'][:200]}")
        return "\n".join(lines)

    async def delete_note(note_id: int) -> str:
        """Delete an outdated or incorrect note."""
        ok = note_store.delete(note_id)
        return f"Note {note_id} deleted." if ok else f"Note {note_id} not found."

    async def search_logs(query: str, type: str = "", agent_id: str = "", limit: int = 30) -> str:
        """Search historical logs (thoughts, tool calls, errors, etc.)."""
        conn = sqlite3.connect(str(LOGS_DB))
        try:
            sql = "SELECT id, timestamp, agent_id, type, content FROM logs WHERE 1=1"
            params: list = []
            if query:
                sql += " AND content LIKE ?"
                params.append(f"%{query}%")
            if type:
                sql += " AND type = ?"
                params.append(type)
            if agent_id:
                sql += " AND agent_id = ?"
                params.append(agent_id)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        if not rows:
            return "No matching logs found."
        lines = []
        for r in rows:
            content_str = r[4][:300] if r[4] else ""
            lines.append(f"[{r[0]}] {r[1][:16]} {r[2] or '-'} ({r[3]}) {content_str}")
        return "\n".join(lines)

    return [
        Tool(
            name="save_note",
            description="Save a note to persistent shared memory. Use topic to categorize (e.g. 'tool:read_file', 'discovery', 'plan', 'error-pattern').",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Category — e.g. 'tool:shell', 'discovery', 'plan', 'bug', 'environment'"},
                    "content": {"type": "string", "description": "The note content — what you learned or want to remember"},
                    "tags": {"type": "string", "description": "JSON array of tags, e.g. '[\"important\",\"windows\"]'. Default: []"},
                    "agent_id": {"type": "string", "description": "Your agent ID (auto-filled if omitted)"},
                },
                "required": ["topic", "content"],
            },
            func=save_note,
        ),
        Tool(
            name="search_notes",
            description="Full-text search across all saved notes. Returns matching notes ranked by relevance.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "topic": {"type": "string", "description": "Optional: filter by topic"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["query"],
            },
            func=search_notes,
        ),
        Tool(
            name="list_notes",
            description="List recent notes, optionally filtered by topic or agent.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Filter by topic"},
                    "agent_id": {"type": "string", "description": "Filter by author agent"},
                    "limit": {"type": "integer", "description": "Max results (default 30)"},
                },
                "required": [],
            },
            func=list_notes,
        ),
        Tool(
            name="delete_note",
            description="Delete an outdated or incorrect note by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "Note ID to delete"},
                },
                "required": ["note_id"],
            },
            func=delete_note,
        ),
        Tool(
            name="search_logs",
            description="Search historical logs — thoughts, tool calls, errors, messages from any agent. Useful for reviewing what happened in the past.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for in log content"},
                    "type": {"type": "string", "description": "Filter by log type: thought, tool_call, tool_result, error, spawn, message, etc."},
                    "agent_id": {"type": "string", "description": "Filter by agent ID"},
                    "limit": {"type": "integer", "description": "Max results (default 30)"},
                },
                "required": ["query"],
            },
            func=search_logs,
        ),
    ]
