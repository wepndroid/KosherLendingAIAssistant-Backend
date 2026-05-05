"""Quality and scale-readiness evaluation for generated content.

Usage:
  python scripts/eval_quality.py --days 30 --limit 1000
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from db.supabase_client import supabase
from core.compliance import REQUIRED_PACKAGE_FIELDS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    rows = _fetch_recent(days=args.days, limit=args.limit)
    report = _build_report(rows, days=args.days)
    print(json.dumps(report, indent=2))


def _fetch_recent(*, days: int, limit: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: list[dict] = []
    start = 0
    page = 500
    while len(out) < limit:
        rows = (
            supabase()
            .table("generated_content")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .range(start, start + page - 1)
            .execute()
            .data
            or []
        )
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page:
            break
        start += page
    return out[:limit]


def _build_report(rows: list[dict], *, days: int) -> dict:
    total = len(rows)
    if total == 0:
        return {"window_days": days, "total_posts": 0}

    duplicate_risk = Counter(str(r.get("duplicate_risk") or "Unknown") for r in rows)
    status_counts = Counter(str(r.get("status") or "Unknown") for r in rows)

    missing_field_counts = Counter()
    missing_examples = []
    combo_counts = Counter()
    spoken_cta_mismatches = 0
    platform_target_issues = 0

    for r in rows:
        missing = [k for k in REQUIRED_PACKAGE_FIELDS if not str(r.get(k, "") or "").strip()]
        if missing:
            missing_field_counts.update(missing)
            if len(missing_examples) < 20:
                missing_examples.append(
                    {"id": r.get("id"), "topic": r.get("topic"), "missing_fields": missing}
                )

        script = str(r.get("script") or "")
        spoken_cta = str(r.get("cta") or "")
        if spoken_cta and script and spoken_cta.lower() not in script.lower():
            spoken_cta_mismatches += 1

        targets = r.get("platform_targets") or []
        if not isinstance(targets, list) or not targets:
            platform_target_issues += 1

        combo = (_norm(r.get("source_book")), _norm(r.get("source_framework")))
        if combo[0] and combo[1]:
            combo_counts[combo] += 1

    repeated_combos = [
        {"source_book": b, "source_framework": f, "count": c}
        for (b, f), c in combo_counts.items()
        if c > 1
    ]
    repeated_combos.sort(key=lambda x: x["count"], reverse=True)

    return {
        "window_days": days,
        "total_posts": total,
        "status_distribution": dict(status_counts),
        "duplicate_risk_distribution": dict(duplicate_risk),
        "required_field_coverage": {
            "complete_posts": total - len(missing_examples),
            "posts_with_missing_fields": len(missing_examples),
            "missing_field_counts": dict(missing_field_counts),
            "examples": missing_examples,
        },
        "spoken_cta_mismatch_count": spoken_cta_mismatches,
        "platform_targets_issue_count": platform_target_issues,
        "repeated_book_framework_combos": repeated_combos[:25],
    }


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


if __name__ == "__main__":
    main()

