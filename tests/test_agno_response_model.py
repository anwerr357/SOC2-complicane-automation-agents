"""One-shot verification test — requires ANTHROPIC_API_KEY in env. Delete after confirming."""
import os
import pytest
from anthropic import AsyncAnthropic
from agno.agent import Agent
from agno.models.anthropic import Claude
from brain.llm import ExplanationResult


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
@pytest.mark.asyncio
async def test_response_model_returns_dataclass():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    print(f"\nDEBUG key prefix: {key[:12]}... length={len(key)}")
    client = AsyncAnthropic(api_key=key)
    # verify the client itself can reach the API before agno touches anything
    import anthropic
    try:
        raw = await client.models.list()
        print(f"DEBUG raw client OK, first model: {raw.data[0].id if raw.data else 'none'}")
    except anthropic.AuthenticationError as e:
        raise AssertionError(f"Raw Anthropic client also rejects key: {e}") from e
    agent = Agent(
        name="test",
        model=Claude(
            id="claude-haiku-4-5-20251001",
            async_client=AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY")),
        ),
        response_model=ExplanationResult,
        instructions="You are a compliance test agent.",
    )
    result = await agent.arun(
        "Explain why an S3 bucket without encryption violates CC6.7.",
        session_id="test-session",
    )
    assert isinstance(result.content, ExplanationResult), (
        f"Expected ExplanationResult, got {type(result.content)}: {result.content!r}"
    )
    assert result.content.violation_summary
    assert result.content.business_impact
    assert result.content.remediation_steps
