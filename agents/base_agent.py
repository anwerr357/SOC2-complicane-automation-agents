"""Abstract base class for compliance agents: declares streams/controls and runs the shared Redis consumer loop."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from store.redis_streams import ack, consume

log = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all compliance agents."""

    NAME:     str       = "base"
    STREAMS:  list[str] = []
    CONTROLS: list[str] = []

    def __init__(self) -> None:
        self._running = True


    async def run(self) -> None:
        """Start consuming from all subscribed streams concurrently."""
        if not self.STREAMS:
            log.warning("[%s] No streams configured — agent idle.", self.NAME)
            return

        log.info("[%s] Starting — subscribing to %s", self.NAME, self.STREAMS)

        tasks = [
            asyncio.create_task(
                self._consume_stream(stream),
                name=f"{self.NAME}:{stream}",
            )
            for stream in self.STREAMS
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            log.info("[%s] Stopped.", self.NAME)

    def stop(self) -> None:
        """Signal the agent to stop after the current event."""
        self._running = False


    @abstractmethod
    async def handle_event(self, stream: str, event: dict) -> None:
        """Process a single event from a subscribed stream."""


    async def _consume_stream(self, stream: str) -> None:
        """Inner loop for a single stream."""
        consumer_name = f"{self.NAME}-worker"

        async for msg_id, event in consume(stream, self.NAME, consumer_name):
            if not self._running:
                break
            try:
                log.info(
                    "[%s] Received event from '%s': source=%s control=%s",
                    self.NAME,
                    stream,
                    event.get("source", "?"),
                    event.get("control_id", "?"),
                )
                await self.handle_event(stream, event)
                await ack(stream, self.NAME, msg_id)

            except asyncio.CancelledError:
                raise   # let the outer gather handle cancellation

            except Exception as exc:
                # Log the error but do NOT ack — Redis will re-deliver on restart
                log.error(
                    "[%s] Failed to handle event %s from '%s': %s",
                    self.NAME, msg_id, stream, exc,
                )
