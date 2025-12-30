-- Initialize PostgreSQL with pgvector extension
-- This runs when the container is first created

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable other useful extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text similarity
CREATE EXTENSION IF NOT EXISTS btree_gin; -- For GIN indexes

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized with pgvector extension';
END $$;
