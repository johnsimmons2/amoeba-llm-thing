"""Model manager — tracks loaded models and provides the provider to agents."""

from __future__ import annotations

import logging

from app.models import ModelProvider
from app.models.ollama import OllamaProvider
from app.config import OLLAMA_URL

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Singleton that owns the model provider and exposes model operations.

    Currently wraps Ollama. Designed so a HuggingFace/transformers provider
    can be added later behind the same ModelProvider interface.
    """

    def __init__(self) -> None:
        self._provider: ModelProvider = OllamaProvider(OLLAMA_URL)

    @property
    def provider(self) -> ModelProvider:
        return self._provider

    async def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        return await self._provider.chat(model, messages, tools)

    async def chat_stream(self, model: str, messages: list[dict], tools: list[dict] | None = None):
        """Proxy streaming chat to the underlying provider."""
        async for chunk in self._provider.chat_stream(model, messages, tools):
            yield chunk

    async def list_models(self) -> list[dict]:
        return await self._provider.list_models()

    async def pull_model(self, name: str) -> str:
        return await self._provider.pull_model(name)

    async def unload_model(self, name: str) -> str:
        return await self._provider.unload_model(name)

    async def delete_model(self, name: str) -> str:
        return await self._provider.delete_model(name)
