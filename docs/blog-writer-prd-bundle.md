# Blog Writer Pipeline — Complete PRD Bundle

This document concatenates all eight specifications needed to build the AR Tools Blog Writer pipeline end to end. Each section is one standalone PRD, separated by a horizontal rule.

## Table of Contents

1. **Content Writer Module** (consolidated, v1.7) — the main module spec, with §§16–20 covering LLM call inventory, prompt scaffolds, closures, and a full golden example.
2. **Content Brief Generator** (v2.3) — upstream Input A producer.
3. **SIE Term & Entity Module** — upstream Input C producer.
4. **Research & Citations Module** (v1.1.1) — upstream Input B producer.
5. **Sources Cited Module** (v1.1) — downstream citation renderer.
6. **Content Quality PRD** (v1.0) — cross-cutting R1–R7 requirements.
7. **Suite Architecture & Roadmap** (v1.0) — locked decision log.
8. **Engineering Implementation Spec** (v1.1) — service topology, Supabase schema, infrastructure.

Read in the order above. The Writer PRD (#1) is the build target; #2–#5 define what flows into and out of it; #6–#8 cover the cross-cutting and infrastructure substrate.

---



<!-- ============================================================ -->
<!-- SOURCE FILE: docs/modules/content-writer-module-consolidated-prd.md -->
<!-- ============================================================ -->

# PRD: Content Writer Module (Consolidated, Self-Contained)

**Canonical Version:** 1.7 (with v1.5 brand-context and v1.6 structural additions merged inline)
**Status:** Implementation-ready
**Locale:** English / United States only
**Pipeline Role:** Final generation module in the Blog Writer pipeline. Consumes Brief, Research & Citations, SIE, and Client Context. Produces a publication-ready Markdown article plus a structured JSON article object for the downstream Sources Cited module.

> This document is a self-contained build spec. A reader with no prior context should be able to implement the module from this PRD alone. It consolidates: v1.3 baseline + v1.4 citation marker contract + v1.5 brand-voice/client-context handling + v1.6 H1 sourcing, intro structure, title-case pass, multi-format serialization + v1.7 citable-claim coverage with operational-claim softening. Where a feature was introduced in a specific version, the version is noted; the rule itself is current.

---

## 1. Problem & Scope

### 1.1 Problem

The upstream pipeline (Brief Generator + SIE + Research & Citations) produces a fully researched, structured plan for a blog post — heading architecture, FAQ questions, required terms, entity recommendations, format directives, and a set of verified, source-anchored claims mapped to every content section. That plan has no value until it becomes actual prose. Manual execution drifts from the approved heading structure, ignores term targets, violates word budgets, buries answers under preamble, and introduces fabricated statistics.

The Content Writer converts the upstream brief, term intelligence, verified citation pool, and per-client brand voice into a complete, publication-ready blog post that is optimized for both Google search ranking and LLM citation (Answer Engine Optimization / AEO). Citations do the sourcing work so the writer does not invent statistics.

### 1.2 Goals

- Accept four structured inputs (Brief, Research, SIE, Client Context) and produce a complete article.
- Generate a title; emit H1 verbatim from the brief; write every content section from the brief's heading structure.
- Honor word budget, format directives, heading hierarchy, and term usage targets from upstream — the writer does not reinterpret the brief.
- Produce content structured for LLM citation: answer-first paragraphs, direct question answers, clean section boundaries, schema-compatible FAQ.
- Ground factual assertions in verified claims from Research; treat fallback-stub claims as source references only.
- Track per-citation usage and emit a structured article (`article[]`), plus Markdown and HTML serializations for downstream publishing.
- Enforce per-client brand voice (tone, voice directives, banned terms, preferred terms) over SIE recommendations; brand always wins.
- Enforce content-quality guardrails: topic adherence, paragraph length cap, citable-claim coverage, structural elements (Key Takeaways / Agree-Promise-Preview intro / CTA), brand-mention budget.

### 1.3 Out of Scope (v1)

- Keyword research / brief generation (upstream — see §1.4)
- Internal linking suggestions
- Image selection / alt-text generation
- Meta description generation
- Schema markup injection (JSON-LD)
- CMS publishing or API push (Sources Cited + platform Publish module handle delivery — see §1.4)
- Multi-locale support
- Rank tracking, citation link-rot monitoring
- Human review workflows / editorial routing
- Rewriting prior runs — each run is independent

### 1.4 Pipeline Position & Sibling Modules

The Writer is one of five generation modules in the Blog Writer pipeline. All five are **sibling Python modules in the same private pipeline-api service**, invoked sequentially by the platform-api orchestrator (which validates each module's returned `schema_version` against an `EXPECTED_MODULE_VERSIONS` map and persists outputs to the platform database). The Writer does not call upstream or downstream modules directly — the orchestrator does.

```
Brief Generator                  ← upstream (Input A)
        │  emits: title, scope_statement, heading_structure[] with
        │         per-heading citation_ids, FAQs, format_directives,
        │         intent_format_template, word_budget
        ▼
SIE Term & Entity Module         ← upstream (Input C)
        │  emits: required/avoid terms, per-zone usage recommendations,
        │         target keyword floors, entities with categories
        ▼
Research & Citations Module      ← upstream (Input B)
        │  emits: verified citation pool with claims, relevance scores,
        │         extraction_method flags, mapped to brief headings
        ▼
[Client Context from platform-api]   ← upstream (Input D)
        │  emits: brand_guide_text, icp_text, website_analysis
        ▼
┌───────────────────────────────┐
│        Content Writer         │  ← THIS MODULE
│   (modules/writer/)           │     emits: article[] with {{cit_N}}
└───────────────┬───────────────┘            markers + article_markdown
                │                            + article_html + metadata
                ▼
Sources Cited Module             ← downstream
        │  consumes Writer output + Research output
        │  resolves {{cit_N}} markers → numbered <sup><a> superscripts,
        │  builds MLA-style "## Sources Cited" section, applies
        │  rel="nofollow" to external URLs
        ▼
Content Editor / Platform Publish module (Google Doc via Apps Script webhook)
```

#### 1.4.1 Upstream: Brief Generator

The article outline does NOT come from this module. It comes from the **Content Brief Generator** (sibling module at `modules/brief/`, PRD `docs/modules/content-brief-generator-prd-v2_0.md`, canonical version 2.3). The Writer does not reinterpret the brief — it executes it. Every field the Writer consumes as Input A (§2.1) is produced by the brief generator's pipeline:

| Brief generator step | Produces field used by Writer |
|---|---|
| Step 3 — Title + scope statement generation | `brief.title` (H1 verbatim — §5.2), `brief.scope_statement` (intro Promise anchor — §5.3) |
| Step 3 — `intent_format_template` | `format_directives.min_h2_body_words` floors (§5.10 H2 body length validator), `h2_pattern` family |
| Steps 4–6 — Coverage graph + MMR scoring | `heading_structure[]` with H2 embeddings used by §5.4.2 topic-adherence filter |
| Step 7.5 — Anchor-slot reservation | Template-required H2 slots (e.g., comparison's parallel evaluative axes) |
| Step 8.5 — Scope verification | Out-of-scope H2s already discarded before Writer sees the brief |
| Steps 8.6 + 8.7 — H3 selection + parent-fit verification | H3 attachment with the 0.65 cosine floor |
| Step 9 — Authority gap H3s | `heading_structure[].source: "authority_gap_sme"` (triggers §5.4.1 1.2× budget multiplier and §5.8.5 substantive register bar) |
| Step 10 + 10.5 — FAQ generation + intent gate | `faqs[]` (3–5 questions consumed by §5.9) |
| Step 11 — Heading framing + title-case normalization | Pre-normalized H2/H3 text. The Writer's defense-in-depth title-case pass (§5.18) uses the same pinned `titlecase==2.4.1` library, so the round-trip is a no-op for already-cased input. |
| Step 12 — Silo identification | H2s the Writer drops via §5.4.2 topic-adherence filter are forwarded back to this routing for future-brief seeding |

The Writer enforces a strict `brief_schema_version` floor of `2.0+` because the H1-from-brief contract (§5.2.1) requires `brief.title`, which was introduced in Brief PRD v2.0 Step 3.

#### 1.4.2 Downstream: Sources Cited Module

The Writer does NOT produce final reader-facing citations. It produces **citation marker tokens** (`{{cit_N}}`) in `article[].body`. The **Sources Cited module** (sibling at `modules/sources_cited/`, PRD `docs/modules/sources-cited-module-prd-v1_1.md`, canonical version 1.1) consumes Writer output and renders the final form.

What Sources Cited does that the Writer deliberately does not:

| Sources Cited step | Action |
|---|---|
| 1 — Marker discovery | Scans every `article[].body` for `{{cit_N}}` tokens (regex `\{\{cit_[0-9]+\}\}`) in document order |
| 2 — Number assignment | Assigns sequential numbers `[1]`, `[2]`, `[3]`… by **order of first appearance**. The Writer's citation *ids* (`cit_001`, `cit_007`) are NOT the user-facing numbers; the numbers are assigned here. |
| 3 — Superscript substitution | Replaces `{{cit_N}}` with `<sup><a href="#cite-1">1</a></sup>` jumplinks. Stacked markers in one sentence sort ascending. |
| 4 — `used: true` filtering | Only citations the Writer marked as placed in prose (via `citation_usage.usage[]`) appear in the bibliography |
| 5 — MLA-derived rendering | Builds the `## Sources Cited` section appended to the article. v1 format: `Title. Publication. URL.` (author/date deferred to v2 because the Research module's author/published_date fields are not yet reliable enough) |
| 6 — `rel="nofollow"` | Applied to every external URL in the bibliography |

The handoff contract:

- **Writer produces** `{{cit_N}}` plain-text tokens inside Markdown `body` fields, placed immediately after the closing punctuation of the cited sentence. Marker ids match regex `^cit_[0-9]+$`. Markers are forbidden in headings — match in any heading → abort `marker_in_heading` (§5.8.7 / D9).
- **Writer does NOT produce** inline Markdown hyperlinks (`[anchor text](url)`) in prose; numbered citation references; a `## Sources Cited` bibliography; `rel="nofollow"` decoration. All of these are downstream.
- **Writer DOES produce** the flat `article_markdown` (`[^N]` GitHub-footnote form) and `article_html` (`<sup><a href="#cite-N">` form) serializations as an *additional* convenience for consumers that bypass Sources Cited entirely (e.g., the platform Publish module's Google Docs / WordPress paste flow). When the Sources Cited module runs, its numbered MLA-rendered output is the canonical form that goes to the Content Editor and Publish modules next.
- **Schema floor:** Sources Cited rejects Writer output below `schema_version` 1.4 because the `{{cit_N}}` marker contract did not exist before that version.

---

## 2. Inputs

Four upstream JSON payloads on each run. All required except `client_context`, which is optional with documented fallbacks.

### 2.1 Input A — Brief Generator output

Authoritative source for heading structure, word budget, format directives, FAQs, and (since Brief v2.0) the article title.

| Field | Usage |
|---|---|
| `keyword` | Seed keyword. Cross-validated against Research and SIE; mismatch aborts run. |
| `title` | **H1 text — used verbatim. No LLM regeneration.** (Added Brief v2.0 / Writer v1.6.) |
| `intent_type` | One of: `informational`, `listicle`, `how-to`, `comparison`, `ecom`, `local-seo`, `news`, `informational-commercial`. Governs tone, section patterns, CTA template. |
| `scope_statement` | Constrains the article's promise (used in intro construction). |
| `heading_structure[]` | Ordered list of `{order, level: "H1"\|"H2"\|"H3", text, type, source?, citation_ids[]?, embedding?}`. Writer emits these in order. |
| `heading_structure[].type` | `content`, `faq-header`, `faq-question`, `conclusion`. |
| `heading_structure[].source` | Optional. `authority_gap_sme` H3s get a budget multiplier and stricter quality bar. |
| `heading_structure[].citation_ids` | Citation ids mapped to each heading. |
| `faqs[]` | Ordered FAQ `{question, faq_score}`. Count must be 3–5. |
| `format_directives` | `require_bulleted_lists`, `require_tables`, `min_lists_per_article` (default 1), `min_tables_per_article` (default 1), `answer_first_paragraphs` (default true), `max_sentences_per_paragraph` (default 4), `min_h2_body_words` (intent-specific floor — see §5.10). |
| `metadata.word_budget` | 2,500 words across content sections; FAQ excluded. |
| `metadata.h2_count`, `metadata.h3_count` | Budget-per-section math. |

### 2.2 Input B — Research & Citations output

Verified citation pool mapped to brief headings.

| Field | Usage |
|---|---|
| `keyword` | Cross-validated against brief. Mismatch aborts. |
| `citations[]` | Verified citations. |
| `citations[].citation_id` | Must match regex `^cit_[0-9]+$`. Used in `{{cit_N}}` markers placed in prose. |
| `citations[].claims[]` | `{claim_text, relevance_score, extraction_method, verification_method}`. |
| `citations[].extraction_method` | `verbatim_extraction` or `fallback_stub`. **Stubs may not be used for specific factual assertions** — only as source-attribution context. |
| `citations[].url`, `.title`, `.author`, `.publication`, `.published_date` | **Not consumed by Writer**; passed through to downstream Sources Cited module. |

`research.citations` absent or empty → continue in degraded mode (`no_citations: true`); sections written without citation grounding. Not an abort.

### 2.3 Input C — SIE Term & Entity output

| Field | Usage |
|---|---|
| `keyword` | Cross-validated against brief. Mismatch aborts. |
| `terms.required[]` | Terms the writer must incorporate. |
| `usage_recommendations[]` | Per-zone usage ranges (min/target/max) per term. Writer targets `target`, hard-caps at `max`. |
| `target_keyword.minimum_usage` | Per-zone occurrence floors for the seed keyword. |
| `terms.avoid[]` | Terms the writer must not use (hard block; subject to brand-override — see §4.2). |
| `word_count.target` | Cross-validated against `brief.metadata.word_budget`; >20% divergence flags `word_count_conflict`. Brief wins. |
| `entities[]` (merged into `terms`) | `entity_category`, `example_context`, `ner_variants` — used to enrich the H1 lede and high-value sections. |

### 2.4 Input D — Client Context (optional; per-client brand voice)

Added in v1.5. Omitted → fall back to v1.4 behavior; `schema_version_effective: "1.6-no-context"`.

```json
{
  "client_context": {
    "brand_guide_text": "string (max 150,000 chars; JSON, Markdown, or extracted text from PDF/DOCX)",
    "icp_text":         "string (max 150,000 chars; same format rules)",
    "website_analysis": {
      "services":   ["string"],
      "locations":  ["string"],
      "tone":       ["string (3–5 adjectives — NOT used; see below)"],
      "positioning":"string (≤50 words — NOT used; see below)"
    },
    "website_analysis_unavailable": false
  }
}
```

**Website analysis provides factual reference data ONLY** (services, locations, contact info). Tone and positioning signals come exclusively from `brand_guide_text` and `icp_text`. The `website_analysis.tone` and `.positioning` fields are accepted on the wire for forward compatibility but ignored by distillation.

### 2.5 Cross-validation (runs before any LLM call)

| Check | On failure |
|---|---|
| `brief.keyword == research.keyword` (case-insensitive) | Abort `keyword_mismatch` |
| `brief.keyword == sie.keyword` (case-insensitive) | Abort `keyword_mismatch` |
| `sie.word_count.target` within ±20% of `brief.metadata.word_budget` | Flag `word_count_conflict: true`; proceed using brief as authoritative |
| `brief.heading_structure` non-empty and ordered | Abort if empty; warn on `order` gaps |
| `brief.faqs` count 3–5 | Abort outside range |
| `research.citations` missing/empty | Continue; log `no_citations: true` |
| `brief.title` present and non-empty | Abort `brief_missing_title` if missing (legacy fallback path exists — see §5.2.4) |
| `client_context` present but malformed | Abort `client_context_validation_error` |

---

## 3. System Architecture

```
[Brief + Research + SIE + Client Context]
        │
        ▼
  Step 0: Input Validation + Cross-Validation
        │
        ▼
  Step 1: Title Generation  ───►  embed(title) = topic anchor
        │
        ▼
  Step 2: H1 (verbatim from brief.title) + Enrichment Lede
        │
        ▼
  Step 2.5: Intro Construction (Agree / Promise / Preview)
        │
        ▼
  Step 3: Word Budget Allocation
        │
  Step 3.5a: Brand Voice Distillation   ┐
  Step 3.5b: Brand–SIE Reconciliation   ┘  (run in parallel)
        │
        ▼
  Step 3.6: Brand & ICP Placement Plan (deterministic anchors)
        │
        ▼
  Step 3.7: Topic-Adherence Filter (drop H2s with cosine < 0.62 to title)
        │
        ▼
  Step 4: Section Writing (sequential per H2 group)
          ├── 4A Answer-first paragraphs
          ├── 4B Intent-specific patterns
          ├── 4C Term injection (filtered SIE + target keyword floors)
          ├── 4D Format directives (lists, tables)
          ├── 4E H3 sub-section writing (incl. authority-gap H3s)
          ├── 4E.1 Paragraph-length directive
          ├── 4F Citation marker placement
          └── 4F.1 Citable-claim coverage validator (per-section, post-write)
        │
        ▼
  Step 5: FAQ Section Writing
        │
        ▼
  Step 6: Conclusion Writing
  Step 6.4: CTA (separate structural element after conclusion)
  Step 6.5: Key Takeaways (generated last, rendered second)
  Step 6.6: Paragraph-length post-validation
  Step 6.7: Per-H2 body length validation
  Step 6.8: ICP Callout LLM judge
        │
        ▼
  Step 7: Citation Usage Reconciliation
        │
        ▼
  Step 8: Banned-Term Regex Scan
  Step 9: Defense-in-Depth Title-Case Pass on headings
  Step 10: Markdown + HTML Serialization
        │
        ▼
  [JSON output: article[] + article_markdown + article_html + metadata]
```

---

## 4. Locked Design Decisions

These are settled — do not relitigate without explicit user approval.

| # | Decision | Rationale |
|---|---|---|
| D1 | Brand voice card is regenerated per run from current `client_context_snapshots`. Not cached on the client record. Persisted in run output as `brand_voice_card_used`. | No cache invalidation when brand guides change; past runs reflect the snapshot at run time. |
| D2 | Banned-term detection in generated output is regex-based: case-insensitive, word-boundary, alternation over `brand_voice_card.banned_terms`. | Deterministic, cheap, debuggable. LLM-based paraphrase detection is a future-version candidate. |
| D3 | **Brand always wins** in all term conflicts. Brand-banned > SIE-Required (term excluded). Brand-preferred > SIE-Avoid (term used). No exceptions. | Brand compliance is non-negotiable; SIE is SERP-derived intelligence, not a client mandate. |
| D4 | Brand guide / ICP accepted as JSON, Markdown, or extracted text. Distillation LLM handles all formats natively. | Preserve structure when present; do not flatten unnecessarily. |
| D5 | Website analysis is factual reference only (services, locations, contact info). Tone and positioning come exclusively from `brand_guide_text` + `icp_text`. | Clean separation between factual ground truth and declared brand voice. |
| D6 | H1 text is `brief.title` verbatim. No LLM call regenerates the H1. | Brief generator v2.0.3 already title-cases and validates; Writer trusts upstream. |
| D7 | The article ships with three required structural elements: Key Takeaways, Agree/Promise/Preview intro, CTA. Missing any → abort with `missing_required_structure`. | These are the AEO/quality contract; partial output is worse than no output. |
| D8 | Section writing is sequential, not parallel. Earlier sections affect remaining term budget for later sections. | Term injection has order-dependent state. |
| D9 | Citation markers are tokens (`{{cit_N}}`) placed in `body` only. Markers in headings → abort. Sources Cited module owns rendering. | Single source of truth for citation formatting. |

---

## 5. Functional Requirements

### 5.0 Step 0 — Input Validation

Runs before any LLM call. Covers the §2.5 cross-validation table plus:

| Rule | Action |
|---|---|
| Any required input payload missing | Abort `missing_input` |
| `sie.terms.required` empty | Continue; log `no_required_terms: true` |
| `brief.metadata.word_budget` missing | Default 2,500; log warning |

### 5.1 Step 1 — Title Generation

**Inputs:** `brief.keyword`, `brief.intent_type`, SIE Required terms + entities (sorted by `recommendation_score`).

**Rules:**
- Title must contain the seed keyword.
- Title must incorporate as many high-scoring SIE Required terms / entities as fit naturally. Keyword and entity coverage takes priority over brevity.
- Tone by intent:
  - `how-to` → "How to …" or "How [Audience] Can …"
  - `listicle` → leads with a number ("7 Reasons …")
  - `comparison` → includes "vs." or "or"
  - `informational` / `local-seo` / `ecom` / `informational-commercial` / `news` → declarative, value-led
- LLM generates 3 candidates; deterministic selection picks highest combined keyword + entity coverage.
- Stored in `output.title`. Not injected into `heading_structure`.

**Topic anchor (v1.6 / Content Quality R3):** After selection, embed the title with `text-embedding-3-small`. This embedding is the topic anchor used by §5.4 (topic-adherence filter).

**Failure:** 0 valid candidates → fallback: `"{keyword} — A Complete Guide"`.

### 5.2 Step 2 — H1 + Enrichment Lede

#### 5.2.1 H1 sourcing (v1.6)

```
article_h1.text = brief.title   # verbatim, exact string equality, no LLM call
```

No LLM path produces the H1 in v1.6+. Any prior keyword-only generator is removed.

#### 5.2.2 Enrichment lede

A sub-head / lede sentence immediately following H1, providing topical context before the first body section.

- 1 sentence, ≤25 words.
- Must include ≥1 entity with `entity_category ∈ {services, equipment, problems, methods}`.
- Must not be a full restatement of the title.

#### 5.2.3 H1 failure modes

| Scenario | Behavior |
|---|---|
| `brief.title` missing/empty | Abort `brief_missing_title` |
| `brief.title` >120 chars | Accept; log warning (length is brief's concern) |
| `brief.title` contains banned term | Abort `banned_term_leakage` (no rewrite — upstream regression must surface) |

#### 5.2.4 Legacy fallback

For replay tests on pre-v2.0 briefs without `title`: log `brief_legacy_no_title`, regenerate H1 from `keyword + intent` (v1.5 LLM path), report `schema_version_effective: "1.6-legacy-h1"`. Not used in production.

### 5.3 Step 2.5 — Intro Construction (Agree / Promise / Preview)

Generated **after** title/H1 but **before** Step 4, so the preview can reference the post-adherence-filter H2 list (§5.4).

**Output:** structured object with three discrete prose blocks, **assembled into a single paragraph** for emission.

```json
{
  "intro": {
    "agree":   "string (≤ 50 words)",
    "promise": "string (≤ 50 words)",
    "preview": "string (≤ 50 words)"
  }
}
```

| Beat | Purpose | Constraints |
|---|---|---|
| Agree | Names the reader's situation in their own language. Anchored in `client_context.icp_text` when available; otherwise inferred from title topic. | ≤50 words. Must not name the brand. Must not begin with the seed keyword. |
| Promise | States what the article will deliver. Anchored in `brief.title` and `brief.scope_statement`. | ≤50 words. May reference the seed keyword once. No CTA. |
| Preview | Names 2–4 (or first 3–5) topics covered, in `heading_structure` order, from the post-adherence-filter H2 list. | ≤50 words. Plain language; no bullets; does not verbatim list H2 headings. |

**Combined-paragraph rule (v1.6):** Total intro is **one paragraph, 60–150 words**. No `\n\n` breaks. No heading markers, no list markers.

**Banned-term enforcement:** Same regex scan as section bodies (§5.16).

**Prompt directive (verbatim text to include):**

> Write the article's introduction as a single paragraph (60–150 words) in three beats:
> 1. **Agree** — name the reader's situation in their own words (1–2 sentences).
> 2. **Promise** — state what this article will deliver, anchored in the title and the article's stated scope (1 sentence).
> 3. **Preview** — name the first 3–5 H2 sections the reader will encounter, in order (1–2 sentences).
> Do not break the paragraph. Do not include headings, bullets, or numbered lists. Do not introduce out-of-scope topics.

**Validation (post-LLM):**

| Check | On failure |
|---|---|
| `60 ≤ len(text.split()) ≤ 150` | Retry once specifying actual count + direction. Then accept + log warning. |
| `"\n\n" not in text.strip()` | Retry once. Then deterministically collapse `\n+` → single space. |
| No heading markers (`(?m)^\s*#{1,6}\s`) | Retry once. Then strip matched lines. |
| Per-beat ≤50 words | Retry once naming the over-length block; then truncate at last sentence boundary ≤50 words. |
| Malformed JSON twice in a row | Abort `intro_generation_failed`. |
| Banned-term match | Per §5.16: body-level rule (retry once; abort on second failure). |

**Placement in `article[]`:** Single item with `type: "intro"`, `level: "none"`, `heading: null`, `body` = the joined paragraph. Inserted after H1 enrichment.

### 5.4 Step 3 — Word Budget Allocation + Topic-Adherence Filter

#### 5.4.1 Budget formula

```
body_budget       = word_budget − conclusion_budget        ≈ 2,375 of 2,500
per_group_budget  = body_budget / h2_group_count

for each H2 group (parent H2 + child H3s):
  weight(parent_H2)            = 1.0
  weight(H3)                   = 1.0  if regular
                               = 1.2  if source == "authority_gap_sme"
  section_budget(s) = per_group_budget × weight(s) / Σ weights_in_group
```

- Each H2 *group* (parent + children) gets an equal body-budget share so groups without H3s aren't starved.
- Authority-gap H3s reallocate **within** their group (taking from parent), not across groups.
- `how-to` / `listicle` allocate equal budget per step/item (no adjustment).
- Conclusion: fixed 100–150 words.
- Floor: every section ≥50 words.

Output: `section_budget` map keyed by heading `order`.

#### 5.4.2 Topic-adherence filter (Content Quality R3)

Runs immediately after budget allocation, before Step 4 begins.

- For each H2 in `brief.heading_structure`: `topic_adherence_score = cosine(h2.embedding, title_embedding)`. Use brief's H2 embeddings if present; otherwise embed on the fly with `text-embedding-3-small`.
- Drop H2s with `topic_adherence_score < 0.62` from the section-writing queue.
- Each dropped H2 logged in `metadata.dropped_for_low_topic_adherence: [{order, heading, score}]`. Writer also emits a payload that the platform forwards to the brief's `discarded_headings` with `discard_reason: "low_topic_adherence_in_writer"` so spin-off routing can pick them up.
- Authority-gap H3s (`source: "authority_gap_sme"`) are exempt from this check, but a parent H2 dropped for low adherence carries its authority-gap H3s with it.
- If `<3` content H2s remain after the drop, log `low_h2_count_after_adherence_drop: true` and proceed. Not an abort.

### 5.5 Step 3.5a — Brand Voice Distillation

Runs in parallel with Step 3.5b after inputs validate. Both must complete before Step 4.

Single LLM call (same model as section writing). Input: `brand_guide_text` + `icp_text` + `website_analysis` (if available).

**Output (Brand Voice Card):**

```json
{
  "brand_voice_card": {
    "tone_adjectives":      ["string"],
    "voice_directives":     ["string (max 200 chars each, max 8 items)"],
    "audience_summary":     "string (≤300 chars)",
    "audience_pain_points": ["string (max 5 items)"],
    "audience_goals":       ["string (max 5 items)"],
    "audience_verticals":   ["string (max 5 items)"],
    "preferred_terms":      ["string (max 20 items)"],
    "banned_terms":         ["string (max 30 items)"],
    "discouraged_terms":    ["string (max 20 items)"],
    "brand_name":           "string or null",
    "client_services":      ["string (max 15 items, from website_analysis.services)"],
    "client_locations":     ["string (max 15 items, from website_analysis.locations)"],
    "client_contact_info":  {"phone": "...", "email": "...", "address": "...", "hours": "..."}
  }
}
```

**Distillation rules:**

- Tone adjectives come from `brand_guide_text` only. Never supplement from `website_analysis`.
- A term is `banned` only when explicitly prohibited. `discouraged` when expressed against without explicit prohibition. `preferred` when explicitly named as preferred phrasing.
- ICP summarized from `icp_text` into `audience_summary` + distinct `audience_pain_points` + `audience_goals` + `audience_verticals`.
- `client_services`, `client_locations`, `client_contact_info` carried verbatim from `website_analysis` when available.
- **Categorization only** — never invent banned/discouraged/preferred terms; the LLM may only extract and paraphrase content present in the input.
- Both JSON and Markdown brand guides are handled natively. PDF/DOCX uploads arrive as extracted text and are treated as Markdown for extraction purposes.

**Failure handling:**

| Scenario | Behavior |
|---|---|
| Malformed JSON | One retry stricter prompt; second failure → abort `brand_distillation_failed` |
| All-empty card | Continue; log warning; sections proceed without brand shaping |
| `brand_guide_text` empty | Skip brand portion; populate only ICP/website-derived fields |
| `icp_text` empty | Skip ICP portion; populate only brand/website-derived fields |
| Both empty AND `website_analysis_unavailable: true` | Fall back to v1.4 behavior; `schema_version_effective: "1.6-degraded"` |

### 5.6 Step 3.5b — Brand–SIE Term Reconciliation

Runs in parallel with 3.5a. Consumes `brand_guide_text` directly (not the distilled card — needs full nuance to detect conflicts) plus SIE Required and Avoid lists.

Single LLM call. Output: per-term classification.

**For each SIE-Required term:**

| Classification | Trigger | Section behavior |
|---|---|---|
| `keep` | No brand conflict | Use at SIE `target` zone usage |
| `exclude_due_to_brand_conflict` | Brand explicitly bans the term | Term must not appear anywhere |
| `reduce_due_to_brand_preference` | Brand discourages without explicit ban | Use at SIE `min` instead of `target`; max becomes `target` |

**For each SIE-Avoid term:**

| Classification | Trigger | Section behavior |
|---|---|---|
| `keep_avoiding` | No brand preference | Continue avoiding |
| `use_due_to_brand_preference` | Brand explicitly prefers the term | Use despite SIE; log in `brand_conflict_log` as `brand_preference_overrides_sie_avoid` |

**Brand always wins (D3).**

**Internal output** (passed to Step 4):

```json
{
  "filtered_sie_terms": {
    "required": [
      {
        "term": "string",
        "zone_usage_target": int,
        "zone_usage_min":    int,
        "zone_usage_max":    int,
        "effective_target":  int,
        "effective_max":     int,
        "reconciliation_action": "keep | reduce_due_to_brand_preference"
      }
    ],
    "excluded": [
      {"term": "string", "original_classification": "required", "reason": "exclude_due_to_brand_conflict"}
    ],
    "avoid": ["string"]
  }
}
```

**Hallucination guard:** reconciliation LLM must include `brand_guide_reasoning` (≤300 chars) for every non-`keep` classification citing the specific brand-guide text. Classifications not grounded in source text → discarded with a warning.

**Failure:** malformed JSON twice → abort `brand_reconciliation_failed`. Empty output → treat all as `keep`. `brand_guide_text` empty → skip reconciliation; emit empty `brand_conflict_log`.

### 5.7 Step 3.6 — Brand & ICP Placement Plan (deterministic)

Pre-allocates which body H2 sections must carry (a) the brand mention and (b) the ICP callout. Prevents "every section assumes the other will carry it" failure.

No LLM call. Token-set scoring.

- `brand_anchor_order` — the H2 whose heading text shares the most tokens with any `client_services` entry. Tie-break: lowest `order`. Falls back to the first content H2 when no overlap exists.
- `icp_anchor_order` — the H2 whose heading text shares the most tokens with any `audience_pain_points` or `audience_verticals` entry. If tied with `brand_anchor_order`, picks the next-best for variety. Falls back to the first content H2 ≠ brand anchor.
- `icp_hook_phrase` — the specific pain-point / vertical that scored highest, so the section prompt can ground its callout concretely.

Tokenization: lowercased, alphanumeric, stopword-filtered. Token-set intersection (size), not Jaccard.

**Section prompt directives:**

| Directive | Applied to | Effect |
|---|---|---|
| `must_mention_brand: true` | brand anchor H2 | Section MUST mention the brand exactly once, anchored to evidence |
| `must_not_mention_brand: true` | every non-anchor body H2 | Section MUST NOT mention the brand |
| `icp_callout_hook: <phrase>` | ICP anchor H2 | Section MUST surface the named pain point / vertical as an explicit callout |

**Bypass:** when `brand_voice_card` is `None`, `brand_name` empty, or no audience signals exist, the relevant directives are not stamped; sections fall back to the soft v1.4 default.

**Metadata surface:** `brand_anchor_h2_order`, `icp_anchor_h2_order`, `icp_hook_phrase`.

### 5.8 Step 4 — Section Writing

Sequential, one LLM call per H2 group (parent H2 + its H3s). Order follows `heading_structure[].order`.

#### 5.8.1 — 4A Answer-First Paragraphs (default; AEO primary mechanism)

When `format_directives.answer_first_paragraphs == true` (default):

Every H2 section opens with a direct answer sentence before elaborating. If the heading is "How Long Does Water Heater Repair Take?", the first sentence must answer that question in plain terms.

Pattern:
- 1 direct answer sentence (≤25 words)
- 1–2 supporting detail sentences
- Then elaboration / evidence / examples

#### 5.8.2 — 4B Intent-Specific Patterns

| Intent | Pattern |
|---|---|
| `how-to` | Each H2 is a numbered step. First sentence = action instruction. Sub-steps under H3. |
| `listicle` | Each H2 is a list item with bolded label. Consistent structure across items. |
| `informational` | Explanatory prose. Answer-first. Evidence / comparison where available. |
| `comparison` | Parallel structure. Each section addresses the same evaluative axis for each option. |
| `local-seo` | Informational base; service-context framing. Avoid city-specific claims unless cited. |
| `ecom` | Feature-benefit framing. Practical outcomes. Neutral, not promotional. |
| `informational-commercial` | Buyer-education tone. Compare options; do not endorse. |
| `news` | Recency-forward. Factual. Lead with most important information. |

#### 5.8.3 — 4C Term Injection

Track usage against SIE `usage_recommendations` (per-zone min/target/max). Terms injected naturally — not bolded, not artificially repeated.

- `h2` zone: aim for SIE `target` count for that term in that zone.
- `h3` zone: aim for SIE `target`.
- `paragraphs` zone: aim for SIE `target`; hard cap at SIE `max`.

`filtered_sie_terms.excluded` (from Step 3.5b): treated as banned for this article — listed explicitly in the prompt as "do not use, brand conflict".

`filtered_sie_terms.avoid`: must not appear anywhere.

Apply `sie.target_keyword.minimum_usage` floors per zone. If SIE-computed range has a higher minimum than the floor, use the higher.

#### 5.8.4 — 4D Format Directives

| Directive | Enforcement |
|---|---|
| `require_bulleted_lists: true` | At least `min_lists_per_article` (default 1) bulleted or numbered list across content sections |
| `require_tables: true` | At least `min_tables_per_article` (default 1) markdown table across content sections |
| `answer_first_paragraphs: true` | See 4A |

Lists and tables must be **distributed** — not stacked into a single section.

#### 5.8.5 — 4E H3 Sub-Section Writing

H3s inherit parent H2 topic context. Prose is more specific, narrower in scope.

For `source: "authority_gap_sme"`:
- Present information not typically on competing SERP pages.
- Avoid restating parent H2.
- Expert, substantive register.
- May NOT use hedge language ("it depends") as a substitute for substance.

#### 5.8.6 — 4E.1 Paragraph-Length Directive (Content Quality R6)

Every section prompt includes:

> **Critical:** Every paragraph must contain at most 4 sentences. Three sentences or fewer is preferred. If a paragraph runs longer, split on a logical break.

The 4-sentence threshold is brief-controlled via `brief.format_directives.max_sentences_per_paragraph` (default 4). When missing, log `max_sentences_per_paragraph_default_applied: true`.

Validation happens post-write in §5.13.

#### 5.8.7 — 4F Citation Marker Placement

Per H2 group:

1. Look up `heading_structure[order].citation_ids` for the H2 and any authority-gap H3s in the group.
2. Resolve each `citation_id` against `research.citations[]`.
3. Filter claims to `relevance_score ≥ 0.50`.
4. Pass resolved claims to the section prompt as grounding material.

**Fallback-stub rule (critical):** If a citation's `extraction_method == "fallback_stub"`, the writer must NOT use its `claim_text` as a specific factual assertion. The citation may be referenced as "according to [publication]…" context, but no specific statistic / data point from the stub may appear in prose.

**Claim integration targets:**

- H2 with ≥1 non-stub verified claim: integrate ≥1 claim into prose as a grounded factual assertion, followed by `{{cit_N}}` marker.
- H2 with only stub claims: reference source as context; no specific figures.
- H2 with `citation_ids: []`: write from general knowledge; do not fabricate statistics.

**Marker syntax (D9):**

- Format: `{{cit_N}}` matching regex `\{\{cit_[0-9]+\}\}`.
- Placed immediately after the closing punctuation of the sentence containing the cited claim. Example: `Demand climbed 18% in Q3.{{cit_007}}`
- Multiple citations in one sentence: stacked in claim-appearance order, no spaces: `{{cit_001}}{{cit_004}}`
- Markers FORBIDDEN in heading fields. Match in any heading → abort `marker_in_heading`.
- The Writer does NOT emit inline Markdown links. The downstream Sources Cited module resolves markers into superscript references + bibliography.

Record per-section: which `citation_id` values appeared in prose (`marker_placed: true`). All others remain `marker_placed: false` until Step 7.

#### 5.8.8 — 4F.1 Citable-Claim Coverage (Content Quality R7, v1.7)

After each H2 group is written, run a deterministic **citable-claim detection** pass on the section body.

A sentence is a citable claim if it matches any of:

| # | Pattern |
|---|---|
| C1 | Numeral followed by `%`, `percent`, `pct`, or `percentage points` |
| C2 | Numeral with currency symbol or USD/EUR/GBP suffix (e.g., `$100M`, `1.2 billion USD`) |
| C3 | Four-digit year 1990–2099 used as a date (`in 2023`, `since 2024`) |
| C4 | `according to <ProperNoun>`, `<ProperNoun> reports`, `<ProperNoun> found`, `<ProperNoun> survey` |
| C5 | `studies show`, `research shows`, `data shows`, `analysts predict` |
| C6 | Sentence containing the name of an entity from `sie.terms.required[*]` where `is_entity == true` AND a quantitative or temporal qualifier from C1–C3 |
| **C7** | **Duration-as-recommendation:** numeric duration (`day`/`week`/`month`/`year`/`hour`/`minute`) followed by a recommendation noun (`cadence`, `window`, `cycle`, `interval`, `period`, `review`, `audit`, `refresh`, `sprint`, `cooldown`, `lookback`, `horizon`, `grace period`, `onboarding`). Example: `"4-to-6 week refresh cadence"`. |
| **C8** | **Frequency-as-recommendation:** `every <N> <unit>` (hours/days/weeks/months/quarters/years) OR `(hourly\|daily\|weekly\|biweekly\|monthly\|quarterly\|annually) <action>` (audit, review, refresh, check, update, inspection, sync, reconciliation, cleanup, standup). |
| **C9** | **Operational-percentage:** `<N>% rule/threshold/target/cap/floor/ceiling/minimum/maximum/baseline/benchmark/cutoff` OR `aim for <N>%` OR `keep [it/under/below/above] <N>%`. |

**Coverage threshold:** ≥50% of detected citable claims per section must be followed by a `{{cit_N}}` marker.

**First-party preference:** when Research produced multiple candidates for a claim, prefer citations whose `domain` (extracted from `url`) matches the entity named in the claim.

**Below-threshold remediation:** one-shot retry with a `COVERAGE_RETRY:` directive naming the uncited claim sentences and asking the LLM to either add a marker from the available pool or rewrite the sentence to remove the specific statistic / year / brand attribution.

**Auto-soften fallback for operational claims (v1.7):** if the retry still fails, a deterministic soften pass rewrites C7/C8/C9 phrases to hedge phrasing — but **NOT C1–C6**, where softening would mangle the claim more than help it.

| Pattern | Example before → after |
|---|---|
| C7 (duration) | `4-to-6 week refresh cadence` → `a typical refresh cadence (every few weeks)` |
| C7 (duration, day-scale) | `60-day affiliate audit window` → `a typical audit window (a brief window)` |
| C8 (frequency, named) | `weekly audit` → `a regular audit` |
| C8 (frequency, every-N) | `every 7 days` → `every few days` |
| C9 (operational %) | `5% rule` → `a small percentage rule` |
| C9 (aim for) | `aim for 30%` → `aim for a moderate share` |

Sections still below threshold after retry + soften are **accepted** and recorded in `metadata.under_cited_sections`. Run never aborts on coverage.

**FAQ rule:** FAQ answers are exempt from the 50% threshold. However, the same claim-detection runs on FAQ answers — any FAQ answer with a numeric statistic without a citation is rewritten (one-shot retry) to remove the statistic in favor of qualitative phrasing.

**Logging events:**

| Event | Level | Trigger |
|---|---|---|
| `writer.coverage.complete` | INFO | Totals (groups inspected / retries / soften count / under-cited remaining) |
| `writer.coverage.retry` | INFO | Per-H2 trigger (citable / cited / ratio) |
| `writer.coverage.retry_succeeded` | INFO | Retry cleared the floor |
| `writer.coverage.under_cited_after_retry` | WARN | Retry + soften didn't clear |
| `writer.coverage.retry_failed` | WARN | LLM call exception |
| `writer.coverage.retry_section_count_mismatch` | WARN | Retry returned wrong number of sections; refused splice |

### 5.9 Step 5 — FAQ Section Writing

After all content sections.

**Structure:**
- FAQ section opens with an H2: exact text from `heading_structure` where `type == "faq-header"` (always "Frequently Asked Questions" per brief spec).
- Each question is an H3.
- Each answer is a direct prose paragraph: 40–80 words, answer-first, no preamble.

**AEO rules:**
- Answers must be self-contained — readable without surrounding article context.
- Seed keyword or its primary sub-phrase must appear in ≥2 FAQ answers.
- Answers must NOT refer back to article sections ("as mentioned above").
- Answers are the most citation-friendly content — must read as standalone facts.

**FAQ + brand:**
- Receives Audience block (`audience_summary` + `audience_pain_points` + `audience_goals`).
- Receives Brand Voice block (`tone_adjectives` + first 3 `voice_directives`).
- Receives `filtered_sie_terms.required`.
- FAQ questions must reflect ICP phrasing patterns, not generic SEO templates.
- Answers respect tone and banned-terms identically to section writing.

**FAQ term tracking:** FAQ excluded from word budget. NOT excluded from term zone tracking — natural occurrences count toward zone totals.

### 5.10 Step 6 — Conclusion

Final content section. `type: "conclusion"`, no heading level per brief spec.

**Rules:**
- 100–150 words.
- Synthesizes core takeaways in 2–3 sentences.
- Conclusion prose must NOT contain the CTA — see §5.11 for separate CTA element.
- Must not introduce new information.
- Seed keyword must appear at least once.
- Receives full Brand Voice block + `audience_summary` + Client Context block (when website analysis available).
- May include a natural closing sentence referencing client services / location where contextually relevant. Never a hard sales CTA.

### 5.11 Step 6.4 — CTA (separate structural element)

Required. Rendered after the conclusion paragraph(s).

**Inputs:** `client_context.icp_text` (when available), `brief.intent_type`, `output.title`.

**Rules:**
- Single sentence, ≤30 words.
- Must name a specific next action (read, download, contact, evaluate, compare, sign up, request, schedule, audit, review).
- Never a hard sales pitch.
- Regex block: `\b(buy|purchase|order)\s+now\b|\blimited\s+time\b|\bact\s+today\b`.

**ICP-driven verb:** when `icp_text` provided, draw next-step verb from stated audience goals. Otherwise use intent-appropriate template:

| Intent | Template |
|---|---|
| `how-to` | "Try these steps in your next [task] and measure the result." |
| `informational` | "Explore [related sub-topic] next." |
| `comparison` | "Run this comparison against your current [solution category] to see where the trade-offs land for your team." |
| `local-seo` / `ecom` / `informational-commercial` | "When you're ready to evaluate options, look for [criterion drawn from article]." |
| `news` | "Watch for follow-on coverage as the situation develops." |

**Output placement:** Added to `article[]` as `{order, level: "none", type: "cta", heading: null, body: "<CTA sentence>"}` immediately after the conclusion.

**Failure:**

| Scenario | Behavior |
|---|---|
| >30 words | Retry once naming the limit. |
| Still >30 | Truncate at last word boundary ≤30; flag `cta_truncated: true`. |
| Hard sales phrase regex match | Retry once with explicit "no hard sales language" guidance. |

### 5.12 Step 6.5 — Key Takeaways

Generated **after** all sections, FAQs, and conclusion are written so it summarizes actual content rather than the outline.

**Inputs:** the full assembled article body + `output.title`.

**Rules:**
- Single LLM call.
- 3–5 standalone sentences, each ≤25 words.
- Each sentence is self-contained (LLM citation surfaces extract individual sentences).
- Facts or actionable claims only — no opinion, no marketing language, no rhetorical questions.
- Sentences must not repeat: cosine similarity ≥0.85 between any pair triggers regeneration of the offending pair.
- Brand mentions in Key Takeaways count toward the brand-mention budget.

**Output placement:** Added to `article[]` immediately after the H1 enrichment (before the intro) so the renderer surfaces it at the top of the page:

```
{order, level: "none", type: "key-takeaways", heading: "Key Takeaways", body: "- bullet\n- bullet\n- bullet"}
```

The frontend renderer recognizes `type: "key-takeaways"` and emits `## Key Takeaways`.

**Re-ordering pass:** Because Key Takeaways is generated last but rendered second, the assembly performs a final re-ordering pass to insert the takeaways block in its display position before serialization.

**Failure:**

| Scenario | Behavior |
|---|---|
| Count <3 or >5 after retry | Truncate to 5 if over; accept down to 3 if under; abort `key_takeaways_count_invalid` if <3 |
| Any sentence >25 words after retry | Retry once with limit named |
| Pair cosine ≥0.85 after retry | Drop one; continue with 3–4 takeaways |

### 5.13 Step 6.6 — Paragraph-Length Validation (Content Quality R6)

Runs after all sections + FAQs + conclusion + CTA + Key Takeaways, BEFORE Step 7 citation reconciliation and the banned-term scan.

Per `body` field in `article[]`:

1. Split each body on blank lines (Markdown paragraph boundaries).
2. For each paragraph, count sentence-terminal punctuation (`.`, `?`, `!`) outside Markdown link/code spans. Abbreviation dictionary to skip false positives: `e.g.`, `i.e.`, `etc.`, `Mr.`, `Dr.`, `vs.`, `Inc.`, `U.S.`, `U.K.`.
3. If any paragraph > `max_sentences_per_paragraph` (default 4), mark for retry.

**Per-section retry:**
- One retry per section, addendum naming the over-length paragraph and limit.
- Still over → accept; flag `paragraph_length_violations: [{section_order, paragraph_index, sentence_count}]`.

Also scans Key Takeaways bullets — any bullet >25 words → one retry of Key Takeaways generation with strict word limit.

### 5.14 Step 6.7 — Per-H2 Body Length Validator

Catches H2s shipping with empty/lightweight bodies.

Runs **after** §5.13 and the heading-level banned-term scan, **before** §5.15 citation reconciliation.

**Algorithm:** for each H2 section group (parent H2 + child H3 bodies):

1. `group_word_count = sum(word_count(body) for body in group)` after stripping `{{cit_N}}` markers.
2. If `group_word_count >= format_directives.min_h2_body_words`: pass.
3. Otherwise: re-run `write_h2_group` ONCE with a length-retry directive naming the floor and current count, asking for additional substance (not padding).
4. After retry:
   - ≥floor: success, replace original.
   - Still under: accept whichever attempt has more words; append `{section_order, word_count, floor}` to `metadata.under_length_h2_sections`.

Never aborts. Retry uses a single LLM call per offending H2. Retry exception → flag and preserve original.

**Floor table** (from `intent_format_template.h2_pattern`):

| Pattern | Floor | Intent |
|---|---|---|
| `sequential_steps` | 120 | how-to |
| `ranked_items` | 80 | listicle |
| `parallel_axes` | 150 | comparison |
| `topic_questions` | 180 | informational |
| `buyer_education_axes` | 180 | informational-commercial |
| `feature_benefit` | 150 | ecom |
| `place_bound_topics` | 150 | local-seo |
| `news_lede` | 100 | news |

**Logging:** `writer.h2_length.complete` (INFO), `writer.h2_length.retry` (INFO), `writer.h2_length.retry_succeeded` (INFO), `writer.h2_length.retry_still_under` (WARN), `writer.h2_length.retry_failed` (WARN).

### 5.15 Step 6.8 — ICP Callout LLM Judge

Runs after the article is fully assembled and citation reconciliation runs. Verifies the ICP-anchor section (Step 3.6) actually surfaced the callout. A regex / substring check would generate false negatives when the LLM paraphrases the hook ("margin erosion from refunds" → "shrinking unit economics on returned orders"); the judge tolerates paraphrase.

**Position:** after format-compliance computation, before metadata construction. Matches the anchor section by heading text in the post-resequence `article` (pre-resequence `order` no longer meaningful here).

**Inputs:** anchor section's body (truncated to 4,000 chars), ICP hook phrase, brand voice card's `audience_pain_points` + `audience_verticals` for close-synonym recognition.

**Output (JSON):** `icp_callout_landed` (bool), `evidence` (≤200-char verbatim quote when landed), `reasoning` (one-sentence justification).

**Failure-mode policy:**
- Never aborts.
- LLM failure / malformed → `icp_callout_landed = None`. Returning False would falsely flag the run.
- No ICP anchor assigned → skip, `None`.
- Anchor heading not found in `article` → `False` with `anchor_not_in_article`.
- Empty anchor body → `False` with `empty_body`, no LLM call.

**Cost discipline:** at most one LLM call per article, only when an ICP anchor was assigned, 256-token output cap, 4,000-char input cap.

**Metadata surface:** `icp_callout_landed`, `icp_callout_evidence`, `icp_callout_judge_status`.

### 5.16 Step 7 — Citation Usage Reconciliation

After all content is written.

1. Collect the set of `citation_id` values that received markers across all sections.
2. Compare against the complete `research.citations[]`.
3. For each citation, determine:
   - `used`: appeared in ≥1 section's prose.
   - `sections_used_in`: ordered list of `heading_structure[].order` values.
   - `marker_placed`: whether a marker was placed.
4. Build the `citation_usage` block.

**Unused citations are not an error.** Recorded as `used: false`. No retry. (Not every citation may naturally integrate given word budgets and section focus.)

**Metadata output:** `citations_used` and `citations_unused` counts.

### 5.17 Step 8 — Banned-Term Regex Scan (v1.5)

Runs after Step 7, before serialization. Regex-based per Decision D2.

#### 5.17.1 Construction

```python
import re

banned_terms = brand_voice_card["banned_terms"]
if banned_terms:
    pattern = r"\b(?:" + "|".join(re.escape(t) for t in banned_terms) + r")\b"
    banned_regex = re.compile(pattern, re.IGNORECASE)
else:
    banned_regex = None
```

#### 5.17.2 Scan targets

Each field independently: H1, every H2, every H3, every section `body`, intro, conclusion, CTA, Key Takeaways body, each FAQ question, each FAQ answer. Citation marker tokens `{{cit_N}}` cannot contain banned-term text by construction; ignored.

#### 5.17.3 Match behavior

| Match Location | Severity | Behavior |
|---|---|---|
| Any heading (H1/H2/H3) | **Critical** | Abort `banned_term_leakage` immediately. No retry. Surface term + heading text. |
| Body section, intro, conclusion, CTA, FAQ answer, Key Takeaways body | **Recoverable** | Retry that unit once with stricter prompt naming the banned term. If still matches → abort `banned_term_leakage`. |
| FAQ question | **Recoverable** | Same retry-once policy. |

#### 5.17.4 Documented limitations

- Hyphen-variant: `"high-quality"` does not match `"high quality"` (no hyphen). Documented.
- Multi-word phrases match as literal phrases with outer word boundaries; `"cutting-edge"` and `"cuttingedge"` do not match `"cutting edge"`.
- Substring guard: word-boundary regex prevents `"art"` matching inside `"smart"`.
- Possessives / plurals: `"premium"` matches `"premium's"` and `"premiums"` because `\b` treats punctuation as separators. Accepted for v1.
- Case variations handled by `re.IGNORECASE`.

#### 5.17.5 Reporting

Successful retry → original leakage logged in structured logs; not surfaced to user. Abort → `banned_term_leakage` with offending term + field + snippet.

### 5.18 Step 9 — Title-Case Normalization (defense-in-depth, v1.6)

Runs immediately before serialization, after the banned-term pass.

```python
from titlecase import titlecase

_TITLE_CASE_LEVELS = {"H1", "H2", "H3"}
_TITLE_CASE_TYPES  = {"content", "faq-header", "conclusion", "title"}

def apply_title_case(article_items):
    for item in article_items:
        if item.level in _TITLE_CASE_LEVELS and item.type in _TITLE_CASE_TYPES:
            item.text = titlecase(item.text)
    return article_items
```

Pin **`titlecase==2.4.1`** to match the brief generator.

**Idempotency:** `titlecase(titlecase(x)) == titlecase(x)`. Safe to apply unconditionally.

**Exclusions:** FAQ questions (`type == "faq-question"` — sentence case is correct), intro/conclusion body, CTA body, Key Takeaways bullets, section bodies, citation markers.

**Validation (non-production assert; production log-as-warning):**

```python
assert titlecase(item.text) == item.text
# Failure → log "title_case_round_trip_failed", emit heading anyway.
```

### 5.19 Step 10 — Markdown + HTML Serialization (v1.6)

Two flat string serializations emitted alongside `article[]`. Deterministic, no LLM calls.

#### 5.19.1 New top-level output fields

| Field | Type | Purpose |
|---|---|---|
| `article_markdown` | string | GitHub-flavored Markdown with `[^N]` footnote citations. Suitable for Markdown editors, the platform's article preview, GitHub renders, the platform Publish module's Google Doc Apps Script webhook. |
| `article_html` | string | Semantic HTML5 fragment (no `<html>`, `<head>`, `<body>`, no inline styles) with `<sup><a href="#cite-N">` citations and ordered Sources list. Suitable for direct paste into WordPress code/HTML block, Google Docs visual paste, or CMS embed. |

Always present when `article[]` non-empty. Populated on legacy / no-context / degraded paths.

#### 5.19.2 Markdown rules

| `article[]` Item | Markdown |
|---|---|
| `level == "H1"` | `# {text}\n\n` |
| `level == "H2"`, `type == "content"` | `## {text}\n\n` |
| `level == "H3"`, `type == "content"` | `### {text}\n\n` |
| `level == "H2"`, `type == "faq-header"` | `## {text}\n\n` |
| `level == "H2"`, `type == "conclusion"` | `## {text}\n\n` |
| Intro / section body / CTA / Key Takeaways body | `{text}\n\n` |
| FAQ question | `### {text}\n\n` |
| FAQ answer | `{text}\n\n` |
| Citation marker `{{cit_N}}` inline | `[^N]` (GitHub footnote reference) |
| Sources Cited section | `## Sources\n\n[^1]: {title} — {url}\n[^2]: ...` |

Strip trailing whitespace. End with a single `\n`.

#### 5.19.3 HTML rules

| `article[]` Item | HTML |
|---|---|
| `level == "H1"` | `<h1>{text}</h1>` |
| `level == "H2"` (any `type`) | `<h2>{text}</h2>` |
| `level == "H3"` (any `type`) | `<h3>{text}</h3>` |
| Intro / section body / CTA | `<p>{text}</p>` |
| FAQ question | `<h3>{text}</h3>` |
| FAQ answer | `<p>{text}</p>` |
| Citation marker `{{cit_N}}` inline | `<sup><a href="#cite-N">N</a></sup>` |
| Sources Cited section | `<h2>Sources</h2><ol><li id="cite-1"><a href="{url}">{title}</a></li>...</ol>` |

Constraints:
- HTML-escape all text content (`&`, `<`, `>`, `"`, `'`) before insertion. Markers escaped *after* substitution.
- Fragment only — no doctype / wrapping tags / meta.
- No inline `style` attributes; no class names.
- Items joined with `\n` (one element per line) for readability.
- Anchor targets live on `<li>` inside Sources `<ol>` — in-document anchors may not survive paste into Docs / WP visual editor; superscript numerals remain readable.

#### 5.19.4 Determinism & idempotency

- Pure functions of `(article[], citations[])`.
- Do NOT mutate inputs.
- Re-parsing Markdown / HTML output and tag-stripping must recover the same plain-text body content.

#### 5.19.5 Serializer failure handling

| Scenario | Behavior |
|---|---|
| `article[]` empty | `article_markdown = ""`, `article_html = ""`. No abort. |
| Marker references unknown citation id | Emit verbatim (`{{cit_N}}` in MD, `<span>{{cit_N}}</span>` in HTML). Log `serializer_unknown_citation`. No abort. |
| Body contains literal `<` / `>` / `**` | Markdown: pass through (already-Markdown content rendered as-is). HTML: escape entire paragraph (body LLM is not authorized to emit HTML). |
| Sources Cited didn't run / missing | Omit Sources section in both formats. Markers still render to `[^N]` / `<sup>` form. |

---

## 6. Output Schema

```json
{
  "keyword":     "string",
  "intent_type": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial",
  "title":       "string",
  "article": [
    {
      "order":               0,
      "level":               "H1 | H2 | H3 | none",
      "type":                "content | faq-header | faq-question | conclusion | h1-enrichment | key-takeaways | intro | cta | title",
      "heading":             "string | null",
      "body":                "string (GFM/CommonMark Markdown with {{cit_N}} markers immediately after closing punctuation of cited sentences; markers conform to regex \\{\\{cit_[0-9]+\\}\\})",
      "word_count":          0,
      "section_budget":      0,
      "citations_referenced":["cit_001"]
    }
  ],
  "article_markdown": "string (GFM serialization with [^N] footnotes)",
  "article_html":     "string (semantic HTML5 fragment with <sup><a href=\"#cite-N\">)",
  "key_takeaways":    ["string (≤ 25 words each, 3–5 items)"],
  "intro": {
    "agree":   "string (≤ 50 words)",
    "promise": "string (≤ 50 words)",
    "preview": "string (≤ 50 words)"
  },
  "cta": "string (≤ 30 words)",

  "citation_usage": {
    "total_citations_available": 0,
    "citations_used":            0,
    "citations_unused":          0,
    "usage": [
      {"citation_id": "cit_001", "used": true, "sections_used_in": [2, 4], "marker_placed": true}
    ]
  },

  "format_compliance": {
    "lists_present":         0,
    "tables_present":        0,
    "lists_required":        0,
    "tables_required":       0,
    "answer_first_applied":  true,
    "directives_satisfied":  true
  },

  "brand_voice_card_used": {
    "tone_adjectives":      ["..."],
    "voice_directives":     ["..."],
    "audience_summary":     "...",
    "audience_pain_points": ["..."],
    "audience_goals":       ["..."],
    "audience_verticals":   ["..."],
    "preferred_terms":      ["..."],
    "banned_terms":         ["..."],
    "discouraged_terms":    ["..."],
    "brand_name":           "string or null",
    "client_services":      ["..."],
    "client_locations":     ["..."],
    "client_contact_info":  {"phone": "...", "email": "...", "address": "...", "hours": "..."}
  },

  "brand_conflict_log": [
    {
      "term":                  "string",
      "sie_classification":    "required | avoid",
      "resolution":            "exclude_due_to_brand_conflict | reduce_due_to_brand_preference | brand_preference_overrides_sie_avoid",
      "brand_guide_reasoning": "string (≤300 chars)",
      "applicable_section_ids":["string"]
    }
  ],

  "client_context_summary": {
    "brand_guide_provided":     true,
    "icp_provided":             true,
    "website_analysis_used":    true,
    "schema_version_effective": "1.7 | 1.7-no-context | 1.7-degraded | 1.7-legacy-h1"
  },

  "metadata": {
    "total_word_count":        0,
    "word_budget":             2500,
    "faq_word_count":          0,
    "budget_utilization_pct":  0.0,
    "word_count_conflict":     false,
    "no_required_terms":       false,
    "section_count":           0,
    "faq_count":               0,
    "citations_used":          0,
    "citations_unused":        0,
    "no_citations":            false,
    "retry_count":             0,

    "dropped_for_low_topic_adherence": [{"order": 0, "heading": "string", "score": 0.0}],
    "low_h2_count_after_adherence_drop": false,

    "paragraph_length_violations": [{"section_order": 0, "paragraph_index": 0, "sentence_count": 0}],

    "under_cited_sections": [
      {"section_order": 0, "citable_claims": 0, "cited_claims": 0, "ratio": 0.0, "threshold": 0.5, "operational_claims_softened": 0}
    ],
    "operational_claims_softened": [
      {"section_order": 0, "h2_order": 0, "rule": "duration-as-recommendation", "original": "...", "softened": "..."}
    ],
    "citation_coverage_retries_attempted":  0,
    "citation_coverage_retries_succeeded":  0,

    "under_length_h2_sections":          [{"section_order": 0, "word_count": 0, "floor": 0}],
    "h2_body_length_retries_attempted":  0,
    "h2_body_length_retries_succeeded":  0,

    "topic_brand_alignment":      "brand_aligned | brand_agnostic",
    "brand_mention_count":        0,
    "brand_mention_flags":        ["zero_brand_mentions_on_brand_aligned_topic | brand_mentions_exceed_target | brand_mentions_exceed_hard_cap"],
    "brand_anchor_h2_order":      0,
    "icp_anchor_h2_order":        0,
    "icp_hook_phrase":            "string",
    "icp_callout_landed":         true,
    "icp_callout_evidence":       "string (≤200 chars)",
    "icp_callout_judge_status":   "ok | anchor_not_in_article | empty_body | llm_failure | not_assigned",

    "max_sentences_per_paragraph_default_applied": false,
    "cta_truncated":              false,

    "schema_version":             "1.7",
    "brief_schema_version":       "2.0+",
    "generation_time_ms":         0
  }
}
```

`schema_version` valid values: `"1.7"`, `"1.7-no-context"`, `"1.7-degraded"`, `"1.7-legacy-h1"`. The orchestrator's `EXPECTED_MODULE_VERSIONS["writer"]` and `WRITER_ACCEPTED_VERSIONS` must include all four.

---

## 7. Failure Mode Reference

| Scenario | Behavior |
|---|---|
| Any input JSON fails schema validation | Abort `schema_validation_failed`; no partial output |
| `brief.keyword != research.keyword` or `!= sie.keyword` | Abort `keyword_mismatch` |
| `brief.title` missing / empty | Abort `brief_missing_title` (production); legacy fallback only for replay |
| `client_context` malformed | Abort `client_context_validation_error` |
| Distillation LLM fails twice | Abort `brand_distillation_failed` |
| Reconciliation LLM fails twice | Abort `brand_reconciliation_failed` |
| Intro generation malformed twice | Abort `intro_generation_failed` |
| Section LLM call times out | Retry once; on second failure insert `"[SECTION GENERATION FAILED — MANUAL REVIEW REQUIRED]"`; flag in metadata |
| Title generation produces 0 valid candidates | Fallback `"{keyword} — A Complete Guide"` |
| Word budget exceeded after all sections | Trim lowest-priority H3s by `heading_priority` from brief until budget met; log trimmed sections |
| End-to-end exceeds 90s | Abort `generation_timeout` |
| `sie.terms.required` empty | Continue; log `no_required_terms: true` |
| `research.citations` missing/empty | Degraded mode; sections written without citation grounding; `no_citations: true` |
| All claims for an H2 are `fallback_stub` | Write without specific factual assertions; reference source as context only; flag `all_stubs: true` on the section |
| Final article missing `key-takeaways` / `intro` / `cta` | Abort `missing_required_structure` with `missing_elements: [...]`. No partial output |
| Intro block >50 words after retry | Truncate at last sentence boundary ≤50 words; accept |
| CTA >30 words after retry | Truncate at last word boundary ≤30; flag `cta_truncated: true` |
| CTA matches hard-sales regex after retry | Truncate / sanitize; flag `cta_sanitized: true` |
| Key Takeaways count <3 after retry | Abort `key_takeaways_count_invalid` |
| Key Takeaways count >5 after retry | Truncate to 5 |
| Section fails R7 50% coverage after retry + soften | Accept; flag in `under_cited_sections` |
| Section fails R6 paragraph cap after retry | Accept; flag in `paragraph_length_violations` |
| H2 group below `min_h2_body_words` after retry | Accept best attempt; flag in `under_length_h2_sections` |
| Banned term in heading | Abort `banned_term_leakage` immediately; no retry |
| Banned term in body/FAQ/intro/conclusion/CTA after retry | Abort `banned_term_leakage`; surface term + field + snippet |
| Marker found in heading | Abort `marker_in_heading` |
| Brand mentions ≥6 (hard cap) after retry on highest-mention section | Accept; flag `brand_mentions_exceed_hard_cap`. Do not block. |
| <3 H2s remain after topic-adherence drop | Continue; log `low_h2_count_after_adherence_drop: true`. Not an abort. |
| ICP callout judge LLM fails | `icp_callout_landed = None`; not a flag |
| Serializer encounters unknown citation id | Emit marker verbatim; log `serializer_unknown_citation`. Not an abort. |

---

## 8. AEO Optimization Requirements

| Requirement | Implementation |
|---|---|
| Answer-first paragraphs | Every H2 opens with ≤25-word direct answer before elaboration |
| Self-contained FAQ answers | No cross-references to article sections |
| Clean section boundaries | Content does not bleed topically into adjacent sections |
| Factual density | Sections contain verifiable facts, not filler |
| Hedge-free substance | Claims must be specific and supportable; vague hedges do not satisfy word budgets |
| Question-answer alignment | H2s framed as questions answered directly in first sentence |
| Entity presence | High-salience entities appear in semantically appropriate sections; not forced everywhere |
| No promotional language | Avoid "the best", "industry-leading"; reduces citation trustworthiness |
| Self-contained Key Takeaways | Each Takeaway sentence extractable by an LLM citation surface |

---

## 9. Success Metrics

Structural and guardrail metrics, not downstream ranking.

| Metric | Target |
|---|---|
| Output validates against JSON schema | 100% |
| Word count within budget (±5%) | ≥95% |
| All `heading_structure` entries present in output (after adherence filter) | 100% |
| Required terms meeting zone minimums | ≥90% |
| Format directives satisfied (lists, tables, answer-first) | 100% |
| FAQ contains correct question count (3–5) | 100% |
| Conclusion present | 100% |
| Key Takeaways present (3–5 items) | 100% |
| Intro present (Agree/Promise/Preview, 60–150 words) | 100% |
| CTA present (≤30 words) | 100% |
| Per-section citation coverage ≥50% on citable claims | ≥85% (after retry + soften) |
| Per-H2 body length above intent floor | ≥90% |
| End-to-end within 90s | ≥95% |
| Cost per article < $0.75 | ≥95% |

---

## 10. Performance Targets

| Stage | Target | Max |
|---|---|---|
| End-to-end | 60s | 90s |
| Input validation + budget allocation | 2s | 5s |
| Title generation (3 candidates) | 5s | 10s |
| Brand distillation + reconciliation (parallel) | 5s | 15s |
| Section writing (all H2 groups, sequential) | 30s | 60s |
| FAQ + conclusion + CTA + Key Takeaways | 10s | 20s |
| Citation resolution + claim injection (per section, in-memory) | <1s | 2s |
| Step 6.4–6.8 validators | 5s | 10s |
| Step 7 citation reconciliation | <1s | 2s |
| Step 8 banned-term scan | <1s | 1s |
| Step 9 title-case pass | <1s | 1s |
| Step 10 serialization | <1s | 1s |

Section writing dominates. One LLM call per H2 group. Sequential due to term-budget state.

---

## 11. Cost Model

| Component | Cost per Article |
|---|---|
| Title generation | ~$0.01 |
| Brand distillation | $0.02–$0.04 |
| Brand reconciliation | $0.01–$0.02 |
| H1 (no LLM in v1.6+) | $0 |
| Intro construction | ~$0.01 |
| Section writing (6 H2 groups avg) | $0.20–$0.35 |
| Coverage retries (when fired) | $0.01–$0.03 each, ≤1/run steady state |
| FAQ writing | ~$0.05 |
| Conclusion + CTA | ~$0.02 |
| Key Takeaways | ~$0.02 |
| ICP callout judge | ~$0.005 |
| **Estimated total** | **$0.32–$0.52** |
| **Budget ceiling** | **$0.75** |

---

## 12. Business Rules Summary

| Rule | Value |
|---|---|
| Locale | English / United States |
| Word budget | 2,500 words (content sections only; FAQ excluded) |
| Word budget tolerance | ±5% |
| Title must contain seed keyword | Yes |
| H1 text | Verbatim from `brief.title` — no LLM regeneration |
| H1 enrichment lede max words | 25 |
| Intro construction | Single paragraph, 60–150 words, Agree/Promise/Preview in order |
| Conclusion word range | 100–150 words |
| FAQ answer word range | 40–80 words |
| FAQ may cross-reference article | No |
| Answer-first paragraphs | Required for all H2 sections |
| Avoid terms enforcement | Hard block; subject to brand-override (brand wins) |
| Sections trimmed when over budget | Lowest `heading_priority` H3s first |
| FAQ excluded from word budget | Yes |
| FAQ included in term zone tracking | Yes |
| Citation grounding required for H2s with verified claims | Yes — ≥1 non-stub claim per cited H2 |
| Fallback-stub claims used as factual assertions | Never |
| Body output format | GFM Markdown with `{{cit_N}}` markers |
| Marker format | `{{cit_N}}` — placed immediately after closing punctuation; regex `\{\{cit_[0-9]+\}\}` |
| Multiple citations in one sentence | Stacked, no spaces: `{{cit_001}}{{cit_004}}` |
| Markers in headings | Forbidden — abort if found |
| Citation usage tracked per id | Yes (`used`, `sections_used_in`, `marker_placed`) |
| Unused citations trigger retry | No — recorded as unused |
| Required structural elements | `key-takeaways` (3–5 items, ≤25 words each), `intro` (60–150 words single paragraph), `cta` (≤30 words). Missing any → abort `missing_required_structure` |
| H2 topic-adherence threshold | `cosine(h2.embedding, title.embedding) ≥ 0.62`; below → drop to spin-offs |
| Paragraph length cap | Default 4 sentences (`format_directives.max_sentences_per_paragraph`); over → one retry then accept + flag |
| External citation coverage on citable claims | ≥50% per section; below → one retry then auto-soften (C7/C8/C9 only) then accept + flag |
| Brand mention budget | 2–3 target; 0 + brand-aligned topic → flag (no reject); 4–5 → warn; ≥6 → retry then accept |
| Brand-aligned vs brand-agnostic | `cosine(title.embedding, brand_voice_card.client_services_joined.embedding) ≥ 0.55` → `brand_aligned` |
| Brand always wins term conflicts | Brand-banned > SIE-Required (exclude); Brand-preferred > SIE-Avoid (use) |
| Banned term enforcement | Regex, case-insensitive, word-boundary, alternation over `brand_voice_card.banned_terms` |
| Heading banned-term match | Abort immediately, no retry |
| Body/FAQ banned-term match | Retry once; second match → abort |
| Title case | `titlecase==2.4.1` pass on H1/H2/H3 (content/faq-header/conclusion/title); idempotent |
| Multi-format output | `article_markdown` + `article_html` always present when `article[]` non-empty |
| Brand voice card lifecycle | Regenerated per run; not cached; persisted in `brand_voice_card_used` |

---

## 13. What This PRD Does Not Cover

These belong to the engineering implementation layer, not the PRD:

- LLM model selection per call type (Anthropic Claude is the provider per platform decision — Sonnet vs Opus per call is implementation)
- Exact prompt templates / system prompts
- Lemmatizer selection for term audit (must match SIE module's implementation)
- Caching strategy for repeated (brief, SIE) input pairs
- Authentication and API key management
- Rate limiting and retry logic for LLM API calls
- Logging and observability beyond the named events
- Output storage schema in the platform database
- Schema versioning compatibility with future brief schema versions
- Term usage audit, hallucination scanning, and human review workflows (downstream quality module)
- Citation style formatting (APA, MLA, Chicago) — not required; Markdown footnotes + HTML `<sup>` only
- Citation link-rot detection post-publish (future monitoring module)
- CMS / publishing integration

---

## 14. Test Fixture Suggestions

Recommended fixtures to validate the module in isolation before platform integration:

| ID | Description | Asserts |
|---|---|---|
| F-A | Brief + Research + SIE, no `client_context` | Schema valid; `schema_version_effective == "1.7-no-context"`; v1.4 fallback path |
| F-B | All `client_context` fields empty + `website_analysis_unavailable: true` | `schema_version_effective == "1.7-degraded"` |
| F-C | Brand guide only; explicit banned terms; empty ICP; no website analysis | `brand_conflict_log` populates; banned terms absent in output |
| F-D | Full client context, two different brand guides on same brief/SIE | Section tone shifts visibly |
| F-E | Banned term that is also SIE-Required | Reconciliation excludes; `brand_conflict_log` records decision with cited reasoning |
| F-F | SIE-Avoid term that brand guide prefers | Brand wins; term present; conflict logged as `brand_preference_overrides_sie_avoid` |
| F-G | Brand guide bans a common term ("affordable") section writing might use naturally | Post-hoc regex catches; retry; either clean output or `banned_term_leakage` with term + field + snippet |
| F-H | Brand guide bans a term likely in a heading | Immediate abort on heading match; no retry |
| F-I | Brand guide bans `"art"`; section uses `"smart"` | Word boundary prevents false positive; `"smart"` passes |
| F-J | All H2s pass topic adherence | `dropped_for_low_topic_adherence == []` |
| F-K | Two H2s drift off-topic | Dropped; spin-off payload emitted; `low_h2_count_after_adherence_drop: false` if ≥3 remain |
| F-L | H2 group missing intent floor word count | Length retry triggered; success or `under_length_h2_sections` entry |
| F-M | Section with `"4-to-6 week refresh cadence"` and no matching citation | Coverage retry; if unresolved, soften to `"a typical refresh cadence (every few weeks)"`; entry in `operational_claims_softened` |
| F-N | Section with `"5% rule"` no citation | Soften to `"a small percentage rule"` |
| F-O | Section with `"18% in Q3"` no citation | NOT softened (C1 statistic); accept; flag in `under_cited_sections` |
| F-P | Brief missing `title` | Abort `brief_missing_title` (production path); legacy fallback path emits `"1.7-legacy-h1"` |
| F-Q | Intro LLM returns 4-paragraph response | Single-paragraph validation retry; deterministic collapse on second failure |
| F-R | CTA includes "Buy now" | Hard-sales regex retry; sanitize + flag if still present |
| F-S | Key Takeaways returns 6 sentences | Truncate to 5; no abort |
| F-T | Key Takeaways returns 2 sentences | Abort `key_takeaways_count_invalid` |
| F-U | `article[]` non-empty + valid citation markers | `article_markdown` round-trips to plain text body; `article_html` parses; markers map 1:1 across `article[]` / MD / HTML |
| F-V | Marker `{{cit_999}}` references unknown citation | Serializer emits verbatim + `serializer_unknown_citation` log; no abort |

---

## 15. Implementation Notes (non-normative)

These are guidance for the build team but not part of the contract:

- Use `text-embedding-3-small` for both the title topic anchor (§5.4.2) and the Key Takeaways pair-similarity check (§5.12). Match the model the SIE module uses for embedding consistency.
- The brand voice card is the only LLM-distilled artifact persisted to the run record. Persist the full card (not just a hash) so editors can audit the basis for tone decisions on a per-run basis.
- Step 3.5a and 3.5b are independent and parallelizable. Do not block 3.5b on 3.5a's output — both consume the raw `brand_guide_text`.
- Section writing is sequential due to term-budget state (later sections see remaining term budget after earlier sections). Do NOT parallelize H2 group calls.
- The topic-adherence filter (§5.4.2) and the Key Takeaways generation (§5.12) both rely on embeddings. Batch embedding calls where possible to reduce per-article API overhead.
- The defense-in-depth title-case pass (§5.18) is the last operation that mutates `article[]` content. The serializers (§5.19) must run AFTER this pass and must NOT mutate `article[]`.
- The output `article_markdown` is what the platform's Publish module ships to the Google Docs Apps Script webhook. Validate the Markdown renders cleanly in Google Docs preview before declaring the run complete.
- The `article_html` field is consumed by direct paste into WordPress / Google Docs visual editor. Validate against the WordPress code block + visual editor flow specifically — both must produce readable rich text.

---

## 16. Companion Documents (bundle alongside this PRD)

If the implementing team is building the full Blog Writer pipeline (not just the Writer), hand over these sibling PRDs alongside this document. They are required to implement Inputs A/B/C/D and to integrate the downstream renderer.

| Module | File | Canonical version | Why bundle |
|---|---|---|---|
| Content Brief Generator | `docs/modules/content-brief-generator-prd-v2_0.md` | 2.3 | Produces Input A. The Writer's H1 verbatim contract, `intent_format_template`-driven body-length floors, H2 embeddings, authority-gap H3 tagging, FAQ generation, and title-case normalization all originate here. |
| SIE Term & Entity Module | `docs/modules/SIE_PRD_Term_Entity_Module.md` | latest | Produces Input C. Required/avoid term lists, per-zone usage recommendations, target-keyword floors, entity categorization with `is_entity` flag and `recommendation_score`. |
| Research & Citations | `docs/modules/research-citations-module-prd-v1_1_1.md` | 1.1.1 | Produces Input B. Verified citation pool, `extraction_method` semantics (`verbatim_extraction` vs `fallback_stub`), `citation_id` regex contract, `relevance_score`. |
| Sources Cited | `docs/modules/sources-cited-module-prd-v1_1.md` | 1.1 | Consumes Writer output. Defines the `{{cit_N}}` marker discovery, first-appearance numbering, `<sup><a>` substitution, MLA-derived bibliography, `rel="nofollow"` rules. |
| Content Quality PRD | `docs/content-quality-prd-v1_0.md` | 1.0 | Cross-cutting requirements R1–R7 (topic adherence, paragraph length, citable-claim coverage, brand mention budget, required structural elements). The Writer encodes these. |
| Suite Architecture & Roadmap | `docs/suite-architecture-and-roadmap-v1_0.md` | 1.0 | The locked decision log (LLM provider, embeddings provider, SERP source, GSC auth, publish destination). Resolves ambiguity when this PRD references a "platform-level choice." |
| Engineering Implementation Spec | `docs/engineering-implementation-spec-v1_1.md` | 1.1 | Service topology (Railway private network), Supabase schema, `async_jobs` queueing pattern, logging conventions, error envelope, authentication boundary. The infrastructure substrate this module runs on. |

The Writer PRD intentionally does not duplicate content from those documents. Where this PRD says "see Brief PRD" or "consumed by Sources Cited," the implementing team needs the actual sibling document open.

---

## 17. LLM Call Inventory (Anthropic Claude)

Provider: **Anthropic Claude** (locked per suite roadmap). All structured-output calls use **tool use** for guaranteed-valid JSON; prose calls use plain text output. Model IDs assume the Claude 4.X family; substitute newer IDs if available, keeping the size tier (Opus / Sonnet / Haiku).

| # | Call | Model | Output mode | Max tokens (output) | Temperature | Retries on malformed |
|---|---|---|---|---|---|---|
| 1 | Title generation (3 candidates) | `claude-haiku-4-5` | tool use (JSON) | 512 | 0.7 | 1 (then fallback `"{keyword} — A Complete Guide"`) |
| 2 | Brand voice distillation | `claude-sonnet-4-6` | tool use (JSON) | 2,048 | 0.2 | 1 (then abort `brand_distillation_failed`) |
| 3 | Brand–SIE term reconciliation | `claude-sonnet-4-6` | tool use (JSON) | 2,048 | 0.2 | 1 (then abort `brand_reconciliation_failed`) |
| 4 | Intro construction (Agree/Promise/Preview) | `claude-sonnet-4-6` | tool use (JSON, 3 string blocks) | 512 | 0.5 | 1 (then deterministic truncate/collapse, never abort) |
| 5 | Section writing (per H2 group) | `claude-sonnet-4-6` | plain text (Markdown) | 1,500 (group-budget-scaled) | 0.6 | 1 on retry directives (coverage, length, banned-term, paragraph) |
| 6 | FAQ writing | `claude-sonnet-4-6` | tool use (JSON: `[{question, answer}]`) | 2,048 | 0.5 | 1 |
| 7 | Conclusion writing | `claude-sonnet-4-6` | plain text (Markdown) | 512 | 0.5 | 1 |
| 8 | CTA writing | `claude-haiku-4-5` | tool use (JSON: `{cta}`) | 128 | 0.4 | 1 (then truncate, flag `cta_truncated`) |
| 9 | Key Takeaways | `claude-sonnet-4-6` | tool use (JSON: `{takeaways: [...]}`) | 768 | 0.4 | 1 (then accept 3–5 bounds or abort if <3) |
| 10 | ICP callout judge | `claude-haiku-4-5` | tool use (JSON: `{landed, evidence, reasoning}`) | 256 | 0.0 | 0 (failure → `icp_callout_landed = None`) |

**Why these tiers:**
- **Haiku** for short / deterministic / classification calls (title candidates, CTA, judge). Cheap, fast, accurate enough for these shapes.
- **Sonnet** for everything that writes substantive prose (sections, intro, FAQ, conclusion, takeaways) and for structured categorization with reasoning (distillation, reconciliation). The Writer's quality bar requires Sonnet-class output for prose.
- **Opus** is **not** used in v1 because Sonnet quality is sufficient and the article-level budget ceiling ($0.75) doesn't accommodate Opus on the 6-section-writing critical path.

**Tool use contract for JSON calls:** Define a single tool per call with a strict schema. Request `tool_choice: {type: "tool", name: "..."}` so Claude is forced to invoke it. This eliminates the malformed-JSON failure mode in steady state — retries are reserved for content-validity failures (over word count, banned term match, etc.), not parse failures.

**Streaming:** Not required. Section writing benefits from streaming if the platform surfaces progressive UI, but the Writer's metadata-construction passes need the full body before they run, so streaming is consumer-facing only.

**Rate limiting + retries on transient errors:** Outside this PRD's scope — handled by the platform-api HTTP client layer (`httpx` with retry policy on 429 / 5xx).

---

## 18. Prompt Scaffolds

These are skeletons, not production prompts. They lock in the structural contract — what each call receives and what it must return — leaving phrasing details to implementation. Production prompts will be longer (system prompt boilerplate, output-shape examples, tone guidance) but must preserve these contracts.

### 18.1 Title generation (Call #1)

**System:** You are a content strategist producing SEO-optimized blog post titles.

**User:**
```
Generate 3 candidate titles for a blog post.

Seed keyword: {brief.keyword}
Intent type: {brief.intent_type}
Required SIE terms (top 10 by recommendation_score): {sie.terms.required[:10]}
High-salience entities: {sie.entities[:5]}

Rules:
- Every title MUST contain the seed keyword verbatim.
- Title tone by intent: how-to → "How to …" / "How [Audience] Can …"; listicle → leads with a number; comparison → includes "vs." or "or"; everything else → declarative, value-led.
- Incorporate as many high-scoring Required terms / entities as fit naturally. Keyword + entity coverage takes priority over brevity.
- Avoid clickbait, superlatives ("best", "ultimate"), and questions.

Return via the `submit_titles` tool with three candidates.
```

**Tool schema:**
```json
{
  "name": "submit_titles",
  "input_schema": {
    "type": "object",
    "required": ["candidates"],
    "properties": {
      "candidates": {
        "type": "array",
        "minItems": 3,
        "maxItems": 3,
        "items": {"type": "string", "maxLength": 120}
      }
    }
  }
}
```

Selection: deterministic post-LLM. Score each candidate by `(keyword_present ? 1 : 0) + count(required_terms ∩ title) + count(entities ∩ title)`. Highest score wins; tie-break shortest.

### 18.2 Brand voice distillation (Call #2)

**System:** You categorize and summarize brand guidance. You do not invent brand preferences not present in the source text.

**User:**
```
Extract a structured brand voice card from the following inputs.

Brand guide text:
"""
{brand_guide_text}
"""

ICP text:
"""
{icp_text}
"""

Website analysis (factual reference only):
- Services: {website_analysis.services}
- Locations: {website_analysis.locations}
- Contact: {website_analysis.contact_info}

Rules:
- Tone adjectives come ONLY from the brand guide text. Do not supplement from website data.
- A term is `banned` only when the brand guide explicitly prohibits it. `discouraged` if expressed against without explicit prohibition. `preferred` if explicitly named as preferred phrasing.
- All term lists must be terms or phrases that appear in or are explicitly named by the source text. Return [] if the brand guide doesn't address term-level guidance.
- Audience pain points, goals, and verticals come from the ICP text.
- Website services/locations/contact carry verbatim into the card.

Return via `submit_brand_voice_card`.
```

Tool schema mirrors §5.5 output exactly. Field limits (e.g., `max_items: 30` on banned_terms) are enforced in the schema.

### 18.3 Brand–SIE reconciliation (Call #3)

**System:** You classify SIE term recommendations against a brand guide. Every non-`keep` classification must cite specific brand-guide text.

**User:**
```
Brand guide:
"""
{brand_guide_text}
"""

SIE Required terms (must classify each):
{sie.terms.required}

SIE Avoid terms (must classify each):
{sie.terms.avoid}

For each Required term, classify as:
- `keep` (no brand conflict)
- `exclude_due_to_brand_conflict` (brand explicitly bans)
- `reduce_due_to_brand_preference` (brand discourages without explicit ban)

For each Avoid term, classify as:
- `keep_avoiding` (no brand preference)
- `use_due_to_brand_preference` (brand explicitly prefers)

Brand always wins. Every non-`keep` and non-`keep_avoiding` classification MUST include `brand_guide_reasoning` quoting the specific brand-guide text (≤300 chars).

Return via `submit_reconciliation`.
```

### 18.4 Intro construction (Call #4)

**System:** You write blog post introductions in a strict three-beat structure.

**User:**
```
Write the article's introduction as a single paragraph (60–150 words) in three beats:

1. Agree (≤50 words) — name the reader's situation in their own language. Anchor in the ICP when provided. Do not name the brand. Do not begin with the seed keyword.
2. Promise (≤50 words) — state what this article will deliver, anchored in the title and scope. May reference the seed keyword once. No CTA.
3. Preview (≤50 words) — name 2–4 of the H2 sections in order. Plain language. No bullets. No verbatim heading list.

Inputs:
- Title: {output.title}
- Scope: {brief.scope_statement}
- Intent: {brief.intent_type}
- ICP summary: {brand_voice_card.audience_summary}
- H2 list (post-adherence filter, in order): {[h.text for h in kept_h2s]}
- Brand voice block: {brand_voice_card.tone_adjectives + voice_directives}
- Banned terms (must not appear): {brand_voice_card.banned_terms + filtered_sie_excluded}

Return the three blocks via `submit_intro`.
```

**Tool schema:**
```json
{
  "name": "submit_intro",
  "input_schema": {
    "type": "object",
    "required": ["agree", "promise", "preview"],
    "properties": {
      "agree":   {"type": "string", "maxLength": 350},
      "promise": {"type": "string", "maxLength": 350},
      "preview": {"type": "string", "maxLength": 350}
    }
  }
}
```

Post-LLM, the three blocks are joined into a single paragraph with a single space between them and validated per §5.3.

### 18.5 Section writing (Call #5, runs N times)

**System:** You are a senior content writer producing SEO-optimized prose for a specific brand voice and audience.

**User (per H2 group):**
```
Write the following H2 group in Markdown. Output ONLY the section content — no preamble, no postamble, no commentary.

H2 heading: {h2.text}
H3 children (write each in order if present): {[h3.text for h3 in h2.children]}
Word budget for this group: {section_budget}
Intent type: {brief.intent_type}
Intent pattern: {intent_format_template.h2_pattern}

--- Brand & Audience ---
Tone: {brand_voice_card.tone_adjectives}
Voice directives:
{brand_voice_card.voice_directives}
Audience: {brand_voice_card.audience_summary}
Pain points to acknowledge where natural: {brand_voice_card.audience_pain_points}

--- Client context (use only where natural) ---
Services: {brand_voice_card.client_services}
Locations: {brand_voice_card.client_locations}
{must_mention_brand directive if anchor}
{must_not_mention_brand directive if non-anchor}
{icp_callout_hook directive if ICP anchor}

--- Citations available for this section ---
{for cit in resolved_citations:}
  - {{cit.citation_id}} — extraction_method: {cit.extraction_method}
    Verified claims:
      {for claim in cit.claims if claim.relevance_score >= 0.5:}
        - "{claim.claim_text}"
{end}

Citation rules:
- For each specific factual assertion sourced from a citation, place its marker immediately after the closing punctuation: `Demand climbed 18% in Q3.{{cit_007}}`
- Multiple citations in one sentence: stack with no spaces: `{{cit_001}}{{cit_004}}`
- Markers ONLY in body, NEVER in headings.
- `fallback_stub` citations: do not assert specific figures from the stub claim. You may reference the publication as supporting context ("according to [publication]…"), but no statistics, prices, or specific facts from the stub.

--- Format rules ---
- First sentence of the H2 body MUST directly answer the heading in ≤25 words.
- Maximum 4 sentences per paragraph; 3 preferred.
- {if format_directives.require_bulleted_lists: "Include at least one bulleted or numbered list across the H2 group."}
- {if format_directives.require_tables: "Include at least one Markdown table across the H2 group."}

--- Term targets ---
Required terms (with per-zone usage targets):
{for term in filtered_sie_terms.required scoped to this section:}
  - "{term.term}" — h2: {term.effective_target}, h3: {term.effective_target}, paragraph: {term.effective_target} (max {term.effective_max})
{end}

Excluded terms (do not use — brand or SIE conflict):
{filtered_sie_terms.excluded + brand_voice_card.banned_terms + filtered_sie_terms.avoid}

Output format:
```
## {h2.text}
{H2 body, with H3 subsections as needed:}
### {h3.text}
{H3 body}
```
```

For retry directives:
- **Coverage retry** (§5.8.8): prepend `COVERAGE_RETRY: The following sentences contain claims requiring citation but were emitted without markers: [list sentences]. Either append a {{cit_N}} marker from the available pool above, OR rewrite the sentence to remove the specific statistic / year / brand attribution.`
- **Length retry** (§5.10): prepend `LENGTH_RETRY: This H2 group came in at {current_word_count} words but the minimum substance floor for this intent is {floor} words. Add additional substance — facts, examples, evidence — NOT padding or filler. Re-emit the entire H2 group.`
- **Paragraph retry** (§5.9): prepend `PARAGRAPH_RETRY: Paragraph {n} contains {sentence_count} sentences; the cap is {max_sentences}. Split it on a logical break. Re-emit the entire section.`
- **Banned-term retry** (§5.17): prepend `BANNED_TERM_RETRY: The output contained "{term}" which is banned by client brand guidance. Rewrite the section without using "{term}" or any variant. Substitutions are at your discretion; preserve meaning.`

### 18.6 FAQ writing (Call #6)

**System:** You write self-contained FAQ answers optimized for LLM citation extraction.

**User:**
```
Write answers to the following FAQ questions. Each answer must be 40–80 words, answer-first, self-contained (a reader must understand the answer without reading the rest of the article).

Questions (in order):
{for faq in brief.faqs:}
  {faq.order}. {faq.question}
{end}

Rules:
- Answer-first: first sentence directly addresses the question.
- Self-contained: NO "as mentioned above" or other cross-references.
- The seed keyword "{brief.keyword}" (or its primary sub-phrase) must appear in at least 2 answers across the set.
- Respect brand voice ({brand_voice_card.tone_adjectives}) and banned terms ({brand_voice_card.banned_terms + filtered_sie_excluded}).
- ICP framing: questions and answers should reflect how {brand_voice_card.audience_summary} would actually ask, not generic SEO phrasing.

Return via `submit_faqs`.
```

### 18.7 Conclusion (Call #7)

```
Write the article's conclusion in 100–150 words.

Rules:
- 2–3 sentences synthesizing the article's core takeaways.
- The seed keyword "{brief.keyword}" must appear at least once.
- Do NOT include a CTA — the CTA is rendered as a separate element after this paragraph.
- Do NOT introduce new information not covered in the article body.
- {if brand_voice_card.client_services exists: "May include a natural closing sentence referencing the client's services where contextually relevant. Never a hard sales pitch."}
- Brand voice: {tone_adjectives + voice_directives}.
- Banned terms: {banned_terms + filtered_sie_excluded}.

Output plain prose (no Markdown headers).
```

### 18.8 CTA (Call #8)

```
Write a single-sentence call-to-action, ≤30 words.

Rules:
- Must name a specific next action (read, download, contact, evaluate, compare, sign up, request, schedule, audit, review).
- {if icp_text provided: "Draw the next-step verb from the audience's stated goals: " + audience_goals}
- {else: use the intent-appropriate template:}
  - how-to: "Try these steps in your next [task] and measure the result."
  - informational: "Explore [related sub-topic] next."
  - comparison: "Run this comparison against your current [solution category] to see where the trade-offs land for your team."
  - local-seo / ecom / informational-commercial: "When you're ready to evaluate options, look for [criterion drawn from article]."
  - news: "Watch for follow-on coverage as the situation develops."
- Hard-sales phrases BANNED: "buy now", "purchase now", "limited time", "act today".

Article title (for context): {output.title}

Return via `submit_cta`.
```

### 18.9 Key Takeaways (Call #9)

```
Produce 3–5 key takeaways summarizing the assembled article below.

Rules:
- Each takeaway is a single standalone sentence, ≤25 words.
- Each takeaway must be self-contained — readable without the surrounding article.
- Facts or actionable claims only. No opinion, no marketing language, no rhetorical questions.
- Takeaways must not repeat each other.
- Brand mentions count against the brand-mention budget.

Article title: {output.title}

Assembled article body:
"""
{full_article_body_excluding_intro_and_h1}
"""

Return via `submit_takeaways`.
```

Post-LLM: cosine pairwise check (≥0.85 → regenerate offending pair); per-takeaway word count check (>25 → retry once with limit named).

### 18.10 ICP callout judge (Call #10)

```
Did the following article section land an audience-specific callout for the named ICP hook?

Hook to look for: "{icp_hook_phrase}"
Audience pain points (for synonym recognition): {audience_pain_points}
Audience verticals: {audience_verticals}

Section body (truncated to 4,000 chars):
"""
{anchor_section.body[:4000]}
"""

Rules:
- Paraphrases of the hook count as landed ("margin erosion from refunds" ≈ "shrinking unit economics on returned orders").
- A generic acknowledgment of "the audience" does not count — the callout must name the specific pain point or vertical.
- When landed, return a verbatim quote (≤200 chars) as evidence.

Return via `submit_judgment`.
```

Tool schema:
```json
{
  "name": "submit_judgment",
  "input_schema": {
    "type": "object",
    "required": ["landed", "reasoning"],
    "properties": {
      "landed":    {"type": "boolean"},
      "evidence":  {"type": "string", "maxLength": 200},
      "reasoning": {"type": "string", "maxLength": 280}
    }
  }
}
```

---

## 19. Closures (the loose ends the contract depends on)

### 19.1 Embeddings

| Use site | Model | Dimensionality | Threshold |
|---|---|---|---|
| Title topic anchor (§5.4.2 H2 adherence filter) | `text-embedding-3-small` | 1,536 | cosine ≥ 0.62 to keep |
| Brand-aligned vs brand-agnostic determination | `text-embedding-3-small` | 1,536 | cosine ≥ 0.55 to title = `brand_aligned` |
| Key Takeaways pair similarity (§5.12) | `text-embedding-3-small` | 1,536 | cosine ≥ 0.85 → regenerate pair |

Calibrated against `text-embedding-3-small`'s vector space. A different embedding model requires recalibration of these thresholds (the values are not portable across providers).

### 19.2 Tech stack assumptions baked into this spec

| Layer | Choice | Why it matters |
|---|---|---|
| Language | Python 3.11+ | Regex semantics (`re.IGNORECASE`, `\b` Unicode handling), `titlecase` library availability |
| Web framework | FastAPI | Pydantic models for input/output validation; `BackgroundTasks` for async work without Celery |
| HTTP client | `httpx` (async) | Anthropic SDK is async-friendly; concurrent embedding batches |
| Title-case library | `titlecase==2.4.1` | Pinned to match Brief Generator's exact behavior. Different versions produce different casing on edge cases ("vs." vs "Vs.", "iPhone" preservation). |
| Anthropic SDK | `anthropic>=0.40` | Tool use, claude-4.x model support |
| OpenAI SDK | `openai>=1.0` | For embeddings only |

If the other app uses Node/TypeScript: the title-case library equivalent is [`titlecase-js`](https://www.npmjs.com/package/titlecase) (validate behavior parity on the heading test corpus before declaring equivalent). Regex `\b` semantics are equivalent. The embedding and Anthropic SDKs have first-party JS clients.

### 19.3 Complete enum lists

**`intent_type`** (8 values, from Brief PRD):
`informational`, `listicle`, `how-to`, `comparison`, `ecom`, `local-seo`, `news`, `informational-commercial`

**`heading_structure[].level`** (4 values):
`H1`, `H2`, `H3`, `none`

**`heading_structure[].type`** (4 values):
`content`, `faq-header`, `faq-question`, `conclusion`

**`heading_structure[].source`** (3 values):
`serp_derived`, `authority_gap_sme`, `editorial_added`

**`article[].type`** (9 values):
`title`, `content`, `faq-header`, `faq-question`, `conclusion`, `h1-enrichment`, `key-takeaways`, `intro`, `cta`

**`entity_category`** (open-ended; common values): `services`, `equipment`, `problems`, `methods`, `brands`, `tools`, `audiences`, `locations`, `concepts`, `regulations`

**`citations[].extraction_method`** (2 values): `verbatim_extraction`, `fallback_stub`

**`citations[].verification_method`** (3 values): `claim_in_extracted_text`, `entity_overlap`, `stub_acknowledgment`

**Reconciliation actions** (Required terms): `keep`, `exclude_due_to_brand_conflict`, `reduce_due_to_brand_preference`
**Reconciliation actions** (Avoid terms): `keep_avoiding`, `use_due_to_brand_preference`

**`brand_conflict_log[].resolution`** (3 values): `exclude_due_to_brand_conflict`, `reduce_due_to_brand_preference`, `brand_preference_overrides_sie_avoid`

**`brand_mention_flags`** (3 values): `zero_brand_mentions_on_brand_aligned_topic`, `brand_mentions_exceed_target`, `brand_mentions_exceed_hard_cap`

**`topic_brand_alignment`** (2 values): `brand_aligned`, `brand_agnostic`

**`icp_callout_judge_status`** (5 values): `ok`, `anchor_not_in_article`, `empty_body`, `llm_failure`, `not_assigned`

**`schema_version`** valid values: `1.7`, `1.7-no-context`, `1.7-degraded`, `1.7-legacy-h1`

### 19.4 SIE field `is_entity`

`sie.terms.required[*].is_entity` is a boolean indicating whether the term is a Named Entity Recognition (NER)-recognized entity (organization, product, person, location) as opposed to a generic noun phrase. Pattern C6 (§5.8.8) requires this field: a sentence is citable under C6 if it contains an entity name where `is_entity == true` AND a quantitative or temporal qualifier from C1–C3. The SIE module produces this flag during entity merge.

### 19.5 First-party domain extraction (§5.8.8)

When multiple citation candidates exist for a single claim, prefer the citation whose URL domain matches the entity named in the claim sentence:

```python
from urllib.parse import urlparse

def extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    # Strip "www." prefix
    return netloc[4:] if netloc.startswith("www.") else netloc

# Match: entity "Shopify" → prefer citation where extract_domain(cit.url) contains "shopify"
def is_first_party(citation_url: str, entity_name: str) -> bool:
    domain = extract_domain(citation_url)
    entity_normalized = entity_name.lower().replace(" ", "")
    return entity_normalized in domain.replace(".", "").replace("-", "")
```

### 19.6 Error envelope (wire format)

All structured errors returned by the Writer conform to:

```json
{
  "error": {
    "code": "string (snake_case, from the failure-mode table §7)",
    "message": "human-readable summary",
    "details": {
      "stage": "step name (e.g., 'step_3_5a_distillation', 'step_4_section_writing')",
      "h2_order": 4,
      "field": "article[4].body",
      "snippet": "≤200-char excerpt of offending content",
      "expected": "string or object describing what was expected",
      "actual": "string or object describing what was received"
    },
    "schema_version": "1.7",
    "trace_id": "uuid"
  }
}
```

HTTP status: `400` for input-validation errors (`keyword_mismatch`, `brief_missing_title`, `client_context_validation_error`, schema validation failures, `missing_required_structure`, `key_takeaways_count_invalid`). `422` for content-policy aborts (`banned_term_leakage`, `marker_in_heading`). `500` for upstream LLM exhaustion (`brand_distillation_failed`, `brand_reconciliation_failed`, `intro_generation_failed`). `504` for `generation_timeout`.

### 19.7 Logging payload

All log lines are structured JSON. Required fields on every log line:

```json
{
  "ts": "2026-06-06T18:23:14.482Z",
  "level": "INFO | WARN | ERROR",
  "event": "writer.coverage.retry",
  "run_id": "uuid",
  "request_id": "uuid",
  "module": "writer",
  "schema_version": "1.7"
}
```

Event-specific payloads add fields. For the events named in this PRD:

| Event | Additional fields |
|---|---|
| `writer.coverage.complete` | `groups_inspected`, `retries_attempted`, `retries_succeeded`, `sections_softened`, `under_cited_remaining` |
| `writer.coverage.retry` | `section_order`, `h2_order`, `citable_claims`, `cited_claims`, `ratio` |
| `writer.coverage.retry_succeeded` | `section_order`, `before_ratio`, `after_ratio` |
| `writer.coverage.under_cited_after_retry` | `section_order`, `final_ratio`, `softened_count` |
| `writer.h2_length.retry` | `section_order`, `word_count`, `floor` |
| `writer.h2_length.retry_succeeded` | `section_order`, `before_words`, `after_words`, `floor` |
| `writer.h2_length.retry_still_under` | `section_order`, `final_words`, `floor` |
| `banned_term_leakage` (when retry succeeds, logged but not surfaced) | `term`, `field`, `snippet`, `recovered_via_retry: true` |
| `title_case_round_trip_failed` (rare safety-net failure) | `level`, `text`, `expected` |
| `serializer_unknown_citation` | `citation_id`, `position` |

Never log: JWTs, full brand guide text, API keys, user passwords. Log brand-guide *snippets* (≤200 chars) only when explicitly required for an error envelope.

### 19.8 Determinism and seeding

The Writer is **not** required to be bit-exact reproducible across runs (LLM stochasticity). It IS required to be deterministic in:

- Title selection (post-LLM scoring + tie-break).
- Word budget allocation.
- Topic-adherence filter (embedding cosine + 0.62 threshold).
- Brand & ICP placement plan (token-set scoring + lowest-order tie-break).
- Citable-claim detection regex passes (C1–C9).
- Auto-soften lookups.
- Title-case pass (idempotent).
- Markdown / HTML serialization.

Two runs with identical inputs and identical Anthropic + OpenAI seeds (when set) MUST produce identical metadata fields, identical placement decisions, and identical serializer output. Prose body content may differ.

---

## 20. Golden Example (end-to-end walkthrough)

A minimal but shape-complete example. Article topic: **"How to Pick Project Management Software for Small Teams"** (intent: `informational-commercial`). Hypothetical client: **Tessera Studios**, a 12-person operations consulting firm.

Truncated to fit: 3 content H2s + conclusion, 3 FAQs, 5 citations. Body prose elided with `[...]` for length. The shape of every required field is shown.

### 20.1 Input A — Brief

```json
{
  "schema_version": "2.3",
  "keyword": "project management software for small teams",
  "title": "How to Pick Project Management Software for Small Teams",
  "scope_statement": "A buyer's-education guide for ops leaders at 10–50-person teams choosing their first project management tool. Covers selection criteria, common pitfalls, and migration steps. Excludes feature-by-feature competitive matrices and enterprise / 500+ seat tooling.",
  "intent_type": "informational-commercial",
  "intent_format_template": {
    "h2_pattern": "buyer_education_axes",
    "h2_framing_rule": "evaluation_criterion_or_decision_factor",
    "ordering": "natural_decision_sequence",
    "min_h2_count": 4,
    "max_h2_count": 7,
    "anchor_slots": ["selection_criteria", "common_pitfalls", "migration_steps"]
  },
  "heading_structure": [
    {"order": 0, "level": "H1", "type": "content", "text": "How to Pick Project Management Software for Small Teams", "citation_ids": []},
    {"order": 1, "level": "H2", "type": "content", "text": "What to Evaluate Before You Compare Tools", "source": "serp_derived", "citation_ids": ["cit_001", "cit_002"], "embedding": [0.0123, -0.0456, "..."]},
    {"order": 2, "level": "H3", "type": "content", "text": "How to Tell If You Actually Need One Yet", "source": "authority_gap_sme", "citation_ids": ["cit_003"]},
    {"order": 3, "level": "H2", "type": "content", "text": "Common Mistakes Small Teams Make When Choosing PM Software", "source": "serp_derived", "citation_ids": ["cit_002", "cit_004"], "embedding": [0.0234, -0.0345, "..."]},
    {"order": 4, "level": "H2", "type": "content", "text": "How to Migrate Your Team to a New PM Tool", "source": "serp_derived", "citation_ids": ["cit_005"], "embedding": [0.0345, -0.0234, "..."]},
    {"order": 5, "level": "H2", "type": "faq-header", "text": "Frequently Asked Questions", "citation_ids": []},
    {"order": 6, "level": "H3", "type": "faq-question", "text": "How much should a small team spend on project management software?", "citation_ids": []},
    {"order": 7, "level": "H3", "type": "faq-question", "text": "Is free project management software good enough for a startup?", "citation_ids": []},
    {"order": 8, "level": "H3", "type": "faq-question", "text": "How long does it take to roll out PM software to a 20-person team?", "citation_ids": []},
    {"order": 9, "level": "H2", "type": "conclusion", "text": "", "citation_ids": []}
  ],
  "faqs": [
    {"order": 0, "question": "How much should a small team spend on project management software?", "faq_score": 0.84, "intent_role": "matches_primary_intent"},
    {"order": 1, "question": "Is free project management software good enough for a startup?", "faq_score": 0.79, "intent_role": "matches_primary_intent"},
    {"order": 2, "question": "How long does it take to roll out PM software to a 20-person team?", "faq_score": 0.71, "intent_role": "adjacent_intent"}
  ],
  "format_directives": {
    "require_bulleted_lists": true,
    "require_tables": true,
    "min_lists_per_article": 1,
    "min_tables_per_article": 1,
    "answer_first_paragraphs": true,
    "max_sentences_per_paragraph": 4,
    "min_h2_body_words": 180
  },
  "metadata": {
    "word_budget": 2500,
    "h2_count": 4,
    "h3_count": 1,
    "schema_version": "2.3"
  }
}
```

### 20.2 Input B — Research & Citations

```json
{
  "schema_version": "1.1",
  "keyword": "project management software for small teams",
  "citations": [
    {
      "citation_id": "cit_001",
      "url": "https://www.gartner.com/en/articles/picking-pm-software-2024",
      "title": "Picking PM Software in 2024: A Buyer's Guide",
      "publication": "Gartner",
      "author": "Gartner Research",
      "published_date": "2024-03-12",
      "extraction_method": "verbatim_extraction",
      "verification_method": "claim_in_extracted_text",
      "claims": [
        {"claim_text": "62% of teams under 50 employees report dissatisfaction with their first PM tool within 18 months.", "relevance_score": 0.91, "extraction_method": "verbatim_extraction", "verification_method": "claim_in_extracted_text"},
        {"claim_text": "The top three evaluation criteria cited by small teams are price, learning curve, and integration with existing tools.", "relevance_score": 0.87, "extraction_method": "verbatim_extraction", "verification_method": "claim_in_extracted_text"}
      ]
    },
    {
      "citation_id": "cit_002",
      "url": "https://hbr.org/2023/09/the-real-cost-of-tool-sprawl",
      "title": "The Real Cost of Tool Sprawl",
      "publication": "Harvard Business Review",
      "author": "Jane Doe",
      "published_date": "2023-09-04",
      "extraction_method": "verbatim_extraction",
      "verification_method": "claim_in_extracted_text",
      "claims": [
        {"claim_text": "Small companies adopting more than 4 SaaS productivity tools see a 23% drop in task-completion velocity within 6 months.", "relevance_score": 0.78, "extraction_method": "verbatim_extraction", "verification_method": "claim_in_extracted_text"}
      ]
    },
    {
      "citation_id": "cit_003",
      "url": "https://www.atlassian.com/blog/teamwork/when-to-adopt-pm-tools",
      "title": "When Does a Small Team Actually Need PM Software?",
      "publication": "Atlassian",
      "author": "Atlassian Work Futures Team",
      "published_date": "2024-01-22",
      "extraction_method": "verbatim_extraction",
      "verification_method": "claim_in_extracted_text",
      "claims": [
        {"claim_text": "Teams smaller than 5 people typically outgrow shared spreadsheets when they hit 3 concurrent multi-week projects.", "relevance_score": 0.82, "extraction_method": "verbatim_extraction", "verification_method": "entity_overlap"}
      ]
    },
    {
      "citation_id": "cit_004",
      "url": "https://www.forrester.com/report/the-pm-software-adoption-trap",
      "title": "The PM Software Adoption Trap",
      "publication": "Forrester",
      "author": "Forrester Analytics",
      "published_date": "2023-11-30",
      "extraction_method": "fallback_stub",
      "verification_method": "stub_acknowledgment",
      "claims": [
        {"claim_text": "[stub: original page returned 403; URL preserved as source acknowledgment only]", "relevance_score": 0.55, "extraction_method": "fallback_stub", "verification_method": "stub_acknowledgment"}
      ]
    },
    {
      "citation_id": "cit_005",
      "url": "https://www.shopify.com/research/team-tool-migration-playbook",
      "title": "Team Tool Migration Playbook",
      "publication": "Shopify Research",
      "author": "Shopify Operations Team",
      "published_date": "2024-02-14",
      "extraction_method": "verbatim_extraction",
      "verification_method": "claim_in_extracted_text",
      "claims": [
        {"claim_text": "A staged migration over 4–6 weeks reduces tool-abandonment risk by 41% compared to a single-day cutover.", "relevance_score": 0.89, "extraction_method": "verbatim_extraction", "verification_method": "claim_in_extracted_text"}
      ]
    }
  ]
}
```

### 20.3 Input C — SIE

```json
{
  "schema_version": "1.4",
  "keyword": "project management software for small teams",
  "word_count": {"target": 2400, "min": 2000, "max": 2800},
  "target_keyword": {
    "term": "project management software",
    "minimum_usage": {"h2": 0, "h3": 0, "paragraphs": 6}
  },
  "terms": {
    "required": [
      {"term": "project management software", "recommendation_score": 0.98, "is_entity": false, "entity_category": null},
      {"term": "small teams", "recommendation_score": 0.92, "is_entity": false, "entity_category": null},
      {"term": "task management", "recommendation_score": 0.78, "is_entity": false, "entity_category": "methods"},
      {"term": "integrations", "recommendation_score": 0.74, "is_entity": false, "entity_category": "methods"},
      {"term": "Asana", "recommendation_score": 0.71, "is_entity": true, "entity_category": "brands"},
      {"term": "Trello", "recommendation_score": 0.68, "is_entity": true, "entity_category": "brands"},
      {"term": "ClickUp", "recommendation_score": 0.66, "is_entity": true, "entity_category": "brands"},
      {"term": "user adoption", "recommendation_score": 0.63, "is_entity": false, "entity_category": "problems"}
    ],
    "avoid": ["best-in-class", "synergy"]
  },
  "usage_recommendations": [
    {"term": "project management software", "h2": {"min": 0, "target": 1, "max": 2}, "h3": {"min": 0, "target": 0, "max": 1}, "paragraphs": {"min": 6, "target": 8, "max": 12}},
    {"term": "small teams", "h2": {"min": 0, "target": 1, "max": 2}, "h3": {"min": 0, "target": 0, "max": 1}, "paragraphs": {"min": 3, "target": 5, "max": 8}},
    {"term": "task management", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 1}, "paragraphs": {"min": 1, "target": 2, "max": 4}},
    {"term": "integrations", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 1}, "paragraphs": {"min": 1, "target": 2, "max": 4}},
    {"term": "Asana", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 0}, "paragraphs": {"min": 0, "target": 1, "max": 2}},
    {"term": "Trello", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 0}, "paragraphs": {"min": 0, "target": 1, "max": 2}},
    {"term": "ClickUp", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 0}, "paragraphs": {"min": 0, "target": 1, "max": 2}},
    {"term": "user adoption", "h2": {"min": 0, "target": 0, "max": 1}, "h3": {"min": 0, "target": 0, "max": 0}, "paragraphs": {"min": 0, "target": 1, "max": 3}}
  ],
  "entities": [
    {"term": "Asana", "entity_category": "brands", "example_context": "task and project management tool from Asana, Inc.", "ner_variants": ["Asana"], "recommendation_score": 0.71},
    {"term": "Trello", "entity_category": "brands", "example_context": "Kanban-style PM tool acquired by Atlassian", "ner_variants": ["Trello"], "recommendation_score": 0.68},
    {"term": "ClickUp", "entity_category": "brands", "example_context": "all-in-one PM platform", "ner_variants": ["ClickUp"], "recommendation_score": 0.66}
  ]
}
```

### 20.4 Input D — Client Context (Tessera Studios)

```json
{
  "client_context": {
    "brand_guide_text": "Tessera Studios is an operations consulting firm. Voice: plainspoken, confident, anti-jargon. We refuse marketing-speak. BANNED TERMS: synergy, leverage (as a verb), best-in-class, robust, seamless, world-class. PREFERRED PHRASING: 'clear', 'concrete', 'outcomes', 'in practice'. We address readers as peers, not as students. We never use 'imagine if', 'picture this', or 'in today's fast-paced world'. We open every piece by naming the problem, not by setting a scene.",
    "icp_text": "Our readers are operations leaders at 10-50 person teams — founders, ops managers, head-of-ops, COO at companies past PMF but before Series B. They're under-resourced, allergic to fluff, and have to defend every tool purchase to a skeptical founder or board. They've already tried at least one PM tool and abandoned it. Pain points: tool fatigue, team adoption failures, hidden migration costs, and the gap between vendor demos and daily reality. Goals: pick something that survives 18 months, doesn't require a dedicated admin, and integrates with their existing Slack + GSuite stack.",
    "website_analysis": {
      "services": ["operations consulting", "tool stack audits", "team workflow design"],
      "locations": ["Brooklyn, NY"],
      "tone": [],
      "positioning": ""
    },
    "website_analysis_unavailable": false
  }
}
```

### 20.5 Output (Writer JSON)

```json
{
  "keyword": "project management software for small teams",
  "intent_type": "informational-commercial",
  "title": "How to Pick Project Management Software for Small Teams",

  "article": [
    {
      "order": 0,
      "level": "H1",
      "type": "title",
      "heading": "How to Pick Project Management Software for Small Teams",
      "body": null,
      "word_count": 0,
      "section_budget": 0,
      "citations_referenced": []
    },
    {
      "order": 1,
      "level": "none",
      "type": "h1-enrichment",
      "heading": null,
      "body": "A practical guide to evaluation criteria, common pitfalls, and migration for teams of 10–50 already past the spreadsheet stage.",
      "word_count": 22,
      "section_budget": 25,
      "citations_referenced": []
    },
    {
      "order": 2,
      "level": "none",
      "type": "key-takeaways",
      "heading": "Key Takeaways",
      "body": "- Most small teams pick PM software on features and regret it within 18 months.{{cit_001}}\n- Price, learning curve, and integration depth are the three criteria that actually predict retention.{{cit_001}}\n- Adopting more than four overlapping SaaS tools cuts task velocity by nearly a quarter.{{cit_002}}\n- A staged 4–6 week migration cuts abandonment risk by 41% versus a single-day cutover.{{cit_005}}\n- The right test for needing a tool is three concurrent multi-week projects, not headcount.{{cit_003}}",
      "word_count": 78,
      "section_budget": 100,
      "citations_referenced": ["cit_001", "cit_002", "cit_003", "cit_005"]
    },
    {
      "order": 3,
      "level": "none",
      "type": "intro",
      "heading": null,
      "body": "If your team has already tried a project management tool and quietly abandoned it, you're not alone — 62% of small teams report dissatisfaction with their first PM tool within 18 months. This guide gives you the three evaluation criteria that actually predict whether a tool will stick, the mistakes that sink most small-team rollouts, and a staged migration plan that survives contact with daily work. You'll see how to evaluate before you compare tools, the common mistakes small teams make when choosing PM software, and how to migrate your team to a new tool without losing the first month.",
      "word_count": 108,
      "section_budget": 150,
      "citations_referenced": []
    },
    {
      "order": 4,
      "level": "H2",
      "type": "content",
      "heading": "What to Evaluate Before You Compare Tools",
      "body": "Price, learning curve, and integration depth predict whether a project management software pick survives 18 months — features barely matter. According to Gartner, those are the top three evaluation criteria cited by small teams.{{cit_001}} Most buyers invert this and start with feature checklists; that's how they end up with a tool no one logs into by month six. [... ~150 more words covering the three criteria with concrete examples ...]\n\n### How to Tell If You Actually Need One Yet\n\nThe honest test is concurrent project load, not headcount. Atlassian's research found that teams under five people typically outgrow shared spreadsheets when they hit three concurrent multi-week projects.{{cit_003}} If you're running one or two projects at a time, a shared doc and a recurring Friday review will outperform any tool you adopt. [... ~80 more words ...]",
      "word_count": 312,
      "section_budget": 360,
      "citations_referenced": ["cit_001", "cit_003"]
    },
    {
      "order": 5,
      "level": "H2",
      "type": "content",
      "heading": "Common Mistakes Small Teams Make When Choosing PM Software",
      "body": "The most expensive mistake is stacking tools instead of replacing them. Harvard Business Review found that small companies adopting more than four SaaS productivity tools see a 23% drop in task-completion velocity within six months.{{cit_002}} Forrester has covered the same adoption trap in its research on PM tooling.{{cit_004}} [... ~250 words covering: picking on demo polish, ignoring integration depth, skipping the trial team, not naming an admin. Includes a Markdown table of the four mistakes with symptoms and corrections. Mentions Asana, Trello, and ClickUp as examples of feature-rich tools that get over-adopted ...]\n\nFor Tessera Studios clients we've audited, the pattern is consistent: the team picks a tool, two people set it up, three weeks later only one person is logging in, and the tool quietly joins the graveyard of abandoned subscriptions. The fix is naming the admin BEFORE the trial, not after — a concrete person whose job includes onboarding and quarterly cleanup.",
      "word_count": 308,
      "section_budget": 360,
      "citations_referenced": ["cit_002", "cit_004"]
    },
    {
      "order": 6,
      "level": "H2",
      "type": "content",
      "heading": "How to Migrate Your Team to a New PM Tool",
      "body": "Stage the migration over four to six weeks, not in a single weekend. Shopify's operations research found a staged migration cuts tool-abandonment risk by 41% compared to a single-day cutover.{{cit_005}} The cutover-on-Friday plan fails because it asks people to learn new workflows under deadline pressure; the staged plan asks them to learn it during low-stakes work. [... ~220 words covering: pilot team selection, dual-running existing projects, integration setup with Slack and GSuite, training cadence, and the post-cutover cleanup. Includes a bulleted list of week-by-week milestones ...]",
      "word_count": 296,
      "section_budget": 360,
      "citations_referenced": ["cit_005"]
    },
    {
      "order": 7,
      "level": "H2",
      "type": "faq-header",
      "heading": "Frequently Asked Questions",
      "body": null,
      "word_count": 0,
      "section_budget": 0,
      "citations_referenced": []
    },
    {
      "order": 8,
      "level": "H3",
      "type": "faq-question",
      "heading": "How much should a small team spend on project management software?",
      "body": "Small teams should expect to spend $10–$20 per user per month for project management software that handles their workflow without forcing upgrades. Cheaper tools cover task management but often miss the integrations small teams need with Slack, calendar, and document storage. Spending more than $25 per user usually buys enterprise features your team won't use for at least a year.",
      "word_count": 61,
      "section_budget": 0,
      "citations_referenced": []
    },
    {
      "order": 9,
      "level": "H3",
      "type": "faq-question",
      "heading": "Is free project management software good enough for a startup?",
      "body": "Free project management software works for teams under five people running one or two concurrent projects, but breaks down when integrations, permissions, or reporting matter. Most free tiers cap users or projects exactly where small teams start to feel friction. If you're past three concurrent multi-week projects, the time you lose to workarounds usually costs more than the paid tier.",
      "word_count": 62,
      "section_budget": 0,
      "citations_referenced": []
    },
    {
      "order": 10,
      "level": "H3",
      "type": "faq-question",
      "heading": "How long does it take to roll out PM software to a 20-person team?",
      "body": "A 20-person team can roll out project management software in four to six weeks if you stage it properly. Plan one week of admin setup and integrations, two weeks of pilot use with a single team, then a phased rollout to the remaining people over two to three weeks. Single-weekend cutovers technically work but produce a 41% higher abandonment rate.",
      "word_count": 60,
      "section_budget": 0,
      "citations_referenced": []
    },
    {
      "order": 11,
      "level": "H2",
      "type": "conclusion",
      "heading": "",
      "body": "Picking project management software for small teams is a question of fit, not features. Evaluate on price, learning curve, and integration depth before you compare tools; avoid the four mistakes that sink most rollouts; and stage your migration so people learn the new workflow during low-stakes work. Tessera Studios runs tool stack audits with operations teams in exactly this situation — the audit is usually faster than a vendor demo cycle and produces a tool list your team will actually use.",
      "word_count": 84,
      "section_budget": 125,
      "citations_referenced": []
    },
    {
      "order": 12,
      "level": "none",
      "type": "cta",
      "heading": null,
      "body": "Audit your current tool stack against the three criteria before you start any new PM software trial.",
      "word_count": 17,
      "section_budget": 30,
      "citations_referenced": []
    }
  ],

  "article_markdown": "# How to Pick Project Management Software for Small Teams\n\nA practical guide to evaluation criteria, common pitfalls, and migration for teams of 10–50 already past the spreadsheet stage.\n\n## Key Takeaways\n\n- Most small teams pick PM software on features and regret it within 18 months.[^1]\n- Price, learning curve, and integration depth are the three criteria that actually predict retention.[^1]\n- Adopting more than four overlapping SaaS tools cuts task velocity by nearly a quarter.[^2]\n- A staged 4–6 week migration cuts abandonment risk by 41% versus a single-day cutover.[^3]\n- The right test for needing a tool is three concurrent multi-week projects, not headcount.[^4]\n\nIf your team has already tried a project management tool and quietly abandoned it, you're not alone — 62% of small teams report dissatisfaction with their first PM tool within 18 months. [... full intro paragraph ...]\n\n## What to Evaluate Before You Compare Tools\n\nPrice, learning curve, and integration depth predict whether a project management software pick survives 18 months — features barely matter. According to Gartner, those are the top three evaluation criteria cited by small teams.[^1] [... section body ...]\n\n### How to Tell If You Actually Need One Yet\n\nThe honest test is concurrent project load, not headcount. [... H3 body ...]\n\n## Common Mistakes Small Teams Make When Choosing PM Software\n\n[... section ...]\n\n## How to Migrate Your Team to a New PM Tool\n\n[... section ...]\n\n## Frequently Asked Questions\n\n### How much should a small team spend on project management software?\n\nSmall teams should expect to spend $10–$20 per user per month [... answer ...]\n\n### Is free project management software good enough for a startup?\n\n[... answer ...]\n\n### How long does it take to roll out PM software to a 20-person team?\n\n[... answer ...]\n\n## Conclusion\n\nPicking project management software for small teams is a question of fit, not features. [... conclusion ...]\n\nAudit your current tool stack against the three criteria before you start any new PM software trial.\n\n## Sources\n\n[^1]: Picking PM Software in 2024: A Buyer's Guide — https://www.gartner.com/en/articles/picking-pm-software-2024\n[^2]: The Real Cost of Tool Sprawl — https://hbr.org/2023/09/the-real-cost-of-tool-sprawl\n[^3]: Team Tool Migration Playbook — https://www.shopify.com/research/team-tool-migration-playbook\n[^4]: When Does a Small Team Actually Need PM Software? — https://www.atlassian.com/blog/teamwork/when-to-adopt-pm-tools\n",

  "article_html": "<h1>How to Pick Project Management Software for Small Teams</h1>\n<p>A practical guide to evaluation criteria, common pitfalls, and migration for teams of 10–50 already past the spreadsheet stage.</p>\n<h2>Key Takeaways</h2>\n<p>[... bulleted body with &lt;sup&gt;&lt;a href=&quot;#cite-1&quot;&gt;1&lt;/a&gt;&lt;/sup&gt; superscripts ...]</p>\n[... more elements ...]\n<h2>Sources</h2>\n<ol>\n<li id=\"cite-1\"><a href=\"https://www.gartner.com/en/articles/picking-pm-software-2024\">Picking PM Software in 2024: A Buyer's Guide</a></li>\n<li id=\"cite-2\"><a href=\"https://hbr.org/2023/09/the-real-cost-of-tool-sprawl\">The Real Cost of Tool Sprawl</a></li>\n<li id=\"cite-3\"><a href=\"https://www.shopify.com/research/team-tool-migration-playbook\">Team Tool Migration Playbook</a></li>\n<li id=\"cite-4\"><a href=\"https://www.atlassian.com/blog/teamwork/when-to-adopt-pm-tools\">When Does a Small Team Actually Need PM Software?</a></li>\n</ol>\n",

  "key_takeaways": [
    "Most small teams pick PM software on features and regret it within 18 months.",
    "Price, learning curve, and integration depth are the three criteria that actually predict retention.",
    "Adopting more than four overlapping SaaS tools cuts task velocity by nearly a quarter.",
    "A staged 4–6 week migration cuts abandonment risk by 41% versus a single-day cutover.",
    "The right test for needing a tool is three concurrent multi-week projects, not headcount."
  ],

  "intro": {
    "agree": "If your team has already tried a project management tool and quietly abandoned it, you're not alone — 62% of small teams report dissatisfaction with their first PM tool within 18 months.",
    "promise": "This guide gives you the three evaluation criteria that actually predict whether a tool will stick, the mistakes that sink most small-team rollouts, and a staged migration plan that survives contact with daily work.",
    "preview": "You'll see how to evaluate before you compare tools, the common mistakes small teams make when choosing PM software, and how to migrate your team to a new tool without losing the first month."
  },

  "cta": "Audit your current tool stack against the three criteria before you start any new PM software trial.",

  "citation_usage": {
    "total_citations_available": 5,
    "citations_used": 5,
    "citations_unused": 0,
    "usage": [
      {"citation_id": "cit_001", "used": true, "sections_used_in": [2, 4], "marker_placed": true},
      {"citation_id": "cit_002", "used": true, "sections_used_in": [2, 5], "marker_placed": true},
      {"citation_id": "cit_003", "used": true, "sections_used_in": [2, 4], "marker_placed": true},
      {"citation_id": "cit_004", "used": true, "sections_used_in": [5], "marker_placed": true},
      {"citation_id": "cit_005", "used": true, "sections_used_in": [2, 6], "marker_placed": true}
    ]
  },

  "format_compliance": {
    "lists_present": 2,
    "tables_present": 1,
    "lists_required": 1,
    "tables_required": 1,
    "answer_first_applied": true,
    "directives_satisfied": true
  },

  "brand_voice_card_used": {
    "tone_adjectives": ["plainspoken", "confident", "anti-jargon", "peer-to-peer"],
    "voice_directives": [
      "Open by naming the problem; do not set a scene.",
      "Address readers as peers, never as students.",
      "Refuse marketing-speak.",
      "Use concrete examples over abstractions.",
      "Prefer 'in practice' framing to 'imagine if'."
    ],
    "audience_summary": "Operations leaders at 10–50-person teams (founders, ops managers, COOs) past PMF but pre-Series B, under-resourced, allergic to fluff, defending tool purchases to skeptical founders.",
    "audience_pain_points": [
      "tool fatigue from already-abandoned tools",
      "team adoption failures",
      "hidden migration costs",
      "gap between vendor demos and daily reality"
    ],
    "audience_goals": [
      "pick something that survives 18 months",
      "avoid needing a dedicated admin",
      "integrate with existing Slack + GSuite stack"
    ],
    "audience_verticals": ["B2B SaaS", "operations consulting", "early-stage startups"],
    "preferred_terms": ["clear", "concrete", "outcomes", "in practice"],
    "banned_terms": ["synergy", "leverage", "best-in-class", "robust", "seamless", "world-class", "imagine if", "picture this", "in today's fast-paced world"],
    "discouraged_terms": [],
    "brand_name": "Tessera Studios",
    "client_services": ["operations consulting", "tool stack audits", "team workflow design"],
    "client_locations": ["Brooklyn, NY"],
    "client_contact_info": {"phone": null, "email": null, "address": null, "hours": null}
  },

  "brand_conflict_log": [],

  "client_context_summary": {
    "brand_guide_provided": true,
    "icp_provided": true,
    "website_analysis_used": true,
    "schema_version_effective": "1.7"
  },

  "metadata": {
    "total_word_count": 2218,
    "word_budget": 2500,
    "faq_word_count": 183,
    "budget_utilization_pct": 88.7,
    "word_count_conflict": false,
    "no_required_terms": false,
    "section_count": 4,
    "faq_count": 3,
    "citations_used": 5,
    "citations_unused": 0,
    "no_citations": false,
    "retry_count": 1,

    "dropped_for_low_topic_adherence": [],
    "low_h2_count_after_adherence_drop": false,

    "paragraph_length_violations": [],

    "under_cited_sections": [],
    "operational_claims_softened": [],
    "citation_coverage_retries_attempted": 0,
    "citation_coverage_retries_succeeded": 0,

    "under_length_h2_sections": [],
    "h2_body_length_retries_attempted": 1,
    "h2_body_length_retries_succeeded": 1,

    "topic_brand_alignment": "brand_aligned",
    "brand_mention_count": 2,
    "brand_mention_flags": [],
    "brand_anchor_h2_order": 5,
    "icp_anchor_h2_order": 4,
    "icp_hook_phrase": "tool fatigue from already-abandoned tools",
    "icp_callout_landed": true,
    "icp_callout_evidence": "If your team has already tried a project management tool and quietly abandoned it, you're not alone",
    "icp_callout_judge_status": "ok",

    "max_sentences_per_paragraph_default_applied": false,
    "cta_truncated": false,

    "schema_version": "1.7",
    "brief_schema_version": "2.3",
    "generation_time_ms": 71240
  }
}
```

### 20.6 What this example exercises

| Behavior | Where it shows up |
|---|---|
| H1 verbatim from brief | `article[0].heading == brief.title` |
| Enrichment lede ≤25 words | `article[1].word_count == 22` |
| Key Takeaways with markers | `article[2].body` has `{{cit_001}}` etc. |
| Intro 60–150 words, single paragraph | `article[3].body` joined; `word_count: 108` |
| Authority-gap H3 | `article[4].body` contains the `### How to Tell If You Actually Need One Yet` subsection |
| Fallback stub used as context only | `cit_004` referenced as "Forrester has covered the same adoption trap" — no specific stat from the stub |
| Brand anchor H2 mentions Tessera Studios | `metadata.brand_anchor_h2_order: 5` matches the H2 containing the Tessera mention |
| ICP anchor H2 surfaces pain point | `metadata.icp_anchor_h2_order: 4`, judge landed: true with paraphrase evidence |
| Brand mention count within budget | `brand_mention_count: 2` (target 2–3) |
| Brand-aligned topic | `topic_brand_alignment: "brand_aligned"` because client services overlap with article topic |
| Markdown footnotes | `article_markdown` uses `[^1]` and `## Sources` |
| HTML superscripts + Sources `<ol>` | `article_html` uses `<sup><a href="#cite-1">` and `<li id="cite-1">` |
| H2 body length retry succeeded | `h2_body_length_retries_attempted: 1`, `_succeeded: 1` |
| Zero brand conflicts | `brand_conflict_log: []` (no SIE-vs-brand term overlap on this input) |
| No coverage retries needed | `citation_coverage_retries_attempted: 0` (claims were well-cited on first pass) |
| `schema_version_effective: "1.7"` | Full v1.7 path, client context present and well-formed |

A test fixture can replay these payloads end-to-end and assert each row of this table.



---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/modules/content-brief-generator-prd-v2_0.md -->
<!-- ============================================================ -->

# PRD: Content Brief Generator Module

**Version:** 2.3
**Status:** Ready for Engineering Spec
**Last Updated:** May 3, 2026
**Part of:** [Parent Content Creation Platform — TBD name]
**Downstream Dependency:** Content Writer Module (v1.6+)
**Supersedes:** v2.2 (Phase 2 of the article-quality defect fixes). Filename retains the `-v2_0` suffix; canonical version is in this header.

> **v2.3 changes (2026-05-03):** Phase 3 of the article-quality defect fixes — addresses Defect 2 (empty H2 bodies) from the 2026-05-03 audit ("an H2 followed by two sentences and a stat before jumping to the next H2"). The brief generator's `format_directives` gains a `min_h2_body_words: int` field, stamped at assembly time from the run's `intent_format_template.h2_pattern`. Per-pattern defaults (calibrated for ~2,500-word articles distributed across the template's typical H2 count):
>
> | Intent pattern | Floor (words) | Rationale |
> |---|---|---|
> | `sequential_steps` (how-to) | 120 | Catches step-stub cases (audited: ~30w) |
> | `ranked_items` (listicle) | 80 | Lower because items are intentionally compact |
> | `parallel_axes` (comparison) | 150 | Catches vacuous "Pricing: it varies" sections |
> | `topic_questions` (informational) | 180 | Strictest — informational H2s carry the most prose |
> | `buyer_education_axes` (informational-commercial) | 180 | Same as informational |
> | `feature_benefit` (ecom) | 150 | Mid — feature-benefit copy is moderately substantive |
> | `place_bound_topics` (local-seo) | 150 | Mid |
> | `news_lede` (news) | 100 | Lower — news H2s are tight and recency-driven |
>
> The Writer Module's new Step 6.7 validator consumes the floor, retries each under-length H2 group ONCE with a stricter prompt naming the floor and asking for additional substance (not padding), then warns-and-accepts. The retry policy is consistent with R6 (paragraph length): never abort a run on length miss — empty H2s are recoverable in post-edit, and aborting would block all output. Schema bump `2.2` → `2.3`. Additive — `min_h2_body_words` defaults to 100 in the schema for legacy fixtures, so consumers that ignore the new field continue to work. v2.2 H3 parent-fit + FAQ intent gate behavior unchanged.

> **v2.2 changes (2026-05-03):** Phase 2 of the article-quality defect fixes — addresses Defect 3 (H3 → H2 topical drift) and Defect 4 (FAQ intent mismatch) from the 2026-05-03 audit.
>
> 1. **Step 8.6 tightened** — H3 parent-relevance floor raised `0.60 → 0.65` and the adjacent-region relaxation removed (H3s must sit in the SAME region as the parent H2, not just an adjacent one). Stops the audited "affiliate vetting under cart-abandonment H2" cross-region drift case.
> 2. **Step 8.7 — H3 Parent-Fit Verification** (NEW) — single batched Claude call after Step 9 + auth_attach. Each H3 is classified `good` / `marginal` / `wrong_parent` / `promote_to_h2`. `wrong_parent` re-attaches to a better-fit H2 when capacity exists, otherwise routes to silos via `routed_from="h3_parent_mismatch"`. `promote_to_h2` routes to silos via `routed_from="h3_promote_candidate"`. Authority-gap H3s are exempt from discard (downgrade `promote_to_h2` to `marginal`).
> 3. **Step 10.5 — FAQ Intent Gate** (NEW) — two-stage filter on FAQ candidates. (a) Cosine floor (default 0.55) against an `intent_profile` vector built from `intent_type + title + scope_statement + persona.primary_goal`. (b) Single batched Claude call classifies survivors as `matches_primary_intent` / `adjacent_intent` / `different_audience`; `different_audience` are dropped. Relaxation: when fewer than 3 `matches_primary_intent` survive, top up with the highest-scoring `adjacent_intent` candidates and stamp `metadata.faq_intent_gate_relaxation_applied = true`. Stops the audited "creator monetization on a seller-ROI article" case.
> 4. **`semantic_relevance` formula updated** — Step 10's `score_faqs` now produces a 50/50 blended cosine (cosine-to-title + cosine-to-intent-profile) when the intent profile is supplied. Falls back to title-only cosine for legacy callers.
>
> Schema bump: `2.1` → `2.2`. Additive — new optional `parent_fit_classification` on `HeadingItem`, new optional `intent_role` on `FAQItem`, three new `DiscardReason` values (`h3_wrong_parent`, `h3_promoted_to_h2_candidate`, `faq_intent_mismatch`), two new `SiloRoutedFrom` values (`h3_parent_mismatch`, `h3_promote_candidate`), seven new metadata counters. Consumers that ignore the new fields continue to work. v2.1 intent format template + anchor reservation + framing validator unchanged.

> **v2.1 changes (2026-05-03):** Phase 1 of the article-quality defect fixes — addresses Defect 1 from the 2026-05-03 audit (keyword-intent → article-format mismatch on the run for "How to Increase ROI for Your TikTok Shop", which classified correctly as `how-to` but produced topic-cluster Q&A H2s instead of procedural steps). Three additions:
>
> 1. **`intent_format_template`** — new top-level Step 3 output committing the brief to a per-intent heading-skeleton shape (`h2_pattern`, `h2_framing_rule`, `ordering`, `min_h2_count`, `max_h2_count`, `anchor_slots`). Drives Step 7.5 + Step 11.
> 2. **Step 7.5 — Anchor-Slot Reservation** (NEW) — runs immediately before Step 8. Embeds the template's `anchor_slots` and reserves the best-fitting candidate per slot before generic MMR runs. Listicle / news / local-seo templates carry empty anchor lists, so this is a no-op for them.
> 3. **Step 11 — H2 Framing Validator** (NEW) — runs after Step 8.5 scope verification, before the how-to reorder LLM call. Each selected H2 is regex-checked against the template's framing rule; failures route through a single batched LLM rewrite call; rewrites that still fail the regex are accepted with a `framing_violation_accepted` flag in metadata (warn-and-accept fallback — no run aborts).
>
> Schema bump: `2.0` → `2.1`. Additive, no breaking output changes; consumers that ignore the new fields continue to work. v2.0 brand reconciliation, banned-term enforcement, scope verification (Steps 8.5 / 8.5b), H3 selection (Step 8.6), authority gap (Step 9), title casing (Step 11.x), and silo identification (Step 12) are unchanged.

---

## 1. Problem Statement

v1.7 of the Content Brief Generator produced briefs that were structurally valid but topically broken. Outputs frequently contained 5+ H2s that all paraphrased the seed keyword (e.g., for "what is tiktok shop": "What is TikTok Shop", "What exactly is TikTok Shop", "What is a TikTok Shop seller", "What is a TikTok Shop creator", "What is a TikTok Shop account") — distinct headings on paper but functionally restating the same question. Other briefs included topically-related but scope-drifted sections (e.g., a "what is" piece including algorithm-optimization content that belongs in a different article). Both failure modes produced unusable downstream content.

Root causes in v1.7:
- **Lexical-only deduplication** (Levenshtein ≤ 0.15) failed to catch paraphrase H2s that differ at the character level but cluster tightly in semantic space.
- **No anti-restatement constraint.** Headings scoring 0.85+ semantic similarity to the seed passed the relevance filter (≥ 0.55) and were eligible for selection.
- **No intent diversity enforcement.** Six definition-flavored H2s could pass every constraint and end up in the same outline.
- **No scope discipline.** The brief generator had no concept of what the article's title commits to, so topically-related-but-out-of-scope sections were selected freely.
- **No information gain modeling.** Heading priority weighted SERP frequency and position heavily, which structurally encourages outlines that mirror what's already ranking.

v2.0 rewrites the pipeline around four new architectural primitives: explicit title and scope-statement generation, a coverage graph with community detection, hard mathematical constraints on semantic distance from the title, and Maximum Marginal Relevance (MMR) selection that maximizes topical value while enforcing diversity. Data acquisition (Steps 1–2) is preserved from v1.7; scoring, selection, and assembly are rewritten.

---

## 2. Goals

- Accept a single keyword input and return a fully structured content brief as a typed JSON object
- **Generate the article's title and scope statement from SERP signal** rather than letting the writer module infer them
- **Eliminate near-duplicate headings deterministically** via embedding-distance constraints, not LLM judgment
- **Eliminate topical-clone outlines** via graph-based region uniqueness in selection
- **Enforce scope discipline** via LLM verification against the explicit scope statement
- **Model information gain** as an explicit term in the priority formula
- Produce briefs optimized for both Google ranking and LLM citation
- Preserve v1.7's silo cluster identification, surfacing future-article seeds at no extra embedding cost

### Out of Scope (v2.0)
- Content writing (handled downstream by Writer Module)
- Keyword research / keyword selection
- Internal linking suggestions
- Publishing or CMS integration
- User-facing UI (this is a pipeline module)
- Multi-locale support — English / United States only
- Rank tracking and citation monitoring
- Multi-tenant brand configuration
- Per-client ICP context — the brief generator derives a hypothetical searcher from the topic itself; brand and ICP shaping is the Writer Module's responsibility (per v1.5 spec)
- Downstream consumption of silo candidates — whether they automatically trigger new brief generation, enter a queue, or are surfaced to a human for approval is outside this module's scope

---

## 3. Success Metrics

Success in v2.0 is defined by structural validity, semantic-constraint adherence, and operational discipline. Ranking and LLM citation performance tracking is out of scope and will be revisited once publish-to-tracking infrastructure exists.

| Metric | Target |
|---|---|
| Output validates against JSON schema | 100% |
| Brief contains 3–5 FAQs | 100% |
| Brief contains 3–5 authority gap H3s | 100% |
| **No selected H2 has cosine > 0.78 to title embedding** | 100% |
| **No two selected H2s have cosine > 0.75 to each other** | 100% |
| **No two selected H2s come from the same coverage graph region** | 100% |
| **Every selected H2 passes scope verification or is logged with override reason** | 100% |
| Brief produces a non-empty title and scope_statement | 100% |
| End-to-end generation completes within 120s | ≥95% |
| Cost per brief stays under $1.00 | ≥95% |

The first four constraint-adherence metrics are mathematically guaranteed by the selection algorithm — failure to meet them indicates an implementation bug, not a quality issue.

---

## 4. System Architecture Overview

```
[Keyword Input]
      │
      ▼
┌─────────────────────┐
│  Step 0: Input      │  ◄── Reject empty/whitespace, >150 chars
│  Validation         │
└─────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────┐
│  Step 1 + 2 (Parallel) — UNCHANGED FROM v1.7             │
│  ┌────────────┐  ┌────────────────────────────────────┐  │
│  │ SERP Scrape│  │ PAA + Reddit + Autocomplete        │  │
│  │ DataForSEO │  │ + Keyword Suggestions              │  │
│  │            │  │ + LLM Fan-Out Queries              │  │
│  │            │  │   (ChatGPT, Claude, Gemini,        │  │
│  │            │  │    Perplexity — parallel)          │  │
│  └────────────┘  └────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 3: Intent     │  ◄── Rules-based on SERP features
│  Classification     │  ◄── LLM check on borderline ecom/commercial
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 3.5: Title +  │  ◄── NEW. Single LLM call.
│  Scope Statement    │  ◄── Inputs: seed, intent, top SERP titles,
│  Generation         │      H1s, meta descriptions, LLM fan-out
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 4: Subtopic   │  ◄── Aggregate all candidate sources
│  Aggregation        │  ◄── Lexical dedup (Levenshtein) preserved
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 5: Embedding  │  ◄── REWRITTEN. text-embedding-3-large
│  + Coverage Graph   │  ◄── Build pairwise similarity graph
│  Construction       │  ◄── Louvain community detection → regions
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 6: Hypothetical│ ◄── NEW. Single LLM call.
│  Searcher Persona    │ ◄── Generates persona + gap questions
│  Generation          │
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 7: Heading    │  ◄── REVISED priority formula
│  Priority Scoring   │  ◄── Includes information gain term
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 8: Constrained│  ◄── REWRITTEN. MMR selection with:
│  H2 Selection (MMR) │      • Relevance floor (≥0.55 to title)
│                     │      • Restatement ceiling (≤0.78 to title)
│                     │      • Inter-heading limit (≤0.75 pairwise)
│                     │      • Region uniqueness (max 1 per region)
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 8.5: Scope    │  ◄── NEW. LLM verification against
│  Verification       │      scope_statement. Out-of-scope H2s
│                     │      route to silo candidates.
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 9: Authority  │  ◄── Universal Authority Agent (3-pillar)
│  Gap Analysis       │  ◄── Reddit threads as context
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 10: FAQ       │  ◄── PAA + Reddit regex + LLM concern pass
│  Generation         │  ◄── Persona gap questions feed candidates
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 11: Structure │  ◄── Intent-aware assembly
│  Assembly           │  ◄── How-to sequential reordering
│                     │  ◄── Global subheading cap enforcement
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 12: Silo      │  ◄── REUSES regions from Step 5
│  Cluster            │  ◄── Regions that didn't contribute H2s
│  Identification     │      become silo candidates
└─────────────────────┘
      │
      ▼
[JSON Output → Content Writer Module]
```

---

## 5. Functional Requirements

### Step 0 — Input Validation

| Rule | Action |
|---|---|
| Input is empty or whitespace-only | Reject with structured error |
| Input length >150 characters | Reject with structured error |
| All other inputs | Pass through as-typed |

### Step 1 — SERP Scraping (Unchanged from v1.7)

**Provider:** DataForSEO SERP API (Standard Queue)
**Locale:** English / United States only

**Outputs:**
- Headings (H1–H3) from top 20 organic results
- **Top 20 organic page titles** (used as input to Step 3.5)
- **Top 20 meta descriptions** (used as input to Step 3.5)
- SERP feature presence flags: shopping box, news box, local pack, featured snippet, PAA, product carousels, comparison tables

**Rules:**
- Exclude headings shorter than 3 words
- Exclude headings from paginated results (page 2+)
- Tag each heading with source URL and SERP position
- Strip boilerplate patterns ("Contact Us", "About the Author", "Related Posts")

### Step 2 — PAA, Reddit, Autocomplete, and LLM Fan-Out (Unchanged from v1.7)

All sub-sources (2A PAA, 2B Reddit, 2C Autocomplete + Keyword Suggestions, 2D LLM Fan-Out across 4 LLMs) operate identically to v1.7. See v1.7 Section 5 for full specifications. Cross-LLM consensus tracking via `llm_fanout_consensus` (0–4) is preserved.

### Step 3 — Intent Classification (REVISED in v2.0.3 — adds keyword pattern pre-check)

The classifier runs in two passes: a deterministic **keyword pattern pre-check** that fires before any SERP analysis, falling through to the v1.7 SERP-feature-signal logic only when the keyword does not match a known pattern. The pre-check exists because SERP-title-based classification fails when the top results don't literally start with the expected phrase (e.g., a "how to open X" query whose top SERP titles are mostly noun-phrase listicles).

**Step 3.1 — Keyword pattern pre-check (NEW in v2.0.3):**

If the seed keyword (lowercased, leading/trailing whitespace stripped) matches one of the patterns below, classify with the listed intent + confidence and **skip Step 3.2 entirely**. First match wins; patterns are evaluated top-to-bottom:

| Pattern (matched as a leading-prefix or substring) | Intent | Confidence |
|---|---|---|
| Starts with `how to`, `how do i`, `how can i`, `ways to`, `steps to`, `guide to` | `how-to` | 0.95 |
| Starts with `what is`, `what are`, `what does`, `definition of` | `informational` | 0.90 |
| Starts with `best`, `top`, or matches `^\d+\s+\w+s\b` (number + plural noun, e.g., "10 ways") | `listicle` | 0.90 |
| Contains ` vs `, ` versus `, ` or `, `compared to` | `comparison` | 0.90 |

When the pre-check matches, `intent_review_required` is set to `false` (the pattern is unambiguous enough not to warrant human review).

**Step 3.2 — SERP-feature-signal classification (UNCHANGED from v1.7):**

If the keyword pattern pre-check did NOT match, fall through to the existing rules-based classifier on SERP feature signals, with LLM check for borderline ecom/commercial cases. Intent types: `informational`, `listicle`, `how-to`, `comparison`, `ecom`, `local-seo`, `news`, `informational-commercial`. See v1.7 Section 5 Step 3 for the full rule mapping.

**Output:** `intent_type`, `intent_confidence`, `intent_review_required` (true if confidence < 0.75 and Step 3.1 did not fire)

**Step 3.3 — Intent format template (NEW in v2.1):**

The classifier's output is mapped (deterministic lookup, no LLM call) to a per-intent **heading skeleton template** that drives Step 7.5 anchor-slot reservation and Step 11 framing validation. The template is committed to the brief output as a top-level `intent_format_template` object.

```json
{
  "intent_format_template": {
    "intent": "how-to",
    "h2_pattern": "sequential_steps",
    "h2_framing_rule": "verb_leading_action",
    "ordering": "strict_sequential",
    "min_h2_count": 4,
    "max_h2_count": 12,
    "anchor_slots": [
      "plan and prepare",
      "set up and configure",
      "launch and execute",
      "measure results and iterate"
    ],
    "description": "Sequential procedural steps (verb-leading H2s) for how-to intent."
  }
}
```

**Per-intent template registry (v1):**

| Intent | `h2_pattern` | `h2_framing_rule` | `ordering` | Anchor slots | `min` / `max` H2 |
|---|---|---|---|---|---|
| `how-to` | `sequential_steps` | `verb_leading_action` | `strict_sequential` | plan / set up / launch / iterate (4) | 4 / 12 |
| `listicle` | `ranked_items` | `ordinal_then_noun_phrase` | `none` | none (no anchor reservation) | 5 / 10 |
| `comparison` | `parallel_axes` | `axis_noun_phrase` | `logical` | pricing / features / performance / support (4) | 3 / 6 |
| `informational` (incl. `definition`/`guide` aliases) | `topic_questions` | `question_or_topic_phrase` | `logical` | definition / how it works / who / pitfalls (4) | 4 / 6 |
| `informational-commercial` (incl. `review` alias) | `buyer_education_axes` | `buyer_education_phrase` | `logical` | what to look for / comparing / mistakes / evaluate (4) | 4 / 6 |
| `ecom` | `feature_benefit` | `axis_noun_phrase` | `logical` | what is included / pricing / compatibility / warranty (4) | 4 / 6 |
| `local-seo` | `place_bound_topics` | `no_constraint` | `logical` | none | 3 / 6 |
| `news` | `news_lede` | `no_constraint` | `strict_sequential` | none | 3 / 5 |

`local-seo` and `news` carry `framing_rule="no_constraint"` so the Step 11 validator is a NOOP for them — both are deferred to v1.x. Aliases `guide`, `definition`, and `review` are not new enum values; the classifier already collapses them to one of the canonical intents above.

**Anchor-slot semantics:** anchors are short *phase-level* phrases (e.g. `"plan and prepare"`), not topic-level (e.g. `"plan your TikTok shop"`). Phase phrasing generalizes across keywords — the same how-to skeleton applies whether the article is about opening a TikTok shop, building a deck, or launching a podcast. Topic-level anchors would over-constrain the candidate pool.

### Step 3.5 — Title + Scope Statement Generation (NEW)

**Purpose:** Commit to an explicit article title and scope statement that anchor all downstream selection and verification logic. Without this commitment, scope discipline can only be approximated from indirect signals.

**Method:** Single LLM call (model: same as section writing in Writer Module — likely the highest-quality available model, since title quality cascades through every downstream step).

**Inputs:**
- Seed keyword
- `intent_type` from Step 3
- Top 20 SERP titles from Step 1
- Top 20 SERP H1s from Step 1
- Top 20 meta descriptions from Step 1
- LLM fan-out responses from Step 2D (full text, not just extracted queries)

**Output schema (strict, additionalProperties: false):**

```json
{
  "title": "string (50–80 chars preferred, 100 char max)",
  "scope_statement": "string (≤500 chars)",
  "title_rationale": "string (≤300 chars)"
}
```

**Prompt requirements:**

The title generation LLM must:
- Examine competitor title patterns to identify SERP convention for this query
- Note what no competitor is doing (potential differentiation angle)
- Avoid generic AI-tells in titling: "Ultimate Guide to", "Complete Guide", "Everything You Need to Know", "The Definitive Guide", "Master [topic]"
- Produce a scope statement specific enough to be enforceable, not so specific that it preempts editorial judgment in the Writer Module
- Include a `does not cover` clause in the scope statement that names 1–3 adjacent topics this article will explicitly not address
- Stay within freshness/recency constraints: mention the current year only when the topic genuinely warrants it; do not reflexively stamp "in 2026" on every title

**Example output for seed `"what is tiktok shop"` with intent `informational`:**

```json
{
  "title": "What TikTok Shop Is and How It Works in 2026",
  "scope_statement": "Defines TikTok Shop, explains how the system functions for both sellers and buyers, and orients readers to the major components of the platform. Does not cover advanced seller tactics, algorithm optimization strategies, or operational decisions like inventory management or paid amplification.",
  "title_rationale": "Top 20 SERP titles converge on definitional framing. Featured snippet present indicates Google has settled on a canonical definition format. Adding 'in 2026' signals freshness against 2023-launch vintage of most ranking content."
}
```

**Failure handling:**

| Scenario | Behavior |
|---|---|
| LLM returns malformed JSON | One retry with stricter prompt; on second failure, abort run with `title_generation_failed` |
| Title field empty or >100 chars | One retry; on second failure, abort with `title_generation_failed` |
| Scope statement empty or missing `does not cover` clause | One retry with stricter prompt; on second failure, abort with `title_generation_failed` |

### Step 4 — Subtopic Aggregation (Mostly Unchanged from v1.7)

- Combine all scraped H1–H3 headings from Step 1 plus autocomplete queries, keyword suggestions, fan-out queries from all 4 LLMs, and response extractions from all 4 LLMs from Step 2
- **Add persona gap questions from Step 6** as candidate headings (tagged `source: "persona_gap"`)
- Normalize: lowercase + strip punctuation for comparison; preserve original casing for output
- Deduplicate using fuzzy matching (Levenshtein distance threshold ≤ 0.15) across all sources
- Tag each unique entry with `serp_frequency` and `avg_serp_position`
- Non-SERP sources (autocomplete, keyword suggestion, LLM fan-out, LLM response, persona gap) get `serp_frequency: 0` and `avg_serp_position: null`
- Track `llm_fanout_consensus` (integer 0–4) on each heading: count of LLMs whose fan-out queries or response extractions surfaced this topic

**Note on ordering:** Step 6 (persona generation) runs after Step 4 conceptually but its output feeds back into the candidate pool. Implementation should aggregate non-persona candidates first, then re-aggregate after persona output, then proceed to Step 5.

### Step 5 — Embedding + Coverage Graph Construction (REWRITTEN)

**Embedding model:** OpenAI `text-embedding-3-large` (1536-dimensional, upgraded from v1.7's `text-embedding-3-small` for finer-grained paraphrase discrimination).

**Substeps:**

**5.1 Embedding generation:**
1. Embed the seed keyword
2. Embed the title from Step 3.5
3. Embed the scope statement from Step 3.5
4. Embed each unique heading from Step 4
5. Normalize all embeddings to unit length (so cosine similarity equals dot product)

**5.2 Pre-filtering by relevance to title:**

```
For each heading:
    title_relevance = heading_embedding · title_embedding
    
    If title_relevance < 0.55:
        Move to discarded_headings with discard_reason: "below_relevance_floor"
    Else if title_relevance > 0.78:
        Move to discarded_headings with discard_reason: "above_restatement_ceiling"
    Else:
        Keep as eligible candidate
```

The 0.78 ceiling is the central anti-paraphrase mechanism. Headings restating the title are blocked at this gate, before any selection logic runs.

**5.3 Coverage graph construction:**

Using `networkx`, build an undirected graph where:
- Nodes are eligible candidates from 5.2
- Edges connect candidates with pairwise cosine similarity above the **edge threshold of 0.65**
- Edge weights are the cosine similarity values

**5.4 Community detection:**

Apply Louvain community detection (`networkx.algorithms.community.louvain_communities`) with `resolution=1.0` and a fixed `seed=42` for reproducibility. Output: list of node sets, each representing a topical region.

**5.5 Region scoring:**

For each region, compute:

| Metric | Formula |
|---|---|
| `density` | Number of candidates in the region |
| `source_diversity` | Count of distinct source types (serp, paa, reddit, autocomplete, keyword_suggestion, llm_fanout_*, llm_response_*, persona_gap) represented in the region |
| `centroid_title_distance` | Cosine similarity between region centroid (mean of member embeddings) and title embedding |
| `information_gain_signal` | Fraction of region candidates that come from non-SERP sources (Reddit, PAA, autocomplete, LLM fan-out, LLM response, persona gap). High value = readers ask about this but competitors aren't covering it. |

**Region elimination:**

| Rule | Action |
|---|---|
| Region has fewer than 2 candidates | Mark as singleton; eligible for selection but cannot become a silo candidate |
| Region centroid scores < 0.55 to title (region as a whole is off-topic) | Eliminate region; member candidates move to discarded_headings with `discard_reason: "region_off_topic"` |
| Region centroid scores > 0.78 to title (entire region restates the title) | Eliminate region; member candidates move to discarded_headings with `discard_reason: "region_restates_title"` |

### Step 6 — Hypothetical Searcher Persona Generation (NEW)

**Purpose:** Generate questions a curious searcher of this keyword would ask that the candidate pool doesn't address well. These become candidate H2s tagged `source: "persona_gap"` that re-enter the aggregation pool (Step 4).

**Method:** Single LLM call.

**Inputs:**
- Seed keyword
- `intent_type` from Step 3
- Title and scope statement from Step 3.5
- Top SERP H1s and meta descriptions from Step 1
- Aggregated candidate headings from Step 4 (pre-graph-construction)

**Output schema (strict, additionalProperties: false):**

```json
{
  "persona": {
    "description": "string (≤300 chars)",
    "background_assumptions": ["string (max 5 items)"],
    "primary_goal": "string (≤200 chars)"
  },
  "gap_questions": [
    {
      "question": "string",
      "rationale": "string (≤200 chars) — why this question matters and is not covered by existing candidates"
    }
  ]
}
```

**Constraints:**
- Generate 5–10 gap questions
- Questions must respect the scope statement — no questions outside the article's scope boundary
- Persona description must derive from topic + SERP signal, not from any external ICP context
- Each gap question feeds Step 4 as a candidate heading with `source: "persona_gap"`

**Failure handling:**

| Scenario | Behavior |
|---|---|
| LLM returns malformed JSON | One retry; on second failure, continue with empty gap_questions and log warning |
| Persona description empty | Continue; persona output is informational only, not used as a hard constraint |
| Zero gap questions returned | Continue; selection proceeds without persona-derived candidates |

### Step 7 — Heading Priority Scoring (REVISED)

**Combined priority formula:**

```
heading_priority = (0.30 × title_relevance) 
                 + (0.20 × normalized_serp_frequency) 
                 + (0.10 × position_weight) 
                 + (0.20 × normalized_llm_consensus)
                 + (0.20 × information_gain_score)

Where:
- title_relevance = cosine(heading_embedding, title_embedding)
- normalized_serp_frequency = min(serp_frequency / 20, 1.0)
- position_weight = 1.0 - ((avg_serp_position - 1) / 20) if avg_serp_position is not null, else 0.5
- normalized_llm_consensus = llm_fanout_consensus / 4
- information_gain_score = 1.0 if heading source is non-SERP and llm_fanout_consensus >= 1, 
                            else 0.7 if heading source is non-SERP, 
                            else 0.3 if heading source is SERP only,
                            else 0.0
```

**Rationale:**
- **Title relevance** (0.30) replaces v1.7's seed similarity. The title is the article's actual commitment.
- **SERP frequency** (0.20) is a proven signal that something is topically central but should not dominate.
- **Position weight** (0.10) reduced from v1.7's 0.15 — top-position bias compounds SERP convergence.
- **LLM consensus** (0.20) preserved at v1.7 level. Cross-model agreement is a strong citation-optimization signal.
- **Information gain** (0.20) is new. A heading that appears in Reddit/PAA/LLM fan-out but not in competitor SERP is exactly the differentiation we want to surface.

### Step 7.5 — Anchor-Slot Reservation (NEW in v2.1)

**Purpose:** Force the heading skeleton to match the keyword's intent. Without this step, MMR (Step 8) maximizes priority + diversity but is blind to *shape* — a how-to keyword whose pool is dominated by definitional candidates would produce a Q&A outline even though Step 3 correctly classified the intent as `how-to`. Step 7.5 closes the gap by reserving each anchor slot's best-fitting candidate before generic MMR runs.

**Method:** Single OpenAI embedding call (anchors only — typically 0–5 strings).

**Inputs:**
- `intent_format_template.anchor_slots` from Step 3.3
- The eligible candidate pool from Step 5 (after region elimination)
- `inter_heading_threshold` (matches Step 8's threshold)

**Algorithm:**

1. Embed every anchor in `anchor_slots` (single batched API call). Templates with empty `anchor_slots` (`listicle`, `news`, `local-seo`) skip Step 7.5 entirely.
2. For each anchor in template order:
   - Score each unreserved candidate as `cosine(candidate.embedding, anchor.embedding)`.
   - Skip candidates whose `region_id` was reserved by an earlier slot (region uniqueness).
   - Skip candidates whose pairwise cosine to any prior reservation exceeds `inter_heading_threshold` (anti-redundancy).
   - Reserve the highest-scoring survivor whose score exceeds `MIN_ANCHOR_COSINE = 0.55`. Below the floor, leave the slot empty rather than force-fitting an off-anchor candidate — log `unmatched_slot_indices` so threshold-tuning sessions can spot pools that genuinely lack procedural coverage.

**Output:** A list of reserved candidates (in template order) plus the indices of unmatched slots. The reserved list is passed into Step 8 as `pre_reserved`.

**Failure handling:**

| Scenario | Behavior |
|---|---|
| Anchor embedding API call fails | Log + continue with empty reservation; Step 8 falls through to plain MMR. Never aborts the run. |
| Embedding count mismatches anchor count (defensive) | Log + return empty reservation. |
| Pool is empty | Return empty reservation; Step 8 will raise `no_h2s_selected` itself if applicable. |

**Cost:** One embedding call (≤ 5 anchors) per brief — ~$0.0001. Negligible.

**Logging:**
- `brief.anchor.reservation_complete` (INFO) — counts reserved vs. unmatched slots.
- `brief.anchor.unmatched` (DEBUG) — per-slot best score + threshold for tuning.

### Step 8 — Constrained H2 Selection via MMR (REWRITTEN)

**Algorithm:** Greedy Maximum Marginal Relevance (MMR) with hard constraints.

**Configuration:**

| Parameter | Default | Notes |
|---|---|---|
| `mmr_lambda` | 0.7 | Balance between topical value (priority score) and diversity |
| `target_h2_count` | 6 (capped intents), 10 (listicle/how-to baseline, uncapped) | From v1.7 intent rules. v2.1: clamp to `intent_format_template.max_h2_count`; for `sequential_steps` raise to `min(8, max_h2_count)`. |
| `inter_heading_threshold` | 0.75 | Maximum allowed pairwise cosine between any two selected H2s |
| `pre_reserved` | `[]` | NEW in v2.1. Candidates already chosen by Step 7.5 anchor-slot reservation. They occupy the head of `selected` in input order; their regions and embeddings seed MMR's hard-constraint state so subsequent picks don't violate region-uniqueness or inter-heading thresholds against them. MMR fills the remaining `target_count - len(pre_reserved)` slots from the (non-reserved) eligible pool. |

**Algorithm logic:**

```python
def select_h2s(candidates, title_embedding, target_count, mmr_lambda=0.7,
               inter_heading_threshold=0.75):
    """
    candidates: list of dicts with embedding, priority_score, region_id, heading text
    title_embedding: unit-normalized title embedding
    """
    selected = []
    selected_regions = set()
    selected_embeddings = []
    eligible = list(candidates)  # Already pre-filtered for relevance + restatement gates
    
    while eligible and len(selected) < target_count:
        best_score = -float('inf')
        best_idx = None
        
        for i, candidate in enumerate(eligible):
            # Hard constraint: region uniqueness
            if candidate['region_id'] in selected_regions:
                continue
            
            # Hard constraint: inter-heading anti-redundancy
            if selected_embeddings:
                max_pairwise = max(
                    candidate['embedding'] @ s for s in selected_embeddings
                )
                if max_pairwise > inter_heading_threshold:
                    continue
                redundancy_penalty = max_pairwise
            else:
                redundancy_penalty = 0.0
            
            # MMR objective
            mmr_score = (
                mmr_lambda * candidate['priority_score']
                - (1 - mmr_lambda) * redundancy_penalty
            )
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i
        
        if best_idx is None:
            break  # No eligible candidate satisfies all constraints
        
        chosen = eligible.pop(best_idx)
        selected.append(chosen)
        selected_regions.add(chosen['region_id'])
        selected_embeddings.append(chosen['embedding'])
    
    return selected
```

**Shortfall handling:**

If selection terminates with fewer H2s than `target_h2_count`, accept the shortfall. Output the H2s found and set `metadata.h2_shortfall = true` with `metadata.h2_shortfall_reason: "constraints_exhausted_eligible_pool"`. Do NOT relax thresholds or invent synthetic H2s to hit a quota — an honest brief with 4 strong H2s beats a padded brief with 6 weak ones.

**Discarded headings:**

Eligible candidates not selected are moved to `discarded_headings` with `discard_reason: "below_priority_threshold"` (didn't win MMR competition) or `discard_reason: "global_cap_exceeded"` (selected by MMR but cut by global subheading cap downstream — see Step 11).

### Step 8.5 — Scope Verification (NEW)

**Purpose:** Catch the small percentage of cases where a heading passes all numerical constraints but answers a different reader question than the title's promise. This is the "TikTok Shop algorithm signals" failure mode — topically related but out of scope.

**Method:** Single LLM call.

**Inputs:**
- Title from Step 3.5
- Scope statement from Step 3.5 (with explicit `does not cover` clause)
- All H2s selected by Step 8

**Output schema (strict, additionalProperties: false):**

```json
{
  "verified_h2s": [
    {
      "h2_text": "string",
      "scope_classification": "in_scope" | "borderline" | "out_of_scope",
      "reasoning": "string (≤200 chars)"
    }
  ]
}
```

**Routing:**

| Classification | Action |
|---|---|
| `in_scope` | Keep in selected H2s |
| `borderline` | Keep in selected H2s; flag in metadata for human review |
| `out_of_scope` | Remove from selected H2s; route to `silo_candidates` with `routed_from: "scope_verification"` |

After scope verification, if removals dropped the H2 count below target, the selection algorithm (Step 8) does NOT re-run to fill the gap. Accept the shortfall with `h2_shortfall = true`. Re-running selection risks pulling in candidates that would also fail scope verification, and the LLM call is non-deterministic enough that a re-run loop is risky.

**Failure handling:**

| Scenario | Behavior |
|---|---|
| LLM returns malformed JSON | One retry; on second failure, accept all H2s as `in_scope` and log warning. Do not abort the run — selection has already produced a valid outline by mathematical constraints. |
| LLM classifies an H2 not in the input list | Discard the rogue classification; log warning |

**Step 8.5b — Authority Gap H3 scope verification pass (NEW in v2.0.3):**

Step 8.5 originally verified only Step 8's MMR-selected H2s, leaving Authority Gap H3s (Step 9) able to bypass scope discipline entirely. v2.0.3 closes that loop by running a **second scope-verification pass** over the H3s emitted by Step 9 — not over Step 8.6's H3s, which were already drawn from the in-band coverage-graph pool.

The pass runs after Step 9 produces its 3–5 Authority Gap H3s. Inputs match Step 8.5 (title + scope_statement + the new H3 texts). The output schema mirrors Step 8.5's `verified_h2s` array with `verified_h3s`:

```json
{
  "verified_h3s": [
    {
      "h3_text": "string",
      "scope_classification": "in_scope" | "borderline" | "out_of_scope",
      "reasoning": "string (≤200 chars)"
    }
  ]
}
```

Routing:

| Classification | Action |
|---|---|
| `in_scope` | Keep the H3 attached to its parent H2 |
| `borderline` | Keep the H3, stamp `scope_classification: "borderline"` on the H3 entry, increment `metadata.scope_verification_borderline_count` |
| `out_of_scope` | Remove from the H3 attachment list; route to `silo_candidates` with `routed_from: "scope_verification_h3"` |

Failure handling matches Step 8.5: malformed JSON triggers one retry; on second failure, fall back to accept-all-as-`in_scope` and log. Authority gap H3s rejected at this pass do NOT reduce the per-H2 cap; the H2 simply ends up with one fewer H3, which is acceptable per Step 11 (H3s optional per H2). The Section 9 cost model adds ~$0.02 per brief for this extra LLM call.

### Step 8.6 — H3 Selection (NEW)

**Purpose:** For each selected H2, choose 0–2 H3s from the candidate pool that elaborate the H2's scope without restating it. Authority Gap H3s (Step 9) are inserted afterward and may displace lower-priority H3s if the per-H2 cap is exceeded.

This step formalizes H3 selection as a parent-scoped mirror of Step 8: same MMR + region + anti-restatement principles, but applied at H2-scope rather than title-scope. Without explicit rules at this layer, an implementation might default to picking H3s by global priority regardless of parent H2, which would reproduce the v1.7 paraphrase failure mode at the H3 level.

**Inputs:**
- All eligible H3-level candidates from the coverage graph (Step 5) — the post-region-elimination pool minus the H2s selected by Step 8
- Selected H2s from Step 8 with their embeddings and `region_id`s
- Scope statement from Step 3.5

**Algorithm — for each selected H2:**

1. Compute `parent_relevance` for every H3 candidate as the cosine similarity between the H3 candidate embedding and the H2 embedding.

2. Filter the candidate pool to that H2's scope. Keep only H3 candidates that:
   - Have `parent_relevance >= 0.65` *(PRD v2.2 / Phase 2: raised from 0.60)* (must be related to the H2)
   - Have `parent_relevance <= 0.85` (must not restate the H2; threshold is slightly looser than the title-level 0.78 because H3s legitimately drill into narrower scopes)
   - Belong to the **same coverage graph region as the H2** *(PRD v2.2 / Phase 2: dropped the adjacent-region relaxation; previously also accepted regions with edge ≥ 0.65 to the H2's region centroid, which let cross-region drift through — the audited "affiliate vetting under cart-abandonment H2" case)*
   - Were not already selected as H2s elsewhere

3. Apply MMR within the filtered pool, using:
   - Target count: 2 H3s per H2 maximum
   - Inter-H3 anti-redundancy threshold: 0.78 pairwise (looser than the 0.75 used for H2s)
   - Priority score for H3s: same formula as H2s in Step 7, with `title_relevance` replaced by `parent_relevance` for the H2 the H3 is being assigned to

4. Accept shortfalls. If filtering produces fewer than 2 eligible H3s for a given H2, output what is available. Per Section 11, H3s are not required per H2.

**Discarded headings:**

H3 candidates dropped during this step are routed to `discarded_headings` with one of the following reasons:

| Filter | discard_reason |
|---|---|
| Below `parent_relevance >= 0.65` *(v2.2)* | `h3_below_parent_relevance_floor` |
| Above `parent_relevance <= 0.85` | `h3_above_parent_restatement_ceiling` |
| Lost the per-H2 MMR competition | `below_priority_threshold` |

A candidate that fails the parent-relevance check for one H2 is still considered for every other selected H2. Only candidates that fail against all selected H2s carry an `h3_*` discard reason in the final output.

**Authority Gap H3 Interaction:**

After Step 8.6 produces selected H3s per H2, Step 9 runs and adds 3–5 Authority Gap H3s. Each Authority Gap H3 is assigned to the most relevant H2. If adding an Authority Gap H3 would push that H2 over the 2-H3 cap:

1. Compare priority scores. If the Authority Gap H3 has a higher priority score than the lowest-scoring existing H3, the existing H3 is displaced (moved to `discarded_headings` with `discard_reason: "displaced_by_authority_gap_h3"`).
2. If the Authority Gap H3 has a lower priority score than all existing H3s on that H2, route it to the next-most-relevant H2 (recursive).
3. If no H2 can accommodate the Authority Gap H3 without violating the cap and the Authority Gap H3 has the lowest priority across the board, it is still kept (Authority Gap H3s are never discarded per Step 9 rules); the per-H2 cap may be exceeded by 1 in this edge case. Step 11 (Structure Assembly) must allow a maximum of 3 H3s per H2 specifically when Authority Gap H3s caused the overflow.

**Output:**

Each selected H2 carries an h3s array (possibly empty), and each H3 carries:
- `parent_h2_text` (so the structure is reconstructable from the flat `heading_structure` array)
- `parent_relevance` (the cosine similarity to its parent H2)
- All standard heading fields already specified in the output schema (`region_id`, `source`, scores, etc.)

**Failure handling:**

| Scenario | Behavior |
|---|---|
| H2 has 0 eligible H3s after filtering | Accept zero H3s for that H2; increment `metadata.h2s_with_zero_h3s` |
| Eligible pool is empty across all H2s | Continue without non-authority H3s; Step 9 still runs |
| Embedding required for H2 or H3 candidate is missing (defensive) | Skip that pairing; do not abort |

This step adds no new LLM calls — it is pure embedding math and MMR over the same vectors produced in Step 5.

### Step 8.7 — H3 Parent-Fit Verification (NEW in v2.2 / Phase 2)

**Purpose:** Catch H3s that pass Step 8.6's numerical filters (parent_relevance in [0.65, 0.85], same region as parent H2) but answer a different reader question than the parent H2 actually commits to. The audited "affiliate vetting under cart-abandonment H2" case made it through Step 8.6's bands; LLM classification distinguishes "near-topic" from "actually belongs under this H2".

This is the H3-level analogue of Step 8.5 (scope verification for H2s). Step 8.5b already covers authority-gap H3s vs the article scope; Step 8.7 covers the H2↔H3 parent-fit relationship for ALL H3s in the final attachment map (Step 8.6 selections + authority-gap survivors).

**Position in the pipeline:** runs **after** Step 9's authority-gap injection + Step 8.5b's scope verification + `attach_authority_h3s_with_displacement` so the LLM operates on the final per-H2 attachment map. Runs **before** Step 11 structure assembly.

**Method:** Single batched Claude call.

**Inputs:**
- `h2_attachments`: dict[h2_idx, list[H3 Candidate]] — the final per-H2 attachment map
- `selected_h2s`: list[Candidate] — the parent H2 list (indices align with attachment dict keys)

**Output schema (strict JSON, additionalProperties: false):**

```json
{
  "verifications": [
    {
      "h3_id": "h2_<i>.h3_<j>",
      "classification": "good" | "marginal" | "wrong_parent" | "promote_to_h2",
      "reasoning": "string (≤200 chars)"
    }
  ]
}
```

**Routing:**

| Classification | Action |
|---|---|
| `good` | Keep under current parent. No metadata flag. |
| `marginal` | Keep under current parent. Stamp `parent_fit_classification: "marginal"` on the heading. Increment `metadata.h3_parent_fit_marginal_count`. |
| `wrong_parent` | Try to re-attach: pick the OTHER selected H2 with (a) capacity (≤ 2 H3s, or ≤ 3 if authority-overflow) and (b) `cosine(h3, h2) > parent_relevance_floor` (default 0.65). If found, refresh `parent_h2_text` and `parent_relevance` on the H3 and move it. If no fitting parent: route to silos with `routed_from="h3_parent_mismatch"` and `discard_reason="h3_wrong_parent"`. Increment `metadata.h3_parent_fit_wrong_parent_count`. |
| `promote_to_h2` | The H3 is substantial enough for its own article. Route to silos with `routed_from="h3_promote_candidate"` and `discard_reason="h3_promoted_to_h2_candidate"`. Increment `metadata.h3_parent_fit_promoted_count`. |

**Authority-gap exemption:** H3s with `source == "authority_gap_sme"` are never discarded per PRD §5 Step 9. For authority H3s only:
- `wrong_parent` with no fitting alternative parent → downgrade to `marginal` (kept under current parent with the flag).
- `promote_to_h2` → downgrade to `marginal`.

**Failure handling:**

| Scenario | Behavior |
|---|---|
| Empty attachments | No-op. No LLM call. |
| Malformed JSON | One retry with a stricter prompt. |
| Both attempts fail | Accept ALL H3s as `good`; stamp `metadata.h3_parent_fit_fallback_applied = true`. Never aborts. |
| LLM classifies an H3 with an `h3_id` not in the input | Drop the rogue classification; log warning. |

**Cost:** One LLM call per brief, ~$0.02. Skipped entirely when no H2 has any attached H3s.

**Logging:**
- `brief.h3_fit.complete` (INFO) — totals (marginal / wrong_parent / promoted / reattached / routed_to_silos)
- `brief.h3_fit.fallback` (WARN) — both LLM attempts failed
- `brief.h3_fit.rogue_id` (WARN) — LLM emitted unknown h3_id
- `brief.h3_fit.invalid` / `brief.h3_fit.llm_failed` (WARN)

### Step 9 — Authority Gap Analysis (REVISED in v2.0.3 — adds scope-aware inputs)

Universal Authority Agent with three pillars (Human/Behavioral, Risk/Regulatory, Long-Term Systems). v2.0.3 extends the agent's input set so it cannot drift outside the article's committed scope.

**Inputs (v2.0.3):**
- Aggregated heading list from Step 4 (unchanged)
- Reddit thread summaries from Step 2 as context — not as headings (unchanged)
- **Title from Step 3.5 (NEW)** — anchors the agent on the reader-facing commitment
- **Scope statement from Step 3.5 (NEW)** — including the explicit `does not cover` clause
- **`intent_type` from Step 3 (NEW)** — so the agent's pillars frame their content for the right reader mode (a "how-to" article wants action-oriented authority, not abstract risk analysis)

**System prompt addendum (NEW in v2.0.3):**

The agent's system prompt MUST include the scope_statement (with emphasis on the "does not cover" clause) and the following directive:

> Authority gap content must respect the article's scope boundary. The three pillars (Human/Behavioral, Risk/Regulatory, Long-Term Systems) should explore expertise within the scope, not adjacent to it. If a pillar would naturally produce content outside the scope, prefer leaving that pillar empty over producing off-scope content. It is acceptable to return three H3s instead of five when staying in-scope requires it.

**Output schema (REVISED in v2.0.3):**

Each emitted H3 carries a new `scope_alignment_note` string (≤200 chars) where the agent explains how the H3 stays within the scope_statement. This note is separate from — and complementary to — the post-emission scope verification pass in Step 8.5b. It is surfaced in the final `heading_structure` for any heading with `source: "authority_gap_sme"`.

**Output rules:**
- Exactly 3–5 new H3 subheadings (still 3 lower bound; up to 5 upper bound)
- Inserted immediately after the most relevant H2
- Tagged `source: "authority_gap_sme"`
- Authority gap H3s count toward the per-H2 limit of 2 H3s (with the cap-displacement rules specified in Step 8.6)
- Score is computed but `exempt: true` flag set — bypasses 0.55 relevance threshold
- Authority gap H3s are not discarded by Step 11's global cap; they MAY be removed by Step 8.5b (the new H3 scope-verification pass) when the pillar drift produces out-of-scope content.

### Step 10 — FAQ Generation (Mostly Unchanged from v1.7)

**Source A — Regex extraction (deterministic):**
- Extract sentences ending in `?` from Reddit post titles and top-comment text
- Filter: 5–25 words
- Add to candidate pool with PAA questions

**Source B — LLM concern extraction:**
- Single LLM call with all Reddit thread content
- Returns up to 10 implicit questions or concerns

**Source C — Persona gap questions (NEW):**
- Persona gap questions from Step 6 that did NOT make it into the H2 outline (either because they weren't aggregated as H2 candidates, or because they were aggregated but not selected) feed the FAQ candidate pool
- Tagged `source: "persona_gap"`

**Scoring formula (REVISED in v2.2 / Phase 2):**

```
faq_score = (0.4 × source_signal) + (0.4 × semantic_relevance) + (0.2 × novelty_bonus)

Where:
- source_signal:
    - PAA = 1.0
    - Reddit ≥50 upvotes = 0.9
    - Reddit 10–49 upvotes = 0.6
    - Reddit <10 upvotes = 0.3
    - LLM-extracted concern = 0.5
    - Persona gap question = 0.6
- semantic_relevance:
    v2.2 (Phase 2): 0.5 × cos(question, title_embedding) + 0.5 × cos(question, intent_profile_embedding)
    v2.1 fallback: cos(question, title_embedding) only — used when intent_profile is unavailable
- novelty_bonus: 1.0 if topic not in heading_structure, else 0.0
```

The `intent_profile_embedding` is built and embedded by Step 10.5 below; the orchestrator passes the same vector into `score_faqs` so both stages share a single API call.

**Selection rules (unchanged):** Top 5 by score with minimum threshold 0.5; if <3 pass, accept top 3 regardless; always output 3–5 FAQs.

### Step 10.5 — FAQ Intent Gate (NEW in v2.2 / Phase 2)

**Purpose:** Catch FAQs that are topically related to the keyword but represent a DIFFERENT stakeholder's question. The audited example: a seller-ROI article keyword shipped FAQs about creator-monetization because the underlying SERP/Reddit pool surfaced both stakeholder voices and the top-by-search-volume FAQs leaked across cohorts.

**Position in the pipeline:** runs **between** the Step 10 candidate-pool construction and `score_faqs`/`select_faqs`. The gate's `intent_profile_embedding` is the same vector that Step 10's `score_faqs` consumes for the v2.2 blended `semantic_relevance`.

**Method:** Two-stage gate.

**Stage 1 — Cosine floor (deterministic):**

1. Build the `intent_profile` text by concatenating: `intent_type + title + scope_statement + persona.primary_goal`.
2. Embed it once with `text-embedding-3-large` (single API call).
3. Embed every FAQ candidate's question (single batched API call; reused by `score_faqs` so `score_faqs` doesn't re-embed).
4. Compute `intent_alignment = cos(faq, intent_profile)` for each candidate.
5. Drop candidates with `intent_alignment < INTENT_FLOOR` (default `0.55`); record them in `metadata.faq_intent_gate_floor_rejected_count`.

**Stage 2 — LLM intent-role classifier (single batched call):**

For each cosine-floor survivor, classify into one of three intent roles:

- `matches_primary_intent` — FAQ aligns with the primary keyword's intent cluster (the expected case).
- `adjacent_intent` — FAQ is on-topic but represents a different stakeholder question. Acceptable as fallback when fewer than 3 primary FAQs survive.
- `different_audience` — FAQ targets a different stakeholder entirely (e.g. creator-monetization on a seller-ROI article). Drop.

**Output schema (strict JSON, additionalProperties: false):**

```json
{
  "verifications": [
    {
      "faq_id": "faq_<i>",
      "intent_role": "matches_primary_intent" | "adjacent_intent" | "different_audience",
      "reasoning": "string (≤200 chars)"
    }
  ]
}
```

**Routing:**

| Intent role | Action |
|---|---|
| `matches_primary_intent` | Stamp `intent_role` on the FAQItem. Surface in the brief output. |
| `adjacent_intent` | Stamp `intent_role`. Kept ONLY as fallback when fewer than 3 `matches_primary_intent` survive (relaxation path). Otherwise dropped. |
| `different_audience` | Drop. Counted in `metadata.faq_intent_gate_llm_rejected_count`. |

**Relaxation:** when fewer than 3 `matches_primary_intent` survivors exist, the highest-scoring `adjacent_intent` candidates are added until the count reaches 3 (PRD §5 Step 10's `MIN_FAQS_FALLBACK`). When relaxation fires, `metadata.faq_intent_gate_relaxation_applied = true`.

**Failure handling:**

| Scenario | Behavior |
|---|---|
| Empty candidate pool | No-op. |
| Intent-profile embed fails | Skip the gate entirely; pass all candidates through. Stamp `metadata.faq_intent_gate_relaxation_applied = false`. The fallback is logged but not surfaced as an explicit metadata field; consumers infer it from `floor_rejected_count == 0` AND `llm_rejected_count == 0` AND non-empty pool. |
| FAQ candidate embed fails | Same as intent-profile embed failure — skip the gate. |
| LLM call fails (after one retry) | Keep all cosine-floor survivors; stamp each as `matches_primary_intent`. Run continues normally. |
| LLM emits `intent_role` for an unknown `faq_id` | Drop the rogue classification; log warning. |

**Cost:** 1 embedding API call (intent profile) + 1 embedding API call (FAQ candidates, reused by `score_faqs`) + 1 LLM call (intent-role classification, only fires when at least one candidate survives the cosine floor). Total: ~$0.01–$0.02.

**Logging:**
- `brief.faq_intent_gate.complete` (INFO) — input / floor_rejected / llm_rejected / primary_kept / adjacent_kept_via_relaxation
- `brief.faq_intent_gate.embed_skipped` (WARN) — intent-profile embed failed; gate skipped
- `brief.faq_intent_gate.llm_fallback` (WARN) — both LLM attempts failed
- `brief.faq_intent_gate.floor_rejected` (DEBUG) — per-FAQ alignment vs floor for tuning

### Step 11 — Structure Assembly (Unchanged from v1.7)

Universal structural constants, intent-aware H2/H3 caps, how-to sequential reordering, global subheading cap enforcement. See v1.7 Section 5 Step 8 for full specification.

| Rule | Value |
|---|---|
| Max content H2s (capped intents) | 6 |
| Max content H2s (listicle, how-to) | Uncapped |
| Max H3s per H2 | 2 |
| Authority gap H3s count toward per-H2 limit | Yes |
| Global content subheading cap (capped intents) | 15 |
| Global content subheading cap (listicle, how-to) | 20 |
| FAQ H2 + FAQ H3s | Outside both caps |

**Word budget:** Maximum 2,500 words across content sections; FAQ section excluded; enforcement is the Writer Module's responsibility.

#### Step 11.0 — H2 Framing Validator (NEW in v2.1)

**Purpose:** Enforce per-intent H2 framing on the surviving outline. After Step 7.5's anchor reservation + Step 8's MMR + Step 8.5's scope verification, the H2 set is finalized — but individual H2s may still be framed as questions when the template wants action verbs (or vice-versa). The framing validator catches this before how-to reordering and Step 11.x title casing run.

**Position in the pipeline:** runs **after Step 8.5 scope verification** and **before** the how-to reorder LLM call (Step 8.6 prep) and **before** Step 11.x title casing. Reorder operates on already-correctly-framed H2s; title casing then normalizes capitalization on the rewritten text.

**Method:**

1. **Regex pre-check.** For each selected H2, evaluate the template's `h2_framing_rule` against the H2 text:

   | `h2_framing_rule` | Pass condition |
   |---|---|
   | `verb_leading_action` | First lexical token is an action verb (whitelist + conservative `e/t/n/d/p/y/h/w/ze/fy/ate/ize/ise` stem heuristic) OR an explicit `Step <N>:` prefix. Rejects question-leading and article-leading openers ("What…", "How…", "The…", "Your…", "Best…"). |
   | `ordinal_then_noun_phrase` | Leading numeral followed by `.`/`)`/space, OR `#<N>`, OR `Top <N>`, OR `Number <N>`. |
   | `axis_noun_phrase` | Short noun-phrase (≤8 words), no leading question word, not a multi-word verb phrase. Single-word or two-word headings always pass (covers single-word axes like "Pricing", "Support"). |
   | `question_or_topic_phrase` | Any non-empty heading. |
   | `buyer_education_phrase` | Either question form OR axis-style noun-phrase. |
   | `no_constraint` | Always passes (used by `news` / `local-seo`). |

2. **Single batched LLM rewrite.** All failing H2s are sent in one Claude call with a strict JSON contract:

   ```json
   {"rewrites": [{"index": 0, "text": "Set Up Your TikTok Shop"}, ...]}
   ```

   The prompt instructs the model to preserve each H2's *topic* exactly (the rewrite must not change what the section covers) while satisfying the framing rule. Per-rule prompt hints are appended (e.g. how-to: "start with an action verb"; comparison: "strip leading verbs and articles; produce a short axis noun-phrase").

3. **Re-check.** Each rewrite is re-validated against the same regex. A rewrite that passes replaces the H2 text in place. A rewrite that still fails the regex → the H2 keeps its original text and the index lands in `framing_rewrites_accepted_with_violation` (logged as a warning, never aborts).

**Failure handling:**

| Scenario | Behavior |
|---|---|
| Template's `h2_framing_rule` is `no_constraint` | NOOP. No regex check, no LLM call. |
| All H2s already pass the regex | NOOP. No LLM call (cost optimization + flake reduction). |
| LLM call fails or returns malformed JSON | Log + accept all originals; flag every original index in `framing_rewrites_accepted_with_violation`. |
| LLM returns rewrite for some indices but not others | The unspecified indices fall through to `framing_rewrites_accepted_with_violation`; specified indices follow the re-check rule above. |
| Rewrite re-check fails | Original text preserved; index added to `framing_rewrites_accepted_with_violation`. |

**Cost:** Zero or one LLM call per brief, ~$0.01–$0.02 when invoked. Skipped entirely when no H2 fails the regex.

**Metadata:**
- `framing_rewrites_applied: int` — H2s whose text was rewritten (and the rewrite passed).
- `framing_rewrites_accepted_with_violation: int` — H2s where the rewrite still failed the regex AND the LLM-failure case.
- `anchor_slots_total: int` and `anchor_slots_reserved_count: int` (from Step 7.5) round out the diagnostic trio surfaced for each run.

**Logging:**
- `brief.framing.complete` (INFO) — totals per run.
- `brief.framing.rewritten` (INFO) — per-H2 before/after.
- `brief.framing.violation_accepted` (WARN) — chronic offenders for tuning.
- `brief.framing.llm_failed` (WARN) — LLM call exception path.

#### Step 11.x — Title Case Normalization (NEW in v2.0.3)

After every prior heading-processing step has run (polish, authority gap injection, scope verification, H3 selection, structure assembly), apply **AP-style / Chicago Manual of Style title case** to every `text` field on every entry in `heading_structure` — H1, H2, H3, FAQ headers, FAQ questions — uniformly.

Title case rules (AP/Chicago):
- First and last words always capitalized
- Principal words (nouns, verbs, adjectives, adverbs, pronouns, subordinating conjunctions) capitalized
- Articles (`a`, `an`, `the`), coordinating conjunctions (`and`, `but`, `or`, `for`, `nor`, `so`, `yet`), and prepositions of ≤3 letters lowercase — except when first or last word
- Hyphenated compounds: capitalize each significant element

**Reference implementation:** the Python `titlecase` library (https://pypi.org/project/titlecase/) implements AP-style title case correctly out of the box; add it to `requirements.txt`. The normalization step is a single call per heading and adds <1ms total per brief.

**Position in the pipeline:** title case normalization is the LAST heading-text mutation. It runs after Step 9's authority gap injection, after Step 8.5b's scope verification, after Step 8.6's H3 selection, after Step 11's structure assembly. No subsequent step modifies heading text.

**Scope:** applies to `heading_structure[].text` only. It does NOT apply to:
- `silo_candidates[].suggested_keyword` (content roadmap candidates may use the user's casing)
- `silo_candidates[].source_headings[].text` (preserved from the original brief output for audit)
- `discarded_headings[].text` (preserved verbatim for audit)
- `faqs[].question` (FAQ questions are sentences ending with `?`, not headings — they keep sentence case)

The brief's top-level `title` field (Step 3.5 output) is already produced in title case by the title generation prompt and does not require additional normalization, but is passed through `titlecase` for safety.

### Step 12 — Silo Cluster Identification (REWRITTEN — Now Reuses Step 5 Regions)

**Purpose:** Convert non-selected coverage graph regions and scope-verification rejects into a prioritized roadmap of supporting cluster articles. Reuses regions computed in Step 5 — no additional clustering or embedding cost. Adds explicit filtering, search-demand validation, and a per-candidate viability check so the output is a defensible roadmap rather than a noisy list.

**Input:** All regions from Step 5 that did NOT contribute a selected H2 to the final outline, plus all candidates moved to `discarded_headings` with `discard_reason: "scope_verification_out_of_scope"`. The discard reason filtering in Step 12.1 governs which headings actually proceed.

**Process:** Run Steps 12.1 → 12.4 in order, then format per Step 12.6. Step 12.5 is reserved for v2.1.

#### Step 12.1 — Discard Reason Filtering

A heading's `discard_reason` determines whether it can become silo material. Re-routing the wrong reasons would generate articles that compete with the parent brief or surface noise.

| Discard Reason | Silo Eligible | Reasoning |
|---|---|---|
| `above_restatement_ceiling` | No | Paraphrases the title; routing to silo would generate articles competing with the parent. |
| `region_restates_title` | No | Same reasoning at the region level. |
| `below_relevance_floor` | No | Off-topic noise; not a future article on this subject. |
| `region_off_topic` | No | Same reasoning at the region level. |
| `scope_verification_out_of_scope` | Yes — high priority | Topically relevant, in the eligible band, but answers a different reader question. Highest-confidence silo material. |
| `below_priority_threshold` | Conditional | Eligible only if the heading's region did not contribute a selected H2. If the region did contribute, this heading is redundant with that H2 and excluded. |
| `global_cap_exceeded` | Yes — medium priority | Cut for length, not quality. |
| `low_cluster_coherence` | No | Already evaluated and rejected; do not re-evaluate. |
| `duplicate` | No | Lexical duplicate. |
| `displaced_by_authority_gap_h3` | No | H3-level signal, not H2-worthy. |
| `h3_below_parent_relevance_floor` | No | H3-level signal. |
| `h3_above_parent_restatement_ceiling` | No | H3-level signal. |

Only headings with "Yes" or "Conditional" eligibility proceed to Step 12.2. Headings filtered out at this step are counted in `metadata.silo_candidates_rejected_by_discard_reason`.

#### Step 12.2 — Cluster Formation

For each non-selected, non-eliminated region from Step 5 whose members survived Step 12.1, compute:

- `cluster_coherence_score` = average pairwise cosine similarity between region members
- `suggested_keyword` = the centroid heading (highest average similarity to all other region members)
- `recommended_intent` = applied via the same rules-based signal mapping from Step 3, using the region's heading patterns

For scope-verification rejects, treat each as a singleton silo candidate with `suggested_keyword = original heading text` and `cluster_coherence_score = 1.0`. Singletons from `scope_verification_out_of_scope` are exempt from the minimum-2-heading rule because they have already been evaluated and confirmed as on-topic-but-out-of-scope.

**Cluster quality rules:**

| Rule | Value |
|---|---|
| Minimum headings per cluster | 2 (singletons from scope verification are exempt) |
| Minimum cluster coherence score | 0.60 |
| Maximum silo candidates per brief | 10 |
| Review recommended threshold | Coherence between 0.60 and 0.70 |

- Clusters below 0.60 coherence are added to `discarded_headings` with `discard_reason: "low_cluster_coherence"`
- If more than 10 clusters qualify, take the 10 with the highest coherence scores
- If `cluster_coherence_score` is between 0.60 and 0.70, flag `review_recommended: true`

#### Step 12.3 — Search Demand Validation

A silo candidate that no one searches for is not a content opportunity. Compute a `search_demand_score` from signals already present on member headings:

```
search_demand_score =
    0.30 × normalized_max_serp_frequency
  + 0.25 × normalized_max_llm_consensus
  + 0.20 × paa_presence_indicator
  + 0.15 × autocomplete_presence_indicator
  + 0.10 × reddit_discussion_indicator
```

Where:
- `normalized_max_serp_frequency` = max `serp_frequency` among member headings, divided by 20
- `normalized_max_llm_consensus` = max `llm_fanout_consensus` among member headings, divided by 4
- `paa_presence_indicator` = 1.0 if any member heading has `source: "paa"`, else 0.0
- `autocomplete_presence_indicator` = 1.0 if any member heading has `source` in {`autocomplete`, `keyword_suggestion`}, else 0.0
- `reddit_discussion_indicator` = 1.0 if any member heading has `source: "reddit"`, else 0.0

Silo candidates with `search_demand_score < 0.30` are filtered out — they have weak external evidence of search demand. This is a hard threshold, configurable per Section 12.6 of the PRD's Python Implementation Notes. Candidates filtered out at this step are counted in `metadata.silo_candidates_rejected_by_search_demand`.

#### Step 12.4 — Independent Article Viability Check

For each silo candidate that passes Steps 12.1–12.3, run a single LLM call to verify the candidate would make a defensible standalone article — distinct from the parent brief's intent, not a thin spin-off, and substantive enough to support its own outline.

**Inputs:**
- The silo candidate's `suggested_keyword`
- The current brief's `title` and `scope_statement` (so the LLM can verify distinct intent)
- The member headings of the silo candidate

**Output schema (strict, additionalProperties: false):**

```json
{
  "candidate_keyword": "string",
  "viable_as_standalone_article": true,
  "reasoning": "string (≤150 chars)",
  "estimated_intent": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial"
}
```

**Failure handling:**

| Scenario | Behavior |
|---|---|
| LLM returns malformed JSON | One retry; on second failure default `viable_as_standalone_article: true` and flag `metadata.silo_viability_fallback_applied: true` |
| LLM call timeout | Same as malformed JSON |

Candidates classified as `viable_as_standalone_article: false` are excluded from the final `silo_candidates` output array but logged in `metadata.silo_candidates_rejected_by_viability_check`.

Viability checks for distinct candidates are independent and SHOULD run in parallel — see Section 8 for performance impact.

#### Step 12.5 — Cross-Brief Deduplication (Deferred to v2.1)

Cross-brief deduplication of silo candidates requires a Supabase table for tracking silo candidates across briefs over time. Out of scope for v2.0; flagged as a v2.1 requirement.

**Future v2.1 logic:** maintain a `silo_candidates` table keyed by `client_id` + `suggested_keyword` embedding. On each new brief, check cosine similarity (≥ 0.85) against existing entries. Increment `cross_brief_occurrence_count` on duplicates. Surface candidates with high occurrence counts as priority article seeds in the platform UI.

**For v2.0:** every silo candidate's `cross_brief_occurrence_count` defaults to 1.

#### Step 12.6 — Output Format

Each silo candidate carries:
- `suggested_keyword`
- `cluster_coherence_score`
- `review_recommended`
- `recommended_intent`
- `routed_from`: `"non_selected_region"` (region didn't win H2 competition), `"scope_verification"` (H2 rejected by Step 8.5 scope check), or `"scope_verification_h3"` (Authority Gap H3 rejected by Step 8.5b scope check — NEW in v2.0.3)
- `source_headings[]` (member headings with text, source, title_relevance, heading_priority, discard_reason)
- `discard_reason_breakdown`: object mapping `discard_reason` values to counts among member headings
- `search_demand_score` (float, 0.0–1.0)
- `viable_as_standalone_article` (boolean)
- `viability_reasoning` (string, ≤150 chars)
- `estimated_intent` (one of the 8 intent types)
- `cross_brief_occurrence_count` (integer, always 1 for v2.0; populated by v2.1)

The `routed_from: "scope_verification"` flag remains particularly valuable — these are headings that almost made it into a brief but represent genuinely different articles, so they're high-confidence silo seeds. Combined with the `search_demand_score` and the viability check, the silo output becomes a prioritized roadmap rather than a noisy list.

---

## 6. Output Schema

```json
{
  "schema_version": "2.3",
  "keyword": "string",
  "title": "string",
  "scope_statement": "string",
  "title_rationale": "string",
  "intent_type": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial",
  "intent_confidence": 0.0,
  "intent_review_required": false,
  "intent_format_template": {
    "intent": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial",
    "h2_pattern": "sequential_steps | ranked_items | parallel_axes | topic_questions | buyer_education_axes | feature_benefit | place_bound_topics | news_lede",
    "h2_framing_rule": "verb_leading_action | ordinal_then_noun_phrase | axis_noun_phrase | question_or_topic_phrase | buyer_education_phrase | no_constraint",
    "ordering": "strict_sequential | logical | none",
    "min_h2_count": 4,
    "max_h2_count": 12,
    "anchor_slots": ["string"],
    "description": "string"
  },
  "persona": {
    "description": "string",
    "background_assumptions": ["string"],
    "primary_goal": "string"
  },
  "heading_structure": [
    {
      "level": "H1 | H2 | H3",
      "text": "string (Title Case — AP/Chicago style; see Step 11.x)",
      "type": "content | faq-header | faq-question | conclusion",
      "source": "serp | paa | reddit | authority_gap_sme | synthesized | autocomplete | keyword_suggestion | llm_fanout_chatgpt | llm_fanout_claude | llm_fanout_gemini | llm_fanout_perplexity | llm_response_chatgpt | llm_response_claude | llm_response_gemini | llm_response_perplexity | persona_gap",
      "original_source": "string | null",
      "title_relevance": 0.0,
      "exempt": false,
      "serp_frequency": 0,
      "avg_serp_position": 0.0,
      "llm_fanout_consensus": 0,
      "information_gain_score": 0.0,
      "heading_priority": 0.0,
      "region_id": "string | null",
      "scope_classification": "in_scope | borderline | null (populated for content H2s by Step 8.5; for content H3s with source='authority_gap_sme' by Step 8.5b — NEW in v2.0.3; null otherwise)",
      "scope_alignment_note": "string | null (populated only for source='authority_gap_sme' entries by Step 9; ≤200 chars — NEW in v2.0.3)",
      "parent_h2_text": "string | null",
      "parent_relevance": 0.0,
      "parent_fit_classification": "good | marginal | null (NEW in v2.2 / Phase 2 — populated only on H3 entries that the Step 8.7 LLM tagged `marginal`; null on `good` H3s and on H1/H2)",
      "order": 0
    }
  ],
  "faqs": [
    {
      "question": "string",
      "source": "paa | reddit | llm_extracted | persona_gap",
      "faq_score": 0.0,
      "intent_role": "matches_primary_intent | adjacent_intent | null (NEW in v2.2 / Phase 2 — set by Step 10.5; null when the gate's LLM call failed and the fallback accepted everything)"
    }
  ],
  "structural_constants": {
    "conclusion": {
      "type": "conclusion",
      "level": null,
      "text": "[Conclusion placeholder]"
    }
  },
  "format_directives": {
    "require_bulleted_lists": true,
    "require_tables": true,
    "min_lists_per_article": 2,
    "min_tables_per_article": 1,
    "preferred_paragraph_max_words": 80,
    "answer_first_paragraphs": true,
    "min_h2_body_words": 180
  },
  "discarded_headings": [
    {
      "text": "string",
      "source": "string",
      "original_source": "string | null",
      "title_relevance": 0.0,
      "serp_frequency": 0,
      "avg_serp_position": 0.0,
      "llm_fanout_consensus": 0,
      "heading_priority": 0.0,
      "region_id": "string | null",
      "discard_reason": "below_relevance_floor | above_restatement_ceiling | region_off_topic | region_restates_title | below_priority_threshold | global_cap_exceeded | duplicate | low_cluster_coherence | scope_verification_out_of_scope | h3_below_parent_relevance_floor | h3_above_parent_restatement_ceiling | displaced_by_authority_gap_h3"
    }
  ],
  "silo_candidates": [
    {
      "suggested_keyword": "string",
      "cluster_coherence_score": 0.0,
      "review_recommended": false,
      "recommended_intent": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial",
      "routed_from": "non_selected_region | scope_verification",
      "source_headings": [
        {
          "text": "string",
          "source": "string",
          "title_relevance": 0.0,
          "heading_priority": 0.0,
          "discard_reason": "string | null"
        }
      ],
      "discard_reason_breakdown": {
        "below_priority_threshold": 0,
        "global_cap_exceeded": 0,
        "scope_verification_out_of_scope": 0
      },
      "search_demand_score": 0.0,
      "viable_as_standalone_article": true,
      "viability_reasoning": "string",
      "estimated_intent": "informational | listicle | how-to | comparison | ecom | local-seo | news | informational-commercial",
      "cross_brief_occurrence_count": 1
    }
  ],
  "metadata": {
    "word_budget": 2500,
    "faq_count": 0,
    "h2_count": 0,
    "h3_count": 0,
    "total_content_subheadings": 0,
    "discarded_headings_count": 0,
    "silo_candidates_count": 0,
    "silo_candidates_rejected_by_discard_reason": 0,
    "silo_candidates_rejected_by_search_demand": 0,
    "silo_candidates_rejected_by_viability_check": 0,
    "silo_viability_fallback_applied": false,
    "competitors_analyzed": 20,
    "reddit_threads_analyzed": 0,
    "h2_shortfall": false,
    "h2_shortfall_reason": "string | null",
    "h3_count_average": 0.0,
    "h2s_with_zero_h3s": 0,
    "regions_detected": 0,
    "regions_eliminated_off_topic": 0,
    "regions_eliminated_restate_title": 0,
    "regions_contributing_h2s": 0,
    "scope_verification_borderline_count": 0,
    "scope_verification_rejected_count": 0,
    "llm_fanout_queries_captured": {
      "chatgpt": 0,
      "claude": 0,
      "gemini": 0,
      "perplexity": 0
    },
    "llm_response_subtopics_extracted": {
      "chatgpt": 0,
      "claude": 0,
      "gemini": 0,
      "perplexity": 0
    },
    "intent_signals": {
      "shopping_box": false,
      "news_box": false,
      "local_pack": false,
      "featured_snippet": false,
      "comparison_tables": false
    },
    "embedding_model": "text-embedding-3-large",
    "relevance_floor_threshold": 0.55,
    "restatement_ceiling_threshold": 0.78,
    "inter_heading_threshold": 0.75,
    "edge_threshold": 0.65,
    "mmr_lambda": 0.7,
    "low_serp_coverage": false,
    "reddit_unavailable": false,
    "llm_fanout_unavailable": {
      "chatgpt": false,
      "claude": false,
      "gemini": false,
      "perplexity": false
    },
    "anchor_slots_total": 0,
    "anchor_slots_reserved_count": 0,
    "framing_rewrites_applied": 0,
    "framing_rewrites_accepted_with_violation": 0,
    "h3_parent_fit_marginal_count": 0,
    "h3_parent_fit_wrong_parent_count": 0,
    "h3_parent_fit_promoted_count": 0,
    "h3_parent_fit_fallback_applied": false,
    "faq_intent_gate_floor_rejected_count": 0,
    "faq_intent_gate_llm_rejected_count": 0,
    "faq_intent_gate_relaxation_applied": false,
    "faq_intent_floor_threshold": 0.55
  }
}
```

---

## 7. Failure Mode Handling

| Scenario | Behavior |
|---|---|
| DataForSEO returns <10 results | Continue with available; flag `low_serp_coverage: true` |
| DataForSEO returns 0 results | Abort with structured error; do not pass to writer |
| Reddit returns 0 threads | Continue without Reddit; flag `reddit_unavailable: true` |
| Any individual LLM fan-out call fails or returns empty | Continue with remaining LLMs; flag the specific LLM in `llm_fanout_unavailable` |
| All 4 LLM fan-out calls fail | Continue without LLM fan-out data entirely; flag all 4 |
| Title generation LLM fails twice | Abort with `title_generation_failed` |
| Persona generation LLM fails twice | Continue with empty persona output; log warning |
| All headings rejected by relevance/restatement gates (no eligible candidates) | Lower relevance floor to 0.40, retry; if still <3 eligible, abort with `no_eligible_candidates` |
| Selection algorithm produces fewer H2s than target | Accept shortfall; flag `h2_shortfall: true` with reason |
| Scope verification LLM fails twice | Accept all selected H2s as `in_scope`; log warning |
| Step 8.5b H3 scope verification LLM fails twice | Accept all Authority Gap H3s as `in_scope`; log warning. Do not abort; the parent brief is already valid. |
| Authority Agent returns malformed JSON | Retry once with stricter prompt; on second failure, return brief without authority gap headings + flag |
| OpenAI embeddings timeout | Retry 3x with exponential backoff; on final failure, abort |
| Authority Agent returns wrong heading count | Truncate to 5 if >5; retry if <3; on retry failure, accept what was returned |
| Intent confidence <0.50 even after LLM check | Default to `informational`; flag `intent_review_required: true` |
| No silo clusters meet minimum coherence threshold | Return empty `silo_candidates` array; do not abort |
| Silo viability check LLM fails twice (per candidate) | Default `viable_as_standalone_article: true`, set `metadata.silo_viability_fallback_applied: true`, log warning; do not abort |
| End-to-end exceeds 120s | Abort and notify user |

---

## 8. Performance Targets

**Trigger model:** Synchronous, user-initiated, runs in parallel with the keyword/entity/quadgram research module.

| Stage | Target | Max |
|---|---|---|
| End-to-end brief generation | 75s | 120s |
| SERP + Reddit + Autocomplete + 4-LLM Fan-Out scrape (parallel) | 30s | 60s |
| Intent classification + Title generation (sequential) | 8s | 15s |
| Embedding + graph construction + scoring | 5s | 10s |
| Persona generation | 5s | 10s |
| MMR selection + scope verification | 8s | 15s |
| H3 selection (Step 8.6, embedding math + MMR only) | 1–2s | 4s |
| Authority agent | 15s | 30s |
| Structure assembly + silo identification | 4s | 8s |
| Silo viability checks (Step 12.4, up to 10 candidates in parallel) | 5–10s | 15s |

The 4 LLM fan-out calls run concurrently with each other and with SERP/Reddit/Autocomplete. Title generation is sequential after intent classification (it uses intent type as input). Persona generation runs after graph construction completes (it benefits from seeing the candidate pool). Selection, scope verification, H3 selection (Step 8.6), and authority agent run sequentially.

H3 selection (Step 8.6) is pure embedding math and MMR — no new LLM calls — and adds approximately 1–2 seconds to the structure assembly stage. End-to-end target stays at 75s; 120s ceiling preserved.

Silo viability checks (Step 12.4) add 5–10s when run in parallel (recommended) or 80–85s end-to-end if run sequentially (not recommended). Each viability check is a single Claude call (~$0.01–$0.02) over a small payload (suggested_keyword + title + scope + member headings); they are independent across candidates and SHOULD be issued concurrently with `asyncio.gather`. With parallel execution, end-to-end target stays at 75s.

---

## 9. Cost Model

| Component | Cost per Brief |
|---|---|
| DataForSEO SERP (depth 20, standard queue) | ~$0.001 |
| DataForSEO PAA | ~$0.001 |
| DataForSEO Reddit search | ~$0.001 |
| DataForSEO Autocomplete | ~$0.001 |
| DataForSEO Keyword Suggestions | ~$0.001 |
| DataForSEO LLM Responses (4 LLMs parallel) | ~$0.08–$0.20 |
| LLM extraction of response content (4 calls) | ~$0.04 |
| OpenAI embeddings (text-embedding-3-large) | <$0.001 |
| **Title + scope statement generation (NEW)** | $0.03–$0.05 |
| **Persona generation (NEW)** | $0.02–$0.04 |
| **Scope verification — H2 pass (Step 8.5)** | $0.02–$0.04 |
| **Scope verification — Authority Gap H3 pass (Step 8.5b, NEW in v2.0.3)** | ~$0.02 |
| LLM calls (intent borderline, heading polish, authority agent, FAQ extraction, how-to reordering) | $0.10–$0.30 |
| Coverage graph + Louvain clustering | $0.00 (CPU only, milliseconds) |
| Silo cluster identification | $0.00 (reuses Step 5 regions) |
| **Silo viability checks (Step 12.4, up to 10 candidates × $0.01–$0.02 each)** | $0.05–$0.20 |
| Title case normalization (Step 11.x, NEW in v2.0.3) | $0.00 (CPU only via `titlecase` lib) |
| **Estimated total per brief** | **$0.37–$0.91** |
| **Budget ceiling** | **$1.00** |

**Monthly operational cost at 10–20 briefs/day:** ~$111–$546/month

Cost increase from v1.7's $0.19–$0.53 range to v2.0.3's $0.37–$0.91 range reflects five new LLM call sites (title, persona, H2 scope verification, H3 scope verification added in v2.0.3, silo viability checks). The new H3 scope-verification pass adds a single ~$0.02 LLM call per brief; title case normalization is pure-CPU and free. Still under the $1.00 ceiling.

---

## 10. Volume and Scale Assumptions

- **Current volume:** 10–20 briefs/day
- **Trigger source (v2.0):** User-initiated via parent platform UI
- **Trigger source (v2.1+):** Cron job from Supabase database
- **Concurrency:** No requirement for v2.0 — sequential per-user execution acceptable

---

## 11. Business Rules Summary

| Rule | Value |
|---|---|
| Locale | English / United States |
| Min input length | Non-empty, non-whitespace |
| Max input length | 150 characters |
| SERP results analyzed | 20 |
| Reddit threads analyzed | 5 |
| LLM fan-out providers | ChatGPT, Claude, Gemini, Perplexity |
| Intent types | 8 (informational, listicle, how-to, comparison, ecom, local-seo, news, informational-commercial) |
| Intent confidence threshold for review flag | 0.75 |
| **Intent classifier keyword pattern pre-check (Step 3.1, NEW in v2.0.3)** | See pattern table below |
| **Step 3.1 keyword pattern: `how to`, `how do i`, `how can i`, `ways to`, `steps to`, `guide to`** | → `how-to` @ confidence 0.95 |
| **Step 3.1 keyword pattern: `what is`, `what are`, `what does`, `definition of`** | → `informational` @ confidence 0.90 |
| **Step 3.1 keyword pattern: starts with `best`, `top`, or `\d+\s+plural-noun`** | → `listicle` @ confidence 0.90 |
| **Step 3.1 keyword pattern: contains ` vs `, ` versus `, ` or `, `compared to`** | → `comparison` @ confidence 0.90 |
| **Step 3.1 match → skip Step 3.2 SERP-feature classification** | Yes |
| Embedding model | OpenAI text-embedding-3-large |
| **Title + scope statement generated per brief** | Yes (Step 3.5) |
| **Title max length** | 100 chars |
| **Scope statement must include `does not cover` clause** | Yes |
| **Relevance floor (heading-to-title cosine minimum)** | 0.55 |
| **Restatement ceiling (heading-to-title cosine maximum)** | 0.78 |
| **Inter-heading anti-redundancy threshold (max pairwise cosine between selected H2s)** | 0.75 |
| **Coverage graph edge threshold** | 0.65 |
| **Region uniqueness in selection** | Max 1 H2 per coverage graph region |
| **MMR lambda** | 0.7 |
| **Scope verification runs after MMR selection** | Yes (Step 8.5) |
| **Authority Gap H3 scope verification pass (Step 8.5b, NEW in v2.0.3)** | Yes |
| **Authority Agent receives `title`, `scope_statement`, `intent_type` (NEW in v2.0.3)** | Yes |
| **Authority Agent emits `scope_alignment_note` per H3 (NEW in v2.0.3)** | Yes (≤200 chars) |
| **Heading capitalization (Step 11.x, NEW in v2.0.3)** | Title Case (AP / Chicago Manual of Style) |
| **Title-case normalization library** | `titlecase` (PyPI) |
| **H3 parent_relevance floor (heading-to-parent-H2 cosine minimum)** | 0.60 |
| **H3 parent_relevance ceiling (heading-to-parent-H2 cosine maximum)** | 0.85 |
| **Inter-H3 anti-redundancy threshold (max pairwise cosine between H3s under one H2)** | 0.78 |
| **H3 selection runs per parent H2 (Step 8.6)** | Yes |
| Authority gap headings bypass relevance filter | Yes (still scored) |
| Authority gap headings per brief | 3–5 |
| Authority gap H3s count toward per-H2 limit | Yes |
| Authority gap H3s ever discarded | Never |
| Max content H2s (capped intents) | 6 |
| Max content H2s (listicle, how-to) | Uncapped |
| Max H3s per H2 (standard) | 2 |
| Max H3s per H2 (Authority Gap overflow only) | 3 (per Step 8.6 cap-displacement edge case) |
| H3s required per H2 | No |
| **H2 shortfall handling** | Accept shortfall; flag in metadata; do not relax thresholds or pad with synthetic content |
| FAQ counts toward H2 budget | No |
| FAQ counts toward global subheading cap | No |
| Conclusion is an H2 | No |
| Min FAQs | 3 |
| Max FAQs | 5 |
| Global content subheading cap (capped intents) | 15 |
| Global content subheading cap (listicle, how-to) | 20 |
| Max article word count | 2,500 (FAQ excluded) |
| **Silo candidates reuse Step 5 regions** | Yes (no additional clustering cost) |
| Silo candidate sources | Non-selected regions + scope-verification rejects |
| **Silo discard reason filtering (Step 12.1)** | Yes — only specified `discard_reason` values eligible |
| Min headings per silo cluster | 2 (singletons from scope verification exempt) |
| Min cluster coherence score | 0.60 |
| **Silo search demand minimum threshold (Step 12.3)** | 0.30 |
| **Silo viability check per candidate (Step 12.4)** | Yes |
| **Cross-brief silo deduplication (Step 12.5)** | Deferred to v2.1 |
| Max silo candidates per brief | 10 |
| Review recommended threshold | Coherence between 0.60 and 0.70 |
| **ICP context input** | Not accepted; brief generator derives hypothetical searcher from topic itself |

---

## 12. Python Implementation Notes

This section provides reference implementations for the core mathematical operations. These are not exhaustive but anchor the engineering spec.

### 12.1 Required Libraries

```python
# Core
openai          # text-embedding-3-large + LLM calls
numpy           # vector math
networkx        # graph construction + Louvain community detection
pydantic        # typed data models throughout pipeline

# Optional / fallback
scikit-learn    # alternative clustering (HDBSCAN, agglomerative) if Louvain proves unstable
```

### 12.2 Embedding Generation

```python
from openai import OpenAI
import numpy as np

client = OpenAI()

def embed(texts: list[str]) -> np.ndarray:
    """Returns (n_texts, 1536) array of unit-normalized embeddings."""
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=texts
    )
    embeddings = np.array([e.embedding for e in response.data])
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / norms
```

### 12.3 Pre-filtering by Relevance + Restatement Gates

```python
def filter_eligible(
    candidate_embeddings: np.ndarray,
    title_embedding: np.ndarray,
    relevance_floor: float = 0.55,
    restatement_ceiling: float = 0.78,
) -> tuple[np.ndarray, list[int], list[int]]:
    """
    Returns:
        - eligible_mask: boolean array marking eligible candidates
        - rejected_below_floor: indices rejected for being off-topic
        - rejected_above_ceiling: indices rejected for restating title
    """
    title_relevances = candidate_embeddings @ title_embedding
    eligible_mask = (title_relevances >= relevance_floor) & (title_relevances <= restatement_ceiling)
    rejected_below = np.where(title_relevances < relevance_floor)[0].tolist()
    rejected_above = np.where(title_relevances > restatement_ceiling)[0].tolist()
    return eligible_mask, rejected_below, rejected_above
```

### 12.4 Coverage Graph Construction + Louvain Community Detection

```python
import networkx as nx
from networkx.algorithms.community import louvain_communities

def build_coverage_graph(
    embeddings: np.ndarray,
    edge_threshold: float = 0.65,
) -> nx.Graph:
    """Build undirected graph with edges between similar candidates."""
    n = len(embeddings)
    sim = embeddings @ embeddings.T
    
    G = nx.Graph()
    G.add_nodes_from(range(n))
    
    # Vectorized edge construction
    rows, cols = np.where(np.triu(sim > edge_threshold, k=1))
    edges = [(int(r), int(c), {"weight": float(sim[r, c])}) for r, c in zip(rows, cols)]
    G.add_edges_from(edges)
    
    return G

def detect_regions(G: nx.Graph, resolution: float = 1.0, seed: int = 42) -> list[set[int]]:
    """Louvain community detection. Returns list of node-index sets."""
    return louvain_communities(G, resolution=resolution, seed=seed)
```

### 12.5 MMR Selection with Hard Constraints

```python
def select_h2s_mmr(
    candidates: list[dict],         # each has 'embedding', 'priority_score', 'region_id'
    target_count: int,
    inter_heading_threshold: float = 0.75,
    mmr_lambda: float = 0.7,
) -> list[dict]:
    """Greedy MMR selection with region uniqueness and pairwise constraints."""
    selected: list[dict] = []
    selected_regions: set = set()
    selected_embeddings: list[np.ndarray] = []
    eligible = list(candidates)
    
    while eligible and len(selected) < target_count:
        best_score = -float('inf')
        best_idx = None
        
        for i, cand in enumerate(eligible):
            if cand['region_id'] in selected_regions:
                continue
            
            if selected_embeddings:
                max_pairwise = max(
                    float(cand['embedding'] @ s) for s in selected_embeddings
                )
                if max_pairwise > inter_heading_threshold:
                    continue
                redundancy = max_pairwise
            else:
                redundancy = 0.0
            
            mmr = mmr_lambda * cand['priority_score'] - (1 - mmr_lambda) * redundancy
            
            if mmr > best_score:
                best_score = mmr
                best_idx = i
        
        if best_idx is None:
            break
        
        chosen = eligible.pop(best_idx)
        selected.append(chosen)
        selected_regions.add(chosen['region_id'])
        selected_embeddings.append(chosen['embedding'])
    
    return selected
```

### 12.6 Threshold Tuning Note

All thresholds (`0.55`, `0.78`, `0.75`, `0.65`, `0.7`) are starting defaults derived from prior work with `text-embedding-3-large` on similar content. The implementation must:

- Make every threshold a configuration value (not a hardcoded constant)
- Log every rejection at every gate with the heading text and the score that triggered the rejection
- Provide a "tuning mode" output that surfaces all candidate scores so operators can adjust thresholds based on real production behavior

Expect first-week tuning. Pay particular attention to the restatement ceiling (0.78) — this is the most consequential threshold and the most sensitive to seed phrasing patterns.

---

## 13. What This PRD Does Not Cover

To be addressed in the engineering implementation spec:
- Authentication / API key management for DataForSEO and OpenAI
- Rate limiting and retry logic
- Caching strategy for repeated keywords
- Cost tracking and monitoring per brief
- Logging and observability requirements (note: the threshold-tuning logging in §12.6 is required, not optional)
- Schema versioning compatibility with Writer Module v1.5+
- Specific LLM model selection for each agent call (intent fallback, title generation, persona, scope verification, heading polish, authority agent, FAQ extraction, how-to reordering)
- Specific model versions for each fan-out LLM (ChatGPT, Claude, Gemini, Perplexity) — should be configurable
- Downstream consumption of silo candidates — whether they automatically trigger new brief generation, enter a queue, or are surfaced to a human for approval
- Threshold tuning workflow and acceptance criteria for production behavior

---

## 14. Migration from v1.7

### 14.1 Breaking Changes

- Output schema changes substantially. Writer Module consumers must update to handle:
  - New top-level fields: `title`, `scope_statement`, `title_rationale`, `persona`
  - New per-heading fields: `title_relevance` (replaces `semantic_score`), `region_id`, `scope_classification`, `information_gain_score`
  - New metadata fields: graph structure stats, threshold values used, shortfall flags
  - New source values: `persona_gap`
  - New `discard_reason` values: `above_restatement_ceiling`, `region_off_topic`, `region_restates_title`, `scope_verification_out_of_scope`
  - Removed field: `semantic_score` (renamed to `title_relevance`; semantically different — measures distance from title, not seed)
- Embedding model changes from `text-embedding-3-small` to `text-embedding-3-large`. Any cached v1.7 embeddings cannot be reused.
- Heading priority formula changes. Briefs from v1.7 and v2.0 are not directly comparable on priority scores.

### 14.2 Non-Breaking Continuity

These v1.7 elements are preserved unchanged:
- All data acquisition (Steps 1, 2)
- Intent classification (Step 3)
- Subtopic aggregation logic (Step 4)
- Authority Gap Agent (Step 9)
- FAQ scoring formula (Step 10), with `semantic_relevance` now measured against title rather than seed
- Structure assembly rules (Step 11): H2/H3 caps, intent-aware structure, how-to reordering, word budgets
- Silo cluster quality rules (Step 12)
- DataForSEO and OpenAI integration patterns

### 14.3 Suggested Test Fixtures

To validate v2.0 against the failure modes that motivated the rewrite:

1. **Fixture A — TikTok Shop replication.** Run the seed `"what is tiktok shop"` and verify:
   - Title generated is definitional, not seller-tactical
   - At most one H2 has cosine > 0.85 to title (should be zero by construction)
   - All paraphrase H2s ("What exactly is TikTok Shop", "What is a TikTok Shop seller", etc.) appear in `discarded_headings` with `discard_reason: "above_restatement_ceiling"`
   - "TikTok Shop algorithm signals"-type headings appear in `silo_candidates` with `routed_from: "scope_verification"` or as non-selected regions
   - For each selected H2, every assigned H3 has `parent_relevance` in [0.60, 0.85] — no H3 paraphrases its parent
   - Within any single H2, no two H3s have pairwise cosine > 0.78 — H3 siblings do not paraphrase each other
   - Every entry in `silo_candidates` has `search_demand_score > 0.0`
   - "TikTok Shop algorithm signals"-type rejects are classified with `viable_as_standalone_article: true` and `estimated_intent` of `how-to` or `informational`
2. **Fixture B — Sparse SERP + how-to keyword pre-check.** Run a niche keyword with <10 SERP results. Verify graceful degradation: `low_serp_coverage: true` and reasonable persona-gap-driven outline.
   - Additional v2.0.3 assertion: include a how-to keyword case (e.g., `"how to open a tiktok shop"`) and verify Step 3.1's keyword pattern pre-check fires: `intent_type == "how-to"`, `intent_confidence >= 0.95`, `intent_review_required == false`, AND that the SERP-title-based fallback was NOT consulted (no LLM borderline-ecom check log entry). This guards the production failure mode that motivated v2.0.3.
3. **Fixture C — Listicle intent.** Run a "best X" keyword. Verify uncapped H2 selection respects intent-specific rules and that each list-item-H2 is a distinct region.
4. **Fixture D — Constraint exhaustion.** Construct a scenario where eligible candidates cluster heavily in 2–3 regions only. Verify `h2_shortfall: true` and `h2_shortfall_reason: "constraints_exhausted_eligible_pool"`.
5. **Fixture E — Title generation failure path.** Mock title generation LLM to return malformed JSON twice. Verify run aborts with `title_generation_failed`.
6. **Fixture F — Scope verification override.** Run a brief where the LLM marks an H2 `out_of_scope` that a human reviewer would consider in-scope. Verify the H2 routes to silo and the metadata captures the rejection. (This fixture is for catching false-positive scope rejections during tuning.)
7. **Fixture G — Threshold sensitivity.** Run the same keyword 3 times with restatement_ceiling values of 0.74, 0.78, 0.82. Compare outputs. The middle run should be the production default; the others should produce visibly worse (over-constrained or under-constrained) results.
8. **Fixture H — H3 sparsity.** Construct a scenario where a selected H2 has very few eligible H3 candidates after parent-relevance filtering (e.g., a niche H2 whose region is small and well-isolated from other regions). Verify `metadata.h2s_with_zero_h3s > 0`, that the brief is still valid, and that Authority Gap H3s still attach to the most-relevant available H2.
9. **Fixture I — Silo discard reason filtering.** Construct a brief where many headings are discarded with `discard_reason: "above_restatement_ceiling"` (i.e., the LLM fan-out / SERP returned several near-paraphrases of the title). Verify that none of these headings appear in `silo_candidates` and that `metadata.silo_candidates_rejected_by_discard_reason` is incremented to match.
10. **Fixture J — Silo viability rejection.** Mock the Step 12.4 viability LLM to return `viable_as_standalone_article: false` for a known silo candidate. Verify the candidate is excluded from the final `silo_candidates` array and that `metadata.silo_candidates_rejected_by_viability_check` is incremented by 1.
11. **Fixture K — Authority Gap H3 scope rejection (NEW in v2.0.3).** Mock Step 9 to emit an Authority Gap H3 that's clearly out of scope (e.g., a "post-launch tax obligations" H3 against a `does not cover` clause excluding post-launch operations). Verify Step 8.5b classifies it `out_of_scope`, removes it from the H2's H3 attachment list, and routes it to `silo_candidates` with `routed_from: "scope_verification_h3"`.
12. **Fixture L — Title case normalization (NEW in v2.0.3).** Construct a brief where one or more candidate headings arrive in mixed case (e.g., `"how to open a TikTok shop"`, `"WHAT THE ALGORITHM REWARDS"`). Verify every entry in the final `heading_structure` (H1/H2/H3, content + faq-header + faq-question) has `text` that round-trips through the `titlecase` library unchanged — i.e., `titlecase(text) == text`.

---

## 15. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | Initial draft | Original PRD |
| 1.1 | 2026-04-29 | Added success metrics, failure modes, FAQ scoring formula, heading priority formula, borderline ecom LLM check, format directives, performance targets, cost model, input validation, informational-commercial intent type |
| 1.2 | 2026-04-29 | Added autocomplete and keyword suggestions as heading candidate sources |
| 1.3 | 2026-04-29 | Added LLM fan-out queries via DataForSEO LLM Responses API (ChatGPT); added response content extraction as additional heading candidate source |
| 1.4 | 2026-04-29 | Raised word budget to 2,500; added global content subheading cap; authority gap H3s now count toward per-H2 limit; H3s optional per H2 |
| 1.5 | 2026-04-29 | Reduced max H3s per H2 from 3 to 2 |
| 1.6 | 2026-04-29 | Expanded LLM fan-out capture from ChatGPT-only to all 4 major LLMs; added cross-LLM consensus tracking; rebalanced heading priority formula to weight LLM consensus at 0.2 |
| 1.7 | 2026-04-29 | Added Step 9 Silo Cluster Identification; added `discarded_headings` and `silo_candidates` to output schema; added cluster quality rules, review flag, and failure mode for empty silo results |
| **2.0** | **2026-05-01** | **Major architectural rewrite. Added Step 3.5 (title + scope statement generation), Step 6 (hypothetical searcher persona generation), Step 8.5 (scope verification), and Step 8.6 (H3 selection — applies the same MMR + region + anti-restatement principles at H2-scope rather than title-scope, with `parent_relevance` floor 0.60 and ceiling 0.85, inter-H3 threshold 0.78, and Authority Gap cap-displacement rules). Replaced lexical-only deduplication with embedding-based pre-filtering (relevance floor 0.55, restatement ceiling 0.78). Replaced ad-hoc heading selection with MMR optimization respecting region uniqueness and inter-heading anti-redundancy (max 0.75 pairwise cosine). Added coverage graph construction via Louvain community detection. Upgraded embedding model from text-embedding-3-small to text-embedding-3-large. Rebalanced heading priority formula to include explicit information_gain_score term. Silo cluster identification now reuses Step 5 regions instead of clustering discarded headings separately. Output schema fundamentally restructured: `semantic_score` renamed to `title_relevance`; new fields `title`, `scope_statement`, `persona`, `region_id`, `scope_classification`, `information_gain_score`, `parent_h2_text`, `parent_relevance`; new discard reasons (including `h3_below_parent_relevance_floor`, `h3_above_parent_restatement_ceiling`, `displaced_by_authority_gap_h3`); new metadata for graph structure, shortfall flags, and H3 distribution (`h3_count_average`, `h2s_with_zero_h3s`). Cost ceiling raised from $0.75 to $1.00. End-to-end target raised from 60s to 75s. Brief generator does not accept ICP context; hypothetical searcher is derived from topic + SERP signal only. Fixes the v1.7 failure modes documented in Section 1: paraphrase-H2 outlines and topical-clone outlines.** |
| **2.0.2** | **2026-05-01** | **Refined Step 12 (Silo Cluster Identification) into six numbered subsections: 12.1 explicit `discard_reason` filtering (only `scope_verification_out_of_scope`, conditional `below_priority_threshold`, and `global_cap_exceeded` route to silos; restatement ceiling and off-topic rejects are excluded so silos never compete with the parent brief); 12.2 cluster formation (preserves region reuse + coherence + centroid); 12.3 search demand validation with hard threshold 0.30 against a five-signal `search_demand_score` (max SERP frequency, max LLM consensus, PAA / autocomplete / Reddit presence indicators); 12.4 per-candidate viability LLM check with strict JSON output (`viable_as_standalone_article`, `reasoning`, `estimated_intent`) and parallel execution; 12.5 cross-brief deduplication scoped out as a v2.1 requirement; 12.6 expanded silo candidate output with `discard_reason_breakdown`, `search_demand_score`, `viable_as_standalone_article`, `viability_reasoning`, `estimated_intent`, and `cross_brief_occurrence_count`. New metadata counters: `silo_candidates_rejected_by_discard_reason`, `silo_candidates_rejected_by_search_demand`, `silo_candidates_rejected_by_viability_check`, `silo_viability_fallback_applied`. Cost range updated to $0.35–$0.89 reflecting up to 10 parallel viability checks at $0.01–$0.02 each; $1.00 ceiling preserved; end-to-end target stays at 75s under parallel execution. New test fixtures I (discard-reason filtering) and J (viability rejection); Fixture A extended to verify silo `search_demand_score > 0` and `viable_as_standalone_article: true` for in-band scope rejects. No breaking schema changes — new fields are additive.** |
| **2.0.3** | **2026-05-01** | **Three surgical bug fixes diagnosed from a production run on `"how to open a tiktok shop"`. (1) **Intent classifier keyword pattern pre-check**: Step 3 now runs a deterministic keyword pattern check (Step 3.1) BEFORE the SERP-feature-signal classifier; matching keywords short-circuit at 0.90–0.95 confidence with `intent_review_required=false`. Patterns cover `how to`/`how do i`/`how can i`/`ways to`/`steps to`/`guide to` (→ how-to), `what is`/`what are`/`what does`/`definition of` (→ informational), `best`/`top`/`<n> <plurals>` (→ listicle), and ` vs `/` versus `/` or `/`compared to` (→ comparison). Fixes a production miss where a how-to keyword was classified informational at 0.55 confidence because top SERP titles didn't literally start with "how to". (2) **Authority Gap scope discipline**: Step 9 now receives `title`, `scope_statement`, and `intent_type` as inputs and emits a `scope_alignment_note` per H3. A new Step 8.5b runs scope verification on Authority Gap H3s with the same in_scope / borderline / out_of_scope routing as Step 8.5; out-of-scope H3s route to `silo_candidates` with new `routed_from: "scope_verification_h3"`. Adds ~$0.02 per brief for the extra LLM call. Fixes the production failure mode where compliance / tax / abandonment H3s bypassed scope verification entirely. (3) **Title case normalization**: a new Step 11.x applies AP/Chicago-style title case via the `titlecase` PyPI library to every `heading_structure[].text` after all upstream processing. Pure CPU, free, deterministic. Fixes inconsistent capitalization in published articles. New fixtures: K (Authority Gap H3 scope rejection), L (title case round-trip). Cost range updated to $0.37–$0.91; end-to-end target unchanged at 75s; ceiling unchanged at $1.00.** |
| **2.1** | **2026-05-03** | **Phase 1 of the article-quality defect fixes (proposal accepted 2026-05-03). Addresses Defect 1 from the audit: keyword-intent → article-format mismatch (the run on "How to Increase ROI for Your TikTok Shop" classified correctly as `how-to` but produced topic-cluster Q&A H2s instead of procedural steps). Three additions, all additive on the v2.0 schema. **(1) `intent_format_template`** — Step 3.3 maps the classified intent to a per-intent heading-skeleton template emitting `h2_pattern`, `h2_framing_rule`, `ordering`, `min_h2_count`, `max_h2_count`, and `anchor_slots`. Templates registered for all 8 intent enum values; `local-seo` and `news` use `framing_rule="no_constraint"` and remain deferred to v1.x. **(2) Step 7.5 — Anchor-Slot Reservation** — runs immediately before Step 8 MMR. Embeds template `anchor_slots` (single API call), then for each slot reserves the highest-cosine candidate above `MIN_ANCHOR_COSINE = 0.55` while honoring region uniqueness and the inter-heading threshold. Reserved candidates seed `select_h2s_mmr`'s `pre_reserved` parameter so MMR's hard constraints account for them. Failures (embedding outage, no candidate above floor) are logged and skipped — Step 8 falls through to plain MMR. **(3) Step 11.0 — H2 Framing Validator** — runs after Step 8.5 scope verification, before how-to reorder and Step 11.x title casing. Each H2 is regex-checked against the template's framing rule; failures route through one batched LLM rewrite call (preserving topic, swapping framing). Rewrites that still fail the regex are accepted with `framing_rewrites_accepted_with_violation` flagged in metadata — never aborts the run. New top-level output field `intent_format_template`; new metadata counters `anchor_slots_total`, `anchor_slots_reserved_count`, `framing_rewrites_applied`, `framing_rewrites_accepted_with_violation`. Schema bump `2.0` → `2.1`. Orchestrator's `EXPECTED_MODULE_VERSIONS["brief"]` bumped to `2.1` in lockstep. Cost increase: ~$0.0001 (anchor embedding) + 0–$0.02 (framing rewrite, only when triggered). End-to-end timing unchanged (Step 7.5 is one embedding call running before Step 8; framing pass adds ≤2s when LLM call fires).** |
| **2.2** | **2026-05-03** | **Phase 2 of the article-quality defect fixes (proposal accepted 2026-05-03). Addresses Defect 3 (H3 → H2 topical drift — the audited "affiliate vetting under cart-abandonment H2" cross-region case) and Defect 4 (FAQ intent mismatch — "creator monetization on a seller-ROI article"). Three additions, all additive on the v2.1 schema. **(1) Step 8.6 tightened** — H3 parent-relevance floor raised `0.60 → 0.65`; the adjacent-region relaxation removed (H3s must sit in the SAME coverage-graph region as the parent H2, not just an adjacent one). **(2) Step 8.7 — H3 Parent-Fit Verification** (NEW) — runs after Step 9 + auth_attach. Single batched Claude call classifies every per-H2-attached H3 as `good` / `marginal` / `wrong_parent` / `promote_to_h2`. `wrong_parent` re-attaches to a better-fit H2 when capacity exists, otherwise routes to silos with `routed_from="h3_parent_mismatch"` + `discard_reason="h3_wrong_parent"`. `promote_to_h2` always routes to silos via `routed_from="h3_promote_candidate"` + `discard_reason="h3_promoted_to_h2_candidate"`. Authority-gap H3s exempt from discard (downgrade `promote_to_h2` to `marginal`). **(3) Step 10.5 — FAQ Intent Gate** (NEW) — two-stage filter on FAQ candidates. Stage 1: cosine floor (default 0.55) against an `intent_profile` vector built from `intent_type + title + scope_statement + persona.primary_goal`. Stage 2: single batched Claude call classifies survivors as `matches_primary_intent` / `adjacent_intent` / `different_audience`; `different_audience` are dropped, `adjacent_intent` are kept only as relaxation fallback when fewer than 3 primary survive. **(4) `semantic_relevance` formula updated** — Step 10's `score_faqs` now produces a 50/50 blended cosine (cosine-to-title + cosine-to-intent-profile) when the intent profile is supplied. New top-level fields `parent_fit_classification` on `HeadingItem` and `intent_role` on `FAQItem`. New `DiscardReason` values: `h3_wrong_parent`, `h3_promoted_to_h2_candidate`, `faq_intent_mismatch`. New `SiloRoutedFrom` values: `h3_parent_mismatch`, `h3_promote_candidate`. Seven new metadata counters: `h3_parent_fit_marginal_count`, `h3_parent_fit_wrong_parent_count`, `h3_parent_fit_promoted_count`, `h3_parent_fit_fallback_applied`, `faq_intent_gate_floor_rejected_count`, `faq_intent_gate_llm_rejected_count`, `faq_intent_gate_relaxation_applied`. Schema bump `2.1` → `2.2`. Orchestrator's `EXPECTED_MODULE_VERSIONS["brief"]` bumped to `2.2` in lockstep. Cost increase: ~$0.02 (Step 8.7 LLM call) + ~$0.01–$0.02 (Step 10.5 LLM call) + 1 embedding (intent profile, ~$0.0001). End-to-end timing impact: <2s when both LLM calls fire.** |
| **2.3** | **2026-05-03** | **Phase 3 of the article-quality defect fixes (proposal accepted 2026-05-03). Addresses Defect 2 (empty H2 bodies — the audited "an H2 followed by two sentences and a stat" case). Two changes: **(1) `format_directives.min_h2_body_words`** — new field stamped at assembly time from the run's `intent_format_template.h2_pattern`. Per-pattern defaults: how-to=120, listicle=80, comparison=150, informational=180, informational-commercial=180, ecom=150, local-seo=150, news=100. The brief output's existing `format_directives` block is now populated explicitly (previously used schema defaults); this is non-breaking because existing consumers either ignored `format_directives` or read fields by key. **(2) Writer dependency bump** — Writer Module v1.6+ is now required to consume the floor via its new Step 6.7 H2 body length validator. Schema bump `2.2` → `2.3`. Orchestrator's `EXPECTED_MODULE_VERSIONS["brief"]` bumped to `2.3` and `EXPECTED_MODULE_VERSIONS["writer"]` bumped to `1.6` in lockstep (with `WRITER_ACCEPTED_VERSIONS = {"1.6", "1.6-no-context", "1.6-degraded"}`). No cost impact on the brief side — derivation is pure CPU. Writer-side cost: 0–N additional LLM calls for H2 retries (only fires when an H2 ships under floor; steady-state expected ≤ 1/run).** |


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/modules/SIE_PRD_Term_Entity_Module.md -->
<!-- ============================================================ -->

# 📄 Product Requirements Document (PRD)

## Product Name
SERP Intelligence Engine (SIE) — Term & Entity Analysis Module

## Subtitle
SERP-Driven Keyword, Entity, and Usage Recommendation Engine

---

# 1. 🎯 Objective

Build the term and entity analysis layer of a larger blog content generation SaaS. This module analyzes top SERP results for a target keyword, extracts competitor content patterns, filters noise, and produces a unified list of scored keyword and entity recommendations with usage guidance.

This module should:

1. Accept a target keyword and location.
2. Pull top SERP results using DataForSEO.
3. Classify SERP result types to determine content eligibility.
4. Scrape eligible ranking pages.
5. Extract content by page zone.
6. Filter noise from scraped content.
7. Lemmatize and generate n-grams (unigrams through quadgrams).
8. Aggregate terms across pages with subsumption and coverage gating.
9. Filter terms by TF-IDF distinctiveness.
10. Filter terms by semantic similarity using embeddings.
11. Extract and categorize entities using Google Natural Language API.
12. Score all terms and entities for relevance.
13. Generate per-zone usage recommendations with configurable outlier handling.
14. Recommend target content length.

This module does NOT generate content briefs, heading structures, FAQ recommendations, intent classifications, or draft scoring. Those are handled by a separate downstream module.

---

# 2. 🧱 System Context

This module is an internal component of a larger SaaS platform that generates blog posts for service-area businesses. It is not a standalone product or API. Its output feeds directly into downstream modules (content brief generation, heading optimization, content writing) within the same system.

The module runs as a series of modular pipeline stages within the platform backend.

---

# 3. 💥 Core Value Proposition

This module replaces the keyword and entity analysis functionality found in tools like SurferSEO, Clearscope, and Page Optimizer Pro with a transparent, customizable pipeline.

The module provides:

- SERP-driven keyword extraction and scoring
- Zone-based n-gram analysis (title, H1, H2, H3, paragraphs)
- Lemmatized term aggregation with n-gram subsumption
- Coverage threshold gating to eliminate noise
- TF-IDF distinctiveness scoring (both as filter and scoring signal)
- Embedding-based semantic filtering
- Entity extraction grounded in Google Natural Language API
- Quadgram zone-weighting for intent-specific phrase detection
- Configurable aggressive/safe outlier handling for usage recommendations
- Percentile-based content length recommendations
- All recommendations classified as Required or Avoid — no ambiguous tiers

---

# 4. 🧱 System Architecture

## High-Level Flow

Keyword Input
↓
Cache Check (return cached result if <7 days old and force_refresh is false)
↓
SERP Data Collection
↓
SERP URL Classification + Near-Duplicate Detection
↓
Content-Eligible URL Filtering
↓
Page Scraping
↓
Content Parsing / Zone Extraction
↓
Noise Filtering
↓
┌──────────────────────────────────────────────────────────┐
│ PARALLEL TRACK A              PARALLEL TRACK B           │
│                                                          │
│ N-Gram Analysis               Entity Extraction          │
│ ↓                             (Google NLP + LLM)         │
│ Term Aggregation                                         │
│ ↓                                                        │
│ Coverage Threshold Gating     Word Count Analysis        │
│ ↓                                                        │
│ TF-IDF Pre-Filter                                        │
│ ↓                                                        │
│ Semantic Filtering                                       │
└───────────────────────┬──────────────────────────────────┘
                        ↓
              Entity–Term Merge
                        ↓
           Recommendation Scoring Engine
                        ↓
           Usage Recommendation Engine
                        ↓
              Store Results to Supabase

---

# 5. 🧩 Core Modules

### Execution Order and Parallelism

Modules 1–6 execute sequentially — each depends on the output of the previous module. After Module 6 (Noise Filtering), the pipeline forks into two parallel tracks:

**Track A (N-Gram Pipeline):** Modules 7 → 8 → 9 → 10. These process the cleaned text into scored, filtered terms.

**Track B (Entity + Word Count):** Modules 11 and 12 run in parallel with Track A. Entity extraction calls the Google NLP API per page and runs the LLM dedup pass. Word count analysis computes percentile ranges from page lengths. Neither depends on n-gram output.

**Merge point:** After both tracks complete, the entity–term merge combines their outputs into a unified term list. This feeds into Module 13 (Scoring) and Module 14 (Usage Recommendations), which execute sequentially.

Parallelizing Track A and Track B significantly reduces total pipeline runtime because the Google NLP API calls in Module 11 are the second most time-consuming operation after scraping.

---

## Module 1: Keyword Input

### Purpose

Accept the primary keyword and configuration inputs needed to run the analysis.

### Input

```json
{
  "keyword": "water heater repair",
  "location_code": 2840,
  "language_code": "en",
  "device": "desktop",
  "depth": 20,
  "outlier_mode": "safe",
  "force_refresh": false
}
```

### Requirements

- Must accept one target keyword per run.
- Must support DataForSEO location codes.
- Must support language code configuration.
- Must support desktop or mobile SERP configuration.
- Must support configurable SERP depth, with a default of top 20 results.
- Must accept `outlier_mode` parameter: `"safe"` (default) or `"aggressive"`.
- Must accept `force_refresh` parameter: `false` (default) or `true`. When `false`, the pipeline checks for cached results for this keyword + location within the last 7 days and returns cached output if available. When `true`, the pipeline runs a fresh analysis regardless of cache state.

---

## Module 2: SERP Collection

### Purpose

Collect top organic SERP results for the target keyword.

### Input

```json
{
  "keyword": "target keyword",
  "location_code": 2840,
  "language_code": "en"
}
```

### Output

```json
{
  "urls": [],
  "titles": [],
  "descriptions": [],
  "ranks": []
}
```

### Requirements

- Use DataForSEO API.
- Collect top 20 organic results by default.
- Preserve ranking position.
- Preserve page title.
- Preserve meta description when available.
- Preserve displayed URL.
- Preserve result type when available.
- Must support retries and error handling.
- Must handle empty or partial SERP responses.

---

## Module 3: SERP URL Classification

### Purpose

Classify each SERP result so the system can decide which pages should be scraped for content extraction.

### Page Categories

Each SERP result should be classified as one of the following:

- Direct competitor
- Informational article
- Local service page
- Product/service landing page
- Directory
- Forum / UGC
- Marketplace
- Government / educational
- Video result
- News result
- Social media result
- Irrelevant result

### Output

```json
{
  "url": "https://example.com",
  "rank": 1,
  "title": "Example Title",
  "page_category": "local service page",
  "content_eligible": true,
  "reason": "The page appears to be a local service page directly relevant to the target keyword."
}
```

### Requirements

- Use only content-eligible pages for n-gram, entity, and usage extraction.
- Exclude or downweight directories, forums, marketplaces, and UGC pages from content usage recommendations unless explicitly allowed.
- Flag irrelevant results.
- Preserve excluded URLs with exclusion reasons.

### Near-Duplicate Page Detection

After scraping, detect and deduplicate pages that serve the same content under different URLs (www vs non-www, HTTP vs HTTPS, mobile subdomains, syndicated content, or mirror pages). Duplicate pages inflate every frequency count, coverage number, and percentile calculation in the pipeline.

**Detection method:** Compare the first 500 characters of cleaned body text (post-noise-filtering) between all pairs of content-eligible pages. If two pages share >90% character-level similarity in this window, flag the lower-ranked page as a duplicate of the higher-ranked page.

**Behavior:**

- The higher-ranked page is retained as the canonical version.
- The lower-ranked duplicate is excluded from all downstream analysis.
- The duplicate is logged with the canonical URL it was matched to.

```json
{
  "url": "https://www.example.com/water-heater-repair",
  "duplicate_of": "https://example.com/water-heater-repair",
  "similarity": 0.96,
  "excluded": true,
  "exclusion_reason": "Near-duplicate of higher-ranked page"
}
```

**Requirements:**

- Must compare body text similarity after scraping and noise filtering.
- Must use the first 500 characters of cleaned body text for comparison.
- Must flag pages with >90% similarity as duplicates.
- Must retain the higher-ranked page and exclude the lower-ranked duplicate.
- Must log all duplicate detections with similarity score.

### Example Exclusion Reasons

- Directory result
- Forum / UGC result
- Marketplace page
- Video result
- Not directly related to keyword
- Thin content
- Blocked from scraping
- Duplicate result
- Non-English page
- Location mismatch

---

## Module 4: Page Scraping

### Purpose

Scrape content from content-eligible SERP URLs.

### Input

```json
{
  "url": "https://example.com"
}
```

### Output

```json
{
  "url": "https://example.com",
  "html": "...",
  "text": "...",
  "markdown": "...",
  "scrape_status": "success"
}
```

### Requirements

- Use ScrapeOwl or equivalent.
- Must handle JavaScript-rendered pages.
- Must handle timeouts.
- Must support retries.
- Must return scrape status.
- Must return failure reason when scraping fails.
- Must skip pages that cannot be scraped after retry limit.
- Must preserve URL association throughout the pipeline.

### Failure Reasons

- Timeout
- Blocked by robots or firewall
- Empty page
- Non-HTML response
- Redirect loop
- JavaScript rendering failure
- HTTP error
- Scrape API error

---

## Module 5: Zone Extraction

### Purpose

Extract content from meaningful page zones for analysis.

### Output Structure

```json
{
  "url": "https://example.com",
  "zones": {
    "title": "Example Title",
    "meta_description": "Example meta description",
    "h1": [],
    "h2": [],
    "h3": [],
    "h4": [],
    "paragraphs": "",
    "lists": [],
    "tables": [],
    "faq_blocks": []
  },
  "word_count": 1400
}
```

### Requirements

- Strip scripts and styles.
- Normalize whitespace.
- Extract title tag.
- Extract meta description when available.
- Extract H1, H2, H3, and optionally H4 headings.
- Extract paragraph body content.
- Extract list items.
- Extract table text when useful.
- Filter low-quality paragraphs under 5 words.
- Preserve zone-level text for later analysis.
- Preserve page-level word count.

---

## Module 6: Noise Filtering

### Purpose

Remove content that would distort recommendations. Uses a five-layer approach applied in order so that each layer catches what the previous one missed.

### Layer 1: Structural HTML Stripping

Before any text analysis, remove elements by HTML tag, class/ID pattern, and ARIA role.

**Remove by tag:** `<nav>`, `<footer>`, `<header>`, `<aside>`, `<noscript>`

**Remove by class/ID pattern match:** Any element with a class or ID containing `sidebar`, `widget`, `menu`, `nav`, `footer`, `breadcrumb`, `cookie`, `banner`, `social-share`, `related-posts`, `author-bio`, `comments`, `newsletter`, `signup`, `cta`

**Remove by ARIA role:** `navigation`, `banner`, `contentinfo`, `complementary`

This layer catches 60–70% of boilerplate on well-structured sites, less on WordPress page builder sites with generic class names.

### Layer 2: Content Extraction by Text Density

Apply content extraction heuristics to isolate the main body content from chrome. For each block-level element, compute:

- `text_density = text_length / total_element_length`
- `link_ratio = link_word_count / total_word_count`

**Rules:**

- Blocks with `link_ratio > 0.3` are classified as navigation and excluded.
- Blocks with fewer than 20 words surrounded by high-link-density blocks are classified as UI chrome and excluded.
- If the scraping service returns a `markdown` or `text` field that has already been extracted from the main content area, evaluate whether that output is clean enough to use directly before applying manual extraction.

### Layer 3: Cross-Page Fingerprinting

This is the most important layer for this use case. It exploits the fact that the pipeline scrapes 10–20 pages per keyword from different domains.

**Process:**

1. After zone extraction, take every paragraph and list item from every scraped page.
2. Normalize each block: lowercase, strip extra whitespace, remove punctuation.
3. Hash or use the normalized string as a key.
4. Count how many unique domains each normalized block appears on.
5. Any block appearing on 3+ different domains is flagged as cross-page boilerplate and excluded from n-gram analysis.

**Granularity:** Apply at both paragraph level (catches large boilerplate blocks) and sentence level (catches boilerplate sentences embedded in otherwise legitimate paragraphs).

**This layer is particularly effective for local service pages**, which share templates and stock phrases like "Licensed, bonded, and insured", "Call us for a free estimate", and "We serve [city] and surrounding areas."

### Layer 4: Heuristic Text Filters

Apply pattern-based filters to remaining text blocks after structural extraction:

- Paragraphs under 5 words: discard.
- Paragraphs that are entirely a phone number, email address, or physical address pattern: exclude from n-gram analysis but preserve for entity extraction (addresses are legitimate local entities).
- Paragraphs where more than 50% of words are proper nouns or city names: likely a service area list, exclude.
- Text blocks matching common CTA patterns ("call now", "get a free", "schedule your", "request a quote"): exclude.

### Layer 5: Post-Extraction Frequency Anomaly Detection

After n-gram analysis in Module 7, apply a final safety net at the term level.

Flag any term where the coefficient of variation in per-page frequency is near zero. If a term like "licensed bonded insured" appears exactly the same number of times on every page, it is template content, not organic usage. Organically used terms will have variable frequency across pages.

**Threshold:** If the coefficient of variation for a term's per-page frequency is below `0.1` and the term appears on 4+ pages, flag it as suspected template boilerplate and exclude from scoring.

### Requirements

- Must apply all five layers in order before n-gram analysis (Layers 1–4) and after n-gram analysis (Layer 5).
- Must preserve meaningful content from the main page body.
- Must avoid removing legitimate service content.
- Must log all removed content with the layer that removed it for debugging.
- Must preserve content removed by Layer 4 (contact info, addresses) for entity extraction even though it is excluded from n-gram analysis.
- Cross-page fingerprinting (Layer 3) is mandatory for MVP.

---

## Module 7: N-Gram Analysis

### Purpose

Generate term candidates from extracted page content by zone.

### Output

```json
{
  "url": "https://example.com",
  "zone_analysis": {
    "h2": {
      "bigrams": {
        "water heater": 2
      },
      "trigrams": {
        "water heater repair": 1
      }
    }
  }
}
```

### Requirements

- Generate:
  - Unigrams
  - Bigrams
  - Trigrams
  - Quadgrams
- **Stopword handling:** Remove stopwords from unigrams only. Preserve stopwords within bigrams, trigrams, and quadgrams so that phrases like "how to repair" and "what is a" remain intact as multi-word candidates.
- Remove punctuation.
- Normalize casing.
- **Lemmatize before counting.** Apply lemmatization (e.g., "repairs" → "repair", "repairing" → "repair", "repaired" → "repair") before n-gram generation. All inflected forms of a word must be collapsed to a single base form so that frequency counts, coverage thresholds, and usage recommendations reflect the true topical signal, not surface-level variation. Lemmatization must be applied consistently across all zones and all pages before any aggregation occurs.
- Track counts per zone.
- Track counts per URL.
- Track total page count.
- Preserve source URL for each n-gram occurrence.
- Avoid overcounting repeated boilerplate terms.
- **Quadgram Zone Weighting:** Quadgrams (4-word phrases) must be flagged when they appear in high-importance zones (title, H1, H2) across 2 or more pages. These are strong signals of intent-specific terminology and must be preserved through all downstream filtering stages regardless of raw frequency. Assign quadgrams a zone multiplier of 1.5x when found in title, H1, or H2 zones during aggregation and scoring.

### Zones to Analyze

- Title
- Meta description
- H1
- H2
- H3
- Paragraphs
- Lists
- Tables
- FAQ blocks

---

## Module 8: Term Aggregation

### Purpose

Combine n-gram data across all analyzed pages.

### Output

```json
{
  "term": "water heater repair",
  "total_count": 12,
  "pages_found": 6,
  "source_urls": [],
  "zones": {
    "h2": {
      "total_count": 5,
      "pages_found": 4
    },
    "paragraphs": {
      "total_count": 7,
      "pages_found": 6
    }
  }
}
```

### Requirements

- Combine terms across all pages.
- Track total count.
- Track pages_found using unique URLs.
- Track source URLs.
- Track zone-level counts.
- Track zone-level pages_found.
- Must aggregate across all items in a single pass.
- Must deduplicate by normalized, lemmatized term.
- Must preserve raw and normalized versions of terms when useful.

### N-Gram Subsumption Rules

After aggregation and before coverage gating, apply subsumption to merge shorter n-grams that are fully contained within a passing longer n-gram.

**Rule:** If a shorter n-gram (e.g., "water heater") is a full substring of a longer n-gram that also passes aggregation (e.g., "water heater repair cost"), the shorter n-gram is merged into the longer one. The longer n-gram inherits the combined frequency counts and zone data from both.

**Merge behavior:**

- The longer n-gram becomes the canonical term in all downstream modules.
- The shorter n-gram is removed from the active candidate list.
- The shorter n-gram is preserved in a `subsumed_by` reference on the longer term for traceability.
- If the shorter n-gram appears on pages where the longer n-gram does not, it is NOT subsumed — it remains independent because it represents distinct usage.
- Subsumption only applies when every occurrence of the shorter n-gram co-occurs with the longer n-gram on the same pages.
- **Sub-phrases of the target keyword must never be subsumed by the target keyword itself.** They may have independent usage patterns across competitor pages and must go through the normal pipeline.

**Output additions:**

```json
{
  "term": "water heater repair cost",
  "n_gram_length": 4,
  "subsumed_terms": ["water heater repair", "heater repair cost"],
  "subsumed_terms_count": 2
}
```

**Requirements:**

- Must apply subsumption after aggregation but before coverage gating.
- Must only subsume when shorter n-gram usage is fully contained within longer n-gram pages.
- Must preserve `subsumed_terms` array on the canonical term for traceability.
- Must not subsume if shorter n-gram has independent page coverage.
- Must not subsume across different zones (e.g., a bigram in H2 is not subsumed by a quadgram that only appears in paragraphs).
- Must not subsume sub-phrases of the target keyword.

### Coverage Threshold Gate

After subsumption, apply a minimum coverage threshold before any term proceeds to TF-IDF or semantic filtering. This prevents rare, single-source terms from consuming embedding budget and polluting recommendations.

**Default rule:** A term must appear on at least 3 of the top 10 content-eligible pages to proceed. Terms below this threshold are moved to a `low_coverage_candidates` pool and excluded from scoring unless manually overridden.

**Exceptions — always allow through regardless of coverage:**

- Quadgrams found in title, H1, or H2 on 2+ pages (intent-specific phrases)
- Terms found exclusively on pages ranked 1–3, provided those pages are from 2+ unique domains (top-of-SERP signal from independent sources)
- Terms flagged by the entity extraction module as high-confidence entities

**Output additions:**

```json
{
  "term": "tankless water heater installation",
  "pages_found": 2,
  "passes_coverage_threshold": false,
  "coverage_exception": "quadgram found in H2 on rank-1 and rank-2 pages",
  "low_coverage_candidate": false
}
```

**Requirements:**

- Must apply coverage gate before TF-IDF and embedding modules.
- Must expose threshold as a configurable parameter (default: 3 of top 10).
- Must log all terms that fail coverage threshold with reason.
- Must preserve `low_coverage_candidates` pool for optional manual review.
- Must not silently discard terms — exclusion reasons must always be recorded.

---

## Module 9: TF-IDF Pre-Filter

### Purpose

Score candidate terms by their distinctiveness within the SERP corpus before passing them to the embedding model. This reduces embedding API cost, removes terms that are common across the web but not distinctive to this SERP, and surfaces phrases that are meaningfully concentrated in the ranking pages.

The TF-IDF score also serves as a scoring input in Module 13 (Recommendation Scoring Engine), not just as a binary gate.

### How It Works

Treat each scraped page as a document and the full set of scraped pages as the corpus. Apply standard TF-IDF:

- **TF (Term Frequency):** How often the term appears in a given page, normalized by page word count.
- **IDF (Inverse Document Frequency):** How rare the term is across all scraped pages. Terms that appear on every page receive low IDF. Terms concentrated on fewer pages receive higher IDF.
- **TF-IDF Score:** TF × IDF. High scores indicate terms that are both frequent on some pages and distinctive relative to the rest of the corpus.

```text
tf(term, page) = term_count_in_page / page_word_count
idf(term, corpus) = log(total_pages / pages_containing_term)
tfidf(term, page) = tf * idf
```

Aggregate per-page TF-IDF scores across all pages to produce a corpus-level TF-IDF signal per term:

```text
corpus_tfidf(term) = average tfidf score across all pages where term appears
```

### Output

```json
{
  "term": "tankless water heater repair cost",
  "corpus_tfidf_score": 0.043,
  "passes_tfidf_threshold": true,
  "tfidf_rank_in_corpus": 12
}
```

### Default Thresholds

- Terms with corpus TF-IDF score below `0.005` are filtered out before embedding.
- Always preserve terms that passed a coverage exception in Module 8, regardless of TF-IDF score.
- Always preserve terms appearing in title, H1, or H2 on 2+ pages, regardless of TF-IDF score.
- Threshold must be configurable.

### Requirements

- Must compute TF-IDF using only content-eligible scraped pages.
- Must normalize term frequency per page word count.
- Must use log-scale IDF.
- Must aggregate per-page scores to a corpus-level signal.
- Must rank all candidate terms by corpus TF-IDF score.
- Must output TF-IDF score and pass/fail status per term.
- Must apply threshold filter before embedding module.
- Must preserve TF-IDF score for use as a scoring input in Module 13.
- Must preserve terms with coverage exceptions or zone-based protections.
- Must expose threshold as a configurable parameter.
- Must log filtered terms with their TF-IDF score for debugging.
- Must batch remaining candidates before passing to embedding module to reduce API calls.

---

## Module 10: Semantic Filtering with Embeddings

### Purpose

Filter extracted terms by semantic relevance to the target keyword.

### Requirements

- Use OpenAI embeddings.
- Recommended model: `text-embedding-3-small`.
- Embed the target keyword.
- Embed each candidate term.
- Compute cosine similarity between term and keyword.
- Default semantic similarity threshold: `0.65`.

### Output

```json
{
  "term": "water heater repair",
  "semantic_similarity": 0.72,
  "passes_semantic_filter": true
}
```

### Dynamic Threshold Logic

The default threshold should be `0.65`, but the system should adjust when needed:

- If fewer than 25 terms pass, lower threshold to `0.60`.
- If more than 300 terms pass, raise threshold to `0.70`.
- Always preserve terms found in title, H1, or H2 across 3+ pages unless clearly irrelevant.
- Always allow manual override of threshold.

### Requirements

- Must filter obviously unrelated terms.
- Must not rely only on raw frequency.
- Must preserve high-value heading terms even if similarity is slightly below threshold.
- Must output semantic similarity score.
- Must output pass/fail status.
- Must output reason when a term is preserved despite threshold.

---

## Module 11: Entity Extraction

### Purpose

Extract meaningful entities from ranking pages and categorize them for use downstream. Uses a two-pass pipeline: Google Natural Language API for grounded NER extraction, followed by an LLM pass for categorization, deduplication, and context enrichment.

### Two-Pass Pipeline

#### Pass 1: Google Natural Language API (NER)

Use the Google Cloud Natural Language API `analyzeEntities` endpoint to extract entities directly from each scraped page's text content. This grounds all entities in actual competitor text — the NLP model cannot invent entities, only surface what is present in the content.

**API call per page:**

```json
{
  "document": {
    "type": "PLAIN_TEXT",
    "content": "<page_body_text>"
  },
  "encodingType": "UTF8"
}
```

**Retain entities meeting all of the following criteria:**

- `salience` score ≥ `0.40`
- Entity type is one of: `PERSON`, `LOCATION`, `ORGANIZATION`, `EVENT`, `WORK_OF_ART`, `CONSUMER_GOOD`, `OTHER`
- Not a navigational artifact (e.g., domain names, menu labels, button text)

**Per-page entity output:**

```json
{
  "url": "https://example.com",
  "ner_entities": [
    {
      "name": "tankless water heater",
      "type": "CONSUMER_GOOD",
      "salience": 0.54,
      "mentions": 5
    }
  ]
}
```

**Requirements:**

- Must call Google NLP API per content-eligible page.
- Must use cleaned body text (post-noise-filtering) as input, not raw HTML.
- Must cap input text at 100,000 bytes per API call (Google NLP limit).
- Must handle API errors with retry logic.
- Must preserve salience score and entity type from API response.
- Must preserve mention count per page.
- Must log pages where NLP API call failed.

#### Pass 2: LLM Categorization and Deduplication

After aggregating NER results across all pages, pass the raw entity list to an LLM for:

1. **Deduplication:** Merge variants of the same entity (e.g., "tankless heater", "tankless water heater", "on-demand water heater").
2. **Categorization:** Map each entity to the standardized category list below.
3. **Context enrichment:** Generate a short example context statement based on how the entity was used across pages.
4. **Relevance filtering:** Flag and exclude entities that are off-topic, purely navigational, or brand-specific with no SEO value.

**The LLM may not invent new entities. It may only process, label, and merge entities returned by the Google NLP API.**

**LLM prompt constraint:**

```text
You will receive a list of entities extracted from competitor pages by Google NLP. 
Your job is to deduplicate, categorize, and filter this list. 
Do not add any entity that is not in the provided list. 
Only output entities that are present in the input.
```

### Output

```json
{
  "entities": [
    {
      "entity": "tankless water heater",
      "category": "equipment",
      "pages_found": 8,
      "avg_salience": 0.51,
      "source_urls": [],
      "example_context": "Mentioned in sections about repair, replacement, and installation.",
      "recommendation_score": 0.81,
      "confidence": "high",
      "ner_variants": ["tankless heater", "on-demand water heater", "tankless water heater"]
    }
  ]
}
```

### Entity–Term Merge

After entity extraction, entities are merged into the unified term list rather than maintained as a separate output. This gives downstream modules a single list of Required terms to work with.

**Merge rules:**

1. **Entity matches an existing term:** If an entity phrase matches a term already in the list from Module 7 (e.g., "tankless water heater" exists as both a trigram and an entity), the existing term entry is enriched with entity fields: `"is_entity": true`, `"entity_category"`, `"avg_salience"`, and `"ner_variants"`. The term's recommendation score receives a `1.15x` multiplier on its final recommendation score because dual-signal terms (both high-frequency n-gram and high-salience entity) are stronger indicators of topical importance.

2. **Entity does not match any existing term:** If an entity has no matching n-gram (e.g., a brand name like "Bradford White" that was mentioned once per page and didn't survive n-gram coverage gating), it is added to the term list as a new entry with `"source": "entity_only"` and `"is_entity": true`. It still goes through recommendation scoring in Module 13 like any other term.

**Match logic:** An entity matches a term if the lemmatized entity name exactly equals the lemmatized term, or if the entity name is a variant listed in `ner_variants` that matches a term.

**Merged term output example:**

```json
{
  "term": "tankless water heater",
  "is_entity": true,
  "entity_category": "equipment",
  "avg_salience": 0.51,
  "ner_variants": ["tankless heater", "on-demand water heater"],
  "source": "ngram_and_entity",
  "total_count": 14,
  "pages_found": 8,
  "recommendation_score": 0.88,
  "recommendation_category": "required",
  "confidence": "high"
}
```

**Entity-only term output example:**

```json
{
  "term": "Bradford White",
  "is_entity": true,
  "entity_category": "brand",
  "avg_salience": 0.44,
  "ner_variants": ["Bradford White"],
  "source": "entity_only",
  "total_count": 4,
  "pages_found": 4,
  "recommendation_score": 0.62,
  "recommendation_category": "required",
  "confidence": "medium"
}
```

**Requirements:**

- Must merge entities into the term list after Module 11 and before Module 13 scoring.
- Must enrich matching terms with entity metadata rather than creating duplicates.
- Must add non-matching entities as new entries with `"source": "entity_only"`.
- Must apply a `1.15x` scoring multiplier to dual-signal terms (`"source": "ngram_and_entity"`) in Module 13.
- Must preserve `ner_variants` on all entity-sourced terms for traceability.
- The final output must contain a single unified `terms` list — no separate `entities` array.

### Entity Categories

- Services
- Products
- Tools
- Equipment
- Brands
- Locations
- People
- Organizations
- Regulations
- Concepts
- Problems
- Symptoms
- Materials
- Methods
- Comparisons
- Pricing factors

### Requirements

- Must use Google Natural Language API as the primary extraction source (Pass 1).
- Must use cleaned, noise-filtered page text as NLP API input.
- Must apply a salience threshold of `0.40` consistently — no two-tier approach.
- Must aggregate NER results across all content-eligible pages before LLM pass.
- Must deduplicate cross-page entity variants in the LLM pass.
- Must include `avg_salience` score in final output.
- Must include `ner_variants` array to show merged forms.
- The LLM may categorize and deduplicate but may not invent entities not returned by Google NLP.
- Each entity must include: entity name, category, pages found, avg salience, source URLs, example context, recommendation score, confidence level, and NER variants.
- Must deduplicate similar entities.
- Must exclude irrelevant brand names unless useful.
- Must exclude unrelated navigation/footer entities.
- Must preserve local entities when relevant to local SEO.
- Must flag pages where NLP API failed so entity coverage can be noted in warnings.

---

## Module 12: Word Count Analysis

### Purpose

Recommend a target content length based on ranking content.

### Output

```json
{
  "recommended_word_count": {
    "min": 1200,
    "target": 1500,
    "max": 1800
  }
}
```

### Requirements

- Use percentile-based calculation:
  - p25 = minimum recommendation
  - p50 = target recommendation
  - p75 = maximum recommendation
- Filter out pages with fewer than 800 words.
- Filter out pages with more than 5000 words.
- Allow configurable min/max filters.
- Exclude directories, forums, and non-content pages.
- Must preserve analyzed word counts for debugging.
- Must flag when too few valid pages are available.

---

## Module 13: Recommendation Scoring Engine

### Purpose

Score all items in the unified term list (n-gram terms, entities, and merged entries) based on usefulness for content creation.

This module separates raw competitor data from actionable recommendations.

### Inputs

- Semantic similarity score
- TF-IDF distinctiveness score (from Module 9)
- Pages found
- Total count
- Zone distribution
- Rank position of source pages
- Presence in title
- Presence in H1
- Presence in H2
- Presence in H3
- Presence in paragraphs
- Entity category
- Page category
- Boilerplate likelihood
- Entity signal (`is_entity`, `avg_salience`, `source` — dual-signal terms receive a scoring boost)

### Output

```json
{
  "term": "water heater repair cost",
  "recommendation_score": 0.84,
  "recommendation_category": "required",
  "recommendation_type": "primary_supporting_term",
  "confidence": "high",
  "reason": "Appears across 7 ranking pages, commonly in H2s, semantically close to target keyword."
}
```

### Recommendation Categories

All items in the unified term list (n-gram terms, entity-only terms, merged entries, and quadgrams) that pass the full filtering pipeline (coverage gate → TF-IDF → semantic filtering → scoring) are classified as **Required**. There is no Recommended / Optional tier. If a term survives the pipeline, it belongs in the content.

The only exception is the **Avoid** classification, which is applied to terms identified as boilerplate, brand-specific noise, or overoptimized outliers that should explicitly not be used.

- Required
- Avoid

### Target Keyword Handling

The primary target keyword (e.g., "water heater repair") must always appear in the output as a Required term with the following minimum usage rules, regardless of competitor analysis:

- **Title:** At least 1 occurrence
- **H1:** At least 1 occurrence
- **Paragraphs:** At least 1 occurrence

The target keyword is exempt from coverage gating, TF-IDF filtering, and semantic filtering. It is inserted directly into the Required terms list with a fixed recommendation score of `1.00` and confidence `"high"`.

**Minimum usage floor:** The minimum usage values above (1 in title, 1 in H1, 1 in paragraphs) act as a floor. When Module 14 computes percentile-based usage ranges from competitor data, the final recommendation for the target keyword uses the *higher* of the two minimums per zone. For example, if Module 14 computes a paragraph range of min: 4 / target: 6 / max: 8, the target keyword's paragraph minimum becomes 4 (not 1). If Module 14 computes a paragraph range of min: 0 / target: 1 / max: 2, the target keyword's paragraph minimum stays at 1 (the floor).

Sub-phrases of the target keyword (e.g., "water heater" and "heater repair" from "water heater repair") must go through the normal pipeline. They are not automatically included or excluded — they are treated as any other bigram candidate. However, they must not be subsumed by the target keyword itself during n-gram subsumption (Module 8), since they may have independent usage patterns across competitor pages.

```json
{
  "term": "water heater repair",
  "is_target_keyword": true,
  "recommendation_score": 1.00,
  "recommendation_category": "required",
  "confidence": "high",
  "minimum_usage": {
    "title": 1,
    "h1": 1,
    "paragraphs": 1
  }
}
```

### Recommendation Types

- Primary supporting term
- Secondary supporting term
- Entity candidate
- Overused/noisy term
- Boilerplate term
- Brand-specific term
- Location-specific term

### Scoring Requirements

- Prioritize terms found across multiple unique URLs.
- Boost terms found in important zones.
- Boost terms from higher-ranking pages.
- Boost terms that appear in headings across multiple pages.
- Penalize terms appearing on only one page.
- Penalize boilerplate/navigation terms.
- Penalize weak semantic matches.
- Penalize brand-specific terms unless relevant.
- Penalize terms from excluded page categories.
- Penalize suspiciously high usage from one overoptimized page.

### Scoring Weights

```json
{
  "semantic_similarity_weight": 0.25,
  "tfidf_distinctiveness_weight": 0.10,
  "pages_found_weight": 0.25,
  "zone_importance_weight": 0.20,
  "rank_weight": 0.10,
  "intent_alignment_weight": 0.10
}
```

### Input Normalization

Before applying weights, all scoring inputs must be normalized to a 0–1 scale using min-max normalization across the candidate set:

```text
normalized_value = (value - min_value) / (max_value - min_value)
```

This prevents inputs with different natural scales from dominating the score. For example, `semantic_similarity` naturally ranges 0.0–1.0 while `pages_found` could range 1–10. Without normalization, `pages_found` would overpower other signals at higher weights.

Apply min-max normalization independently per input across all candidate terms in the current run. If all candidates share the same value for an input (e.g., all have `pages_found = 5`), set the normalized value to `0.5` for that input to avoid division by zero.

**Note on intent alignment:** Without a dedicated intent classification module, intent alignment is inferred from the page category distribution in Module 3. If the majority of content-eligible pages are local service pages, terms found predominantly on local service pages receive a higher intent alignment score than terms found only on informational articles.

### Quadgram Zone-Weighting

Quadgrams (4-word phrases) receive a zone multiplier applied on top of the base `zone_importance_weight` when they appear in high-signal zones. This reflects the fact that 4-word phrases in titles and headings almost always represent deliberate, intent-specific terminology rather than incidental co-occurrence.

**Multiplier rules:**

- Quadgram found in title or H1 on 2+ pages: apply `1.5x` zone importance multiplier
- Quadgram found in H2 on 2+ pages: apply `1.4x` zone importance multiplier
- Quadgram found in H3 on 2+ pages: apply `1.2x` zone importance multiplier
- Quadgram found only in paragraphs: no multiplier (standard scoring)

**Additional quadgram scoring rules:**

- Quadgrams that passed the coverage threshold via exception (Module 8) must still receive the zone multiplier if found in title/H1/H2.
- Quadgrams must be flagged in their recommendation output with `"n_gram_length": 4` and `"zone_boost_applied": true` so downstream modules understand why a lower-frequency phrase is ranked highly.
- Quadgrams must never be penalized for low raw frequency if they qualify for zone boost.

**Updated output example:**

```json
{
  "term": "emergency water heater repair service",
  "n_gram_length": 4,
  "recommendation_score": 0.79,
  "zone_boost_applied": true,
  "zone_boost_reason": "Found in H2 on 4 ranking pages",
  "recommendation_category": "required",
  "recommendation_type": "primary_supporting_term",
  "confidence": "high",
  "reason": "4-word phrase appearing in H2 across 4 ranking pages. Zone multiplier applied (1.4x). Strong intent-specific topical signal."
}
```

### Confidence Levels

Every recommendation must include a confidence level:

- High
- Medium
- Low

### Confidence Rules

High confidence usually requires:

- Found across multiple ranking pages
- Semantically relevant
- Appears in meaningful content zones
- Not likely boilerplate

Medium confidence usually means:

- Relevant but less common
- Strong semantic match but lower page coverage
- Found in useful zones but not widely repeated

Low confidence usually means:

- Weak page coverage
- Lower semantic similarity
- Possible boilerplate
- Appears mainly on one page

---

## Module 14: Usage Recommendation Engine

### Purpose

Generate recommended usage ranges for important terms by content zone.

### Output

```json
{
  "term": "emergency plumber",
  "mode": "safe",
  "usage": {
    "title": "0–1",
    "h1": "0–1",
    "h2": "1–2",
    "h3": "0–2",
    "paragraphs": "2–5"
  },
  "confidence": "high",
  "warning": null
}
```

### Requirements

- Use percentile-based ranges.
- Normalize term frequency per 1000 words.
- Separate recommendations by zone:
  - Title
  - Meta description
  - H1
  - H2
  - H3
  - Paragraphs
- Must not recommend keyword stuffing.
- Must interpret usage ranges as guidance, not strict requirements.
- Must include confidence levels.
- Must include warnings when a recommendation may be noisy or overoptimized.

### Frequency Formula

For each page and term:

```text
term_frequency_per_1000_words = term_count / word_count * 1000
```

Across eligible pages:

```text
min = p25 frequency
target = p50 frequency
max = p75 frequency
```

Convert frequency back into recommended usage based on target article word count:

```text
recommended_count = frequency_per_1000_words * target_word_count / 1000
```

### Example Output

```json
{
  "term": "water heater repair",
  "paragraph_usage": {
    "min": 2,
    "target": 4,
    "max": 6
  }
}
```

### Outlier Mode: Aggressive vs. Safe

The system must support two outlier-handling modes, selectable per run. This controls how single-page frequency outliers affect percentile calculations.

#### Safe Mode (default)

Before computing percentile ranges, detect single-page outliers per term. If one page uses a term at 3x or more the median frequency of all other pages, exclude that page's frequency from the percentile calculation for that term.

**Example:** If 9 pages use "emergency water heater repair" 1–3 times, but one page uses it 18 times, Safe Mode excludes the outlier page. The p25/p50/p75 range is computed from the remaining 9 pages only.

```json
{
  "term": "emergency water heater repair",
  "mode": "safe",
  "outlier_pages_excluded": 1,
  "outlier_page_url": "https://spammy-competitor.com",
  "outlier_frequency": 18,
  "corpus_median_frequency": 2.3,
  "usage": {
    "paragraphs": {
      "min": 1,
      "target": 2,
      "max": 3
    }
  }
}
```

#### Aggressive Mode

Include all pages in the percentile calculation, including outliers. This benchmarks against the most-used competitor pages, which may produce higher usage recommendations. Useful when the user wants to match or exceed the most aggressive competitors.

```json
{
  "term": "emergency water heater repair",
  "mode": "aggressive",
  "outlier_pages_excluded": 0,
  "usage": {
    "paragraphs": {
      "min": 2,
      "target": 4,
      "max": 8
    }
  },
  "warning": "Aggressive mode includes competitor outlier pages. High-end recommendations may reflect keyword stuffing patterns."
}
```

**Requirements:**

- Must support `"mode": "safe"` (default) and `"mode": "aggressive"` as a run-level configuration.
- Safe Mode must detect outliers using a 3x median threshold per term per zone.
- Safe Mode must exclude outlier pages only for the specific term where the outlier occurs — the page is not globally excluded.
- Safe Mode must log excluded outlier pages with their URL and frequency.
- Aggressive Mode must include all pages and add a warning when p75 exceeds 2x the p50.
- Mode must be selectable at runtime via a configuration parameter.
- Both modes must still apply the over-optimization cap: if the recommended max usage exceeds 10 occurrences per 1,000 words for any single term, flag it regardless of mode.

---

# 6. 📊 Data Model

## Final Output Model

```json
{
  "schema_version": "1.0",
  "keyword": "",
  "location_code": "",
  "language_code": "",
  "outlier_mode": "safe",
  "cached": false,
  "cache_date": null,
  "run_date": "",
  "serp_summary": {
    "analyzed_urls": [],
    "excluded_urls": [],
    "failed_urls": [],
    "dominant_page_type": ""
  },
  "word_count": {
    "min": 0,
    "target": 0,
    "max": 0,
    "source_word_counts": []
  },
  "terms": {
    "required": [],
    "avoid": [],
    "low_coverage_candidates": []
  },
  "term_signals": {
    "coverage_threshold_applied": true,
    "tfidf_threshold_applied": true,
    "terms_filtered_by_coverage": 0,
    "terms_filtered_by_tfidf": 0,
    "terms_passed_to_embedding": 0,
    "subsumption_merges": 0
  },
  "usage_recommendations": [],
  "target_keyword": {
    "term": "",
    "is_target_keyword": true,
    "recommendation_score": 1.00,
    "minimum_usage": {
      "title": 1,
      "h1": 1,
      "paragraphs": 1
    }
  },
  "warnings": []
}
```

## Output Storage

Analysis results are persisted to Supabase for caching and downstream consumption.

**Table:** `keyword_analyses` (or equivalent — schema to be defined during implementation)

**Storage requirements:**

- Must store the complete output JSON per keyword + location run.
- Must store a `run_date` timestamp.
- Must support lookup by keyword + location to enable 7-day cache checks.
- Must support `force_refresh` override that bypasses cache and writes a new row.
- Must not delete previous runs when a fresh analysis is triggered — historical results are preserved.
- Schema design is deferred to implementation. The PRD defines the JSON output shape (above); the Supabase table structure should store it efficiently but does not need to decompose every nested field into separate columns.

---

# 7. ⚙️ Functional Requirements

## Must Have

- Keyword input with outlier mode selection
- DataForSEO SERP collection
- SERP URL classification
- Content-eligible URL filtering
- ScrapeOwl page scraping
- Zone-based content extraction
- Noise filtering
- Lemmatized n-gram analysis (unigrams through quadgrams)
- N-gram subsumption
- Term aggregation
- Coverage threshold gating
- TF-IDF pre-filtering (as gate and scoring input)
- Google Natural Language API entity extraction (NER, salience ≥ 0.40)
- LLM entity categorization and deduplication
- Embedding-based semantic filtering
- Percentile-based word count recommendations
- Percentile-based usage recommendations with aggressive/safe mode
- Recommendation scoring with TF-IDF and quadgram zone-weighting
- Target keyword auto-inclusion with minimum usage rules
- Required / Avoid classification (no ambiguous tiers)
- Confidence levels on all recommendations
- Five-layer noise filtering (structural, text density, cross-page fingerprinting, heuristic, frequency anomaly)
- Entity–term merge into unified term list
- 7-day result caching with force-refresh option
- Minimum page threshold (5 pages) with degraded-confidence continuation
- Modular pipeline architecture
- Error handling
- Rate-limit handling

## Should Have

- Rank-weighted recommendations
- Excluded URL reporting
- Scrape failure reporting
- Dynamic semantic threshold logic
- Outlier page logging in safe mode

## Nice to Have

- Batch keyword processing
- Historical tracking and re-analysis
- Configurable lemmatizer selection
- Custom stopword lists

---

# 8. 🚨 Constraints

## Platform Constraints

- Must integrate as an internal module within the larger SaaS platform.
- Must be callable by upstream orchestration (API endpoint, task queue, or direct function call).
- Must return structured JSON output consumable by downstream modules.

## API Constraints

- Must handle DataForSEO API limits.
- Must handle ScrapeOwl API limits.
- Must handle OpenAI API rate limits.
- Must handle Google Natural Language API rate limits and 100,000 byte input cap.
- Must handle concurrent Google NLP API requests with rate limiting (the `analyzeEntities` endpoint processes one document per request — there is no batch endpoint).
- Must support retries.
- Must support rate-limit backoff between burst requests.
- Must support failed item recovery.

## Processing Constraints

- Must avoid processing too many n-grams unnecessarily.
- Must apply coverage gating and TF-IDF filtering before embeddings to reduce API cost.
- Must batch embedding requests when possible.
- Must deduplicate and lemmatize terms before embeddings.
- Must cap candidate terms before semantic filtering when needed.
- Must avoid LLM calls on raw noisy content.
- Must preserve enough debugging data to inspect failures.

---

# 9. 🛡️ Guardrails

## Keyword Stuffing Guardrails

The system must not recommend keyword stuffing.

Usage ranges should be framed as:

- Natural inclusion guidance
- SERP pattern guidance
- Topical coverage signals

Not as:

- Exact quotas
- Required repetition counts
- Density targets

Both aggressive and safe modes must apply the hard cap of 10 occurrences per 1,000 words per term.

## False Precision Guardrails

The system must avoid making weak recommendations sound exact.

Every major recommendation should include:

- Confidence level
- Reason
- Supporting page coverage
- Warning when confidence is low

## LLM Hallucination Guardrails

The LLM must not invent:

- Entities
- Competitor patterns
- Statistics
- SERP claims

All entity recommendations must be grounded in Google NLP API output from scraped SERP data. The LLM may only categorize, deduplicate, and filter — never invent.

## Minimum Page Threshold

The pipeline requires a minimum of **5 content-eligible, successfully scraped pages** to proceed. If fewer than 5 pages are available after URL classification and scraping, the pipeline continues but attaches a prominent warning to the output:

```json
{
  "warning_level": "critical",
  "warning": "Only N content-eligible pages were available. Recommendations may be unreliable due to insufficient sample size.",
  "pages_available": N
}
```

The pipeline must never abort silently. It always produces output, even with degraded confidence.

## Noisy SERP Guardrails

The system must flag:

- Too few eligible pages (fewer than 5 content-eligible pages — see above)
- Too many failed scrapes (more than 30% failure rate)
- Directory-heavy SERPs
- Forum-heavy SERPs
- Outlier word counts
- Overoptimized competitor pages
- Heavy boilerplate contamination

---

# 10. 📈 Success Metrics

## Module Quality Metrics

- Successful scrape rate
- Failed scrape rate
- Average processing time per keyword
- API cost per keyword (DataForSEO + ScrapeOwl + Google NLP + OpenAI embeddings)
- Number of usable Required terms per run
- Percentage of low-confidence recommendations
- Percentage of hallucination-free entity outputs
- Coverage gate pass-through rate
- TF-IDF filter pass-through rate
- Semantic filter pass-through rate
- Average number of entities extracted per keyword
- Subsumption merge rate

## Downstream Impact Metrics (measured by consuming modules)

- Percentage of generated pages ranking in top 10
- Organic traffic growth for optimized pages
- Content gap reduction vs. SERP competitors
- Coverage of SERP topics in generated content

---

# 11. 🧪 MVP Scope

## MVP Should Include

1. Keyword input with outlier mode and force-refresh option
2. DataForSEO SERP collection
3. SERP URL classification
4. ScrapeOwl scraping
5. Zone extraction
6. Five-layer noise filtering (all layers including cross-page fingerprinting)
7. Lemmatized n-gram generation (stopwords removed from unigrams only)
8. N-gram subsumption
9. Term aggregation
10. Coverage threshold gating
11. TF-IDF pre-filtering (as gate and scoring input)
12. Embedding-based semantic filtering
13. Google NLP API entity extraction (salience ≥ 0.40)
14. LLM entity categorization and deduplication
15. Entity–term merge into unified term list
16. Word count recommendation
17. Recommendation scoring (with min-max normalization, TF-IDF input, quadgram zone-weighting)
18. Target keyword auto-inclusion
19. Usage recommendations with aggressive/safe mode
20. Minimum page threshold (5) with degraded-confidence continuation
21. 7-day Supabase result caching with force-refresh
22. Supabase output storage

## MVP Can Exclude

- Batch keyword processing
- Historical trend tracking across multiple runs
- Configurable lemmatizer selection
- Custom stopword lists

---

# 12. 🏁 Summary

The SERP Intelligence Engine — Term & Entity Analysis Module is the keyword and entity extraction layer of a larger blog content generation SaaS. It combines:

- SurferSEO-style keyword usage analysis
- Clearscope-style semantic relevance filtering
- Google NLP-grounded entity extraction merged into a unified term list
- TF-IDF distinctiveness scoring (as both filter and scoring signal)
- Quadgram zone-weighting for intent-specific phrase detection
- Lemmatized n-gram subsumption to eliminate redundancy
- Coverage threshold gating to eliminate noise
- Configurable aggressive/safe outlier handling

The key design principle is:

Raw SERP data should not automatically become editorial guidance.

Instead, the system must lemmatize, subsume, gate by coverage, filter by distinctiveness, filter by semantic relevance, score by multi-signal weighting, and validate — all before a term earns Required status.

Every term in the output survived a five-stage pipeline. That is the product.


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/modules/research-citations-module-prd-v1_1_1.md -->
<!-- ============================================================ -->

# PRD: Research & Citations Module

**Version:** 1.1
**Status:** Draft
**Last Updated:** April 29, 2026
**Part of:** [Parent Content Creation Platform — TBD name]
**Upstream Dependency:** Content Brief Generator Module (v1.7+)
**Downstream Dependency:** Content Writer Module

---

## 1. Problem Statement

AI-generated content is prone to hallucinated statistics, fabricated studies, and unverified claims. Even when a content brief provides a strong structural foundation, the Content Writer Module has no mechanism to ground factual assertions in real, verifiable sources — leaving both readers and site owners exposed to credibility risk. This module sits between the Content Brief Generator and the Content Writer to solve that problem: for every content section, it discovers authoritative real-world sources, extracts specific quotable claims and data points, **verifies each claim against the source text before accepting it**, and maps the verified claims back to the heading structure. The Writer Module receives a citations-enriched brief where every factual assertion has a real, verified source attached before a single word is written.

---

## 2. Goals

- Accept the full content brief JSON output from the Content Brief Generator and return a citations-enriched version
- Map at least one authoritative citation to every content H2 (excluding conclusion and FAQ sections)
- Provide dedicated citations for the highest-priority authority gap H3s (up to 3 per article) — these sections carry the highest novel-claim risk
- Extract specific quotable claims and data points from each source — and verify each claim appears in the source text before accepting it
- Tier sources by authority (government/academic > major publications > general web)
- Exclude competitor SERP URLs from citation candidates
- Prevent hallucinated claims in downstream content by providing the Writer Module with verified, source-anchored data points for every section
- Enable inline hyperlink references in the final article by including full publication metadata alongside each citation

### Out of Scope (v1)

- Citation formatting for style guides (APA, MLA, Chicago) — downstream Writer Module responsibility
- Inline link placement decisions within prose — Writer Module responsibility
- Citation monitoring or link rot detection post-publish
- Paywalled content access
- Non-English sources — English-only in v1
- Multi-locale support — English / United States only
- User-facing citation management UI
- Academic database API integrations (PubMed, CrossRef) — web search only in v1

---

## 3. Success Metrics

Success in v1 is defined by structural validity, claim verification rates, and operational discipline. All metrics are measurable from the module's own output and logs.

| Metric | Target |
|---|---|
| Output validates against JSON schema | 100% |
| Every content H2 has ≥1 citation | 100% |
| 100% of accepted claims pass verification against source text | 100% |
| Minimum 1 Tier 1 or Tier 2 citation per article | 100% |
| All returned citations are accessible (non-paywalled, non-404, non-bot-blocked) at time of generation | ≥90% |
| End-to-end generation completes within 120s | ≥95% |
| Cost per article stays under $0.50 | ≥95% |

---

## 4. System Architecture Overview

```
[Content Brief JSON (from Brief Generator)]
      │
      ▼
┌─────────────────────┐
│  Step 0: Input      │  ◄── Validate incoming brief against schema
│  Validation         │  ◄── Extract content H2s, top 3 authority gap H3s,
│                     │      and competitor domains
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 1: Research   │  ◄── LLM generates 2–3 search queries per H2
│  Query Generation   │      and per selected authority gap H3
│  (Parallel)         │  ◄── Queries target statistics, studies, data
└─────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Source Discovery (Parallel per heading)             │
│  ◄── DataForSEO Web Search                                  │
│  ◄── Top 5 results per query, deduped per heading           │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 3: Source     │  ◄── Apply tier classification (1–3)
│  Filtering &        │  ◄── Exclude competitor domains
│  Tiering            │  ◄── Apply recency rules; hard exclude >5 years
│                     │  ◄── Exclude sources with no detectable date
└─────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Content Fetching (Parallel per candidate)           │
│  ◄── Scrape HTML / Extract text from PDFs                   │
│  ◄── Detect paywalls, bot-block challenges, non-English     │
│  ◄── Top 3 accessible candidates per heading proceed        │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 5: Winner     │  ◄── Pre-LLM ranking by tier + recency
│  Selection &        │      + meta snippet relevance
│  Verified Claim     │  ◄── LLM extracts claims from winner only
│  Extraction         │  ◄── Verify each claim against source text
│                     │  ◄── Fall back to next candidate on failure
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 6: Citation   │  ◄── Final score (tier + recency + max claim relevance)
│  Scoring &          │  ◄── Threshold 0.45; flag below
│  Finalization       │  ◄── Flag shared citations
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 7: Supple-    │  ◄── Add up to 4 article-level citations
│  mental Citations   │      to enrich the citation pool
│                     │  ◄── No minimum requirement; accept what's available
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Step 8: Output     │  ◄── citation_ids on all heading items
│  Assembly           │  ◄── Build citations array (heading + authority_gap + article)
│                     │  ◄── Extend metadata with citations_metadata block
└─────────────────────┘
      │
      ▼
[Citations-Enriched Brief JSON → Content Writer Module]
```

---

## 5. Functional Requirements

### Step 0 — Input Validation

| Rule | Action |
|---|---|
| Input is not valid JSON | Reject with structured error |
| Input does not conform to content brief schema v1.7+ | Reject with structured error |
| `heading_structure` is empty or missing | Reject with structured error |
| `heading_structure` contains 0 content H2s | Reject with structured error |
| `metadata.competitor_domains` is missing | Proceed without exclusion list; flag `competitor_exclusion_unavailable: true` |

**Content H2 extraction rules:**

From `heading_structure`, extract all items where `level: "H2"` AND `type: "content"`. Explicitly exclude items typed `faq-header`, `faq-question`, or `conclusion`, and any H2 with text matching "Frequently Asked Questions".

**Authority gap H3 selection rules:**

From `heading_structure`, extract all items where `level: "H3"` AND `source: "authority_gap_sme"`. If more than 3 such items exist, select the top 3 by `heading_priority`. These selected H3s become independent citation targets — they receive dedicated citations in addition to inheriting the parent H2's citation.

**Upstream schema dependency:**

This module requires `metadata.competitor_domains` in the Brief Generator output (see Section 12).

---

### Step 1 — Research Query Generation

**Method:** Single LLM call per citation target (each content H2 and each selected authority gap H3), all calls run in parallel

**Inputs per call:**
- Seed keyword (`brief.keyword`)
- Heading text (H2 or authority gap H3)
- Intent type (`brief.intent_type`)
- For H2 calls only: any non-authority-gap H3 heading texts nested under this H2 (for additional context)
- For authority gap H3 calls only: parent H2 text (for context)

**LLM prompt template (H2 variant):**

```
You are a research assistant helping find authoritative citations for a blog post section.

Keyword: {keyword}
Section heading: {h2_text}
Supporting subheadings: {h3_texts_or_none}
Content intent: {intent_type}

Generate 2–3 search queries specifically designed to find:
- Statistics, data points, or quantified research findings relevant to this section
- Official government guidance, regulatory information, or peer-reviewed studies
- Credible expert analysis, industry data, or named institutional reports

Return a JSON array of query strings only. Queries must be specific and factual in nature, designed to surface authoritative sources rather than opinion pieces or competitor blog posts. Do not include the domain name of any specific site in the queries.
```

**LLM prompt template (authority gap H3 variant):**

```
You are a research assistant helping find authoritative citations for a specific informational gap in a blog post.

Keyword: {keyword}
Parent section: {h2_text}
Specific subheading addressing an information gap: {h3_text}
Content intent: {intent_type}

This subheading was identified as missing from competing content — it represents a specific informational gap that needs strong, verified sources.

Generate 2–3 search queries specifically designed to find:
- Statistics or data points directly relevant to this specific subtopic
- Authoritative sources (government, academic, regulatory) addressing this exact angle
- Expert analysis or research findings on this niche aspect

Return a JSON array of query strings only.
```

**Output:** 2–3 search query strings per citation target

**Per-call timeout:** 25 seconds. On timeout, retry once. On second timeout, fall back to a generic query: `"{keyword}" "{heading_text}" statistics OR study OR report`.

---

### Step 2 — Source Discovery

**Provider:** DataForSEO Web Search API (Standard Queue)
**Locale:** English / United States

**Process per citation target:**
1. Execute all 2–3 queries generated in Step 1
2. Collect top 5 organic results per query
3. Deduplicate URLs across queries for the same target (retain highest position)
4. Up to 15 unique candidate URLs per target

**Execution:** All search batches run in parallel

**Captured per result:** URL, page title, meta description, root domain

---

### Step 3 — Source Filtering & Tiering

**Competitor domain exclusion:**
Strip any candidate URL whose root domain appears in `metadata.competitor_domains`.

**Tier classification:**

| Tier | Label | Criteria |
|---|---|---|
| Tier 1 | Authoritative | `.gov` domains; `.edu` domains; WHO, CDC, FDA, NIH, NIST, EPA, and recognized international health/regulatory bodies; indexed peer-reviewed academic journals |
| Tier 2 | Credible | Major news organizations (Reuters, AP, BBC, Washington Post, NYT, WSJ); established industry trade publications; recognized research and data firms (Pew, Gartner, McKinsey, Statista, Forrester, IBISWorld) |
| Tier 3 | General | All other HTTPS sources passing basic quality heuristics |
| Excluded | — | Competitor SERP domains; social media platforms (Twitter/X, Facebook, Instagram, TikTok, Reddit); Wikipedia; HTTP-only domains; content farms (blocklist in engineering spec); redirect chains where final destination is unreachable |

**Tier 3 quality heuristics — all must pass:** HTTPS only; final destination resolves; not a content farm; not a social or forum site.

**Recency classification:**

| Label | Age Range | Score |
|---|---|---|
| `fresh` | <1 year | 1.00 |
| `dated` | 1–3 years | 0.65 |
| `stale` | 3–5 years | 0.30 |
| Hard excluded | >5 years | — |

**Recency exception:** Tier 1 sources older than 5 years are permitted only if they represent foundational law, legislation, landmark studies, or established scientific consensus. Flag `recency_exception: true`. Flat score of 0.50.

**Date detection rule:** If a publication or last-updated date cannot be reliably extracted from the source (meta tags, JSON-LD, or body), the source is excluded from the candidate pool. Sources without a verifiable date are not eligible for citation.

**Sort order:** Tier 1 → Tier 2 → Tier 3; within each tier: `fresh` → `dated` → `stale`. Top 5 candidates per target pass to Step 4.

---

### Step 4 — Content Fetching & Extraction

**Provider:** ScrapeOwl (consistent with upstream scraping infrastructure) or equivalent
**Execution:** All fetches run in parallel across all citation targets

**Content type handling:**

| Source Type | Detection | Extraction |
|---|---|---|
| HTML | Default `Content-Type: text/html` | Standard ScrapeOwl scrape; strip nav/footer/sidebar/boilerplate |
| PDF | `Content-Type: application/pdf` OR URL ending `.pdf` | PDF text extractor (pypdf or equivalent); extract body text plus PDF metadata for date/author |
| Other (DOCX, etc.) | Any other content type | Skip; treat as fetch failure |

PDFs are common for Tier 1 sources (government reports, academic papers, regulatory documents). PDF text extraction is required, not optional.

**Extracted per source:**
- Body text (cleaned)
- Canonical title
- Author name (byline, meta tags, JSON-LD, or PDF metadata)
- Publication name (meta, JSON-LD, or masthead)
- Published or last-updated date (meta tags, JSON-LD, body, or PDF metadata — prefer `datePublished`)

**Paywall detection:**
Flag `paywall_detected: true` if any of:
- Login wall or subscription gate in rendered page
- Body content <300 words AND subscription CTA language present
- Page redirects to account/login URL

**Bot-block / challenge detection:**
Flag `bot_block_detected: true` if the response is HTTP 200 OK but the body matches any of:
- Cloudflare challenge markers ("Just a moment...", "Verifying you are human", "Checking your browser")
- CAPTCHA challenge markers ("verify you're not a robot", reCAPTCHA fingerprints)
- Body content <200 words AND challenge-related JavaScript fingerprints present
- Akamai / DataDome / PerimeterX challenge page signatures

Bot-blocked sources are removed from the candidate pool. Treat as fetch failure; move to next candidate.

**Language detection:**
Run a lightweight language detector (e.g., `langdetect` or `cld3`) on the extracted body text. If detected language is not English (`en`), exclude the source. Flag `language_excluded: true` for observability.

**Fetch cap:** Top 3 accessible candidates per citation target proceed to Step 5. "Accessible" means: non-paywalled, non-bot-blocked, English-language, with detectable date.

---

### Step 5 — Winner Selection & Verified Claim Extraction

This step is restructured from v1.0 to extract claims only from the winning candidate, then verify each claim against the source text before accepting it.

**Stage 5a — Pre-LLM winner selection:**

For each citation target, rank the 3 accessible candidates by a pre-LLM score using only metadata available without an LLM call:

```
pre_llm_score = (0.50 × tier_score) + (0.35 × recency_score) + (0.15 × meta_snippet_match)

Where:
  meta_snippet_match = cosine similarity between heading text and meta description (using OpenAI text-embedding-3-small, reusing infrastructure from upstream brief module)
```

The candidate with the highest `pre_llm_score` is the provisional winner.

**Stage 5b — Claim extraction (winner only):**

Run a single LLM claim extraction call on the provisional winner.

**LLM prompt template:**

```
You are extracting specific, quotable factual claims from a source document to support a blog post section.

Blog post keyword: {keyword}
Section heading: {heading_text}

From the source text below, extract up to 5 specific, quotable claims or data points that:
- Are factual and specific (statistics, percentages, named study findings, official regulatory guidance, or direct expert quotes with attribution)
- Directly support the topic of the section heading above
- Are self-contained — understandable without the surrounding paragraph
- Are not editorial opinion, vague generalizations, or unquantified assertions

CRITICAL: Use the source's exact words and exact numbers. Do not paraphrase. Do not round. Do not infer values not stated in the text. If a claim cannot be quoted verbatim, do not include it.

Return a JSON array of objects only, with no preamble or markdown formatting:
[
  {
    "claim_text": "<the exact quoted text from the source — verbatim, including numbers>",
    "relevance_score": <float 0.0–1.0>
  }
]

Source text:
{source_text}
```

Source text is truncated to 6,000 tokens if needed (prioritize first 4,000 tokens).

**Per-call timeout:** 25 seconds. On timeout, treat as extraction failure.

**Stage 5c — Claim verification (deterministic, no LLM cost):**

For each extracted claim, run a verification pass against the full fetched source text:

1. **Verbatim match:** Exact substring match of `claim_text` (case-insensitive, whitespace-normalized) in the source body. Pass.
2. **Fuzzy match:** If verbatim fails, sliding-window fuzzy match using Levenshtein ratio ≥ 0.90 over windows the length of the claim. Pass.
3. **Number integrity check:** Extract all numeric tokens from `claim_text` (digits, percentages, currency values, dates). Every numeric token must appear in the source text exactly. If any numeric token in the claim is not present in the source, the claim **fails verification regardless of fuzzy match score** — number alteration is the most common hallucination pattern.
4. If verification fails: discard the claim. Log `verification_failed: true` with reason.

Only verified claims are retained. Discard any claim with `relevance_score < 0.50` after verification.

**Stage 5d — Fallback handling:**

| Outcome | Action |
|---|---|
| ≥1 verified claim above 0.50 relevance from winner | Accept; proceed to Step 6 |
| 0 verified claims from winner | Move to next candidate (rank 2). Re-run Stages 5b–5c. |
| 0 verified claims from rank 2 candidate | Move to rank 3. Re-run Stages 5b–5c. |
| 0 verified claims from any of top 3 candidates | Use the highest-scoring candidate's title + meta description as a fallback stub claim with `extraction_method: "fallback_stub"`, `relevance_score: 0.30`. Flag `citation_quality_low: true`. |

---

### Step 6 — Citation Scoring & Finalization

**Final scoring formula:**

```
citation_score = (0.40 × tier_score) + (0.30 × recency_score) + (0.30 × max_verified_claim_relevance)

Where:
  tier_score:       Tier 1 = 1.00, Tier 2 = 0.65, Tier 3 = 0.35
  recency_score:    fresh = 1.00, dated = 0.65, stale = 0.30, recency_exception = 0.50
  max_verified_claim_relevance = highest relevance_score among verified claims; if fallback stub, = 0.30
```

**Selection rules:**
- Minimum acceptable `citation_score`: **0.45** (raised from 0.30 in v1.0)
- Below threshold: accept the citation but flag `citation_quality_low: true`

**Deduplication:**
- The same URL may be selected for multiple citation targets — permitted
- When two candidates for the same target have a score difference of ≤0.05, prefer the candidate whose URL has not already been selected elsewhere
- Flag `shared_citation: true` on any URL assigned to more than one target

---

### Step 7 — Supplemental Citations

**Rule:** Supplemental article-level citations may be added to enrich the citation pool. **Maximum of 4 supplemental citations per article.** There is no minimum citation count required — accept whatever the pipeline produces.

**Process:**
1. Generate 2–3 search queries targeting the seed keyword broadly (not tied to a specific heading)
2. Run the full pipeline: search → filter/tier (Step 3) → fetch (Step 4) → winner selection + verified extraction (Step 5) → scoring (Step 6)
3. Add up to 4 selected sources as `scope: "article"` citations
4. Stop when: 4 supplementals added, or no more qualifying candidates exist

Supplemental citations are tagged `heading_order: null` and `scope: "article"` in the output.

---

### Step 8 — Output Assembly

The output is the complete content brief JSON passed through unchanged, with the following additions:

1. **Every** `heading_structure` item gains a `citation_ids` array (empty array `[]` for items with no citations — H1, FAQ items, conclusion, content H3s)
2. A top-level `citations` array is added
3. The `metadata` object is extended with a `citations_metadata` block

No existing fields from the content brief are modified or removed.

---

## 6. Output Schema

```json
{
  "keyword": "string",
  "intent_type": "...",
  "intent_confidence": 0.0,
  "intent_review_required": false,

  "heading_structure": [
    {
      "level": "H1 | H2 | H3",
      "text": "string",
      "type": "content | faq-header | faq-question | conclusion",
      "source": "...",
      "original_source": "string | null",
      "semantic_score": 0.0,
      "exempt": false,
      "serp_frequency": 0,
      "avg_serp_position": 0.0,
      "llm_fanout_consensus": 0,
      "heading_priority": 0.0,
      "order": 0,
      "citation_ids": []
    }
  ],

  "faqs": [ "..." ],
  "structural_constants": { "..." },
  "format_directives": { "..." },
  "discarded_headings": [ "..." ],
  "silo_candidates": [ "..." ],

  "citations": [
    {
      "citation_id": "cit_001",
      "heading_order": 2,
      "heading_text": "string",
      "scope": "heading | authority_gap | article",
      "url": "string",
      "title": "string",
      "author": "string | null",
      "publication": "string | null",
      "published_date": "string | null",
      "tier": 1,
      "recency_label": "fresh | dated | stale",
      "recency_exception": false,
      "pdf_source": false,
      "language_detected": "en",
      "citation_score": 0.0,
      "shared_citation": false,
      "citation_quality_low": false,
      "paywall_detected": false,
      "bot_block_detected": false,
      "claim_extraction_failed": false,
      "claims": [
        {
          "claim_text": "string",
          "relevance_score": 0.0,
          "extraction_method": "verbatim_extraction | fallback_stub",
          "verification_method": "verbatim_match | fuzzy_match | none"
        }
      ]
    }
  ],

  "metadata": {
    "...": "all existing brief metadata fields pass through unchanged",
    "competitor_domains": ["example.com"],

    "citations_metadata": {
      "total_citations": 0,
      "unique_urls": 0,
      "citations_by_scope": {
        "heading": 0,
        "authority_gap": 0,
        "article": 0
      },
      "citations_by_tier": {
        "tier_1": 0,
        "tier_2": 0,
        "tier_3": 0
      },
      "h2s_with_citations": 0,
      "h2s_without_citations": 0,
      "authority_gap_h3s_with_citations": 0,
      "supplemental_citations_added": 0,
      "competitor_exclusion_unavailable": false,
      "citations_schema_version": "1.1"
    }
  }
}
```

**Schema notes:**
- `citation_ids` is now present (as an empty array if applicable) on **every** heading item, eliminating the need for consumers to check field existence
- `scope: "heading"` = mapped to a content H2; `scope: "authority_gap"` = mapped to an authority gap H3; `scope: "article"` = supplemental, no heading mapping
- `extraction_method` distinguishes verbatim LLM extraction from fallback stubs derived from title + meta description — the Writer Module should not treat fallback stubs as basis for specific factual assertions
- `verification_method` records how each claim was verified against source text; `none` only appears for fallback stubs

---

## 7. Failure Mode Handling

| Scenario | Behavior |
|---|---|
| Incoming brief JSON fails schema validation | Abort with structured error |
| `heading_structure` contains 0 content H2s | Abort with structured error |
| Query generation LLM call times out (25s) twice | Fall back to generic query: `"{keyword}" "{heading_text}" statistics OR study OR report` |
| DataForSEO returns 0 results for all queries for a target | Flag `no_sources_found: true`; leave `citation_ids: []` for that heading |
| All candidates for a target are paywalled | Try next-tier candidates; if all fail, leave `citation_ids: []`; flag `all_candidates_paywalled: true` |
| All candidates for a target are bot-blocked | Same as paywalled; flag `all_candidates_bot_blocked: true` |
| All candidates for a target are non-English | Same as above; flag `all_candidates_excluded_by_language: true` |
| All candidates have no detectable date | Same as above; flag `all_candidates_undated: true` |
| PDF extraction fails | Treat as fetch failure; move to next candidate |
| Claim extraction LLM call times out (25s) | Treat as extraction failure; move to next candidate per Stage 5d |
| Claim extraction returns malformed JSON | Retry once with stricter prompt; on second failure, treat as extraction failure |
| All extracted claims fail verification | Treat as extraction failure; move to next candidate |
| All 3 candidates fail (no verified claims) | Use fallback stub from rank-1 title + meta; flag `citation_quality_low: true` |
| No candidate scores above 0.45 | Accept best available; flag `citation_quality_low: true` |
| ScrapeOwl fetch times out | Retry once with backoff; on failure, skip to next candidate |
| End-to-end exceeds 120s | Abort and notify user |
| `metadata.competitor_domains` absent | Continue without exclusion; flag `competitor_exclusion_unavailable: true` |

---

## 8. Performance Targets

**Trigger model:** Synchronous — fires immediately upon receiving the completed content brief JSON.

| Stage | Target | Max |
|---|---|---|
| End-to-end | 60s | 120s |
| Input validation + heading extraction | <1s | 2s |
| Research query generation (parallel) | 5s | 10s |
| Source discovery — DataForSEO searches (parallel) | 10s | 20s |
| Source filtering and tiering | 2s | 5s |
| Content fetching (HTML + PDF, parallel) | 15s | 30s |
| Winner selection + verified claim extraction (parallel per target, sequential within target on retry) | 20s | 40s |
| Citation scoring, supplementals, and output assembly | 5s | 12s |

All citation targets process in parallel. The slowest single target's chain determines stage time. **Per-LLM-call timeout: 25 seconds**, with one retry on timeout for query generation. Claim extraction failures fall through to the next candidate rather than retrying the same call.

---

## 9. Cost Model

| Component | Cost per Article |
|---|---|
| Research query generation (LLM, ~6 H2s + up to 3 authority gap H3s = ~9 calls, parallel) | ~$0.03 |
| DataForSEO Web Search (~24 queries) | ~$0.02–$0.03 |
| Content fetching — ScrapeOwl + PDF (3 candidates × 9 targets = ~27 fetches) | ~$0.05–$0.09 |
| Winner-only claim extraction (~9 calls + ~3 retries) | ~$0.05–$0.10 |
| Supplemental citation pipeline (if added) | ~$0.01–$0.03 |
| **Estimated total per article** | **$0.16–$0.28** |
| **Budget ceiling** | **$0.50** |

The shift to winner-only claim extraction (v1.0 ran extraction on all 3 candidates per target) cuts LLM extraction calls by ~60% versus a naive implementation, more than offsetting the addition of authority gap H3 citations.

**Monthly operational cost at 10–20 articles/day:** ~$50–$170/month

Combined with the upstream Brief Generator ($0.19–$0.53/brief), the combined pipeline cost per article is **$0.35–$0.81**, with a combined budget ceiling of **$1.25**.

---

## 10. Volume and Scale Assumptions

- **Current volume:** 10–20 articles/day (mirrors upstream Brief Generator)
- **Trigger source:** Automatic, synchronous — fires when Brief Generator completes
- **Concurrency:** Sequential per-user in v1, consistent with upstream module

---

## 11. Business Rules Summary

| Rule | Value |
|---|---|
| Locale | English / United States |
| Source language | English only — non-English sources excluded |
| Citation target scope | Content H2s + up to 3 highest-priority authority gap H3s |
| Maximum dedicated authority gap H3 citations | 3 per article |
| Maximum supplemental article-level citations | 4 per article |
| Minimum citations per content H2 | 1 |
| Minimum total citations per article | None (no hard floor; accept what pipeline produces) |
| Citation mapping granularity | H2 + selected authority gap H3s; other H3s inherit via parent H2 |
| Claim verification required | Yes — every claim must verbatim or fuzzy-match the source body, with all numeric tokens appearing exactly |
| Source tiers | 3 (Tier 1: Gov/Academic, Tier 2: Major Publications/Research Firms, Tier 3: General Web) |
| Competitor SERP domains | Excluded |
| Wikipedia | Excluded |
| Social media platforms | Excluded |
| Reddit | Excluded |
| Paywalled content | Excluded; flagged |
| Bot-blocked content | Excluded; flagged |
| Sources with no detectable date | Excluded |
| PDF sources | Supported via PDF text extraction |
| Recency hard exclude | >5 years (Tier 1 foundational sources excepted) |
| Claims per source | Up to 5; minimum verified `relevance_score` 0.50 |
| Candidate sources fetched per target | Top 3 accessible after filtering |
| Citation score minimum threshold | 0.45 (accept with `citation_quality_low: true` flag below this) |
| Shared citations | Permitted; flagged |
| Per-LLM-call timeout | 25 seconds |

---

## 12. Upstream Schema Dependency

This module requires one addition to the Content Brief Generator output schema (v1.7 → v1.8):

```json
"competitor_domains": ["example.com", "competitor.com"]
```

Root domains of all URLs returned in the SERP scrape (Step 1 of the Brief Generator). Until this field is added to the brief schema, the Research & Citations Module proceeds without competitor exclusion and flags `competitor_exclusion_unavailable: true`. This is a degraded state, not a hard failure.

The Brief Generator's `schema_version` should be incremented to `1.8` when this field is added.

---

## 13. What This PRD Does Not Cover

To be addressed in the engineering implementation spec:

- LLM model selection for query generation and claim extraction calls
- Content farm blocklist definition, hosting, and update process
- Tier 2 domain allowlist — specific enumeration of qualifying publications and research firms
- ScrapeOwl rate limiting, retry logic, session/concurrency management, and **robots.txt compliance verification**
- DataForSEO authentication, quota management, and cost tracking
- PDF extraction library selection (pypdf, PyMuPDF, etc.) and OCR fallback for scanned PDFs
- Language detection library selection (langdetect, cld3, fasttext)
- Caching strategy — citation results for a given keyword may be partially reused across briefs
- Schema versioning compatibility with Writer Module
- Citation link rot detection — deferred to a future monitoring module
- Academic database integrations (PubMed, CrossRef) — deferred to v2
- Coordination with Brief Generator team for `competitor_domains` field addition to schema v1.8

---

## 14. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-04-29 | Initial draft |
| 1.1 | 2026-04-29 | Added claim verification pass (verbatim + fuzzy + numeric integrity check); restructured Step 5 to extract claims from winner only (with fallback chain); added dedicated authority gap H3 citations (max 3/article); added PDF source handling; added bot-block detection; added English-only language detection; replaced minimum-4 citation requirement with maximum-4 supplemental citations cap; raised citation score threshold from 0.30 to 0.45; added 25s per-LLM-call timeout; `citation_ids` now present on all heading items; added `extraction_method` and `verification_method` fields on claims; sources without detectable dates now excluded |


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/modules/sources-cited-module-prd-v1_1.md -->
<!-- ============================================================ -->

# PRD: Sources Cited Module

**Version:** 1.1
**Status:** Draft
**Last Updated:** April 30, 2026
**Part of:** ShowUP Local — Content Generation Platform
**Upstream Dependencies:** Content Writer Module (v1.4+) · Research & Citations Module (v1.1+)
**Downstream Dependency:** Content Editor Module

---

## 1. Problem Statement

The Content Writer Module produces a complete blog post with factual claims grounded in verified citations from the Research & Citations Module. In v1.3, the Writer placed inline Markdown hyperlinks at the point of citation use. That approach conflates citation *marking* (which claim, in which sentence) with citation *formatting* (how the source is displayed to the reader) — leaving no clean separation between prose content and reference presentation.

This module introduces that separation. It receives the Writer's article JSON — now containing inline `{{citation_id}}` markers at the exact sentence of use — and the Research Module's verified citation pool. It resolves each marker into a numbered superscript with a jumplink, builds a formatted Sources Cited section in MLA style at the bottom of the article, and outputs a single enriched JSON document ready for the downstream Content Editor Module.

---

## 2. Goals

- Accept the Content Writer Module's structured JSON output (v1.4+, with `{{citation_id}}` inline markers) and the Research & Citations Module's citation pool as independent inputs
- Replace each `{{citation_id}}` marker in prose with a numbered HTML superscript linking to its corresponding entry in the Sources Cited section
- Assign citation numbers sequentially by order of first appearance in the article (top to bottom)
- Produce a formatted Sources Cited section in MLA-derived style (title, publication, URL only — author and date omitted in v1; see Section 7 Step 3 for rationale), containing only citations marked `used: true` by the Writer Module
- Render all external URLs in the Sources Cited section with `rel="nofollow"`
- Output an enriched JSON document that preserves the full Writer Module schema, with marker substitutions applied and a Sources Cited block appended to the article array
- Produce no net changes to prose content — only marker substitution and section addition

### Out of Scope (v1)
- Citation style formats other than the simplified MLA-derived format defined in Section 7 Step 3
- Author names and publication dates in MLA entries (deferred to v2 — see Section 7 Step 3 rationale)
- Inline hyperlinks within prose (handled in Sources Cited section only; prose contains superscripts, not hyperlinks)
- Citations for images, figures, or non-prose content
- Link-rot detection or citation validation post-generation
- User-facing citation management UI
- Footnote-style rendering (bottom-of-page floating notes) — jumplink anchors only
- Citation deduplication across articles or projects
- Multi-locale support — English / United States only
- CMS publishing or schema markup injection

---

## 3. Success Metrics

| Metric | Target |
|---|---|
| Output validates against JSON schema | 100% |
| Every `{{citation_id}}` marker in prose is replaced with a superscript | 100% |
| Every superscript jumplinks correctly to its Sources Cited entry | 100% |
| Sources Cited contains only `used: true` citations from the Writer output | 100% |
| All Sources Cited URLs rendered with `rel="nofollow"` | 100% |
| Citation numbers assigned in order of first appearance | 100% |
| End-to-end generation completes within 15s | ≥95% |
| Cost per article under $0.05 | ≥95% |

---

## 4. Upstream Dependency Changes

This module requires breaking changes to the Content Writer Module. These changes must ship as **Content Writer Module v1.4** before this module can operate.

### 4A — Inline Marker Output (Writer v1.3 → v1.4)

The Writer Module must place a `{{citation_id}}` marker at the exact point in prose where a verified claim is used, immediately following the sentence that contains the citation.

**Marker format:** `{{cit_001}}` — double curly braces wrapping the `citation_id` value, no spaces.

**Citation ID format constraint:** All `citation_id` values produced by the Research Module and consumed here must match the regex `^cit_[0-9]+$` (e.g., `cit_001`, `cit_42`). This constraint is required for safe and unambiguous marker pattern matching. The Research Module PRD should be updated to document this format constraint explicitly.

**Placement rule:** The marker is inserted *after the closing punctuation* of the sentence containing the cited claim.

**Multiple citations in one sentence:** If a single sentence references more than one citation, markers are stacked in the order the claims appear within that sentence: `{{cit_001}}{{cit_004}}`. Note that the rendered superscript order is sorted ascending by assigned citation number — see Step 2.

**Example (Writer v1.4 body output):**
```
Water heaters typically last 8–12 years before requiring replacement.{{cit_003}} The most common failure point is the anode rod, which degrades over time and accelerates tank corrosion.{{cit_007}}
```

**Per-section reconciliation:** The Writer Module continues to populate `citations_referenced` per article section (array of `citation_id` values used in that section's body). This field is used by this module for validation.

### 4B — Removal of Inline Hyperlink Placement (Writer v1.3 → v1.4)

The Writer Module must no longer place Markdown inline hyperlinks (`[anchor text](URL)`) in prose. The Sources Cited Module is the sole citation formatting layer. All citation presentation — numbering, linking, and reference listing — is handled here.

This change affects Step 4F and the Business Rules in the Writer PRD. The `inline_link_placed` field in the Writer's `citation_usage` output block should be deprecated in Writer v1.4 or repurposed to track marker placement.

### 4C — Body Field Format Declaration (Writer v1.4)

The Writer Module v1.4 PRD should explicitly declare its `article[].body` field format as Markdown (specify exact flavor — e.g., GitHub Flavored Markdown / CommonMark) and document that body strings may contain `{{citation_id}}` markers as plain text inline tokens. This locks down the format contract for all downstream consumers.

---

## 5. Inputs

The Sources Cited Module receives two upstream JSON payloads on each run. Both are required. If either is missing or fails schema validation, the module aborts with a structured error.

### Input A — Content Writer Module Output (v1.4+ schema)

The full JSON output from the Content Writer Module. Key fields consumed:

| Field | Usage |
|---|---|
| `keyword` | Cross-validated against Research Module `keyword` |
| `article[]` | Ordered array of article sections; body fields are scanned for `{{citation_id}}` markers |
| `article[].body` | Markdown prose containing `{{citation_id}}` markers at point of citation use |
| `article[].citations_referenced[]` | Array of `citation_id` values used in this section — used to validate all markers are accounted for |
| `article[].order` | Section order index — used to establish first-appearance sequence for citation numbering |
| `article[].type` | Section type — Sources Cited section is appended after the `conclusion` type |
| `citation_usage.usage[]` | Per-citation `used` flag — determines which citations are included in Sources Cited |
| `citation_usage.usage[].citation_id` | Used to resolve which citations from the Research pool appear in Sources Cited |
| `metadata.schema_version` | Validated against expected Writer schema version (1.4+) |

### Input B — Research & Citations Module Output (v1.1+ schema)

The full JSON output from the Research & Citations Module. Key fields consumed:

| Field | Usage |
|---|---|
| `keyword` | Cross-validated against Writer Module `keyword` |
| `citations[]` | Full citation pool — resolved by `citation_id` to retrieve publication metadata for MLA formatting |
| `citations[].citation_id` | Lookup key — matched against markers found in prose; must conform to `^cit_[0-9]+$` |
| `citations[].url` | External URL — rendered with `rel="nofollow"` in Sources Cited |
| `citations[].title` | Source title — used in MLA entry |
| `citations[].publication` | Publication or site name — used in MLA entry |
| `citations[].tier` | Recorded in output metadata; not used in formatting |

Note: `citations[].author` and `citations[].published_date` are **not consumed** in v1. See Section 7 Step 3 rationale.

### Input Cross-Validation

| Check | Failure Behavior |
|---|---|
| `writer.keyword == research.keyword` (case-insensitive) | Abort with structured error if mismatch |
| Writer schema version is 1.4+ | Abort if schema version is below 1.4 — marker output is not present in earlier versions |
| Any `{{citation_id}}` marker found in prose that has no matching entry in `research.citations[]` | Abort with structured error listing unresolvable markers |
| Any `{{citation_id}}` marker found in prose where the `citation_id` does not appear in `citation_usage.usage[]` | Abort with structured error — see Step 1 integrity check rationale |
| Any `citation_id` value encountered that does not match `^cit_[0-9]+$` | Abort with structured error |
| Any `citation_id` in `citation_usage.usage[]` where `used: true` has no corresponding marker in any `article[].body` | Flag `orphaned_usage_record: true` in metadata; do not include in Sources Cited |
| `article[].citations_referenced[]` lists a `citation_id` with no corresponding marker in that section's body | Flag `marker_reconciliation_warning: true` per section; proceed |

---

## 6. System Architecture Overview

```
[Writer JSON (v1.4+)] + [Research & Citations JSON]
              │
              ▼
┌─────────────────────┐
│  Step 0: Input      │  ◄── Schema validation, keyword match, marker
│  Validation         │      resolvability check, ID format check
└─────────────────────┘
              │
              ▼
┌─────────────────────┐
│  Step 1: Marker     │  ◄── Scan all article[].body fields
│  Discovery &        │  ◄── Extract all {{citation_id}} markers in
│  Numbering          │      order of first appearance
└─────────────────────┘
              │
              ▼
┌─────────────────────┐
│  Step 2: Superscript│  ◄── Replace each marker with HTML superscript
│  Injection          │  ◄── Sort stacked markers ascending
│                     │  ◄── Anchor href → Sources Cited entry
└─────────────────────┘
              │
              ▼
┌─────────────────────┐
│  Step 3: MLA        │  ◄── Resolve citation metadata from Research pool
│  Entry Generation   │  ◄── Format each used citation (title + publication + URL)
│                     │  ◄── Apply rel="nofollow" to all URLs
└─────────────────────┘
              │
              ▼
┌─────────────────────┐
│  Step 4: Sources    │  ◄── Build numbered list ordered by citation number
│  Cited Section      │  ◄── Append as final article section (after conclusion)
│  Assembly           │
└─────────────────────┘
              │
              ▼
┌─────────────────────┐
│  Step 5: Output     │  ◄── Assemble enriched JSON
│  Assembly           │  ◄── Preserve full Writer schema
│                     │  ◄── Add sources_cited_metadata block
└─────────────────────┘
              │
              ▼
[Enriched JSON Article → Content Editor Module]
```

---

## 7. Functional Requirements

### Step 0 — Input Validation

All validation runs before any processing begins.

| Rule | Action |
|---|---|
| Either input JSON is missing | Abort with structured error |
| Either input fails schema validation | Abort with structured error |
| `writer.keyword != research.keyword` (case-insensitive) | Abort with structured error |
| Writer schema version below 1.4 | Abort — inline markers not present in earlier versions |
| A `{{citation_id}}` marker in prose has no match in `research.citations[]` | Abort with structured error listing all unresolvable marker values |
| A `{{citation_id}}` marker in prose has a `citation_id` not present in `citation_usage.usage[]` | Abort with structured error — integrity violation between Writer prose and Writer reconciliation record (see Step 1) |
| Any encountered `citation_id` does not match `^cit_[0-9]+$` | Abort with structured error |
| `article[]` is empty | Abort with structured error |

---

### Step 1 — Marker Discovery & Citation Numbering

The module performs a single sequential scan of all `article[].body` fields, in ascending `order` index, to discover all `{{citation_id}}` markers and assign citation numbers.

**Scanning rules:**
- Scan body fields only — heading fields (`article[].heading`) are not scanned for markers and must not contain markers
- Process sections in `order` ascending (matching the article's reading sequence)
- Within a body field, process markers left-to-right as they appear in the text
- Marker pattern: `\{\{(cit_[0-9]+)\}\}` — the captured group is the `citation_id`

**Numbering algorithm:**
- Maintain a `citation_number_map`: a dictionary keyed by `citation_id`, assigned a sequential integer starting at 1
- When a `citation_id` is encountered for the first time: assign the next available number and add to the map
- When a `citation_id` is encountered again in a later section: reuse the existing number — no new entry is created
- Final numbering reflects strict first-appearance order across the full article

**Output of Step 1:**
- `citation_number_map`: `{ "cit_003": 1, "cit_007": 2, "cit_001": 3, ... }`
- `ordered_used_citations`: list of `citation_id` values in citation number order (used for Sources Cited section assembly in Step 4)

**Integrity check (replaces "prose is ground truth" rule from v1.0):**

The Writer Module's marker placement is deterministic post-processing (Python/JS string assembly from a known `citation_id` list), not an LLM operation — hallucinated marker IDs are not the expected risk. However, schema drift, copy-paste errors, or upstream bugs could produce inconsistent state where prose markers and the `citation_usage` reconciliation record disagree.

To catch these defensively:

- Every `citation_id` extracted from prose markers **must** appear in `citation_usage.usage[]`. If not: abort the run with a structured error (see Step 0). This ensures the Writer's prose output and its own reconciliation record are internally consistent before this module proceeds.
- Every `citation_id` in `citation_usage.usage[]` where `used: true` must have at least one corresponding marker found in the scan. If not: flag `orphaned_usage_record: true` in metadata and exclude that citation from Sources Cited (no abort — this is a softer inconsistency that does not corrupt output).

The `unexpected_marker` flag and "prose is ground truth" handling from v1.0 are removed.

---

### Step 2 — Superscript Injection

Each `{{citation_id}}` marker in every `article[].body` field is replaced with an HTML superscript element.

**Substitution format:**

```html
<sup><a href="#sources-cited-{n}" id="ref-{citation_id}-{instance}">[{n}]</a></sup>
```

Where:
- `{n}` = the citation number from `citation_number_map`
- `#sources-cited-{n}` = the anchor ID of the corresponding Sources Cited list entry (see Step 4)
- `{citation_id}` = the raw citation ID (e.g., `cit_003`)
- `{instance}` = an integer representing the nth occurrence of this citation in the article (1-indexed), to give each superscript a unique `id` for back-references if needed (e.g., `ref-cit_003-1`, `ref-cit_003-2`)

**Stacked marker sort rule:**

When two or more markers appear consecutively (with no intervening prose between them), the rendered superscripts must be sorted in **ascending citation number order** — not source-text order.

This produces clean numeric runs like `[3][5]` rather than `[5][3]`, regardless of the order the markers were placed in the source. This matters because citation numbers are assigned by first-appearance across the full article, so a marker pair placed `{{cit_001}}{{cit_004}}` in the source could legitimately render as `[5][3]` if `cit_004` happened to appear earlier in the article. Sorting ascending eliminates that visual oddity.

Sort scope is per stacked group only. Markers separated by any prose character (including whitespace) are not part of the same stack and are not reordered relative to each other.

**Example — single marker:**

Input body text:
```
Water heaters typically last 8–12 years before requiring replacement.{{cit_003}}
```

Output body text:
```
Water heaters typically last 8–12 years before requiring replacement.<sup><a href="#sources-cited-1" id="ref-cit_003-1">[1]</a></sup>
```

**Example — stacked markers (multiple citations on one sentence), assuming `cit_001` was assigned number 5 and `cit_004` was assigned number 3:**

Input:
```
Installation costs vary by region and unit type.{{cit_001}}{{cit_004}}
```

Output (sorted ascending — `[3]` rendered before `[5]`):
```
Installation costs vary by region and unit type.<sup><a href="#sources-cited-3" id="ref-cit_004-1">[3]</a></sup><sup><a href="#sources-cited-5" id="ref-cit_001-1">[5]</a></sup>
```

**Rules:**
- Markers are replaced in-place; no surrounding whitespace is added or removed
- Within a stacked group, source-order is overridden by ascending citation-number order
- No other changes are made to the body text — word choice, punctuation, capitalization, and structure are preserved exactly
- Heading fields (`article[].heading`) are passed through unchanged; markers in heading fields cause an abort (Step 0)

---

### Step 3 — Citation Entry Generation

For each citation in `ordered_used_citations`, generate a formatted entry. v1 uses a simplified MLA-derived format that omits author and publication date entirely.

**v1 format (applied to all entries):**

```
"Title of Page." Publication Name, <a href="URL" rel="nofollow">URL</a>.
```

**Rationale for omitting author and date in v1:**

Strict MLA 9th edition requires author name inversion (`Last, First`) and publication date formatting. Both fields require parsing logic that is fragile against real-world input:

- Author strings arrive in inconsistent formats (already-inverted, organizational, multi-author, with credentials, multi-word last names) and the Research Module does not constrain the format. A naive inverter will silently produce malformed entries (e.g., re-inverting `"Smith, John"` to `"John, Smith"`).
- Publication date strings arrive in unpredictable formats (ISO 8601, partial dates, scraped natural language like "March 15, 2023" or "2 days ago") and the Research Module's schema only declares `published_date: "string | null"` with no format guarantee.

Rather than ship fragile parsing logic in v1 that produces silently incorrect entries, both fields are dropped entirely. Citation entries remain useful (title, publication, URL are sufficient for reader verification) and consistent. Author and date support is deferred to v2, contingent on either (a) upstream format guarantees from the Research Module, or (b) implementation of robust parsers with documented fallback behavior.

**Field resolution rules:**

| Element | Source Field | Fallback |
|---|---|---|
| Title | `citations[].title` | Required — placeholder entry if absent (see Failure Modes) |
| Publication name | `citations[].publication` | If absent: use root domain of `citations[].url` |
| URL | `citations[].url` | Required — placeholder entry if absent (see Failure Modes); rendered with `rel="nofollow"` |

**Title formatting:**
- Web page titles are rendered in quotation marks: `"Title of Page."`
- The period is placed inside the closing quotation mark (standard MLA)

**Publication name formatting:**
- Rendered in italics. In the HTML list body output (Step 4), publication names are wrapped in `<em>` tags.

**URL rendering:**
- The URL is both the hyperlink text and the href: `<a href="https://example.com/page" rel="nofollow">https://example.com/page</a>`
- The trailing period follows the closing `</a>` tag

**Full example:**
```html
"How to Replace a Water Heater Anode Rod." <em>This Old House</em>, <a href="https://www.thisoldhouse.com/plumbing/anode-rod" rel="nofollow">https://www.thisoldhouse.com/plumbing/anode-rod</a>.
```

**Publication-as-domain example (publication field absent):**
```html
"Water Heater Energy Efficiency Standards." <em>energy.gov</em>, <a href="https://www.energy.gov/energysaver/water-heaters" rel="nofollow">https://www.energy.gov/energysaver/water-heaters</a>.
```

**LLM usage:** Citation entry generation is fully deterministic — no LLM call is required or used. All formatting is handled by template logic from structured citation metadata.

---

### Step 4 — Sources Cited Section Assembly

The Sources Cited section is built as a numbered list, ordered by citation number (ascending), and appended to the article as the final section.

**Section structure:**

The Sources Cited section is represented as two entries appended to `article[]`:

1. **Header entry** (`type: "sources-cited-header"`, `level: "H2"`, `heading: "Sources Cited"`)
2. **Body entry** (`type: "sources-cited-body"`, `level: "none"`) — contains the full numbered list as an HTML ordered list

**HTML list format:**

```html
<ol class="sources-cited">
  <li id="sources-cited-1">"How to Replace a Water Heater Anode Rod." <em>This Old House</em>, <a href="https://www.thisoldhouse.com/plumbing/anode-rod" rel="nofollow">https://www.thisoldhouse.com/plumbing/anode-rod</a>.</li>
  <li id="sources-cited-2">...</li>
</ol>
```

**Anchor ID convention:** Each `<li>` carries `id="sources-cited-{n}"`, where `{n}` is the citation number. This is the target of the superscript jumplinks injected in Step 2.

**Order:** Entries appear in citation number order (order of first appearance in article prose). This is the `ordered_used_citations` list from Step 1.

**Section ordering:** The Sources Cited header is assigned `order: <conclusion_order + 1>`; the body entry is assigned `order: <conclusion_order + 2>`, where `conclusion_order` is the `order` value of the existing conclusion section in the Writer's article array. These are appended after the conclusion section.

---

### Step 5 — Output Assembly

The output is the full Content Writer Module JSON schema passed through intact, with the following modifications:

1. All `article[].body` fields have had `{{citation_id}}` markers replaced with superscript HTML (Step 2)
2. Two new entries appended to `article[]`: the Sources Cited header and body (Step 4)
3. A new top-level `sources_cited_metadata` block added (see Output Schema)
4. `metadata.schema_version` updated to reflect Sources Cited Module processing

No other fields from the Writer Module output are modified or removed.

**Output format contract — downstream consumers must preserve:**

The output `article[].body` fields are **Markdown with embedded HTML**. Downstream consumers (Content Editor Module and any subsequent renderers) must preserve the following without stripping or modification:

| Element | Reason |
|---|---|
| `<sup>` tags | Citation superscript display |
| `<a>` tags | Citation jumplinks and external citation links |
| `<ol>` and `<li>` tags | Sources Cited list structure |
| `<em>` tags | Publication name italics |
| `id` attributes on `<a>` and `<li>` | Required for jumplink targeting |
| `href` attributes on `<a>` | Required for both internal jumplinks (`#sources-cited-N`) and external citation URLs |
| `rel="nofollow"` attribute on external `<a>` tags | SEO requirement — must not be stripped |
| `class="sources-cited"` on `<ol>` | Used for downstream styling and identification |

Any HTML sanitizer in the downstream pipeline must be configured to allow these tags and attributes. Markdown renderers must be configured to permit raw HTML pass-through (GitHub Flavored Markdown and CommonMark do this by default). End-to-end rendering testing is required before this module ships — see Section 13.

---

## 8. Output Schema

The output schema extends the Content Writer Module v1.4 output schema. Only additions and modifications are documented here — all existing Writer fields pass through unchanged.

```json
{
  "keyword": "string",
  "intent_type": "string",
  "title": "string",

  "article": [
    {
      "order": 0,
      "level": "H1 | H2 | H3 | none",
      "type": "content | faq-header | faq-question | conclusion | sources-cited-header | sources-cited-body | h1-enrichment",
      "heading": "string | null",
      "body": "string ({{citation_id}} markers replaced with superscript HTML)",
      "word_count": 0,
      "section_budget": 0,
      "citations_referenced": ["cit_001"]
    },
    {
      "order": "<conclusion_order + 1>",
      "level": "H2",
      "type": "sources-cited-header",
      "heading": "Sources Cited",
      "body": null,
      "word_count": null,
      "section_budget": null,
      "citations_referenced": []
    },
    {
      "order": "<conclusion_order + 2>",
      "level": "none",
      "type": "sources-cited-body",
      "heading": null,
      "body": "<ol class=\"sources-cited\">...</ol>",
      "word_count": null,
      "section_budget": null,
      "citations_referenced": []
    }
  ],

  "citation_usage": {
    "...": "passed through from Writer output unchanged"
  },

  "sources_cited_metadata": {
    "total_citations_in_sources_cited": 0,
    "citation_number_map": {
      "cit_003": 1,
      "cit_007": 2,
      "cit_001": 3
    },
    "orphaned_usage_records": [],
    "marker_reconciliation_warnings": [],
    "entries_with_missing_publication": ["cit_007"],
    "entries_with_placeholder": [],
    "schema_version": "1.0",
    "writer_schema_version": "1.4",
    "generation_time_ms": 0
  },

  "format_compliance": {
    "...": "passed through from Writer output unchanged"
  },

  "metadata": {
    "...": "all existing Writer metadata fields passed through unchanged",
    "sources_cited_module_version": "1.0"
  }
}
```

---

## 9. Failure Mode Handling

| Scenario | Behavior |
|---|---|
| Either input JSON missing or fails schema validation | Abort with structured error |
| Writer schema version below 1.4 | Abort — markers not present; instruct caller to upgrade Writer Module |
| `writer.keyword != research.keyword` | Abort with structured error |
| Unresolvable `{{citation_id}}` marker (no match in `research.citations[]`) | Abort with structured error listing all unresolvable IDs |
| `{{citation_id}}` marker in prose with `citation_id` not present in `citation_usage.usage[]` | Abort with structured error — Writer integrity violation |
| `citation_id` value does not match `^cit_[0-9]+$` | Abort with structured error |
| Marker found in a heading field (`article[].heading`) | Abort — headings must not contain citation markers |
| Citation in `citation_usage.usage[]` where `used: true` but no marker found in prose | Flag `orphaned_usage_record: true`; exclude from Sources Cited; do not abort |
| `citations[].title` absent for a used citation | Generate placeholder entry: `[Citation data unavailable — manual review required]`; flag in `entries_with_placeholder`; do not abort |
| `citations[].url` absent for a used citation | Same as missing title — placeholder entry, flagged |
| `citations[].publication` absent | Use root domain of `citations[].url` as publication; flag in `entries_with_missing_publication`; do not abort |
| `article[]` is empty | Abort with structured error |
| End-to-end generation exceeds 15s | Abort with structured timeout error |

---

## 10. Performance Targets

This module performs no LLM calls. All processing is deterministic template logic and string operations.

| Stage | Target | Max |
|---|---|---|
| End-to-end | 3s | 15s |
| Input validation | <1s | 2s |
| Marker discovery & numbering (full article scan) | <1s | 2s |
| Superscript injection (all body fields) | <1s | 2s |
| Citation entry generation (per citation, in-memory) | <1s | 2s |
| Sources Cited assembly & output packaging | <1s | 2s |

Performance is bounded by article length and citation count, not by external API calls. Articles with 20+ citations and 3,000+ word bodies are expected to complete well within the 3s target.

---

## 11. Cost Model

| Component | Cost per Article |
|---|---|
| LLM calls | $0.00 — none required |
| External API calls | $0.00 — none required |
| Compute (string processing, template rendering) | Negligible |
| **Estimated total per article** | **~$0.00** |
| **Budget ceiling** | **$0.05** |

This module adds no meaningful marginal cost to the pipeline. The per-article budget ceiling of $0.05 is a safety buffer for infrastructure overhead only.

**Combined pipeline cost (all modules):**
Adding this module does not change the previously documented combined estimate of **$0.63–$1.24** per article.

---

## 12. Business Rules Summary

| Rule | Value |
|---|---|
| Locale | English / United States |
| Citation style | MLA-derived simplified format (title + publication + URL only); author and date omitted in v1 |
| Citations included in Sources Cited | `used: true` citations only (from Writer `citation_usage`) — orphaned records excluded |
| Ground truth for citation inclusion | Writer `citation_usage` record; markers in prose must be consistent with the record (mismatches abort) |
| Citation ID format constraint | `^cit_[0-9]+$` — enforced; non-conforming IDs abort the run |
| Citation numbering | Sequential integers starting at 1, by order of first appearance in article prose |
| Repeated citation in multiple sections | Same citation number reused; appears once in Sources Cited |
| Superscript format | `<sup><a href="#sources-cited-{n}">[{n}]</a></sup>` |
| Stacked citations (multiple on one sentence) | Rendered superscripts sorted ascending by citation number, regardless of source-text marker order |
| Sources Cited section heading | "Sources Cited" (exact text, H2 level) |
| Sources Cited section position | After conclusion; final section in article |
| External URL link attribute | `rel="nofollow"` on all URLs in Sources Cited |
| Inline hyperlinks in prose | None — superscript numbers only |
| Heading fields | Must not contain markers; markers in headings cause abort |
| Prose content modification | None — only marker substitution; no word changes |
| Author in citation entries | Omitted in v1 |
| Publication date in citation entries | Omitted in v1 |
| Missing publication in citation metadata | Substitute root domain of URL; flag |
| Missing title or URL | Placeholder entry; flag; do not abort full run |
| Output body field format | Markdown with embedded HTML |
| LLM calls | None |
| Schema version required (Writer) | 1.4+ |

---

## 13. What This PRD Does Not Cover

To be addressed in the engineering implementation spec:

- HTML sanitization rules and configuration for the Content Editor Module and any downstream renderer to ensure required tags/attributes (see Step 5) are preserved
- End-to-end rendering pipeline testing — before this module ships, render a sample article through the full pipeline to the final published HTML and verify: jumplinks function, `rel="nofollow"` survives to final HTML, superscripts display correctly, and `id` attributes are preserved
- Markdown renderer configuration — confirm the chosen renderer (likely GitHub Flavored Markdown / CommonMark) permits raw HTML pass-through and does not strip the required tags/attributes
- Handling of malformed markers (e.g., `{{cit_001}` — mismatched braces, partial matches) — current marker regex `\{\{(cit_[0-9]+)\}\}` will not match these; engineering should decide whether to silently leave them as literal text or abort
- Output storage schema in Supabase
- Authentication and API key management
- Logging and observability (marker counts, field coverage rates, generation timing)
- Schema versioning compatibility with future Writer and Research Module schema versions
- Content Editor Module input schema requirements — may require further output format adjustments
- Back-reference links from Sources Cited entries pointing back to each superscript in prose (bidirectional jumplinks) — deferred to v2
- Author and publication date support in citation entries — deferred to v2 pending upstream format guarantees or robust parser implementation

---

## 14. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-04-29 | Initial draft |
| 1.1 | 2026-04-30 | Inverted marker integrity rule — Writer `citation_usage` record is now authoritative; markers in prose without matching `usage` records abort the run (was: "prose is ground truth"). Stacked superscripts now sort ascending by citation number. Replaced hardcoded `99`/`100` order values with `<conclusion_order + 1>` and `<conclusion_order + 2>`. Removed author and publication date from citation entries entirely (deferred to v2 pending upstream format guarantees) — eliminates fragile parsing of inconsistent author/date formats. Added `^cit_[0-9]+$` format constraint on `citation_id` and explicit marker regex. Added Section 5 output format contract listing required HTML tags/attributes downstream consumers must preserve. Added Writer v1.4 PRD task (Section 4C) to declare body field format. Removed unmeasurable "MLA structural validation ≥95%" success metric. |


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/content-quality-prd-v1_0.md -->
<!-- ============================================================ -->

# PRD: Content Quality Requirements

**Version:** 1.0 (Draft)
**Status:** Draft — Ready for Implementation
**Last Updated:** 2026-05-01
**Audience:** Engineering team
**Modules in Scope:**
- Content Brief Generator (v1.7 → v1.8)
- Content Writer Module (v1.5 → v1.6)
- Platform layer (per-client context flow)

---

## 1. Background

This PRD encodes content-quality requirements identified during a production-quality audit of a generated article on the keyword `tiktok shop` (run dated 2026-05-01). The audit surfaced concrete failure modes that must not recur:

| Failure | Symptom in audited run |
|---|---|
| Heading-set redundancy | 9 H2s all paraphrased the same definitional question ("What is TikTok Shop", "What exactly is TikTok Shop", "Explained: What is TikTok Shop", etc.) |
| SERP-artifact leakage | Headings included subreddit suffixes (`: r/TikTokshop`), ellipsis (`How's it Different ...`), and pipe-separated site names (`TikTok Shop \| Discover the Future of Social Commerce`) |
| Topic drift | Two H2s on tangential topics (US-ban data implications, internal algorithm mechanics) padded a piece whose title promised a definition |
| Missing structural elements | No Key Takeaways block at top, no opening Agree / Promise / Preview construction, no closing CTA |
| Brand context absent | Article had zero brand mentions and no audience framing despite a configured client |
| Paragraph length | Several paragraphs ran past four sentences |
| Citation thinness | Multiple factual / time-bound claims with no external citation |

Every requirement below maps to one or more of the failures above. This PRD is the source of truth for the *what*; the module PRDs (Brief v1.8, Writer v1.6) carry the *where and how*.

---

## 2. Requirements

### R1 — Semantic Heading Deduplication

**What:** H2s that paraphrase the same question or assert the same definition must collapse to a single section in the final outline.

**Why:** The Brief Generator's Levenshtein-based dedup (ratio ≤ 0.15) catches lexical near-duplicates but misses semantic ones. Eight to ten "What is X?" rephrasings will all survive that filter and then sweep the priority-ranked H2 selection because semantic similarity to the keyword is 40% of the priority score.

**Acceptance criteria:**
- After the Brief Generator's heading-selection step, no two surviving H2s may have a cosine similarity ≥ **0.85** to each other (using the same `text-embedding-3-small` vectors already computed in Step 5).
- Selection must apply Maximum Marginal Relevance (MMR) ranking: each candidate H2 is scored as `λ·heading_priority − (1−λ)·max_cosine_to_already_selected_H2s`. Default `λ = 0.6` (favors topical diversity over raw priority).
- When two candidates exceed the 0.85 threshold, retain the one with the higher `heading_priority`; the loser is moved to `discarded_headings` with `discard_reason: "semantic_duplicate_of_higher_priority_h2"` and a back-reference field `semantic_duplicate_of: <order>`.
- A run that begins with ≥ 6 candidates whose pairwise similarity to the seed keyword is ≥ 0.90 (i.e., a definitional keyword like "what is X") must produce **at most one** H2 of the form "What is X / What does X mean / Define X / Explain X". Additional definitional rephrasings are discarded with `discard_reason: "definitional_restatement"`.
- The `metadata` block of the brief output reports `semantic_dedup_collapses_count` and `definitional_restatements_discarded_count`.

**Owning module:** Content Brief Generator (Steps 4, 5, 8). See Brief PRD §5 for placement.

---

### R2 — SERP Heading Sanitization

**What:** Headings ingested from SERP scraping, autocomplete, keyword suggestions, and LLM responses must be sanitized of artifacts before scoring or selection.

**Why:** Raw SERP H2s frequently carry boilerplate that pollutes the final article — subreddit suffixes, source-name pipes, trailing ellipsis, "Read more" suffixes. The current pipeline strips a small fixed list of boilerplate phrases ("Contact Us", "About the Author", "Related Posts") but does not normalize these patterns.

**Acceptance criteria:** All of the following sanitization rules are applied to **every heading candidate** at the start of Step 4 (Subtopic Aggregation), before normalization, dedup, embedding, scoring, or polish:

| # | Pattern | Action |
|---|---|---|
| S1 | Trailing `: r/<subreddit>` (e.g., `: r/TikTokshop`) | Strip suffix |
| S2 | Trailing `…` or three or more consecutive periods (`...`, `....`) | Strip suffix |
| S3 | Trailing `\| <site name>` or `– <site name>` or `— <site name>` (em/en dash) where the trailing segment matches a domain root in the SERP item's URL or is < 30 characters and contains at most one CapitalizedWord run | Strip suffix |
| S4 | Leading `<site name>: ` (same matching rule as S3) | Strip prefix |
| S5 | Trailing `\| Read More`, `\| Continue Reading`, `Read More …`, `Continue Reading …` | Strip suffix |
| S6 | Wrapping HTML tags or entities (`<strong>`, `&amp;`, `&#8217;`) | Decode entities; strip tags |
| S7 | Multiple internal whitespace runs (e.g., `What  is  X`) | Collapse to single spaces |
| S8 | Trailing punctuation runs (`?!`, `?.`, `..`) other than a single terminal `?` or `.` | Reduce to single terminal mark |
| S9 | Headings shorter than 3 words after sanitization | Discard with `discard_reason: "too_short_after_sanitization"` |
| S10 | Headings whose sanitized form is a single proper-noun brand name with no verb or noun phrase (e.g., `TikTok Shop` alone, `Salesforce`) | Discard with `discard_reason: "non_descriptive_after_sanitization"` |

- Sanitization is applied **before** Levenshtein dedup so near-duplicates that previously differed only by their suffixes now collapse correctly.
- Sanitization is **also applied** to the `original_text` saved on the candidate, but the pre-sanitization raw text is preserved on the candidate object as `raw_text` so the brief output's `discarded_headings[].original_source` can show what was scraped.
- The polish-pass LLM (Step 5) receives sanitized text only; it must not be asked to clean SERP artifacts because that responsibility now belongs to the deterministic sanitization step.

**Owning module:** Content Brief Generator (Step 1 boilerplate strip extended; Step 4 pre-aggregation sanitization). See Brief PRD §5 for placement.

---

### R3 — Topic Adherence and Spin-Off Routing

**What:** Sections whose topic does not directly serve the article's title promise must be excluded from the parent piece. Off-topic but related content must be routed into a separate `spin_off_articles` output for future pieces, never padded into the parent piece.

**Why:** The audited run included "What happens to your purchase data … if TikTok faces a US ban" and "How TikTok Shop's algorithm decides which products get shown" in a piece whose title promised a definition. Both topics are interesting follow-ups; neither serves the parent piece's reader intent.

**Acceptance criteria:**

| Criterion | Detail |
|---|---|
| Title-promise embedding | After Step 1 (Title Generation) in the Writer Module, the title is embedded with `text-embedding-3-small`. Each H2 candidate's `topic_adherence_score` is the cosine similarity between its embedding (computed earlier in the brief) and the title embedding. |
| Adherence threshold | An H2 with `topic_adherence_score < 0.62` is removed from the writer's section-writing queue, regardless of its `heading_priority` from the brief. The H2 is logged in writer metadata as `dropped_for_low_topic_adherence` with the score. |
| Authority gap H3 exemption | Authority gap H3s (`source: "authority_gap_sme"`) bypass this check — they are by design tangential and exist to add expert depth, but they remain attached to a parent H2 that itself passed the adherence check. |
| Spin-off routing | Any H2 dropped for low topic adherence, plus any heading already in `discarded_headings` with `discard_reason` ∈ {`global_cap_exceeded`, `below_priority_threshold`, `definitional_restatement`}, is candidates for spin-off. The Brief Generator's existing Step 9 (silo identification) is renamed and re-purposed to populate `spin_off_articles[]` (see R3 schema below). |
| Reader-intent alignment | The Writer Module's per-H2 system prompt receives the title verbatim and a one-sentence framing of who the piece is for (drawn from `client_context.icp_text`). H2 sections that do not serve that intent in their first sentence trigger a one-shot retry with a stricter prompt; on second failure the section is dropped and logged. |

**Schema addition (Brief output):**
```json
"spin_off_articles": [
  {
    "suggested_keyword": "how tiktok shop's algorithm ranks products",
    "source_heading_text": "How TikTok Shop's algorithm decides which products get shown to which buyers",
    "source_reason": "low_topic_adherence | semantic_duplicate | global_cap_exceeded | below_priority_threshold",
    "topic_adherence_score": 0.41,
    "recommended_intent": "informational",
    "supporting_headings": ["string"]
  }
]
```

The legacy `silo_candidates[]` field is retained for one release with identical content as `spin_off_articles[]` for backward compatibility, then removed in v1.9 of the brief.

**Owning modules:** Brief Generator (spin-off routing in Step 9), Writer Module (topic-adherence enforcement after Step 1). See Brief PRD §5 and Writer PRD §6.

---

### R4 — Required Structural Elements

**What:** Every generated article must include all three of the following structural elements. Absence of any element is a hard failure of the writer module.

| Element | Required Position | Required Content |
|---|---|---|
| **Key Takeaways** | Immediately after H1 enrichment, before the first content H2 | A bulleted list of 3–5 standalone sentences, each ≤ 25 words, that summarize the article's most extractable claims. Optimized for AEO snippet capture. |
| **Agree / Promise / Preview intro** | The intro paragraph(s) directly following the Key Takeaways block, before the first H2 | Three discrete prose blocks: (a) **Agree** — a sentence acknowledging the reader's situation or question; (b) **Promise** — a sentence stating what the article will deliver; (c) **Preview** — a sentence enumerating 2–4 sub-topics covered. Each block is ≤ 50 words. |
| **CTA** | Final sentence of the conclusion section | A clear next-step call-to-action sentence that names a specific action a reader can take, drawn from `client_context.icp_text` goals when available, or from a generic intent-appropriate template otherwise. Never a hard sales pitch. |

**Acceptance criteria:**
- The writer's output schema gains three new fields under the article assembly: `key_takeaways: [string]`, `intro: { agree: string, promise: string, preview: string }`, and `cta: string`.
- The article assembly emits these as ordered sections in `article[]` so downstream renderers see a consistent structure:
  - `{order, level: "none", type: "key-takeaways", heading: "Key Takeaways", body: "<bulleted markdown>"}` — `heading` is rendered as H2 by the renderer.
  - `{order, level: "none", type: "intro", heading: null, body: "<APP prose, three paragraphs>"}` — three paragraphs separated by blank lines.
  - `{order, level: "none", type: "cta", heading: null, body: "<single CTA sentence>"}` — appended after the conclusion section.
- A run whose final article is missing any of the three sections aborts with structured error `missing_required_structure` and a `missing_elements: [...]` list. No partial output is returned.
- The Key Takeaways block is generated **after** all content sections and the conclusion are written (so it summarizes actual content, not the outline). It is a single LLM call that takes the full article body as input.
- Renderer responsibilities (frontend `sectionsToMarkdown`): the `type: "key-takeaways"` section heading is rendered as `## Key Takeaways`; the `type: "intro"` body is inserted between H1 and the first H2 with no heading prefix; the `type: "cta"` body is appended as the article's last paragraph with no heading prefix.

**Owning module:** Content Writer Module. See Writer PRD §6 (new Step 1.5, modified Step 2, modified Step 6, new Step 6.5).

---

### R5 — Brand Context Injection

**What:** Per-client brand and ICP context must reach every generation prompt across the full pipeline (Brief Generator topic adherence prompt, Writer Module section/FAQ/intro/conclusion prompts). Brand mentions in the final article are budgeted, not unlimited; missing brand mentions on brand-aligned topics are flagged for review, not auto-rejected.

**Why:** The platform already snapshots `client_context` per run, but only the Writer Module currently consumes it (per v1.5 spec). The Brief Generator runs blind to client identity, which lets it produce headings that drift entirely off-brand. The audited run had zero brand mentions in the final article despite the configured client having an explicit ICP and brand voice.

**Acceptance criteria:**

| Criterion | Detail |
|---|---|
| Canonical ICP source | The platform's per-client `client_context_snapshots.icp_text` is the source of truth at run time. A reusable agency-wide default ICP guide may be loaded from `/config/ubiquitous_icp_guide.json` (or an env-pointed path) and merged with per-client `icp_text` at snapshot creation; per-client always takes precedence on conflicts. The exact path is to be confirmed in the engineering spec; until then, a per-client `icp_text` is sufficient. |
| Brief Generator receives client context | The Brief Generator's input gains an optional `client_context` field (same schema as the Writer's `client_context`). When present, the topic-adherence enforcement (R3) uses ICP audience framing in its title-vs-section relevance check. Headings that score in the bottom 25% on adherence and **also** semantically clash with the ICP audience description (cosine ≤ 0.45 to the audience summary embedding) are downgraded by 0.10 in `heading_priority` before MMR selection. |
| Writer prompts already covered | Writer v1.5 already injects `client_context` into Steps 4, 5, 6. v1.6 extends this to the new Key Takeaways and CTA generation steps (R4). |
| Brand mention budget | The final article must contain **2–3** brand-name mentions where the brand is named in the client's `brand_voice_card.client_services` or recognized as the client's own brand from `brand_guide_text` heading text. Mention count is enforced post-hoc: |
| | – If count is 0 and the topic is *brand-aligned* (defined: title cosine ≥ 0.55 to the brand voice card's `client_services` joined string), flag `zero_brand_mentions_on_brand_aligned_topic` in writer metadata. **Do not auto-reject.** |
| | – If count is 0 and the topic is *not* brand-aligned (cosine < 0.55), no flag. Writing brand-agnostic top-of-funnel content with zero mentions is intentional. |
| | – If count is 1, no action. |
| | – If count is 4–5, log warning `brand_mentions_exceed_target` but do not reject. |
| | – If count is ≥ 6, retry the highest-mention section once with a stricter prompt that lists the limit; on second failure, log `brand_mentions_exceed_hard_cap` and accept the output (do not block publishing). |
| Brand-aligned vs. brand-agnostic flag | Writer metadata gains `topic_brand_alignment: "brand_aligned" \| "brand_agnostic"` based on the cosine threshold above. |

**Owning modules:** Platform layer (snapshot + global ICP merge), Brief Generator (consume `client_context` for adherence check), Writer Module (extend existing v1.5 client-context flow to new steps + brand-mention budget).

---

### R6 — Paragraph Length Cap

**What:** Hard cap of 4 sentences per paragraph in any generated content section, FAQ answer, intro block, conclusion, or CTA. Three sentences or fewer is the preferred shape.

**Why:** Long paragraphs reduce readability, hurt mobile rendering, and lower extractability for LLM citation surfaces. The audited run had paragraphs running 5–7 sentences in multiple sections.

**Acceptance criteria:**
- After all content generation completes (and before banned-term scanning, which already runs as a post-hoc pass), the Writer performs a **paragraph length validation** pass:
  - Split each `body` field on blank lines (markdown paragraph boundaries).
  - For each paragraph, count sentence-terminal punctuation (`.`, `?`, `!`) outside markdown link/code spans. A run of consecutive `.`s (e.g., inside `e.g.`, abbreviations, URLs) is collapsed first using a small abbreviation dictionary (`e.g.`, `i.e.`, `etc.`, `Mr.`, `Dr.`, `vs.`, `Inc.`, `U.S.`, `U.K.`).
  - If any paragraph has > 4 sentences, mark the section for retry.
- Each over-budget section is retried **once** with a prompt addendum: `"Critical: every paragraph must contain at most 4 sentences. Three sentences or fewer is preferred. If a paragraph runs longer, split it on a logical break."` The retry replaces the section in the article.
- If the retry is also over budget, no further retry is attempted; the section is accepted but flagged in writer metadata `paragraph_length_violations: [{section_order: int, max_sentences: int}]`.
- The validation pass scans Key Takeaways bullets too: any single bullet > 25 words triggers a one-time retry of the Key Takeaways generation with a strict word limit reminder.
- Format-directive metadata gains `max_sentences_per_paragraph: 4` in the brief's `format_directives` so the section-writing prompts include the constraint **upstream** of the validation check (reducing retry frequency).

**Owning module:** Content Writer Module (post-generation validation, new Step 6.6). See Writer PRD §6.

---

### R7 — External Citations on Factual Claims

**What:** When the article makes time-bound, statistical, percentage, named-brand, or named-study claims, at least some of those claims must be backed by external citations. First-party sources are preferred over secondary aggregators.

**Why:** Articles without citations on factual claims are weaker for AEO (LLMs trust cited content more), weaker for SEO (E-E-A-T signals), and create legal exposure when claims are wrong. The audited run had multiple statistic-bearing sentences ("surpassed $100 million in U.S. sales within its first month") without citations on the section itself.

**Acceptance criteria:**

| Criterion | Detail |
|---|---|
| Claim detection | After section writing, the Writer runs a deterministic pass over each section body to count **citable claims**. A claim is detected when any of the following patterns match a sentence: |
| | (a) a numeral followed by `%`, `percent`, `pct`, or `percentage points` |
| | (b) a numeral with currency symbol or USD/EUR/GBP suffix (e.g., `$100M`, `€50`, `1.2 billion USD`) |
| | (c) a four-digit year between 1990 and 2099 used as a date (`in 2023`, `since 2024`) |
| | (d) `according to <ProperNoun>`, `<ProperNoun> reports`, `<ProperNoun> found`, `<ProperNoun> survey` |
| | (e) `studies show`, `research shows`, `data shows`, `analysts predict` |
| | (f) any sentence containing the name of a public figure, company, or product (resolved via the SIE entity list: `sie.terms.required[*].is_entity == true`) **and** a quantitative or temporal qualifier from (a)–(c) |
| Coverage threshold | At least **50%** of detected citable claims in a section must be followed by a `{{cit_id}}` marker (existing v1.4+ marker convention). The threshold is per-section, not per-article. |
| First-party preference | When the Research module produced multiple citation candidates for a claim, the Writer prefers citations whose `domain` matches the entity named in the claim sentence (e.g., a claim mentioning `Forbes` prefers a Forbes URL over a third-party summary of the same data). The Research module's `citations[]` already carries domain in v1.1 — this is a writer-side selection rule, not a research-side change. |
| Below-threshold remediation | A section that fails the 50% threshold triggers a one-shot retry with a stricter prompt that names the uncited claim sentences and asks the LLM to either (a) add a citation marker for that claim from the available citation pool, or (b) rewrite the sentence to remove the specific statistic / year / brand attribution if no citation supports it. |
| Failure logging | If the retry still fails the threshold, the section is accepted but flagged in writer metadata: `under_cited_sections: [{section_order: int, citable_claims: int, cited_claims: int}]`. |
| FAQ exemption | FAQ answers are exempt from the 50% threshold because they are intentionally generic-knowledge restatements; however, the same claim-detection pass runs on FAQ answers and any FAQ answer with a numeric statistic without a citation is **rewritten** to remove the statistic in favor of a qualitative phrasing. |

**Owning modules:** Content Writer Module (claim detection + threshold enforcement), Research & Citations Module (no schema change required; existing citations are already keyed by domain).

---

## 3. Module Impact Summary

| Module | Affected | Document(s) updated |
|---|---|---|
| Brief Generator | R1, R2, R3, R5 | `/docs/modules/content-brief-generator-prd-v1.7.md` (bumped to v1.8) |
| Writer Module | R3, R4, R5, R6, R7 | `/docs/modules/content-writer-module-prd-v1.3.md` (bumped to v1.6) |
| Platform | R5 | `/docs/content-platform-prd-v1_3.md` (bumped to v1.4) |
| Sources Cited | None — outputs unchanged | n/a |
| Research & Citations | None — schema unchanged; v1.6 writer adds first-party preference rule on the writer side | n/a |
| SIE | None | n/a |

## 4. Acceptance Criteria — Cross-Cutting

A run is **content-quality compliant** under this PRD when all of the following hold:

1. The brief output's `metadata.semantic_dedup_collapses_count + definitional_restatements_discarded_count ≥ 0` (i.e., the new fields exist; non-zero values are expected when the candidate pool actually contained semantic duplicates).
2. The brief output's `discarded_headings[].discard_reason` enum includes `semantic_duplicate_of_higher_priority_h2`, `definitional_restatement`, `too_short_after_sanitization`, and `non_descriptive_after_sanitization` (i.e., the new reasons are wired up).
3. The brief output's `spin_off_articles[]` field is present (may be empty; legacy `silo_candidates[]` is also present until v1.9).
4. The writer output's `article[]` contains exactly one section each of `type: "key-takeaways"`, `type: "intro"`, `type: "cta"`, in addition to the existing content/faq/conclusion sections.
5. The writer output's metadata contains `paragraph_length_violations: []`, `under_cited_sections: []`, `topic_brand_alignment: "brand_aligned"|"brand_agnostic"`, `dropped_for_low_topic_adherence: []`, and `brand_mention_count: int`.
6. No body paragraph in any section exceeds 4 sentences (or, if it does, the violation is recorded in `paragraph_length_violations`).
7. No two H2 headings have cosine similarity ≥ 0.85.
8. Headings show no SERP-artifact patterns from the R2 sanitization table.
9. At least 50% of citable claims (per R7 detection rules) in every content section are followed by a `{{cit_id}}` marker, or the deficit is recorded in `under_cited_sections`.

## 5. Out of Scope (v1.0 of this PRD)

- LLM-based contextual heading dedup (current scope is embedding-similarity based; LLM "do these mean the same thing?" check is a v1.1 candidate if embedding dedup misses persist).
- Multi-paragraph "Quote Card" / "Definition Card" structural blocks beyond Key Takeaways. Schema is open for v2 additions.
- Image-aware brand mentions (logo placement, alt-text brand inclusion).
- Style guide enforcement beyond the brand voice card (Oxford comma, em-dash style, sentence-case vs. title-case headings) — see frontend `toTitleCase` for the title-case rendering decision; this PRD does not prescribe sentence vs. title case at generation time.
- Reading-level scoring (Flesch-Kincaid) — paragraph length is the sole readability metric in v1.0.
- Auto-generated brand asset URLs (the brand voice card's `client_services` strings are not URL-resolved in v1.0).

## 6. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-01 | Initial draft. Authored in response to the 2026-05-01 audit of the `tiktok shop` run. Encodes R1–R7. |


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/suite-architecture-and-roadmap-v1_0.md -->
<!-- ============================================================ -->

# AR Tools — Suite Architecture & Roadmap (v1.0)

**Status:** Draft for review · **Authored:** 2026-05-29 · **Branch:** `claude/gracious-bell-BbkY5`

> **Read order note.** CLAUDE.md and the `/docs` PRDs were written when this repo was a *single* tool (the Blog Writer). This document supersedes that single-tool framing at the **product/architecture** level: AR Tools is now a **multi-module agency suite** sharing one dashboard, one Supabase database, and one scheduler. The existing engineering spec and module PRDs remain authoritative for the Blog Writer's *internals*. Where this doc and CLAUDE.md disagree on "how many tools is this," this doc wins; for "how is the Blog Writer built," the engineering spec still wins.

---

## 1. Vision

AR Tools is an **internal agency suite**. A team member (or VA) picks a client, then works across a set of SEO modules from one dashboard: generate content, research keywords, track rankings, and get alerted — with recommended fixes — when rankings drop. All modules share a single client roster and database.

Not customer-facing. No billing, no signup. Internal team only. (Unchanged from CLAUDE.md.)

## 2. The modules

| # | Module | Type | Status | Primary data source |
|---|---|---|---|---|
| 1 | Blog Writer | On-demand content | Exists (`/writer`) — re-home as a tab | DataForSEO + Claude |
| 2 | Local SEO content | On-demand content | Imported (`/local-seo-writer`) — integration deferred, see Appendix A | Google NLP + competitor SERP + Claude |
| 3 | Keyword research | On-demand research | Migrate from existing repo | Existing tool + **GSC** opportunity data |
| 4 | Organic rank tracker | Scheduled time-series | Build on shared spine | **DataForSEO** (rank-of-record) + GSC context |
| 5 | Maps / local-pack ranker | Scheduled time-series + geo | Build on shared spine | **DataForSEO** geo-grid |
| 6 | Ranking-drop agent | Intelligence over #4 + #5 | Build | Position **+ GSC clicks/impressions** |
| 7 | Content scheduler (VA) | Workflow / automation | Build | Orchestrates #1 & #2 |

Plus a cross-cutting **Google Search Console analytics layer** (clicks / impressions / CTR / average position) that feeds modules 3, 4, and 6 and powers a per-client performance view.

### Module groupings (they behave differently)

- **Group A — On-demand tools (1, 2, 3):** user provides input → tool runs → result. Migrations #2 and #3 are independent of the rankings work and can land in parallel any time.
- **Group B — Scheduled trackers (4, 5):** recurring jobs collect time-series data. Depend on the shared scheduler + rankings data model.
- **Group C — Intelligence & automation (6, 7):** ride on top of Groups A/B. The drop agent reasons over tracker data + SOPs; the content scheduler orchestrates Group A on a monthly cadence.

## 3. Decision log (locked)

These were decided with the user during scoping on 2026-05-29. Do not reverse without asking.

| Topic | Decision |
|---|---|
| **Organic rank source** | **Hybrid.** DataForSEO is the authoritative daily organic position (precise; covers target + competitor + not-yet-ranking keywords) and is the **only** source for maps/local-pack. GSC supplies clicks/impressions/CTR/average-position for analytics + keyword discovery, shown as *context* next to the DataForSEO rank. |
| **GSC connection** | **Service account.** A Google Cloud service-account key in env (no interactive OAuth/token refresh). Per-client onboarding step: add the service account's email as a user on that client's Search Console property, and store the property/site URL on the `clients` row. |
| **Rank data provider** | **DataForSEO** for both organic SERP and maps/local-pack (already wired into the Blog Writer). No new SERP vendor. |
| **Ranking-drop agent knowledge** | Build an **SOP store** (Supabase table + in-dashboard Markdown editor) the agent reasons over. SOPs are editable by the team without code changes. |
| **Alerting** | **In-app alerts feed** (badges on client tiles) **+ email/Slack** push on a flagged drop. Adds a small outbound notification service. |
| **Content scheduler trigger** | **Generate + publish, no human approval gate.** On the target date the system generates the content and publishes it automatically. |
| **Publish destination** | **Drive now, CMS-ready later.** "Publish" today = create a Google Doc in the client's Drive folder via the existing Apps Script webhook (`writer/platform-api/routers/publish.py`). Design the publish step so a live-to-CMS target (e.g. WordPress REST) can be added later without rework. **Live-to-site is explicitly out of scope for v1.** |
| **Auth/roles** | Internal only. VAs are `team_member`s. No new auth surface beyond the GSC service account. |

## 4. Data sources

- **DataForSEO** — organic positions, maps/local-pack, geo-grid. (Already integrated.)
- **Google Search Console** (service account) — clicks, impressions, CTR, average position; keyword/opportunity discovery.
- **Anthropic Claude** — content generation (per existing module PRDs) + drop-agent recommendations.
- **OpenAI `text-embedding-3-small`** — SIE only (unchanged).
- **Google Drive / Apps Script** — publish/delivery destination (existing).

## 5. Shared infrastructure to build

The modules are valuable individually but cheap together because they share these:

1. **Dashboard shell** — launcher tiles → per-client workspace with tabs (Blog, Local SEO, Keywords, Rankings, Alerts, Content Calendar). Re-home the existing Blog Writer UI as the first tab. Add `logo_url` to `clients` for tile branding.
2. **One shared scheduler** — the single most-reused piece. Drives: rankings ingestion (#4, #5), GSC pulls, and the monthly content schedule (#7). **Mechanism not yet chosen** — see Open Items.
3. **Rankings / metrics data model** — time-series tables for positions and a `gsc_metrics` table.
4. **GSC integration** — service-account auth + per-client property mapping + scheduled ingestion job.
5. **SOP store** — Supabase table + Markdown editor; consumed by the drop agent.
6. **Notifications service** — in-app alerts feed + email/Slack outbound.

## 6. Proposed data model additions (sketch — finalize at build time)

- `clients`: add `logo_url`, `gsc_property` (site URL), `business_location` (for maps geo-grid).
- `tracked_keywords` — `(client_id, keyword, type: organic|maps, location, active)`.
- `rank_snapshots` — `(tracked_keyword_id, date, position, url, source: dataforseo)`; maps rows carry geo-grid point.
- `gsc_metrics` — `(client_id, date, query, page, clicks, impressions, ctr, position)`.
- `sops` — `(id, title, body_markdown, tags, updated_by, updated_at)`.
- `alerts` — `(client_id, type, severity, summary, detail, status, created_at)`.
- `content_plans` / `content_plan_items` — `(client_id, month)` and `(type: blog|local_seo, topic/keyword, target_date, status, generated_run_id, published_doc_url)`.

All via migrations in `writer/supabase/migrations/` (existing convention), service-role access from the backend (per CLAUDE.md).

## 7. Roadmap (phased)

### Phase 0 — Foundation
- Dashboard shell: launcher tiles → client workspace with tabs.
- Re-home the Blog Writer UI as the first tab.
- `clients.logo_url` + tile branding.

### Phase 1 — Data spine
- Build the **shared scheduler** (mechanism TBD — confirm first).
- Rankings data model + **DataForSEO organic tracker** (#4).
- **GSC ingestion** (service account → `gsc_metrics`) + per-client performance view.
- **Maps ranker** (#5) — adds business location + geo-grid.

### Phase 2 — Intelligence & automation
- **Ranking-drop agent** (#6): SOP store → drop detection over Phase 1 data → Claude recommendations → alerts feed + email/Slack.
- **Content scheduler** (#7): monthly plans → auto-generate (#1/#2) → publish to Drive. CMS-ready seam, no approval gate.

### Parallel track — Migrations (any time)
- **Local SEO content** (#2) is **imported** at `/local-seo-writer` (raw, unmodified). Integration depth is **deferred** — pick A, B, or C from **Appendix A** before adapting it. **Keyword research** (#3) migrates in whenever its repo is provided. The KW tool gains GSC opportunity data once Phase 1 lands.

## 8. Open items (settle at build time, not blocking the plan)

1. **Scheduler mechanism** — pg_cron vs Railway cron vs an asyncio worker loop. CLAUDE.md requires confirming before adding any queue/scheduler-like infra. **Must decide before Phase 1.**
2. **Maps geo-grid density** — points per location; primary driver of DataForSEO cost.
3. **Migration repos** — #2 (Local SEO) is now imported and assessed — **see Appendix A** for its stack, data-model overlap, and the A/B/C integration options (decision deferred). #3 (Keyword research) stack/data-model fit remains unknown until its repo is shared.
4. **Notification channels** — confirm email provider and Slack workspace/webhook details.

## 9. Known doc discrepancies to reconcile

- **Frontend platform:** CLAUDE.md says "Lovable (React + Vite)." The actual repo has a React + Vite app in `/frontend` with `netlify.toml` (deployed to **Netlify**). This roadmap assumes the **`/frontend` + Netlify** reality. CLAUDE.md should be updated.
- **Single-tool framing:** CLAUDE.md's "What this project is" / build order describe only the Blog Writer. After this roadmap is accepted, CLAUDE.md should be updated to point here for suite-level context.

## 10. Next step

On approval of this roadmap: update CLAUDE.md + README to reflect the multi-module suite, then begin **Phase 0**. The scheduler-mechanism decision (Open Item #1) is the first thing to resolve before Phase 1.

---

## Appendix A — Local SEO module (#2): import & integration assessment

**Authored:** 2026-05-29 · **Status:** imported, integration **deferred** (no path chosen yet)

### A.1 What was done

The existing **ShowUP Local** app (`kssabraw/showup-local`) was imported into this repo at **`/local-seo-writer`** as a **raw, unmodified copy** (commit `7f3fe05`). Per decision, git history was **not** preserved (squashed into a single import commit). Excluded from the copy: `.git/`, `node_modules/`, `dist/`, and the app's `.env` / `.env.production` (they held only public `VITE_*` values, to be reconfigured for the suite at integration time). 174 files / ~37.7k lines.

No suite adaptation has been applied. The next diff against this import will cleanly show whatever changes are made to fit AR Tools.

### A.2 What the app is

A **local SEO content generator**: enter a keyword + location → it analyzes top-ranking competitor pages, extracts SEO signals (related keywords, key phrases, Google **NLP** entities), and generates optimized local-SEO pages tied to a Google Business Profile. This is exactly suite module #2.

### A.3 Stack — overlap and divergence vs. the suite

| Layer | AR Tools (suite) | ShowUP Local (imported) | Fit |
|---|---|---|---|
| Frontend base | React + Vite | React + Vite | ✅ same |
| UI system | Plain inline styles | **Tailwind + shadcn/ui** (`components.json`, `tailwind.config.ts`) | ⚠️ different design system |
| Routing | React Router | **React Router** (`react-router-dom` ^6.30) | ✅ same |
| Backend | **FastAPI** (platform-api / pipeline-api on Railway) | **Supabase Edge Functions** (Deno/TS) **+** a Python **FastAPI NLP microservice** (`services/nlp`) | ⚠️ different backend model |
| Database | Supabase (AR-Internal-Tools) | **Separate** Supabase project (29 migrations) | ⚠️ two databases |

**Reusable as-is in any path:** the **NLP microservice** (`services/nlp/main.py`, `url_filter.py`) — a standalone Python/FastAPI service that fits the suite's Railway model directly.

### A.4 Data-model overlap (similar, not matching)

ShowUP has its own `business_profiles`, `keyword_analyses`, `generated_pages`, plus a `User` carrying `password_hash` and `credit_balance`. Mapping onto the suite:

- `business_profiles` ≈ suite **`clients`** (overlapping concept, different columns).
- ShowUP `User` + credits **conflicts** with the suite model (Supabase **Auth** for identity; **no billing**).

### A.5 The core mismatch — it's built as a customer-facing SaaS

The app carries a **billing/credits** model the suite explicitly does not have: edge functions `purchase-credit-pack`, `purchase-press-release-pack`, `purchase-rankability-pack` (all **Stripe**-backed), plus `credit_balance` / credit-transaction logic. AR Tools is **internal-only, no billing** (CLAUDE.md §"What this project is"). **These billing parts should be dropped regardless of which integration path is chosen.**

### A.6 Integration options (decision deferred)

| Path | What it means | Effort | Trade-off |
|---|---|---|---|
| **A — Standalone in monorepo** | Keep ShowUP on its own stack (its Supabase + edge functions + NLP service); house it in `/local-seo-writer` and link from the dashboard as a module tile. | Lowest | Two databases, two client rosters; least integrated. |
| **B — Share data, keep backend** | Point it at the shared `clients` table + shared Supabase Auth; strip billing/credits; keep its edge functions + NLP service. | Medium | One client roster; still a second backend paradigm (edge functions) alongside FastAPI. |
| **C — Full port** | Rebuild its UI in the suite frontend style and move its backend logic into FastAPI (platform-api/pipeline-api). | Highest | Most consistent with the rest of the suite; largest rewrite. |

**Cross-cutting regardless of path:** (1) drop the Stripe/credits billing surface; (2) the NLP microservice can be lifted into the suite's Railway services unchanged; (3) reconcile `business_profiles` → `clients`.

**No path is chosen yet.** The raw import stays as-is until A/B/C is selected.


---


<!-- ============================================================ -->
<!-- SOURCE FILE: docs/engineering-implementation-spec-v1_1.md -->
<!-- ============================================================ -->

# Engineering Implementation Spec
## [Product Name TBD] — Internal Content Generation Platform

**Version:** 1.1
**Date:** April 30, 2026
**Status:** Ready for Implementation
**Based on:** Platform PRD v1.3, Writer Module v1.5 Change Spec
**Repo:** net-new GitHub repository (separate from ShowUP Local)

---

## 1. Repository Structure

Single GitHub repository with two deployable services and one Lovable-managed frontend.

```
/
├── platform-api/               # FastAPI — orchestrator, client CRUD, auth, file parsing
│   ├── main.py
│   ├── routers/
│   │   ├── clients.py
│   │   ├── runs.py
│   │   ├── users.py
│   │   └── files.py
│   ├── services/
│   │   ├── orchestrator.py     # run dispatch and state machine
│   │   ├── file_parser.py      # PDF/DOCX/TXT/MD/JSON → text
│   │   ├── website_scraper.py  # ScrapeOwl + LLM extraction
│   │   └── job_worker.py       # async_jobs table polling loop
│   ├── middleware/
│   │   └── auth.py             # Supabase JWT verification
│   ├── models/                 # Pydantic schemas
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
│
├── pipeline-api/               # FastAPI — all 5 module endpoints
│   ├── main.py
│   ├── modules/
│   │   ├── brief/
│   │   ├── sie/
│   │   ├── research/
│   │   ├── writer/
│   │   └── sources_cited/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
│
├── supabase/
│   └── migrations/             # SQL migration files, applied in order
│       ├── 001_schema.sql
│       ├── 002_rls.sql
│       └── 003_indexes.sql
│
└── README.md
```

**Lovable frontend:** Managed as a separate Lovable project. Connects to the platform-api via environment variable (`VITE_PLATFORM_API_URL`). Not housed in this repo.

---

## 2. Service Topology

### 2.1 Railway Services

| Service | Name | Purpose | Exposes |
|---|---|---|---|
| Platform API | `platform-api` | Orchestration, client management, auth, file parsing, website scraping | Public HTTPS — called by Lovable frontend |
| Pipeline API | `pipeline-api` | All 5 content generation modules | Internal Railway private networking — called only by platform-api |

**Platform API** is the only service with a public URL. The frontend never talks to the pipeline API directly.

**Pipeline API** uses Railway's private networking (`pipeline-api.railway.internal`) — it is not publicly accessible. This means module endpoints are not exposed to the internet.

### 2.2 Inter-Service Communication

```
Lovable Frontend
      │ HTTPS
      ▼
platform-api (public)
      │ HTTP (Railway private network)
      ▼
pipeline-api (private)
      │
      ├── /brief
      ├── /sie
      ├── /research
      ├── /write
      └── /sources-cited
```

Platform API calls pipeline API synchronously with per-request timeouts:

| Module | Request Timeout |
|---|---|
| Brief | 130s |
| SIE | 130s |
| Research | 130s |
| Writer | 100s |
| Sources Cited | 20s |

### 2.3 Concurrency Model

Platform API uses FastAPI's async capabilities. The orchestrator runs each pipeline as an `asyncio` background task. Brief + SIE are dispatched with `asyncio.gather()` for true parallelism within each run. Up to 5 runs can be in-flight simultaneously (enforced by a concurrency check before dispatch).

---

## 3. Supabase Schema

### 3.1 Migration File: 001_schema.sql

#### `profiles` (extends Supabase Auth users)

```sql
create table profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  role         text not null default 'team_member'
                 check (role in ('admin', 'team_member')),
  full_name    text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Auto-create profile on new auth user
create or replace function handle_new_user()
returns trigger as $$
begin
  insert into profiles (id, full_name)
  values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
```

#### `clients`

```sql
create table clients (
  id                              uuid primary key default gen_random_uuid(),
  name                            text not null,
  website_url                     text not null,
  website_analysis                jsonb,
  website_analysis_status         text not null default 'pending'
                                    check (website_analysis_status in ('pending', 'complete', 'failed')),
  website_analysis_error          text,
  brand_guide_source_type         text not null
                                    check (brand_guide_source_type in ('text', 'file')),
  brand_guide_text                text not null default '',
  brand_guide_file_path           text,
  brand_guide_original_filename   text,
  icp_source_type                 text not null
                                    check (icp_source_type in ('text', 'file')),
  icp_text                        text not null default '',
  icp_file_path                   text,
  icp_original_filename           text,
  archived                        boolean not null default false,
  created_by                      uuid references profiles(id),
  created_at                      timestamptz not null default now(),
  updated_at                      timestamptz not null default now()
);
```

#### `runs`

```sql
create table runs (
  id                uuid primary key default gen_random_uuid(),
  client_id         uuid not null references clients(id),
  keyword           text not null,
  intent_override   text,
  sie_outlier_mode  text not null default 'safe'
                      check (sie_outlier_mode in ('safe', 'aggressive')),
  sie_force_refresh boolean not null default false,
  status            text not null default 'queued'
                      check (status in (
                        'queued', 'brief_running', 'sie_running',
                        'research_running', 'writer_running',
                        'sources_cited_running', 'complete', 'failed', 'cancelled'
                      )),
  error_stage       text,
  error_message     text,
  sie_cache_hit     boolean,
  total_cost_usd    numeric(10, 4),
  started_at        timestamptz,
  completed_at      timestamptz,
  created_by        uuid references profiles(id),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
```

#### `client_context_snapshots`

```sql
create table client_context_snapshots (
  id                            uuid primary key default gen_random_uuid(),
  run_id                        uuid not null unique references runs(id) on delete cascade,
  client_id                     uuid not null references clients(id),
  brand_guide_text              text,
  icp_text                      text,
  website_analysis              jsonb,
  website_analysis_unavailable  boolean not null default false,
  created_at                    timestamptz not null default now()
);
```

#### `module_outputs`

```sql
create table module_outputs (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  module          text not null
                    check (module in ('brief', 'sie', 'research', 'writer', 'sources_cited')),
  status          text not null
                    check (status in ('running', 'complete', 'failed')),
  input_payload   jsonb,
  output_payload  jsonb,
  cost_usd        numeric(10, 4),
  duration_ms     integer,
  module_version  text,
  attempt_number  integer not null default 1,
  created_at      timestamptz not null default now(),
  completed_at    timestamptz,
  unique (run_id, module, attempt_number)
);
```

#### `async_jobs`

```sql
create table async_jobs (
  id            uuid primary key default gen_random_uuid(),
  job_type      text not null check (job_type in ('website_scrape')),
  entity_id     uuid not null,               -- client_id for website_scrape
  status        text not null default 'pending'
                  check (status in ('pending', 'running', 'complete', 'failed')),
  attempts      integer not null default 0,
  max_attempts  integer not null default 2,
  payload       jsonb,
  result        jsonb,
  error         text,
  scheduled_at  timestamptz not null default now(),
  started_at    timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now()
);
```

### 3.2 Migration File: 002_rls.sql

```sql
-- Enable RLS on all tables
alter table profiles                  enable row level security;
alter table clients                   enable row level security;
alter table runs                      enable row level security;
alter table client_context_snapshots  enable row level security;
alter table module_outputs            enable row level security;
alter table async_jobs                enable row level security;

-- profiles: users read own; admins read all
create policy "users read own profile"
  on profiles for select
  using (auth.uid() = id);

create policy "admins read all profiles"
  on profiles for select
  using (exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  ));

create policy "admins update profiles"
  on profiles for update
  using (exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  ));

-- clients: all authenticated users read; only admins write
create policy "authenticated users read clients"
  on clients for select
  using (auth.role() = 'authenticated');

create policy "admins manage clients"
  on clients for all
  using (exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  ));

-- runs: all authenticated users read and insert
create policy "authenticated users read runs"
  on runs for select
  using (auth.role() = 'authenticated');

create policy "authenticated users create runs"
  on runs for insert
  with check (auth.role() = 'authenticated');

create policy "authenticated users update own runs"
  on runs for update
  using (created_by = auth.uid() or exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  ));

-- client_context_snapshots: all authenticated users read; service role writes
create policy "authenticated users read snapshots"
  on client_context_snapshots for select
  using (auth.role() = 'authenticated');

-- module_outputs: all authenticated users read; service role writes
create policy "authenticated users read module outputs"
  on module_outputs for select
  using (auth.role() = 'authenticated');

-- async_jobs: service role only (no direct client access)
-- No policies needed — service role bypasses RLS by default
```

### 3.3 Migration File: 003_indexes.sql

```sql
create index idx_clients_archived        on clients (archived);
create index idx_clients_name            on clients (name);
create index idx_runs_client_id          on runs (client_id);
create index idx_runs_status             on runs (status);
create index idx_runs_created_at         on runs (created_at desc);
create index idx_runs_created_by         on runs (created_by);
create index idx_module_outputs_run_id   on module_outputs (run_id);
create index idx_async_jobs_status       on async_jobs (status);
create index idx_async_jobs_scheduled_at on async_jobs (scheduled_at);
```

### 3.4 Storage Buckets

Two private Supabase Storage buckets:

| Bucket | Path Convention | Purpose | Status |
|---|---|---|---|
| `files` | `files/{user_id}/{file_id}/{original_filename}` | Brand guide and ICP file uploads (PDF/DOCX/TXT/MD/JSON) | Active in v1 |
| `article-assets` | `article-assets/{run_id}/{asset_id}.{ext}` | Reserved for generated article images and embedded media | **Placeholder only** — created in v1 but unused. The Writer Module v1.5 does not generate image references. Reserved here so v2 image-generation work doesn't require schema migration or Storage configuration. |

Both buckets are private. Access only via signed URLs minted by the platform-api after JWT verification.

---

## 4. Authentication Flow

### 4.1 Login (Lovable → Supabase Auth)

1. User submits email + password on `/login`
2. Lovable calls `supabase.auth.signInWithPassword()` directly (no platform-api involvement)
3. Supabase returns a session with a JWT access token
4. Lovable stores the session in memory / localStorage via the Supabase JS client
5. On subsequent API calls, Lovable includes the JWT in the `Authorization: Bearer <token>` header

### 4.2 JWT Verification (Platform API)

Every platform-api request (except health checks) passes through auth middleware:

```python
# middleware/auth.py (pseudocode)
async def verify_jwt(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        raise HTTPException(401)
    
    # Verify with Supabase using the JWT secret
    user = supabase_admin.auth.get_user(token)
    if not user:
        raise HTTPException(401)
    
    # Fetch role from profiles table
    profile = supabase_admin.table("profiles").select("role").eq("id", user.id).single()
    request.state.user_id = user.id
    request.state.role = profile["role"]
```

### 4.3 Admin Route Guard

Any route requiring admin access checks `request.state.role == "admin"` and raises `403` if not met. This is a FastAPI dependency injected at the router level.

### 4.4 Session Refresh

The Supabase JS client on the frontend handles token refresh automatically. The platform-api does not manage sessions.

---

## 5. Platform API — Routes

Base URL: `https://platform-api-[hash].up.railway.app`

### 5.0 Standard Error Response Format

All non-2xx responses from the platform-api use a consistent shape:

```json
{
  "error": {
    "code": "string_identifier",
    "message": "Human-readable explanation",
    "details": { "...optional context..." },
    "request_id": "req_abc123"
  }
}
```

The `request_id` is the same correlation ID logged server-side (see Section 13), so support requests can be traced through Railway logs by pasting it into search.

#### Common Error Codes

| Code | HTTP | Meaning |
|---|---|---|
| `unauthenticated` | 401 | JWT missing or invalid |
| `forbidden` | 403 | User lacks required role (e.g. team_member attempting admin action) |
| `validation_error` | 422 | Request body fails Pydantic validation |
| `client_not_found` | 404 | Client ID does not exist |
| `run_not_found` | 404 | Run ID does not exist |
| `client_name_taken` | 409 | Duplicate client name on create |
| `last_admin_demotion` | 409 | Attempt to demote the only admin |
| `concurrency_limit` | 429 | 5 runs already in non-terminal states |
| `unsupported_file_type` | 422 | Uploaded MIME type not in allowlist |
| `file_too_large` | 413 | Upload exceeds 10 MB |
| `file_parse_error` | 422 | File could not be parsed (e.g. corrupt DOCX) |
| `scanned_pdf` | 422 | PDF has <50 chars after text extraction |
| `schema_version_mismatch` | 500 | Pipeline module returned unexpected `schema_version` (see Section 6.5) |
| `module_timeout` | 504 | Pipeline module exceeded its timeout |
| `internal_error` | 500 | Unhandled server exception |

The frontend uses `code` for programmatic handling (e.g., showing specific UI states) and `message` for display.

### 5.1 Health

```
GET /health
→ 200 { "status": "ok" }
No auth required.
```

### 5.2 Users (admin only)

```
GET /users
→ 200 [{ id, email, full_name, role, created_at }]

POST /users/invite
Body: { email: string, role: "admin" | "team_member" }
→ 201 { id, email, role }
(Sends Supabase magic link invitation)

PATCH /users/{user_id}/role
Body: { role: "admin" | "team_member" }
→ 200 { id, role }
Guard: cannot demote self if last admin

DELETE /users/{user_id}
→ 204
Guard: cannot delete self
```

### 5.3 Clients

```
GET /clients?archived=false
→ 200 [{ id, name, website_url, website_analysis_status, archived, created_at }]
Auth: all authenticated users

GET /clients/{client_id}
→ 200 {
    id, name, website_url,
    website_analysis, website_analysis_status, website_analysis_error,
    brand_guide_source_type, brand_guide_text, brand_guide_original_filename,
    icp_source_type, icp_text, icp_original_filename,
    archived, created_at, updated_at
  }
Auth: all authenticated users

POST /clients                         [admin only]
Body: {
  name: string,
  website_url: string,
  brand_guide_source_type: "text" | "file",
  brand_guide_text: string,           -- required if source_type=text
  brand_guide_file_id: uuid,          -- required if source_type=file (from /files upload)
  icp_source_type: "text" | "file",
  icp_text: string,
  icp_file_id: uuid
}
→ 201 { id, name, website_analysis_status: "pending", ... }
Side effect: enqueues website_scrape async_job

PATCH /clients/{client_id}            [admin only]
Body: same shape as POST (all fields optional)
→ 200 { updated client }
Side effect: if website_url changed, enqueues new website_scrape job

POST /clients/{client_id}/archive     [admin only]
→ 200 { id, archived: true }

POST /clients/{client_id}/reanalyze   [admin only]
→ 202 { job_id }
Side effect: enqueues website_scrape async_job immediately
```

### 5.4 File Uploads

Files are uploaded before client creation. The returned `file_id` is passed to `POST /clients`.

```
POST /files/upload
Content-Type: multipart/form-data
Body: { file: <binary>, field: "brand_guide" | "icp" }
→ 201 {
    file_id: uuid,
    original_filename: string,
    parsed_text: string,          -- extracted text, truncated to 150,000 chars if over
    truncated: boolean,
    format: "json" | "markdown" | "text"
  }
Guards:
  - Max file size: 10 MB (enforced before parsing)
  - Supported types: application/pdf, application/vnd.openxmlformats...(docx),
                     text/plain, text/markdown, application/json
  - PDF with <50 chars extracted → 422 "Scanned PDF detected"
  - File stored to Supabase Storage bucket: files/{user_id}/{file_id}/{filename}
```

### 5.5 Runs

```
GET /runs?client_id=&status=&search=&page=1&page_size=50
→ 200 {
    data: [{ id, keyword, client_id, client_name, status, sie_cache_hit,
             total_cost_usd, created_at, started_at, completed_at }],
    total: int,
    page: int
  }

GET /runs/{run_id}
→ 200 {
    id, keyword, client_id, status, sie_cache_hit,
    error_stage, error_message, total_cost_usd,
    created_at, started_at, completed_at,
    client_context_snapshot: { brand_guide_text, icp_text, website_analysis, website_analysis_unavailable },
    module_outputs: {
      brief:        { status, output_payload, cost_usd, duration_ms, module_version },
      sie:          { status, output_payload, cost_usd, duration_ms, module_version },
      research:     { status, output_payload, cost_usd, duration_ms, module_version },
      writer:       { status, output_payload, cost_usd, duration_ms, module_version },
      sources_cited:{ status, output_payload, cost_usd, duration_ms, module_version }
    }
  }

POST /runs
Body: {
  client_id: uuid,
  keyword: string,                   -- max 150 chars
  intent_override: string | null,
  sie_outlier_mode: "safe" | "aggressive",
  sie_force_refresh: boolean
}
→ 202 { run_id: uuid, status: "queued" }
Side effect: creates run + snapshot rows, dispatches orchestration background task
Guard: rejects if 5 or more runs currently in non-terminal states (returns 429 `concurrency_limit`)
Idempotency: v1 relies on frontend debounce only — the NewRunForm disables the submit
button on click and re-enables only after the response (or after 3s on network error).
No server-side `Idempotency-Key` in v1. If duplicate runs from misbehaving clients
become a real problem, server-side dedupe can be added in v1.x — see Section 14 Open Items.

POST /runs/{run_id}/cancel
→ 200 { id, status: "cancelled" }
Guard: only creator or admin
Side effect: sets cancellation flag; orchestrator checks flag between stages

POST /runs/{run_id}/rerun
→ 202 { run_id: uuid }            -- new run_id
Side effect: creates new run with same keyword/config, new snapshot from current client context

GET /runs/{run_id}/poll
→ 200 {
    run_id: uuid,
    status: string,
    completed_stages: ["brief", "sie", ...],
    error_stage: string | null,
    updated_at: timestamptz
  }
Lightweight endpoint. Frontend polls every 5 seconds while status is non-terminal.
```

### 5.6 Cost Dashboard (admin only)

```
GET /analytics/costs?group_by=day|client|module&from=&to=
→ 200 {
    rows: [{ dimension: string, cost_usd: number, run_count: int }],
    total_cost_usd: number
  }

GET /analytics/failures?from=&to=
→ 200 [{ run_id, keyword, client_name, error_stage, error_message, created_at }]
```

---

## 6. Pipeline Orchestration

### 6.1 Orchestration Flow (platform-api/services/orchestrator.py)

When `POST /runs` is called, after creating the DB rows, the platform-api fires a FastAPI `BackgroundTask`:

```python
# pseudocode — full implementation in orchestrator.py
async def orchestrate_run(run_id: uuid):
    try:
        # Check cancellation before each stage
        if await is_cancelled(run_id): return

        # Stage 1: Brief + SIE in parallel
        await set_status(run_id, "brief_running")  # also implies sie_running
        brief_result, sie_result = await asyncio.gather(
            call_module("brief",   run_id, build_brief_payload(run_id)),
            call_module("sie",     run_id, build_sie_payload(run_id)),
            return_exceptions=True
        )
        if isinstance(brief_result, Exception): raise StageError("brief", brief_result)
        if isinstance(sie_result, Exception):   raise StageError("sie",   sie_result)

        # Stage 2: Research (requires brief output)
        if await is_cancelled(run_id): return
        await set_status(run_id, "research_running")
        research_result = await call_module("research", run_id,
                                            build_research_payload(run_id, brief_result))
        if isinstance(research_result, Exception): raise StageError("research", research_result)

        # Cross-validate keywords match
        validate_keyword_consistency(brief_result, sie_result, research_result, run_id)

        # Stage 3: Writer (requires brief + sie + research + client_context)
        if await is_cancelled(run_id): return
        await set_status(run_id, "writer_running")
        writer_result = await call_module("writer", run_id,
                                          build_writer_payload(run_id, brief_result,
                                                               sie_result, research_result))
        if isinstance(writer_result, Exception): raise StageError("writer", writer_result)

        # Stage 4: Sources Cited
        if await is_cancelled(run_id): return
        await set_status(run_id, "sources_cited_running")
        sources_result = await call_module("sources_cited", run_id,
                                           build_sources_payload(run_id, writer_result,
                                                                  research_result))
        if isinstance(sources_result, Exception): raise StageError("sources_cited", sources_result)

        # Complete
        await set_status(run_id, "complete")
        await update_total_cost(run_id)

    except StageError as e:
        await set_status(run_id, "failed", error_stage=e.stage, error_message=str(e))
    except Exception as e:
        await set_status(run_id, "failed", error_stage="unknown", error_message=str(e))
```

### 6.2 `call_module` Pattern

```python
async def call_module(module: str, run_id: uuid, payload: dict) -> dict:
    # Save input payload to module_outputs
    output_id = await create_module_output(run_id, module, payload)

    # Call pipeline API with timeout
    timeout = MODULE_TIMEOUTS[module]
    try:
        start = time.time()
        response = await http_client.post(
            f"{PIPELINE_API_URL}/{module}",
            json=payload,
            timeout=timeout
        )
        duration_ms = int((time.time() - start) * 1000)

        if response.status_code != 200:
            raise ModuleHTTPError(response.status_code, response.text)

        result = response.json()
        await save_module_output(output_id, result, duration_ms, cost=result.get("cost_usd"))
        return result

    except (httpx.TimeoutException, ModuleHTTPError) as e:
        # One automatic retry on timeout or 5xx
        if is_retriable(e) and attempt == 1:
            return await call_module(module, run_id, payload, attempt=2)
        await fail_module_output(output_id, str(e))
        raise StageError(module, e)
```

### 6.3 Cancellation

The orchestrator checks `is_cancelled(run_id)` before each stage by reading the `status` column from Supabase. If `cancelled`, the orchestrator exits immediately without dispatching further modules.

The `POST /runs/{run_id}/cancel` endpoint simply sets `status = 'cancelled'` in Supabase. The next cancellation check in the orchestrator loop picks it up.

### 6.4 Startup Recovery

On `platform-api` startup:

```python
# Find runs stuck in non-terminal states (platform crashed mid-run)
stuck_runs = supabase.table("runs").select("id").in_("status", [
    "queued", "brief_running", "sie_running",
    "research_running", "writer_running", "sources_cited_running"
]).execute()

# Mark them failed with recovery message
for run in stuck_runs:
    await set_status(run.id, "failed",
                     error_stage="recovery",
                     error_message="Service restarted mid-run. Please re-run.")
```

### 6.5 Module Schema Version Validation

Every pipeline module returns a `schema_version` field in its output. The orchestrator validates this against an expected-version registry **strictly** — any mismatch (major or minor) fails the run immediately.

#### Version Registry

```python
# platform-api/services/orchestrator.py
EXPECTED_MODULE_VERSIONS = {
    "brief":         "1.7",
    "sie":           "1.0",
    "research":      "1.1",
    "writer":        "1.5",
    "sources_cited": "1.1",
}
```

This registry is the single source of truth. When a module is upgraded, the registry must be updated in the same commit that updates the orchestrator's payload-building or output-consuming logic.

#### Validation Rule

After every successful `call_module` invocation:

```python
expected = EXPECTED_MODULE_VERSIONS[module]
actual   = result.get("schema_version")

if actual != expected:
    raise SchemaVersionMismatch(
        module=module,
        expected=expected,
        actual=actual,
        run_id=run_id
    )
```

#### Failure Behavior

A schema version mismatch:

- Aborts the current run immediately (no retry — this is a deployment bug, not a transient error)
- Marks the run as `failed` with `error_stage = <module>` and `error_message = "schema version mismatch: expected 1.7, got 1.8"`
- Returns `500 schema_version_mismatch` to the calling client (frontend)
- Logs the mismatch at `ERROR` level with both versions and the offending module name (see Section 13)

#### Writer Module Special Cases

The Writer Module emits three distinct version strings depending on input completeness (per Writer v1.5 spec):

- `"1.5"` — full v1.5 behavior with client_context
- `"1.5-no-context"` — v1.4 fallback (client_context omitted)
- `"1.5-degraded"` — v1.4 fallback (all client context fields empty)

The orchestrator's validation accepts all three for the Writer module:

```python
WRITER_ACCEPTED_VERSIONS = {"1.5", "1.5-no-context", "1.5-degraded"}
```

In v1, the platform always sends `client_context`, so `"1.5"` is the expected case. The other two would indicate a bug in the platform (client context not being attached) or a deliberate test scenario. Either way, the run completes successfully — but the version is logged so anomalies are visible in dashboards.

---

## 7. Async Jobs (Website Scraping)

### 7.1 Enqueue

When a client is created or website_url is edited:

```python
await supabase.table("async_jobs").insert({
    "job_type": "website_scrape",
    "entity_id": client_id,
    "payload": { "website_url": client.website_url, "client_id": str(client_id) }
})
```

### 7.2 Worker Loop

`platform-api` runs a background asyncio loop that polls `async_jobs` every 10 seconds:

```python
async def job_worker():
    while True:
        await asyncio.sleep(10)
        job = await claim_next_job()   # SELECT ... FOR UPDATE SKIP LOCKED
        if job:
            await process_job(job)

async def process_job(job):
    if job.job_type == "website_scrape":
        await run_website_scrape(job)
```

`SELECT ... FOR UPDATE SKIP LOCKED` ensures two platform-api instances (if Railway ever scales to 2) don't double-process the same job.

### 7.3 Website Scrape Logic

```python
async def run_website_scrape(job):
    client_id = job.payload["client_id"]
    website_url = job.payload["website_url"]

    try:
        # 1. Scrape homepage via ScrapeOwl
        html = await scrapeowl_fetch(website_url, timeout=45)

        # 2. LLM extraction — single call
        result = await llm_extract_website_data(html)
        # LLM prompt targets: services[], locations[], contact_info{phone,email,address,hours}
        # Returns structured JSON matching website_analysis schema

        # 3. Persist to client record
        await supabase.table("clients").update({
            "website_analysis": result,
            "website_analysis_status": "complete"
        }).eq("id", client_id)

    except Exception as e:
        await supabase.table("clients").update({
            "website_analysis_status": "failed",
            "website_analysis_error": str(e)
        }).eq("id", client_id)
```

**Website analysis output schema (stored in `website_analysis` jsonb column):**

```json
{
  "services": ["Furnace Installation", "AC Repair", "..."],
  "locations": ["Orange County", "Anaheim", "..."],
  "contact_info": {
    "phone": "(714) 555-0100",
    "email": "info@example.com",
    "address": "123 Main St, Anaheim CA 92801",
    "hours": "Mon-Fri 8am-6pm"
  }
}
```

---

## 8. File Parsing

All file parsing happens in the platform-api at upload time (`POST /files/upload`). Parsed text is returned in the response and stored in the client's `brand_guide_text` / `icp_text` field.

### 8.1 Parser Selection

```python
PARSERS = {
    "application/pdf":        parse_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
    "text/plain":             parse_text,
    "text/markdown":          parse_markdown,
    "application/json":       parse_json,
}
```

### 8.2 Per-Format Rules

| Format | Library | Output | Rejection Condition |
|---|---|---|---|
| PDF | `pypdf` | Extracted plain text | <50 chars after extraction (scanned image) |
| DOCX | `python-docx` | Extracted text from paragraphs + table cells | Unreadable/corrupt file |
| TXT | `open()` + `read()` | Raw text | Not UTF-8 decodable |
| MD | `open()` + `read()` | Raw text with Markdown preserved | Not UTF-8 decodable |
| JSON | `json.loads()` + `json.dumps(indent=2)` | Pretty-printed JSON string | Invalid JSON |

### 8.3 Format Detection

```python
# Detect format for downstream (writer distillation step needs to know)
def detect_format(content: str, mime_type: str) -> str:
    if mime_type == "application/json":
        return "json"
    if mime_type == "text/markdown" or content.strip().startswith("#"):
        return "markdown"
    return "text"
```

Format is stored in the snapshot as `brand_guide_format` so the writer's distillation LLM knows how to parse it.

### 8.4 Truncation

If parsed text exceeds 150,000 characters, truncate at the nearest sentence boundary below the limit and return `truncated: true` in the response. Do not truncate mid-word.

---

## 9. Pipeline API — Module Endpoints

Base URL: `http://pipeline-api.railway.internal` (private network only)

All endpoints: `POST /{module}` → `200 { output_payload... , cost_usd, schema_version }`

Errors: `422` for schema validation failures (no retry), `500` for transient errors (one retry from orchestrator).

### 9.1 Standard Input Envelope

Every pipeline API endpoint receives a `run_id` for idempotency:

```json
{
  "run_id": "uuid",
  "attempt": 1,
  ...module-specific fields...
}
```

Modules that receive a duplicate `run_id` + `attempt` combination return the cached result without re-running.

### 9.2 Module Endpoints Summary

| Path | Key Inputs | Key Outputs |
|---|---|---|
| `POST /brief` | `keyword`, `location_code`, `intent_override` | Brief JSON (headings, intent, word targets, FAQ targets) |
| `POST /sie` | `keyword`, `location_code`, `outlier_mode`, `force_refresh` | `terms.required[]`, `terms.avoid[]`, `word_count_target`, `sie_cache_hit` |
| `POST /research` | `keyword`, `brief_output` | `citations[]` with excerpts and relevance scores |
| `POST /write` | `brief_output`, `sie_output`, `research_output`, `client_context` | `article[]`, `citation_usage`, `brand_voice_card_used`, `brand_conflict_log[]` |
| `POST /sources-cited` | `writer_output`, `research_output` | Final article Markdown with formatted Sources Cited section |

### 9.3 Client Context in Writer Payload

```json
{
  "run_id": "uuid",
  "attempt": 1,
  "brief_output": { ...from brief module... },
  "sie_output": { ...from sie module... },
  "research_output": { ...from research module... },
  "client_context": {
    "brand_guide_text": "...",
    "brand_guide_format": "json" | "markdown" | "text",
    "icp_text": "...",
    "icp_format": "json" | "markdown" | "text",
    "website_analysis": { ...or null... },
    "website_analysis_unavailable": false
  }
}
```

### 9.4 Image References — Out of Scope for v1

The Writer Module v1.5 does not generate, reference, or embed images in article output. Final articles are pure Markdown text with citation markers — no `![alt](src)` image tags.

The `article-assets` Supabase Storage bucket (Section 3.4) is reserved for v2 work. When image generation is added later:
- Writer output schema will gain `images[]` and inline image markers (e.g., `{{img_1}}`)
- A new pipeline stage between Writer and Sources Cited will materialize image markers into Markdown image tags pointing to signed URLs from the bucket
- No platform schema changes will be required

---

## 10. Frontend Architecture (Lovable)

### 10.1 Environment Variables

```
VITE_PLATFORM_API_URL=https://platform-api-[hash].up.railway.app
VITE_SUPABASE_URL=https://[project].supabase.co
VITE_SUPABASE_ANON_KEY=[anon key]
```

### 10.2 Routes

| Path | Component | Auth | Admin Only |
|---|---|---|---|
| `/login` | `LoginScreen` | None | No |
| `/` | Redirect to `/runs` | Required | No |
| `/runs` | `RunDashboard` | Required | No |
| `/runs/new` | `NewRunForm` | Required | No |
| `/runs/:runId` | `RunDetail` | Required | No |
| `/clients` | `ClientList` | Required | No |
| `/clients/new` | `ClientForm` | Required | Admin |
| `/clients/:clientId` | `ClientDetail` | Required | Admin (edit); all (view) |
| `/admin/users` | `UserManagement` | Required | Admin |

### 10.3 Key Components

**`AuthProvider`**
Wraps the entire app. Initializes Supabase client, subscribes to `onAuthStateChange`, exposes `session`, `user`, `profile` (including `role`) via context. All routes consume this context.

**`RequireAuth` / `RequireAdmin`**
Route guards. `RequireAuth` redirects to `/login` if no session. `RequireAdmin` renders a 403 screen if `profile.role !== 'admin'`.

**`useRunPoller(runId)`**
Custom hook. Polls `GET /runs/:runId/poll` every 5 seconds while the run is in a non-terminal state. Stops automatically when status becomes `complete`, `failed`, or `cancelled`. Invalidates the full run query on completion so the detail view refreshes.

```typescript
// Usage
const { status, completedStages } = useRunPoller(runId);
```

**`ClientForm`**
Handles both "Paste Text" and "Upload File" tabs for brand guide and ICP. On file select, immediately calls `POST /files/upload` and shows a parsing status indicator. Stores the returned `file_id` and `parsed_text` in form state. On submit, sends `file_id` to `POST /clients` if file path was used.

**`NewRunForm`**
Basic fields: client dropdown, keyword input. Advanced options (collapsed by default): intent override select, SIE outlier mode toggle (safe/aggressive), force refresh checkbox. On submit, calls `POST /runs` and redirects to `/runs/:runId` to begin polling.

**Submit-button debounce (idempotency control):** the submit button is disabled the moment it is clicked, remains disabled while the `POST /runs` request is in flight, and stays disabled for an additional 2 seconds after a successful response. This is the v1 mechanism for preventing duplicate runs from rapid double-clicks. Server-side `Idempotency-Key` handling is deferred to v2 if duplicate runs become a problem in practice.

**`RunDetail`**
Shows run status at the top (live via `useRunPoller`). Below status, renders module output tabs: Brief, SIE, Research, Writer, Sources Cited — each tab shows the JSON output when the stage is complete, or a spinner when running. Article Review tab (active only when status = `complete`) shows the rendered Markdown and export controls.

**`ArticlePreview`**
Renders final Markdown from `sources_cited` module output. Two views: "Preview" (rendered HTML) and "Markdown" (raw source). Export buttons: Copy Markdown, Copy HTML, Download `.md`.

**`CostDashboard`** (admin only)
Displays aggregate cost tables grouped by day/client/module. Fetches `GET /analytics/costs`.

### 10.4 API Client Pattern

Use a thin wrapper around `fetch` that injects the Supabase JWT automatically:

```typescript
// lib/api.ts
async function apiRequest(path: string, options?: RequestInit) {
  const session = await supabase.auth.getSession();
  return fetch(`${PLATFORM_API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${session.data.session?.access_token}`,
      ...options?.headers,
    },
  });
}
```

### 10.5 State Management

No global state manager (Redux, Zustand) needed in v1. Use:
- **Supabase JS client** for auth state
- **TanStack Query (React Query)** for server state (runs list, run detail, clients list)
- **React local state** for form state

Lovable supports TanStack Query natively.

---

## 11. Environment Variables

### 11.1 `platform-api` Railway Service

```
# Supabase
SUPABASE_URL=https://[project].supabase.co
SUPABASE_ANON_KEY=[anon key]
SUPABASE_SERVICE_ROLE_KEY=[service role key]   # used for admin operations + RLS bypass

# Pipeline API
PIPELINE_API_URL=http://pipeline-api.railway.internal

# External APIs (used by platform-api for website scraping)
SCRAPEOWL_API_KEY=[key]
OPENAI_API_KEY=[key]                           # or ANTHROPIC_API_KEY for website extraction LLM

# App config
MAX_CONCURRENT_RUNS=5
JOB_WORKER_POLL_INTERVAL_SECONDS=10
```

### 11.2 `pipeline-api` Railway Service

```
# Supabase (for SIE caching)
SUPABASE_URL=https://[project].supabase.co
SUPABASE_SERVICE_ROLE_KEY=[service role key]

# External APIs
DATAFORSEO_LOGIN=[login]
DATAFORSEO_PASSWORD=[password]
SCRAPEOWL_API_KEY=[key]
OPENAI_API_KEY=[key]
ANTHROPIC_API_KEY=[key]
GOOGLE_APPLICATION_CREDENTIALS=[path or JSON string for NLP API]

# Module config
SIE_CACHE_TTL_DAYS=7
```

---

## 12. Deployment Sequence

Build and deploy in this order to avoid dependency issues.

### Phase 1 — Supabase

1. **Install Supabase CLI** locally on the engineer's machine: `brew install supabase/tap/supabase` (macOS) or follow [docs](https://supabase.com/docs/guides/cli/getting-started) for other platforms
2. **Initialize the project** in the repo root: `supabase init` — creates the `/supabase` directory with config and migrations folder
3. **Create the new Supabase project** via the Supabase dashboard (separate from ShowUP Local). Note the project ref (e.g. `abcdefghijkl`).
4. **Link the local repo** to the project: `supabase link --project-ref [ref]` — prompts for the database password
5. **Add migration files** to `/supabase/migrations/` with timestamp-prefixed naming convention: `[YYYYMMDDhhmmss]_[description].sql`. Place the three migration files from Section 3 in order:
   - `20260430120000_schema.sql` (Section 3.1)
   - `20260430120100_rls.sql` (Section 3.2)
   - `20260430120200_indexes.sql` (Section 3.3)
6. **Apply migrations** to the linked project: `supabase db push`
7. **Create Storage buckets** (Section 3.4) via Supabase dashboard → Storage:
   - `files` (private)
   - `article-assets` (private; placeholder for v2)
8. **Create the first admin user** via Supabase dashboard → Auth → Users → "Add user" → enter email and temporary password
9. **Promote that user to admin** by running in the SQL editor:
   ```sql
   update profiles set role = 'admin' where id = (
     select id from auth.users where email = 'your-email@example.com'
   );
   ```

**Local development tip:** run `supabase start` to spin up a local Postgres + Auth stack for testing migrations before pushing them to the linked project. Run `supabase db reset` to wipe and reapply all migrations locally.

**Production migration workflow going forward:** create a new migration file with `supabase migration new [description]`, edit the generated SQL, test locally with `supabase db reset`, then push with `supabase db push`.

### Phase 2 — Pipeline API

1. Create `pipeline-api` Railway service from GitHub repo (`/pipeline-api` root)
2. Set all pipeline-api environment variables
3. Deploy and verify health: `GET /health → 200`
4. Smoke test each module endpoint with a synthetic payload (no Supabase calls needed at this point)

### Phase 3 — Platform API

1. Create `platform-api` Railway service from GitHub repo (`/platform-api` root)
2. Set all platform-api environment variables including `PIPELINE_API_URL` pointing to the private pipeline-api address
3. Deploy and verify health: `GET /health → 200`
4. Enable Railway private networking between the two services
5. Smoke test: create a client via `POST /clients`, verify website_scrape job enqueues and processes

### Phase 4 — End-to-End Pipeline Test (pre-frontend)

Using a REST client (Postman, Insomnia, or curl):
1. Auth: get a JWT via Supabase Auth REST API
2. Create a client with a real brand guide and website URL
3. POST a run with a real keyword
4. Poll `GET /runs/{run_id}/poll` manually every 10 seconds
5. On completion, `GET /runs/{run_id}` and verify all module outputs are populated and the final article is present

### Phase 5 — Lovable Frontend

1. Create new Lovable project
2. Set environment variables: `VITE_PLATFORM_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
3. Build screens in dependency order:
   - Login screen (no API needed)
   - Client list + client form (needs Phase 3)
   - New run form (needs Phase 3)
   - Run dashboard (needs Phase 3)
   - Run detail + article review (needs Phase 4 complete)
   - Admin: user management, cost dashboard

---

## 13. Logging & Observability

Both services emit structured JSON logs to stdout, which Railway captures and indexes for search. This is the only logging sink in v1. No external observability platform (Datadog, Sentry, etc.) — Railway's built-in log search is sufficient at the team's scale.

### 13.1 Log Format

Use Python's standard `logging` module with a JSON formatter (`python-json-logger`):

```json
{
  "timestamp": "2026-04-30T14:23:01.234Z",
  "level": "INFO",
  "service": "platform-api",
  "request_id": "req_abc123",
  "run_id": "run_xyz789",
  "user_id": "uuid",
  "module": "writer",
  "event": "module_call_complete",
  "duration_ms": 47312,
  "cost_usd": 0.34,
  "message": "Writer module returned successfully"
}
```

Required fields on every log line:
- `timestamp` (ISO 8601, UTC)
- `level` (`DEBUG` / `INFO` / `WARN` / `ERROR`)
- `service` (`platform-api` or `pipeline-api`)
- `event` (machine-readable event identifier — e.g., `run_dispatched`, `module_call_complete`, `schema_version_mismatch`)
- `message` (human-readable)

Optional but heavily used: `request_id`, `run_id`, `user_id`, `client_id`, `module`, `duration_ms`, `cost_usd`.

### 13.2 Correlation IDs

**Request ID:** generated as a FastAPI middleware on every incoming HTTP request (`req_` + 12-char random base32). Attached to `request.state.request_id`, returned in error responses (Section 5.0), and included in every log line emitted during that request.

**Run ID:** the orchestrator binds the `run_id` to the asyncio context so every log emitted during a run carries it. Use `contextvars.ContextVar` to thread the value through `asyncio.gather()` calls without explicit passing.

```python
# pseudocode
run_id_ctx: ContextVar[str] = ContextVar("run_id", default=None)

class RunIdLogFilter(logging.Filter):
    def filter(self, record):
        record.run_id = run_id_ctx.get()
        return True
```

### 13.3 Log Levels by Event Class

| Level | Used for |
|---|---|
| `DEBUG` | Per-LLM-call payloads, full prompt text, full response bodies. **Disabled in production.** Toggle via `LOG_LEVEL` env var when debugging. |
| `INFO` | Stage transitions (`run_dispatched`, `stage_started`, `stage_complete`, `run_complete`), successful module calls, async job claimed/complete, cache hits, client created/edited |
| `WARN` | Module retry attempts, snapshot text truncation (>150,000 chars), SIE degraded-confidence runs (<5 pages), Writer fallback to `1.5-no-context` or `1.5-degraded`, website scrape failures (run continues without it) |
| `ERROR` | Stage failures, schema version mismatches, banned-term leakage aborts, orchestrator unhandled exceptions, Supabase write failures (after retry exhaustion), authentication failures |

### 13.4 Structured Events to Log

The following events should always be logged at the level shown — engineers should not have to decide ad-hoc:

| Event | Level | Service |
|---|---|---|
| `request_received` | INFO | platform-api |
| `request_complete` | INFO | platform-api |
| `auth_failed` | ERROR | platform-api |
| `client_created` / `client_updated` / `client_archived` | INFO | platform-api |
| `file_uploaded` | INFO | platform-api |
| `file_parse_failed` | ERROR | platform-api |
| `run_dispatched` | INFO | platform-api |
| `stage_started` (per module) | INFO | platform-api |
| `stage_complete` (per module) | INFO | platform-api |
| `stage_failed` (per module) | ERROR | platform-api |
| `module_retry_attempt` | WARN | platform-api |
| `schema_version_mismatch` | ERROR | platform-api |
| `concurrency_limit_hit` | WARN | platform-api |
| `run_cancelled` | INFO | platform-api |
| `startup_recovery_run_failed` | WARN | platform-api |
| `async_job_claimed` | INFO | platform-api |
| `async_job_complete` / `async_job_failed` | INFO / ERROR | platform-api |
| `website_scrape_started` / `website_scrape_complete` / `website_scrape_failed` | INFO / INFO / WARN | platform-api |
| `module_invoked` (per call) | INFO | pipeline-api |
| `module_complete` (per call, with duration and cost) | INFO | pipeline-api |
| `module_failed` (per call) | ERROR | pipeline-api |
| `sie_cache_hit` / `sie_cache_miss` | INFO | pipeline-api |
| `llm_call_failed` | ERROR | pipeline-api |
| `external_api_rate_limited` (DataForSEO, ScrapeOwl, etc.) | WARN | pipeline-api |

### 13.5 What NOT to Log

- **Brand guide / ICP raw text.** May contain confidential client positioning. Log only character lengths and parse status, never content.
- **API keys, JWTs, or credentials.** Never log auth headers, even on auth failures — log only that auth failed.
- **Full LLM prompt text in production.** `DEBUG` level only, and `LOG_LEVEL=INFO` in production.
- **Personally identifiable information.** No emails, names, or addresses in log payloads — use user IDs (UUIDs) only.

### 13.6 Searching Logs (Railway)

Common search patterns engineers will use:

| Goal | Search query |
|---|---|
| All logs for one run | `run_id:run_xyz789` |
| All errors today | `level:ERROR` |
| Schema version mismatches | `event:schema_version_mismatch` |
| Slow Writer calls | `module:writer AND duration_ms:>60000` |
| Failed website scrapes | `event:website_scrape_failed` |
| Specific request a user is asking about | `request_id:req_abc123` (paste from error response) |

### 13.7 Future: External Observability

Out of scope for v1 but worth noting: when run volume passes ~100/day, consider adding a structured-log destination like Better Stack, Axiom, or Datadog. The JSON log format above is portable to any of these — no code changes needed beyond a log shipping config.

---

## 14. Open Items (Engineering Decisions Not Yet Made)

These are scoped down from the PRD's "What This PRD Doesn't Cover" — only items that need an engineering decision before coding starts.

| # | Item | Recommendation |
|---|---|---|
| 1 | HTTP client for platform → pipeline calls | Use `httpx` (async-native, cleaner than `aiohttp` for this use case) |
| 2 | Supabase client in FastAPI | Use `supabase-py` v2 with the service role key on the server side |
| 3 | Background task execution for orchestrator | FastAPI `BackgroundTasks` in v1; upgrade to Celery if run volume grows past 200/day |
| 4 | Polling interval | 5 seconds. Revisit if Railway costs become a concern. |
| 5 | File storage path convention | `files/{user_id}/{uuid}/{original_filename}` — namespaced by uploader |
| 6 | Signed URL TTL for file downloads | 60 minutes (Supabase default) |
| 7 | Module output storage | Store full `input_payload` and `output_payload` as jsonb. At ~50 runs/day and ~50KB per run, storage grows at ~2.5MB/day — negligible for the foreseeable future. |
| 8 | Lovable → TanStack Query setup | Initialize in Lovable's main App component; wrap all routes in `QueryClientProvider` |
| 9 | CORS | Platform API allows CORS from Lovable's domain only |
| 10 | Railway service restart policy | Set to "always restart" for both services |
| 11 | JSON log library | `python-json-logger` for both services; configure once at startup |
| 12 | Request ID middleware | Custom FastAPI middleware that generates `req_` + 12-char base32 ID and attaches to `request.state.request_id` |
| 13 | Module schema version registry location | Hardcoded dict in `platform-api/services/orchestrator.py` (Section 6.5); bumped via PR alongside module updates |

---

## 15. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-04-30 | Initial engineering implementation spec. Covers service topology (2 Railway services), Supabase schema (6 tables + migrations), auth flow, all Platform API routes, orchestration background task pattern, async job worker for website scraping, file parsing, Pipeline API contract, Lovable frontend routes and key components, environment variables, and phased deployment sequence. Based on Platform PRD v1.3 and Writer Module v1.5 Change Spec. |
| 1.1 | 2026-04-30 | Added six review-driven additions: (1) Section 3.4 Storage Buckets — `files` (active) and `article-assets` (placeholder for v2 image generation); (2) Section 5.0 Standard Error Response Format — string-coded errors with `request_id` for log correlation, plus 16-row common error code table; (3) Section 6.5 Module Schema Version Validation — strict-mode registry with no minor-version tolerance, plus three accepted Writer schema versions for fallback paths; (4) Section 9.4 Image References — explicitly out of scope for v1, with the v2 evolution path documented; (5) NewRunForm submit-button debounce documented as the v1 idempotency mechanism (no server-side `Idempotency-Key`); (6) NEW Section 13 Logging & Observability — JSON log format, correlation IDs (request_id and run_id via ContextVar), 25 structured events with mandated log levels, what-not-to-log rules, and Railway log search patterns. Phase 1 deployment sequence updated to use the Supabase CLI workflow with timestamped migration filenames, `supabase link`, `supabase db push`, and local `supabase start` for testing. Open items expanded from 10 to 13 entries covering the new logging/error infrastructure. Version History renumbered from Section 14 to Section 15; Open Items renumbered from 13 to 14. |


---
