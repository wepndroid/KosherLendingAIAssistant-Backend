"""LLM reranker — sends candidate chunks + query to Claude Haiku 4.5
and returns the top-K indices most relevant for the user's request.

Using Haiku (not Sonnet) keeps per-query cost ~$0.001 even on 30 candidates.
"""
from __future__ import annotations
import json
import re
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings

_client: Anthropic | None = None


def _client_or_raise() -> Anthropic:
    global _client
    if _client is None:
        s = get_settings()
        if not s.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = Anthropic(api_key=s.ANTHROPIC_API_KEY)
    return _client


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
def rerank(*, query: str, candidates: list[dict], top_k: int = 8, model: str = "claude-haiku-4-5-20251001") -> list[int]:
    """Returns indices (into `candidates`) of the top-k most relevant chunks.

    Falls back to identity ranking on any failure — the upstream caller
    must handle that gracefully (the original RRF order is already good).
    """
    if not candidates:
        return []
    if len(candidates) <= top_k:
        return list(range(len(candidates)))

    items = []
    for i, c in enumerate(candidates):
        snippet = (c.get("chunk_text") or "")[:600].replace("\n", " ")
        meta = c.get("metadata") or {}
        src = meta.get("document_name") or meta.get("source") or "?"
        section = meta.get("section") or ""
        head = f"[{i}] {src}" + (f" — {section}" if section else "")
        items.append(f"{head}\n{snippet}")
    block = "\n\n".join(items)

    prompt = (
        f"User query: {query}\n\n"
        f"Below are {len(candidates)} candidate passages from a knowledge base. "
        f"Return a JSON array of the {top_k} indices most useful for answering the query, "
        f"ordered most-to-least relevant. JSON only, no prose.\n\n"
        f"{block}\n\n"
        f"Output: a JSON array of {top_k} integers from 0 to {len(candidates) - 1}."
    )

    try:
        msg = _client_or_raise().messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return list(range(min(top_k, len(candidates))))
        idxs = json.loads(m.group(0))
        valid = [int(i) for i in idxs if isinstance(i, (int, float)) and 0 <= int(i) < len(candidates)]
        # de-duplicate while preserving order
        seen: set[int] = set()
        out: list[int] = []
        for i in valid:
            if i not in seen:
                seen.add(i)
                out.append(i)
            if len(out) >= top_k:
                break
        if not out:
            return list(range(min(top_k, len(candidates))))
        return out
    except Exception:
        return list(range(min(top_k, len(candidates))))
