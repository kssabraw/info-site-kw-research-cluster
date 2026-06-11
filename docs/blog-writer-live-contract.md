# Blog Writer — live contract (recovered from production)

**Status: ground-truth reference, captured 2026-06-11.** Pulled directly from the
AR-Internal-Tools Supabase (`wvcthtmmcmhkybcesirb`, `public` schema) via MCP, NOT
from the PRD bundle. This is the `handoff.md` §9.13 **Tier-2 item #5** ("3–5 sample
Writer outputs … ground truth — they win over the documented schemas if the two
disagree"), partially obtained: we have the **I/O contract + observable behaviors**,
but **not** the internal prompts / step logic (still the Tier-1 blocker — those live
in the writer service's source, not the DB).

M12 build is **on hold** until the verbatim Writer PRD v1.7 + Engineering Spec
arrive (owner's out-of-band fetch). This doc de-risks the wait and corrects the
plan; it does not authorize building yet.

---

## The run pipeline (5 modules, fixed status chain)

A `public.runs` row (59 in prod) flows through:

```
queued → brief_running → sie_running → research_running → writer_running
       → sources_cited_running → complete   (also: failed, cancelled)
```

Run input is minimal: `keyword`, `intent_override`, `sie_outlier_mode`
(safe/aggressive), `sie_force_refresh`, `brief_force_refresh`, `client_id`. Each
module writes one `public.module_outputs` row (`module`, `status`,
`input_payload`, `output_payload`, `cost_usd`, `duration_ms`, `module_version`,
`attempt_number`). Per-run total in `runs.total_cost_usd`; frozen client context in
`client_context_snapshots`.

**Production module versions / health (2026-06-11):**

| Module | Version | Complete / Failed | Avg latency |
|---|---|---|---|
| brief | **2.6** | 42 / 12 | ~98s |
| sie | 1.4 | 42 / 14 | ~48s |
| research | 1.1 | 39 / — | ~93s |
| **writer** | **1.7** | **35 / 4** | **~187s** |
| sources_cited | 1.1 | 35 / — | <1s |

Writer is **v1.7** (matches the plan's target). `cost_usd` is null per-module
(cost is tracked at run level only).

---

## Writer module I/O contract (verified keys)

**Input** (`input_payload`) — the writer is purely a consumer of the upstream four
modules; it makes no external research calls itself:

- `brief_output` (object) — keys: `keyword`, `h1`, `title`, `title_rationale`,
  `scope_statement`, `intent_type`, `intent_confidence`, `intent_review_required`,
  `intent_format_template`, `format_directives`, `heading_structure` (array),
  `faqs`, `persona`, `structural_constants`, `silo_candidates`, `discarded_headings`,
  `editorial_critique`, `customer_review_insights`, `reddit_insights`,
  `llm_disagreement`, `metadata`.
- `sie_output` (object) — keys: `keyword`, `target_keyword`, `terms`,
  `term_signals`, `usage_recommendations`, `zone_category_targets`,
  `word_count_target`, `serp_summary`, `outlier_mode`, `location_code`,
  `language_code`, `schema_version`, `warnings`, cache fields.
- `research_output` (object) — keys: `citations`, `citations_metadata`,
  `supporting_stats`, `enriched_brief`.
- `client_context` (object) — brand guide / ICP / website analysis.
- `run_id`, `attempt`.

**Output** (`output_payload`):

- `article` — **ordered ARRAY of section blocks** (21 in the sample). Each block:
  `{ order, level (H1/H2/H3/none), heading, type, body (Markdown), word_count,
  section_budget, citations_referenced }`. `type` ∈ {`key-takeaways`, `content`,
  `faq`, …}. Bodies are **Markdown** (e.g. `- ` bullets). Serialization to MD/HTML
  is built from this array.
- `title`, `keyword`, `intent_type`.
- `metadata` — see below.
- `format_compliance`, `term_usage_by_zone`, `citation_usage`,
  `brand_voice_card_used`, `brand_conflict_log`, `client_context_summary`.

### `metadata` (real sample) — the writer's enforced invariants

```
word_budget 2500 · total_word_count 2973 · budget_utilization_pct 118.9
word_count_conflict true · section_count 11 · faq_count 5 · faq_word_count 313
schema_version "1.7" · brief_schema_version "2.6"
citations_used 4 · citations_unused 0 · no_citations false
under_cited_sections [{section_order 8, cited_claims 0, citable_claims 1,
                       threshold 0.5, ratio 0}]
icp_anchor_h2_text "…" · icp_anchor_h2_order 2 · icp_callout_judge_status "no_anchor"
icp_callout_landed null · icp_hook_phrase null
brand_anchor_h2_text "…" · brand_anchor_h2_order 5 · brand_mention_landed false
h2_body_length_retries_attempted/succeeded 0/0
citation_coverage_retries_attempted/succeeded 0/0 · retry_count 0
banned_terms_leaked_in_body [] · operational_claims_softened []
faq_like_h2_content_dropped [] · duplicate_h2_headings_dropped []
h3_children_dropped_under_h2 [] · under_length_h2_sections []
```

These confirm the §9.1 "invariants we keep": topic adherence, per-H2 body floor +
retries, citation-coverage retries, paragraph cap, banned-term filter, key
takeaways, FAQ section. The ICP/brand/citation fields are the degraded-mode levers
(empty/`no_anchor`/`landed:false` when `1.7-no-context` + `no_citations`).

### `brief_output.format_directives` (real sample)

```
require_tables true · min_tables_per_article 1 · min_lists_per_article 2
require_bulleted_lists true · min_h2_body_words 180
answer_first_paragraphs true · preferred_paragraph_max_words 80
```

This is exactly the lookup the §9.2 adapter must populate. NOTE: the brief output
also carries an `intent_format_template` key directly — we may be able to **copy**
v2.6's template from a real brief rather than re-deriving the §9.2 static table.

### `brief_output.heading_structure[0]` (real sample — it's heavy)

```
{ text, type "content", level "H1", order 1, exempt false, source "serp",
  serp_frequency, avg_serp_position, information_gain_score, title_relevance,
  parent_relevance, heading_priority, scope_classification, scope_alignment_note,
  parent_fit_classification, llm_fanout_consensus, region_id, parent_h2_text,
  original_source }
```

Most fields are SERP-derived scoring metadata the adapter can leave null/0; the
load-bearing ones for the writer are `text`/`type`/`level`/`order`/`parent_h2_text`.

---

## Degraded-mode mapping (§9.1 plan, now contract-verified)

Per article, M12 would:
- **Feed** a synthesized `brief_output` (from the cluster), a `sie_output` stub
  (supporting keywords as flat `terms`), an **empty** `research_output`
  (`no_citations: true`), an **omitted** `client_context`.
- **Get** the `article` section array → deterministic link-injector → serialize →
  `fanout.article_outputs`.
- Brand/ICP/citation metadata return empty — intended degraded behavior, confirmed
  against real `metadata`.

---

## Corrections to handoff §9 (from this probe)

1. Real schema names: `module` / `input_payload` / `output_payload` (NOT
   `module_name` / `output_json` — §9.13's SQL sketch would error).
2. **Brief module is v2.6**, not the v2.3 the §9.2 adapter cites. Re-pull
   `format_directives` / `intent_format_template` from a v2.6 brief.
3. Writer `article` is a **section array**, not a single HTML blob — bodies are
   Markdown. The adapter/injector operate on sections.

## Still missing (Tier-1, blocks faithful port)

- Verbatim Writer PRD v1.7: ordered step list (1→10), section-call prompts, §17
  Call Inventory (which step → Sonnet vs Haiku, max-tokens, retries), exact
  `1.7-no-context` + `no_citations` behavior, topic-adherence mechanic/threshold,
  Agree/Promise/Preview + CTA templates, paragraph cap + per-H2 floor numerics.
- Engineering Spec PRD (JSON Schemas + module contracts).
- Production Anthropic model IDs (in the writer service config, not the DB).

## Security (re-confirmed, unchanged — `handoff.md` §8.7)

`public.sie_cache` has **RLS disabled** (Supabase advisor flags it critical). Fix =
`ALTER TABLE public.sie_cache ENABLE ROW LEVEL SECURITY;` but **do not run blind** —
no policy ⇒ the writer service's reads break. Add a service-role policy + clear with
the AR-Internal-Tools owner first.
