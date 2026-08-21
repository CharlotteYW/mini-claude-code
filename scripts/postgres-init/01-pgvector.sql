-- Enable pgvector on first Postgres boot.
-- Used later for embeddings; unused in M0 (provision vs use).
CREATE EXTENSION IF NOT EXISTS vector;
