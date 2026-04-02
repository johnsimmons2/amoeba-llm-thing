"""Tool base class shared by all primitive and dynamic tool modules."""

from __future__ import annotations

from typing import Any, Callable, Coroutine


class Tool:
    """A single callable tool exposed to agents."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._func = func

    async def call(self, **kwargs: Any) -> Any:
        return await self._func(**kwargs)

    def to_ollama_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
