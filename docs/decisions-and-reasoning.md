# Decisions and Reasoning

This document captures the reasoning behind architectural and strategic
decisions made during initial project design. It supplements
[PROJECT_BRIEF.md](../PROJECT_BRIEF.md) by documenting not just *what*
was decided but *why*, including alternatives considered and tradeoffs
accepted.

When future contributors (including future you) wonder "why was X chosen
over Y?" — this document is the answer. Decisions are organized by topic,
not chronologically.

---

## Scope and Scale Decisions

### Decision: 500 articles per site, not 2000

**Context:** Initial scoping considered 2000 articles per site as the
target for topical authority.

**Decision:** Reduced to 500 articles at higher quality per article.

**Reasoning:**
- For YMYL niches (medical/health), Google's helpful content system
  penalizes high-volume thin content harder than smaller authoritative
  sites
- 2000 mediocre articles consistently underperform 500 deep articles
  in ranking outcomes
- Maintenance burden of 2000 articles is real: refreshing, monitoring,
  pruning stale content
- Budget redirected from raw volume to quality (better research, more
  thorough review, expert review on pillars, initial link building)
- $1,500 spent on 500 well-built articles tends to outperform $2,000
  spent on 2000 articles in this niche

**Alternatives considered:**
- 2000 articles at standard quality (~$2,000/year) — too high risk of
  HCU penalty in YMYL niche
- 50-100 articles as MVP validation — too few to establish topical
  authority signals
- Variable per-niche (different scale per site) — harder to plan and
  budget, deferred to "see what works"

**Tradeoffs accepted:**
- Less long-tail capture
- Slower path to ranking on tangential queries
- Smaller initial content footprint

### Decision: 20-site portfolio target, not single site

**Context:** Question of whether retatrutide should be a one-off or
part of a portfolio strategy.

**Decision:** Build retatrutide as the prototype for a 20-site portfolio.

**Reasoning:**
- Source library reuse compounds across adjacent niches (FDA pages,
  ClinicalTrials.gov, peer-reviewed journals serve multiple drug sites)
- Per-site infrastructure cost amortizes from ~$400/site to ~$50/site
  when split across 20 sites
- Generation pipeline built once works for all sites
- Risk distribution: if 5 of 20 sites become winners, portfolio pays
  for itself many times over

**Alternatives considered:**
- Single site, focused investment — higher risk concentration
- 50+ site portfolio — operational complexity outweighs benefits at
  this scale
- 5-10 site portfolio — leaves compounding value on the table

**Tradeoffs accepted:**
- Architectural complexity (multi-tenant from day one) for future benefit
- First site costs more (building infrastructure) than subsequent sites
- Requires discipline to not over-engineer for 20 sites when only 1 exists

### Decision: Lean update budget, not no updates or full updates

**Context:** Question of whether to budget for ongoing content refresh
in year 1.

**Decision:** Lean updates (~$90/site/year). Critical-content quarterly
refresh, major-event handling, weekly news articles.

**Reasoning:**
- Retatrutide niche moves fast: FDA milestones, Phase 3 readouts,
  regulatory changes occur multiple times per year
- Competitors update aggressively (some sites touch core pages every
  1-2 weeks) — falling behind on freshness loses rankings
- Full updates ($240+/year) are probably overkill for evergreen content
- Skipping updates entirely creates HCU vulnerability

**Alternatives considered:**
- No updates ($360 total year 1) — high risk for fast-moving niche
- Full updates ($565 total year 1) — overkill for most articles
- Per-niche variable — adopted at portfolio level (fast-moving sites
  get full, evergreen sites get none, medium sites get lean)

**Tradeoffs accepted:**
- Some content will go slightly stale before refresh cycles catch it
- Less aggressive content freshness than competitors who update weekly
- Acceptable for a 500-article site where 80 critical articles get
  quarterly attention

---

## Tool Selection Decisions

### Decision: DataForSEO only, not Semrush

**Context:** Need to discover ~10-15K keywords in a niche. Semrush is
the industry standard for keyword research with a $140/month subscription.

