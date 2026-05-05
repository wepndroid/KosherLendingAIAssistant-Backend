"""Cross-analyzes a newly uploaded document against the existing library.

Surfaces three categories: overlap (duplicate-prevention awareness), complementary frameworks
(synthesis opportunities), and net-new material (fresh content).
"""
from __future__ import annotations

import json
import re
from db.supabase_client import supabase
from integrations.claude_client import client as claude_client
from config import get_settings


PROMPT_BATCH = """You are the librarian of a content knowledge base for a mortgage professional.
A new document was just added. Compare it against this portion of the existing library and produce a JSON object:

{
  "overlap": [<sentences describing concepts already covered>],
  "complementary": [<frameworks that pair WELL with existing books for synthesis>],
  "contradictions": [<claims that appear to disagree with existing library viewpoints>],
  "net_new": [<truly new material>],
  "suggested_combinations": [<book/framework pairings worth testing in new posts>],
  "suggested_synthesis_angles": [<3-5 short content angle ideas combining new + existing>]
}

NEW DOCUMENT SUMMARY:
{new_summary}

EXISTING LIBRARY SUMMARIES (BATCH):
{existing_summaries}

Reply with JSON only.
"""

PROMPT_CONSOLIDATE = """You are consolidating cross-analysis results from multiple library batches.
Merge these partial results into one final JSON object. Deduplicate similar items, keep the most useful phrasing,
and prioritize concrete, actionable synthesis opportunities.

Return JSON with exactly these keys:
{
  "overlap": [],
  "complementary": [],
  "contradictions": [],
  "net_new": [],
  "suggested_combinations": [],
  "suggested_synthesis_angles": []
}

NEW DOCUMENT SUMMARY:
{new_summary}

PARTIAL RESULTS:
{partials}

Reply with JSON only.
"""

_PAGE_SIZE = 500
_SUMMARY_BATCH_SIZE = 30


def run(new_document_id: str) -> dict:
    db = supabase()
    new_doc = db.table("knowledge_documents").select("id,name,summary").eq("id", new_document_id).limit(1).execute().data
    if not new_doc:
        return {}
    new_summary = new_doc[0].get("summary") or new_doc[0].get("name", "")
    others = _fetch_other_summaries(new_document_id)
    if not others:
        result = {
            "overlap": [],
            "complementary": [],
            "contradictions": [],
            "net_new": [],
            "suggested_combinations": [],
            "suggested_synthesis_angles": [],
        }
        db.table("knowledge_documents").update({"cross_analysis": result}).eq("id", new_document_id).execute()
        return result

    partials: list[dict] = []
    for batch in _chunks(others, _SUMMARY_BATCH_SIZE):
        existing_block = "\n\n".join(f"- {d['name']}: {d.get('summary') or '(no summary)'}" for d in batch)
        partial = _ask_llm(PROMPT_BATCH.replace("{new_summary}", new_summary).replace("{existing_summaries}", existing_block))
        partials.append(_normalize_shape(partial))

    if len(partials) == 1:
        result = partials[0]
    else:
        partials_blob = json.dumps(partials, ensure_ascii=False)
        result = _ask_llm(PROMPT_CONSOLIDATE.replace("{new_summary}", new_summary).replace("{partials}", partials_blob))
        result = _normalize_shape(result)

    db.table("knowledge_documents").update({"cross_analysis": result}).eq("id", new_document_id).execute()
    return result


def _fetch_other_summaries(new_document_id: str) -> list[dict]:
    out: list[dict] = []
    start = 0
    while True:
        rows = (
            supabase()
            .table("knowledge_documents")
            .select("name,summary")
            .neq("id", new_document_id)
            .eq("status", "Indexed")
            .order("uploaded_at", desc=True)
            .range(start, start + _PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        if not rows:
            break
        for r in rows:
            if (r.get("summary") or r.get("name")):
                out.append({"name": r.get("name") or "Unknown", "summary": r.get("summary") or ""})
        if len(rows) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    return out


def _ask_llm(prompt: str) -> dict:
    s = get_settings()
    msg = claude_client().messages.create(
        model=s.ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        return json.loads(m.group(0) if m else raw)
    except Exception:
        return {"raw": raw}


def _normalize_shape(result: dict) -> dict:
    normalized = dict(result or {})
    for k in (
        "overlap",
        "complementary",
        "contradictions",
        "net_new",
        "suggested_combinations",
        "suggested_synthesis_angles",
    ):
        v = normalized.get(k)
        if not isinstance(v, list):
            normalized[k] = []
    return normalized


def _chunks(items: list[dict], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]
