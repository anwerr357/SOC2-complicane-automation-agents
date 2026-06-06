"""
store/redis_streams.py
──────────────────────
Redis Streams client — shared by all agents and event publishers.

Three core operations
─────────────────────
publish(stream, event)
    XADD — drop an event into a stream.
    Called by: k8s_watcher, api/webhooks (GitHub events), CI triggers.

consume(stream, group, consumer)
    XREADGROUP async generator — yields (msg_id, event) tuples forever.
    Called by: every agent's run() loop.

ack(stream, group, msg_id)
    XACK — mark an event as successfully processed.
    Called by: agents after handle_event() completes without error.

Session lifecycle
─────────────────
Call init_redis(url) once from the FastAPI lifespan.
Call close_redis() on shutdown.
All other functions use the module-level client automatically.

Event envelope
──────────────
Every event published through this module gets two fields injected:
    event_id  : UUID v4 (generated if not supplied)
    timestamp : ISO 8601 UTC string

Nested dicts/lists in the payload are JSON-serialised because Redis
Streams only store flat string key-value pairs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import redis.asyncio as aioredis

log = logging.getLogger(__name__)

# ── Module-level client ────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None


async def init_redis(redis_url: str) -> None:
    """
    Create the async Redis client.
    Call once from the FastAPI lifespan before any publish/consume calls.
    """
    global _redis
    _redis = aioredis.from_url(
        redis_url,
        decode_responses=True,   # return str not bytes
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    await _redis.ping()
    log.info("Redis connected at %s", redis_url)


async def close_redis() -> None:
    """Close the Redis connection on shutdown."""
    if _redis:
        await _redis.aclose()
        log.info("Redis connection closed.")


def _get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first.")
    return _redis


# ── Serialisation helpers ──────────────────────────────────────────────────

def _serialise(event: dict) -> dict[str, str]:
    """
    Flatten a dict for Redis Streams storage.
    Nested dicts/lists are JSON-encoded. All values become strings.
    """
    flat: dict[str, str] = {}
    for key, value in event.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value)
        else:
            flat[key] = str(value)
    return flat


def _deserialise(fields: dict[str, str]) -> dict:
    """
    Reverse of _serialise — try to JSON-decode each value.
    Values that are not valid JSON are returned as plain strings.
    """
    event: dict = {}
    for key, value in fields.items():
        try:
            event[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            event[key] = value
    return event


# ── Core operations ────────────────────────────────────────────────────────

async def publish(stream: str, event: dict) -> str:
    """
    Publish an event to a Redis Stream.

    Parameters
    ──────────
    stream : stream name, e.g. "k8s.events"
    event  : dict — nested values are JSON-serialised automatically

    Returns the Redis-assigned message ID (e.g. "1716979200000-0").
    """
    r = _get_redis()

    # Inject standard envelope fields if not present
    event.setdefault("event_id",  str(uuid.uuid4()))
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("stream",    stream)

    msg_id = await r.xadd(stream, _serialise(event))
    log.info("Published to %s [%s] event_id=%s", stream, msg_id, event["event_id"])
    return msg_id


async def ensure_consumer_group(stream: str, group: str) -> None:
    """
    Create a consumer group if it doesn't already exist.

    Uses MKSTREAM so the stream is created automatically if it is new.
    Safe to call repeatedly — BUSYGROUP error (group exists) is silently ignored.
    """
    r = _get_redis()
    try:
        # id="0" means the group starts from the beginning of the stream
        # so agents that restart will re-process any pending (unacked) messages
        await r.xgroup_create(stream, group, id="0", mkstream=True)
        log.info("Consumer group '%s' created on stream '%s'.", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            pass   # group already exists — that's fine
        else:
            raise


async def consume(
    stream: str,
    group:  str,
    consumer: str,
    *,
    block_ms: int = 2000,
    batch:    int = 10,
) -> AsyncGenerator[tuple[str, dict], None]:
    """
    Async generator that yields (msg_id, event) tuples from a stream.

    Runs forever — use inside an asyncio task.
    Stops cleanly when the enclosing task is cancelled.

    Parameters
    ──────────
    stream   : stream name, e.g. "k8s.events"
    group    : consumer group name, e.g. "policy_agent"
    consumer : unique consumer name within the group, e.g. "worker-1"
    block_ms : how long to wait for new events if the stream is empty (ms)
    batch    : max events to fetch per XREADGROUP call

    Usage
    ─────
    async for msg_id, event in consume("k8s.events", "policy_agent", "w1"):
        await handle(event)
        await ack("k8s.events", "policy_agent", msg_id)
    """
    await ensure_consumer_group(stream, group)
    r = _get_redis()

    log.info("Agent '%s' consuming '%s' (group=%s)", consumer, stream, group)

    while True:
        try:
            # ">" means: give me only NEW messages not yet delivered to this group
            results = await r.xreadgroup(
                group,
                consumer,
                {stream: ">"},
                count=batch,
                block=block_ms,
            )

            if not results:
                # Timeout with no new messages — loop again
                continue

            for _stream_name, messages in results:
                for msg_id, fields in messages:
                    yield msg_id, _deserialise(fields)

        except asyncio.CancelledError:
            log.info("Consumer '%s' on '%s' cancelled — shutting down.", consumer, stream)
            break
        except Exception as exc:
            log.error("Consume error on '%s': %s — retrying in 2s.", stream, exc)
            await asyncio.sleep(2)


async def ack(stream: str, group: str, msg_id: str) -> None:
    """
    Acknowledge a message — tell Redis this consumer processed it successfully.

    Call this AFTER handle_event() completes without error.
    If you don't call ack(), Redis will re-deliver the message when the
    consumer restarts (crash-safe retry behaviour).
    """
    r = _get_redis()
    await r.xack(stream, group, msg_id)
    log.debug("ACK %s on %s/%s", msg_id, stream, group)


async def stream_length(stream: str) -> int:
    """Return the number of messages currently in a stream."""
    r = _get_redis()
    return await r.xlen(stream)
