-- Add 'filtered_language' to fanout.keyword_status. The pre-embedding language-ID
-- filter (lingua-py) tags keywords whose detected language is not English with
-- high confidence — caught after the junk filter, before embedding. DataForSEO is
-- locked to en/US but its related/autocomplete endpoints occasionally surface
-- non-English Latin-script phrases when the dominant terms happen to share
-- spelling with English (e.g. "wat is een managed service provider"); the
-- embedding-cosine relevance gate then accepts them because most of the string
-- embeds close to the English equivalent.
--
-- ALTER TYPE ... ADD VALUE cannot run inside an explicit transaction block, so
-- this migration MUST be the only statement in the file (Supabase's migration
-- runner applies each file as a single batch). The IF NOT EXISTS clause keeps it
-- idempotent across re-runs (Postgres 12+).

alter type fanout.keyword_status add value if not exists 'filtered_language';
