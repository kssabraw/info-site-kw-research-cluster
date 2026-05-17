-- ============================================================================
-- Migration 20260517193436_rename_updated_at_function
-- ============================================================================
-- Why: The function created by migration 20260517185927 was named
-- update_updated_at_column — colliding with public.update_updated_at_column
-- and storage.update_updated_at_column on Supabase (verified: 3 hits in
-- pg_proc). Triggers bind by oid so it's functionally safe, but the name
-- collision is a latent ambiguity for anyone running the function
-- ad-hoc with search_path covering multiple schemas. See ADR-021.
--
-- This migration renames kw_clustering.update_updated_at_column to
-- kw_clustering.set_updated_at. Idempotent: a fresh DB deployed via
-- schema.sql already has set_updated_at and this is a no-op.
-- ============================================================================

\set ON_ERROR_STOP on
BEGIN;

SET LOCAL search_path TO kw_clustering, public, extensions;

-- Rename in place if the old name exists. ALTER FUNCTION ... RENAME
-- preserves the function oid, so triggers continue working without
-- needing to be dropped and recreated — they resolve the function by
-- oid and pg_get_triggerdef just shows the current name.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'kw_clustering'
          AND p.proname = 'update_updated_at_column'
    ) THEN
        ALTER FUNCTION kw_clustering.update_updated_at_column()
            RENAME TO set_updated_at;
    END IF;
END $$;

-- Safety net: if neither name exists (DB in an unexpected state),
-- create the new one so subsequent migrations and the canonical
-- schema.sql can rely on it.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

COMMIT;

-- ============================================================================
-- Migration 20260517193436 complete
-- ============================================================================
