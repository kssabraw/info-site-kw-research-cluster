"""Brief Generator pipeline orchestration (M13 slice 5b).

`generate_brief` runs the answer-engine-first flow end to end:

  sources (Step 1-2) → intent (Step 3 + A1) → title/scope (Step 3.5)
  → main entity (Step 3.6) → MCS H2 skeleton (Steps 7-8, gate-prefiltered)
  → assemble the v2.6 BriefOutput (Step 11).

Deps are injected (`BriefDeps`) so the orchestration is testable; `build_brief_deps`
constructs the real clients, including the DUAL embedding spaces (aio §0 #1): OpenAI
`text-embedding-3-large` for the organic gates + ChatGPT proximity, and Gemini
(RETRIEVAL_* task types) for AIO proximity — the Gemini path is invoked DIRECTLY here,
independent of the app-wide `embedding_provider` (which stays openai). Persona /
authority / H3 / FAQ enrichment (5c) layer onto the BriefOutput after this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .assemble import build_brief_output
from .entity import derive_main_entity
from .faq import generate_faqs
from .gates import prefilter
from .intent import classify_intent
from .mcs import MCSDeps, run_mcs
from .models import BriefOutput
from .persona import generate_persona
from .sources import gather_sources
from .title import generate_title_scope

EmbedFn = Callable[[list[str]], list[list[float]]]


@dataclass
class BriefDeps:
    dfs: object                 # DataForSEOClient (bound to the session location_code)
    scrapeowl: object           # ScrapeOwlClient (discussion-thread content)
    np_extract: object          # spaCy noun-phrase extractor (entity derivation)
    embed_3large: EmbedFn       # OpenAI text-embedding-3-large (gates + ChatGPT proximity)
    embed_aio_query: EmbedFn    # Gemini RETRIEVAL_QUERY (candidate headings)
    embed_aio_doc: EmbedFn      # Gemini RETRIEVAL_DOCUMENT (AIO answer points)
    gen_llm: object             # Haiku — MCS candidate generation
    intent_llm: object          # Haiku — intent + A1 classification
    title_llm: object           # Sonnet — title/scope


def build_brief_deps(location_code: int) -> BriefDeps:
    """Construct the real egress clients (lazy imports keep the pure modules importable
    without httpx/openai/spaCy). Builds the two Gemini embedders (asymmetric retrieval
    task types) directly — independent of `embedding_provider`."""
    from openai import OpenAI

    from app.config import get_settings
    from app.dataforseo import get_dataforseo
    from app.llm.anthropic_client import AnthropicLLM
    from app.llm.embeddings import GeminiEmbedder, OpenAIEmbedder
    from app.sie.scrapeowl_client import ScrapeOwlClient

    from .entity import build_np_extractor

    s = get_settings()
    large = OpenAIEmbedder(OpenAI(api_key=s.openai_api_key), s.brief_embedding_model_large)
    gem_q = GeminiEmbedder(
        api_key=s.gemini_api_key, model=s.gemini_embedding_model,
        output_dim=s.gemini_embedding_dim, task_type=s.brief_aio_query_task_type,
        max_workers=s.gemini_embedding_max_workers,
    )
    gem_d = GeminiEmbedder(
        api_key=s.gemini_api_key, model=s.gemini_embedding_model,
        output_dim=s.gemini_embedding_dim, task_type=s.brief_aio_doc_task_type,
        max_workers=s.gemini_embedding_max_workers,
    )
    return BriefDeps(
        dfs=get_dataforseo(location_code),
        scrapeowl=ScrapeOwlClient(
            s.scrapeowl_api_key, s.scrapeowl_base_url,
            cost_per_scrape=s.scrapeowl_cost_per_scrape,
            cost_per_scrape_premium=s.scrapeowl_cost_per_scrape_premium,
            premium_on_5xx=s.sie_scrapeowl_premium_on_500,
            max_attempts=s.sie_max_transport_attempts,
        ),
        np_extract=build_np_extractor(),
        embed_3large=large.embed,
        embed_aio_query=gem_q.embed,
        embed_aio_doc=gem_d.embed,
        gen_llm=AnthropicLLM(api_key=s.anthropic_api_key, model=s.brief_gen_model),
        intent_llm=AnthropicLLM(api_key=s.anthropic_api_key, model=s.brief_intent_model),
        title_llm=AnthropicLLM(api_key=s.anthropic_api_key, model=s.brief_title_model),
    )


def generate_brief(keyword: str, *, location_code: int, deps: BriefDeps) -> BriefOutput:
    """Run the brief pipeline for one keyword and return the v2.6 BriefOutput. Raises on
    a load-bearing failure (SERP / title) — there is no degraded-brief fallback (owner
    rule); the caller (the metered job) marks the run errored."""
    sources = gather_sources(keyword, deps.dfs, scrapeowl=deps.scrapeowl)
    serp_titles = [o.get("title") or "" for o in sources.organic]
    serp_metas = [o.get("description") or "" for o in sources.organic]

    intent = classify_intent(
        keyword, serp_titles=serp_titles, serp_h2s=[], paa=sources.paa, llm=deps.intent_llm,
    )
    title = generate_title_scope(
        keyword, intent_type=intent.intent_type, serp_titles=serp_titles,
        serp_h1s=serp_titles, serp_metas=serp_metas, llm_answers=sources.llm_answers,
        llm=deps.title_llm,
    )
    entity = derive_main_entity(
        aio_answer=sources.aio.get("answer_text", ""), aio_present=bool(sources.aio.get("present")),
        title=title.title, keyword=keyword, np_extract=deps.np_extract,
        embed_fn=deps.embed_3large, comparison_intent=(intent.intent_type == "comparison"),
    )

    topic_vec = deps.embed_3large([keyword])[0]

    def gate_fn(cands: list[str]) -> list[str]:
        # Eligibility pre-filter (X.3): on-topic to the keyword + not a bare restatement
        # of the title (cross-candidate redundancy is handled by MCS coverage).
        results = prefilter(
            cands, topic_vec=topic_vec, references=[title.title], main_entity=entity,
            embed_fn=deps.embed_3large,
        )
        return [r.heading for r in results if r.passed]

    tpl = intent.intent_format_template
    mcs = run_mcs(
        entity=entity.canonical, aio=sources.aio,
        chatgpt_answer=sources.llm_answers.get("chat_gpt"), keyword=keyword,
        deps=MCSDeps(
            gen_llm=deps.gen_llm, embed_aio_query=deps.embed_aio_query,
            embed_aio_doc=deps.embed_aio_doc, embed_3large=deps.embed_3large,
        ),
        min_count=tpl.get("min_h2_count", 3), max_count=tpl.get("max_h2_count", 12),
        gate_fn=gate_fn,
    )

    # Step 6 persona (informational; degrades to empty) — gap questions feed the FAQ pool.
    h2_texts = [s.text for s in mcs.selected]
    persona = generate_persona(
        keyword, intent_type=intent.intent_type, title=title.title,
        scope_statement=title.scope_statement, serp_h1s=serp_titles, serp_metas=serp_metas,
        candidate_headings=h2_texts, llm=deps.intent_llm,
    )
    # Steps 10/10.5 FAQ generation + intent gate.
    faqs, faq_meta = generate_faqs(
        paa=sources.paa, discussions=sources.reddit, persona_gaps=persona.gap_questions,
        intent_type=intent.intent_type, title=title.title, scope_statement=title.scope_statement,
        primary_goal=persona.primary_goal, heading_texts=[title.title, *h2_texts],
        embed_3large=deps.embed_3large, classify_llm=deps.gen_llm, concern_llm=deps.gen_llm,
    )

    return build_brief_output(
        keyword=keyword, intent=intent, title=title, entity=entity, mcs=mcs, sources=sources,
        persona=persona, faqs=faqs, extra_metadata=faq_meta,
    )
