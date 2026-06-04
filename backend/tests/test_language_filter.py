"""Tests for the language ID filter factory (`app/pipeline/language.py`).

The detector model itself isn't tested here — that's lingua-py's job. We assert
the wrapper's contract: it returns None when lingua is unavailable, the
returned callable returns True only for confidently-non-English strings, and
short/empty inputs never trip a false positive.
"""

from __future__ import annotations

import sys
import types
from importlib import reload

import pytest


def _install_fake_lingua(monkeypatch, *, english_score: float, top_lang: str = "DUTCH"):
    """Inject a stub `lingua` module so `make_language_filter` can be tested
    deterministically without the real model files. The fake reports
    `english_score` for ENGLISH and (1 - english_score) for `top_lang`."""

    class _FakeLanguageMeta(type):
        # Stub `Language.<ANY_NAME>` -> a `_FakeLanguage` instance, so the test
        # doesn't need to enumerate every language in `DEFAULT_LANGUAGES`.
        _cache: dict[str, "_FakeLanguage"] = {}

        def __getattr__(cls, name):
            if name.isupper():
                inst = cls._cache.get(name)
                if inst is None:
                    inst = cls._cache[name] = cls(name)
                return inst
            raise AttributeError(name)

    class _FakeLanguage(metaclass=_FakeLanguageMeta):
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, _FakeLanguage) and self.name == other.name

        def __hash__(self):
            return hash(self.name)

    class _Conf:
        def __init__(self, language, value):
            self.language = language
            self.value = value

    class _FakeDetector:
        def compute_language_confidence_values(self, text):
            top = getattr(_FakeLanguage, top_lang)
            other = _FakeLanguage.ENGLISH
            if english_score >= 0.5:
                return [_Conf(other, english_score), _Conf(top, 1 - english_score)]
            return [_Conf(top, 1 - english_score), _Conf(other, english_score)]

    class _FakeBuilder:
        def __init__(self, langs):
            self._langs = langs

        def build(self):
            return _FakeDetector()

        @classmethod
        def from_languages(cls, *langs):
            return cls(list(langs))

    fake = types.ModuleType("lingua")
    fake.Language = _FakeLanguage
    fake.LanguageDetectorBuilder = _FakeBuilder
    monkeypatch.setitem(sys.modules, "lingua", fake)


def _fresh_language_module():
    """Re-import the language module so a stubbed `lingua` takes effect."""
    from app.pipeline import language  # noqa: PLC0415

    return reload(language)


def test_returns_none_when_lingua_is_unavailable(monkeypatch):
    # Drop lingua from sys.modules and block re-import.
    monkeypatch.setitem(sys.modules, "lingua", None)
    language = _fresh_language_module()
    assert language.make_language_filter() is None


def test_filters_confident_non_english(monkeypatch):
    _install_fake_lingua(monkeypatch, english_score=0.2)  # 0.8 Dutch
    language = _fresh_language_module()
    f = language.make_language_filter(confidence_threshold=0.6)
    assert f is not None
    assert f("wat is een managed service provider") is True


def test_keeps_english(monkeypatch):
    _install_fake_lingua(monkeypatch, english_score=0.95)  # confidently English
    language = _fresh_language_module()
    f = language.make_language_filter(confidence_threshold=0.6)
    assert f is not None
    assert f("what is a managed service provider") is False


def test_keeps_low_confidence_non_english(monkeypatch):
    # Non-English wins the top slot but only at 0.55 — below the 0.6 threshold,
    # so the keyword stays in (short/ambiguous strings shouldn't be killed).
    _install_fake_lingua(monkeypatch, english_score=0.45)  # 0.55 Dutch -> below 0.6
    language = _fresh_language_module()
    f = language.make_language_filter(confidence_threshold=0.6)
    assert f is not None
    assert f("ambiguous short") is False


def test_empty_string_short_circuits_to_keep(monkeypatch):
    # Empty string is never embedded / never sent to the detector; the filter
    # returns False (= keep) immediately. (Per-call detector errors are tested
    # in tests/test_relevance.py via the gate's swallowing path.)
    _install_fake_lingua(monkeypatch, english_score=0.1)
    language = _fresh_language_module()
    f = language.make_language_filter(confidence_threshold=0.6)
    assert f is not None
    assert f("") is False


def test_returns_none_when_english_missing_from_language_pool(monkeypatch):
    _install_fake_lingua(monkeypatch, english_score=0.1)
    language = _fresh_language_module()
    # An English-less pool would label everything non-English; reject the
    # config at build time rather than ship a footgun.
    assert language.make_language_filter(languages=("DUTCH", "GERMAN")) is None


@pytest.fixture(autouse=True)
def _restore_module():
    """Reload the real module after each test so other test files see the
    un-stubbed version."""
    yield
    sys.modules.pop("lingua", None)
    from app.pipeline import language  # noqa: PLC0415

    reload(language)


# Layer 1 (starter regex) has no model dependency, so these tests run regardless
# of whether lingua is installed. They guard the dominant failure mode reported
# by the user — a non-English question wrapping an English noun phrase.

def test_starter_catches_dutch_what_is_pattern():
    from app.pipeline.language import matches_non_english_starter

    assert matches_non_english_starter("wat is een managed service provider")
    assert matches_non_english_starter("hoe werkt msp")
    assert matches_non_english_starter("waarom msp gebruiken")


def test_starter_catches_other_european_mixed_patterns():
    from app.pipeline.language import matches_non_english_starter

    assert matches_non_english_starter("was ist eine managed service provider")
    assert matches_non_english_starter("wie funktioniert msp")
    assert matches_non_english_starter("qué es un msp")
    assert matches_non_english_starter("cómo funciona msp")
    assert matches_non_english_starter("comment fonctionne msp")
    assert matches_non_english_starter("pourquoi msp")
    assert matches_non_english_starter("o que é msp")
    assert matches_non_english_starter("cos è un msp")
    assert matches_non_english_starter("cosa significa msp")
    assert matches_non_english_starter("co to msp")
    assert matches_non_english_starter("jak działa msp")
    assert matches_non_english_starter("apa itu msp")


def test_starter_catches_suffix_marker():
    # Some languages embed the question marker as a suffix ("msp nedir" =
    # Turkish "what is msp"). The regex picks that up via the suffix branch.
    from app.pipeline.language import matches_non_english_starter

    assert matches_non_english_starter("msp nedir")
    assert matches_non_english_starter("managed service provider bedeutung")


def test_starter_does_not_false_positive_on_english():
    from app.pipeline.language import matches_non_english_starter

    safe = [
        "what is a managed service provider",
        "how to choose a managed service provider",
        "why use a managed service provider",
        "when should i use msp",
        "which msp is best",
        "msp pricing",
        "best msp providers",
        "top 10 msps",
        "msp meaning",
        "compare msp providers",
        "reddit msp",
        "retatrutide",
        "retatrutide vs tirzepatide",
        "how to get retatrutide",
        "comment box plugin",        # 'comment' is English here
        "how to add a comment",
        "como kitchen reviews",       # english brand name 'como', no Italian verb
    ]
    for kw in safe:
        assert not matches_non_english_starter(kw), f"false positive on {kw!r}"
