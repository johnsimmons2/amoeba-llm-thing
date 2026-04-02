from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import DATA_DIR, CIVITAI_API_KEY

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


class SpawnRequest(BaseModel):
    role: str = "assistant"
    model: str = "qwen3.5:27b"
    system_prompt: str = ""
    goal: str = ""
    agent_id: str = ""
    mode: str = "chat"  # start in chat mode by default


class PullModelRequest(BaseModel):
    name: str


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


@router.post("/control/spawn")
async def control_spawn(request: Request, body: SpawnRequest):
    """Spawn a new agent from the dashboard."""
    mesh = request.app.state.mesh
    aid = await mesh.spawn_agent(
        role=body.role,
        model=body.model,
        system_prompt=body.system_prompt,
        goal=body.goal,
        agent_id=body.agent_id or None,
    )
    # Optionally start paused
    if body.mode == "chat":
        entry = mesh.agents.get(aid)
        if entry:
            entry["agent"]._paused = True
    return {"status": "spawned", "agent_id": aid}


@router.post("/control/kill")
async def control_kill(request: Request, body: ModeChange):
    """Kill an agent."""
    mesh = request.app.state.mesh
    ok = await mesh.kill_agent(body.agent_id)
    if not ok:
        return {"error": f"Agent {body.agent_id} not found"}
    return {"status": "killed", "agent_id": body.agent_id}


@router.post("/control/pull")
async def control_pull(request: Request, body: PullModelRequest):
    """Download a model from Ollama registry."""
    mm = request.app.state.mesh.model_manager
    try:
        result = await mm.pull_model(body.name)
        return {"status": result, "name": body.name}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/control/unload")
async def control_unload(request: Request, body: PullModelRequest):
    """Unload a model from VRAM."""
    mm = request.app.state.mesh.model_manager
    try:
        result = await mm.unload_model(body.name)
        return {"status": result}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/control/delete_model")
async def control_delete_model(request: Request, body: PullModelRequest):
    """Delete a model from disk."""
    mm = request.app.state.mesh.model_manager
    try:
        result = await mm.delete_model(body.name)
        return {"status": result}
    except Exception as exc:
        return {"error": str(exc)}


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
# Image serving + diffusion control
# ------------------------------------------------------------------

IMAGES_DIR = DATA_DIR / "images"


