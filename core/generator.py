"""Generation orchestrator: RAG retrieve → assemble prompt → Claude → validate → store."""
from __future__ import annotations
from typing import Any
from db.supabase_client import supabase
from integrations.claude_client import generate_json
from integrations.perplexity_client import research
from prompts.generation_prompt import load_system_prompt, build_retrieved_block, build_user_request
from . import brand_context, retrieval, duplicate_check, compliance, synthesis


_PILLAR_KEYS = {
    "Psychology": "Psychology",
    "Psychology & Behavioral Economics": "Psychology",
    "Negotiation": "Negotiation",
    "Negotiation Tactics": "Negotiation",
    "Jefferson Fisher Communication": "Communication",
    "Geographic": "Geographic",
    "Geographic Market Intelligence": "Geographic",
    "Financing Strategy": "Financing",
    "Wealth & Life Philosophy": "Wealth",
    "Myth-Bust / Story": "Myth-Bust",
}


class DuplicateAngleError(Exception):
    """Raised when a generated angle is too similar to a recent post — caller should retry."""
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__(f"Angle too similar to recent post(s): {[c.get('id') for c in conflicts]}")


class DuplicateComboError(Exception):
    """Raised when source_book + source_framework combo was recently used."""
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__("Book/framework combination was recently used")


async def generate_one(
    *,
    pillar: str,
    platform: str,
    duration: str = "45 seconds",
    topic: str | None = None,
    goal: str | None = None,
    source_strategy: str | None = None,
    dm_keyword: str | None = None,
    source_books: list[str] | None = None,
    use_perplexity: bool = False,
    block_on_duplicate: bool = True,
) -> dict[str, Any]:
    brand = brand_context.load()

    pillar_key = _PILLAR_KEYS.get(pillar, pillar)

    retrieve_query = topic or f"{pillar} content for home buyers"
    chunks = retrieval.retrieve(retrieve_query, pillar=None, k=8)

    avoidance = duplicate_check.recent_avoidance(pillar=pillar, limit=40)

    try:
        unexplored = synthesis.unexplored_pairs(limit=8)
    except Exception:
        unexplored = []

    perplexity_ctx = None
    if use_perplexity and pillar_key == "Geographic" and topic:
        perplexity_ctx = await research(f"Current US mortgage / real-estate market context for: {topic}")

    user_request = build_user_request(
        topic=topic,
        pillar=pillar,
        platform=platform,
        duration=duration,
        goal=goal,
        source_strategy=source_strategy,
        dm_keyword=dm_keyword,
        source_books=source_books,
        avoidance=avoidance,
        perplexity_context=perplexity_ctx,
        unexplored_pairs=unexplored,
    )

    raw = generate_json(
        system_prompt=load_system_prompt(),
        retrieved_block=build_retrieved_block(chunks),
        user_request=user_request,
    )

    raw["source_chunks"] = [c["id"] for c in chunks if c.get("id")]
    if not raw.get("pillar"):
        raw["pillar"] = pillar
    if not raw.get("platform"):
        raw["platform"] = platform
    if not raw.get("duration"):
        raw["duration"] = duration
    if raw.get("cta") and raw.get("spoken_cta"):
        raw["cta_strategy"] = raw["cta"]
        raw["cta"] = raw["spoken_cta"]
    elif raw.get("spoken_cta") and not raw.get("cta"):
        raw["cta"] = raw["spoken_cta"]
    elif raw.get("cta") and not raw.get("spoken_cta"):
        raw["spoken_cta"] = raw["cta"]
    if not isinstance(raw.get("platform_targets"), list) or not raw.get("platform_targets"):
        raw["platform_targets"] = [platform]
    else:
        seen: set[str] = set()
        normalized_targets: list[str] = []
        for tgt in raw.get("platform_targets", []):
            t = str(tgt).strip()
            if t and t not in seen:
                seen.add(t)
                normalized_targets.append(t)
        raw["platform_targets"] = normalized_targets or [platform]

    # Idea-level dedup: embed (topic + hook + perspective_shift + framework) and check
    # against recent posts. Tier may BLOCK and force regeneration.
    angle_emb = duplicate_check.embed_angle(raw)
    raw["angle_embedding"] = angle_emb
    angle_check = duplicate_check.assess_angle_similarity(angle_emb)

    if angle_check["should_block"] and block_on_duplicate:
        raise DuplicateAngleError(angle_check["conflicts"])

    combo_check = duplicate_check.assess_combo_reuse(raw, pillar=pillar)
    if combo_check["should_block"] and block_on_duplicate:
        raise DuplicateComboError(combo_check["conflicts"])

    # Combine string-level and angle-level signals; angle takes precedence when stronger
    string_tier = duplicate_check.assess_risk(raw, avoidance)
    raw["duplicate_risk"] = _max_tier(string_tier, angle_check["tier"], combo_check["tier"])

    val = compliance.validate(
        raw,
        excluded_states=brand.get("excluded_states") or ["NY"],
        compliance_footer=brand.get("compliance_footer", ""),
    )
    content = val["content"]
    all_conflicts = (angle_check.get("conflicts") or []) + (combo_check.get("conflicts") or [])
    content["validations"] = {
        "status": val["status"],
        "errors": val["errors"],
        "warnings": val["warnings"],
        "conflicts": all_conflicts,
        "duplicate_checks": {
            "angle": angle_check,
            "combo": combo_check,
            "string": string_tier,
        },
        "cta_strategy": raw.get("cta_strategy"),
    }

    if val["errors"] or angle_check["tier"] in {"High", "Block"} or combo_check["tier"] in {"High", "Block"}:
        content["status"] = "Needs Review"
    else:
        content["status"] = "Draft"

    saved = _persist(content)
    saved["spoken_cta"] = content.get("spoken_cta") or saved.get("cta")
    saved["cta_strategy"] = (content.get("validations") or {}).get("cta_strategy")
    duplicate_check.log(content_id=saved["id"], content=saved)

    supabase().table("activity_log").insert(
        {"text": f"Generated: {saved.get('topic','(untitled)')}", "icon": "sparkles"}
    ).execute()

    return saved


