# Schema Migrations

Sequential migrations for the multi-tenant keyword discovery and
clustering pipeline. Each file is a forward-only change to the database
schema.

## File layout

```
schema/
├── schema.sql                                        # CANONICAL current state — use for fresh deploys
└── migrations/
    ├── README.md                                     # this file
    ├── 20260517185927_kw_clustering_initial_schema.sql
    ├── YYYYMMDDHHmmss_<description>.sql
    └── ...
```

## The two files contract

- **`schema/schema.sql`** is what you run against a **fresh database**. It
  always reflects the full schema at HEAD.
- **`schema/migrations/YYYYMMDDHHmmss_*.sql`** are what you run against an
  **existing database** to bring it up to HEAD. They are sequential diffs
  with timestamp-prefixed names matching Supabase's tracking convention.

**Every schema change must update both.** If you add a column via
`20260601120000_add_X_to_topics.sql`, you must also edit `schema.sql` to
include the column in the `CREATE TABLE topics` block.

## Naming

`YYYYMMDDHHmmss_<snake_case_description>.sql`, where the timestamp is the
UTC instant the migration was *authored* (not applied). Matches Supabase's
`apply_migration` server-side tracking format — see
[ADR-020](../../docs/decisions-log.md). The `<description>` part is what
gets passed as the `name` argument to `apply_migration`.

Generate a timestamp with: `date -u +%Y%m%d%H%M%S`.

Never renumber. Never edit a migration that has been applied to any real
database — add a new one instead.

## Required structure for each migration

```sql
-- ============================================================================
-- Migration <timestamp>: <description>
-- ============================================================================
-- Why: <one-line rationale, linked to docs/decisions-log.md ADR if relevant>
-- ============================================================================

\set ON_ERROR_STOP on
BEGIN;

-- Schema namespace (ADR-019). SET LOCAL keeps the search_path
-- transaction-scoped — won't leak into other queries on the pooled
-- connection after COMMIT.
SET LOCAL search_path TO kw_clustering, public, extensions;

-- Your DDL here. Use IF NOT EXISTS / IF EXISTS where possible so the
-- migration is idempotent — safe to re-run against a partially-applied db.

COMMIT;
```

`ON_ERROR_STOP on` is non-negotiable. Without it, psql swallows errors
and "succeeds" with a partial schema. (This is exactly how the original
HNSW-on-3072 bug almost shipped.)

**Schema namespace.** All pipeline tables live in `kw_clustering`,
not `public` (ADR-019). Every migration must include the
`SET LOCAL search_path` line above. Without it, new objects land in
`public` and break the isolation.

## Running migrations

There is no migration runner yet. For now:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema/migrations/20260517185927_kw_clustering_initial_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema/migrations/<next-timestamp>_<desc>.sql
# ...etc
```

When deploying to Supabase via the MCP `apply_migration` tool, pass the
`name` (the portion after the timestamp) so the server-side
`supabase_migrations.schema_migrations` entry has matching metadata:

```
mcp__supabase__apply_migration(
    name="kw_clustering_initial_schema",  # matches the file's name suffix
    query="<contents of the migration file, sans psql meta-commands>"
)
```

Supabase generates its own `version` timestamp at apply time. The file's
authoring timestamp and Supabase's apply timestamp may differ by minutes
or hours; that's fine — the `name` suffix is the unifying identifier
between the file and the server record.

A migration runner that aligns these (or accepts the file's timestamp as
the version) will land when the CLI is built. A `_migrations` tracking
table local to non-Supabase deploys is not yet defined; add one when
the runner is built.

## Data migrations

DDL-only migrations are idempotent and safe to re-run. Data
backfills (UPDATEs against existing rows) are not. When you write a
data migration:

1. Make it idempotent where possible (e.g., `UPDATE ... WHERE col IS NULL`)
2. State explicitly at the top of the file: `-- NOT IDEMPOTENT — run once`
3. Consider whether it belongs in the schema migration at all, or
   should be a separate one-shot script in `scripts/`.

## When to add a migration vs edit schema.sql only

- **Pre-launch, no deployments yet:** edit `schema.sql` directly AND
  edit `20260517185927_kw_clustering_initial_schema.sql` to match.
  There's nothing to migrate.
- **Any time after a real deploy exists:** add a new
  `schema/migrations/YYYYMMDDHHmmss_*.sql` AND update `schema.sql`.
  Never edit past migrations.
