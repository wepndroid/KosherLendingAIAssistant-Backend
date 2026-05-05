"""Cross-analyzes a newly uploaded document against the existing library.

Surfaces three categories: overlap (duplicate-prevention awareness), complementary frameworks
(synthesis opportunities), and net-new material (fresh content).
"""
from db.supabase_client import supabase
from integrations.claude_client import client as claude_client
from config import get_settings


PROMPT = """You are the librarian of a content knowledge base for a mortgage professional.
A new document was just added. Compare it against the existing summaries below and produce a brief JSON object:

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

EXISTING LIBRARY SUMMARIES:
{existing_summaries}

Reply with JSON only.
"""


def run(new_document_id: str) -> dict:
    db = supabase()
    new_doc = db.table("knowledge_documents").select("id,name,summary").eq("id", new_document_id).limit(1).execute().data
    if not new_doc:
        return {}
    new_summary = new_doc[0].get("summary") or new_doc[0].get("name", "")

    others = (
        db.table("knowledge_documents")
        .select("name,summary")
        .neq("id", new_document_id)
        .eq("status", "Indexed")
        .limit(40)
        .execute()
        .data
        or []
    )
    if not others:
        return {
            "overlap": [],
            "complementary": [],
            "contradictions": [],
            "net_new": [],
            "suggested_combinations": [],
            "suggested_synthesis_angles": [],
        }

    existing_block = "\n\n".join(f"- {d['name']}: {d.get('summary') or '(no summary)'}" for d in others)
    s = get_settings()
    msg = claude_client().messages.create(
        model=s.ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": PROMPT.replace("{new_summary}", new_summary).replace("{existing_summaries}", existing_block),
            }
        ],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    try:
        import json, re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group(0) if m else raw)
    except Exception:
        result = {"raw": raw}
    result = _normalize_shape(result)
    db.table("knowledge_documents").update({"cross_analysis": result}).eq("id", new_document_id).execute()
    return result


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
