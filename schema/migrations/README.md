# Schema Migrations

Sequential migrations for the multi-tenant keyword discovery and clustering
pipeline. Each file is a forward-only change to the database schema.

## File layout

```
schema/
├── schema.sql              # CANONICAL current state — use for fresh deploys
└── migrations/
    ├── README.md           # this file
    ├── 0001_initial_schema.sql
    ├── 0002_<description>.sql
    └── ...
```

## The two files contract

- **`schema/schema.sql`** is what you run against a **fresh database**. It
  always reflects the full schema at HEAD.
- **`schema/migrations/NNNN_*.sql`** are what you run against an **existing
  database** to bring it up to HEAD. They are sequential diffs.

**Every schema change must update both.** If you add a column via
`0002_add_X_to_topics.sql`, you must also edit `schema.sql` to include the
column in the `CREATE TABLE topics` block.

## Naming

`NNNN_<snake_case_description>.sql` where `NNNN` is a zero-padded
sequential integer starting at `0001`. Never renumber. Never edit a
migration that has been applied to any real database — add a new one
instead.

## Required structure for each migration

```sql
-- ============================================================================
-- Migration NNNN: <description>
-- ============================================================================
-- Why: <one-line rationale, linked to docs/decisions-log.md ADR if relevant>
-- ============================================================================

\set ON_ERROR_STOP on
BEGIN;

-- Your DDL here. Use IF NOT EXISTS / IF EXISTS where possible so the
-- migration is idempotent — safe to re-run against a partially-applied db.

COMMIT;
```

`ON_ERROR_STOP on` is non-negotiable. Without it, psql swallows errors
and "succeeds" with a partial schema. (This is exactly how the original
HNSW-on-3072 bug almost shipped.)

**Schema namespace.** All pipeline tables live in `kw_clustering`,
not `public` (ADR-019). Every migration must include:

```sql
SET search_path TO kw_clustering, public, extensions;
```

near the top, AFTER any `CREATE SCHEMA IF NOT EXISTS kw_clustering`
if a future migration introduces new schemas. Without it, new objects
land in `public` and break the isolation.

## Running migrations

There is no migration runner yet. For now:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema/migrations/0001_initial_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema/migrations/0002_<desc>.sql
# ...etc
```

When the pipeline gets a CLI entry point, a `--migrate` subcommand will
read this directory and apply unapplied migrations in order. Until then,
this is manual. A `_migrations` tracking table is not yet defined; add
one when the runner is built.

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
  edit `0001_initial_schema.sql` to match. There's nothing to migrate.
- **Any time after a real deploy exists:** add a new
  `schema/migrations/NNNN_*.sql` AND update `schema.sql`. Never edit
  past migrations.
