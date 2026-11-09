"""In-process fan-out for `/ws/events`.

Publishing is synchronous and side-effect free besides the queue. Nothing
here talks to an exchange.
"""

from __future__ import annotations

import asyncio
from typing import Any

from hypergrok.logging_config import redact
from hypergrok.serialize import to_jsonable


class EventBus:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.history: list[dict[str, Any]] = []

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        safe = redact(to_jsonable(event))
        self.history.append(safe)
        if len(self.history) > 500:
            self.history = self.history[-500:]
        queues = list(self._queues)
        loop = self._loop
        if loop is None or not queues:
            return

        def _fanout() -> None:
            for queue in queues:
                queue.put_nowait(safe)

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            _fanout()
        else:
            loop.call_soon_threadsafe(_fanout)
