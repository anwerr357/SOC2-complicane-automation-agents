"""
agents/policy_agent.py
──────────────────────
Policy Agent — governance watcher for Terraform and Kubernetes YAML.

Domain
──────
Subscribes to the `k8s.events` and `tf.plans` Redis Streams.
Runs the Checkov scanner on every incoming IaC file.
Owns SOC 2 controls: CC6.1, CC6.6, CC6.7, CC9.1.

Implemented in Week 1 (Checkov scanning + evidence logging).
LangGraph state machine added in Week 5.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class PolicyAgent:
    """
    Watches governance policies across all infrastructure.

    Week 1 scope: Checkov scanning triggered via the /scan/checkov HTTP
    endpoint.  Event-bus subscription (Redis Streams) is added in Week 4.
    """

    NAME = "policy"
    STREAMS = ["k8s.events", "tf.plans"]
    CONTROLS = ["CC6.1", "CC6.6", "CC6.7", "CC9.1"]

    async def run(self) -> None:
        """
        Main event loop — subscribe to Redis Streams and dispatch scans.
        Implemented in Week 4 when the event bus is wired up.
        """
        log.info("[PolicyAgent] Starting — waiting for tf.plans and k8s.events…")
        # TODO (Week 4): Redis XREAD consumer group loop
        await asyncio.sleep(0)
