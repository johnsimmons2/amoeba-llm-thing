"""Task board tools — let agents create, claim, complete, and view tasks."""

from __future__ import annotations

import json

from app.tools import Tool


def make_task_tools(mesh: object) -> list[Tool]:
    async def create_task(title: str, description: str = "", priority: str = "normal", assign_to: str = "") -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        # Determine the calling agent from context (first agent or specified)
        created_by = ""
        for aid, info in mesh.agents.items():  # type: ignore[attr-defined]
            created_by = aid
            break
        task = board.add(
            title=title,
            description=description,
            created_by=created_by,
            priority=priority,
            assigned_to=assign_to,
        )
        await board.publish_update()
        assigned = f" → assigned to {assign_to}" if assign_to else ""
        return f"Task {task['id']} created: {title}{assigned}"

    async def list_tasks(status: str = "") -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        tasks = board.list_tasks(status=status or None)
        if not tasks:
            return "No tasks" + (f" with status '{status}'" if status else "")
        lines = []
        for t in tasks:
            owner = f" [{t['assigned_to']}]" if t["assigned_to"] else ""
            lines.append(f"[{t['id']}] {t['status'].upper():8s} {t['priority']:6s} {t['title']}{owner}")
        return "\n".join(lines)

    async def claim_task(task_id: str, agent_id: str) -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        result = board.claim(task_id, agent_id)
        await board.publish_update()
        return result

    async def complete_task(task_id: str, agent_id: str) -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        result = board.complete(task_id, agent_id)
        await board.publish_update()
        return result

    async def fail_task(task_id: str, agent_id: str, reason: str = "") -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        result = board.fail(task_id, agent_id, reason)
        await board.publish_update()
        return result

    async def my_task(agent_id: str) -> str:
        board = mesh.task_board  # type: ignore[attr-defined]
        task = board.agent_current_task(agent_id)
        if not task:
            return f"Agent {agent_id} has no current task"
        return json.dumps(task, indent=2)

    return [
        Tool("create_task", "Add a task to the shared board. Optionally assign it to an agent_id immediately.", {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short task title"},
                "description": {"type": "string", "description": "Detailed task description"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"], "description": "Task priority"},
                "assign_to": {"type": "string", "description": "Agent ID to assign to (leave empty for unassigned)"},
            },
            "required": ["title"],
        }, create_task),
        Tool("list_tasks", "View all tasks on the shared board. Optionally filter by status.", {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "assigned", "done", "failed", ""], "description": "Filter by status (empty = all)"},
            },
            "required": [],
        }, list_tasks),
        Tool("claim_task", "Assign an open task to yourself. You cannot claim if you already have an active task.", {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to claim"},
                "agent_id": {"type": "string", "description": "Your agent ID"},
            },
            "required": ["task_id", "agent_id"],
        }, claim_task),
        Tool("complete_task", "Mark your current task as done. You must finish tasks before taking new ones.", {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to complete"},
                "agent_id": {"type": "string", "description": "Your agent ID"},
            },
            "required": ["task_id", "agent_id"],
        }, complete_task),
        Tool("fail_task", "Mark a task as failed with an optional reason. It can be reopened later.", {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to fail"},
                "agent_id": {"type": "string", "description": "Your agent ID"},
                "reason": {"type": "string", "description": "Why the task failed"},
            },
            "required": ["task_id", "agent_id"],
        }, fail_task),
        Tool("my_task", "Check what task you are currently working on.", {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"},
            },
            "required": ["agent_id"],
        }, my_task),
    ]
