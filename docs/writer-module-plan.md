# M13 — Writer Foundation: Build Plan

> **Re-sequenced 2026-06-12 (owner decision, same day this was drafted as
> "M12"):** the **SIE Term & Entity module now builds first as M12**
> (`docs/sie-module-plan.md`) — the Writer is **M13**, and scheduling + link
> injection shift to **M14**. Two consequences for this plan: **(a)** the §3
> adapter consumes the **real SIE output** (`fanout.keyword_analyses`) instead
> of the flat-keyword stub — the stub remains the documented fallback when no
> analysis exists; with real SIE data, per-zone term targets are real, the C6
> citable-claim pattern activates (`is_entity` exists), and the Δ4 relaxations
> below largely fall away. **(b)** Providers were re-decided: SIE runs
> ScrapeOwl + Google NLP as provisioned services (PRD-exact), which retires
> the "no new third-party services" framing in §1 — for the *Writer's own
> calls* nothing changes (Anthropic + OpenAI only). Milestone numbers in the
> body below were written before the re-sequence; read M12→M13 and M13→M14.
> (File renamed from `m12-writer-foundation-plan.md`.)

**Status:** Draft for owner review (2026-06-12). Nothing built.
**Sources:** `docs/blog-writer-pipeline-bundle.md` (the real PRDs, landed 2026-06-12),
`handoff.md §9` (the integration sketch + locked decisions §9.11), PRD #1 = Content
Writer Module v1.7 (bundle lines ~26–2470), Brief Gen v2.3 (for the
`intent_format_template` registry the adapter mirrors).

This document reconciles the §9 sketch (written from a conversation summary)
against the real Writer PRD, and specifies M12 per the §9.10 milestone split:
**port the Writer module + adapter + degraded-mode contract + a manual
owner-only `Generate now`**. No scheduling, no link injection (M13).

---

## 1. Reconciliation: §9 sketch vs. the real PRD

The sketch holds up well. Confirmed as-designed:

- **Degraded mode is a first-class documented path, not a hack.** `client_context`
  omitted → `schema_version_effective: "1.7-no-context"` (PRD §2.4, §6; test
  fixture **F-A** is literally our production path). Steps 3.5a/3.5b (brand
  distillation/reconciliation) skip; Step 3.6 placement-plan directives are not
  stamped when `brand_voice_card` is None (§5.7 bypass); Step 6.8 ICP judge
  returns `not_assigned`; banned-term regex is a no-op with an empty list
  (§5.17.1). `research.citations` empty → `no_citations: true`, "continue;
  sections written without citation grounding. **Not an abort**" (§2.5).
