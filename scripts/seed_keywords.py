"""Seed the dm_keywords / dm_deliverables tables with the canonical 13 active keywords.

Geographic 48 state-specific keywords are not seeded here — they're best loaded by
extracting from the DM Hook deliverables DOCX in a follow-up pass.

Run from project root:
    python -m backend.scripts.seed_keywords
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.supabase_client import supabase  # noqa: E402


KEYWORDS = [
    {"keyword": "BRAIN", "category": "Psychology", "pillars": ["Psychology"], "intent": "Medium Intent",
     "cta_template": "Comment BRAIN for the field guide.",
     "summary": "Buyer Psychology Field Guide — 8 cognitive biases."},
    {"keyword": "BIAS", "category": "Psychology", "pillars": ["Psychology"], "intent": "Medium Intent",
     "cta_template": "Comment BIAS for the cheatsheet.",
     "summary": "Cognitive bias cheatsheet for buyers."},
    {"keyword": "BUYDOWN", "category": "Financing", "pillars": ["Financing Strategy"], "intent": "High Intent",
     "cta_template": "Comment BUYDOWN for the calculator.",
     "summary": "2-1 buydown calculator with seller-credit scenarios."},
    {"keyword": "OFFER", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "High Intent",
     "cta_template": "Comment OFFER for the templates.",
     "summary": "Winning offer template pack."},
    {"keyword": "CREDIT", "category": "Financing", "pillars": ["Financing Strategy"], "intent": "High Intent",
     "cta_template": "Comment CREDIT for the 90-day plan.",
     "summary": "90-day credit optimization plan."},
    {"keyword": "SCRIPT", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "Medium Intent",
     "cta_template": "Comment SCRIPT for the library.",
     "summary": "30+ negotiation scripts."},
    {"keyword": "VALUE", "category": "Financing", "pillars": ["Financing Strategy"], "intent": "Medium Intent",
     "cta_template": "Comment VALUE for the breakdown.",
     "summary": "Real loan value vs APR breakdown."},
    {"keyword": "WEALTH", "category": "Wealth", "pillars": ["Wealth & Life Philosophy"], "intent": "Low Intent",
     "cta_template": "Comment WEALTH for the roadmap.",
     "summary": "Wealth-building roadmap for first-time buyers."},
    {"keyword": "RULES", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "Medium Intent",
     "cta_template": "Comment RULES for the negotiation rules.",
     "summary": "Keld Jensen's negotiation rules summary."},
    {"keyword": "TIMING", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "Medium Intent",
     "cta_template": "Comment TIMING for the cheat sheet.",
     "summary": "Best timing for offers, counters, walk-aways."},
    {"keyword": "SELLER", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "High Intent",
     "cta_template": "Comment SELLER for the script.",
     "summary": "Seller psychology script — what listing agents won't say."},
    {"keyword": "LETTER", "category": "Negotiation", "pillars": ["Negotiation"], "intent": "Medium Intent",
     "cta_template": "Comment LETTER for the buyer letter template.",
     "summary": "Persuasive offer cover letter template."},
    {"keyword": "BIGGER", "category": "Financing", "pillars": ["Financing Strategy"], "intent": "High Intent",
     "cta_template": "Comment BIGGER for the bigger-house playbook.",
     "summary": "How to qualify for a bigger home with the same income."},
]


def main():
    db = supabase()
    for k in KEYWORDS:
        existing = db.table("dm_keywords").select("keyword").eq("keyword", k["keyword"]).execute().data
        if existing:
            db.table("dm_keywords").update(k).eq("keyword", k["keyword"]).execute()
        else:
            db.table("dm_keywords").insert({**k, "ghl_status": "Pending", "status": "Active"}).execute()
        print(f"  upserted {k['keyword']}")


if __name__ == "__main__":
    main()
