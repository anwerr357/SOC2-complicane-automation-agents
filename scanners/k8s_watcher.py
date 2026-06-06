"""
scanners/k8s_watcher.py
────────────────────────
Mock Kubernetes event publisher — Week 4 (no real cluster needed).

In production (Week 5+), this module would use the kubernetes-asyncio
watch API to stream real resource change events from the cluster.

For Week 4, it publishes realistic mock events to the `k8s.events`
Redis Stream so the Policy Agent and Cluster Operator Agent can be
developed and tested without a running cluster.

Mock events simulate the most common SOC 2 violations found in
Kubernetes workloads:

    CC6.6  — container running as root / no securityContext
    CC6.6  — container with hostPath volume mount
    CC6.8  — privileged container (security boundary bypass)
    A1.1   — deployment missing resource limits / liveness probe
    CC8.1  — resource modified directly (bypassing GitOps)
    CC7.2  — pod spec changed without audit trail

Usage
─────
    from scanners.k8s_watcher import publish_mock_events
    await publish_mock_events(count=5)     # publishes 5 random events
    await publish_mock_events(count=None)  # publishes all 8 events
"""

from __future__ import annotations

import asyncio
import logging
import random

from store.redis_streams import publish

log = logging.getLogger(__name__)

STREAM = "k8s.events"


# ── Mock event templates ───────────────────────────────────────────────────
# Each entry represents a realistic K8s drift scenario.
# In production these would come from the kubernetes-asyncio watch API.

MOCK_EVENTS: list[dict] = [
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "api-server",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_30",
        "control_id":     "CC6.6",
        "control_name":   "Least privilege and logical access restriction",
        "severity":       "HIGH",
        "violation":      (
            "Container 'api' in Deployment 'api-server' has no securityContext. "
            "It may be running as root (UID 0), violating the principle of least privilege."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "worker",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_11",
        "control_id":     "A1.1",
        "control_name":   "Availability and redundancy",
        "severity":       "MEDIUM",
        "violation":      (
            "Container 'worker' in Deployment 'worker' has no CPU or memory limits. "
            "A runaway process can exhaust cluster resources and cause an outage."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Pod",
        "resource_name":  "debug-pod",
        "namespace":      "production",
        "change_type":    "ADDED",
        "check_id":       "CKV_K8S_6",
        "control_id":     "CC6.8",
        "control_name":   "Unauthorized or malicious software protection",
        "severity":       "HIGH",
        "violation":      (
            "Pod 'debug-pod' is running with privileged=true. "
            "A privileged container has full access to the host kernel — "
            "equivalent to root on the node."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "frontend",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_8",
        "control_id":     "A1.1",
        "control_name":   "Availability and redundancy",
        "severity":       "MEDIUM",
        "violation":      (
            "Deployment 'frontend' has no livenessProbe defined. "
            "Kubernetes cannot detect and restart crashed containers automatically."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "payment-service",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_28",
        "control_id":     "CC6.6",
        "control_name":   "Least privilege and logical access restriction",
        "severity":       "HIGH",
        "violation":      (
            "Container 'payment' in Deployment 'payment-service' mounts "
            "hostPath '/etc/ssl/certs'. Direct host filesystem access "
            "violates container isolation and least-privilege principles."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "api-server",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_37",
        "control_id":     "CC6.8",
        "control_name":   "Unauthorized or malicious software protection",
        "severity":       "MEDIUM",
        "violation":      (
            "Deployment 'api-server' does not set allowPrivilegeEscalation=false. "
            "A process inside the container can gain more privileges than its parent."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "ConfigMap",
        "resource_name":  "app-config",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CC8.1_DRIFT",
        "control_id":     "CC8.1",
        "control_name":   "Change management and authorised changes",
        "severity":       "HIGH",
        "violation":      (
            "ConfigMap 'app-config' was modified directly in the cluster "
            "(kubectl apply/edit) without a corresponding Git commit or PR. "
            "This bypasses the GitOps change management process."
        ),
    },
    {
        "source":         "k8s_watch",
        "resource_kind":  "Deployment",
        "resource_name":  "auth-service",
        "namespace":      "production",
        "change_type":    "MODIFIED",
        "check_id":       "CKV_K8S_43",
        "control_id":     "CC7.2",
        "control_name":   "Audit logging and monitoring",
        "severity":       "MEDIUM",
        "violation":      (
            "Deployment 'auth-service' image tag is 'latest'. "
            "Mutable tags prevent a reliable audit trail — "
            "the exact image deployed cannot be determined from the spec alone."
        ),
    },
]


# ── Publisher ──────────────────────────────────────────────────────────────

async def publish_mock_events(
    count: int | None = None,
    *,
    delay_seconds: float = 0.5,
) -> list[str]:
    """
    Publish mock K8s drift events to the `k8s.events` Redis Stream.

    Parameters
    ──────────
    count         : number of events to publish.
                    None = publish all 8 mock events.
                    Any integer = pick that many at random.
    delay_seconds : pause between events (simulates real-time drift).

    Returns
    ───────
    List of Redis message IDs that were published.
    """
    events = MOCK_EVENTS if count is None else random.sample(
        MOCK_EVENTS, min(count, len(MOCK_EVENTS))
    )

    msg_ids: list[str] = []

    for event in events:
        msg_id = await publish(STREAM, event.copy())
        msg_ids.append(msg_id)
        log.info(
            "Mock K8s event published: %s/%s [%s] → %s",
            event["resource_kind"],
            event["resource_name"],
            event["control_id"],
            msg_id,
        )
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    log.info("Published %d mock K8s events to '%s'.", len(msg_ids), STREAM)
    return msg_ids