**Decision:** Use DataForSEO API exclusively for keyword discovery.

**Reasoning:**
- Semrush requires manual CSV exports — breaks programmatic workflow
- DataForSEO covers 90-95% of relevant keyword discovery for tight
  niches at fraction of cost (~$15-20 vs $140)
- DataForSEO is fully programmatic, scales naturally across 20-site
  portfolio
- Semrush database advantage is biggest for broad niches; in single-
  drug niches like retatrutide, the gap matters less
- Already have DataForSEO integration from ShowUP Local

**Alternatives considered:**
- Semrush one-month subscription, cancel after — saves $0 in long run
  if scaling to 20 sites, adds manual workflow friction
- Hybrid (Semrush for seeds, DataForSEO for expansion) — added
  complexity for marginal coverage gain
- Ahrefs API — more expensive than DataForSEO, fewer pipeline-friendly
  endpoints

**Tradeoffs accepted:**
- 5-10% less coverage of obscure low-volume long-tails
- No native Semrush "Keyword Gap" convenience
- Slightly more code complexity in discovery scripts
- Lose UI for data browsing

### Decision: OpenAI text-embedding-3-large, not Voyage or self-hosted

**Context:** Need embedding model for keyword clustering. Multiple
options exist: Voyage 3 Large (best benchmarks), OpenAI 3-large
(widely used), Cohere Embed v4 (multilingual leader), open-source
options like BGE-M3 (free self-hosted).

**Decision:** OpenAI text-embedding-3-large.

**Reasoning:**
- Already using OpenAI for other parts of pipeline (one API key, one SDK)
- Quality gap to Voyage is real but small (~5% on relevant benchmarks)
  and probably invisible at our scale (12K keywords clustering to 500)
- Matryoshka dimension flexibility (can reduce from 3072 to 1024 or 512)
- Cost is trivial for one-time embedding: ~$0.04 per site
- Self-hosted (BGE-M3) saves money but adds GPU/Docker complexity not
  worth it at this scale
- Voyage's domain advantage is for RAG retrieval, not clustering

**Alternatives considered:**
- Voyage 3 Large — best benchmark score, but new SDK to learn and
  cost premium not justified at our scale
- BGE-M3 self-hosted — would save API costs but engineering time
  outweighs savings until processing millions of texts
- RoBERTa/sentence-transformers — 10-point MTEB gap is real,
  outdated training data, no domain understanding of current terms

**Tradeoffs accepted:**
- ~5% potentially better clustering with Voyage
- Vendor dependency on OpenAI
- API cost (though trivial at $0.04/run)

### Decision: Claude for content generation (multi-model routing)

**Context:** Content generation needs research, drafting, review, and
revision passes. Multiple model options across price/quality spectrum.

**Decision:** Smart routing across Claude models:
- Sonnet 4.6 for outlines and adversarial review
- Opus 4.7 for draft and revision passes
- Haiku 4.5 for utility tasks (intent classification, link selection)

**Reasoning:**
- Cost difference between using Opus everywhere and smart routing is
  ~$150 across 500 articles
- Sonnet handles outline and review well, no meaningful quality loss
- Opus genuinely outperforms Sonnet on creative drafting
- Haiku is sufficient for structured classification
- Batch API + prompt caching brings effective cost to ~$0.22/article

**Alternatives considered:**
- Opus on every pass — best quality but ~$1,020 vs $480 for 2000
  articles, marginal quality improvement
- Sonnet everywhere — saves more money, but drafting quality dips
- GPT-4-class for drafting — comparable quality, more vendor switching

**Tradeoffs accepted:**
- Slight orchestration complexity (different models per pass)
- Manage multiple model versions over time
- Need to maintain prompt compatibility across models

### Decision: Curated source library, not live web search

**Context:** Article generation needs grounding in authoritative sources.
Options: live web search via Sonar/Claude native search, or pre-fetched
source library.

**Decision:** Pre-fetched source library in Supabase with selective live
search for news articles.

