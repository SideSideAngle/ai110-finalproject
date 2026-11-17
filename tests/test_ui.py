"""Smoke tests for the Streamlit app, driven headlessly with streamlit.testing."""
import json
import os

import pytest
from streamlit.testing.v1 import AppTest

from src.llm import validate_llm
from src.logging_setup import LOG_DIR, log_event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")


def fresh() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def search(at: AppTest, text: str) -> AppTest:
    at.text_input[0].set_value(text)
    return next(b for b in at.button if b.label == "Find music").click().run()


def test_app_loads_without_errors():
    at = fresh()
    assert not at.exception
    assert at.title[0].value.endswith("Apex Music Recommender")


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
    first = [e.value for e in at.markdown if "** by *" in e.value]
    next(b for b in at.button if "Not quite" in b.label).click().run()
    at.text_input(key="note_input").set_value("too slow, more energy")
    next(b for b in at.button if b.label == "Try again").click().run()
    assert not at.exception
    second = [e.value for e in at.markdown if "** by *" in e.value]
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
