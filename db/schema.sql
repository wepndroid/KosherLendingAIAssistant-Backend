-- KosherLending AI Content OS — Supabase schema
-- Apply via: psql $SUPABASE_DB_URL -f schema.sql
-- or paste into Supabase SQL editor.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─── Knowledge base ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  file_type TEXT,
  file_size_bytes BIGINT,
  storage_path TEXT,
  status TEXT DEFAULT 'Uploaded',
  total_chunks INTEGER DEFAULT 0,
  pillars TEXT[] DEFAULT '{}',
  summary TEXT,
  cross_analysis JSONB,
  uploaded_at TIMESTAMPTZ DEFAULT NOW(),
  indexed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  chunk_text TEXT NOT NULL,
  embedding vector(1536),
  metadata JSONB,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON knowledge_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON knowledge_chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON knowledge_chunks(document_id);

-- ─── DM keywords + deliverables ────────────────────────────────
CREATE TABLE IF NOT EXISTS dm_deliverables (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  keyword TEXT,
  title TEXT,
  category TEXT,
  content_markdown TEXT,
  storage_path TEXT,
  source_books TEXT[] DEFAULT '{}',
  ghl_workflow_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dm_keywords (
  keyword TEXT PRIMARY KEY,
  category TEXT,
  pillars TEXT[] DEFAULT '{}',
  intent TEXT,
  cta_template TEXT,
  deliverable_id UUID REFERENCES dm_deliverables(id),
  ghl_status TEXT DEFAULT 'Pending',
  usage_count INTEGER DEFAULT 0,
  last_used TIMESTAMPTZ,
  status TEXT DEFAULT 'Active',
  summary TEXT
);

-- ─── Generated content ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS generated_content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic TEXT NOT NULL,
  pillar TEXT NOT NULL,
  platform TEXT,
  platform_targets TEXT[] DEFAULT '{}',
  duration TEXT,
  word_count INTEGER,
  status TEXT DEFAULT 'Draft',
  hook TEXT,
  script TEXT,
  on_screen TEXT,
  production_brief TEXT,
  caption TEXT,
  caption_tiktok TEXT,
  caption_instagram TEXT,
  caption_linkedin TEXT,
  caption_facebook TEXT,
  caption_x TEXT,
  cta TEXT,
  cta_structure TEXT,
  dm_keyword TEXT,
  deliverable TEXT,
  hashtags TEXT[] DEFAULT '{}',
  source_book TEXT,
  source_framework TEXT,
  source_reason TEXT,
  source_chunks UUID[] DEFAULT '{}',
  experience_named TEXT,
  perspective_shift TEXT,
  angle_embedding vector(1536),
  duplicate_risk TEXT DEFAULT 'Low',
  scheduled_for DATE,
  scheduled_time TIME,
  posted_at TIMESTAMPTZ,
  ghl_post_id TEXT,
  validations JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_content_status ON generated_content(status);
CREATE INDEX IF NOT EXISTS idx_content_scheduled ON generated_content(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_content_pillar ON generated_content(pillar);
CREATE INDEX IF NOT EXISTS idx_content_angle ON generated_content
  USING ivfflat (angle_embedding vector_cosine_ops) WITH (lists = 100);

-- ─── Duplicate prevention ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id UUID REFERENCES generated_content(id) ON DELETE CASCADE,
  topic TEXT,
  source_book TEXT,
  framework TEXT,
  pillar TEXT,
  platform TEXT,
  state_referenced TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_recent ON usage_log(created_at DESC);

-- ─── Brand config (singleton row) ─────────────────────────────
CREATE TABLE IF NOT EXISTS brand_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_name TEXT,
  product_name TEXT,
  creator_name TEXT,
  nmls TEXT,
  website TEXT,
  voice_description TEXT,
  compliance_footer TEXT,
  excluded_states TEXT[] DEFAULT '{}',
  licensed_states TEXT[] DEFAULT '{}',
  pillars JSONB,
  cta_structures JSONB,
  posting_windows JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Posting queue ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS posting_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id UUID REFERENCES generated_content(id) ON DELETE CASCADE,
  platform TEXT,
  scheduled_for TIMESTAMPTZ,
  status TEXT DEFAULT 'Queued',
  ghl_response JSONB,
  error TEXT,
  attempts INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_queue_due ON posting_queue(status, scheduled_for);

-- ─── Exports ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  format TEXT NOT NULL,
  posts INTEGER DEFAULT 0,
  status TEXT DEFAULT 'Preparing',
  storage_path TEXT,
  download_url TEXT,
  filters JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Auth ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name TEXT,
  role TEXT DEFAULT 'admin',
  scoped_resources JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_login TIMESTAMPTZ
);

-- ─── Client portal (Phase 3) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS client_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  scope TEXT,
  messages JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Batch jobs (persistent across restarts) ──────────────────
CREATE TABLE IF NOT EXISTS batch_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT DEFAULT 'Running',          -- Running | Done | Failed | Cancelled
  total INTEGER NOT NULL,
  completed INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0,
  request JSONB,                          -- the BatchRequest snapshot
  cost_estimate JSONB,                    -- { tokens_in, tokens_out, dollars }
  results JSONB DEFAULT '[]'::jsonb,      -- last-N results
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_batch_status ON batch_jobs(status);

-- ─── Activity feed ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text TEXT NOT NULL,
  icon TEXT DEFAULT 'check',
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── pgvector RPC: pure similarity (kept for fallback) ────────
CREATE OR REPLACE FUNCTION match_chunks(
  query_embedding vector(1536),
  match_count INT DEFAULT 8,
  filter_pillar TEXT DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  chunk_text TEXT,
  metadata JSONB,
  similarity FLOAT
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    kc.id,
    kc.document_id,
    kc.chunk_text,
    kc.metadata,
    1 - (kc.embedding <=> query_embedding) AS similarity
  FROM knowledge_chunks kc
  JOIN knowledge_documents kd ON kd.id = kc.document_id
  WHERE kd.status = 'Indexed'
    AND (filter_pillar IS NULL OR filter_pillar = ANY(kd.pillars))
  ORDER BY kc.embedding <=> query_embedding
  LIMIT match_count;
END; $$;

-- ─── Hybrid retrieval RPC: vector + full-text + RRF fusion ────
-- Returns top-N candidates by Reciprocal Rank Fusion across the two signals.
CREATE OR REPLACE FUNCTION hybrid_match_chunks(
  query_embedding vector(1536),
  query_text TEXT,
  match_count INT DEFAULT 30,
  filter_pillar TEXT DEFAULT NULL,
  rrf_k INT DEFAULT 60
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  chunk_text TEXT,
  metadata JSONB,
  vector_rank INT,
  keyword_rank INT,
  rrf_score FLOAT
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH vec AS (
    SELECT kc.id, kc.document_id, kc.chunk_text, kc.metadata,
           ROW_NUMBER() OVER (ORDER BY kc.embedding <=> query_embedding) AS rnk
    FROM knowledge_chunks kc
    JOIN knowledge_documents kd ON kd.id = kc.document_id
    WHERE kd.status = 'Indexed'
      AND (filter_pillar IS NULL OR filter_pillar = ANY(kd.pillars))
    ORDER BY kc.embedding <=> query_embedding
    LIMIT match_count * 2
  ),
  kw AS (
    SELECT kc.id, kc.document_id, kc.chunk_text, kc.metadata,
           ROW_NUMBER() OVER (ORDER BY ts_rank(kc.tsv, plainto_tsquery('english', query_text)) DESC) AS rnk
    FROM knowledge_chunks kc
    JOIN knowledge_documents kd ON kd.id = kc.document_id
    WHERE kd.status = 'Indexed'
      AND (filter_pillar IS NULL OR filter_pillar = ANY(kd.pillars))
      AND kc.tsv @@ plainto_tsquery('english', query_text)
    ORDER BY ts_rank(kc.tsv, plainto_tsquery('english', query_text)) DESC
    LIMIT match_count * 2
  ),
  fused AS (
    SELECT
      COALESCE(vec.id, kw.id) AS id,
      COALESCE(vec.document_id, kw.document_id) AS document_id,
      COALESCE(vec.chunk_text, kw.chunk_text) AS chunk_text,
      COALESCE(vec.metadata, kw.metadata) AS metadata,
      vec.rnk::INT AS vector_rank,
      kw.rnk::INT AS keyword_rank,
      COALESCE(1.0/(rrf_k + vec.rnk), 0) + COALESCE(1.0/(rrf_k + kw.rnk), 0) AS rrf_score
    FROM vec
    FULL OUTER JOIN kw ON vec.id = kw.id
  )
  SELECT * FROM fused
  ORDER BY rrf_score DESC
  LIMIT match_count;
END; $$;

-- ─── Angle similarity for idea-level dedup ────────────────────
CREATE OR REPLACE FUNCTION match_angle(
  query_embedding vector(1536),
  window_days INT DEFAULT 90,
  match_count INT DEFAULT 5,
  similarity_floor FLOAT DEFAULT 0.75
)
RETURNS TABLE (
  id UUID,
  topic TEXT,
  pillar TEXT,
  hook TEXT,
  similarity FLOAT,
  created_at TIMESTAMPTZ
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT gc.id, gc.topic, gc.pillar, gc.hook,
         1 - (gc.angle_embedding <=> query_embedding) AS similarity,
         gc.created_at
  FROM generated_content gc
  WHERE gc.angle_embedding IS NOT NULL
    AND gc.created_at >= NOW() - (window_days || ' days')::interval
    AND 1 - (gc.angle_embedding <=> query_embedding) >= similarity_floor
  ORDER BY gc.angle_embedding <=> query_embedding
  LIMIT match_count;
END; $$;
