# Session Handoff — 2026-05-17

Resume point for the next Claude Code session. Self-contained but
points at the existing docs for details.

---

## TL;DR

Multi-tenant keyword discovery & clustering pipeline. Docs, schema,
and conventions are fully scaffolded and reviewed (adversarially,
twice). Schema is deployed live to Supabase. **No Python code exists
yet** — the foundation scaffold (`pipeline/` package) is the next
work.

Repo: https://github.com/kssabraw/info-site-kw-research-cluster
Main branch: `main` (all session work merged via 8 PRs)
Working branch the session used: `claude/general-session-CDqn2`

If picking up fresh: clone, read `CLAUDE.md` first, then this file.

---

## What's live right now

**Supabase project:** `AR-Internal-Tools` (`wvcthtmmcmhkybcesirb`),
Postgres 15.8, pgvector 0.8.0. Full instance ledger in `DEPLOYMENT.md`.

- 15 tables in the `kw_clustering` schema (all RLS-enabled, no policies — see ADR-013)
- pgvector `vector`/`halfvec` types in `public` (pinned via `WITH SCHEMA public`)
- HNSW index `kw_clustering.idx_embeddings_hnsw` on `halfvec(3072)` embedding column
- One site registered: `retatrutide` (id=1) — empty otherwise
- 2 migrations applied:
  - `20260517185927_kw_clustering_initial_schema`
  - `20260517193622_rename_updated_at_function`

**Supabase MCP server is available** — the next session has tools
prefixed `mcp__cfcbc64b-...__*` for `list_projects`, `apply_migration`,
`execute_sql`, `list_tables`, `get_advisors`, etc. No need to ask the
user for credentials.

**GitHub MCP server is available** — tools `mcp__github__*` for PRs,
issues, etc.

---

## Critical conventions (read these in CLAUDE.md)

The convention checker at `scripts/check-conventions.sh` enforces most
of these. It no-ops today because `pipeline/` doesn't exist; it fires
the moment code lands.

- **All DB access through `pipeline/utils/database.py`** (no direct
  `psycopg`/`supabase`/`sqlalchemy` imports anywhere else)
- **All API clients live in `pipeline/utils/`** — `dataforseo.py`,
  `openai_client.py`, `claude_client.py`. Phases call these utilities
  only.
- **Config loading through `pipeline/utils/config.py`** — no direct
  `yaml.safe_load` or `os.environ` in phase modules.
- **`@track_job` decorator** on every `def run(...)` in
  `pipeline/phases/*.py`. CLAUDE.md R4.
- **Always pass `site_id` explicitly** — never derive from context/globals.
- **Idempotency** — phases safely re-runnable.

Plus the architectural contracts pinned in ADRs:

- **ADR-014** — `CostTracker` mandatory in every API client (running-total kill-switch on `MAX_RUN_COST_USD`)
- **ADR-015** — every phase splits `fetch` vs `derive`; `--rederive` runs only derive (zero API cost)
- **ADR-016** — phases iterating over API calls commit per-batch (sizes pinned per phase)
- **ADR-019** — pipeline tables in `kw_clustering` schema; `SET LOCAL search_path TO kw_clustering, public, extensions` on every transaction

Full ADR list in `docs/decisions-log.md` (21 ADRs).

---

## What this session did

Eight merged PRs against `main`. Each was a focused atomic change with
adversarial review at key checkpoints.

| PR | Title | What it did |
|---|---|---|
| #1 | Scaffold project: docs, schema, conventions, Tier 1 + Tier 2 fixes | Initial scaffolding + 12 ADRs |
| #2 | Tier 3 fixes (ADRs 013–017) | RLS posture, cost tracker, fetch/derive, per-batch commit, commercial seeds |
| #3 | Close remaining adversarial review findings | C2 composite FK gap, M1 cluster self/cross-site merge, H5 DATABASE_URL, `.gitignore`, plus 6 docs/cleanup items |
| #4 | Deploy schema to Supabase in `kw_clustering` namespace (ADR-019) | Live deploy + namespace isolation |
| #5 | Pin pgvector to public schema (C1 fix) | `CREATE EXTENSION ... WITH SCHEMA public` before SET search_path |
| #6 | Qualify README SQL examples with `kw_clustering.` (H1) | Setup-step queries now work in fresh sessions |
| #7 | Migration hygiene (M2, M3, M4) | Timestamp filenames, SET LOCAL, function rename `set_updated_at` (ADR-020, ADR-021) |
| #8 | L2: Move deployment instance facts out of CLAUDE.md into DEPLOYMENT.md | Last review finding closed |

Every adversarial review finding from this session is resolved.

---

## Status checklist (from CLAUDE.md)

