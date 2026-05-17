# Architecture

Detailed system design for the multi-tenant keyword discovery and
clustering pipeline.

For strategic context and decisions, see
[PROJECT_BRIEF.md](../PROJECT_BRIEF.md) and
[docs/decisions-and-reasoning.md](decisions-and-reasoning.md).

For per-phase specifications, see
[docs/pipeline-phases.md](pipeline-phases.md).

## How to read this doc

Each section below is either:

- **Specified** — has concrete answers and code references. Treat as
  current truth.
- **OPEN** — lists the specific questions that must be answered before
  the corresponding code is written. The first commit implementing that
  area must replace the OPEN block with answers.

OPEN sections are deliberately short and pointed. Long aspirational
placeholders accumulate; checklists either get ticked or get noticed.

---

## System Overview

**OPEN** — answer when the first phase is implemented.

1. What is the top-level entry point? (`pipeline/run.py:main`? a Click
   group?)
2. How is a phase invoked from the CLI vs. from another phase?
3. Does any phase ever call another phase directly, or is the only
   composition path "CLI invokes them in sequence"?
4. Where does the runtime read config from — a single load at startup,
   or per-phase?

---

## Multi-Tenancy

**Specified (column level):** every non-`sites` table has
`site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE`. See
`schema/schema.sql` and CLAUDE.md "Multi-tenant from day one."

**OPEN** — answer when `pipeline/utils/database.py` is written.

1. How is `site_id` enforced in queries — a wrapper that injects
   `WHERE site_id = $1`, or by convention only?
2. Denormalized `site_id` on child tables (`keyword_serps`,
   `keyword_embeddings`, `cluster_members`, `topic_keywords`,
   `topic_relationships`) is not constrained to match the parent's
   `site_id`. Acceptable for now (service-role pipeline only) but
   becomes a multi-tenant integrity bug as soon as RLS policies are
   added. Decide: composite FK now, trigger now, or document as a
   known limitation with an ADR?
3. RLS policies are deferred until team UI. The trigger for adding
   them must be defined: which event (first non-service-role
   connection? team UI design doc?) initiates that work?

---

## Database Layer

**OPEN** — answer when `pipeline/utils/database.py` is written.

1. Sync or async? (Supabase Python client supports both.)
2. Connection pooling: rely on Supabase's pooler URL, pgbouncer, or
   neither?
3. Where do transactions start and end — per phase, per logical unit
   inside a phase, or per row?
4. How does the layer expose pgvector inserts? (Halfvec casts need
   explicit handling — `[0.5, 0.5, ...]::halfvec(3072)` works in raw
   SQL, but the Python client may or may not handle it.)
5. Do we use raw SQL, an ORM (SQLAlchemy), or query builders? CLAUDE.md
   R2 says "all DB ops through `pipeline/utils/database.py`" — what
   does that module's public surface look like?

---

## API Client Patterns

**OPEN** — answer when the first of `pipeline/utils/dataforseo.py`,
`openai_client.py`, `claude_client.py` is written.

1. Shared base class or three independent clients? What's actually
   shared (retry, rate limiting, cost tracking)?
2. Retry policy: exponential backoff with what max attempts? Which
   status codes are retriable?
3. Rate limiting: client-side token bucket, or rely on server 429
   responses?
4. Per-call cost tracking: does each call return its cost alongside
   the result, or does the client accumulate into a per-job counter?
   (This decision feeds the Cost Management section below.)
5. How are API keys loaded — at client construction, lazily on first
   call, or from a central secrets manager?

---

## Configuration System

**OPEN** — answer when `pipeline/utils/config.py` is written.

1. Pydantic v2 models for the YAML schema — yes/no? If yes, where do
   they live and how are they kept in sync with the example YAML?
2. Where is intent enum validation enforced? (The schema does not
   constrain `raw_keywords.primary_intent` to the YAML enum — see
   `docs/decisions-log.md` need-to-write ADR.)
3. How are env vars merged with YAML — env wins, YAML wins, or
   namespace separation (e.g., env for secrets only, YAML for behavior)?
4. Site config is mutable (e.g., `google_sheets.sheet_id` populated
   after first export). What writes back to the YAML file, and is
   that write captured in git or in the DB only?

---

## Phase Orchestration

**OPEN** — answer when `pipeline/run.py` is written.

1. `@track_job` decorator: what's its signature and what does it wrap?
   (CLAUDE.md mandates its use but no implementation exists yet.)
2. How are phase dependencies declared — a static graph, runtime
   checks against `pipeline_jobs`, or implicit through CLI ordering?
3. `--force` is the only re-run modifier (see prior review). Add
   partial re-run flags? Defer? Decide here.
4. How does the runner detect mid-phase failures and recover? Per-row
   commit pattern, or restart-from-scratch with idempotent inserts?

---

## Error Handling

**OPEN** — answer alongside Phase Orchestration.

1. Categories: recoverable (transient API failure), fatal (config
   invalid), partial (some rows failed, others succeeded). How does
   each propagate up to `pipeline_jobs.status`?
2. Errors hitting `pipeline_jobs.error_message` are TEXT — truncate
   or summarize long tracebacks? `error_traceback` is separate; what
   goes where?
3. Are errors raised, returned as result objects, or both? Pick one
   convention and apply across all phases.

---

## Cost Management

**OPEN** — answer when the first API client is written.

1. `MAX_RUN_COST_USD` is currently decorative (env var declared, no
   mechanism). Two paths: build pre-run estimation (hard) or convert
   it into a kill-switch that aborts when running total exceeds
   threshold (easier). Pick one.
2. Where is per-call cost recorded — `pipeline_jobs.output_summary`,
   a separate `api_calls` table, or both?
3. The README claims ~$15-20 per site run; ADR-002 says ~$0.10 for
   embeddings. Are these reconciled? When the first real run
   happens, replace the rough estimates with actuals.

---

## Testing Approach

**Specified (MVP):** no unit or integration tests for the 8-hour build
(see `docs/decisions-and-reasoning.md` → Rejected: Test coverage for
MVP). Database state is the success signal.

**OPEN** — revisit when the second site launches or the first VA is
onboarded.

1. What's the minimum smoke test for a fresh deploy? (Currently:
   manual `schema/schema.sql` against a throwaway db.) Turn that into
   a script.
2. What's the minimum smoke test for the pipeline itself? (Suggestion:
   a fixture site with 50 hand-crafted keywords that exercises every
   phase end-to-end against a local pgvector.)
3. When tests do get added, where do they live — `tests/` at repo
   root, or `pipeline/tests/`?

---

## How This Document Is Maintained

This document captures architectural patterns. Update it when:

- A new cross-cutting pattern is established (error handling, logging,
  API client structure)
- A pattern is changed (breaking change, refactor)
- A new component is added (new utility, new integration)
- An **OPEN** section is resolved — replace the question list with the
  answers and code references.

Don't update for:

- Phase-specific details (those go in `pipeline-phases.md`)
- Specific decisions and tradeoffs (those go in `decisions-log.md`)
- Schema details (those go in `database-schema.md`)
