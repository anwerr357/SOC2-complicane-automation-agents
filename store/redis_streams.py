"""Redis Streams client (publish/consume/ack) shared by all agents and event publishers."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import redis.asyncio as aioredis

log = logging.getLogger(__name__)


_redis: aioredis.Redis | None = None


async def init_redis(redis_url: str) -> None:
    """Create the async Redis client."""
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



def _serialise(event: dict) -> dict[str, str]:
    """Flatten a dict for Redis Streams storage."""
    flat: dict[str, str] = {}
    for key, value in event.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value)
        else:
            flat[key] = str(value)
    return flat


def _deserialise(fields: dict[str, str]) -> dict:
    """Reverse of _serialise — try to JSON-decode each value."""
    event: dict = {}
    for key, value in fields.items():
        try:
            event[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            event[key] = value
    return event



async def publish(stream: str, event: dict) -> str:
    """Publish an event to a Redis Stream."""
    r = _get_redis()

    # Inject standard envelope fields if not present
    event.setdefault("event_id",  str(uuid.uuid4()))
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("stream",    stream)

    msg_id = await r.xadd(stream, _serialise(event))
    log.info("Published to %s [%s] event_id=%s", stream, msg_id, event["event_id"])
    return msg_id


async def ensure_consumer_group(stream: str, group: str) -> None:
    """Create a consumer group if it doesn't already exist."""
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
    """Async generator that yields (msg_id, event) tuples from a stream."""
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
    """Acknowledge a message — tell Redis this consumer processed it successfully."""
    r = _get_redis()
    await r.xack(stream, group, msg_id)
    log.debug("ACK %s on %s/%s", msg_id, stream, group)


async def stream_length(stream: str) -> int:
    """Return the number of messages currently in a stream."""
    r = _get_redis()
    return await r.xlen(stream)
