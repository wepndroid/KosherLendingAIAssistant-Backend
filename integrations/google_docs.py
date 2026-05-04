"""Stub for Google Docs export. Wire to Google Drive API once OAuth is configured.

For Phase 1 we expose the same content as a Markdown blob that Jeffrey can paste into Google Docs.
Once OAuth credentials are added, replace `export_markdown` with a real Drive create call.
"""
from typing import Iterable


def export_markdown(items: Iterable[dict], title: str, compliance_footer: str) -> str:
    parts: list[str] = [f"# {title}", ""]
    for item in items:
        parts.append(f"## {item.get('topic','Untitled')}")
        parts.append(
            f"_{item.get('pillar','-')} · {item.get('platform','-')} · {item.get('duration','-')}_"
        )
        parts.append("")
        parts.append(f"**Hook:** {item.get('hook','')}")
        parts.append(f"**On-screen:** {item.get('on_screen','')}")
        parts.append("")
        parts.append("**Script:**")
        parts.append(item.get("script", ""))
        parts.append("")
        parts.append(f"**Production brief:** {item.get('production_brief','')}")
        parts.append("")
        for label, key in [
            ("TikTok", "caption_tiktok"),
            ("Instagram", "caption_instagram"),
            ("LinkedIn", "caption_linkedin"),
            ("Facebook", "caption_facebook"),
            ("X/Twitter", "caption_x"),
        ]:
            v = item.get(key) or item.get("caption")
            if v:
                parts.append(f"**{label} caption:** {v}")
        parts.append("")
        parts.append(f"**CTA:** {item.get('cta','')}")
        parts.append(
            f"**DM keyword → deliverable:** `{item.get('dm_keyword','-')}` → {item.get('deliverable','-')}"
        )
        tags = item.get("hashtags") or []
        if tags:
            parts.append(f"**Hashtags:** {' '.join(tags)}")
        parts.append(
            f"**Source:** {item.get('source_book','-')} — {item.get('source_framework','-')}"
        )
        parts.append("")
        parts.append(f"_{compliance_footer}_")
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts)
