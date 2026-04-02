"""Shared task board — agents post, claim, and complete tasks collaboratively."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.bus import EventBus

logger = logging.getLogger(__name__)

CHANNEL = "agentbus"
KV_KEY = "taskboard:tasks"


class TaskBoard:
    """
    In-memory task board synced to the EventBus KV store.

    Task lifecycle:
      open → assigned → done / failed

    Rules enforced here:
      - An agent with an in-progress task cannot take another.
      - Tasks track who created and who owns them.
    """

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._tasks: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        title: str,
        description: str = "",
        created_by: str = "",
        priority: str = "normal",
        assigned_to: str = "",
    ) -> dict:
        task_id = uuid.uuid4().hex[:8]
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "status": "assigned" if assigned_to else "open",
            "priority": priority,
            "created_by": created_by,
            "assigned_to": assigned_to,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._tasks[task_id] = task
        self._save()
        return task

    def claim(self, task_id: str, agent_id: str) -> str:
        """Assign an open task to an agent. Returns status message."""
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task["status"] != "open":
            return f"Task {task_id} is already {task['status']}"
        if self.agent_busy(agent_id):
            return f"Agent {agent_id} already has an in-progress task — finish it first"
        task["status"] = "assigned"
        task["assigned_to"] = agent_id
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return f"Task {task_id} assigned to {agent_id}"

    def complete(self, task_id: str, agent_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task["assigned_to"] != agent_id:
            return f"Task {task_id} is not assigned to {agent_id}"
        task["status"] = "done"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return f"Task {task_id} marked done"

    def fail(self, task_id: str, agent_id: str, reason: str = "") -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task["assigned_to"] != agent_id:
            return f"Task {task_id} is not assigned to {agent_id}"
        task["status"] = "failed"
        task["description"] += f"\n[FAILED] {reason}" if reason else ""
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return f"Task {task_id} marked failed"

    def reopen(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        task["status"] = "open"
        task["assigned_to"] = ""
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return f"Task {task_id} reopened"

    def list_tasks(self, status: str | None = None) -> list[dict]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return sorted(tasks, key=lambda t: t["created_at"])

    def get(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def agent_busy(self, agent_id: str) -> bool:
        """True if the agent has any assigned (in-progress) task."""
        return any(
            t["assigned_to"] == agent_id and t["status"] == "assigned"
            for t in self._tasks.values()
        )

    def agent_current_task(self, agent_id: str) -> dict | None:
        """Return the agent's current assigned task, or None."""
        for t in self._tasks.values():
            if t["assigned_to"] == agent_id and t["status"] == "assigned":
                return t
        return None

    # ------------------------------------------------------------------
    # Bus integration
    # ------------------------------------------------------------------

    async def publish_update(self) -> None:
        """Push the full task list to the bus for dashboard visibility."""
        msg = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "taskboard",
            "type": "task_update",
            "content": self.list_tasks(),
            "metadata": {},
        })
        await self.bus.publish(CHANNEL, msg)

    # ------------------------------------------------------------------
    # Persistence via bus KV
    # ------------------------------------------------------------------

    def _save(self) -> None:
        self.bus.set(KV_KEY, json.dumps(self._tasks))

    def _load(self) -> None:
        raw = self.bus.get(KV_KEY)
        if raw:
            try:
                self._tasks = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                self._tasks = {}
