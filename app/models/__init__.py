"""Model provider abstraction — interface for LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    """Backend that can serve chat completions for a given model."""

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Send a chat completion request. Returns Ollama-compatible response dict."""

    @abstractmethod
    async def list_models(self) -> list[dict]:
        """Return available models: [{"name": ..., "size": ..., "loaded": bool}, ...]"""

    @abstractmethod
    async def pull_model(self, name: str) -> str:
        """Pull/download a model. Returns status string."""

    @abstractmethod
    async def unload_model(self, name: str) -> str:
        """Unload a model from memory."""
