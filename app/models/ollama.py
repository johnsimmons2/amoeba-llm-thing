"""Ollama model provider — wraps the Ollama REST API."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.models import ModelProvider

logger = logging.getLogger(__name__)


class OllamaProvider(ModelProvider):

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream a chat response.  Yields partial chunks; final chunk has done=True."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Running models (loaded in VRAM)
            try:
                ps = await client.get(f"{self.base_url}/api/ps")
                ps.raise_for_status()
                running = {m["name"] for m in ps.json().get("models", [])}
            except Exception:
                running = set()

            # All available models
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])

        return [
            {
                "name": m["name"],
                "size": m.get("size", 0),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                "family": m.get("details", {}).get("family", ""),
                "loaded": m["name"] in running,
            }
            for m in models
        ]

    async def pull_model(self, name: str) -> str:
        logger.info("Pulling model %s", name)
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/pull",
                json={"name": name, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("status", "ok")

    async def unload_model(self, name: str) -> str:
        """Unload by sending a chat with keep_alive=0."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": name, "messages": [], "keep_alive": 0},
            )
            resp.raise_for_status()
        logger.info("Unloaded model %s", name)
        return f"Unloaded {name}"

    async def delete_model(self, name: str) -> str:
        """Remove a model from local storage."""
        logger.info("Deleting model %s", name)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                "DELETE", f"{self.base_url}/api/delete",
                json={"name": name},
            )
            resp.raise_for_status()
        return f"Deleted {name}"
