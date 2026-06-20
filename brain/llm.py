"""Claude API client shared by all agents: explanations and file patches."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
    return _client


class ExplanationResult(BaseModel):
    violation_summary:  str
    business_impact:    str
    remediation_steps:  str


@dataclass
class PatchResult:
    patched_content:  str
    changes_summary:  str
    used_llm:         bool


_EXPLANATION_TOOL = {
    "name": "submit_explanation",
    "description": (
        "Submit a structured SOC 2 violation explanation. "
        "Always call this tool — never return plain text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["violation_summary", "business_impact", "remediation_steps"],
        "properties": {
            "violation_summary": {
                "type": "string",
                "description": (
                    "One sentence describing what is wrong with the resource. "
                    "Name the specific resource and the missing configuration."
                ),
            },
            "business_impact": {
                "type": "string",
                "description": (
                    "Two to three sentences explaining why this matters — "
                    "what data is at risk, what regulation is broken, "
                    "and what an auditor would flag."
                ),
            },
            "remediation_steps": {
                "type": "string",
                "description": (
                    "Concrete, actionable steps to fix the violation. "
                    "Reference the specific Terraform resource or code change needed."
                ),
            },
        },
    },
}

_PATCH_TOOL = {
    "name": "submit_patch",
    "description": (
        "Submit the corrected file content. "
        "Always call this tool — never return plain text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["patched_content", "changes_summary"],
        "properties": {
            "patched_content": {
                "type": "string",
                "description": (
                    "The complete corrected file content. "
                    "Must be valid Terraform HCL or YAML. "
                    "Include the entire file — not just the changed section."
                ),
            },
            "changes_summary": {
                "type": "string",
                "description": (
                    "One sentence describing exactly what was added or changed."
                ),
            },
        },
    },
}


def build_system_prompt(control_text: str, control_id: str, control_name: str) -> str:
    """Build the cached system prompt embedding the SOC 2 control text."""
    return (
        "You are a senior SOC 2 compliance engineer with deep expertise in "
        "AWS infrastructure security, Terraform, and Kubernetes.\n\n"
        "You are reviewing infrastructure code for violations of SOC 2 "
        "Trust Service Criteria. Your explanations must be precise, "
        "auditor-grade, and grounded in the exact control text below.\n\n"
        f"## Relevant SOC 2 Control\n\n"
        f"**{control_id} — {control_name}**\n\n"
        f"{control_text}\n\n"
        "## Instructions\n\n"
        "- Always call the provided tool — never respond with plain text.\n"
        "- Be specific: name the exact resource, file, and missing configuration.\n"
        "- Use the control text above as your grounding — quote it when relevant.\n"
        "- Remediation steps must reference the exact Terraform resource type needed."
    )


async def generate_explanation(
    *,
    check_id:     str,
    control_id:   str,
    control_name: str,
    control_text: str,
    resource_name: str,
    file_path:    str,
    severity:     str,
    check_type:   str = "terraform",
) -> ExplanationResult:
    """Generate a plain-English explanation of a SOC 2 violation."""
    client = _get_client()

    system_prompt = build_system_prompt(control_text, control_id, control_name)

    user_message = (
        f"Explain the following SOC 2 violation:\n\n"
        f"- **Check ID:** {check_id}\n"
        f"- **Resource:** `{resource_name}`\n"
        f"- **File:** `{file_path}`\n"
        f"- **Severity:** {severity}\n"
        f"- **Infrastructure type:** {check_type}\n\n"
        f"The resource `{resource_name}` failed Checkov check `{check_id}`, "
        f"which maps to SOC 2 criterion **{control_id} ({control_name})**.\n\n"
        f"Call `submit_explanation` with your analysis."
    )

    try:
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_EXPLANATION_TOOL],
            tool_choice={"type": "tool", "name": "submit_explanation"},
            messages=[{"role": "user", "content": user_message}],
        )

        tool_block = next(
            b for b in response.content if b.type == "tool_use"
        )
        args = tool_block.input

        log.info(
            "Generated explanation for %s/%s (cache=%s)",
            control_id,
            check_id,
            getattr(response.usage, "cache_read_input_tokens", 0) > 0,
        )

        return ExplanationResult(
            violation_summary=args["violation_summary"],
            business_impact=args["business_impact"],
            remediation_steps=args["remediation_steps"],
        )

    except Exception as exc:
        log.error("generate_explanation failed for %s: %s", check_id, exc)
        return ExplanationResult(
            violation_summary=(
                f"Resource `{resource_name}` failed check {check_id} "
                f"({control_id} — {control_name})."
            ),
            business_impact=(
                f"This violation has severity {severity} and must be "
                f"remediated to meet SOC 2 criterion {control_id}."
            ),
            remediation_steps="Review and fix the resource configuration manually.",
        )


async def generate_patch(
    *,
    file_content:  str,
    check_id:      str,
    control_id:    str,
    control_name:  str,
    control_text:  str,
    resource_name: str,
    file_path:     str,
) -> PatchResult:
    """Generate a corrected version of the violating file via Claude."""
    client = _get_client()

    system_prompt = build_system_prompt(control_text, control_id, control_name)

    user_message = (
        f"Fix the following SOC 2 violation in this Terraform file.\n\n"
        f"- **Check ID:** {check_id}\n"
        f"- **Resource to fix:** `{resource_name}`\n"
        f"- **File:** `{file_path}`\n"
        f"- **Control:** {control_id} — {control_name}\n\n"
        f"## Current file content\n\n"
        f"```hcl\n{file_content}\n```\n\n"
        f"## Instructions\n\n"
        f"1. Add or modify only what is needed to fix `{check_id}` "
        f"on resource `{resource_name}`.\n"
        f"2. Do not remove or change any other resource.\n"
        f"3. Return the **complete** corrected file — not just the changed section.\n"
        f"4. Call `submit_patch` with the result."
    )

    try:
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_PATCH_TOOL],
            tool_choice={"type": "tool", "name": "submit_patch"},
            messages=[{"role": "user", "content": user_message}],
        )

        tool_block = next(
            b for b in response.content if b.type == "tool_use"
        )
        args = tool_block.input

        log.info(
            "Generated patch for %s/%s — %s (cache=%s)",
            control_id,
            check_id,
            args["changes_summary"],
            getattr(response.usage, "cache_read_input_tokens", 0) > 0,
        )

        return PatchResult(
            patched_content=args["patched_content"],
            changes_summary=args["changes_summary"],
            used_llm=True,
        )

    except Exception as exc:
        log.error("generate_patch failed for %s: %s — using original file.", check_id, exc)
        return PatchResult(
            patched_content=file_content,
            changes_summary="LLM patch generation failed — manual fix required.",
            used_llm=False,
        )
