from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bus import EventBus
from app.config import HOST, LOG_LEVEL, PORT, STARTUP_JSON
from app.agents.mesh import AgentMesh
from app.memory.log_store import LogStore
from app.api.routes import router
from app.api.websocket import websocket_logs

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("app")

# Shared singletons
bus = EventBus()
mesh = AgentMesh(bus=bus)
log_store = LogStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with open(STARTUP_JSON) as f:
        startup = json.load(f)

    await log_store.start(bus)
    await mesh.start(startup)
    logger.info("Ready — %d agent(s)", len(mesh.agents))
    yield
    mesh.stop()


app = FastAPI(title="AI Sandbox", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.add_api_websocket_route("/ws/logs", websocket_logs)

# Expose singletons to route handlers via request.app.state
app.state.bus = bus
app.state.mesh = mesh
app.state.log_store = log_store

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