- [x] Project scaffold and database schema
- [x] Schema deployed to Supabase and retatrutide site registered
- [ ] Phase 00: Concept mapping
- [ ] Phase 01: Seed expansion
- [ ] Phase 02: SERP fetching
- [ ] Phase 03: URL + domain frequency analysis
- [ ] Phase 04: URL-level keyword mining
- [ ] Phase 05: Domain-level keyword mining
- [ ] Phase 06: Relevance filtering
- [ ] Phase 07: Volume enrichment
- [ ] Phase 08: Intent classification
- [ ] Phase 09: Embedding generation
- [ ] Phase 10: HDBSCAN clustering
- [ ] Phase 11: SERP overlap refinement
- [ ] Phase 12: Review export and import
- [ ] Approved topics exported to topics table

**Each phase has an OPEN block in `docs/pipeline-phases.md`** with
specific unanswered questions. The phase-completion contract in
CLAUDE.md requires: (1) tick the checkbox, (2) replace the OPEN block
with a Specified entry, (3) link any new ADRs — all in the same commit.

---

## Immediate next step: foundation scaffold

The contracts are defined; this is what they're defined against.
Roughly 500 lines split across these files:

```
pyproject.toml                              # uv-managed deps
pipeline/__init__.py
pipeline/run.py                             # CLI entry point (Click or argparse)
pipeline/utils/__init__.py
pipeline/utils/database.py                  # Supabase connection, MUST set search_path
pipeline/utils/config.py                    # YAML + env loading, Pydantic models
pipeline/utils/cost_tracker.py              # ADR-014 implementation
pipeline/utils/dataforseo.py                # DataForSEO client
pipeline/utils/openai_client.py             # OpenAI client (embeddings)
pipeline/utils/claude_client.py             # Anthropic client (Haiku, Sonnet, Opus)
pipeline/utils/normalize.py                 # ADR-006 keyword normalizer
pipeline/utils/track_job.py                 # @track_job decorator
pipeline/phases/__init__.py
pipeline/phases/_template.py                # Template phase module showing the pattern
```

**What `pipeline/utils/database.py` MUST do** (per the OPEN block in
`docs/architecture.md` Database Layer):
- Wrap the Supabase Python client (or psycopg directly — your call)
- Set `search_path TO kw_clustering, public, extensions` on every connection
- Provide a query interface that always takes `site_id` as a parameter
- Expose `unprocessed_for_phase(site_id, phase_name)` for resume queries (ADR-016)
- Handle halfvec(3072) inserts (the pgvector Python lib supports this; OpenAI returns float32, cast at insert time)

**`CostTracker` per ADR-014** — `pipeline/utils/cost_tracker.py`:
- One instance per pipeline run (threaded via phase context or contextvar)
- `check(estimated_cost)` raises `CostBudgetExceeded` if would exceed cap
- `charge(method_name, cost)` after successful API response
- Writes running total to `pipeline_jobs.output_summary` on every charge
- Loaded with `MAX_RUN_COST_USD` from env at init (default 100)
- Cost constants in ADR-014's table

**`@track_job` decorator** — per CLAUDE.md R4:
- Wraps phase `def run(site_id, mode='normal', ...)` functions
- Creates `pipeline_jobs` row at entry, marks `running`
- On success: updates `status='completed'`, `output_summary`
- On exception: updates `status='failed'`, `error_message`, `error_traceback`
- Re-raises to caller

**Config loader** per `docs/architecture.md` Configuration System OPEN block:
- Pydantic v2 models for site YAML
- Env var loading
- Intent enum validation at config-load time (ADR — M7 from first review;
  schema doesn't enforce intent enum, so the loader is the gate)

**Once foundation lands**, the convention checker should pass cleanly
(`scripts/check-conventions.sh` — verify before first commit). Then
phase implementation can start.

---

## After foundation: phase ordering

Phases are independently runnable but have data dependencies:

```
00 Concept mapping ──┐
                     ▼
01 Seed expansion ───┐
                     ▼
02 SERP fetching ────┐
                     ├── 03 URL/domain frequency analysis
                     │       │
                     │       ▼
                     │   04 URL-level mining
                     │   05 Domain-level mining
                     ▼       │
                  06 Relevance filtering ◄┘
                     │
                     ▼
                  07 Volume enrichment
                     │
                     ▼
                  08 Intent classification
                     │
                     ▼
                  09 Embedding generation
                     │
                     ▼
                  10 HDBSCAN clustering
                     │
                     ▼
                  11 SERP overlap refinement
                     │
                     ▼
                  12 Review export/import
```

Suggested implementation order:
1. Start with **Phase 09 (embeddings)** as a smoke test of the
   foundation — small surface area, exercises OpenAI client + halfvec
   inserts end-to-end, doesn't depend on previous phases (could feed
   it hand-crafted keywords).
