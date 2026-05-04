"""One-time migration: ingest the 5 source DOCX files in Docs/Attached Souce/.

Run from project root:
    python -m backend.scripts.seed_existing_docs

The Year 1 / Year 2 calendar files are LARGE (9.6 MB each, ~4,745 entries each).
They are loaded as knowledge documents AND parsed for the entries that should
populate `usage_log` so the duplicate checker knows what's already been published.
"""
from pathlib import Path
import sys

# Ensure project root is importable when this is run as a module
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core import ingestion, cross_analysis  # noqa: E402
from backend.db.supabase_client import supabase  # noqa: E402


SOURCE_DIR = ROOT / "Docs" / "Attached Souce"  # NOTE: folder name has missing 'r'

KNOWN_FILES = [
    ("kosherlending_master_strategy_bible.docx", "Strategy Doc", ["All Pillars"]),
    ("kosherlending_DM Hook_deliverables_FINAL.docx", "DM Deliverable", ["All Pillars"]),
    ("Claudes Distribution Matrix and advice.docx", "Strategy Doc", ["All Pillars"]),
    ("kosherlending_Year1_FINAL_v2 with advanced CTA's.docx", "Content Calendar", ["All Pillars"]),
    ("kosherlending_Year2_FINAL_v2 with advanced CTA's.docx", "Content Calendar", ["All Pillars"]),
]


def main():
    db = supabase()
    if not SOURCE_DIR.exists():
        print(f"Source directory not found: {SOURCE_DIR}")
        return
    for filename, category, pillars in KNOWN_FILES:
        path = SOURCE_DIR / filename
        if not path.exists():
            print(f"  skip (missing): {filename}")
            continue
        existing = db.table("knowledge_documents").select("id").eq("name", filename).execute().data
        if existing:
            print(f"  already seeded: {filename}")
            continue
        data = path.read_bytes()
        row = {
            "name": filename,
            "category": category,
            "file_type": "DOCX",
            "file_size_bytes": len(data),
            "status": "Uploaded",
            "pillars": pillars,
        }
        inserted = db.table("knowledge_documents").insert(row).execute().data[0]
        print(f"  ingesting {filename} ({len(data)//1024} KB)…")
        try:
            ingestion.ingest_document(document_id=inserted["id"], filename=filename, data=data)
            cross_analysis.run(inserted["id"])
            print(f"  done: {filename}")
        except Exception as e:
            print(f"  FAILED {filename}: {e}")


if __name__ == "__main__":
    main()
