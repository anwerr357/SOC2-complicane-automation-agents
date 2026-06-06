"""
agents/base_agent.py
────────────────────
Abstract base class for all three compliance agents.

Every agent:
  - declares which Redis Streams it subscribes to  (STREAMS)
  - declares which SOC 2 controls it owns          (CONTROLS)
  - implements handle_event() for its domain logic
  - inherits the Redis consumer loop from BaseAgent.run()

Usage
─────
class PolicyAgent(BaseAgent):
    NAME     = "policy"
    STREAMS  = ["k8s.events", "tf.plans"]
    CONTROLS = ["CC6.1", "CC6.6", "CC6.7", "CC9.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        ...

agent = PolicyAgent()
await agent.run()   # runs forever — call from an asyncio.create_task()
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from store.redis_streams import ack, consume

log = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for all compliance agents.

    Subclasses must define:
        NAME     : str         — agent identifier stored in evidence rows
        STREAMS  : list[str]   — Redis Streams to subscribe to
        CONTROLS : list[str]   — SOC 2 controls this agent is responsible for

    Subclasses must implement:
        handle_event(stream, event) — process one event from any subscribed stream
    """

    NAME:     str       = "base"
    STREAMS:  list[str] = []
    CONTROLS: list[str] = []

    def __init__(self) -> None:
        self._running = True

    # ── Public ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Start consuming from all subscribed streams concurrently.

        Each stream gets its own asyncio task.
        Runs until stop() is called or the task is cancelled.
        """
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

    # ── Abstract ───────────────────────────────────────────────────────────

    @abstractmethod
    async def handle_event(self, stream: str, event: dict) -> None:
        """
        Process a single event from a subscribed stream.

        Parameters
        ──────────
        stream : which stream the event came from (e.g. "k8s.events")
        event  : deserialised event dict (see redis_streams.py event envelope)

        Raise any exception to skip ack — Redis will re-deliver the event
        on the next consumer restart.
        """

    # ── Internal ───────────────────────────────────────────────────────────

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
