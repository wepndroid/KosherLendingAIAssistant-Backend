"""Synthesis tracker: which book pairings have NOT yet been explored in generation.

Each generated content row records which knowledge_chunks fed it (`source_chunks`).
Two documents "co-appear" when the same generation pulled from both. Pairs that
have never co-appeared are "unexplored" — fresh combinations the engine should
prefer next.
"""
from __future__ import annotations
from itertools import combinations
from ..db.supabase_client import supabase


def library_log(limit: int = 100) -> list[dict]:
    """Chronological list of indexed knowledge documents — Jeffrey's running library list."""
    return (
        supabase()
        .table("knowledge_documents")
        .select("id,name,category,uploaded_at,indexed_at,total_chunks,summary,pillars,status")
        .order("uploaded_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def unexplored_pairs(limit: int = 10) -> list[dict]:
    """Return top-N book pairs that have never been used together in a generation."""
    db = supabase()
    docs = (
        db.table("knowledge_documents")
        .select("id,name,category,pillars")
        .eq("status", "Indexed")
        .in_("category", ["Book", "Strategy Doc"])
        .execute()
        .data
        or []
    )
    if len(docs) < 2:
        return []
    docs_by_id = {d["id"]: d for d in docs}

    content = (
        db.table("generated_content")
        .select("id,source_chunks")
        .not_.is_("source_chunks", "null")
        .execute()
        .data
        or []
    )

    co_pairs: set[frozenset[str]] = set()
    chunk_to_doc_cache: dict[str, str] = {}

    for c in content:
        chunk_ids = c.get("source_chunks") or []
        if len(chunk_ids) < 2:
            continue
        missing = [cid for cid in chunk_ids if cid not in chunk_to_doc_cache]
        if missing:
            rows = db.table("knowledge_chunks").select("id,document_id").in_("id", missing).execute().data or []
            for r in rows:
                chunk_to_doc_cache[r["id"]] = r["document_id"]
        doc_ids = {chunk_to_doc_cache[cid] for cid in chunk_ids if cid in chunk_to_doc_cache and chunk_to_doc_cache[cid] in docs_by_id}
        for a, b in combinations(sorted(doc_ids), 2):
            co_pairs.add(frozenset({a, b}))

    all_pairs = (frozenset({a["id"], b["id"]}) for a, b in combinations(docs, 2))
    unexplored = [pair for pair in all_pairs if pair not in co_pairs]

    out: list[dict] = []
    for pair in unexplored[:limit]:
        a_id, b_id = list(pair)
        a, b = docs_by_id[a_id], docs_by_id[b_id]
        out.append(
            {
                "a": {"id": a["id"], "name": a["name"], "pillars": a.get("pillars") or []},
                "b": {"id": b["id"], "name": b["name"], "pillars": b.get("pillars") or []},
                "shared_pillars": list(set(a.get("pillars") or []) & set(b.get("pillars") or [])),
            }
        )
    return out
