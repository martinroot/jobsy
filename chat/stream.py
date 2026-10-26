"""WebSocket stream for jobsy chat.

Forwards order events to the chat frontend in real time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from bridge.events import events as bridge_events


class EventStream:
    """In-memory event broadcaster for a single order."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, client_id: str) -> asyncio.Queue:
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue()
            self._queues[client_id] = q
            return q

    async def unsubscribe(self, client_id: str) -> None:
        async with self._lock:
            self._queues.pop(client_id, None)

    async def publish(self, order_number: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._queues.values())
        for q in queues:
            try:
                q.put_nowait(event)
            except Exception:
                pass


stream = EventStream()


def recent_events(order_number: str, after: int = 0, limit: int = 200) -> list[dict]:
    return bridge_events(order_number, after=after, limit=limit)
