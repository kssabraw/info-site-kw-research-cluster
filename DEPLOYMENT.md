# Deployment

Current deployment instance for the keyword discovery & clustering
pipeline. **This file describes one specific deployment**, not the
codebase. If you fork the repo or stand up a second instance, copy
this file as a template and replace the values.

For codebase conventions (schema namespace, search_path requirement,
critical rules), see [CLAUDE.md](CLAUDE.md). For the design rationale
behind the namespace choice, see
[docs/decisions-log.md](docs/decisions-log.md) ADR-019.

## Current instance

| | |
|---|---|
| **Supabase project name** | AR-Internal-Tools |
| **Project ref** | `wvcthtmmcmhkybcesirb` |
| **API URL** | `https://wvcthtmmcmhkybcesirb.supabase.co` |
| **Region** | `us-west-1` |
| **Postgres version** | 15.8 |
| **pgvector version** | 0.8.0 (in `public` schema) |
| **Pipeline schema** | `kw_clustering` |
| **Tables in `kw_clustering`** | 15 |
| **Sites registered** | 1 (`retatrutide`, id=1) |
| **Last migration applied** | `20260517193622_rename_updated_at_function` (per ADR-021) |
| **State last verified** | 2026-05-17 |

The project is **shared** with the unrelated AR-Internal-Tools
application sitting in the `public` schema (9 tables). The namespace
isolation per ADR-019 keeps the two workloads from colliding.

## Deploy to a fresh instance

If you're standing up a *new* deployment (different Supabase project),
the process is:

1. Create the project in Supabase Studio. Note its ref.
2. Add `DATABASE_URL` and `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` to
   your local `.env` (see `.env.example`).
3. Apply migrations in order. Either:
   ```bash
   for f in schema/migrations/*.sql; do
     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
   done
   ```
   Or via the Supabase MCP `apply_migration` tool (one call per file,
   passing the `name` portion after the timestamp).
4. Verify per the README's deploy steps (count tables in
   `kw_clustering`, confirm `idx_embeddings_hnsw` exists).
5. Register your first site:
   ```sql
   INSERT INTO kw_clustering.sites (slug, domain, display_name, niche_description, config)
   VALUES ('your_slug', 'your.com', 'Display Name', 'niche description', '{}'::jsonb);
   ```
6. Copy this file, fill in the new instance's values.

## Multiple instances

This file describes one instance. If a future contributor adds another
deployment (e.g., a staging instance, or a fork running a different
portfolio), the cleanest patterns are:

- Add a new top-level section per instance ("## Production",
  "## Staging") with the same table of facts.
- Or fork this file (`DEPLOYMENT.production.md`, `DEPLOYMENT.staging.md`).

Either way, **don't put per-instance facts in CLAUDE.md** — it's a
codebase doc, not a deployment registry.
