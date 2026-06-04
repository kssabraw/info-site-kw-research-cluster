-- Add 'filtered_language' to fanout.keyword_status. The pre-embedding language-ID
-- filter (lingua-py) tags keywords whose detected language is not English with
-- high confidence — caught after the junk filter, before embedding. DataForSEO is
-- locked to en/US but its related/autocomplete endpoints occasionally surface
-- non-English Latin-script phrases when the dominant terms happen to share
-- spelling with English (e.g. "wat is een managed service provider"); the
-- embedding-cosine relevance gate then accepts them because most of the string
-- embeds close to the English equivalent.
--
-- Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction block, but
-- the newly-added enum value cannot be USED in the same transaction. This file
-- only adds the value (no inserts/updates that reference it), so it's safe to
-- run as a single migration regardless of how Supabase wraps it. The IF NOT
-- EXISTS clause makes the migration idempotent across re-runs.

alter type fanout.keyword_status add value if not exists 'filtered_language';
