from __future__ import annotations

import asyncio

from app.tools import Tool
from app.config import WORKSPACE


def make_shell_tools() -> list[Tool]:
    async def run_shell(command: str, timeout: int = 30) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(WORKSPACE),
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            output = stdout.decode("utf-8", errors="replace")
            if len(output) > 4096:
                output = output[:4096] + f"\n... (truncated, {len(output)} bytes total)"
            return output or "(no output)"
        except asyncio.TimeoutError:
            proc.kill()
            return f"Command timed out after {timeout}s"

    return [
        Tool("run_shell", "Run a shell command. Working directory is the workspace.", {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds (default 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        }, run_shell),
    ]