**Reasoning:**
- For a single-drug niche, ~30-50 sources cover 95% of factual claims
- Pre-fetched sources are pre-verified to exist (eliminates fabricated
  citations)
- Citations resolve consistently across articles
- Sources are tagged by topic for precise retrieval
- Lower cost than per-article live search ($69 total vs $35-65 in live
  search across 500 articles)
- Better E-E-A-T story: documented methodology, auditable source list
- Live search reserved for news articles and verification (~50 articles)

**Alternatives considered:**
- Sonar Pro on every article (~$0.13/article) — recurring cost,
  inconsistent sources across articles
- Claude native web search on every article (~$0.07/article) — cheaper
  than Sonar but still has consistency problem
- No grounding (rely on Claude's training) — unacceptable for YMYL
- Sonar Deep Research — overkill for typical articles at $0.41+/query

**Tradeoffs accepted:**
- Initial source library setup time (Perplexity discovery + verification)
- Source library maintenance overhead (weekly re-fetch cron)
- Less responsive to brand-new sources unless manually added

---

## Architecture Decisions

### Decision: Multi-tenant from day one

**Context:** Building first site (retatrutide) but planning portfolio
of 20 sites. Question: build single-tenant now and refactor later, or
multi-tenant from the start?

**Decision:** Multi-tenant from day one. Every database table has
site_id column referencing sites.id.

**Reasoning:**
- Retrofitting multi-tenancy is expensive: backfilling site_id on
  every row, updating every query, possibly data migration
- Adding site_id columns upfront costs ~15 minutes
- Pipeline code that filters by site_id from day one is the same code
  that supports 20 sites
- Database schema is the hardest thing to change retroactively

**Alternatives considered:**
- Single-tenant for retatrutide, refactor at site #2 — multi-day
  migration when site #2 launches
- Separate Supabase project per site — operational overhead, no
  source library sharing, no cross-site queries
- Multi-tenant via separate schemas — more complex than column-based
  tenancy, no real benefit at this scale

**Tradeoffs accepted:**
- All queries must filter by site_id (small cognitive overhead)
- Slight schema complexity from day one
- RLS policies to add eventually (deferred until team UI)

### Decision: Phase-based, database-mediated pipeline

**Context:** Pipeline has many steps. Question of how to structure them:
monolithic script, function calls, or independent phase modules.

**Decision:** 12 discrete phases, each reads from Supabase, performs
work, writes to Supabase, can be run independently.

**Reasoning:**
- Phases can be re-run individually without restarting pipeline
- Failure in phase 8 doesn't waste phases 1-7 work
- Same architecture works for CLI today and web UI tomorrow (UI just
  calls phase functions)
- Database state is the contract between phases (clear interfaces)
- Idempotent design enables parameter iteration without rebuilds

**Alternatives considered:**
- Monolithic script — failures lose all progress, can't iterate on
  individual steps, harder to reason about
- DAG framework (Airflow, Prefect) — overkill for current scale,
  operational overhead
- Function calls with in-memory state — can't easily expose as service
  later

**Tradeoffs accepted:**
- More code (each phase is its own module)
- Database round-trips between phases (negligible cost)
- Slightly more complex orchestration logic

### Decision: Config-driven, not hardcoded

**Context:** Pipeline behavior needs to vary per site (seeds, niche
terms, taxonomies). Question of how to manage these differences.

**Decision:** YAML config per site. Pipeline code reads config and
behaves accordingly. Never hardcode niche-specific values.

**Reasoning:**
- New sites should be launched by creating YAML, not editing code
- VAs can eventually update configs through a UI without developer
  involvement
- The same code runs all 20 sites — no per-site forks
- Templates can emerge from common patterns across sites later

**Alternatives considered:**
- Hardcoded values, copy code for each site — multiple codebases to
  maintain, drift between sites
- Environment variables only — works for simple config, breaks down
  for structured config like intent taxonomies
- JSON config — YAML is more readable for the editing pattern (humans
  editing structured config)

**Tradeoffs accepted:**
- Config validation complexity (Pydantic models for safety)
- Slightly more code to read config than to reference globals
- YAML parsing overhead (microseconds, irrelevant)

### Decision: Job tracking from day one

**Context:** Pipeline runs need observability. Question of whether to
build job tracking now or add later.

**Decision:** pipeline_jobs table from day one. Every phase logs start,
end, config snapshot, output summary, errors.

**Reasoning:**
- Even for solo CLI usage, helps debug failures and compare runs
- Config snapshots enable reproducing historical results
- When team UI is built, same table powers status displays (no
  retrofit needed)
- Cost is trivial: one table, ~50 rows per run, indexed properly

**Alternatives considered:**
- Print to console only — no historical record, hard to debug after
  the fact
- Log files only — not queryable, breaks the "database as source of
  truth" principle
- Build observability later — would require retrofit and we'd lose
  early runs' data

**Tradeoffs accepted:**
- Every phase needs job tracking boilerplate (mitigated by decorator)
- Storage cost (negligible at this scale)
- Code complexity to handle job status transitions

### Decision: Supabase as source of truth, no intermediate files

**Context:** Pipeline produces lots of intermediate data. Question of
where it lives between phases.

**Decision:** Everything in Supabase tables. No CSV/JSON files between
phases. Local files only for human-review exports (Google Sheets).

**Reasoning:**
- Future UI needs to read pipeline state from somewhere queryable
- Files scattered locally can't be displayed in dashboards
- Files have no natural multi-tenant boundary
- Database state is easier to debug (SQL queries) than file inspection
- Supabase is already required for sites/jobs, doesn't add new infrastructure

**Alternatives considered:**
- CSV intermediate files — simpler for solo CLI but breaks UI integration
- Both DB and files — duplicate state, sync problems
- S3/blob storage for large intermediate data — overkill, Supabase
  handles our scale fine

**Tradeoffs accepted:**
- Slightly slower than pure in-memory pipelines
- Database connection required for every phase
- Schema design effort upfront

---

## Pipeline Design Decisions

### Decision: Intent classification before clustering

**Context:** Sequencing question. Should we cluster keywords first then
classify cluster intent, or classify each keyword first then cluster
within intent buckets?

**Decision:** Classify first, cluster within intent buckets.

**Reasoning:**
- Mixed-intent clusters produce bad articles (e.g., "retatrutide cost"
  and "is retatrutide worth it" should be different articles)
- Per-intent clustering can use HDBSCAN parameters tuned to that
  intent's typical cluster characteristics
- Subfolder assignment becomes trivial (intent maps directly to subfolder)
- Cost increase is small (~$1 in Haiku calls per site)

**Alternatives considered:**
- Cluster first, classify cluster intent — produces mixed clusters
  that need splitting downstream
- Classify within clusters — both passes adds complexity
- Skip classification, rely on clustering — loses important
  organizational signal

**Tradeoffs accepted:**
- Extra phase in pipeline (Phase 08)
- LLM API costs (small)
- Some keywords are genuinely ambiguous between intents (flagged for
  human review)

### Decision: Auto-derive competitors from SERPs, not manual list

**Context:** SERP mining needs competitor domains. Question of whether
to require manual competitor identification or derive automatically.

**Decision:** Phase 3 analyzes URL/domain frequency across seed SERPs,
top N domains by frequency become the auto-derived competitor list for
Phase 5 mining.

**Reasoning:**
- Frequency-derived competitors are objectively the ones competing for
  your seed keywords
- No upfront manual research per site
- Reproducible for site #2 (same process, different seeds → different
  competitors)
