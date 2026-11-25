import asyncio
from collections import defaultdict
from typing import Any


class RunEventBus:
    """In-process pub/sub broadcast for real-time SSE run progress events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(run_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(run_id, None)

    async def publish(self, run_id: str, event_payload: dict[str, Any]) -> None:
        subs = list(self._subscribers.get(run_id, ()))
        for queue in subs:
            try:
                queue.put_nowait(event_payload)
            except asyncio.QueueFull:
                # Drop oldest buffered item if consumer is lagging, never block graph execution
                try:
                    queue.get_nowait()
                    queue.put_nowait(event_payload)
                except asyncio.QueueEmpty:
                    pass


class CancellationRegistry:
    """Thread/async-safe cooperative cancellation tracker per run_id."""

    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    def request_cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    def clear(self, run_id: str) -> None:
        self._cancelled.discard(run_id)


event_bus = RunEventBus()
cancellation_registry = CancellationRegistry()
