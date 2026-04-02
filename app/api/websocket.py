from __future__ import annotations

import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


async def websocket_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = websocket.app.state.bus
    logger.info("Dashboard connected")

    # Replay recent messages so the UI isn't blank on connect
    for entry in bus.history("agentbus"):
        try:
            await websocket.send_text(entry)
        except Exception:
            return

    # Stream live messages
    sub = bus.subscribe("agentbus")
    try:
        async for message in sub:
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        sub.unsubscribe()
        logger.info("Dashboard disconnected")