@router.get("/images")
async def list_images():
    """List generated images."""
    if not IMAGES_DIR.exists():
        return []
    files = sorted(IMAGES_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        if not f.is_file() or f.suffix == ".json":
            continue
        entry = {
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
            "url": f"/api/images/{f.name}",
            "meta": None,
        }
        meta_path = f.with_suffix(".json")
        if meta_path.exists():
            try:
                entry["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        result.append(entry)
    return result


@router.get("/images/{filename}")
async def serve_image(filename: str):
    """Serve a generated image file."""
    # Sanitize: only allow simple filenames
    safe = Path(filename).name
    filepath = IMAGES_DIR / safe
    if not filepath.exists() or not filepath.is_file():
        return {"error": "Image not found"}
    return FileResponse(filepath)


@router.get("/diffusion/status")
async def diffusion_status(request: Request):
    """Get diffusion pipeline status."""
    dp = request.app.state.mesh.diffusion_provider
    return dp.status()


@router.get("/diffusion/models")
async def diffusion_models(request: Request):
    """List available diffusion models."""
    dp = request.app.state.mesh.diffusion_provider
    return dp.available_models()


class GenerateImageRequest(BaseModel):
    prompt: str
    model: str = ""
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    guidance_scale: float = 7.5
    clip_skip: int = 0
    seed: int = -1
    batch_count: int = 1


@router.post("/diffusion/generate")
async def diffusion_generate(request: Request, body: GenerateImageRequest):
    """Generate image(s) directly from a prompt — no agent needed."""
    dp = request.app.state.mesh.diffusion_provider
    try:
        results = await dp.generate_image(
            prompt=body.prompt,
            model=body.model,
            negative_prompt=body.negative_prompt,
            width=body.width,
            height=body.height,
            steps=body.steps,
            guidance_scale=body.guidance_scale,
            clip_skip=body.clip_skip,
            seed=body.seed,
            batch_count=body.batch_count,
        )
        return {"images": results, "count": len(results)}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/diffusion/unload")
async def diffusion_unload(request: Request):
    """Unload diffusion pipeline to free VRAM."""
    dp = request.app.state.mesh.diffusion_provider
    result = await dp.unload()
    return {"status": result}


class LoadModelRequest(BaseModel):
    model: str


class AddDiffusionModelRequest(BaseModel):
    model: str
    source: str = "huggingface"  # "huggingface", "civitai", "ollama"
    format: str = "safetensors"  # "safetensors" or "gguf"
    # HuggingFace GGUF fields
    gguf_repo: str = ""
    gguf_file: str = ""
    base_pipeline: str = ""
    # CivitAI fields
    download_url: str = ""
    civitai_filename: str = ""
    pipeline_class: str = "StableDiffusionXLPipeline"
    # Common
    description: str = ""
    vram: str = ""
    recommended: Optional[dict] = None


@router.post("/diffusion/load")
async def diffusion_load(request: Request, body: LoadModelRequest):
    """Load (swap to) a diffusion pipeline model."""
    dp = request.app.state.mesh.diffusion_provider
    try:
        result = await dp.load(body.model)
        return {"status": result}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/diffusion/add_model")
async def diffusion_add_model(request: Request, body: AddDiffusionModelRequest):
    """Add a custom model to the tracked list without loading it."""
    dp = request.app.state.mesh.diffusion_provider
    if body.source == "civitai":
        dp.add_civitai_model(
            name=body.model,
            download_url=body.download_url,
            civitai_filename=body.civitai_filename,
            pipeline_class=body.pipeline_class,
            description=body.description,
            vram=body.vram,
            recommended=body.recommended,
        )
    elif body.format == "gguf":
        dp.add_gguf_model(
            name=body.model,
            gguf_repo=body.gguf_repo,
            gguf_file=body.gguf_file,
            base_pipeline=body.base_pipeline,
            description=body.description,
            vram=body.vram,
        )
    else:
        dp._used_models.add(body.model)
    return {"status": "added", "model": body.model}


# ------------------------------------------------------------------
# CivitAI model resolution
# ------------------------------------------------------------------

def _parse_civitai_id(url_or_id: str) -> int:
    """Extract a CivitAI model ID from a URL or raw ID string."""
    url_or_id = url_or_id.strip()
    if url_or_id.isdigit():
        return int(url_or_id)
    m = re.search(r'civitai\.com/models/(\d+)', url_or_id)
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot parse CivitAI model ID from: {url_or_id}")


class ResolveCivitaiRequest(BaseModel):
    url: str


@router.post("/diffusion/resolve_civitai")
async def resolve_civitai(request: Request, body: ResolveCivitaiRequest):
    """Resolve a CivitAI model URL/ID to downloadable metadata."""
    from app.models.huggingface import CIVITAI_PIPELINE_MAP

    try:
        model_id = _parse_civitai_id(body.url)
    except ValueError as exc:
        return {"error": str(exc)}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if CIVITAI_API_KEY:
        headers["Authorization"] = f"Bearer {CIVITAI_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://civitai.com/api/v1/models/{model_id}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"CivitAI returned {exc.response.status_code}"}
    except Exception as exc:
        return {"error": str(exc)}

    versions = []
    for v in data.get("modelVersions", []):
        base_model = v.get("baseModel", "")
        pipeline_class = CIVITAI_PIPELINE_MAP.get(base_model, "StableDiffusionXLPipeline")
        files = []
        for f in v.get("files", []):
            fmt = (f.get("metadata") or {}).get("format", "")
            if fmt in ("SafeTensor", "PickleTensor", ""):
                files.append({
                    "name": f.get("name", ""),
                    "size_kb": f.get("sizeKb"),
                    "format": fmt or "Other",
                    "fp": (f.get("metadata") or {}).get("fp", ""),
                })
        download_url = v.get("downloadUrl", "")
        if files:
            versions.append({
                "id": v["id"],
                "name": v.get("name", ""),
                "base_model": base_model,
                "pipeline_class": pipeline_class,
                "download_url": download_url,
                "files": files,
            })

    return {
        "name": data.get("name", ""),
        "type": data.get("type", ""),
        "model_id": model_id,
        "versions": versions,
    }


# ------------------------------------------------------------------
# Audio serving + generation
# ------------------------------------------------------------------

AUDIO_DIR = DATA_DIR / "audio"


class GenerateAudioRequest(BaseModel):
    prompt: str
    model: str = ""
    duration: float = 10.0
    guidance_scale: float = 3.0
    filename: str = ""
    batch_count: int = 1


@router.get("/audio")
async def list_audio():
    """List generated audio files."""
    if not AUDIO_DIR.exists():
        return []
    files = sorted(AUDIO_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        if not f.is_file() or f.suffix == ".json":
            continue
        entry = {
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
            "url": f"/api/audio/{f.name}",
            "duration": None,
            "meta": None,
        }
        # Read WAV header to get actual duration
        try:
            import wave
            with wave.open(str(f), 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    entry["duration"] = round(frames / rate, 2)
        except Exception:
            pass
        # Load sidecar metadata
        meta_path = f.with_suffix(".json")
        if meta_path.exists():
            try:
                entry["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        result.append(entry)
    return result


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve a generated audio file."""
    safe = Path(filename).name
    filepath = AUDIO_DIR / safe
    if not filepath.exists() or not filepath.is_file():
        return {"error": "Audio not found"}
    return FileResponse(filepath, media_type="audio/wav")


@router.get("/audio_gen/status")
async def audio_status(request: Request):
    """Get audio pipeline status."""
    ap = request.app.state.mesh.audio_provider
    return ap.status()


@router.get("/audio_gen/models")
async def audio_models(request: Request):
    """List available audio generation models."""
    ap = request.app.state.mesh.audio_provider
    return ap.available_models()


@router.post("/audio_gen/generate")
async def audio_generate(request: Request, body: GenerateAudioRequest):
    """Generate audio directly from a prompt."""
    ap = request.app.state.mesh.audio_provider
    try:
        results = await ap.generate_audio(
            prompt=body.prompt,
            model=body.model,
            duration=body.duration,
            guidance_scale=body.guidance_scale,
            filename=body.filename,
            batch_count=body.batch_count,
        )
        return {"clips": results, "count": len(results)}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/audio_gen/unload")
async def audio_unload(request: Request):
    """Unload audio pipeline to free VRAM."""
    ap = request.app.state.mesh.audio_provider
    result = await ap.unload()
    return {"status": result}


@router.post("/audio_gen/load")
async def audio_load(request: Request, body: LoadModelRequest):
    """Load (swap to) an audio pipeline model."""
    ap = request.app.state.mesh.audio_provider
    try:
        result = await ap.load(body.model)
        return {"status": result}
    except Exception as exc:
        return {"error": str(exc)}


class AddAudioModelRequest(BaseModel):
    model: str
    source: str = "huggingface"  # "huggingface", "civitai", "ollama"


@router.post("/audio_gen/add_model")
async def audio_add_model(request: Request, body: AddAudioModelRequest):
    """Add a custom model to the tracked list without loading it."""
    ap = request.app.state.mesh.audio_provider
    ap._used_models.add(body.model)
    return {"status": "added", "model": body.model}


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
