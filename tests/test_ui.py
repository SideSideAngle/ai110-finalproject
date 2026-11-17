"""Smoke tests for the Streamlit app, driven headlessly with streamlit.testing."""
import json
import os
import re

import pytest
from streamlit.testing.v1 import AppTest

from src.llm import validate_llm
from src.logging_setup import LOG_DIR, log_event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")


def card_titles(at: AppTest) -> list:
    """Song titles currently shown on the cards (read from the rank/title header HTML)."""
    return [t for e in at.markdown for t in re.findall(r'class="song-title">(.*?)</span>', e.value)]


def fresh() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def search(at: AppTest, text: str) -> AppTest:
    at.text_input[0].set_value(text)
    return next(b for b in at.button if b.label == "Find music").click().run()


def test_app_loads_without_errors():
    at = fresh()
    assert not at.exception
    assert any(b.label.endswith("SymphonySearch") for b in at.button)  # the clickable title


def test_search_shows_five_song_cards():
    at = search(fresh(), "Wraith")
    assert not at.exception
    assert len(at.get("link_button")) == 5


def test_bad_input_shows_error_not_crash():
    at = search(fresh(), "zzzz qqqq xxxx")
    assert not at.exception and len(at.error) == 1


def test_quick_start_button_runs_a_search():
    at = fresh()
    next(b for b in at.button if b.label == "Octane").click().run()
    assert not at.exception and len(at.get("link_button")) == 5


def test_thumbs_down_then_retry_shows_new_songs():
    at = search(fresh(), "calm study music")
    first = card_titles(at)
    assert len(first) == 5
    next(b for b in at.button if "Not quite" in b.label).click().run()
    at.text_input(key="note_input").set_value("too slow, more energy")
    next(b for b in at.button if b.label == "Try again").click().run()
    assert not at.exception
    second = card_titles(at)
    assert second and not set(first) & set(second)


def test_validate_llm_reports_failure_without_leaking_the_key():
    secret = "sk-ant-SECRET123"

    def rejecting(system, user):
        raise PermissionError(f"bad key {secret}")  # even if an error mentions the key...

    ok, message = validate_llm(rejecting)
    assert not ok and secret not in message  # ...we never show it


def test_validate_llm_accepts_a_working_key():
    assert validate_llm(lambda s, u: "OK")[0]


def test_request_text_is_redacted_when_logging_is_private(monkeypatch):
    monkeypatch.setenv("LOG_REQUEST_TEXT", "0")
    log_event("request", request="my private breakup playlist", note="secret note", confidence=0.5)
    with open(os.path.join(LOG_DIR, "events.jsonl"), encoding="utf-8") as f:
        last = json.loads(f.readlines()[-1])
    assert last["request"] == "[redacted]" and last["note"] == "[redacted]"
    assert last["confidence"] == 0.5  # non-sensitive fields are kept


def test_welcome_state_shows_examples_before_any_search():
    at = fresh()
    assert not at.exception and not card_titles(at)
    assert any("romantic" in b.label for b in at.button)  # one-click example searches


def test_example_button_runs_a_search():
    at = fresh()
    next(b for b in at.button if "romantic" in b.label).click().run()
    assert not at.exception and len(card_titles(at)) == 5


def test_clicking_the_title_returns_to_the_start_and_keeps_the_key():
    at = search(fresh(), "Wraith")
    assert len(card_titles(at)) == 5
    at.session_state["llm"] = lambda s, u: "OK"  # pretend the visitor pasted a working key
    next(b for b in at.button if b.label.endswith("SymphonySearch")).click().run()
    assert not at.exception and not card_titles(at)  # back to the welcome state
    assert any("romantic" in b.label for b in at.button)
    assert at.session_state["llm"] is not None  # the key survived


def test_cards_show_audio_players_when_previews_are_found(monkeypatch):
    from src import previews
    monkeypatch.setenv("SYMPHONY_PREVIEWS", "1")
    previews.clear_cache()
    monkeypatch.setattr(previews, "_http_get_json", lambda url: {"results": []})  # nothing found
    at = search(fresh(), "Wraith")
    assert not at.exception and len(card_titles(at)) == 5 and len(at.get("audio")) == 0

    previews.clear_cache()

    def fake(url):  # a match for whatever song is searched
        import urllib.parse
        term = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["term"][0]
        return {"results": [{"trackName": term, "artistName": term, "previewUrl":
                             "https://audio-ssl.itunes.apple.com/p.m4a", "artworkUrl100":
                             "https://is1-ssl.mzstatic.com/a/100x100bb.jpg"}]}

    monkeypatch.setattr(previews, "_http_get_json", fake)
    at = search(fresh(), "Wraith")
    assert not at.exception and len(at.get("audio")) >= 1
    previews.clear_cache()
