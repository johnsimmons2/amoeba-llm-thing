"""Lifecycle tools — let agents restart the app process after code changes."""

from __future__ import annotations

import os

from app.tools import Tool

RESTART_CODE = 42


def make_lifecycle_tools() -> list[Tool]:
    async def request_restart(reason: str = "") -> str:
        # os._exit(42) terminates immediately. The launcher detects code 42
        # and re-launches the process, picking up any code changes.
        # SQLite commits are per-insert so no data is lost.
        os._exit(RESTART_CODE)

    async def request_shutdown(reason: str = "") -> str:
        os._exit(0)

    return [
        Tool("request_restart", "Restart the app. Use after editing source code so changes take effect.", {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the restart is needed"},
            },
            "required": [],
        }, request_restart),
        Tool("request_shutdown", "Shut down the app completely.", {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the shutdown is needed"},
            },
            "required": [],
        }, request_shutdown),
    ]