- Self-correcting: if seeds are good, competitors are good
- Manual override still possible (config has manual_competitor_domains
  for additions)

**Alternatives considered:**
- Manual competitor list per site — adds 30 minutes per site, can miss
  competitors, requires SEO research skills VAs may not have
- Pure manual + no auto-discovery — same problem
- Auto-discovery only, no manual override — sometimes useful to mine
  known competitors that don't rank for seed keywords

**Tradeoffs accepted:**
- Quality depends on quality of seeds
- May miss niche competitors that don't rank for seed terms
- Slightly more pipeline complexity (Phase 3 doing dual purpose)

### Decision: Single-level SERP mining, no recursion

**Context:** SERP mining could recurse — mine URLs, find new keywords,
mine THOSE keywords' URLs, etc.

**Decision:** Single-level mining only. No recursion.

**Reasoning:**
- Each recursion level drifts further from seed concept
- Level 1 produces keywords still relevant to niche
- Level 2+ produces keywords from broader topical territory
- Level 3+ produces unrelated noise
- Filtering recursion output costs more time than the value it adds

**Alternatives considered:**
- 2-level recursion — keyword pollution outweighs value
- Recursion with strict relevance filter — added complexity, marginal gain
- No SERP mining at all — leaves significant value on the table

**Tradeoffs accepted:**
- Some long-tail keywords missed
- Coverage depth limited to what's reachable in one SERP hop

