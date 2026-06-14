"""Embeds the SOC 2 control texts into Qdrant at startup (idempotent)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

log = logging.getLogger(__name__)


COLLECTION_NAME = "soc2_controls"
EMBEDDING_MODEL  = "BAAI/bge-small-en-v1.5"
VECTOR_SIZE      = 384   # output dimension of bge-small-en-v1.5


# Source: AICPA Trust Services Criteria 2017.
# Each entry is (numeric_id, control_id, control_name, full_text).
# numeric_id is used as the Qdrant point ID (must be integer or UUID).

@dataclass
class ControlEntry:
    id:           int
    control_id:   str    # e.g. "CC6.7"
    control_name: str    # e.g. "Encryption at rest"
    text:         str    # full AICPA criterion text


SOC2_CONTROLS: list[ControlEntry] = [
    ControlEntry(
        id=1,
        control_id="CC6.1",
        control_name="Logical and physical access controls",
        text=(
            "The entity implements logical access security software, "
            "infrastructure, and architectures over protected information "
            "assets to protect them from security events to meet the "
            "entity's objectives. This includes controls to identify and "
            "authenticate users, restrict access to authorized users, and "
            "prevent unauthorized access to systems and data."
        ),
    ),
    ControlEntry(
        id=2,
        control_id="CC6.2",
        control_name="Authentication and multi-factor authentication",
        text=(
            "Prior to issuing system credentials and granting system access, "
            "the entity registers and authorizes new internal and external "
            "users whose access is administered by the entity. For those "
            "users whose access is administered by the entity, user system "
            "credentials are removed when user access is no longer authorized."
        ),
    ),
    ControlEntry(
        id=3,
        control_id="CC6.3",
        control_name="Access removal and user lifecycle management",
        text=(
            "The entity authorizes, modifies, or removes access to data, "
            "software, functions, and other protected information assets "
            "based on approved and documented access requests and the rules "
            "of least privilege. Access is removed when no longer required "
            "or when employees leave the organization."
        ),
    ),
    ControlEntry(
        id=4,
        control_id="CC6.6",
        control_name="Least privilege and logical access restriction",
        text=(
            "The entity implements logical access security measures to "
            "protect against threats from sources outside its system "
            "boundaries. This includes restricting access to the minimum "
            "necessary permissions — the principle of least privilege — "
            "and preventing overly permissive IAM policies, wildcard "
            "permissions, and excessive administrative rights."
        ),
    ),
    ControlEntry(
        id=5,
        control_id="CC6.7",
        control_name="Encryption at rest",
        text=(
            "The entity restricts the transmission, movement, and removal "
            "of information to authorized internal and external users and "
            "processes, and protects it during transmission, movement, or "
            "removal to meet the entity's objectives. Data stored at rest "
            "must be encrypted using approved algorithms such as AES-256 "
            "or AWS KMS. This applies to S3 buckets, RDS instances, "
            "DynamoDB tables, EBS volumes, and any other storage resources."
        ),
    ),
    ControlEntry(
        id=6,
        control_id="CC6.8",
        control_name="Unauthorized or malicious software protection",
        text=(
            "The entity implements controls to prevent or detect and act "
            "upon the introduction of unauthorized or malicious software "
            "to meet the entity's objectives. This includes preventing "
            "containers from running as root, restricting privilege "
            "escalation, and enforcing read-only root filesystems in "
            "Kubernetes workloads."
        ),
    ),
    ControlEntry(
        id=7,
        control_id="CC7.1",
        control_name="System monitoring and alerting",
        text=(
            "To meet its objectives, the entity uses detection and monitoring "
            "procedures to identify changes to configurations that result in "
            "the introduction of new vulnerabilities, and susceptibilities to "
            "newly discovered vulnerabilities. This includes enabling access "
            "logging on S3 buckets, CloudTrail for API activity, and "
            "VPC Flow Logs for network monitoring."
        ),
    ),
    ControlEntry(
        id=8,
        control_id="CC7.2",
        control_name="Audit logging and monitoring",
        text=(
            "The entity monitors system components and the operation of those "
            "components for anomalies that are indicative of malicious acts, "
            "natural disasters, and errors affecting the entity's ability to "
            "meet its objectives. All data modification operations must be "
            "recorded in an immutable audit log. Application functions that "
            "write to a database must call audit_log() to record the action, "
            "the actor, and the timestamp."
        ),
    ),
    ControlEntry(
        id=9,
        control_id="CC8.1",
        control_name="Change management and authorised changes",
        text=(
            "The entity authorizes, designs, develops or acquires, configures, "
            "documents, tests, approves, and implements changes to "
            "infrastructure, data, software, and procedures to meet its change "
            "management objective. All infrastructure changes must go through "
            "a reviewed pull request and must not be applied directly to "
            "production environments."
        ),
    ),
    ControlEntry(
        id=10,
        control_id="CC9.1",
        control_name="Risk assessment and mitigation",
        text=(
            "The entity identifies, selects, and develops risk mitigation "
            "activities for risks arising from potential business disruptions. "
            "This includes regularly assessing infrastructure for "
            "misconfigurations, unrotated keys, exposed secrets, and "
            "other security risks that could lead to a breach."
        ),
    ),
    ControlEntry(
        id=11,
        control_id="A1.1",
        control_name="Availability and redundancy",
        text=(
            "The entity maintains, monitors, and evaluates current processing "
            "capacity and use of system components to manage capacity demand "
            "and to enable the implementation of additional capacity to help "
            "meet its objectives. Kubernetes workloads must define liveness "
            "and readiness probes. Services must define resource limits to "
            "prevent a single workload from exhausting cluster resources."
        ),
    ),
]


# fastembed caches the model weights after the first download.

_embedding_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        log.info("Loading fastembed model %s…", EMBEDDING_MODEL)
        _embedding_model = TextEmbedding(EMBEDDING_MODEL)
        log.info("Embedding model loaded.")
    return _embedding_model



async def embed_controls(qdrant_url: str) -> None:
    """Embed all SOC 2 controls and upsert them into Qdrant."""
    client = QdrantClient(url=qdrant_url)

    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,  # cosine similarity for text
            ),
        )
        log.info("Created Qdrant collection '%s'.", COLLECTION_NAME)
    else:
        # Check if already populated
        count = client.count(collection_name=COLLECTION_NAME).count
        if count >= len(SOC2_CONTROLS):
            log.info(
                "Collection '%s' already has %d points — skipping embed.",
                COLLECTION_NAME, count,
            )
            return

    model  = _get_model()
    texts  = [c.text for c in SOC2_CONTROLS]
    vectors = list(model.embed(texts))   # returns list of numpy arrays

    points = [
        PointStruct(
            id=control.id,
            vector=vectors[i].tolist(),
            payload={
                "control_id":   control.control_id,
                "control_name": control.control_name,
                "text":         control.text,
            },
        )
        for i, control in enumerate(SOC2_CONTROLS)
    ]

    client.upsert(collection_name=COLLECTION_NAME, points=points)

    log.info(
        "Embedded %d SOC 2 controls into Qdrant collection '%s'.",
        len(points),
        COLLECTION_NAME,
    )
