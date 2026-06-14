"""Best-effort Slack delivery for escalated findings; failures are logged and swallowed, never raised."""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

SLACK_BOT_TOKEN     = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_ALERT_CHANNEL = os.environ.get("SLACK_ALERT_CHANNEL", "#compliance-alerts")
SLACK_POST_URL      = "https://slack.com/api/chat.postMessage"

# Slack section text limit is 3000 chars; leave headroom.
_MAX_BLOCK_CHARS = 2900


def _build_blocks(
    *,
    check_id: str,
    control_id: str,
    control_name: str,
    severity: str,
    resource_name: str,
    agent_name: str,
    explanation: str,
    event_id: str,
    detail: str,
) -> list[dict]:
    """Build the Block Kit `blocks` list for an escalation. Pure — no network."""
    body = (explanation or "")[:_MAX_BLOCK_CHARS]
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Compliance escalation — {control_id}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                {"type": "mrkdwn", "text": f"*Resource:*\n{resource_name}"},
                {"type": "mrkdwn", "text": f"*Check:*\n{check_id}"},
                {"type": "mrkdwn", "text": f"*Agent:*\n{agent_name}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Control:*\n{control_id} — {control_name}",
                },
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"event `{event_id}` · {detail}"}
            ],
        },
    ]


async def post_escalation(
    *,
    check_id: str,
    control_id: str,
    control_name: str,
    severity: str,
    resource_name: str,
    agent_name: str,
    explanation: str,
    event_id: str,
    detail: str,
) -> bool:
    """Post a Block Kit escalation to Slack."""
    if not SLACK_BOT_TOKEN:
        log.debug("[slack] SLACK_BOT_TOKEN unset — skipping escalation notify")
        return False

    blocks = _build_blocks(
        check_id=check_id,
        control_id=control_id,
        control_name=control_name,
        severity=severity,
        resource_name=resource_name,
        agent_name=agent_name,
        explanation=explanation,
        event_id=event_id,
        detail=detail,
    )
    payload = {
        "channel": SLACK_ALERT_CHANNEL,
        "text": (
            f"🚨 Compliance escalation — {control_id} "
            f"({severity}) on {resource_name}"
        ),
        "blocks": blocks,
    }

    return await _post(payload, event_id, kind="escalation")


async def post_remediation(
    *,
    check_id: str,
    control_id: str,
    control_name: str,
    severity: str,
    resource_name: str,
    agent_name: str,
    explanation: str,
    event_id: str,
    pr_url: str,
) -> bool:
    """Post a Block Kit auto-remediation notice (fix PR opened) to Slack."""
    if not SLACK_BOT_TOKEN:
        log.debug("[slack] SLACK_BOT_TOKEN unset — skipping remediation notify")
        return False

    body = (explanation or "")[:_MAX_BLOCK_CHARS]
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
            "text": f"✅ Auto-remediated — {control_id}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
            {"type": "mrkdwn", "text": f"*Resource:*\n{resource_name}"},
            {"type": "mrkdwn", "text": f"*Check:*\n{check_id}"},
            {"type": "mrkdwn", "text": f"*Agent:*\n{agent_name}"},
            {"type": "mrkdwn", "text": f"*Control:*\n{control_id} — {control_name}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Fix PR:* <{pr_url}|{pr_url}>"}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"event `{event_id}` · remediation PR opened"}]},
    ]
    payload = {
        "channel": SLACK_ALERT_CHANNEL,
        "text": f"✅ Auto-remediated {control_id} ({severity}) on {resource_name} — {pr_url}",
        "blocks": blocks,
    }
    return await _post(payload, event_id, kind="remediation")


async def _post(payload: dict, event_id: str, *, kind: str) -> bool:
    """POST a message to Slack; best-effort — log and swallow any failure."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                SLACK_POST_URL,
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json=payload,
            )
        data = resp.json()
        if data.get("ok") is True:
            log.info("[slack] %s posted for event %s", kind, event_id)
            return True
        log.warning("[slack] %s post failed: %s", kind, data.get("error"))
        return False
    except Exception as exc:
        log.warning("[slack] %s notify failed: %s", kind, exc)
        return False
