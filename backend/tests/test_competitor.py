from app.dataforseo import DataForSEOClient, DataForSEOError
from app.pipeline.competitor import MineTopic, run_competitor_mining


def test_domain_of_strips_scheme_www_and_path():
    assert DataForSEOClient.domain_of("https://www.Example.com/a/b?x=1") == "example.com"
    assert DataForSEOClient.domain_of("http://sub.example.com/page") == "sub.example.com"
    assert DataForSEOClient.domain_of("not a url") is None


def test_ranked_keywords_parses_keyword_data(monkeypatch):
    c = DataForSEOClient(base_url="http://x", login="l", password="p")
    fake_task = {
        "result": [
            {
                "items": [
                    {"keyword_data": {"keyword": "kw one"}},
                    {"keyword_data": {"keyword": "kw two"}},
                    {"keyword_data": {}},  # no keyword -> skipped
                    "junk",  # non-dict -> skipped
                ]
            }
        ]
    }
    monkeypatch.setattr(c, "_post", lambda path, payload: fake_task)
    assert c.ranked_keywords("example.com") == ["kw one", "kw two"]


def test_serp_top_urls_pulls_only_organic_capped(monkeypatch):
    c = DataForSEOClient(base_url="http://x", login="l", password="p")
    fake_task = {
        "result": [
            {
                "items": [
                    {"type": "organic", "url": "https://a.com/1"},
                    {"type": "people_also_ask", "url": "https://nope.com"},
                    {"type": "organic", "url": "https://b.com/2"},
                    {"type": "organic", "url": "https://c.com/3"},
                ]
            }
        ]
    }
    monkeypatch.setattr(c, "_post", lambda path, payload: fake_task)
    assert c.serp_top_urls("seed", top_n=2) == ["https://a.com/1", "https://b.com/2"]


class FakeDFS:
    def __init__(self, *, serp=None, ranked=None, serp_fail=(), ranked_fail=()):
        self.serp = serp or {}            # anchor -> [urls]
        self.ranked = ranked or {}        # domain -> [keywords]
        self.serp_fail = set(serp_fail)   # anchors that raise
        self.ranked_fail = set(ranked_fail)  # domains that raise

    def serp_top_urls(self, keyword, top_n=5):
        if keyword in self.serp_fail:
            raise DataForSEOError("serp boom")
        return list(self.serp.get(keyword, []))[:top_n]

    def ranked_keywords(self, target_domain, limit=500, max_position=20):
        if target_domain in self.ranked_fail:
            raise DataForSEOError("ranked boom")
        return list(self.ranked.get(target_domain, []))

    domain_of = staticmethod(DataForSEOClient.domain_of)


def test_mining_aggregates_dedupes_domains_and_tags_competitor():
    dfs = FakeDFS(
        serp={"retatrutide benefits": [
            "https://www.drugs.com/a", "https://drugs.com/b",  # same domain -> mined once
            "https://wikipedia.org/x",
        ]},
        ranked={
            "drugs.com": ["Retatrutide Benefits", "side effects"],
            "wikipedia.org": ["retatrutide"],
        },
    )
    r = run_competitor_mining(
        topics=[MineTopic(id="t1", anchor="retatrutide benefits", name="Benefits")],
        dfs=dfs,
    )
    kws = r.per_topic["t1"]
    assert set(kws) == {"retatrutide benefits", "side effects", "retatrutide"}
    assert kws["retatrutide benefits"] == ["competitor"]
    assert r.degraded_notes == []


def test_mining_empty_topics_returns_empty():
    r = run_competitor_mining(topics=[], dfs=FakeDFS())
    assert r.per_topic == {}
    assert r.total_keywords == 0


def test_serp_failure_degrades_that_topic_only():
    dfs = FakeDFS(
        serp={"good anchor": ["https://x.com/1"]},
        ranked={"x.com": ["kw"]},
        serp_fail=("bad anchor",),
    )
    r = run_competitor_mining(
        topics=[
            MineTopic(id="t1", anchor="bad anchor", name="Bad"),
            MineTopic(id="t2", anchor="good anchor", name="Good"),
        ],
        dfs=dfs,
    )
    assert r.per_topic["t1"] == {}  # degraded
    assert set(r.per_topic["t2"]) == {"kw"}
    assert any("Bad" in n and "SERP" in n for n in r.degraded_notes)


def test_ranked_keywords_failure_degrades_that_domain_only():
    dfs = FakeDFS(
        serp={"a": ["https://ok.com/1", "https://broken.com/2"]},
        ranked={"ok.com": ["good kw"]},
        ranked_fail=("broken.com",),
    )
    r = run_competitor_mining(
        topics=[MineTopic(id="t1", anchor="a", name="Silo")], dfs=dfs
    )
    assert set(r.per_topic["t1"]) == {"good kw"}
    assert any("broken.com" in n for n in r.degraded_notes)
