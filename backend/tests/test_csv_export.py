"""M10 — pure CSV generation (PRD §12).

These carry all of M10's correctness coverage because the Storage upload +
signed-URL layer can't run in the sandbox. Exercise the three formats, CSV
formula-injection hardening, blank-metrics columns, empty inputs, and the
topic-grouped zip packing."""

import csv
import io
import zipfile

from app.csv_export import (
    ARCHITECTURE_HEADERS,
    FLAT_HEADERS,
    LINKING_HEADERS,
    build_architecture_csv,
    build_flat_csv,
    build_linking_csv,
    build_topic_grouped_csvs,
    snapshot_timestamp,
    zip_named_csvs,
)


def _parse(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


TOPIC_NAME = {"t1": "Mechanism", "t2": "Practical & Commercial"}
CLUSTER_NAME = {"c1": "How it works", "c2": "Where to buy"}


def _kw(keyword, topic="t1", cluster="c1", sources=None, status="active", rel=0.83):
    return {
        "keyword": keyword,
        "topic_id": topic,
        "cluster_id": cluster,
        "sources": sources if sources is not None else ["keyword_ideas"],
        "status": status,
        "relevance_score": rel,
    }


# ---- flat -----------------------------------------------------------------
def test_flat_headers_and_basic_row():
    out = _parse(build_flat_csv([_kw("how does it work")], TOPIC_NAME, CLUSTER_NAME))
    assert out[0] == FLAT_HEADERS
    row = out[1]
    assert row[0] == "how does it work"
    assert row[1] == "Mechanism"
    assert row[2] == "How it works"
    assert row[3] == "keyword_ideas"
    assert row[4] == "" and row[5] == "" and row[6] == ""  # vol/kd/cpc blank
    assert row[7] == "0.8300"
    assert row[8] == "active"


def test_flat_unassigned_cluster_and_null_relevance():
    rows = _parse(
        build_flat_csv(
            [_kw("orphan kw", cluster=None, rel=None)], TOPIC_NAME, CLUSTER_NAME
        )
    )
    assert rows[1][2] == "Unassigned"
    assert rows[1][7] == ""


def test_flat_multiple_sources_joined():
    rows = _parse(
        build_flat_csv(
            [_kw("kw", sources=["competitor", "autocomplete"])], TOPIC_NAME, CLUSTER_NAME
        )
    )
    assert rows[1][3] == "competitor, autocomplete"


def test_flat_empty_keywords_just_header():
    rows = _parse(build_flat_csv([], TOPIC_NAME, CLUSTER_NAME))
    assert rows == [FLAT_HEADERS]


# ---- CSV formula injection ------------------------------------------------
def test_formula_injection_guarded_on_dangerous_keywords():
    dangerous = ["=cmd()", "+1+1", "-2", "@SUM(A1)", "\ttab", "\rcr"]
    for kw in dangerous:
        rows = _parse(build_flat_csv([_kw(kw)], TOPIC_NAME, CLUSTER_NAME))
        # The cell is neutralized with a leading single quote.
        assert rows[1][0].startswith("'"), f"{kw!r} not guarded"
        assert rows[1][0] == "'" + kw


def test_formula_injection_guards_all_text_columns():
    # A malicious topic/cluster/status value is also neutralized.
    rows = _parse(
        build_flat_csv(
            [_kw("safe", topic="tX", cluster="cX", sources=["=evil"])],
            {"tX": "=danger"},
            {"cX": "=cluster"},
        )
    )
    assert rows[1][1].startswith("'")  # topic
    assert rows[1][2].startswith("'")  # cluster
    assert rows[1][3].startswith("'")  # source


def test_safe_keyword_not_modified():
    rows = _parse(build_flat_csv([_kw("retatrutide dosage")], TOPIC_NAME, CLUSTER_NAME))
    assert rows[1][0] == "retatrutide dosage"


def test_numeric_relevance_never_guarded():
    # 0.83 -> "0.8300", a digit lead, so the guard is a no-op (no apostrophe).
    rows = _parse(build_flat_csv([_kw("kw", rel=0.83)], TOPIC_NAME, CLUSTER_NAME))
    assert rows[1][7] == "0.8300"


# ---- topic_grouped --------------------------------------------------------
def test_topic_grouped_one_csv_per_topic():
    kws = [
        _kw("a", topic="t1"),
        _kw("b", topic="t1"),
        _kw("c", topic="t2"),
    ]
    named = build_topic_grouped_csvs(kws, TOPIC_NAME, CLUSTER_NAME)
    assert len(named) == 2
    blob = zip_named_csvs(named)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = zf.namelist()
    assert all(n.endswith(".csv") for n in names)
    # Each per-topic CSV has its header + only that topic's rows.
    contents = {n: _parse(zf.read(n).decode("utf-8")) for n in names}
    counts = sorted(len(rows) - 1 for rows in contents.values())  # minus header
    assert counts == [1, 2]


def test_topic_grouped_filename_collision_disambiguated():
    # Two distinct topic ids whose names slug identically must not overwrite.
    kws = [_kw("a", topic="t1"), _kw("b", topic="t2")]
    named = build_topic_grouped_csvs(
        kws, {"t1": "Cost!!!", "t2": "Cost???"}, CLUSTER_NAME
    )
    filenames = [n for n, _ in named]
    assert len(set(filenames)) == 2


def test_topic_grouped_empty():
    assert build_topic_grouped_csvs([], TOPIC_NAME, CLUSTER_NAME) == []


# ---- architecture ---------------------------------------------------------
ARCH_JSON = {
    "pillars": [
        {
            "topic_id": "t1",
            "silo_name": "Mechanism",
            "title": "How Retatrutide Works",
            "target_keyword": "how retatrutide works",
            "summary": "...",
            "h2_outline": ["What is it", "The receptors"],
            "supporting_article_ids": ["c1"],
            "lateral_pillar_links": ["t2"],
        },
        {
            "topic_id": "t2",
            "silo_name": "Practical",
            "title": "Getting Retatrutide",
            "target_keyword": "how to get retatrutide",
            "h2_outline": ["Cost"],
            "supporting_article_ids": [],
            "lateral_pillar_links": [],
        },
    ],
    "supporting_articles": [
        {
            "article_id": "c1",
            "name": "Triple agonism explained",
            "intent": "informational",
            "parent_pillar_topic_id": "t1",
            "lateral_article_links": [],
        }
    ],
}


def test_architecture_rows():
    article_name = {"c1": "Triple agonism explained"}
    pillar_title = {"t1": "How Retatrutide Works", "t2": "Getting Retatrutide"}
    target_kw = {"c1": "what is triple agonism"}
    h2s = {"c1": ["Definition", "Mechanism"]}
    out = _parse(
        build_architecture_csv(ARCH_JSON, article_name, pillar_title, target_kw, h2s)
    )
    assert out[0] == ARCHITECTURE_HEADERS
    pillar = out[1]
    assert pillar[0] == "pillar"
    assert pillar[1] == "How Retatrutide Works"
    assert pillar[3] == ""  # pillar has no parent
    assert pillar[4] == "What is it | The receptors"
    # down-link to its supporting article + lateral pillar link, name-resolved.
    assert "Triple agonism explained" in pillar[5]
    assert "Getting Retatrutide" in pillar[5]
    # supporting article row.
    supp = out[3]
    assert supp[0] == "supporting"
    assert supp[1] == "Triple agonism explained"
    assert supp[2] == "what is triple agonism"
    assert supp[3] == "How Retatrutide Works"  # parent pillar (up-link)
    assert supp[4] == "Definition | Mechanism"
    assert "How Retatrutide Works" in supp[5]  # up-link in links_out


def test_architecture_empty_json():
    out = _parse(build_architecture_csv({}, {}, {}, {}, {}))
    assert out == [ARCHITECTURE_HEADERS]


# ---- linking (edge list) --------------------------------------------------
def test_linking_csv_emits_one_row_per_edge_with_resolved_names():
    arch = {
        "pillars": [
            {
                "topic_id": "topic-mech",
                "title": "How Retatrutide Works",
                "supporting_article_ids": ["a1", "a2"],
                "lateral_pillar_links": ["topic-dose"],
            },
            {
                "topic_id": "topic-dose",
                "title": "Retatrutide Dosing",
                "supporting_article_ids": ["a3"],
                "lateral_pillar_links": [],
            },
        ],
        "supporting_articles": [
            {
                "article_id": "a1",
                "name": "Triple agonism explained",
                "parent_pillar_topic_id": "topic-mech",
                "lateral_article_links": ["a2"],
            },
            {
                "article_id": "a2",
                "name": "Mechanism deep dive",
                "parent_pillar_topic_id": "topic-mech",
                "lateral_article_links": [],
            },
            {
                "article_id": "a3",
                "name": "Dose escalation schedule",
                "parent_pillar_topic_id": "topic-dose",
                "lateral_article_links": ["a1"],
            },
        ],
    }
    csv_text = build_linking_csv(
        arch,
        article_name_by_id={
            "a1": "Triple agonism explained",
            "a2": "Mechanism deep dive",
            "a3": "Dose escalation schedule",
        },
        pillar_title_by_topic={
            "topic-mech": "How Retatrutide Works",
            "topic-dose": "Retatrutide Dosing",
        },
    )
    rows = _parse(csv_text)
    assert rows[0] == LINKING_HEADERS

    # Cast to a set-of-tuples for order-insensitive comparison; the function
    # produces a deterministic order but we assert on edge content, not order.
    edges = {tuple(r) for r in rows[1:]}
    # Pillar -> articles (down-links)
    assert ("How Retatrutide Works", "pillar", "Triple agonism explained", "article", "pillar_to_article") in edges
    assert ("How Retatrutide Works", "pillar", "Mechanism deep dive", "article", "pillar_to_article") in edges
    assert ("Retatrutide Dosing", "pillar", "Dose escalation schedule", "article", "pillar_to_article") in edges
    # Pillar -> pillar (lateral)
    assert ("How Retatrutide Works", "pillar", "Retatrutide Dosing", "pillar", "pillar_to_pillar") in edges
    # Article -> pillar (up-link)
    assert ("Triple agonism explained", "article", "How Retatrutide Works", "pillar", "article_to_pillar") in edges
    assert ("Dose escalation schedule", "article", "Retatrutide Dosing", "pillar", "article_to_pillar") in edges
    # Article -> article (lateral peer)
    assert ("Triple agonism explained", "article", "Mechanism deep dive", "article", "article_to_article") in edges
    assert ("Dose escalation schedule", "article", "Triple agonism explained", "article", "article_to_article") in edges
    # Total: 3 down + 1 pillar-lateral + 3 up + 2 article-lateral = 9
    assert len(edges) == 9


def test_linking_csv_skips_article_to_pillar_when_parent_unresolved():
    # A supporting article whose parent_pillar_topic_id doesn't resolve to a
    # pillar title gets no up-link row — better an honest omission than a row
    # pointing at a stale or empty title.
    arch = {
        "pillars": [],
        "supporting_articles": [
            {"article_id": "a1", "name": "Orphan",
             "parent_pillar_topic_id": "missing", "lateral_article_links": []},
        ],
    }
    rows = _parse(build_linking_csv(arch, {"a1": "Orphan"}, {}))
    assert rows == [LINKING_HEADERS]


def test_linking_csv_falls_back_to_ids_when_names_missing():
    # A lateral link to an article id with no name in the resolver renders the
    # raw id rather than dropping the edge — the export is for human review.
    arch = {
        "pillars": [{"topic_id": "t1", "title": "T",
                     "supporting_article_ids": ["a-ghost"],
                     "lateral_pillar_links": []}],
        "supporting_articles": [],
    }
    rows = _parse(build_linking_csv(arch, {}, {"t1": "T"}))
    # The pillar -> ghost article edge survives, with the raw id as the title.
    assert ("T", "pillar", "a-ghost", "article", "pillar_to_article") in {tuple(r) for r in rows[1:]}


def test_linking_csv_empty_architecture():
    assert _parse(build_linking_csv({}, {}, {})) == [LINKING_HEADERS]


# ---- misc -----------------------------------------------------------------
def test_snapshot_timestamp_is_filesystem_safe():
    ts = snapshot_timestamp()
    assert ":" not in ts and "/" not in ts and ts.endswith("Z")
