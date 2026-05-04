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


def validate(content: dict, *, excluded_states: list[str], compliance_footer: str) -> dict:
    """Returns a dict with status, errors, warnings, and an auto-corrected copy."""
    errors: list[str] = []
    warnings: list[str] = []

    script = content.get("script", "") or ""
    duration = content.get("duration", "") or ""

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

    # DM keyword shape
    kw = content.get("dm_keyword", "") or ""
    if not re.fullmatch(r"[A-Z0-9_]{2,20}", kw):
        warnings.append(f"DM keyword '{kw}' is not a clean uppercase token")

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
