"""In-process async pub/sub event bus — replaces Redis."""

from __future__ import annotations

import asyncio
from collections import deque


class Subscription:
    """Async iterator over messages published to a channel."""

    def __init__(
        self,
        queue: asyncio.Queue[str],
        channel: str,
        registry: dict[str, list[asyncio.Queue[str]]],
    ) -> None:
        self._queue = queue
        self._channel = channel
        self._registry = registry

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        return await self._queue.get()

    def unsubscribe(self) -> None:
        subs = self._registry.get(self._channel, [])
        if self._queue in subs:
            subs.remove(self._queue)


class EventBus:
    """Pub/sub with message replay and a small key-value store."""

    def __init__(self, history_size: int = 500) -> None:
        self._subs: dict[str, list[asyncio.Queue[str]]] = {}
        self._history: dict[str, deque[str]] = {}
        self._max_history = history_size
        self._store: dict[str, str] = {}

    async def publish(self, channel: str, message: str) -> None:
        buf = self._history.setdefault(channel, deque(maxlen=self._max_history))
        buf.append(message)
        for q in self._subs.get(channel, []):
            q.put_nowait(message)

    def subscribe(self, channel: str) -> Subscription:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subs.setdefault(channel, []).append(q)
        return Subscription(q, channel, self._subs)

    def history(self, channel: str) -> list[str]:
        """Return a copy of the replay buffer for a channel."""
        return list(self._history.get(channel, []))

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)
