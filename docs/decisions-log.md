# Decisions Log

Architecture Decision Records (ADRs) — narrowly-scoped, dated
implementation decisions. Each ADR documents one concrete choice with
its rationale and consequences.

## Which file does a decision go in?

There are two decision docs in this project. The split is:

| It belongs here (`decisions-log.md`) | It belongs in [`decisions-and-reasoning.md`](decisions-and-reasoning.md) |
|---|---|
| One specific technical choice | A class of decisions or a principle |
| Has a date and a status | Timeless / topic-organized |
| Could plausibly be reversed in a future ADR | Reversing it would mean rethinking the project |
| Example: "use HALFVEC(3072), not VECTOR(3072)" | Example: "use OpenAI embeddings, not Voyage" |

If you're not sure, default to **here** (ADR). Granular is fine; the
log is append-only and never deleted. The other doc is for thematic
reasoning — if a topic doesn't have a top-level section there already,
your decision probably isn't strategic enough to need one.

When an ADR captures the implementation of a strategic choice already
discussed in `decisions-and-reasoning.md`, link back to that section
rather than duplicating the reasoning.

## ADR format

```
## ADR-NNN: <Short title>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-MMM
- **Context:** What problem are we solving? What constraints exist?
- **Decision:** What was decided? (one sentence)
- **Consequences:** What follows? Both positive and negative.
- **Alternatives considered:** What else was evaluated and why rejected?
- **Related:** Optional cross-refs to other ADRs, docs, or code.
```

ADRs are numbered sequentially. Don't renumber. If superseded, mark
status and link to the new ADR rather than editing the old one.

---

## ADR-001: Use DataForSEO API exclusively for keyword discovery

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Need to discover ~10–15K keywords per niche. Industry
  default is Semrush at ~$140/month + manual CSV exports.
- **Decision:** Use DataForSEO API only. No Semrush.
- **Consequences:**
  - Programmatic end-to-end; no manual CSV step in any phase.
  - Cost drops from $140/month to ~$15-20 per site run.
  - Lose ~5-10% coverage of obscure long-tails.
  - Lose Semrush UI for data browsing (not needed since pipeline is
    headless).
- **Alternatives considered:** Semrush (manual workflow), hybrid
  (Semrush seeds → DataForSEO expansion), Ahrefs API. All rejected for
  reasons documented in the linked strategic discussion.
- **Related:** Full reasoning in [decisions-and-reasoning.md →
  Decision: DataForSEO only, not Semrush](decisions-and-reasoning.md#decision-dataforseo-only-not-semrush).

---

## ADR-002: Use OpenAI text-embedding-3-large for clustering embeddings

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Need an embedding model for HDBSCAN clustering of
  ~12-15K keywords per site. Options span Voyage 3 Large (best
  benchmarks), OpenAI 3-large (widely supported), Cohere Embed v4,
  BGE-M3 (self-hosted).
- **Decision:** OpenAI `text-embedding-3-large`, default 3072 dims with
  Matryoshka reduction available.
- **Consequences:**
  - One vendor surface (already using OpenAI elsewhere in pipeline).
  - Cost is negligible at our scale (~$0.10 per site run).
  - ~5% quality gap to Voyage on clustering benchmarks, accepted.
  - Matryoshka reduction to 1024 or 1536 available if storage becomes
    a constraint (it isn't at current scale).
- **Alternatives considered:** Voyage 3 Large (better but new SDK),
  BGE-M3 self-hosted (free but engineering overhead), older
  sentence-transformers (10-pt MTEB gap, outdated training data).
- **Related:** Full reasoning in [decisions-and-reasoning.md →
  Decision: OpenAI text-embedding-3-large, not Voyage or self-hosted](decisions-and-reasoning.md#decision-openai-text-embedding-3-large-not-voyage-or-self-hosted).

---

## ADR-003: Store embeddings as HALFVEC(3072), not VECTOR(3072)

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `text-embedding-3-large` is 3072-dim native (see
  ADR-002). pgvector's HNSW index has a hard 2000-dim ceiling on the
  `VECTOR` type. The original schema declared `VECTOR(3072)` plus a
  HNSW index, which fails at deploy with `column cannot have more than
  2000 dimensions for hnsw index` — and the failure was silent under
  psql's default `ON_ERROR_STOP=off`.
- **Decision:** Change `keyword_embeddings.embedding` to `HALFVEC(3072)`
  with a `halfvec_cosine_ops` HNSW index. pgvector's HNSW supports
  `HALFVEC` up to 4000 dims. Also enforce `ON_ERROR_STOP=1` in schema
  deployment so future partial-deploy failures surface.
- **Consequences:**
  - HNSW index now builds successfully on Supabase (pgvector 0.8.x).
  - Storage halves: ~6 KB per row (was ~12 KB), ~90 MB per site
    (was ~180 MB).
  - Half-precision arithmetic introduces sub-1% cosine error at 3072
    dims, well below the noise floor of HDBSCAN clustering on
    semantic-similarity vectors.
  - Adds a soft dependency on pgvector ≥ 0.7.0 (Supabase ships 0.8.x).
- **Alternatives considered:**
  - Reduce dimensions via Matryoshka to 1024 or 1536 (rejected: changes
    the dimensional commitment already made in three docs, and storage
    was not the constraint).
  - Use IVFFlat instead of HNSW (rejected: same 2000-dim ceiling).
- **Related:** ADR-002, `schema/migrations/0001_initial_schema.sql`,
  [database-schema.md → keyword_embeddings](database-schema.md#keyword_embeddings).

---

## How This Document Is Maintained

Add a new ADR when:

- A non-obvious technical choice is made (parameter tuned, library
  picked, tradeoff resolved)
- An implementation pattern is established that future code should
  follow
- The implementation of a strategic decision happens (link back to
  `decisions-and-reasoning.md`)

Don't add ADRs for:

- Obvious technical choices ("use UTF-8 encoding")
- Strategic principles or scoping (those belong in
  `decisions-and-reasoning.md`)
- Per-phase mechanics (those belong in `pipeline-phases.md`)

ADRs are numbered sequentially. Don't renumber when adding new ones.
If an ADR is superseded, mark its status (`Superseded by ADR-MMM`) and
link to the new ADR. Do not edit the body of a superseded ADR — history
is the point.