2. Then **Phase 01 (seed expansion)** to start the actual pipeline.
3. Then phases in numeric order.

Phase 10 (HDBSCAN) and Phase 12 (review export) are already most-fully
specified — those are easier to implement against the existing specs.

---

## Known gotchas / things to verify

- **Local pgvector binary has a SIGILL bug** in this specific container
  for halfvec inserts (CPU instruction set mismatch from a source
  build). End-to-end halfvec testing works on Supabase but crashes
  Postgres locally. Not a code issue; environment-specific. If the next
  session uses a different container, may not reproduce. Tests
  against live Supabase are the source of truth for halfvec behavior.

- **Supabase migrations are recorded with apply-time timestamps**, not
  the file's authoring-time timestamp (ADR-020). They differ by
  minutes. The `<name>` suffix is the canonical identifier between
  local file and server record. See `schema/migrations/README.md`.

- **`update_updated_at_column` exists in `public` and `storage`** on
  the Supabase project — those are unrelated functions (AR-Internal-Tools
  app + Supabase storage). Ours is `kw_clustering.set_updated_at`.
  Don't touch the other two.

- **RLS is enabled on all 15 tables but no policies exist** (ADR-013).
  Non-`service_role` connections get zero rows. The first commit that
  introduces a `site_users` table, non-service-role connection, or
  team UI MUST also land policies in `schema/policies/`.

- **Pipeline tables share Supabase project with 9 unrelated tables in
  `public`**. The namespace isolation (ADR-019) keeps them apart, but
  the Supabase advisor still flags `public.sie_cache` (RLS-disabled
  on the AR-Internal-Tools side). That's not our problem; surface it
  to the user as a separate concern if it comes up.

- **`MAX_RUN_COST_USD=100` is the default in `.env.example`**. ADR-014
  enforces it via CostTracker. No mechanism yet (code not written).
  First API client to land must implement charge/check or the env var
  is decorative.

- **`output/` directory doesn't exist yet** — it's in `.gitignore`,
  Phase 12 will create it for CSV fallback.

---

## Verify state on entry (fresh session)

```bash
cd /path/to/info-site-kw-research-cluster
git log --oneline -5
git status                          # should be clean

# Convention checker (no-ops until pipeline/ exists)
bash scripts/check-conventions.sh   # should print "no pipeline/, exit 0"

# Read in this order
cat CLAUDE.md                       # start here
cat DEPLOYMENT.md                   # current Supabase instance
cat docs/decisions-log.md           # 21 ADRs
cat docs/pipeline-phases.md         # phase OPEN blocks
cat docs/architecture.md            # cross-cutting OPEN blocks
```

To verify Supabase live state (using MCP tools, no extra creds needed):

```
mcp__cfcbc64b-...__list_tables(project_id="wvcthtmmcmhkybcesirb",
                                schemas=["kw_clustering"], verbose=false)
# expect 15 tables

mcp__cfcbc64b-...__execute_sql(project_id="wvcthtmmcmhkybcesirb",
    query="SELECT slug FROM kw_clustering.sites;")
# expect [{"slug": "retatrutide"}]
```

---

## Open items (not blocking, but worth noting)

- **M7 from the first adversarial review** — intent enum has no
  DB-level validation. Defensible deferral; belongs in the Pydantic
  config loader when that lands. Document in an ADR at that time.

- **No tests** — per the strategic doc (Rejected: Test coverage for
  MVP), DB state is the success signal. Revisit when second site
  launches.

- **No CI** — convention checker is wired into `.pre-commit-config.yaml`
  but no GitHub Actions workflow yet. Add one when team adoption
  starts.

- **No migration runner** — `schema/migrations/README.md` says one
  will land when CLI gets built. Until then, manual `psql` or MCP
  `apply_migration` per file.

- **DataForSEO and OpenAI/Anthropic credentials not yet configured in
  `.env`** — `.env.example` has placeholders. Foundation code will
  read these via `pipeline/utils/config.py` (the canonical reader per
  CLAUDE.md R3).

---

## Quick reference

| Need to | Look at |
|---|---|
| Understand the project | `CLAUDE.md` then `PROJECT_BRIEF.md` |
| See the current Supabase deploy | `DEPLOYMENT.md` |
| Understand a design decision | `docs/decisions-log.md` (find by ADR-NNN) |
| Implement a phase | `docs/pipeline-phases.md` (find Phase NN's OPEN block) |
| Implement a utility module | `docs/architecture.md` (find the matching OPEN block) |
| Verify schema changes | `schema/schema.sql` (canonical), `schema/migrations/*.sql` (history) |
| Add a new ADR | Bottom of `docs/decisions-log.md`; follow the template at the top |
| Check a convention | `scripts/check-conventions.sh` (auto on commit via pre-commit) |

Good luck.
