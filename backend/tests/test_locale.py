"""E1 per-country locale (2026-06-17): the DataForSEO client must send the
session's location_code, defaulting to US, and the session helper must coerce
unknown/missing values back to US."""

from app.dataforseo import DataForSEOClient
from app.storage.silo import (
    DEFAULT_LOCATION_CODE,
    SUPPORTED_LOCATION_CODES,
    session_location_code,
)


def _capture_payload(monkeypatch, client):
    seen: dict = {}

    def fake_post(path, payload):
        seen["payload"] = payload
        # minimal well-formed shape for serp_top_urls
        return {"result": [{"items": []}]}

    monkeypatch.setattr(client, "_post", fake_post)
    client.serp_top_urls("seed", top_n=2)
    return seen["payload"][0]


def test_default_client_sends_us_en(monkeypatch):
    c = DataForSEOClient(base_url="http://x", login="l", password="p")
    item = _capture_payload(monkeypatch, c)
    assert item["location_code"] == 2840
    assert item["language_code"] == "en"


def test_client_sends_configured_location(monkeypatch):
    c = DataForSEOClient(base_url="http://x", login="l", password="p", location_code=2826)
    item = _capture_payload(monkeypatch, c)
    assert item["location_code"] == 2826  # UK
    assert item["language_code"] == "en"  # English stays "en" across markets


def test_all_supported_markets_are_codes():
    assert SUPPORTED_LOCATION_CODES == frozenset({2840, 2826, 2124, 2036, 2554})
    assert DEFAULT_LOCATION_CODE == 2840


def test_session_location_code_defaults_and_validates():
    assert session_location_code({"location_code": 2554}) == 2554       # NZ, supported
    assert session_location_code({"location_code": 2840}) == 2840       # US
    assert session_location_code({}) == 2840                            # missing -> US
    assert session_location_code({"location_code": None}) == 2840       # null -> US
    assert session_location_code({"location_code": 9999}) == 2840       # unknown -> US
