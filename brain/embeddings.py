"""
brain/embeddings.py
───────────────────
Embeds SOC 2 Trust Service Criteria text into Qdrant at startup.

The 17 TSC criteria relevant to this system are stored as dense vectors.
Every agent queries this collection with the scanner finding description
to retrieve the exact control text before sending it to Claude.

Implemented in Week 3 — Qdrant + RAG pipeline.
"""

from __future__ import annotations

# SOC 2 Trust Service Criteria — source-of-truth text snippets
# These are the canonical control descriptions that get embedded.
# Added here for reference; the embedding logic is Week 3 scope.

SOC2_CRITERIA: dict[str, str] = {
    "CC6.1": (
        "The entity implements logical access security software, infrastructure, "
        "and architectures over protected information assets to protect them from "
        "security events to meet the entity's objectives."
    ),
    "CC6.2": (
        "Prior to issuing system credentials and granting system access, the entity "
        "registers and authorizes new internal and external users whose access is "
        "administered by the entity."
    ),
    "CC6.3": (
        "The entity authorizes, modifies, or removes access to data, software, "
        "functions, and other protected information assets based on approved and "
        "documented access requests and the rules of least privilege."
    ),
    "CC6.6": (
        "The entity implements logical access security measures to protect against "
        "threats from sources outside its system boundaries."
    ),
    "CC6.7": (
        "The entity restricts the transmission, movement, and removal of information "
        "to authorized internal and external users and processes, and protects it "
        "during transmission, movement, or removal to meet the entity's objectives."
    ),
    "CC6.8": (
        "The entity implements controls to prevent or detect and act upon the "
        "introduction of unauthorized or malicious software to meet the entity's "
        "objectives."
    ),
    "CC7.1": (
        "To meet its objectives, the entity uses detection and monitoring procedures "
        "to identify (1) changes to configurations that result in the introduction of "
        "new vulnerabilities, and (2) susceptibilities to newly discovered "
        "vulnerabilities."
    ),
    "CC7.2": (
        "The entity monitors system components and the operation of those components "
        "for anomalies that are indicative of malicious acts, natural disasters, and "
        "errors affecting the entity's ability to meet its objectives."
    ),
    "CC8.1": (
        "The entity authorizes, designs, develops or acquires, configures, documents, "
        "tests, approves, and implements changes to infrastructure, data, software, "
        "and procedures to meet its change management objective."
    ),
    "CC9.1": (
        "The entity identifies, selects, and develops risk mitigation activities for "
        "risks arising from potential business disruptions."
    ),
    "A1.1": (
        "The entity maintains, monitors, and evaluates current processing capacity "
        "and use of system components (infrastructure, data, and software) to manage "
        "capacity demand and to enable the implementation of additional capacity to "
        "help meet its objectives."
    ),
}

# TODO (Week 3): implement embed_controls() using sentence-transformers or
# the Anthropic embeddings API, and upsert into Qdrant collection "soc2_controls"
