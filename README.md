# KosherLending AI Content OS — Backend

FastAPI + Supabase + Claude + OpenAI embeddings + pgvector.

## Setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
cp .env.example .env              # then fill in keys
```

Apply the schema once in Supabase (SQL Editor → paste `db/schema.sql` → Run).

## Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

## Seed (optional but recommended)

```bash
python -m backend.scripts.seed_keywords
python -m backend.scripts.seed_existing_docs   # ingests the 5 DOCXs in Docs/Attached Souce/
```

The Year 1 / Year 2 calendar files are 9.6 MB each and produce many thousand chunks.
First-time ingestion will burn OpenAI embedding credit and take a while.

## Routes

| Method | Path | Purpose |
|---|---|---|
| POST | /api/auth/register | Create admin account |
| POST | /api/auth/login | Get JWT |
| POST | /api/generate | Single content generation |
| POST | /api/batch | Multi-day batch generation |
| GET/POST | /api/knowledge | Upload + list docs |
| GET/PATCH/DELETE | /api/content | CRUD generated content |
| GET/POST/PATCH | /api/keywords | DM keywords + deliverables |
| GET/PATCH | /api/brand | Brand config |
| GET | /api/dashboard | Aggregate metrics |
| GET/POST | /api/calendar | Schedule + queue |
| POST | /api/export | word / gdocs / csv / ghl_map |
| GET | /api/integrations | Connection status |
| POST | /api/webhooks/ghl | GHL DM keyword inbound |

## Architecture

- `core/generator.py` — orchestrates RAG retrieve → prompt → Claude → validate → store
- `core/ingestion.py` — DOCX/PDF parsing, chunking (800 tokens / 100 overlap), embedding, indexing
- `core/retrieval.py` — pgvector similarity via `match_chunks` RPC
- `core/cross_analysis.py` — compares new uploads against existing library, surfaces synthesis angles
- `core/duplicate_check.py` — `usage_log` table feeds avoidance list back into every prompt
- `core/compliance.py` — NMLS footer, NY exclusion, prohibited language, word-count validation
- `prompts/system_prompt.txt` — cached static brand brief
- `integrations/claude_client.py` — two cache breakpoints (system + retrieved chunks)