### Decision: URL frequency-weighted mining

**Context:** Some URLs appear in many seed SERPs ("hub" URLs covering
the niche broadly). Others appear in only one or two SERPs.

**Decision:** Mine hub URLs deeply (top 200 keywords), peripheral URLs
lightly (top 30) or skip entirely (<3 appearances).

**Reasoning:**
- Captures most of the benefit of recursion without the drift
- Hub URLs have broader topical coverage worth mining deeper
- Peripheral URLs add diminishing returns per keyword fetched
- Reduces API cost while improving relevance signal

**Alternatives considered:**
- Mine all URLs equally — wasted API budget on irrelevant URLs
- Mine only hub URLs — misses some valuable peripheral content
- Position-only weighting (depth based on URL's average rank) — less
  predictive of relevance than frequency

**Tradeoffs accepted:**
- Slight code complexity in determining mining depth
- Need threshold tuning (3+ frequency for any mining)

---

## Site Architecture Decisions

### Decision: 12-folder subfolder structure with three-tier hierarchy

**Context:** URL structure decision. Affects every article's URL,
internal linking, sitemap structure, topical authority signals.

**Decision:**
- 12 top-level folders: /about/, /guides/, /dosage/, /safety/,
  /research/, /compare/, /conditions/, /lifestyle/, /glossary/,
  /get/, /legal/, /news/
- Three tiers: root → mini-pillar → leaf
- Hierarchical not flat URL structure

**Reasoning:**
- Topical silos are well-documented Google ranking signal
- Hub-and-spoke structure supports internal linking strategy
- Each folder gets clear topical identity
- Three-tier supports growth from 500 to 2000+ articles
- /get/ as unified commercial silo (not /buy/) reduces YMYL ranking risk
- /legal/ as separate silo recognizes scope of regulatory content

**Alternatives considered:**
- Flat structure (everything at root) — loses silo benefits, harder
  navigation at scale
- /buy/ for commercial content — stronger commercial signal but YMYL
  ranking penalty risk for unapproved drug
- /access/ for commercial content — too soft, doesn't acknowledge
  purchase intent
- Different folder count (8-15) — 12 felt like the right balance
  between specificity and fragmentation

**Tradeoffs accepted:**
- Commits to a structure that's expensive to change later
- 12 folders to maintain (some will grow faster than others)
- Decision about what goes where for ambiguous content

### Decision: Topics-not-keywords as the content unit

**Context:** Article model question. Does each article target one
keyword, or one topic that absorbs many keywords?

**Decision:** Each article targets one topic, with primary keyword +
secondary + supporting + FAQ keywords as supporting content structure.

**Reasoning:**
- Topical depth ranks better than keyword targeting in 2026 Google
- One article serving 20-50 related keywords is stronger than 20
  articles fighting for variants of same query
- Aligns with "topics not keywords" SEO best practice
- Lets clustering pipeline produce article-ready output (one cluster
  = one article)

**Alternatives considered:**
- One keyword per article — produces too many thin articles, keyword
  cannibalization
- One major keyword cluster per article without sub-keyword roles —
  loses information about which keywords inform H2s/H3s/FAQ
- Topic + keyword combination — adopted via topic_keywords.role field

**Tradeoffs accepted:**
- More complex content generation (must address multiple keyword
  intents per article)
- topic_keywords junction table complexity
- Longer articles (target word counts higher to absorb supporting content)

---

## Cost and Quality Decisions

### Decision: Smart routing over premium-everywhere

**Context:** Content generation budget question. Use Opus on every pass
(premium) or route by task complexity (smart)?

**Decision:** Smart routing — Sonnet for outline/review, Opus for
draft/revision, Haiku for utility.

**Reasoning:**
- Cost savings of ~$150 across 500 articles
- Quality differences between Sonnet and Opus are real but mostly
  invisible on outline/review tasks
- Opus's strengths (creative drafting, complex revision) are where
  premium dollars actually matter
- Haiku is sufficient for structured classification

**Alternatives considered:**
- Opus everywhere — best quality, costs $440 vs $150 saved
- Sonnet everywhere — saves more but drafting quality suffers
- GPT-4 for some tasks — vendor switching complexity not worth it

**Tradeoffs accepted:**
- Slightly less consistent style across passes
- Need to test that pipeline works with different models per stage
- Maintain compatibility across model updates

### Decision: Selective live search, not on every article

**Context:** Some articles need timely information (news, recent
trial results). Most articles are evergreen-ish (mechanism, glossary).

**Decision:** Live web search (Claude native, with domain whitelist)
for ~50 of 500 articles. Curated source library for everything else.

**Reasoning:**
- News articles need current data (FDA updates, trial readouts)
- Evergreen articles need consistent source attribution
- Cost per live-search article: ~$0.07
- 50 articles × $0.07 = $5 total in selective search
- vs $35 if applied to all articles

**Alternatives considered:**
- Live search every article — consistency problems, recurring cost
- No live search ever — misses time-sensitive content
- Manual flag per article — added curation overhead, but adopted in
  config via freshness_tier

**Tradeoffs accepted:**
- Need to identify which articles benefit from live search
- Two different generation paths (with/without live search)
- Source library can go stale for time-sensitive content

### Decision: Lean infrastructure, not enterprise-grade

**Context:** Infrastructure budget decision. Real options range from
$50/year (lean) to $500+/year (enterprise).

**Decision:** Start lean (~$50/site/year amortized across 20 sites).
Upgrade specific items when actual constraints bite.

**Specific choices:**
- Supabase Free tier initially, upgrade to Pro when daily backups matter
- GitHub Actions cron, not Railway (free for our usage)
- Cloudflare Pages (free)
- Domain only paid cost (~$12/site)

**Reasoning:**
- Most "defensive" infrastructure spend doesn't pay off until production
  scale issues exist
- Free tiers are sufficient for prototype and early operations
- Easy to upgrade individual services when needed
- Easier to defend a $50/site budget than a $400/site budget

**Alternatives considered:**
- Premium everything (Supabase Pro, Railway, image CDN) — $400+/site,
  most features unused initially
- Even leaner (no Supabase, files only) — breaks the "DB as source of
  truth" principle

**Tradeoffs accepted:**
- Will need to migrate features (e.g., upgrade Supabase) as constraints
  emerge
- Less buffer for traffic spikes
- Manual monitoring (no premium observability tools)

---

## Quality and Risk Decisions

### Decision: YMYL/regulatory awareness, not editorial neutrality

**Context:** Retatrutide is unapproved investigational drug. Content
about it has YMYL implications. Question of how aggressively to
acknowledge this in architecture.

**Decision:** Build YMYL/regulatory tracking into schema and pipeline:
- intent_taxonomy includes ymyl_risk and regulatory_sensitivity flags
- topics table has ymyl_risk, regulatory_sensitivity, freshness_tier
- Generation pipeline applies stricter standards to high-YMYL content
- Source library mandatory for medical claims

**Reasoning:**
- Google's medical content guidelines penalize unsourced YMYL content
- FDA enforcement on health content sites is real risk
- Trust signals matter for ranking and brand
- Cost of building this awareness is small; cost of NOT having it is
  potentially total ranking loss

**Alternatives considered:**
- Treat all content the same — works for non-YMYL niches, dangerous here
- Editorial neutrality without metadata — implicit handling, hard to
  enforce consistency
- More aggressive (separate site disclaimer per article) — overkill,
  hurts user experience

**Tradeoffs accepted:**
- More schema complexity
- More careful content review for high-risk content
- Slower content generation for high-YMYL articles

### Decision: Human-in-the-loop review for clusters

**Context:** Clustering algorithm produces ~500 clusters. Question of
whether to trust algorithm output or require human approval.

**Decision:** Algorithm produces clusters with confidence scores. High-
confidence clusters bulk-approve. Low-confidence clusters get focused
human review. All clusters in regulatory-sensitive intents (VENDOR,
LEGAL, ACCESS) require human review regardless of confidence.

**Reasoning:**
- Topical articles depend on cluster quality — wrong clusters produce
  bad articles
- Spot-checking saves time vs reviewing everything
- Low-confidence clusters are where algorithm is most likely wrong
- Regulatory-sensitive content has highest cost of error

**Alternatives considered:**
- Full algorithmic trust — too risky for YMYL/regulatory niche
- Manual review every cluster — too slow at 500 clusters
- Random sampling — misses the systematic errors that low-confidence
  flagging catches

**Tradeoffs accepted:**
- Review workflow (Google Sheet for v1)
- Time investment per site for cluster review (~2-3 hours)
- Need to handle merge/split actions in pipeline

---

## Future-Proofing Decisions

### Decision: Build for solo CLI now, plan for team UI later

**Context:** Pipeline could be built as CLI scripts or web app.

**Decision:** CLI scripts first, with architecture that supports web UI
later without rewrites.

**Reasoning:**
- 8-hour scope can't deliver web UI
- UI requirements aren't known until pipeline runs against real data
- Phase-based architecture works equally well from CLI or HTTP endpoints
- Database state is shareable across access patterns
- Premature UI building optimizes for assumed needs, not real ones

**Alternatives considered:**
- Build UI first — too much scope, wrong order
- Build CLI, accept rewrite for UI — wastes effort, decoupling decision
  matters
- Hybrid (CLI + minimal HTML review page) — adds 1.5-2 hours, marginal
  value

**Tradeoffs accepted:**
- VAs can't use tool yet
- UI build happens later
- Some context-switching when UI eventually built

### Decision: Templates as future refactor, not initial structure

**Context:** Several patterns will likely be shared across sites
(intent taxonomies, concept categories, subfolder structures). Build
templates upfront or refactor when patterns emerge?

**Decision:** Inline everything in site configs for now. Refactor into
templates after 3-5 sites reveal what should be shared.

**Reasoning:**
- Premature abstraction is a common failure mode
- Don't know what should be templated until multiple instances exist
- Refactoring templates is mechanical and cheap
- Building templates upfront adds complexity for hypothetical needs

**Alternatives considered:**
- Templates from day one — over-engineering, may build wrong
  abstractions
- Never template — code duplication grows linearly with site count

**Tradeoffs accepted:**
- Some YAML duplication across sites until refactor
- Need discipline to actually refactor at the right time
- Risk of forgetting to refactor and accumulating duplication

### Decision: Defer source library generation pipeline

**Context:** Source library is required for content generation. Building
it is a separate ~20-hour effort.

**Decision:** Defer source library tool building. Use Perplexity
manually for initial source discovery. Build pipeline after clustering
is working.

**Reasoning:**
- Source library doesn't block clustering work
- Manual Perplexity workflow is sufficient for first source library
- Building automation before knowing the actual pattern is premature
- Clustering itself is more uncertain and deserves focus

**Alternatives considered:**
- Build everything in parallel — too much scope
- Skip source library entirely — content generation fails downstream
- Use Sonar instead — costs more and produces lower-quality consistency

**Tradeoffs accepted:**
- Manual workflow for initial source library
- Source library tool gets built later (different conversation)
- Risk of source library quality varying without pipeline standards

---

## What We Considered and Decided NOT to Do

### Rejected: Building a SaaS product

This is an internal tool. May grow into a team tool. Will not be
marketed externally, will not have customer billing, will not have
multi-org isolation. The 20-site portfolio is owned operations,
not a customer product.

### Rejected: Multi-language from day one

US English market only for current sites. Multi-language requires
per-language embeddings, classification prompts, SERP fetching. Deferred
indefinitely until specific multi-language site is needed.

### Rejected: Test coverage for MVP

No unit tests, integration tests, or formal QA for the 8-hour build.
Database state is the success signal. Tests can be added when team
adopts the tool and quality regression becomes a real risk.

### Rejected: Sophisticated retry/recovery logic

Pipeline phases re-run on failure (--force flag). Don't build exponential
backoff, circuit breakers, or sophisticated error handling until simple
retry proves insufficient.

### Rejected: Real-time pipeline visibility

No live dashboard, no streaming progress updates. Pipeline runs are
batch operations with start/end logging. Build observability when team
UI exists and operational visibility becomes a real need.

### Rejected: Plugin architecture for clustering algorithms

HDBSCAN is what we're using. Don't build abstractions for swapping in
alternate clustering algorithms until there's a specific reason to use
a different algorithm.

### Rejected: Cross-site content recommendation

Each site is topically isolated. Don't build cross-site article
suggestions or shared content pools until specific use case emerges.

### Rejected: Vector search exposed to end users

pgvector is used internally for clustering. Don't expose semantic
search as a user-facing feature until specifically needed by a site.

---

## Open Questions Not Yet Decided

Documented here so they're not forgotten when they become relevant:

### When does team UI get built?

Trigger: when operating 3+ sites concurrently becomes painful via CLI,
or when first VA is onboarded to run the pipeline. Until then, CLI is
sufficient.

### How are topics and articles linked in production?

Current scope ends at topics table. Article generation reads from there.
Schema for article generation phase (with article_lifecycle, performance
tracking, source citations) is deferred to article generation tool design.

### How do downstream pipelines consume topics?

Interface is the topics + topic_keywords tables. Other systems read
these tables. Changes to that schema affect downstream consumers.
Schema versioning may become necessary.

### What's the source library generation tool look like?

Out of scope for clustering pipeline. Will be designed when actually
building it. May share infrastructure (Supabase, sites table) with
clustering pipeline or may be separate.

### How does internal linking actually work?

Programmatic linking based on topic_relationships table. Rules:
- UP to sub-pillar and pillar (breadcrumbs)
- SIDEWAYS to topically similar articles (embedding similarity)
- DOWN to glossary terms (auto-link)
- Cross-silo bridges (manual or rule-based)

Implementation is deferred to article generation tool.

### What happens when a site's keyword pool grows?

If new keywords appear (new trial results, FDA changes, etc.), pipeline
can be re-run to expand. Topics table integrates new clusters without
disturbing existing approved topics. Process untested in practice.

### How to handle competing sites in same portfolio?

E.g., retatrutide-info.com and tirzepatide-info.com both target
"retatrutide vs tirzepatide" keyword. Currently: each site independently
clusters, may both produce that article. Acceptable for now. May become
issue if portfolio specializes further.

---

## Maintaining This Document

Update this document when:
- New architectural decisions are made
- Existing decisions are reversed or refined
- Open questions get answered
- Patterns emerge that deserve documentation

Don't update for:
- Implementation details (those go in docs/architecture.md)
- Specific parameter values (those go in docs/decisions-log.md as ADRs)
- Phase-specific behavior (those go in docs/pipeline-phases.md)

The principle: this document captures decisions and reasoning at the
architectural level. More granular decisions go in more granular
documents.
