from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class ChatMessage(BaseModel):
    message: str


class SqlQuery(BaseModel):
    sql: str
    db: str = "logs"


class ModeChange(BaseModel):
    agent_id: str
    mode: str  # "auto" or "chat"


class ModelChange(BaseModel):
    agent_id: str
    model: str


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/agents")
async def get_agents(request: Request):
    data = request.app.state.bus.get("mesh:agents")
    return json.loads(data) if data else []


@router.post("/chat")
async def send_chat(request: Request, body: ChatMessage):
    text = body.message.strip()
    if not text:
        return {"error": "Empty message"}
    msg = json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "human",
        "role": "human",
        "type": "human",
        "content": text,
        "metadata": {},
    })
    await request.app.state.bus.publish("agentbus", msg)
    return {"status": "sent"}


# ------------------------------------------------------------------
# Control panel
# ------------------------------------------------------------------

@router.get("/control/status")
async def control_status(request: Request):
    """Get mode and model info for all agents."""
    mesh = request.app.state.mesh
    agents = []
    for aid, info in mesh.agents.items():
        agent = info["agent"]
        agents.append({
            "agent_id": aid,
            "role": info["role"],
            "model": agent.model,
            "mode": "chat" if agent._paused else "auto",
            "activity": agent._current_activity,
            "step_count": agent._step_count,
        })
    # Available models
    try:
        models = await mesh.model_manager.list_models()
    except Exception:
        models = []
    return {"agents": agents, "models": models}


@router.post("/control/mode")
async def control_mode(request: Request, body: ModeChange):
    """Switch an agent between 'auto' (looping) and 'chat' (manual) mode."""
    mesh = request.app.state.mesh
    entry = mesh.agents.get(body.agent_id)
    if not entry:
        return {"error": f"Agent {body.agent_id} not found"}
    agent = entry["agent"]
    if body.mode == "chat":
        agent._paused = True
        return {"status": "chat", "agent_id": body.agent_id}
    elif body.mode == "auto":
        agent._paused = False
        agent._chat_event.set()  # wake the loop
        return {"status": "auto", "agent_id": body.agent_id}
    return {"error": f"Invalid mode: {body.mode}. Use 'auto' or 'chat'."}


@router.post("/control/model")
async def control_model(request: Request, body: ModelChange):
    """Swap an agent's model."""
    mesh = request.app.state.mesh
    entry = mesh.agents.get(body.agent_id)
    if not entry:
        return {"error": f"Agent {body.agent_id} not found"}
    await entry["agent"].swap_model(body.model)
    return {"status": "swapped", "agent_id": body.agent_id, "model": body.model}


@router.post("/control/step")
async def control_step(request: Request, body: ChatMessage, agent_id: str = "coordinator-1"):
    """Send a message and trigger one step in chat mode."""
    mesh = request.app.state.mesh
    entry = mesh.agents.get(agent_id)
    if not entry:
        return {"error": f"Agent {agent_id} not found"}
    agent = entry["agent"]
    if not agent._paused:
        return {"error": "Agent is in auto mode. Switch to chat mode first."}
    # Inject the message into history
    text = body.message.strip()
    if text:
        agent.history.append({"role": "user", "content": text})
        # Also publish so it shows in logs
        msg = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": "human",
            "role": "human",
            "type": "human",
            "content": text,
            "metadata": {},
        })
        await request.app.state.bus.publish("agentbus", msg)
    # Trigger one step
    agent._chat_event.set()
    return {"status": "step_triggered", "agent_id": agent_id}


@router.get("/resources")
async def get_resources():
    """Return system resource stats (RAM, disk, GPU)."""
    from app.tools.primitive.resources import _get_resources
    return _get_resources()


@router.get("/oracle/status")
async def oracle_status(request: Request):
    """Check oracle configuration and remaining daily requests."""
    oracle = request.app.state.mesh.oracle
    return {
        "enabled": oracle.enabled,
        "model": oracle.model,
        "remaining": oracle.remaining,
        "daily_limit": oracle.daily_limit,
    }


@router.get("/files")
async def get_files():
    """Return flat file list under SANDBOX_ROOT with modification times."""
    import os
    from app.config import SANDBOX_ROOT

    skip = {".git", "__pycache__", "node_modules", ".dev", "runs", "data"}
    result = []

    for root, dirs, files in os.walk(SANDBOX_ROOT):
        dirs[:] = [d for d in sorted(dirs) if d not in skip and not d.startswith(".")]
        rel_root = os.path.relpath(root, SANDBOX_ROOT)
        for f in sorted(files):
            full = os.path.join(root, f)
            rel = f if rel_root == "." else os.path.join(rel_root, f)
            try:
                st = os.stat(full)
                result.append({
                    "path": rel.replace("\\", "/"),
                    "size": st.st_size,
                    "modified": st.st_mtime,
                })
            except OSError:
                continue

    return result


@router.get("/notes")
async def get_notes(
    request: Request,
    topic: str | None = None,
    agent_id: str | None = None,
    q: str | None = None,
    limit: int = 50,
):
    """List or search notes."""
    ns = request.app.state.mesh.note_store
    if q:
        return ns.search(query=q, topic=topic, limit=limit)
    return ns.list_notes(topic=topic, agent_id=agent_id, limit=limit)


@router.get("/logs")
async def get_logs(
    request: Request,
    limit: int = 200,
    agent_id: str | None = None,
    type: str | None = None,
):
    return request.app.state.log_store.query(limit=limit, agent_id=agent_id, msg_type=type)


@router.get("/tasks")
async def get_tasks(request: Request, status: str | None = None):
    """Return task board contents, optionally filtered by status."""
    tb = request.app.state.mesh.task_board
    return tb.list_tasks(status=status)


# ------------------------------------------------------------------
# SQLite explorer
# ------------------------------------------------------------------

_DB_WHITELIST = {"logs", "context", "memory"}


@router.get("/db/tables")
async def db_tables(db: str = "logs"):
    """List tables and their columns for a database."""
    conn = _get_db_conn(db)
    if conn is None:
        return {"error": f"Unknown database: {db}. Available: {', '.join(_DB_WHITELIST)}"}
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        tables = {}
        for (name,) in rows:
            cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
            tables[name] = [{"name": c[1], "type": c[2]} for c in cols]
        return {"db": db, "tables": tables}
    finally:
        conn.close()


@router.post("/db/query")
async def db_query(body: SqlQuery):
    """Execute a read-only SQL query against a database."""
    conn = _get_db_conn(body.db)
    if conn is None:
        return {"error": f"Unknown database: {body.db}. Available: {', '.join(_DB_WHITELIST)}"}

    sql = body.sql.strip()

    # Block write operations
    first_word = sql.split()[0].upper() if sql else ""
    if first_word not in ("SELECT", "PRAGMA", "EXPLAIN", "WITH"):
        return {"error": "Only SELECT/PRAGMA/EXPLAIN/WITH queries are allowed."}

    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(500)
        return {"columns": columns, "rows": [list(r) for r in rows], "count": len(rows)}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        conn.close()


def _get_db_conn(name: str):
    import sqlite3
    from app.config import DATA_DIR

    if name not in _DB_WHITELIST:
        return None
    path = DATA_DIR / f"{name}.db"
    if not path.exists():
        return None
    return sqlite3.connect(str(path), check_same_thread=False)