- **Model tiers match the §9.11 lock, with one refinement** — PRD §17 specifies
  **Sonnet for all prose calls** (sections, intro, FAQ, conclusion, takeaways)
  and **Haiku for short calls** (title candidates, CTA, ICP judge). §9.11 said
  "Sonnet 4.6 for all section calls" — same thing; we adopt §17 exactly.
  Explicitly: **no Opus** (§17: budget ceiling doesn't accommodate it).
- **Embeddings:** `text-embedding-3-small`, 1,536-dim (§19.1) — identical to
  this repo's locked choice; the PRD's cosine thresholds (0.62 adherence, 0.85
  takeaways-pair) are calibrated for it and port as-is.
- **Tech stack (§19.2):** Python 3.11 + FastAPI + httpx + `anthropic` tool-use +
  `openai` embeddings — all already in this repo. One new dep:
  **`titlecase==2.4.1`** (pinned; pure-python, no service).
- **Cost:** full-context estimate $0.32–$0.52, ceiling $0.75 (§11). Degraded
  mode drops distillation/reconciliation/judge (≈ −$0.04–$0.07) → **≈$0.25–$0.45
  /article**, consistent with §9.1's $0.20–$0.40.
- **Serialization (§5.19)** is pure/deterministic over `(article[], citations[])`
  — confirms M13's `link_injector` can run between assembly and Step 10 exactly
  as §9.5 plans.
- **Sections are written sequentially by design (D8)** — term-budget state is
  order-dependent. Do NOT parallelize H2-group calls. (The M13 worker's
  concurrency cap of 3 applies across *articles*, not within one.)

### The four deltas (sketch → real PRD)

**Δ1 — The adapter must generate the heading structure (the predicted H2 gap,
now concrete).** The Writer hard-depends on `brief.heading_structure[]`: Step 0
aborts if empty; budget allocation, the adherence filter, and section writing
are all keyed to it; intent templates expect 3–12 H2s. Our clusters persist
**empty** `h2_outline` (2026-06-09 writer-ownership decision). So the adapter
gains a **fourth LLM call: heading-structure generation**, guided by the Brief
Gen v2.3 `intent_format_template` registry (which the bundle supplies verbatim:
`h2_pattern`, `h2_framing_rule`, `ordering`, `anchor_slots`, min/max H2 counts
per intent). This is "the new step the external PRD didn't include" that
handoff §9.13 predicted. H2-only in v1 (no H3s — we have no SERP/authority-gap
signal to source them from); cached on `clusters.adapter_cache`.

**Δ2 — Title + scope are one call with a real contract, not a derivation.**
§9.2 sketched `scope_statement` as "derived from `clusters.intent` + name".
The bundle's Brief Gen Step 3.5 gives the actual contract: a single LLM call
producing `{title (50–80 chars, ≤100), scope_statement (≤500 chars, must
include a "does not cover" clause naming 1–3 adjacent topics), title_rationale}`,
with anti-AI-tell rules (no "Ultimate Guide to…", no reflexive year-stamping).
The adapter adopts this contract (minus the SERP inputs we don't have — it
grounds in the cluster's keywords instead). The scope statement matters
downstream: the intro's Promise beat anchors on it (§5.3).

**Δ3 — Citable-claim coverage (§5.8.8) should NOT be fully skipped.** §9.1's
sketch said "skip Step 4F + the §5.8.8 citable-claim retries". Correct for 4F
(no citation pool → no markers to place). But the real §5.8.8 reveals the
retry directive has a **second arm**: "…OR rewrite the sentence to remove the
specific statistic / year / brand attribution," plus the deterministic
**auto-soften** pass for operational claims (C7/C8/C9). In no-citations mode
this is an **anti-fabrication guard**: without it the Writer can emit uncited
statistics with nothing to catch them. **Recommendation (flagged, §8 below):**
run C1–C9 detection per section; one rewrite-to-remove retry; soften C7–C9;
accept + flag in `metadata.under_cited_sections`. Never aborts (PRD-consistent).
Cost: ≤1 retry/run steady-state per §11 (~$0.01–$0.03).

**Δ4 — Two constraints need degraded-mode relaxations the PRD doesn't define.**
(a) The **enrichment lede** (§5.2.2) requires ≥1 entity with `entity_category ∈
{services, equipment, problems, methods}` — our SIE stub has `entities: []`.
Relax to: lede must include ≥1 high-relevance supporting keyword. (b) **Term
zone targets** (§5.8.3) expect per-zone `usage_recommendations` from SIE — we
have none. Provide a flat default per required term (paragraphs target 1, max
3; no h2/h3 targets) so injection is "mention each supporting keyword
naturally, don't stuff." Both logged as degraded-mode adaptations.

---

## 2. Degraded-mode contract (what runs / what's bypassed)

| PRD step | M12 behavior |
|---|---|
| 0 Input validation + cross-validation | **Runs.** Keyword equality is trivial (adapter builds all inputs from one cluster). FAQs 3–5 enforced at adapter level. |
| 1 Title generation (3 candidates, Haiku) | **Runs** — but `output.title` ≈ `brief.title` source differs; see note below. Topic anchor = embed(title). |
| 2 H1 verbatim + enrichment lede | **Runs.** H1 = `brief.title` verbatim (D6). Lede entity rule relaxed (Δ4a). |
| 2.5 Intro (Agree/Promise/Preview) | **Runs.** Agree beat infers from title topic (no `icp_text`) — documented fallback. |
| 3 Word budget allocation | **Runs** (pure). 2,500 default; conclusion 100–150; per-group split. |
| 3.5a / 3.5b Brand distillation / reconciliation | **Bypassed** (no `client_context`). All SIE terms treated `keep`; empty `brand_conflict_log`. |
| 3.6 Brand & ICP placement plan | **Bypassed** (§5.7: no card → directives not stamped). |
| 3.7 Topic-adherence filter | **Runs** (pure + embeddings). Drop H2 below 0.62 cosine to title; log `dropped_for_low_topic_adherence`. Spin-off payload: logged only (no brief `discarded_headings` to route to). |
| 4 Section writing (sequential, Sonnet) | **Runs.** 4A answer-first, 4B intent patterns, 4C term injection (flat defaults, Δ4b), 4D lists/tables, 4E.1 paragraph directive. |
| 4F citation markers | **Skipped** (no pool). No `{{cit_N}}` anywhere. |
| 4F.1 / §5.8.8 coverage | **Detection + rewrite-retry + soften, no markers** (Δ3, flagged §8). |
| 5 FAQ writing | **Runs** (Sonnet; questions from adapter; 40–80-word answer-first answers; AEO rules). |
| 6 Conclusion | **Runs** (100–150 words, seed keyword present, no CTA inside). |
| 6.4 CTA | **Runs** (Haiku). No `icp_text` → intent-template table (§5.11). Hard-sales regex enforced. |
| 6.5 Key Takeaways | **Runs** (Sonnet; 3–5 × ≤25 words; 0.85 pair-cosine check; rendered second, generated last). |
| 6.6 Paragraph-length validation | **Runs** (pure; 4-sentence cap; retry-once-then-flag). |
| 6.7 Per-H2 body-length floor | **Runs** (pure check + retry; floors from the intent `h2_pattern` table: 120/80/150/180/180/150/150/100). |
| 6.8 ICP callout judge | **Bypassed** (`icp_callout_judge_status: "not_assigned"`). |
| 7 Citation reconciliation | **Trivial** (`citation_usage` all-empty; `no_citations: true`). |
| 8 Banned-term scan | **No-op** (empty list → `banned_regex = None`, §5.17.1). |
| 9 Title-case pass | **Runs** (`titlecase==2.4.1`, idempotent). |
| 10 MD + HTML serialization | **Runs** (pure). No markers → no footnotes/`<sup>`; no Sources section. |

Output `client_context_summary.schema_version_effective = "1.7-no-context"`,
`metadata.no_citations = true`. Required structural elements (D7: takeaways /
intro / CTA) keep their **abort** semantics — partial output is worse than none.
End-to-end timeout 90s → abort `generation_timeout` (§7).

**Title note:** the Writer's Step 1 generates `output.title` while H1 comes
verbatim from `brief.title`. Since *our* `brief.title` is itself adapter-
generated (Δ2), running Step 1 again would produce a second, competing title.
**M12 collapses them: `output.title = brief.title`; Step 1 is reduced to
embedding the title for the topic anchor.** Saves one call; removes drift
between H1 and topic anchor. Flagged (§8) since it's a structural deviation.

## 3. Adapter spec — `backend/app/writer/adapter.py`

`build_writer_payload(cluster, session, settings) → (brief, sie)`. Pure
assembly over **four cached LLM calls** (all results stored on
`clusters.adapter_cache` jsonb; re-generate reuses the cache → ~$0 amortized):

| # | Call | Model | Contract |
|---|---|---|---|
| A1 | Intent classification | Haiku 4.5, tool-use | `clusters.intent` text + primary/supporting keywords → one of the 8 `intent_type` enums. |
| A2 | Title + scope | Sonnet 4.6, tool-use | Brief Gen Step 3.5 contract (Δ2): title 50–80 chars containing the seed keyword; scope ≤500 chars with "does not cover" clause; rationale. Grounded in cluster keywords (no SERP inputs). |
| A3 | Heading structure | Sonnet 4.6, tool-use | Δ1. Inputs: title, scope, the intent's `intent_format_template` row (pattern / framing rule / ordering / anchor slots / min–max H2), supporting keywords. Output: ordered H2 list (H2-only v1), respecting framing rule + anchor slots. Adapter appends `faq-header` + N `faq-question` rows + `conclusion` row. |
| A4 | FAQs | Sonnet 4.6, tool-use | 3–5 `{question, faq_score}`. Questions from real keyword phrasings (the cluster's question-form keywords first). |

Static (no LLM): `format_directives` from the intent registry (incl.
`min_h2_body_words` per the floor table); `metadata.word_budget = 2500`;
`sie.terms.required[]` = supporting keywords (flat, sorted by gate
`relevance_score`; no `is_entity` → C6 never fires, fine per §19.4);
`sie.target_keyword.minimum_usage = {h2: 1, h3: 0, paragraphs: 6}`;
`sie.terms.avoid = []`; `sie.word_count.target = 2500` (avoids
`word_count_conflict`); flat per-term zone defaults (Δ4b).

The `intent_format_template` registry + `min_h2_body_words` floors + CTA
templates are transcribed **verbatim from the bundle** into
`backend/app/writer/templates.py` as module constants.

## 4. Module layout — `backend/app/writer/`

```
writer/
  models.py      # pydantic: Brief, SieStub, ArticleItem, WriterOutput, error envelope (§19.6)
  templates.py   # intent_format_template registry, H2-body floors, CTA templates, soften table
  adapter.py     # build_writer_payload + the 4 cached calls (A1–A4)
  pipeline.py    # the step runner (sequential; §2 table above); 90s budget
  validators.py  # citable-claim C1–C9 + auto-soften; paragraph splitter (+abbrev dict);
                 # intro/CTA/takeaways validators; title-case pass
  serialize.py   # article[] → article_markdown / article_html (pure, §5.19)
```

- LLM calls go through `llm/anthropic_client.py`, **extended to take a model
  param** (it's currently Opus-pinned for the M5 orchestrator) — forced
  tool-use for JSON calls per §17, plain text for prose. Max-tokens/temperature
  per the §17 table.
- Embeddings reuse `llm/openai_client.py::embed` (batched: title anchor + H2
  embeddings + takeaways in ≤2 calls, per §15 guidance).
- Every external call already flows through the M11 `CostMeter`; jobs wrap in
  `metered_run(session_id, "article_generation")` — the new phase §9.6 names.
- Structured logging adopts the PRD's `writer.*` event names (§19.7) on top of
  this repo's §16.3 log shape (`session_id`/`correlation_id` instead of their
  `run_id`/`request_id`).
- New dep: `titlecase==2.4.1` (pinned, matches the Brief Gen). No other deps.

## 5. Schema — migration `2026XXXX_writer_foundation.sql` (M12-owned only)

```sql
alter table fanout.clusters add column adapter_cache jsonb;

create table fanout.article_outputs (
  id                       uuid primary key default gen_random_uuid(),
  cluster_id               uuid not null references fanout.clusters(id) on delete cascade,
  session_id               uuid not null references fanout.sessions(id) on delete cascade,
  article_json             jsonb not null,          -- full §6 output object
  article_markdown         text not null,
  article_html             text not null,
  total_word_count         int,
  cost_usd                 numeric(10,4),
  schema_version_effective text not null,           -- "1.7-no-context"
  generated_at             timestamptz not null default now()
);
create index on fanout.article_outputs (cluster_id, generated_at desc);
```

Real RLS: owner all; VA via the `sessions`-join (mirrors keywords /
site_architecture / csv_exports policies). Never `using (true)`.

**Deferred to M13** (vs. the §9.3 sketch): `clusters.slug` + its unique index
(link injection), `sessions.site_base_url` (schedule modal),
`content_schedules` / `scheduled_article_runs` (+ the
`article_outputs.scheduled_article_run_id` FK, added when its target exists).
Per CLAUDE.md: each milestone owns its schema additions; none of these are
consumed by M12 code. Apply to prod via Supabase MCP **as part of the deploy**
(the standing lesson).

## 6. API + frontend (M12 slice)

- `POST /sessions/{id}/clusters/{cluster_id}/generate-article` —
  **require_owner** (per §9.10; VA access arrives with M13's gated scheduling).
  Async per the house pattern: 202 + background job (`run_article_job`,
  `@_metered("article_generation")`, `raise_if_cancelled` between steps);
  per-cluster claim guard (409 if that cluster is already generating).
- `GET /clusters/{cluster_id}/article` — latest `article_outputs` row
  (RLS-scoped read; both roles).
- Frontend: **`Generate now`** button per supporting article on the
  Architecture view (owner-only), plus a minimal article readout
  (`/session/:id/article/:cluster_id`: rendered Markdown + word count + cost +
  `Regenerate`). The fuller article view + schedule overview are M13 (§9.7).

## 7. Tests (sandbox-runnable, mocked LLM)

The PRD's §14 fixture table maps directly; everything below is deterministic
or mockable, no egress:

- **F-A** (no client_context → `"1.7-no-context"`) — the production path.
- **F-J/F-K** adherence filter keep/drop (synthetic embeddings).
- **F-L** H2-length floor retry → success / `under_length_h2_sections`.
- **F-M/F-N/F-O** soften: C7 duration / C9 "5% rule" softened; C1 "18% in Q3"
  NOT softened, flagged. (Pure-regex tests of `validators.py`.)
- **F-Q** intro 4-paragraph response → retry → deterministic collapse.
- **F-R** CTA "Buy now" → hard-sales regex retry/sanitize.
- **F-S/F-T** takeaways 6 → truncate to 5; 2 → abort `key_takeaways_count_invalid`.
- **F-U** serialization round-trip (MD/HTML recover plain-text body; no
  markers in degraded mode).
- Adapter: cache hit/miss; FAQ-count 3–5 enforcement; heading-structure
  min/max + framing-rule shape; keyword cross-validation trivially passes.
- Budget allocator: group math, authority-gap weights (present but unused in
  v1 — no `authority_gap_sme` H3s), 50-word floor.

## 8. Flagged decisions for owner sign-off

1. **Δ3 — keep citable-claim detection in no-citations mode** (rewrite-retry +
   soften as an anti-fabrication guard) vs. the §9.1 sketch's "skip §5.8.8
   entirely". Recommended: keep (config flag `writer_claim_coverage_enabled`,
   default on). Diverges from the locked §9.1 wording, so flagging.
2. **Title collapse** (`output.title = brief.title`; Writer Step 1 reduced to
   anchor embedding) — see §2 note. Recommended; structural deviation from PRD §5.1.
3. **Pillar generation is out of M12.** `Generate now` covers supporting
   articles (clusters) only. Pillars need a different adapter path (silo-level
   brief; the writer owns pillar title/summary per the 2026-06-09 decision) and
   are required by M13's pillars-first drip anyway — build the pillar path in
   M13. Consequence: through M12, pillar editorial stays placeholder.
4. **H2-only heading structure** in v1 (no H3s — no SERP/authority-gap source).
   Budget math + validators still handle H3s (code ported intact) so M14+ can
   add them without rework.
5. **Δ4 relaxations** (lede entity rule → top supporting keyword; flat term
   zone defaults) — degraded-mode adaptations the PRD doesn't define.
6. **Tier-2 sample outputs still unfetched** (real `module_outputs` rows from
   AR-Internal-Tools). Not blocking; fetch if the documented `article_json`
   schema proves ambiguous during the port ("ground truth wins" per §9.13).

## 9. Out of scope (M13, per §9.10)

Scheduling (`content_schedules` / `scheduled_article_runs` / asyncio worker /
`Schedule all` modal / $90 VA approval gate), `link_injector` + slugs +
`site_base_url`, pillar generation, article/schedule UI surfaces beyond the
minimal readout, app-shell badge. M14 (optional): brand voice + citations
(the bundle's full-context path — the schema fields are already carried).
