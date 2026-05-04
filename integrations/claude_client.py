import json
import re
from typing import Any
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from ..config import get_settings

_client: Anthropic | None = None


def client() -> Anthropic:
    global _client
    if _client is None:
        s = get_settings()
        if not s.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = Anthropic(api_key=s.ANTHROPIC_API_KEY)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def generate_json(
    *,
    system_prompt: str,
    retrieved_block: str,
    user_request: str,
    max_tokens: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Call Claude with two cache breakpoints (system + retrieved chunks) and parse JSON output."""
    s = get_settings()
    msg = client().messages.create(
        model=model or s.ANTHROPIC_MODEL,
        max_tokens=max_tokens or s.ANTHROPIC_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": retrieved_block,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": user_request},
                ],
            }
        ],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return _parse_json(text)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
def summarize(text: str, instruction: str = "Summarize this document in 5-8 sentences for a content strategist.") -> str:
    s = get_settings()
    msg = client().messages.create(
        model=s.ANTHROPIC_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n{text[:30000]}"}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError("Claude response did not contain valid JSON")
        return json.loads(m.group(0))
