"""
scanners/k8s_watcher.py
────────────────────────
Kubernetes watch API client — detects live cluster drift.

Uses kubernetes-asyncio to subscribe to resource change events.
Publishes events to the `k8s.events` Redis Stream.

Key patterns detected:
  - Pod spec edited directly (bypassing Git) → CC8.1
  - Container running as root → CC6.6
  - Container with hostPath volume mounts → CC6.6
  - Missing resource limits → A1.1

Implemented in Week 4.
"""

from __future__ import annotations

# TODO (Week 4): implement K8sWatcher using kubernetes_asyncio.watch.Watch()
# Subscribe to Pods, Deployments, Services, and ConfigMaps
