"""The yes/no feedback loop in the CLI, driven with scripted keyboard input."""
import json
import os

import pytest

from src import main as cli
from src.pipeline import App


@pytest.fixture()
def app():
    return App.from_defaults(llm=None)


def script_inputs(monkeypatch, answers):
    answers = iter(answers)
    monkeypatch.setattr(cli, "is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))


def test_no_triggers_follow_up_and_new_songs(app, monkeypatch):
    # first answer: "n", note: "too slow", second answer: "y"
    script_inputs(monkeypatch, ["n", "too slow", "y"])
    result = cli.converse(app, "calm study music", 5)
    assert result.refinement == 1
    assert result.intent.profile["energy"] > 0.8  # "too slow" raised the energy target


def test_yes_ends_the_conversation_without_refining(app, monkeypatch):
    script_inputs(monkeypatch, ["y"])
    assert cli.converse(app, "Wraith", 5).refinement == 0


def test_skip_does_not_refine(app, monkeypatch):
    script_inputs(monkeypatch, [""])
    assert cli.converse(app, "Wraith", 5).refinement == 0


def test_refinement_is_capped(app, monkeypatch):
    script_inputs(monkeypatch, ["n", "", "n", "", "n", "", "n"])  # always "no"
    assert cli.converse(app, "Octane", 5).refinement == cli.MAX_REFINEMENTS


def test_feedback_and_note_are_logged(app, monkeypatch):
    script_inputs(monkeypatch, ["n", "too slow", "y"])
    cli.converse(app, "calm study music", 5)
    from src.logging_setup import LOG_DIR
    with open(os.path.join(LOG_DIR, "events.jsonl"), encoding="utf-8") as f:
        events = [json.loads(line) for line in f]
    kinds = [e["kind"] for e in events]
    assert "feedback" in kinds and "feedback_note" in kinds
    assert [e["helpful"] for e in events if e["kind"] == "feedback"][-2:] == [False, True]
