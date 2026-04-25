"""In-memory event bus for streaming updates to WebSocket clients."""

import asyncio
from typing import Any, Dict, Optional, Set


class EventBus:
    """Broadcasts JSON-safe events to any active subscribers."""

    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called from FastAPI startup so thread-safe publish works."""
        self._main_loop = loop

    def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        """Register a subscriber queue and return it."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """Unregister a subscriber queue safely."""
        self._subscribers.discard(queue)

    async def publish(self, event: Dict[str, Any]) -> None:
        """Publish an event to all current subscribers."""
        for subscriber in list(self._subscribers):
            await subscriber.put(event)

    def publish_fire_and_forget(self, event: Dict[str, Any]) -> None:
        """
        Thread-safe publish from worker threads (e.g. Gemini tool callbacks).

        Requires set_main_loop() from app startup.
        """
        if self._main_loop is None or not self._main_loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.publish(event), self._main_loop)


event_bus = EventBus()