_TIER_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Block": 3}


def _max_tier(*tiers: str) -> str:
    return max(tiers, key=lambda t: _TIER_ORDER.get(t, 0))


def _persist(content: dict) -> dict:
    row = {
        "topic": content.get("topic"),
        "pillar": content.get("pillar"),
        "platform": content.get("platform"),
        "platform_targets": content.get("platform_targets") or [content.get("platform")],
        "duration": content.get("duration"),
        "word_count": content.get("word_count"),
        "status": content.get("status", "Draft"),
        "hook": content.get("hook"),
        "script": content.get("script"),
        "on_screen": content.get("on_screen"),
        "production_brief": content.get("production_brief"),
        "caption": content.get("caption_instagram") or content.get("caption_tiktok"),
        "caption_tiktok": content.get("caption_tiktok"),
        "caption_instagram": content.get("caption_instagram"),
        "caption_linkedin": content.get("caption_linkedin"),
        "caption_facebook": content.get("caption_facebook"),
        "caption_x": content.get("caption_x"),
        "cta": content.get("cta"),
        "cta_structure": content.get("cta_structure"),
        "dm_keyword": content.get("dm_keyword"),
        "deliverable": content.get("deliverable"),
        "hashtags": content.get("hashtags") or [],
        "source_book": content.get("source_book"),
        "source_framework": content.get("source_framework"),
        "source_reason": content.get("source_reason"),
        "source_chunks": content.get("source_chunks") or [],
        "experience_named": content.get("experience_named"),
        "perspective_shift": content.get("perspective_shift"),
        "angle_embedding": content.get("angle_embedding"),
        "duplicate_risk": content.get("duplicate_risk", "Low"),
        "validations": content.get("validations"),
    }
    res = supabase().table("generated_content").insert(row).execute()
    return res.data[0] if res.data else row
