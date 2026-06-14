"""Cluster Operator Agent: watches live K8s/Prometheus drift; findings are escalated for human review."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent
from agents.remediation import run_remediation_loop

log = logging.getLogger(__name__)

# Maps substrings found in Prometheus alertname → (control_id, control_name).
# Checked in order; first match wins.
_ALERT_CONTROL_MAP: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (
        ("crashloop", "nodenotready", "highmemory", "diskfull", "oomkill", "podpending"),
        ("A1.1", "Availability and redundancy"),
    ),
    (
        ("unauthorized", "suspicious", "malware", "exploit", "intrusion"),
        ("CC6.8", "Unauthorized or malicious software protection"),
    ),
    (
        ("auditlog", "logging", "eventlog", "auditfail"),
        ("CC7.2", "Audit logging and monitoring"),
    ),
]
_DEFAULT_CONTROL = ("CC7.1", "System monitoring and alerting")

_SEVERITY_MAP = {
    "critical": "HIGH",
    "warning": "MEDIUM",
    "info": "LOW",
}


def _map_alert(alertname: str) -> tuple[str, str]:
    lower = alertname.lower()
    for keywords, control in _ALERT_CONTROL_MAP:
        if any(k in lower for k in keywords):
            return control
    return _DEFAULT_CONTROL


def _prom_severity(labels: dict) -> str:
    raw = labels.get("severity", "warning").lower()
    return _SEVERITY_MAP.get(raw, "MEDIUM")


class ClusterOperatorAgent(BaseAgent):
    NAME = "cluster_operator"
    STREAMS = ["k8s.events", "prometheus.alerts"]
    CONTROLS = ["CC7.1", "CC7.2", "A1.1", "CC6.8"]

    async def handle_event(self, stream: str, event: dict) -> None:
        if stream == "prometheus.alerts":
            await self._handle_prometheus(event)
        else:
            await self._handle_k8s(event)


    async def _handle_k8s(self, event: dict) -> None:
        control_id = event.get("control_id", "")
        if control_id not in self.CONTROLS:
            log.debug("[ClusterOperator] Skipping control %s — not owned.", control_id)
            return

        namespace = event.get("namespace", "default")
        fd = {
            "agent_name": self.NAME,
            "scanner_used": "k8s_watch",
            "check_id": event.get("check_id", "K8S_UNKNOWN"),
            "control_id": control_id,
            "control_name": event.get("control_name", ""),
            "resource_name": (
                f"{event.get('resource_kind','')}/{event.get('resource_name','')}"
            ),
            "file_path": f"k8s/{namespace}/{event.get('resource_name','')}",
            "severity": event.get("severity", "MEDIUM"),
            "violation_description": event.get("violation", ""),
            "raw_finding": {
                "check_id": event.get("check_id"),
                "resource_kind": event.get("resource_kind"),
                "resource_name": event.get("resource_name"),
                "namespace": namespace,
                "change_type": event.get("change_type"),
                "violation": event.get("violation", ""),
            },
        }
        log.info(
            "[ClusterOperator] k8s violation: %s on %s [%s]",
            fd["check_id"], fd["resource_name"], control_id,
        )
        outcome = await run_remediation_loop(fd, repo_full_name="", github_token="")
        log.info("[ClusterOperator] %s/%s → %s", control_id, fd["check_id"], outcome.status)


    async def _handle_prometheus(self, event: dict) -> None:
        alertname  = event.get("alertname", "PROM_UNKNOWN")
        namespace  = event.get("namespace", "default")
        resource   = event.get("resource", alertname)
        labels     = event.get("labels", {})
        summary    = event.get("summary", "")
        description = event.get("description", summary)
        severity   = _prom_severity(labels)
        control_id, control_name = _map_alert(alertname)

        fd = {
            "agent_name": self.NAME,
            "scanner_used": "prometheus",
            "check_id": f"PROM_{alertname.upper()}",
            "control_id": control_id,
            "control_name": control_name,
            "resource_name": resource,
            "file_path": f"k8s/{namespace}/{resource}",
            "severity": severity,
            "violation_description": description,
            "raw_finding": {
                "alertname": alertname,
                "labels": labels,
                "summary": summary,
                "description": description,
                "starts_at": event.get("starts_at", ""),
            },
        }
        log.info(
            "[ClusterOperator] Prometheus alert: %s → %s [%s]",
            alertname, control_id, severity,
        )
        # No IaC file to patch — escalated to Slack for human review.
        outcome = await run_remediation_loop(fd, repo_full_name="", github_token="")
        log.info("[ClusterOperator] PROM_%s → %s", alertname, outcome.status)
