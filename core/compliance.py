"""Validates and auto-corrects generated content against brand rules."""
from __future__ import annotations
import re
from .word_count import count_words, target_for


PROHIBITED_PATTERNS = [
    r"\bguaranteed\b",
    r"\blowest rate ever\b",
    r"\bfree money\b",
    r"\bno cost\b",
    r"\b100% approval\b",
]

REQUIRED_PACKAGE_FIELDS = [
    "hook",
    "script",
    "production_brief",
    "cta",
    "spoken_cta",
    "dm_keyword",
    "deliverable",
    "caption_tiktok",
    "caption_instagram",
    "caption_linkedin",
    "caption_facebook",
    "caption_x",
    "source_book",
    "source_framework",
    "source_reason",
    "experience_named",
    "perspective_shift",
]


def validate(content: dict, *, excluded_states: list[str], compliance_footer: str) -> dict:
    """Returns a dict with status, errors, warnings, and an auto-corrected copy."""
    errors: list[str] = []
    warnings: list[str] = []

    script = content.get("script", "") or ""
    duration = content.get("duration", "") or ""

    # Full package completeness
    missing = [k for k in REQUIRED_PACKAGE_FIELDS if not str(content.get(k, "") or "").strip()]
    if missing:
        errors.append("Missing required content package fields: " + ", ".join(missing))

    # Word count check
    wc = count_words(script)
    lo, hi = target_for(duration)
    if not (lo <= wc <= hi):
        warnings.append(f"Script is {wc} words; target {lo}-{hi} for {duration}")

    # Excluded state check (full phrase match — avoid matching "NY" inside "any")
    for st in excluded_states:
        full = _state_name_for(st)
        text = f"{script} {content.get('caption_instagram','')} {content.get('caption_tiktok','')} {content.get('caption_facebook','')}"
        if re.search(rf"\b{re.escape(st)}\b", text) or (full and re.search(rf"\b{re.escape(full)}\b", text, re.I)):
            errors.append(f"References excluded state: {st}")

    # Prohibited language
    full_text = " ".join(
        str(content.get(k, "") or "")
        for k in ["hook", "script", "caption_tiktok", "caption_instagram", "caption_facebook", "caption_linkedin", "caption_x", "cta"]
    ).lower()
    for pat in PROHIBITED_PATTERNS:
        if re.search(pat, full_text):
            errors.append(f"Prohibited phrase matched: /{pat}/")

    # Citation present
    if not (content.get("source_book") and content.get("source_framework")):
        errors.append("Missing source_book or source_framework citation")

    # Voice absolutes — the model must fill these
    if not (content.get("experience_named") or "").strip():
        errors.append("Missing experience_named — voice rule #1 (name the experience)")
    if not (content.get("perspective_shift") or "").strip():
        errors.append("Missing perspective_shift — voice rule #2 (deliver a shift, not info)")
    if _looks_generic(content.get("perspective_shift", "")):
        warnings.append("perspective_shift looks generic — consider regenerating")

    # DM keyword shape
    kw = content.get("dm_keyword", "") or ""
    if not re.fullmatch(r"[A-Z0-9_]{2,20}", kw):
        warnings.append(f"DM keyword '{kw}' is not a clean uppercase token")

    # Spoken CTA should appear verbatim in script
    spoken_cta = (content.get("spoken_cta", "") or "").strip()
    if spoken_cta and script and spoken_cta.lower() not in script.lower():
        warnings.append("spoken_cta does not appear verbatim in script")

    # Platform/output quality checks
    x_caption = content.get("caption_x", "") or ""
    if len(x_caption) > 280:
        warnings.append("caption_x exceeds 280 characters")
    hashtags = content.get("hashtags") or []
    if not isinstance(hashtags, list) or len(hashtags) < 3:
        warnings.append("Hashtags should include at least 3 tags")
    elif any(not str(t).startswith("#") for t in hashtags):
        warnings.append("All hashtags should start with #")
    targets = content.get("platform_targets") or []
    if not isinstance(targets, list) or not targets:
        warnings.append("platform_targets should include recommended platforms for this post")
    elif len(targets) > 6:
        warnings.append("platform_targets should be a focused recommendation list, not every platform")
    brief = (content.get("production_brief", "") or "").strip()
    if brief and len(brief.split()) < 10:
        warnings.append("production_brief is too short; include visual direction + pacing + energy notes")

    # Auto-corrections
    corrected = dict(content)
    # Append compliance footer to Instagram caption if missing
    insta = corrected.get("caption_instagram", "") or ""
    if compliance_footer and compliance_footer not in insta:
        corrected["caption_instagram"] = f"{insta}\n\n{compliance_footer}".strip()

    # Update word_count to actual
    corrected["word_count"] = wc

    status = "Valid" if not errors else "Invalid"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "content": corrected,
    }


def _state_name_for(abbr: str) -> str | None:
    return {"NY": "New York"}.get(abbr.upper())


_GENERIC_PHRASES = (
    "buyers learn", "readers understand", "people realize",
    "this post explains", "informs the reader", "provides information",
    "helps people understand",
)


def _looks_generic(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _GENERIC_PHRASES)
