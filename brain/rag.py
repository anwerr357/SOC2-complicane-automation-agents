"""RAG retrieval: queries Qdrant for the SOC 2 control text most relevant to a violation description."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient

from brain.embeddings import COLLECTION_NAME, _get_model

log = logging.getLogger(__name__)



@dataclass
class ControlMatch:
    """The closest SOC 2 control for a given violation description."""
    control_id:   str    # e.g. "CC6.7"
    control_name: str    # e.g. "Encryption at rest"
    text:         str    # full AICPA criterion text
    score:        float  # cosine similarity score (0–1, higher = closer)



async def retrieve_control(
    query: str,
    qdrant_url: str,
    *,
    top_k: int = 1,
) -> ControlMatch:
    """Find the most relevant SOC 2 control for a violation description."""
    try:
        model        = _get_model()
        query_vector = list(model.embed([query]))[0].tolist()

        client  = QdrantClient(url=qdrant_url)
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )

        if not results:
            log.warning("Qdrant returned no results for query: %s", query[:80])
            return _unknown_control()

        top      = results[0]
        payload  = top.payload

        match = ControlMatch(
            control_id=payload["control_id"],
            control_name=payload["control_name"],
            text=payload["text"],
            score=top.score,
        )

        log.info(
            "RAG retrieved %s (score=%.3f) for query: %.60s…",
            match.control_id,
            match.score,
            query,
        )
        return match

    except Exception as exc:
        # RAG failure must never crash the pipeline — return a safe fallback
        log.error("RAG retrieval failed: %s — using unknown control fallback.", exc)
        return _unknown_control()


async def retrieve_by_control_id(
    control_id: str,
    qdrant_url: str,
) -> ControlMatch:
    """Fetch a SOC 2 control directly by its ID (e.g. "CC6.7")."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client  = QdrantClient(url=qdrant_url)
        results, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[FieldCondition(
                    key="control_id",
                    match=MatchValue(value=control_id),
                )]
            ),
            limit=1,
            with_payload=True,
        )

        if not results:
            log.warning("Control %s not found in Qdrant.", control_id)
            return _unknown_control(control_id)

        payload = results[0].payload
        log.info("Direct lookup retrieved %s from Qdrant.", control_id)

        return ControlMatch(
            control_id=payload["control_id"],
            control_name=payload["control_name"],
            text=payload["text"],
            score=1.0,   # exact match
        )

    except Exception as exc:
        log.error("retrieve_by_control_id failed for %s: %s", control_id, exc)
        return _unknown_control(control_id)


def _unknown_control(control_id: str = "CC0.0") -> ControlMatch:
    """Safe fallback when Qdrant is unreachable or the ID is not found."""
    return ControlMatch(
        control_id=control_id,
        control_name="Unknown control",
        text=(
            "The entity implements controls to protect information assets. "
            "Review this finding manually and map it to the appropriate "
            "SOC 2 Trust Service Criterion."
        ),
        score=0.0,
    )
