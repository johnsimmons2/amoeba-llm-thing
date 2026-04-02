from __future__ import annotations

import os
from pathlib import Path

import aiofiles

from app.tools import Tool
from app.config import SANDBOX_ROOT


def _safe_path(relative: str) -> Path:
    """Resolve a path safely within the project root. Blocks any traversal outside."""
    base = SANDBOX_ROOT.resolve()
    target = (base / relative.lstrip("/")).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path traversal blocked: {relative!r}")
    return target


def make_file_tools() -> list[Tool]:
    async def read_file(path: str) -> str:
        full = _safe_path(path)
        async with aiofiles.open(full, "r", encoding="utf-8", errors="replace") as fh:
            return await fh.read()

    async def write_file(path: str, content: str) -> str:
        full = _safe_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full, "w", encoding="utf-8") as fh:
            await fh.write(content)
        return f"Written: {path}"

    async def list_dir(path: str = "") -> str:
        full = _safe_path(path)
        if not full.exists():
            return f"Path does not exist: {path}"
        entries = sorted(os.listdir(full))
        return "\n".join(entries) if entries else "(empty)"

    async def delete_file(path: str) -> str:
        full = _safe_path(path)
        if not full.is_file():
            raise ValueError(f"Not a file: {path}")
        full.unlink()
        return f"Deleted: {path}"

    return [
        Tool("read_file", "Read a file from the project.", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path within the project root"},
            },
            "required": ["path"],
        }, read_file),
        Tool("write_file", "Write content to a file. Creates directories as needed.", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path within the project root"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        }, write_file),
        Tool("list_dir", "List directory contents.", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path (empty for project root)"},
            },
            "required": [],
        }, list_dir),
        Tool("delete_file", "Delete a file from the project.", {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        }, delete_file),
    ]
