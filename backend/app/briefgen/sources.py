"""Brief Generator Steps 1-2 — source gathering (M13 slice 2).

Fetches the candidate-source bundle the later slices (intent, gates, MCS) consume:
the SERP (organic results + headings via the shared SIE scrape), the **AI Overview**
answer (X.1 — an MCS scoring target), PAA, Reddit discussions, autocomplete +
keyword suggestions, and the **LLM fan-out** answers (ChatGPT + Gemini — the other
MCS targets; E4 trims Claude + Perplexity).

The DataForSEO egress is thin (`dataforseo/client.py` returns raw items[]); the
parsers here are PURE and unit-tested with fixtures. The Reddit / LLM-Responses /
AIO shapes are docs-derived — confirm on the first deployed brief run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.concurrency import ContextThreadPoolExecutor

logger = logging.getLogger(__name__)

# E4: the answer-engine fan-out is ChatGPT + Gemini only (Claude + Perplexity dropped).
DEFAULT_LLM_PROVIDERS = ("chat_gpt", "gemini")


# ----- pure parsers ---------------------------------------------------------


def parse_organic(items: list[dict], depth: int = 20) -> list[dict]:
    """Top organic results with metadata (url/title/description/rank)."""
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "organic":
            continue
        url = item.get("url")
        if not url:
            continue
        out.append({
            "url": url,
            "title": item.get("title"),
            "description": item.get("description"),
            "rank": _coerce_int(item.get("rank_absolute")) or len(out) + 1,
        })
        if len(out) >= depth:
            break
    return out


def parse_paa(items: list[dict]) -> list[str]:
    """People-Also-Ask questions from the SERP items."""
    questions: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "people_also_ask":
            continue
        for q in item.get("items") or []:
            title = q.get("title") if isinstance(q, dict) else None
            if title:
                questions.append(title)
    return questions


def parse_aio(items: list[dict]) -> dict:
    """X.1 AI-Overview target: {present, answer_text, cited_sources}. Absent AIO is a
    normal, common case (`present: False`) the answer-engine path degrades on."""
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "ai_overview":
            continue
        texts: list[str] = []
        if isinstance(item.get("text"), str):
            texts.append(item["text"])
        for el in item.get("items") or []:
            if isinstance(el, dict) and isinstance(el.get("text"), str):
                texts.append(el["text"])
        sources: list[dict] = []
        for ref in item.get("references") or []:
            if not isinstance(ref, dict):
                continue
            url = ref.get("url")
            if url:
                sources.append({
                    "url": url, "domain": ref.get("domain"), "title": ref.get("title"),
                })
        return {
            "present": True,
            "answer_text": "\n".join(t for t in texts if t).strip(),
            "cited_sources": sources,
        }
    return {"present": False, "answer_text": "", "cited_sources": []}


def parse_reddit(items: list[dict], limit: int = 10) -> list[dict]:
    """Reddit discussion results (organic items from the site:reddit.com SERP)."""
    from urllib.parse import urlparse

    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "organic":
            continue
        url = item.get("url")
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        if host != "reddit.com" and not host.endswith(".reddit.com"):
            continue
        out.append({
            "title": item.get("title"), "url": url,
            "description": item.get("description"),
        })
        if len(out) >= limit:
            break
    return out


def parse_llm_answer(items: list[dict]) -> str | None:
    """One LLM's answer text from the AI-Optimization "LLM Responses" items. The exact
    shape is docs-derived, so we pull text from the common keys / nested blocks
    defensively (confirm live)."""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("text", "message", "content", "answer"):
            if isinstance(item.get(key), str):
                parts.append(item[key])
        for sub in (item.get("sections") or []) + (item.get("items") or []):
            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                parts.append(sub["text"])
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def _coerce_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ----- orchestration --------------------------------------------------------


@dataclass
class BriefSources:
    keyword: str
    organic: list[dict] = field(default_factory=list)
    aio: dict = field(default_factory=lambda: {"present": False, "answer_text": "", "cited_sources": []})
    paa: list[str] = field(default_factory=list)
    reddit: list[dict] = field(default_factory=list)
    autocomplete: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    llm_answers: dict[str, str] = field(default_factory=dict)  # {provider: answer_text}


def gather_sources(
    keyword: str, dfs, *, depth: int = 20, llm_prompt: str | None = None,
    llm_providers: tuple[str, ...] = DEFAULT_LLM_PROVIDERS, max_workers: int = 6,
) -> BriefSources:
    """Run Steps 1-2 concurrently and assemble `BriefSources`. Per-source failures
    degrade that source (logged) rather than failing the brief here; the pipeline
    slice decides which sources are load-bearing. The shared SERP call (Step 1) yields
    organic + AIO + PAA together (E2/E3)."""
    prompt = llm_prompt or keyword
    src = BriefSources(keyword=keyword)

    def _serp() -> None:
        items = dfs.serp_advanced_items(keyword, depth=depth)
        src.organic = parse_organic(items, depth)
        src.aio = parse_aio(items)
        src.paa = parse_paa(items)

    def _reddit() -> None:
        src.reddit = parse_reddit(dfs.reddit_serp_items(keyword))

    def _autocomplete() -> None:
        src.autocomplete = dfs.autocomplete(keyword)

    def _suggestions() -> None:
        src.suggestions = dfs.keyword_suggestions(keyword)

    def _llm(provider: str):
        def run() -> None:
            src.llm_answers[provider] = parse_llm_answer(
                dfs.llm_response_items(prompt, provider)
            ) or ""
        return run

    tasks = [_serp, _reddit, _autocomplete, _suggestions, *(_llm(p) for p in llm_providers)]

    def _safe(fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — one bad source degrades, not the brief
            logger.warning(
                "brief_source_failed",
                extra={"event": "brief_source_failed", "source": fn.__name__,
                       "keyword": keyword, "reason": repr(exc)},
            )

    with ContextThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_safe, tasks))
    return src
