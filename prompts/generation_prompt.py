from typing import Iterable
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent
_SYSTEM_PROMPT_PATH = _PROMPT_DIR / "system_prompt.txt"


def load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_retrieved_block(chunks: Iterable[dict]) -> str:
    """Format retrieved knowledge chunks for Claude with cite-able indices."""
    lines = ["═══ RETRIEVED KNOWLEDGE PASSAGES ═══", ""]
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata") or {}
        src = meta.get("document_name") or meta.get("source") or "Unknown source"
        section = meta.get("section") or meta.get("page") or ""
        header = f"[{i}] {src}"
        if section:
            header += f" — {section}"
        lines.append(header)
        lines.append(c["chunk_text"].strip())
        lines.append("")
    return "\n".join(lines)


def build_user_request(
    *,
    topic: str | None,
    pillar: str,
    platform: str,
    duration: str,
    goal: str | None,
    source_strategy: str | None,
    dm_keyword: str | None,
    source_books: list[str] | None,
    avoidance: list[dict],
    perplexity_context: str | None = None,
    unexplored_pairs: list[dict] | None = None,
) -> str:
    parts: list[str] = ["═══ USER REQUEST ═══"]
    if topic:
        parts.append(f"Topic: {topic}")
    parts.append(f"Pillar: {pillar}")
    parts.append(f"Primary platform: {platform}")
    parts.append(f"Duration: {duration}")
    if goal:
        parts.append(f"Goal: {goal}")
    if source_strategy:
        parts.append(f"Source strategy: {source_strategy}")
    if dm_keyword and dm_keyword != "Auto-select":
        parts.append(f"DM keyword (forced): {dm_keyword}")
    if source_books:
        parts.append("Preferred source books: " + ", ".join(source_books))

    if avoidance:
        parts.append("")
        parts.append("═══ DUPLICATE AVOIDANCE — DO NOT REPEAT THESE ═══")
        for a in avoidance[:30]:
            book = a.get("source_book") or "?"
            fw = a.get("framework") or "?"
            t = (a.get("topic") or "")[:80]
            parts.append(f"- [{a.get('pillar','?')}] {book} / {fw} → {t}")

    if unexplored_pairs:
        parts.append("")
        parts.append("═══ FRESH SYNTHESIS OPPORTUNITIES — pairings not yet used ═══")
        parts.append("Prefer combining concepts from these book pairs if the topic allows:")
        for pair in unexplored_pairs[:8]:
            a = pair.get("a", {}).get("name") or "?"
            b = pair.get("b", {}).get("name") or "?"
            parts.append(f"- {a}  ×  {b}")

    if perplexity_context:
        parts.append("")
        parts.append("═══ CURRENT MARKET CONTEXT (Perplexity) ═══")
        parts.append(perplexity_context)

    parts.append("")
    parts.append(
        "Produce one complete content package as a single JSON object matching the schema. "
        "Cite specifically from the retrieved passages above. Include platform_targets as a recommended subset "
        "and include spoken_cta as exact end-of-script words. Output JSON only."
    )
    return "\n".join(parts)
