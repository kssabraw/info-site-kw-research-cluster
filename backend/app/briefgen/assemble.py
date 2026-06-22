"""Brief Generator Step 11 — assemble the v2.6 Brief Output (M13 slice 5b).

Pure: combines the upstream pieces (intent, title/scope, main entity, MCS-selected H2s,
sources) into the `BriefOutput` (Writer Input A). H3 selection / persona / authority /
FAQ enrich this in 5c — they default empty here and the output is already valid.
"""

from __future__ import annotations

from statistics import mean

from .entity import MainEntity
from .intent import IntentResult
from .mcs import MCSResult
from .models import SCHEMA_VERSION, BriefOutput
from .sources import BriefSources
from .title import TitleScope


def build_brief_output(
    *, keyword: str, intent: IntentResult, title: TitleScope, entity: MainEntity,
    mcs: MCSResult, sources: BriefSources,
) -> BriefOutput:
    """Assemble the v2.6 BriefOutput. heading_structure = H1 (the title, verbatim per the
    Writer's D6 contract) + the MCS-selected H2s; discarded MCS candidates are recorded
    with their proximity scores for the X.6 measurement loop / spin-off intel."""
    headings: list[dict] = [{
        "text": title.title, "type": "content", "level": "H1", "order": 1, "source": "title",
    }]
    for i, sh in enumerate(mcs.selected, start=2):
        headings.append({
            "text": sh.text, "type": "content", "level": "H2", "order": i, "source": "mcs",
            # answer-engine proximity readouts (X.8) — extra fields kept by extra="allow".
            "aio_cosine": round(sh.aio_headline, 4),
            "chatgpt_cosine": round(sh.chatgpt_cosine, 4),
            "mcs_blended": round(sh.blended, 4),
        })

    discarded = [{
        "text": d.text, "reason": "not_selected_by_mcs",
        "aio_cosine": round(d.aio_headline, 4), "chatgpt_cosine": round(d.chatgpt_cosine, 4),
    } for d in mcs.discarded]

    selected = mcs.selected
    metadata = {
        "brief_schema_version": SCHEMA_VERSION,
        "main_entity": {
            "canonical": entity.canonical, "variants": entity.variants,
            "source": entity.source, "confidence": entity.confidence,
            "multi_entity_flag": entity.multi_entity_flag,
            "secondary_entity": entity.secondary_entity, "emq_identical": entity.emq_identical,
        },
        "mcs": {
            "pool_size": len(mcs.pool), "selected_count": len(selected),
            "aio_present": bool(sources.aio.get("present")),
            "chatgpt_present": bool((sources.llm_answers.get("chat_gpt") or "").strip()),
            "set_mean_aio_cosine": round(mean([s.aio_headline for s in selected]), 4) if selected else 0.0,
            "set_mean_chatgpt_cosine": round(mean([s.chatgpt_cosine for s in selected]), 4) if selected else 0.0,
        },
        "decision_fit_qualifies": intent.decision_fit_qualifies,
        "sources": {
            "organic": len(sources.organic), "paa": len(sources.paa),
            "discussions": len(sources.reddit), "llm_answers": sorted(sources.llm_answers),
        },
    }

    return BriefOutput(
        schema_version=SCHEMA_VERSION,
        keyword=keyword,
        h1=title.title, title=title.title, title_rationale=title.title_rationale,
        scope_statement=title.scope_statement,
        intent_type=intent.intent_type, intent_confidence=intent.intent_confidence,
        intent_review_required=intent.intent_review_required,
        intent_format_template=intent.intent_format_template,
        format_directives=intent.format_directives,           # dict -> FormatDirectives (coerced)
        heading_structure=headings,
        faqs=[], persona=None,                                  # 5c enrichment
        discarded_headings=discarded,
        metadata=metadata,
    )
