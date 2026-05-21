# Topic Fanout Tool — PRD v1.7

**Owner:** Kyle
**Status:** Draft v1.7 — build-ready, repo target finalized
**Date:** 2026-05-20
**Working name:** Fanout (placeholder — confirm before build)
**GitHub repo:** [`kssabraw/info-site-kw-research-cluster`](https://github.com/kssabraw/info-site-kw-research-cluster) — standalone monorepo (backend + frontend in one repo). Currently empty save for a README documenting a 2026-05-21 reset of the previous implementation; this PRD is the basis for the fresh build.
**Railway deployment:** project `AR Tools`, service `info-site-kw-research-cluster` (pre-provisioned)
**Stack:** FastAPI on Railway · Supabase (Postgres + Storage + Auth) shared with AR Tools, isolated under a `fanout` schema · React frontend on Netlify · OpenAI · Anthropic · DataForSEO

---

## 1. What This Is

A **topic-fanout engine for single-topic niche sites**.

The user supplies one seed keyword that represents the subject of an entire niche site (e.g., `retatrutide`). The tool maps the full semantic territory around that subject — subtopics, the keywords inside each subtopic, the questions people ask, the phrases Google autocompletes, and the keywords competitors are quietly ranking for — and returns a clustered, editable content map plus a proposed site architecture (pillar pages + supporting articles + internal linking) that can be reviewed in a browser, edited inline, exported to CSV, or handed off to the Content Brief Generator.

This is not a generic keyword research tool. It assumes:

- The user is building or operating one niche site dedicated to one subject.
- The seed represents the whole site, not a single page.
- The deliverable is a site-wide content plan, not a single-page keyword list.

### Why the previous attempt failed

The last build returned irrelevant keywords. The root cause:

1. Keyword fanout from DataForSEO alone produces volume-neighbors, not concept-neighbors. For a niche like `retatrutide`, volume-neighbors are other GLP-1 drugs, weight loss supplements, and pharmacy spam. The concept-neighbors that actually matter — `triple agonist`, `incretin mimetics`, `GIP/GLP-1/glucagon receptor` — require understanding what the topic *is*, not statistical adjacency to it.
2. Nothing distinguished **peer entities** (`tirzepatide`, `semaglutide`) from **inherent properties** (`triple agonist`). Both land at similar cosine similarity to the seed, but the first dilutes a niche site while the second deepens it.

This PRD fixes both problems with an LLM-driven, web-grounded topic discovery step that operates against an explicit niche-site / topical-authority mission and a structured relationship taxonomy. DataForSEO becomes the expansion engine running underneath each LLM-validated topic, not the source of the topics themselves.

---

## 2. Goals & Non-Goals

### Goals (v1)

- Take one seed keyword and return a hierarchical content map: `seed → N topics → clusters → keywords`, plus a proposed site architecture.
- Make topic discovery genuinely concept-aware and niche-site-aware (not volume-adjacent and not peer-polluted).
- Cover the standard DataForSEO fanout per topic: `keyword_ideas`, `keyword_suggestions`, `query_fanouts`, PAA two tiers deep, autocomplete on every surfaced keyword.
- Mine competitor SERPs on user-selected gated topics for additional ranked-keyword coverage.
- Cluster the final keyword set into editable, page-ready groups.
- Generate a full site architecture: pillar pages, supporting articles, and an internal linking matrix.
- Offer optional volume / CPC / KD enrichment.
- Offer optional recursive fanout (each LLM topic re-runs the pipeline one level deep).
- Provide a SEMrush-quality data table view AND a cluster view, side-by-side toggleable.
- Let the user manually move keywords between clusters, rename clusters, merge, and split.
- Persist sessions under projects so multi-run niche-site planning aggregates correctly.
- Run end-to-end in under 4 minutes per seed at default settings; cost under $2 per run at default.
- Two output paths: live tree/table view in the browser, and CSV export (live-generated from Postgres + snapshot to Supabase Storage on every download).
- Support two distinct user roles (Owner / VA) with different UIs and capability scopes so a VA can do useful work without the risk of running an expensive operation or breaking a session through advanced editing.
- Soft-cap approval workflow: VA-initiated runs above a configurable cost threshold (or any recursive fanout) require Owner approval before the pipeline runs.

### Non-Goals (v1)

- Multi-seed input. One seed per session.
- Multi-tenant client management at the org level. Sessions are tagged by user and grouped under projects, but no per-client billing or permissions.
- Rank tracking. Different tool.
- Competitor URL reverse-engineering as a standalone mode. Competitor mining only operates within the topic-fanout flow.
- Local SEO geo-modifier handling. Different tool (ShowUP Local).
- Auto-generating briefs or articles. Handoff to the Brief Generator is a manual one-click step per cluster.
- Non-English seeds.
- Real-time collaboration on a session (concurrent editing). v1 is single-user-at-a-time per session.

---

## 3. Users & Use Cases

**Owner (primary):** Kyle. Full access to all features, all projects, all sessions across the workspace. Sees the three-view power-user UI (§9). Approves VA runs that exceed the cost cap.

**VA (secondary):** A virtual assistant doing independent keyword research. Picks their own seeds, runs their own sessions, edits their own clusters. Sees a simplified wizard-style UI (§10). Cannot run recursive fanout without approval; cannot run any session estimated above the workspace soft cap without approval. Cannot split/merge clusters, regenerate site architecture, delete sessions, or change the relevance threshold.

A VA's runs become Owner-visible immediately (no "publishing" concept in v1) but only the Owner can promote results downstream into the Brief Generator with confidence, since the VA's editorial decisions on clusters are visible and reviewable.

**Primary use cases:**

1. *Owner:* "I'm starting a niche site about retatrutide. Map every topic, question, and keyword I should cover, and show me what the site architecture should look like."
2. *Owner:* "I've already published 30 articles. Run the seed again, let me see the new clusters, manually mark which ones I've already covered." (Gap-detection auto-diff deferred to v2.)
3. *Owner:* "Send this whole cluster into the Brief Generator so I can start producing articles."
4. *Owner:* "Show me every keyword I've ever pulled for this niche site across all my research sessions." (Project-level aggregation.)
5. *VA:* "Research peptide niches. Pull a topic map for `tirzepatide` and another for `BPC-157`, edit the clusters so they're clean, hand the results back for review."
6. *VA:* "This seed needs comprehensive mode and that puts it over the cap. Submit it for the Owner to approve, then run it when approved."

---

## 4. Input

A research session takes a single seed keyword plus the following settings. Most are optional; only the seed is required.

| Field | Type | Required? | Default | Notes |
|---|---|---|---|---|
| `seed_keyword` | string | Yes | — | Free text. One seed per session. |
| `project_id` | uuid | No | "Scratch" project | Auto-defaulted; user can promote to a named project later. |
| `audience_hint` | string | No | null | Free text describing the intended audience (e.g., `clinicians researching prescribing decisions`, `biohackers buying research peptides`, `homeowners considering installation`). When null, the agent infers audience from the dominant audience in top SERP results during silo discovery. |
| `disambiguation_hint` | string | No | null | Free text disambiguating an ambiguous seed (e.g., for `mercury`: `the chemical element, not the planet or the car brand`). When null, the agent uses the dominant interpretation from grounding search. The grounding step also detects when a seed appears genuinely ambiguous and surfaces a disambiguation prompt to the user before silo discovery proceeds (see §7.1.2). |
| `topic_count` | int (3–10) | No | 5 | How many silos the LLM should propose. |
| `coverage_mode` | enum | No | `standard` | `standard` (top 5 competitor URLs) or `comprehensive` (top 10). |
| `recursive_fanout` | bool | No | false | If true, each LLM topic re-seeds the full pipeline one level deep. |
| `enrich_with_metrics` | bool | No | false | If true, fetch volume / CPC / KD for every surviving keyword. |

No location, no client, no competitor URL, no language toggle. The user picks which topics to deep-mine for competitor keywords *after* silo discovery completes (see §7.2).

**Why these inputs are optional, not required:** the agent can produce useful output from the seed alone for ~80% of real-world niches. The audience and disambiguation hints are escape hatches for the cases where the seed's default interpretation isn't what the user wants. Requiring them up-front would add friction to the common case; making them optional preserves the "just type a seed and go" UX while supporting the harder cases when needed.

---

## 5. The Niche Site Mission

The topic-discovery LLM is given an explicit mission: propose subtopics that a niche site about the seed would need to cover to demonstrate **topical authority**. This is materially different from "propose related topics," and the distinction is what keeps `tirzepatide` from showing up as a topic on a retatrutide-only site.

### 5.1 Relationship taxonomy

Every proposed topic must be tagged with one of the following `relationship_type` values:

| `relationship_type` | Include as topic? | Example for `retatrutide` |
|---|---|---|
| `property_or_mechanism` | Yes | `triple agonist`, `GIP/GLP-1/glucagon receptor` |
| `use_case` | Yes | `retatrutide for weight loss`, `retatrutide for diabetes` |
| `effect_or_outcome` | Yes | `retatrutide side effects`, `retatrutide results timeline` |
| `practical_commercial` | Yes | `retatrutide dosing`, `where to buy retatrutide` |
| `research_or_trial` | Yes | `retatrutide phase 3 trial`, `retatrutide vs placebo` |
| `broader_class` | Conditional — only if niche-strategic; LLM must justify in rationale | `incretin mimetics`, `GLP-1 agonists` |
| `peer_entity` | **No** — filtered before display | `tirzepatide`, `semaglutide` |

Peer entities are not banned from the site content; they're banned from being *topics*. They can still appear inside another topic as comparison content (e.g., `retatrutide vs tirzepatide` lives under `practical_commercial`).

### 5.2 Off-taxonomy handling

Topics returned without a valid `relationship_type` are rejected and the LLM is reprompted (max two attempts). Failed slots are dropped; the final topic count may come back below the requested number, which is surfaced to the user.

---

## 6. Pipeline Overview

```
seed_keyword + settings
   │
   ▼
[1] Silo Discovery (LLM + web grounding + demand sample + competitor structure)
   │     ├─ Grounding search on seed
   │     ├─ DataForSEO keyword_ideas sample (~200 results, no expansion)
   │     ├─ SERP fetch → extract URL path patterns from top 5 domains
   │     ├─ Disambiguation gate (if seed is ambiguous and no hint given)
   │     └─ LLM proposes N silos: {name, rationale, relationship_type,
   │                                supporting_evidence, embedding}
   │
   ▼
[1.5] User Silo Review (UI — mandatory checkpoint)
   │     User can remove proposed silos, add custom silos, edit silo
   │     names/rationales, override audience. Pipeline pauses here.
   │
   ▼
[2] User Deep-Mine Selection (UI)
   │     Seed is always mined. User checks which additional silos
   │     to mine for SERP competitor keywords. Live cost estimate shown.
   │
   ▼
[3] Per-Silo DataForSEO Expansion (all silos, parallel)
   │     ├─ keyword_ideas         (DataForSEO Labs)
   │     ├─ keyword_suggestions   (DataForSEO Labs)
   │     ├─ query_fanouts         (DataForSEO Labs)
   │     └─ People Also Ask, 2 tiers deep (DataForSEO SERP)
   │
   ▼
[4] SERP Competitor Mining (deep-mined silos only)
   │     ├─ DataForSEO SERP → top 5 or top 10 URLs per silo
   │     └─ DataForSEO Labs ranked_keywords → top 20 positions per URL
   │
   ▼
[5] Autocomplete Enrichment
   │     DataForSEO autocomplete for every keyword surfaced so far.
   │
   ▼
[6] Relevance Gate + Dedup
   │     Per-keyword embedding check against parent silo's
   │     (seed + rationale + audience) embedding. Cross-source dedup.
   │     Junk filter.
   │
   ▼
[7] (Optional) Recursive Fanout
   │     If toggle on: each silo becomes a new seed, steps 1–6
   │     re-run one level deep. Cost confirmation gate required.
   │
   ▼
[8] (Optional) Metrics Enrichment
   │     DataForSEO Keyword Data: volume, CPC, KD.
   │
   ▼
[9] Statistical Clustering (intermediate, not user-facing)
   │     Embeddings + NetworkX + Louvain per topic. Produces candidate
   │     groupings as input to the orchestrator.
   │
   ▼
[10] Article Planning (Editorial Orchestrator, per topic + cross-topic dedup)
   │     ├─ Fetch SERPs for candidate primary keywords
   │     ├─ Per-topic LLM call: merge/split/promote-demote/route/drop
   │     │   each statistical grouping; flag coverage gaps
   │     └─ Cross-topic dedup pass to catch collisions
   │
   ▼
[11] Site Architecture Generation (LLM)
   │     Pillar pages (1 per topic) organize the article plans into a
   │     site structure with internal linking.
   │
   ▼
[12] Persist + Render
         Save to Supabase Postgres. Render three views (table / cluster /
         architecture). CSV export on demand, snapshot to Supabase Storage.
```

**Target latency at default settings:** under 300 seconds.
**Target cost at default settings:** under $3.00 per run.

---

## 7. Pipeline Detail

### 7.1 Silo Discovery

The single most important step. Its output is the **top-level structure of the niche site** — the silos, sections, or subfolders that the site will be organized around. Every downstream pipeline step fills these silos with content. If silo discovery returns generic or peer-polluted silos, every downstream API call is wasted.

This step is what we previously called "Topic Discovery"; it's been renamed to reflect what it actually produces: site structure, not just topic ideas. The terms "silo" and "topic" are used interchangeably in this document.

#### 7.1.1 Pre-discovery grounding pass

Before the LLM proposes any silos, three signals are gathered automatically. None of this requires user input beyond the seed; all three feed the silo-proposal prompt as evidence.

| Signal | How it's gathered | Why it matters |
|---|---|---|
| **Subject grounding** | LLM with web search reads top-ranking content for the bare seed. Detects subject category (drug, product, concept, location, etc.) and dominant audience. | Concept-aware silo proposals; baseline for audience inference when `audience_hint` is null. |
| **Search demand sample** | DataForSEO `keyword_ideas` call on the bare seed, ~200 results, no expansion. | Reveals the actual demand landscape so silos reflect what's searched, not just what the LLM thinks should exist. |
| **Competitor URL structure** | DataForSEO SERP on the bare seed → top 5 ranking domains → extract URL path patterns (e.g., `/dosing/`, `/side-effects/`, `/results/`). | Empirical evidence of how successful sites in this niche are structured. Closest available ground truth. |

Combined cost of the pre-discovery pass: ~$0.05. Latency: ~5–10 seconds.

#### 7.1.2 Disambiguation gate

After subject grounding, if the grounding search returns content spanning **two or more disjoint subjects** (e.g., `mercury` returning content about both the planet and the element), the pipeline pauses and surfaces a disambiguation prompt to the user before proceeding.

- The user picks the intended interpretation from a short list of candidates the grounding pass discovered.
- If the user supplied a `disambiguation_hint` at input, it's used directly and no prompt is shown.
- Ambiguity is detected by clustering the grounding content's embeddings: if the top results split into two or more well-separated clusters (silhouette score > 0.5), the seed is flagged as ambiguous.

This is a v1 feature; specific clustering thresholds are tunable during MVP testing (Q16).

#### 7.1.3 Silo proposal

With grounding, search-demand sample, competitor structure, and any user-supplied hints (`audience_hint`, `disambiguation_hint`) all in hand, **GPT-5.4 with browsing** is prompted to propose `topic_count` silos for the niche site. GPT-5.4 was chosen for this step specifically because the silo-discovery work is browsing-bound (it benefits from the model's ability to resolve and read live competitor pages and trade publications during proposal) more than it is structured-output-bound.

The prompt explicitly:

1. States the niche-site mission and topical authority framework.
2. Provides the relationship taxonomy (§5.1) with examples of allowed and forbidden silo types.
3. Provides the gathered evidence: subject grounding summary, top 30 keywords from the demand sample, competitor URL paths.
4. Includes any `audience_hint` (otherwise an inferred audience descriptor from the grounding pass).
5. Asks for `topic_count` silos with name, rationale, relationship_type, and a `supporting_evidence` field that ties each silo back to at least one piece of the gathered evidence (a search-demand keyword cluster, a competitor URL pattern, or an explicit reference to a domain concept).

Each proposed silo:

```json
{
  "name": "triple agonist",
  "rationale": "Retatrutide's defining mechanism — it acts on three receptors (GIP, GLP-1, glucagon). A niche site needs deep coverage of what triple agonism is and why it matters.",
  "relationship_type": "property_or_mechanism",
  "supporting_evidence": "Demand sample shows ~30 keywords on receptor agonism and mechanism. Two of top-5 competitor sites have dedicated /mechanism/ sections.",
  "is_broader_class": false
}
```

Off-taxonomy returns are reprompted once. Peer entities are filtered. Broader-class silos are tagged `is_broader_class: true` and surfaced to the user with a visual flag in the next step.

#### 7.1.4 User silo review and editing

After silo proposals are generated, the pipeline **pauses** and presents the proposed silos to the user for review before any downstream API calls run. This is a new mandatory step in v1.3 (previously this was conflated with §7.2).

The review screen shows:

- Each proposed silo with its name, rationale, relationship_type, and supporting_evidence.
- A visual flag on any `is_broader_class` silo with a tooltip explaining the conditional inclusion.
- The detected audience (either the user's `audience_hint` or the agent's inference).

User actions on this screen:

| Action | Notes |
|---|---|
| **Remove silo** | Click an X on any proposed silo to drop it. Final count may go below the original `topic_count`. |
| **Add custom silo** | "+ Add silo" button opens a small form: name (required), rationale (optional but recommended), relationship_type (dropdown from §5.1, defaults to `property_or_mechanism`). User-added silos are tagged `source: user_added` and skip the LLM's taxonomy validation (the user is asserting it belongs). |
| **Edit silo name or rationale** | Inline edit. Triggers re-embedding when saved. |
| **Override audience** | Free-text override of the detected audience. Used by downstream LLM calls (orchestrator, architecture) for tone and content-angle decisions. |
| **Continue** | Locks the silo list and proceeds to §7.2 (deep-mine selection) with the final silo set. |

Once the user clicks Continue, each finalized silo is embedded with `text-embedding-3-small` against `seed + " " + rationale + " " + audience` (audience appended so downstream relevance filters are audience-aware). The embedding becomes the per-silo relevance anchor used in every downstream filter.

**Why seed-plus-rationale-plus-audience rather than just the silo name:** the name alone is brittle (`triple agonist` is lexically distant from `retatrutide`); the expanded string gives the embedding model the semantic surface area it needs to produce a robust anchor for downstream filtering, and including audience prevents an audience drift where, e.g., consumer-focused content slips into a clinician-targeted site.

### 7.2 User Deep-Mine Selection

After silo review (§7.1.4) completes, the UI presents the second user gate: **which silos to deep-mine for competitor keywords.** The seed itself is always mined. Two to three additional silos is the recommended budget; a live cost estimate updates as boxes are checked.

### 7.3 Per-Topic DataForSEO Expansion

For every accepted topic, three Labs endpoints and one SERP endpoint run in parallel:

| Endpoint | Purpose | Approx. yield per topic |
|---|---|---|
| `keyword_ideas` | Broad ideation around the topic anchor | 500–1,000 |
| `keyword_suggestions` | Phrase-match suggestions | 200–500 |
| `query_fanouts` | Long-tail variations | 100–300 |
| SERP → People Also Ask, 2 tiers deep | Question-based discovery | 20–50 |

For PAA two tiers deep: top-level PAA returns ~4–8 questions per topic; each of those is treated as a seed for a second PAA call, returning ~4–8 more each. This compounds quickly; cap the tier-2 fanout at 40 questions per topic to bound cost and latency.

### 7.4 SERP Competitor Mining (gated topics only)

For each topic the user checked in step 7.2:

1. Run a DataForSEO SERP on the topic's anchor keyword.
2. Pull the top 5 URLs (`standard` mode) or top 10 (`comprehensive` mode).
3. For each URL, call `ranked_keywords` and pull keywords where that URL ranks in positions 1–20.

Yield per URL: roughly 200–500 ranked keywords. At default (3 gated topics × 5 URLs = 15 URLs), this single step contributes 3,000–7,500 raw keywords — typically the largest single contributor to the candidate pool.

### 7.5 Autocomplete Enrichment

After 7.3 and 7.4 complete, the unique keyword set is passed to DataForSEO's autocomplete endpoint, one call per keyword. Autocomplete is the cheapest endpoint (~$0.0006/call) so this scales to ~1,000–2,000 keywords per run.

### 7.6 Relevance Gate + Dedup

The volume control point. Every keyword that has reached this stage is checked against its parent topic's `seed + rationale` embedding using cosine similarity.

- **Threshold:** 0.62 default. Tunable per-run during v1 testing; locked once a stable value is found.
- **Cross-source dedup:** normalize whitespace, casing, trailing punctuation; merge duplicates while preserving source-attribution metadata (so the user can see whether a keyword came from PAA, autocomplete, competitor mining, etc.).
- **Junk filter:** drop pure brand names not connected to the seed, blocked tokens (porn / gambling / etc.), or keywords failing min/max length sanity check.

Keywords that fail the relevance gate are stored in Postgres tagged as `filtered_relevance` so they can be reviewed and reinstated during v1 calibration.

### 7.7 Recursive Fanout (optional)

If `recursive_fanout` is true, each accepted topic from 7.1 becomes a new seed and steps 7.1–7.6 re-run one level deep. Depth is hard-capped at one to prevent runaway cost.

**Cost multiplier:** 5×–8× the non-recursive run. **Cost confirmation gate triggers automatically** when the toggle is on (see §8.4).

### 7.8 Metrics Enrichment (optional)

If `enrich_with_metrics` is true, the surviving keyword set is sent to DataForSEO's Keyword Data endpoints for volume, CPC, KD. Batched in groups of 1,000.

### 7.9 Statistical Clustering

**This step produces candidate groupings, not articles.** The output is an intermediate signal that feeds the editorial orchestrator in §7.10. It is not directly user-facing.

Same machinery as Content Brief Generator v2.0:

- Embed every surviving keyword with `text-embedding-3-small`.
- Build a NetworkX graph per topic; edges weighted by cosine similarity above 0.55.
- Run Louvain community detection to extract candidate groupings.
- Apply MMR to pick a representative keyword per grouping.

**Clustering is scoped within each topic** — a candidate grouping never spans two topics.

The output of this step is persisted in the session's `statistical_clustering_log` jsonb field for debugging and re-runnability, but is never shown to the user as a final answer. The user sees only the article plan produced by §7.10.

### 7.10 Article Planning (Editorial Orchestrator)

**This is the step that does the work you actually want when you say "cluster."** It takes each topic's statistical groupings and converts them into a plan of articles, with editorial judgment about which keywords share a URL, which need their own, and how they interlink.

The orchestrator is **Claude Opus 4.7** with a clearly bounded job, run once per topic. Opus 4.7 was chosen for this step because the orchestrator's work is structured-reasoning-bound — merge/split/promote-demote decisions against a strict JSON schema — where Opus's tool-use mode with strict schemas reliably enforces output shape. The orchestrator does not need browsing; all the evidence it operates on (SERPs, embeddings, keyword pool) is already in its prompt context.

#### 7.10.1 Inputs to the orchestrator

For one topic, the orchestrator receives:

1. **Topic context** — name, rationale, relationship_type.
2. **Statistical groupings** for that topic — each grouping with its keywords, the MMR-selected representative, and the within-grouping cohesion score (mean pairwise cosine similarity).
3. **SERP data for each candidate primary keyword** — top 10 ranking URLs. The MMR-selected representative of each statistical grouping is treated as a "candidate primary keyword" and a SERP fetch is run for each. This is a new SERP cost line in §8.
4. **Intent inference** — the orchestrator infers intent from the SERP composition itself (product pages → transactional, comparison articles → comparison, how-to / explainer content → informational, etc.). No separate intent-classification pass is needed.
5. **Volume data** — if `enrich_with_metrics` ran. Used for the promote/demote decision.

#### 7.10.2 The orchestrator's decisions

For each statistical grouping the orchestrator returns one of these outcomes:

| Outcome | Trigger | Result |
|---|---|---|
| **Merge into one article** | Keywords share intent AND top-3 SERP URLs overlap ≥ 3/10 across the grouping AND the grouping is topically cohesive | One article record. Primary = the highest-volume or highest-cohesion keyword. The rest become supporting keywords. |
| **Split into N articles** | Keywords cluster statistically but have distinct intents OR SERP overlap < 2/10 between sub-groups | N article records, one per sub-group. Orchestrator decides the split lines. |
| **Promote + demote** | One broad keyword has volume; several narrow children lack standalone volume but share its SERP space | One article with the broad keyword as primary; narrow children become suggested H2s. |
| **Route to another grouping** | Keyword is semantically similar but editorially belongs in a different grouping within the same topic | Move keyword's grouping assignment before article planning runs on the receiving grouping. |
| **Drop** | Keyword doesn't justify article-level treatment (no volume, no SERP traction, off-niche) | Tagged `status: dropped_by_orchestrator` with reason. Stored, not deleted. |

Plus, at the topic level, the orchestrator flags:

- **Coverage gaps** — article concepts that should exist for topical authority but don't appear in the topic's groupings. Each flagged gap includes a suggested article title, a target keyword, and the rationale.

#### 7.10.3 Output schema

The orchestrator returns a list of **article records** per topic, each:

```json
{
  "primary_keyword": "how does retatrutide work",
  "supporting_keywords": ["retatrutide mechanism", "retatrutide mode of action", ...],
  "intent": "informational",
  "suggested_h2s": [
    "What is retatrutide?",
    "The three receptors retatrutide targets",
    "How triple agonism produces weight loss",
    "What happens in the body after injection"
  ],
  "peer_article_links": ["uuid-of-peer-article-1", "uuid-of-peer-article-2"],
  "parent_topic_id": "uuid",
  "source_statistical_grouping_id": "uuid",
  "orchestrator_notes": "Merged from 1 grouping; SERP overlap 6/10 across keywords."
}
```

Plus the gap list:

```json
[
  {
    "suggested_title": "Retatrutide long-term safety",
    "target_keyword": "retatrutide long term effects",
    "rationale": "Topical-authority sites about prescription drugs require explicit long-term-use coverage. No grouping surfaced for this; recommend creating a placeholder article."
  }
]
```

#### 7.10.4 Cross-topic dedup pass

After all five topic-level orchestrators complete, a **single final pass** runs across the full article set to catch cross-topic collisions:

1. Embed every article's primary keyword.
2. Find pairs of articles across topics with primary-keyword cosine similarity > 0.85 OR top-3 SERP overlap ≥ 2/3.
3. For each collision:
   - Assign the article to whichever parent topic gives a higher relevance score (cosine similarity of primary keyword to topic's `seed + rationale` embedding).
   - The losing topic gets a `peer_article_link` to the winning article instead of its own duplicate.
4. Log all dedup decisions for review.

The cross-topic dedup is a single LLM call with the full article set; cost ~$0.10.

#### 7.10.5 Why this fixes the perceived "irrelevant keywords" problem

Statistical clustering alone produces groupings where `retatrutide dosing schedule`, `how much retatrutide to take`, and `retatrutide weight loss results` can end up together (they share the seed and embed nearby). The user opens the result and sees an incoherent grouping and concludes the keywords are irrelevant. They're not — they just don't belong on the same article.

The orchestrator catches this. SERP overlap between `retatrutide dosing schedule` and `retatrutide weight loss results` is low (different ranking pages), intent differs (one is practical-procedural, the other is outcome-informational), so the orchestrator splits them into separate articles. The user opens the result and sees coherent article plans, each with keywords that genuinely belong together.

### 7.11 Site Architecture Generation

The final pipeline step. After article planning completes, **Claude Opus 4.7** is given the full structure (seed → topics → article plans → linking graph) and asked to propose the site-level architecture. Opus 4.7 was chosen for this step for the same reason as the orchestrator: structured editorial reasoning under a strict output schema. Architecture generation and orchestration share the same LLM client and credentials in the service.

- **One pillar page per topic.** Working title, target keyword, summary of what the pillar covers. The pillar is *separate* from the supporting articles produced by article planning — it's a higher-level overview page that links down to them.
- **Supporting articles** are the articles already planned by §7.10. The architecture step does not re-plan them; it organizes them.
- **Internal linking matrix:**
  - Every supporting article links *up* to its pillar (mandatory).
  - Every pillar links *down* to all its supporting articles (mandatory).
  - Each supporting article gets 2–3 *lateral* links to peer supporting articles, prioritizing the `peer_article_links` already set by the orchestrator.
  - Pillars link laterally to other pillars where topic embedding similarity > 0.55.

Approximate cost: $0.20–$0.50 per run. The architecture is stored as a structured JSON object alongside the article data and rendered in the Architecture View (§9.3).

---

## 8. Cost & Latency

### 8.1 Cost matrix (estimated)

| Step | Standard mode | Comprehensive mode | Recursive (added on top) |
|---|---|---|---|
| Silo discovery: LLM grounding + keyword_ideas sample + SERP structure | $0.20 | $0.20 | $1.00 (5×) |
| Per-silo expansion (5 silos × 4 endpoints) | $0.55 | $0.55 | $2.75 |
| SERP competitor mining (3 gated silos) | $0.50 | $0.95 | $2.50 |
| Autocomplete enrichment | $0.30 | $0.60 | $1.50 |
| Relevance gate + dedup (embeddings) | $0.05 | $0.10 | $0.25 |
| Statistical clustering (compute only) | — | — | — |
| SERP fetch for orchestrator candidate primaries | $0.30 | $0.50 | $1.50 |
| Article planning orchestrator (5 silo-level calls) | $0.50 | $0.50 | $2.50 |
| Cross-topic dedup pass (1 call) | $0.10 | $0.10 | $0.10 |
| Site architecture generation | $0.30 | $0.30 | $0.30 |
| Metrics enrichment (if toggle on) | +$0.30 | +$0.60 | +$1.50 |
| **Subtotal (metrics off)** | **~$2.80** | **~$3.80** | **~$14.65** |
| **Subtotal (metrics on)** | **~$3.10** | **~$4.40** | **~$16.15** |

The silo-discovery step is slightly more expensive in v1.3 (was $0.15, now $0.20) due to the added `keyword_ideas` sample and SERP-structure scrape. The quality gain — silos grounded in actual demand and competitor structure rather than pure LLM intuition — is worth the $0.05.

All numbers are estimates based on current DataForSEO and OpenAI pricing. Real numbers will surface during MVP testing; update this table after the first 10 production runs.

### 8.2 Latency target

| Mode | Target end-to-end |
|---|---|
| Standard, metrics off | < 240 s |
| Standard, metrics on | < 300 s |
| Comprehensive, metrics on | < 360 s |
| Recursive fanout | < 20 min |

The article-planning step adds roughly 30–60 seconds to every run (5 sequential LLM calls plus the dedup pass; per-topic calls can run in parallel to recover most of this).

Recursive fanout is intentionally a "go get coffee" operation. UI must indicate this clearly.

### 8.3 Yield (estimated)

| Mode | Raw keywords | After relevance gate | After article planning |
|---|---|---|---|
| Standard | 5,000–8,000 | 1,500–2,500 | 25–50 articles |
| Comprehensive | 8,000–15,000 | 2,500–4,500 | 40–80 articles |
| Recursive (standard base) | 25,000–50,000 | 8,000–15,000 | 150–300 articles |

Article counts are lower than statistical-cluster counts in v1.0 / v1.1 because the orchestrator merges, drops, and demotes — which is the point. A "cluster" in the v1.2 sense is one publishable article on the site.

### 8.4 Cost confirmation gate

The UI shows a live cost estimate as the user adjusts inputs.

**For Owner sessions:**
When the estimate exceeds **$6.00**, a confirmation modal blocks the run until the Owner explicitly confirms. Below $6, the run proceeds without friction. (Threshold raised from v1.1's $5.00 since base costs are now higher with the orchestrator step.)

**For VA sessions:**
A configurable workspace **soft cap** (default **$5.00** — set so that standard mode with metrics, comprehensive mode with metrics, and most non-recursive runs all pass without approval; only recursive fanout and unusually expensive sessions require it) applies. Sessions estimated *at or below* the cap run immediately. Sessions estimated *above* the cap, OR any session with `recursive_fanout: true` regardless of cost, trigger the approval workflow detailed in §11.3 — the session is created with `status: pending_approval` and the pipeline does not start until the Owner approves it.

In both cases, the estimate is non-binding. A banner during execution shows real cost accumulated so far, and the user can cancel at any pipeline stage. Cancelled runs are still persisted (with the partial data collected) and tagged `status: cancelled`.

---

## 9. UI — Owner Mode

The Owner-facing UI is built around **three views of the same data**, switchable from a top-of-page segmented control. The VA-facing UI is a separate wizard-style flow detailed in §10.

1. **Table View** — SEMrush Keyword Magic Tool style.
2. **Cluster View** — SEMrush Keyword Strategy Builder style.
3. **Architecture View** — proposed site map and internal linking.

The user can also enter **Split View** mode, which puts Table and Cluster side-by-side (desktop only; mobile defaults to single-view tabs).

### 9.1 Table View

A sortable, filterable data table of every surviving keyword.

**Columns:**

| Column | Notes |
|---|---|
| Keyword | Free-text |
| Topic | The parent topic from §7.1 |
| Cluster | The cluster ID/name from §7.9 |
| Source | One or more of: `keyword_ideas`, `keyword_suggestions`, `query_fanouts`, `paa_t1`, `paa_t2`, `autocomplete`, `competitor` |
| Volume | If metrics enrichment ran |
| KD | If metrics enrichment ran |
| CPC | If metrics enrichment ran |
| Relevance | Cosine similarity to parent topic embedding |
| Status | `active` / `excluded` / `covered` |

**Filters:**

- By topic (multi-select)
- By cluster (multi-select)
- By source (multi-select)
- By volume range (slider)
- By KD range (slider)
- By keyword length: short-tail (1–2 words) / mid-tail (3–4) / long-tail (5+)
- By question vs non-question (boolean)
- Free-text keyword search

**Bulk actions on selected rows:**

- Move to different cluster
- Exclude (sets status = excluded; keyword stays in DB but hides from default view)
- Mark as covered (status = covered; useful for tracking what's already on the site)
- Export selected to CSV

### 9.2 Cluster View

The "cluster" in the UI is the **article unit** produced by the orchestrator (§7.10) — one cluster = one planned article on the site. The view groups articles by their parent topic.

```
▼ Topic: Triple Agonist  [property_or_mechanism]  [12 articles]
    ▼ Article: How triple agonism works  [informational]
        Primary:    how does triple agonist work
        Supporting: what is a triple agonist, triple agonist mechanism, ...  [11 kws]
        H2 outline: What is a triple agonist · The three receptors · How agonism
                    produces weight loss · What happens after injection
        Links to:   Receptor binding pharmacology, GIP receptor specifically
    ▶ Article: Triple agonist vs dual vs single agonist  [comparison]
    ▶ Article: Receptor binding pharmacology  [informational]
    ▶ ⚠ Gap: Long-term mechanism implications [flagged by orchestrator]
▶ Topic: Practical & Commercial  [practical_commercial]  [9 articles]
```

The orchestrator's flagged **coverage gaps** appear inline as their own placeholder rows, visually distinguished. The user can accept a gap (which creates an empty article placeholder for the Brief Generator to fill in) or dismiss it.

**Cluster editing actions (Owner only — VAs see a restricted subset per §10):**

- **Rename article** — inline edit on the article header.
- **Edit H2 outline** — inline edit on the suggested H2s.
- **Edit intent label** — dropdown on the article row.
- **Move keyword** — drag-and-drop a keyword onto a different article (desktop), or select keyword(s) + "Move to..." action (mobile-friendly).
- **Promote a supporting keyword to primary** — click any supporting keyword → "Make primary." The current primary becomes supporting.
- **Merge articles** — multi-select two or more articles → "Merge" → user confirms the merged article name, primary keyword, and combined H2 outline.
- **Split article** — select an article → "Split" → modal lets the user either (a) manually select which keywords go into the new article, or (b) re-run the orchestrator on just this article's keywords with a stricter SERP-overlap threshold.
- **Delete article** — moves all keywords to a special "Unassigned" bucket within the same topic. Keywords are never destroyed.
- **Accept gap / Dismiss gap** — explicit user decision on orchestrator-flagged coverage gaps.
- **Re-run orchestrator** — explicit Owner action to re-run §7.10 for a single topic or for the whole session, useful after manual keyword edits.

All edits write immediately to Postgres. The orchestrator does not re-run automatically on edits.

### 9.3 Architecture View

A two-panel layout:

- **Left:** site map tree — pillars at level 1, supporting articles at level 2, with cluster names and keyword counts.
- **Right:** detail pane for the selected node — working title, target keyword, suggested H2 outline (for supporting articles) or covered topics (for pillars), and the **internal linking matrix** showing what links to and from this page.

Each node has a **"Send to Brief Generator"** button that hands off the relevant cluster's keywords plus the proposed title and H2 outline.

The architecture is regeneratable on demand (one-click "Regenerate architecture" button that re-runs §7.11 with the current edited clusters as input).

### 9.4 Project + Session Browser

A left-rail navigation lists all projects, with sessions nested under each.

- **Scratch project** is always present and contains any sessions that weren't assigned to a named project.
- Sessions display: seed keyword, created date, mode (standard/comprehensive/recursive), cluster count, status.
- Right-click / long-press on a session → move to another project, duplicate, archive, delete.
- Project-level view aggregates all sessions: union of keywords across runs, deduped by exact match, with a "first seen in session X" column for traceability.

---

## 10. UI — VA Mode

The VA-facing UI is a linear wizard, not a dashboard. The flow strips out every power-user feature that doesn't serve someone running a routine keyword research task, and locks in sensible defaults for everything else. A VA logging in goes straight into the wizard; they cannot navigate into Owner-mode views.

### 10.1 Wizard Flow

```
Step 1: Pick or create project
Step 2: Enter seed keyword (+ optional audience and disambiguation hints)
Step 3: Choose run settings (most are locked)
Step 4: (If seed is detected as ambiguous) Disambiguation prompt
Step 5: Review proposed silos (remove, add custom, edit, override audience)
Step 6: Pick which silos to deep-mine
Step 7: Cost confirmation (or approval request)
Step 8: Progress screen
Step 9: Results — simplified two-view
```

### 10.2 Step Detail

**Step 1 — Project.** Dropdown of projects the VA owns or has access to, plus a "+ New project" option and a default "Scratch (VA name)" project. No access to projects owned only by the Owner unless explicitly shared.

**Step 2 — Seed and optional hints.** Single text input for the seed. Two collapsed-by-default optional fields beneath it:
- *"Audience (optional)"* — free text. Hidden by default behind a "Specify audience" link.
- *"Disambiguation (optional)"* — free text. Hidden by default behind a "Seed is ambiguous?" link.

Real-time validation on the seed (non-empty, max length, English-only check).

**Step 3 — Run settings.** Only two controls are visible:
- `topic_count` — slider, 3 to 10, default 5.
- `coverage_mode` — toggle: `standard` (free) or `comprehensive` (may exceed cap).

Hidden / locked for VAs:
- `recursive_fanout` — not exposed in the UI. Available only via explicit approval request (see §11.3).
- `enrich_with_metrics` — locked **on** by default for VAs, since the VA's primary deliverable benefits from having volume/KD/CPC in the output.
- Relevance threshold — locked at workspace default (0.62).

**Step 4 — Disambiguation (conditional).** If the grounding pass detects an ambiguous seed and no `disambiguation_hint` was provided, the VA picks the intended interpretation from a short list. Skipped entirely when the seed is unambiguous or the hint was provided.

**Step 5 — Silo review.** All proposed silos are shown with name, rationale, relationship_type, and supporting evidence. The detected audience is shown at the top of the screen. VA actions:
- Remove any silo (drop with confirmation if it brings the count below 3).
- Add a custom silo via "+ Add silo" (name + optional rationale + relationship_type dropdown).
- Edit any silo name or rationale inline.
- Override the detected audience via inline edit.

If too many silos are removed (< 3 remaining), Next is disabled with a tooltip explaining why.

**Step 6 — Deep-mine selection.** VA picks which silos get SERP competitor mining. Capped at **seed + 2 additional silos maximum** in VA mode (Owner mode allows all silos). Live cost estimate updates as boxes are checked.

**Step 7 — Cost confirmation.**
- If estimate ≤ workspace soft cap: a single "Run now" button.
- If estimate > soft cap, OR `recursive_fanout` requested: a "Submit for approval" button. Clicking creates the session at `status: pending_approval`; the VA lands on a "Waiting for approval" screen with the option to cancel the request.

**Step 8 — Progress.** Step-by-step status indicator (Silo discovery → Expansion → Mining → Autocomplete → Filtering → Clustering → Article Planning → Architecture). Estimated time remaining. Live cost accumulator. Cancel button.

**Step 9 — Results.** A simplified two-view interface:

- **Table view** — same columns as Owner mode, but advanced filters are collapsed by default and the bulk-actions menu only exposes: Move to cluster, Mark as covered, Export selected. (No "Exclude," no "Tag.")
- **Cluster view** — same as Owner mode, but cluster-level actions are restricted to **Rename** and **Move keyword in/out**. No Split, no Merge, no Delete cluster. A "Request restructure from Owner" button lets the VA flag a cluster that needs editorial intervention.

The Architecture view is **read-only** for VAs (they can see the proposed pillars and supporting articles but cannot regenerate or edit). The "Send to Brief Generator" button is enabled per-cluster.

### 10.3 What VAs Cannot Access

- Owner-mode three-view interface, split-view, or any view of sessions outside their projects.
- Recursive fanout (only via approval request).
- Cluster split / merge / delete.
- Relevance threshold adjustment.
- Site architecture regeneration.
- Session or project deletion.
- Workspace settings (soft cap value, default LLM, etc.).
- Approval queue for other VAs.
- Cost data for any sessions other than their own.

---

## 11. Roles, Permissions & Approval Workflow

### 11.1 Roles

Two roles in v1:

- **`owner`** — full workspace access. Sees §9 Owner UI. Manages workspace settings. Approves/rejects VA requests.
- **`va`** — restricted access. Sees §10 VA wizard. Independent research within their own projects, subject to cost cap and capability restrictions.

Role is stored on a `user_profiles` row keyed to `auth.users.id`. There is exactly one Owner in v1; multiple VAs are supported.

### 11.2 Capability Matrix

| Capability | Owner | VA |
|---|---|---|
| Create session in own projects | ✓ | ✓ |
| Create new project | ✓ | ✓ |
| View sessions in projects owned by another user | ✓ (all) | ✗ (only if explicitly shared) |
| Run `standard` mode | ✓ | ✓ |
| Run `comprehensive` mode | ✓ | ✓ if under cap, else request approval |
| Run `recursive_fanout` | ✓ (with cost confirm above $5) | ✗ — always requires approval |
| Run `enrich_with_metrics` | ✓ | ✓ (locked on by default) |
| Adjust `topic_count` | ✓ | ✓ |
| Adjust relevance threshold | ✓ | ✗ |
| Edit clusters (move keywords, rename) | ✓ | ✓ |
| Split / merge / delete clusters | ✓ | ✗ — request restructure only |
| Regenerate site architecture | ✓ | ✗ (read-only view) |
| Delete session | ✓ | ✗ |
| Delete project | ✓ | ✗ |
| Export CSV | ✓ | ✓ |
| Send cluster to Brief Generator | ✓ | ✓ |
| Approve VA requests | ✓ | ✗ |
| View cost data | ✓ (all sessions) | ✓ (own sessions only) |
| Change workspace soft cap | ✓ | ✗ |
| Promote a user from VA → Owner | ✗ (manual DB change in v1) | ✗ |

### 11.3 Approval Workflow

A run requires approval when **either** of these is true:
- Estimated cost exceeds the workspace soft cap (default $3.00, configurable by Owner).
- `recursive_fanout` is requested.

**Flow:**

1. VA configures a run that meets one of the trigger conditions.
2. VA clicks "Submit for approval." Backend creates the session with `status: pending_approval` and stores the settings + cost estimate. Pipeline does not start.
3. Owner receives an in-app notification (badge on the "Approvals" nav item; count of pending requests). Optional: email notification if the Owner is offline (v1.1 stretch; spec'd as a flag in §15).
4. Owner opens the Approvals queue, sees a row per pending request with: VA name, project, seed keyword, settings, cost estimate, time submitted.
5. Owner clicks a row → modal opens with full settings detail and two buttons: **Approve** and **Reject**. Optional note field on both.
6. **On Approve:** session moves to `status: running`, pipeline kicks off immediately. VA is notified in-app. The Owner's approval is recorded on the session (`approval_decided_by_user_id`, `approval_decision_at`).
7. **On Reject:** session moves to `status: rejected`. VA is notified in-app with the optional note. VA can clone the session into a new draft, adjust settings, and resubmit.

**Concurrency note:** the Approvals queue is small (~handfuls of items, not hundreds). v1 polls every 30 seconds when the Owner has the Approvals view open. Real-time push (websockets / Supabase Realtime) is deferred to v2.

### 11.4 Workspace Settings

A single workspace-level settings record stores:

| Setting | Default | Owner-editable |
|---|---|---|
| `va_soft_cap_usd` | 5.00 | ✓ |
| `owner_cost_confirm_threshold_usd` | 6.00 | ✓ |
| `default_relevance_threshold` | 0.62 | ✓ |
| `silo_discovery_model` | `gpt-5.4` (with browsing) | ✓ |
| `orchestrator_model` | `claude-opus-4-7` | ✓ |
| `architecture_model` | `claude-opus-4-7` | ✓ |
| `default_embedding_model` | `text-embedding-3-small` | ✓ |

Workspace settings are global; this is a single-tenant deployment (Kyle + team), not multi-tenant SaaS.

---

## 12. CSV Export & Storage

CSV downloads work as follows:

- **The user clicks "Download CSV"** on any view or selection.
- **Postgres generates the CSV live** from the current state of the data (including any user edits to clusters, exclusions, etc.).
- **The generated CSV is written to Supabase Storage** under `csv-snapshots/{user_id}/{session_id}/{timestamp}.csv` and the download is served from there.
- An entry is added to a `csv_exports` table tracking who generated which export when.

This means:

- The live UI always reads from Postgres (no stale data).
- Every download produces a frozen historical snapshot in Storage for audit / sharing.
- Past snapshots are listed in a session's "Exports" tab and can be re-downloaded.

**Three CSV formats are offered:**

1. **Flat keyword list** — one row per keyword, all columns from the Table View.
2. **Topic-grouped** — one CSV per topic, useful for sharing one section of the site with a freelancer.
3. **Site architecture** — one row per page (pillar or supporting article), with columns: `page_type`, `title`, `target_keyword`, `parent_pillar`, `outline_h2s`, `internal_links_out`.

---

## 13. Data Model (Supabase Postgres)

Simplified schema; field types and indexes finalized at build time.

### `projects`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK to auth.users |
| `name` | text | "Scratch" is the auto-created default per user |
| `is_scratch` | bool | True only for the auto-Scratch project |
| `created_at` | timestamp | |

### `sessions`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `project_id` | uuid | FK to projects |
| `user_id` | uuid | FK to auth.users |
| `seed_keyword` | text | |
| `audience_hint` | text | nullable; user-provided at input |
| `disambiguation_hint` | text | nullable; user-provided at input |
| `detected_audience` | text | The audience inferred during silo discovery (or `audience_hint` if provided); used by downstream LLM calls |
| `disambiguation_choice` | text | nullable; the interpretation selected at the disambiguation gate, if triggered |
| `settings` | jsonb | `topic_count`, `coverage_mode`, `recursive_fanout`, `enrich_with_metrics` |
| `status` | enum | `pending_approval` / `rejected` / `running_pre_review` / `awaiting_silo_review` / `running` / `complete` / `cancelled` / `error` |
| `estimated_cost_usd` | numeric | Computed at submission, used by the approval gate |
| `actual_cost_usd` | numeric | Tracked live as pipeline runs |
| `approval_required` | bool | True if cost exceeded VA cap OR `recursive_fanout` was on |
| `approval_decided_by_user_id` | uuid | FK to auth.users; null until decided |
| `approval_decision_at` | timestamp | null until decided |
| `approval_note` | text | Optional note from Owner on approve/reject |
| `statistical_clustering_log` | jsonb | Raw Louvain output before orchestrator transformation; for debugging |
| `orchestrator_log` | jsonb | Per-topic orchestrator decisions (merge/split/drop) with rationales; for debugging |
| `created_at` | timestamp | |
| `completed_at` | timestamp | |

### `topics`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `session_id` | uuid | FK to sessions |
| `name` | text | |
| `rationale` | text | |
| `relationship_type` | enum | From taxonomy in §5.1 |
| `supporting_evidence` | text | LLM's evidence tying the silo back to demand sample or competitor structure; null for user-added silos |
| `source` | enum | `llm_proposed` / `user_added` / `llm_proposed_then_user_edited` |
| `is_broader_class` | bool | Visual flag on `relationship_type: broader_class` silos |
| `embedding` | vector(1536) | pgvector; computed against `seed + rationale + detected_audience` |
| `is_gated_for_competitor_mining` | bool | |

### `clusters` (article units, produced by the orchestrator)
The `clusters` table is the canonical user-facing unit — one row per planned article. Despite the legacy name, a row here represents an article plan, not a raw statistical grouping.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `topic_id` | uuid | FK to topics |
| `name` | text | Article title; auto-generated from primary keyword, user-editable |
| `primary_keyword_id` | uuid | FK to keywords; the chosen primary for the article |
| `intent` | enum | `informational` / `commercial` / `transactional` / `comparison` / `navigational` |
| `suggested_h2s` | text[] | Orchestrator-proposed H2 outline, user-editable |
| `peer_article_links` | uuid[] | FKs to peer `clusters.id` for lateral internal linking |
| `source_statistical_grouping_id` | uuid | The Louvain grouping this article was derived from; for debugging |
| `orchestrator_notes` | text | The orchestrator's rationale for the merge/split/promote decision |
| `is_user_edited` | bool | True if the user has manually modified this article |
| `is_gap_placeholder` | bool | True if this was created from an accepted coverage gap (no source keywords yet) |
| `centroid_embedding` | vector(1536) | Recomputed on edit; used by cross-topic dedup |

### `keywords`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `session_id` | uuid | FK to sessions (denormalized for fast project-level aggregation) |
| `topic_id` | uuid | FK to topics |
| `cluster_id` | uuid | FK to clusters (nullable; null = "Unassigned" bucket within the topic) |
| `keyword` | text | |
| `sources` | text[] | One or more source tags |
| `serp_top_urls` | text[] | Top 10 URLs from SERP, populated for primary-candidate keywords (used by orchestrator) |
| `is_primary_for_cluster` | bool | True if this is the cluster's primary keyword |
| `volume` | int | nullable |
| `cpc_usd` | numeric | nullable |
| `kd` | int | nullable |
| `relevance_score` | numeric | Cosine similarity to parent topic embedding |
| `status` | enum | `active` / `excluded` / `covered` / `filtered_relevance` / `filtered_junk` / `dropped_by_orchestrator` |
| `orchestrator_drop_reason` | text | Populated when `status = dropped_by_orchestrator` |

### `coverage_gaps`
Orchestrator-flagged gaps that the user can accept (creating a placeholder cluster) or dismiss.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `topic_id` | uuid | FK to topics |
| `suggested_title` | text | |
| `target_keyword` | text | |
| `rationale` | text | Orchestrator's reason for flagging |
| `status` | enum | `pending` / `accepted` / `dismissed` |
| `accepted_cluster_id` | uuid | FK to clusters; populated when status = accepted |

### `site_architecture`
| Column | Type | Notes |
|---|---|---|
| `session_id` | uuid | FK to sessions; one architecture per session |
| `architecture_json` | jsonb | Full pillar/supporting/links structure |
| `generated_at` | timestamp | |
| `is_user_edited` | bool | |

### `csv_exports`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `session_id` | uuid | FK to sessions |
| `user_id` | uuid | FK to auth.users |
| `format` | enum | `flat` / `topic_grouped` / `architecture` |
| `storage_path` | text | Path in Supabase Storage |
| `generated_at` | timestamp | |

### `user_profiles`
| Column | Type | Notes |
|---|---|---|
| `user_id` | uuid | PK; FK to auth.users |
| `display_name` | text | |
| `role` | enum | `owner` / `va` |
| `created_at` | timestamp | |

### `workspace_settings`
Singleton table (one row total). Stores workspace-level configuration values defined in §11.4.

| Column | Type | Notes |
|---|---|---|
| `id` | int | PK; always 1 |
| `va_soft_cap_usd` | numeric | Default 5.00 |
| `owner_cost_confirm_threshold_usd` | numeric | Default 6.00 |
| `default_relevance_threshold` | numeric | Default 0.62 |
| `silo_discovery_model` | text | Default `gpt-5.4` (with browsing) |
| `orchestrator_model` | text | Default `claude-opus-4-7` |
| `architecture_model` | text | Default `claude-opus-4-7` |
| `default_embedding_model` | text | Default `text-embedding-3-small` |
| `updated_at` | timestamp | |
| `updated_by_user_id` | uuid | FK to auth.users |

### Row-Level Security (RLS) policy summary

- `projects`, `sessions`, `topics`, `clusters`, `keywords`, `site_architecture`, `csv_exports`:
  - **Owner role** can SELECT/UPDATE/DELETE all rows.
  - **VA role** can SELECT/UPDATE only rows where the parent project's `user_id` matches the VA's `user_id`, OR where the project has been explicitly shared with the VA (sharing mechanism deferred to v2; in v1 the VA sees only their own rows).
  - INSERTs are gated by the same scope.
- `workspace_settings`:
  - **Owner role** can SELECT/UPDATE.
  - **VA role** can SELECT only (so the wizard can read the soft cap and locked defaults).
- `user_profiles`:
  - **Owner role** can SELECT all rows, UPDATE all rows.
  - **VA role** can SELECT/UPDATE only their own row (and cannot change their own `role`).

RLS policies are defined in the Supabase migration; the FastAPI service uses the user's JWT to drive the policy.

---

## 14. Tech Stack & Deployment

### 14.1 Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | FastAPI (Python 3.11) | Deployed to the **`info-site-kw-research-cluster`** service inside the Railway project **`AR Tools`**. The service is already provisioned in the dashboard; the build pushes code into it rather than creating a new service. |
| Frontend | React (Vite + TypeScript) | Lives in `/frontend` inside the `info-site-kw-research-cluster` GitHub repo (monorepo with the backend). Routed at `/fanout` for Owner mode and `/fanout/va` for VA mode. Deploys to Netlify; no shared shell needed. |
| Database | Supabase Postgres + pgvector | Shared with rest of AR Tools |
| Storage | Supabase Storage | For CSV snapshots |
| Auth | Supabase Auth | Shared session with Writer + other AR Tools; role from `user_profiles` |
| LLM (silo discovery) | **GPT-5.4 with browsing** | Browsing-bound work: live web access during silo proposal. Uses OpenAI SDK. |
| LLM (orchestrator + architecture) | **Claude Opus 4.7** | Structured-reasoning-bound work: strict-schema JSON output for editorial decisions. Uses Anthropic SDK with tool-use mode for schema enforcement. |
| Embeddings | OpenAI `text-embedding-3-small` | Reused from Brief Generator |
| External data | DataForSEO Labs + SERP + Keyword Data APIs | |
| Clustering | NetworkX + python-louvain | Reused from Brief Generator v2.0 |

### 14.2 Repo Structure & Deployment

The source code lives in **one standalone GitHub repo**: [`kssabraw/info-site-kw-research-cluster`](https://github.com/kssabraw/info-site-kw-research-cluster). Both the backend and the frontend are in this repo (monorepo). The repo is currently empty save for a README; the v1 build scaffolds the structure from scratch.

**Proposed layout:**

```
info-site-kw-research-cluster/
├── README.md
├── .gitignore
├── docs/
│   └── topic-fanout-prd-v1_7.md        ← this PRD, kept in the repo as source-of-truth
├── backend/
│   ├── Dockerfile
│   ├── railway.json
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                         ← FastAPI routers
│   │   ├── pipeline/                    ← silo discovery → architecture
│   │   ├── llm/                         ← OpenAI + Anthropic clients
│   │   ├── dataforseo/                  ← DataForSEO client
│   │   ├── storage/                     ← Supabase client wrappers
│   │   └── logging/                     ← structured logging setup (§16.3)
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── netlify.toml
│   ├── vite.config.ts
│   └── src/
│       ├── owner/                       ← Owner three-view UI (§9)
│       ├── va/                          ← VA wizard (§10)
│       ├── shared/                      ← shared components, auth, API client
│       └── App.tsx
└── supabase/
    └── migrations/
        └── 2026XXXX_fanout_initial.sql  ← creates the `fanout` schema and all tables
```

The PRD itself is checked into `docs/` so Claude Code (and any future contributor) can read it directly from the repo on every milestone. When the PRD updates, commit a new version to `docs/`.

**Railway deployment (backend):**

The backend deploys to the pre-provisioned Railway service **`info-site-kw-research-cluster`** inside the **`AR Tools`** Railway project. Configuration:

- Set Railway's root directory to `/backend` so it builds only the backend folder.
- Dockerfile-based deploy matching the pattern of `services/nlp` in `showup-local`.
- Service inherits project-level env vars from the `AR Tools` Railway project.

**Private networking:** the service can call other AR Tools services (e.g., `content-platform-api`, once that exists after the AR Tools rebuild) over Railway's private network for the Brief Generator handoff. The handoff is wired up in v1 but expected to **fail gracefully** until `content-platform-api` exists — see §16.2 for the degraded-mode behavior.

**Required environment variables on the service** (all already configured in the Railway project per Q8; the service inherits project-level variables, but service-specific overrides may need to be added):

| Variable | Notes |
|---|---|
| `DATAFORSEO_LOGIN` | Reused from project-level |
| `DATAFORSEO_PASSWORD` | Reused from project-level |
| `OPENAI_API_KEY` | Reused — drives both GPT-5.4 (silo discovery) and embeddings |
| `ANTHROPIC_API_KEY` | Reused — drives Opus 4.7 (orchestrator + architecture) |
| `SUPABASE_URL` | Reused from project-level |
| `SUPABASE_SERVICE_ROLE_KEY` | Reused; service uses this for admin queries, user JWT for scoped queries |
| `OPENAI_EMBEDDING_MODEL` | Service-specific. Defaults to `text-embedding-3-small`. |
| `OPENAI_SILO_MODEL` | Service-specific. Defaults to `gpt-5.4`. |
| `ANTHROPIC_ORCHESTRATOR_MODEL` | Service-specific. Defaults to `claude-opus-4-7`. |
| `ANTHROPIC_ARCHITECTURE_MODEL` | Service-specific. Defaults to `claude-opus-4-7`. |
| `CONTENT_PLATFORM_API_URL` | Service-specific. Internal Railway URL for the Brief Generator handoff. Empty string disables the handoff (degraded mode). |
| `PORT` | Auto-injected by Railway |
| `LOG_LEVEL` | Service-specific. Default `INFO`, set `DEBUG` during MVP testing. |

The four `*_MODEL` env vars exist so model upgrades can happen without redeploying — change the env var in Railway, restart the service. The workspace_settings table holds the same defaults and overrides them at runtime when set.

**Netlify deployment (frontend):**

The React UI deploys to Netlify directly from the same GitHub repo. Configuration:

- Connect Netlify to `kssabraw/info-site-kw-research-cluster`.
- Set the **base directory** to `frontend/` so Netlify only builds that folder.
- Build command: `npm run build` (or `pnpm build`).
- Publish directory: `frontend/dist`.
- Environment variable: `VITE_API_BASE_URL` pointing at the Railway public URL of the backend service.

Auto-deploys on push to `main`. A separate Netlify subdomain (e.g., `fanout.netlify.app` or a custom subdomain) hosts the app.

### 14.3 Supabase Schema Migration

Tables introduced in §13 are deployed via a new migration in the **existing AR Tools Supabase project** (shared with the rest of AR Tools per Q-Supabase resolution in v1.7). To avoid name collisions with other AR Tools work and keep this app's data easily portable to a dedicated Supabase project later, **all tables live under a dedicated `fanout` schema** — for example, `fanout.projects`, `fanout.sessions`, `fanout.topics`, `fanout.clusters`, `fanout.keywords`.

Migration filename: `2026XXXX_fanout_initial.sql`. The migration must:

- Create the `fanout` schema.
- Enable `pgvector` extension in that schema if not already enabled project-wide (it likely is, from the Brief Generator).
- Create all tables defined in §13 under the `fanout` schema with RLS enabled by default.
- Define RLS policies per the capability matrix in §11.2 and the RLS summary in §13.
- Insert exactly one row into `fanout.workspace_settings` with the defaults from §11.4.
- Seed a `fanout.user_profiles` row for Kyle with `role = 'owner'`.
- Provide a follow-up admin script to create `fanout.user_profiles` rows after VAs sign up via Supabase Auth.

**Important:** before running the migration, verify no existing tables in the AR Tools Supabase project use the `fanout` schema. If anything from the *prior* (archived) keyword research implementation remains, the migration should fail loud rather than silently overwrite — Claude Code should add a defensive check.

---

## 15. Build Plan & Milestones

This section converts the PRD into a buildable sequence. Each milestone is independently testable and produces something demonstrable. Milestones are designed so Claude Code can build them in order without backtracking; later milestones depend on earlier ones but earlier milestones never depend on what comes later.

### 15.1 Build Sequencing

| # | Milestone | What "done" looks like | Depends on |
|---|---|---|---|
| **M1** | **Foundation: auth, roles, projects, sessions schema** | Owner and VA can sign in via Supabase Auth. `user_profiles`, `projects`, `sessions`, `workspace_settings` tables exist with RLS policies enforced. Owner sees empty project list; VA sees empty project list scoped to themselves. Scratch project auto-created on first login. | — |
| **M2** | **Front-half pipeline: silo discovery + user review** | User enters a seed, optional `audience_hint`, optional `disambiguation_hint`. Pipeline runs the grounding pass, keyword_ideas demand sample, SERP structure scrape, and LLM silo proposal. Disambiguation gate triggers on ambiguous seeds. User sees proposed silos with rationale, evidence, and audience. User can remove silos, add custom silos, edit names/rationales, override audience. Finalized silos persist to `topics` table with embeddings. **No expansion yet** — pipeline halts after silo review for now. | M1 |
| **M3** | **Expansion pipeline** | Per-silo DataForSEO expansion (`keyword_ideas`, `keyword_suggestions`, `query_fanouts`, PAA 2-tier) runs in parallel for all finalized silos. Autocomplete enrichment runs on the surfaced keyword pool. All keywords persist to `keywords` table with source attribution. | M2 |
| **M4** | **SERP competitor mining + relevance gate + statistical clustering** | User deep-mine selection UI exists. SERP competitor mining runs on gated silos. Relevance gate filters keywords against per-silo embedding. Statistical clustering (Louvain) produces candidate groupings, persisted to `statistical_clustering_log`. End state: per-silo statistical groupings exist but are not yet user-facing. | M3 |
| **M5** | **Article planning orchestrator + cross-topic dedup** | SERP fetches run for candidate primary keywords. Per-silo orchestrator runs and converts statistical groupings into article plans. Cross-topic dedup pass runs. `clusters` table populated with article-level records. Coverage gaps persist to `coverage_gaps` table. | M4 |
| **M6** | **Site architecture generation** | LLM produces pillar/supporting structure with internal linking matrix. `site_architecture` row persists. Read-only architecture view available in API. | M5 |
| **M7** | **Owner UI: table, cluster, architecture views + editing** | Three views render against the data model. Split-view mode works on desktop. Filters and sort on table view. All cluster-editing operations work: rename, move keyword, merge, split, delete, edit H2, edit intent, promote primary, accept/dismiss gap, re-run orchestrator. Architecture view shows pillars, supporting articles, and internal links. | M6 |
| **M8** | **VA wizard** | 9-step linear wizard renders. All steps gated correctly (disambiguation only on ambiguous seeds, etc.). VA can complete a full run end-to-end. Restricted cluster-editing surface enforced. Architecture view is read-only for VAs. | M7 |
| **M9** | **Approval workflow** | Cost estimate calculated correctly before submission. Soft cap triggers approval flow for VA sessions over cap or with `recursive_fanout`. Approval queue UI for Owner. Approve/reject with note. VA notified on decision. 30-second polling in v1. | M8 |
| **M10** | **CSV export with Postgres-live + Storage snapshots** | All three CSV formats generate correctly. Snapshots write to Supabase Storage. Export history listed per session. Downloads served from Storage. | M7 |
| **M11** | **Cost confirmation + observability** | Live cost banner during pipeline execution. Per-step cost attribution logged. Structured logs (§16.3) flowing. Owner debug view shows `statistical_clustering_log` and `orchestrator_log` for any session. | M9, M10 |

**Critical sequencing notes:**

- M2 deliberately stops at silo review with no expansion. This lets the highest-risk step (silo quality) be validated against multiple test seeds before any expensive API work is built.
- M4 stops *before* the orchestrator. This lets statistical clustering be validated against eyeballed expectations before the orchestrator layer is built on top.
- M7 (Owner UI) precedes M8 (VA wizard) because the VA wizard is a restricted subset of the Owner UI. Building Owner first means VA mode is a configuration of what already exists rather than a parallel implementation.
- M9 (approval workflow) is intentionally late. It can be stubbed during M8 such that VAs always proceed without approval; the real approval flow gets wired in M9.
- M11 ties together cost + observability. These can be partially in place from M1 onwards (structured logging boilerplate is added per-service), but the *complete* picture only emerges at the end.

### 15.2 Acceptance Criteria per Pipeline Step

Each step's acceptance is the set of conditions that must be true before the step is considered complete in a build sense. These are *behavioral* criteria, not unit-test pass rates — they're the things you'd manually verify when reviewing a milestone.

| Step | Acceptance criteria |
|---|---|
| **§7.1 Silo Discovery** | (1) Returns `topic_count` silos, all with non-empty `name`, `rationale`, valid `relationship_type`, and non-empty `supporting_evidence`. (2) Zero `peer_entity` silos in the final output. (3) `is_broader_class: true` is flagged visually in the UI. (4) For the `mercury` test seed (Appendix A), the disambiguation gate triggers and the user can pick an interpretation. (5) For the `retatrutide` test seed, `tirzepatide` and `semaglutide` do NOT appear as silo names. |
| **§7.2 User Deep-Mine Selection** | (1) Seed is always pre-checked and ungated. (2) Live cost estimate updates within 200ms of any checkbox change. (3) VA mode caps selection at seed + 2 additional silos; UI prevents further selection with tooltip. |
| **§7.3 Per-Silo Expansion** | (1) All four endpoints run in parallel per silo. (2) Failure on one endpoint does not block the others; failed endpoint logs degraded-mode flag. (3) Total keyword pool ≥ 500 per silo at standard mode for the retatrutide test seed. (4) PAA tier-2 fanout caps at 40 questions per silo. |
| **§7.4 Competitor Mining** | (1) Runs only on user-gated silos. (2) Pulls top 5 URLs in standard mode, top 10 in comprehensive. (3) `ranked_keywords` returns positions 1–20 per URL. (4) Per-URL failure does not block the rest; failed URL logs degraded-mode flag. |
| **§7.5 Autocomplete** | (1) Runs on the deduped keyword pool, not on raw pool. (2) Throttles to avoid rate limit hits. (3) Failure on individual keywords skips and continues (does not retry indefinitely). |
| **§7.6 Relevance Gate + Dedup** | (1) Filters at least 40% of raw candidates on retatrutide test seed. (2) Manual spot-check on 100 sampled survivors shows ≥ 90% are topically relevant to their parent silo. (3) Cross-source dedup merges keywords with identical normalized form. (4) `tirzepatide`-related keywords are filtered out (peer entity, low cosine to retatrutide silos). |
| **§7.7 Recursive Fanout** | (1) Off by default. (2) Cost confirmation gate triggers when on. (3) Depth hard-capped at 1 (no infinite recursion). (4) Sub-sessions are persisted and traceable from the parent session. |
| **§7.8 Metrics Enrichment** | (1) Batches in groups of 1,000. (2) Volume / CPC / KD populate on the keywords table. (3) Failure on a batch falls through with `metrics_unavailable` flag, does not fail the run. |
| **§7.9 Statistical Clustering** | (1) Louvain runs per silo, not across silos. (2) Produces 3–15 candidate groupings per silo (within reason for the keyword pool size). (3) Output persisted to `statistical_clustering_log`. (4) Not directly user-facing. |
| **§7.10 Article Planning Orchestrator** | (1) Returns valid JSON matching the schema in §7.10.3. (2) Schema validation runs after the LLM call; one reprompt on malformed output, then degraded fallback. (3) Each article has a non-empty `primary_keyword`, valid `intent` enum, and at least one `supporting_keyword` OR is flagged as `is_gap_placeholder`. (4) Cross-topic dedup catches at least one collision on the retatrutide test seed (manually verified). (5) Coverage gaps flagged for retatrutide include at least one item that is plausibly a real gap (e.g., long-term safety, regulatory status). |
| **§7.11 Site Architecture** | (1) One pillar per accepted silo. (2) Every supporting article links up to its pillar. (3) Internal linking graph has no orphans (every supporting article is linked from at least one place). (4) Pillar lateral links only between pillars with cosine similarity > 0.55. |

### 15.3 Definition of Done for v1 MVP

The build is considered v1 MVP complete when **all** of the following are true:

1. All three primary test seeds in Appendix A (`retatrutide`, `metal roofing`, `sourdough starter`) produce coherent silos that pass manual editorial review.
2. The `mercury` test seed triggers the disambiguation gate and produces a coherent result after user selection.
3. End-to-end run completes in under 4 minutes at standard mode with metrics enrichment off.
4. A VA can complete the full 9-step wizard for a routine seed without external help, including triggering and waiting for an approval flow.
5. Peer entity leakage on retatrutide is zero in the silo set and below 5% in the final keyword pool.
6. CSV export in all three formats produces a downloadable file matching the data shown in the UI.
7. Total cost on the retatrutide test seed at standard mode + metrics on lands within ±25% of the §8.1 estimate.
8. Owner can review the orchestrator's decisions for any session via the debug view.
9. Approval queue end-to-end works: VA submits, Owner approves with a note, session runs, VA sees the result.
10. All RLS policies enforce expected access boundaries (VA cannot see Owner-only data; VA cannot see another VA's projects).

---

## 16. Error Handling, Degraded Modes & Observability

The pipeline makes external API calls at every step and runs LLM calls that can fail or return malformed output. Production behavior on the unhappy path matters as much as the happy path. This section is the failure-handling spec.

### 16.1 Failure Modes by Pipeline Step

| Failure | Response | Result |
|---|---|---|
| DataForSEO 5xx | Retry with exponential backoff (1s, 3s, 9s). After 3 failures, mark step as failed-degraded. | Pipeline continues with partial data; degraded flag surfaced to user. |
| DataForSEO 4xx (auth, quota, malformed) | No retry. Log full request/response. Surface error to user. | Pipeline halts; session marked `status: error`. |
| DataForSEO rate limit | Respect `Retry-After` header. Up to 30 seconds wait. After that, treat as 5xx. | Pipeline continues after wait; if wait exceeded, degraded. |
| ScrapeOwl failure (if used for HTML scraping) | Retry once. Then skip the URL and flag. | Step continues with partial data. |
| LLM call timeout (> 60 seconds for non-orchestrator, > 120 seconds for orchestrator) | Retry once with same prompt. If still timeout, fall through to degraded behavior for that step. | See §16.2 per-step degraded modes. |
| LLM returns malformed JSON | Validate against expected schema. If invalid, reprompt once with the validation error appended to the prompt. If second attempt also invalid, fall through to degraded behavior. | See §16.2. |
| LLM returns valid JSON but content fails business rules (e.g., orchestrator returns an article with no primary keyword) | Drop the offending item, continue with the rest. Log the dropped item for debug review. | Partial output; flag in `orchestrator_log`. |
| Supabase write failure | Retry with backoff (1s, 3s, 9s). After 3 failures, surface error and halt pipeline. Persist as much state as possible before halting. | Session marked `status: error`; user can resume from the partial state in v2 (in v1, must restart). |
| Embedding API failure | Retry with backoff. If embeddings cannot be computed, halt — too many downstream steps depend on them. | Session marked `status: error`. |
| Pipeline cancellation (user clicks Cancel) | Persist current state. Mark session as `status: cancelled`. Release any in-progress workers. | Partial data viewable; cost up to cancellation point counted. |
| Worker process crash mid-pipeline | Sessions in non-terminal states older than 30 minutes are auto-marked `status: error` by a periodic sweep. | User can re-run; partial state preserved for debug. |

### 16.2 Degraded Mode Behaviors

Degraded modes are explicit "the pipeline finished but something didn't work perfectly" states. Each is surfaced in the UI with a banner explaining what's degraded and why.

| Pipeline step | Degraded behavior | UI surface |
|---|---|---|
| Silo discovery: competitor structure scrape fails | Proceed with grounding + demand sample only. LLM gets a note that competitor structure is unavailable. | Banner on silo review screen: "Competitor structure unavailable for this run. Silos based on demand signal and topic grounding only." |
| Silo discovery: demand sample fails | Proceed with grounding + competitor structure only. | Similar banner. |
| Silo discovery: grounding fails | Halt. Cannot proceed without it. | Error state. |
| Expansion: one of four endpoints fails per silo | Proceed with the other three. The silo's keyword pool is smaller. | Silo card shows a "Partial expansion" badge. |
| Competitor mining: a URL's ranked_keywords fails | Skip that URL, continue with others. | Silo card shows "N/5 competitor URLs mined" instead of 5/5. |
| Autocomplete enrichment: bulk failures | Skip autocomplete entirely if > 50% of calls fail. | Banner: "Autocomplete enrichment unavailable for this run." |
| Metrics enrichment: any failure | Skip entire enrichment, mark all keywords as `volume: null, cpc: null, kd: null`. | Banner: "Metrics enrichment unavailable. Volume/CPC/KD not shown." |
| Orchestrator: fails on one silo (after retry) | Fall back to presenting that silo's statistical groupings directly as clusters, labeled with the MMR representative. No article-planning intelligence for that silo. | Silo card shows "Editorial planning unavailable — clusters shown as raw groupings." |
| Orchestrator: fails on every silo | Pipeline halts at orchestrator step. Statistical clustering output persists for debug. | Error state with diagnostic info. |
| Cross-topic dedup: fails | Skip dedup. Possible duplicates remain. | Banner: "Cross-topic deduplication skipped — review for duplicate articles." |
| Site architecture: fails | Pipeline completes without architecture. User can trigger regeneration. | Architecture view shows empty state with "Regenerate" button. |
| Brief Generator handoff: `CONTENT_PLATFORM_API_URL` is unset OR the call fails | Per-cluster "Send to Brief Generator" button is visible but disabled with a tooltip, OR the call returns an error and the user is shown a one-line "Brief Generator unavailable" message. The cluster data is unaffected; CSV export remains available. | Tooltip on disabled button or inline error toast. This is the expected state during the AR Tools rebuild window when `content-platform-api` does not yet exist. |

### 16.3 Structured Logging Requirements

Every external API call and every pipeline step emits a structured log entry to stderr (Railway captures stderr).

**Per-session correlation:**

- Every log entry includes `session_id` and a per-request `correlation_id`.
- The correlation ID propagates through all downstream calls within that session.

**Per-step log shape:**

```json
{
  "ts": "2026-05-20T14:32:01.234Z",
  "level": "INFO",
  "session_id": "uuid",
  "correlation_id": "uuid",
  "step": "silo_discovery",
  "event": "step_complete",
  "duration_ms": 8234,
  "cost_usd": 0.18,
  "status": "success",
  "external_calls": [
    { "service": "openai", "endpoint": "messages", "tokens_in": 1200, "tokens_out": 450, "cost_usd": 0.06, "latency_ms": 3100 },
    { "service": "dataforseo", "endpoint": "keyword_ideas", "result_count": 200, "cost_usd": 0.05, "latency_ms": 2100 },
    { "service": "dataforseo", "endpoint": "serp", "result_count": 10, "cost_usd": 0.05, "latency_ms": 1800 }
  ]
}
```

**LLM call log shape:**

```json
{
  "ts": "...",
  "level": "INFO",
  "session_id": "uuid",
  "correlation_id": "uuid",
  "event": "llm_call",
  "purpose": "silo_proposal",
  "provider": "openai",
  "model": "gpt-5.4",
  "prompt_tokens": 1200,
  "completion_tokens": 450,
  "cost_usd": 0.06,
  "latency_ms": 3100,
  "status": "success",
  "retry_count": 0
}
```

Other `purpose` values use Anthropic's Opus 4.7:
- `purpose: "article_planning"` → `provider: "anthropic"`, `model: "claude-opus-4-7"`
- `purpose: "cross_topic_dedup"` → `provider: "anthropic"`, `model: "claude-opus-4-7"`
- `purpose: "architecture_generation"` → `provider: "anthropic"`, `model: "claude-opus-4-7"`

**Required log levels:**

- `DEBUG` — full prompts and responses; enabled only during MVP testing via env var.
- `INFO` — step start/complete, external calls, costs.
- `WARN` — degraded modes, retries.
- `ERROR` — halt-the-pipeline errors with full context.

### 16.4 Cost Attribution

Every external API call increments the session's running cost. To avoid hot-row contention on `sessions.actual_cost_usd`:

- API calls write to an in-memory accumulator within the worker.
- Accumulator flushes to `sessions.actual_cost_usd` every 10 seconds via a single UPDATE.
- Final flush on step completion or session terminal state.
- Per-step cost breakdown persists in a `cost_breakdown` jsonb field on the session, populated on step completion.

The cost breakdown enables post-hoc analysis ("which step is most expensive on average?") and validates the §8.1 estimates against reality. After the first 10 production runs, the §8.1 estimates table should be updated with observed actuals.

---

## 17. MVP Scope vs. v2

### v1 (this PRD)
Everything above.

### Deferred to v2
- Automatic gap detection (diff a new session against a project's covered clusters).
- Multi-seed sessions (compare multiple seeds in one view).
- Site CMS export (push site architecture directly to WordPress / Astro / etc.).
- Recursive fanout depth >1.
- Multilingual support.
- Real-time collaborative editing.
- Programmatic API for headless use.
- LLM-suggested cluster names (currently MMR-picked representative keyword).
- Real-time push notifications for the approval queue (v1 uses 30s polling).
- Email notifications for approval requests when the Owner is offline.
- Project sharing between users (v1: each user sees only their own projects; Owner sees all via RLS).
- Aggregate VA budget caps (e.g., $50/month per VA across all runs); v1 is per-run only.
- Additional roles beyond Owner / VA (e.g., Reviewer, Read-only).

---

## 18. Open Questions

| # | Question | Resolution / default assumption |
|---|---|---|
| Q1 | Which LLM for silo discovery, orchestrator, and architecture generation? | **RESOLVED (v1.5):** Split-model approach. GPT-5.4 with browsing for silo discovery (browsing-bound); Claude Opus 4.7 for orchestrator and architecture generation (structured-reasoning-bound). |
| Q2 | Default relevance threshold at §7.6 — locked at 0.62 or tunable per-run in production? | Locked once 10 production runs validate a value. Tunable during MVP testing. |
| Q3 | Does the Scratch project ever get auto-cleaned? | No — manual cleanup only. Surface session count in UI to encourage promotion to real projects. |
| Q4 | Does the architecture view allow user editing of the linking matrix? | v1: read-only with a "Regenerate" button. Manual editing deferred to v2. |
| Q5 | Should re-running the same seed in the same project automatically merge with prior runs, or always create a new session? | Always a new session. Merge/diff is the v2 gap-detection feature. |
| Q6 | Working name "Fanout" — confirm or pick something else. | Use placeholder until product naming. |
| Q7 | Confirm the existing Railway project name. | **RESOLVED (v1.6):** Project is `AR Tools`. The pre-provisioned service `info-site-kw-research-cluster` inside that project is the deployment target. Build pushes code into the existing service rather than creating a new one. |
| Q8 | Is `ANTHROPIC_API_KEY` already configured in the Railway project, or does it need to be added? | **RESOLVED (v1.5):** All required keys (DataForSEO, OpenAI, Anthropic, Supabase) are already configured in the Railway project. New service inherits them. |
| Q9 | Soft cap default — right number? | **RESOLVED (v1.5):** $5.00. Standard mode with metrics (~$3.10), comprehensive with metrics (~$4.40), and most non-recursive runs all pass without approval. Recursive fanout always requires approval. |
| Q10 | "Request restructure from Owner" button on VA cluster view — does this create a notification, an annotation on the cluster, or both? | Both: a flag on the cluster visible to the Owner, plus an entry in a (lightweight) "Restructure requests" inbox. |
| Q11 | When a VA is removed from the workspace, what happens to their projects and sessions? | Ownership transfers to the Owner; nothing is deleted. |
| Q12 | SERP overlap threshold for orchestrator merge/split decisions — 3/10 URLs in common is a guess. | Start at 3/10. Tune during MVP testing against real niches; the right number probably varies between commercial-intent topics (where SERPs are tighter) and informational-intent topics (where SERPs are looser). |
| Q13 | What happens to user edits when the user clicks "Re-run orchestrator" on a session that already has edited articles? | Default: orchestrator runs on the *current* state (post-edit). Edits are preserved as input, not clobbered. Articles created by the orchestrator that the user has since renamed retain their custom names. Confirm. |
| Q14 | Cross-topic dedup similarity threshold (0.85 primary-keyword cosine OR 2/3 SERP overlap) — right balance? | Tune in MVP. Too tight misses real duplicates; too loose merges legitimate-but-similar articles across topics. |
| Q15 | Should the orchestrator have access to volume data when metrics enrichment is OFF? | No — orchestrator runs on the data available. Without volume, promote/demote decisions fall back to SERP-overlap and intent signals only. Document this as a known degraded mode. |
| Q16 | Silhouette-score threshold for ambiguity detection in the disambiguation gate. | Start at 0.5. Tune during MVP testing — too low triggers spurious disambiguation prompts on legitimately complex seeds; too high misses real ambiguity. |
| Q17 | If the user adds a custom silo with a `relationship_type` that the LLM would have rejected (e.g., `peer_entity`), do we let it through? | Yes in v1 — user is asserting it belongs. Tag with `source: user_added` for traceability. Consider a soft warning in the UI explaining the topical-authority risk. |
| Q18 | Where in the wizard should `audience_hint` and `disambiguation_hint` live? Step 2 (with the seed) or Step 3 (run settings)? | Step 2 with the seed, collapsed by default — they're conceptually part of "what are you researching," not "how should the system behave." |

---

## 19. Version History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-20 | Initial draft. Single-seed niche-site topic fanout. Pipeline includes LLM topic discovery with web grounding + relationship taxonomy, full DataForSEO expansion (keyword_ideas / keyword_suggestions / query_fanouts / PAA 2-tier / autocomplete), gated competitor SERP mining, optional recursive fanout, optional metrics enrichment, clustering, and site architecture generation. UI: three views (table / cluster / architecture) with split mode, editable clusters (move / merge / split / rename), project + session persistence with Scratch default, CSV export via Postgres-live + Supabase Storage snapshots. |
| 1.1 | 2026-05-20 | Added Owner / VA role model with separate UIs: Owner keeps the three-view power-user interface; VA gets a linear wizard flow with locked-in defaults and restricted cluster editing (move/rename only, no split/merge). Added approval workflow: VA runs over the workspace soft cap (default $3.00) or any recursive fanout request require Owner approval before pipeline execution. Added `user_profiles`, `workspace_settings` tables and RLS policy summary. Sessions table extended with approval columns. Added Railway deployment specifics for the existing AR Tools project (service `kw-research-api`, env vars, private networking note). New v2 deferred items: real-time approval push, email notifications, project sharing, aggregate VA budget caps. New open questions Q7–Q11 covering Railway verification, soft-cap default, restructure-request mechanics, and VA off-boarding. |
| 1.2 | 2026-05-20 | Split clustering into two distinct steps: §7.9 Statistical Clustering (intermediate, not user-facing) and §7.10 Article Planning (Editorial Orchestrator). The orchestrator is an LLM that runs per-topic plus a cross-topic dedup pass; it converts statistical groupings into article plans using SERP overlap, intent inference, and volume signals. Decisions per grouping: merge / split / promote-demote / route / drop. Orchestrator also flags coverage gaps for user acceptance. Site architecture generation (now §7.11) consumes the article plan rather than raw clusters. Added SERP fetch for orchestrator candidate primaries to the pipeline ($0.25–$0.50 per run). Updated `clusters` table to represent article units with `primary_keyword_id`, `intent`, `suggested_h2s`, `peer_article_links`, `orchestrator_notes`, `is_gap_placeholder`. Added `coverage_gaps` table. Added session-level `statistical_clustering_log` and `orchestrator_log` for debugging. Updated `keywords` table with `serp_top_urls`, `is_primary_for_cluster`, `orchestrator_drop_reason`. Cost matrix updated: standard mode now ~$2.75 (was $1.85), comprehensive ~$3.75 (was $2.65). VA soft cap default raised from $3.00 to $4.00 to keep standard mode under cap. Owner cost-confirm threshold raised from $5.00 to $6.00. UI: Cluster View redesigned to show article-level data (primary keyword, intent, H2 outline, peer links, coverage gaps inline). New cluster-editing actions: edit H2 outline, edit intent, promote supporting keyword to primary, accept/dismiss gap, re-run orchestrator. New open questions Q12–Q15 covering SERP overlap thresholds, edit preservation on re-run, cross-topic dedup tuning, and degraded-mode orchestrator behavior. |
| 1.3 | 2026-05-20 | Reframed §7.1 from "Topic Discovery" to "Silo Discovery" to reflect what it actually produces: top-level site structure. Added pre-discovery grounding pass that gathers three signals before silo proposal: subject grounding, DataForSEO `keyword_ideas` demand sample (~200 keywords), and competitor URL structure from top-5 SERP. Silo prompt now requires `supporting_evidence` tying each silo back to evidence. Added optional `audience_hint` and `disambiguation_hint` input fields; disambiguation gate triggers automatically when grounding detects an ambiguous seed (silhouette score > 0.5) and no hint was provided. Added mandatory user silo-review step (§7.1.4) where the user can remove proposed silos, add custom ones, edit names and rationales, and override detected audience before the rest of the pipeline runs. Audience is now baked into the per-silo embedding (`seed + rationale + audience`) so downstream relevance filtering is audience-aware. §7.2 renamed to "User Deep-Mine Selection" to disambiguate from §7.1.4. Updated `sessions` table with `audience_hint`, `disambiguation_hint`, `detected_audience`, `disambiguation_choice`, and new status values `running_pre_review` and `awaiting_silo_review`. Updated `topics` table with `supporting_evidence`, `source` (llm_proposed / user_added / llm_proposed_then_user_edited), and `is_broader_class`. VA wizard updated from 8 to 9 steps to include disambiguation prompt (conditional) and silo review. Cost of silo discovery step bumped from $0.15 to $0.20 due to added grounding signals. New open questions Q16–Q18 covering ambiguity threshold, user-added silos with off-taxonomy relationship types, and wizard placement of optional hints. |
| 1.4 | 2026-05-20 | Build-readiness pass. Added §15 Build Plan & Milestones: 11 sequenced milestones (M1 Foundation → M11 Observability), each independently testable; per-step acceptance criteria for every §7 step; explicit Definition of Done for v1 MVP with 10 measurable criteria. Added §16 Error Handling, Degraded Modes & Observability: per-failure response table covering DataForSEO 4xx/5xx/rate limit, LLM timeout/malformed JSON/business-rule violations, Supabase write failures, worker crash; explicit degraded-mode behaviors per pipeline step with UI surface descriptions; structured logging requirements with correlation IDs and JSON log shapes for per-step and per-LLM-call events; cost attribution strategy (in-memory accumulator with 10s flush to avoid hot-row contention). Added Appendix A with 5 test seeds (`retatrutide`, `metal roofing`, `sourdough starter`, `mercury`, `plumber`) covering pharmaceutical, home-improvement, food/hobby, ambiguous, and would-be-local niches; per-seed expected silos, sample articles, and edge cases. Added Appendix B with rough first-draft prompts for the three highest-leverage LLM steps: silo proposal, orchestrator, and architecture generation; explicitly marked as starting points for iteration during build, not final prompts. Renumbered §15/§16/§17 from v1.3 to §17/§18/§19. |
| 1.5 | 2026-05-20 | Resolved Q1, Q7, Q8, Q9 — final model/deployment decisions locked. **Split-model architecture:** GPT-5.4 with browsing handles silo discovery (browsing-bound work); Claude Opus 4.7 handles the orchestrator and architecture generation (structured-reasoning work, with tool-use mode for strict JSON schemas). Service uses both OpenAI and Anthropic SDKs. Railway project name confirmed as `AR Tools info-site-kw-research-cluster` (with a verify-in-dashboard note in case the actual project is `AR Tools` and the rest is a service/environment). All required API keys confirmed already configured in the Railway project; no new key provisioning required. VA soft cap raised to $5.00 (was $4.00 in v1.4) so standard mode with metrics, comprehensive mode with metrics, and most non-recursive runs all pass without approval; only recursive fanout consistently requires approval. `workspace_settings` extended with three model-name fields (`silo_discovery_model`, `orchestrator_model`, `architecture_model`) for runtime overrides without redeployment. Four new env vars added on the service (`OPENAI_SILO_MODEL`, `ANTHROPIC_ORCHESTRATOR_MODEL`, `ANTHROPIC_ARCHITECTURE_MODEL`, plus the existing `OPENAI_EMBEDDING_MODEL`). Appendix B prompts updated with per-prompt model designations; orchestrator and architecture prompts note the use of Anthropic tool-use mode with strict schemas to enforce JSON output shape. LLM call log shape extended with `provider` field. |
| 1.6 | 2026-05-20 | Final clarification on Q7. Railway target is now fully resolved: the project is `AR Tools` and the service `info-site-kw-research-cluster` is a pre-provisioned service inside it. The build deploys code into the existing service rather than creating a new one. Renamed every reference from the previously-assumed service name `kw-research-api` to `info-site-kw-research-cluster`. Rewrote §14.2 Railway Deployment to reflect the correct project-vs-service structure. All deployment-side open questions are now closed; the PRD is complete and ready to hand off to Claude Code. |
| 1.7 | 2026-05-20 | Repo target finalized. Source code lives in the standalone GitHub repo `kssabraw/info-site-kw-research-cluster` (not an AR Tools monorepo) as a monorepo with both backend and frontend. Repo was reset on 2026-05-21 after the previous 12-phase implementation was archived; v1.7 build starts from an essentially empty repo with only a README. Added §14.2 proposed repo layout (`backend/`, `frontend/`, `supabase/`, `docs/` for the PRD itself). Frontend now deploys to Netlify directly from `/frontend` in this repo — no AR Tools frontend shell required. Supabase is shared with the existing AR Tools project but isolated under a dedicated `fanout` schema (`fanout.projects`, `fanout.sessions`, etc.) to prevent name collisions and make a future Supabase split trivial. Migration must include a defensive check that the `fanout` schema is empty before creating it. Added `CONTENT_PLATFORM_API_URL` env var with empty-string-disables semantics. Brief Generator handoff explicitly expected to be in degraded mode during the AR Tools rebuild window; new §16.2 entry describes the graceful failure (disabled button with tooltip OR inline error toast). PRD is kept in `docs/` inside the repo as source of truth for every milestone. |

---

## Appendix A — Test Seeds & Expected Outputs

Five test seeds chosen to exercise different niche types and edge cases. The build is validated against these. "Expected output" describes a *passing* output, not a unique correct one — multiple valid silo sets exist; what matters is that no obvious failure modes appear.

### A.1 `retatrutide` (pharmaceutical / emerging research drug)

**Why this seed:** the primary debugging seed throughout the PRD. Tests peer-entity filtering (must not return `tirzepatide` / `semaglutide` as silos). Tests broader-class handling (`incretin mimetics` is a candidate). Tests scientific/clinical vocabulary grounding.

**Expected silos (~5):**
- `triple agonist` (`property_or_mechanism`)
- `use cases and indications` or `weight loss applications` (`use_case`)
- `side effects and safety profile` (`effect_or_outcome`)
- `dosing and administration` (`practical_commercial`)
- `clinical trial results` (`research_or_trial`)

**Sample articles (per silo):**
- triple agonist → "How triple agonism works"; "GIP receptor specifically"; "Triple vs dual vs single agonist"
- side effects → "Common side effects"; "Nausea and GI effects"; "Long-term safety considerations"

**Edge cases the build must handle:**
- `tirzepatide` and `semaglutide` MUST NOT appear as silos.
- They MAY appear as keywords inside `practical_commercial` (comparison content).
- Long-term safety is likely a coverage gap the orchestrator flags.

### A.2 `metal roofing` (home improvement product)

**Why this seed:** tests a commercial-intent-dominated niche with strong product subtypes. Tests competitor structure scraping against a niche with well-organized commercial sites.

**Expected silos (~5):**
- `metal roof types and materials` (`property_or_mechanism`)
- `installation and contractors` (`practical_commercial`)
- `cost and pricing` (`practical_commercial`)
- `pros, cons, and comparisons to other roofing` (`comparison` use case)
- `maintenance and longevity` (`effect_or_outcome`)

**Sample articles:**
- types → "Standing seam metal roofs"; "Corrugated metal roofing"; "Stone-coated steel"
- cost → "Metal roof cost per square foot"; "Metal roof vs asphalt cost"; "Hidden costs of metal roofing"

**Edge cases:**
- `asphalt shingles` MUST NOT appear as a silo (peer entity / competitor product).
- Silos should reflect the commercial-heavy demand profile rather than pure informational.

### A.3 `sourdough starter` (food / hobby)

**Why this seed:** tests a hobbyist niche with primarily informational intent. Tests the agent's ability to surface practical / how-to silos that aren't products or services.

**Expected silos (~5):**
- `how to make a starter` (`use_case`)
- `feeding and maintenance` (`practical_commercial`)
- `troubleshooting` (`effect_or_outcome`)
- `recipes using starter` (`use_case`)
- `science of fermentation` (`property_or_mechanism`)

**Edge cases:**
- `commercial yeast` MUST NOT appear as a silo.
- `bread machine` should not appear as a silo (different niche).

### A.4 `mercury` (ambiguous seed)

**Why this seed:** the canary for the disambiguation gate. Without disambiguation, the agent will likely mix planet content, chemical element content, automotive content, and Greek mythology.

**Expected pipeline behavior:**
- Grounding pass returns content spanning ≥ 2 well-separated clusters.
- Silhouette score on grounding content > 0.5.
- Disambiguation gate triggers; UI prompts user to pick (planet / element / car brand / Roman god / company name).
- If user provides `disambiguation_hint: "the chemical element"`, gate is skipped and silos focus on toxicology, chemistry, environmental impact, industrial uses.

**Failure mode if disambiguation is broken:** silos mix astrology, chemistry, and 1960s automobiles. Easy to spot manually.

### A.5 `plumber` (would-be-local seed without geo modifier)

**Why this seed:** confirms the tool gracefully handles seeds that "want" to be local but weren't supplied with a location. The PRD scopes local SEO to ShowUP Local, not this tool, but the pipeline shouldn't crash or produce nonsense.

**Expected pipeline behavior:**
- Silos are topical rather than geographic: `services` (drain cleaning, water heaters, etc.), `tools and trade`, `how-to and DIY`, `hiring and pricing`, `licensing and trade career`.
- No silo proposes city-level geo splits.
- If the user supplies `audience_hint: "homeowners"`, articles skew toward DIY and hiring; if `audience_hint: "plumbers"`, articles skew toward trade tools and licensing.

**Edge cases:**
- The agent should NOT propose a `plumber [city]` silo. If it does, that's a regression — the tool isn't a local SEO tool.

---

## Appendix B — LLM Prompts (Rough First Drafts)

These are starting points for the three highest-leverage LLM calls, not final prompts. Expect to iterate during MVP testing against the test seeds in Appendix A. Prompt quality on these three calls is the single biggest determinant of output quality.

### B.1 Silo Proposal Prompt — GPT-5.4 with browsing

This prompt runs against GPT-5.4 with the browsing tool enabled, so the model can resolve and read live competitor pages during proposal.

```
You are proposing the top-level subfolder structure for a niche authority site about {seed_keyword}.

The site will be dedicated entirely to {seed_keyword}. Every article on it must serve someone researching, evaluating, or using {seed_keyword}.

AUDIENCE: {detected_audience_or_hint}

EVIDENCE GATHERED:
[Subject grounding summary from web search, ~500 words]

[Top 30 keywords from DataForSEO keyword_ideas sample]

[Top 5 ranking domains for the seed, with their URL path patterns]

YOUR JOB:
Propose {topic_count} subfolders ("silos") that together cover what this site needs to demonstrate topical authority. Each silo becomes a top-level section of the site with multiple articles inside it.

RULES:
1. Every silo must be tagged with one of these relationship_types:
   - property_or_mechanism: something {seed_keyword} IS or DOES
   - use_case: an application or scenario where {seed_keyword} is used
   - effect_or_outcome: what happens as a result of {seed_keyword}
   - practical_commercial: how someone obtains, uses, or operationalizes {seed_keyword}
   - research_or_trial: scientific evidence about {seed_keyword}
   - broader_class: a category that contains {seed_keyword} (use SPARINGLY; justify why a {seed_keyword} site needs this category-level coverage)
2. NEVER propose a peer entity as a silo. Peer entities are other things in the same category as {seed_keyword} (e.g., competing drugs, competing products, sibling concepts). They dilute topical authority.
3. Every silo must cite specific evidence in `supporting_evidence` — a keyword cluster from the demand sample, a competitor URL pattern, or an explicit reference to a fact from the grounding.

OUTPUT FORMAT:
Strict JSON array of {topic_count} objects:
[
  {
    "name": "short name, 2-5 words",
    "rationale": "2-3 sentences on why this silo is essential for topical authority",
    "relationship_type": "one of the enums above",
    "supporting_evidence": "specific evidence from the materials provided",
    "is_broader_class": boolean
  }
]
```

### B.2 Article Planning Orchestrator Prompt — Claude Opus 4.7

This prompt runs against Claude Opus 4.7 using tool-use mode with strict schemas to enforce the output JSON shape. The `tool_choice` should force the model to call a single `submit_article_plan` tool whose input schema matches the expected output.

```
You are the editorial planning agent for a niche authority site about {seed_keyword}, audience: {detected_audience}.

You are planning articles for one silo: {silo_name}
Silo rationale: {silo_rationale}

You have been given:
1. {N} statistical groupings of keywords within this silo
2. SERP data (top 10 URLs) for the representative keyword of each grouping
3. Volume / intent inference for each candidate primary keyword (or null if metrics unavailable)

YOUR JOB:
Decide what articles should be published in this silo. For each statistical grouping, choose one of these outcomes:
- MERGE: keywords share intent AND SERP overlap ≥ 3/10 URLs → one article
- SPLIT: keywords cluster statistically but have distinct intents OR SERP overlap < 2/10 → N articles
- PROMOTE+DEMOTE: one broad keyword has volume, narrow children lack standalone volume → one article with broad as primary and narrow as H2s
- ROUTE: keyword belongs in a different grouping within this silo → flag for relocation
- DROP: no article-level treatment justified → flag with reason

Additionally, identify COVERAGE GAPS: article concepts that should exist for topical authority but no grouping surfaced for them. Be specific.

RULES:
1. Every article must have a primary keyword and at least one supporting keyword (or be a gap placeholder).
2. Intent is inferred from SERP composition: product pages → transactional, comparison content → comparison, how-to/explainer → informational, definition pages → informational.
3. H2 outline (4-6 H2s) reflects what successful SERP pages cover for the primary keyword, NOT what the silo as a whole covers.
4. Peer-article-links: 2-3 links to other articles in this silo that are semantically related (use the supplied embeddings to identify peers).
5. Do not invent keywords. Only use keywords from the input groupings.

OUTPUT FORMAT:
Strict JSON object:
{
  "articles": [ { primary_keyword, supporting_keywords, intent, suggested_h2s, peer_article_links, source_statistical_grouping_id, orchestrator_notes } ],
  "routes": [ { keyword, from_grouping_id, to_grouping_id, reason } ],
  "drops": [ { keyword, reason } ],
  "gaps": [ { suggested_title, target_keyword, rationale } ]
}
```

### B.3 Architecture Generation Prompt — Claude Opus 4.7

This prompt also runs against Opus 4.7 with tool-use mode, using a `submit_architecture` tool with the architecture JSON schema. Shares the Anthropic client with the orchestrator.

```
You are designing the site architecture for a niche authority site about {seed_keyword}, audience: {detected_audience}.

You have been given:
1. The finalized list of silos
2. The article plan for each silo (from the orchestrator)

YOUR JOB:
Produce a site-level architecture with pillars, supporting articles, and internal linking.

RULES:
1. ONE pillar per silo. Pillar is a high-level overview article that establishes the silo's authority and links down to all supporting articles in it.
2. Pillar working title should reflect the silo's name but feel like a real article title (e.g., "The Complete Guide to Triple Agonist Drugs").
3. Pillar target keyword should be the broadest commercially-meaningful keyword in the silo.
4. Pillar H2 outline (5-8 H2s) summarizes the silo's coverage, with each H2 corresponding to one or more supporting articles.
5. Internal linking matrix:
   - Every supporting article links UP to its pillar (mandatory).
   - Every pillar links DOWN to all its supporting articles (mandatory).
   - Each supporting article gets 2-3 lateral links to peer articles in the same silo (use the peer_article_links the orchestrator already proposed where possible).
   - Pillars link laterally to other pillars where topically adjacent (use the supplied silo embeddings).

OUTPUT FORMAT:
Strict JSON object:
{
  "pillars": [ { silo_id, title, target_keyword, summary, h2_outline, supporting_article_ids, lateral_pillar_links } ],
  "supporting_articles": [ { article_id, parent_pillar_id, lateral_article_links } ]
}
```

**Iteration notes:**

- These prompts are intentionally schematic. Expect to add few-shot examples to each during MVP testing once you've seen real outputs on the test seeds.
- The orchestrator prompt is the most likely to need a JSON-schema-enforcing wrapper (e.g., OpenAI structured outputs, Claude's tool use with strict schemas). Malformed JSON is the highest-frequency failure mode for this call.
- Consider adding a "self-check" final instruction to the orchestrator prompt: "Before returning, verify every article has a primary keyword from the input and that no keyword appears in more than one article."
