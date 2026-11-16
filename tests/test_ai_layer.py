"""Tests for guardrails, retrieval, intent parsing, explanation checks and the pipeline.

The LLM is replaced by small fake callables so these tests are deterministic and offline.
"""
import json

import pytest

from src.explainer import check_explanations, explain
from src.guardrails import GuardrailError, sanitize_text, validate_profile
from src.intent_parser import parse_intent
from src.pipeline import App

GENRES = ["pop", "ambient", "trip hop", "metal", "indie pop"]
MOODS = ["happy", "moody", "chill"]


@pytest.fixture(scope="module")
def app() -> App:
    return App.from_defaults(llm=None)


# ---- guardrails -------------------------------------------------------------
def test_sanitize_rejects_empty_and_whitespace():
    for bad in ("", "   \n\t ", None, 42):
        with pytest.raises(GuardrailError):
            sanitize_text(bad)


def test_sanitize_rejects_oversized_and_strips_control_chars():
    with pytest.raises(GuardrailError):
        sanitize_text("x" * 501)
    assert sanitize_text("calm\x00  music\x07") == "calm music"


def test_validate_profile_drops_unknown_and_clamps():
    profile, warnings = validate_profile(
        {"genres": ["Pop", "vaporwave"], "moods": ["happy"], "energy": 3, "confidence": 9},
        GENRES, MOODS)
    assert profile["genres"] == ["pop"]
    assert profile["energy"] == 1.0 and profile["confidence"] == 1.0
    assert any("vaporwave" in w for w in warnings)


def test_validate_profile_rejects_when_nothing_usable():
    with pytest.raises(GuardrailError):
        validate_profile({"genres": ["vaporwave"]}, GENRES, MOODS)
    with pytest.raises(GuardrailError):
        validate_profile("not a dict", GENRES, MOODS)


# ---- retrieval --------------------------------------------------------------
def test_retrieval_finds_legend_by_name(app):
    assert app.kb.retrieve("play me some Wraith music")[0].doc.name == "Wraith"


def test_retrieval_finds_situation_by_description(app):
    names = [r.doc.name for r in app.kb.retrieve("quiet music to study and do homework")]
    assert "Studying or homework" in names


# ---- intent parsing ---------------------------------------------------------
def test_rule_parser_uses_retrieved_profile_to_change_the_profile(app):
    octane = app.recommend("Octane", use_llm=False).intent.profile
    wraith = app.recommend("Wraith", use_llm=False).intent.profile
    assert octane["energy"] > 0.85 > 0.6 > wraith["energy"]  # retrieval changes the scorer's input


def test_keyword_cue_overrides_retrieved_energy(app):
    profile = app.recommend("calm studying music", use_llm=False).intent.profile
    assert profile["energy"] <= 0.3


def test_llm_json_is_validated_and_blended_into_confidence(app):
    reply = json.dumps({"genres": ["ambient", "made-up"], "moods": ["chill"],
                        "energy": 0.2, "confidence": 0.9})
    intent = parse_intent("Wraith", app.kb.retrieve("Wraith"), app.genres, app.moods, lambda s, u: reply)
    assert intent.source == "llm"
    assert intent.profile["genres"] == ["ambient"]  # unknown genre dropped
    assert 0.9 <= intent.confidence <= 1.0  # 0.6 * 0.9 + 0.4 * 1.0


@pytest.mark.parametrize("bad_reply", ["I cannot do that", "{not json}", "{}"])
def test_bad_llm_output_falls_back_to_rules(app, bad_reply):
    intent = parse_intent("Wraith", app.kb.retrieve("Wraith"), app.genres, app.moods,
                          lambda s, u: bad_reply)
    assert intent.source == "fallback"


def test_llm_exception_falls_back_to_rules(app):
    def boom(s, u):
        raise TimeoutError("api down")
    intent = parse_intent("Octane", app.kb.retrieve("Octane"), app.genres, app.moods, boom)
    assert intent.source == "fallback" and intent.profile["energy"] > 0.85


# ---- explainer --------------------------------------------------------------
def test_explanation_check_rejects_wrong_count_and_ungrounded_legend():
    legends = ["Wraith", "Octane"]
    assert not check_explanations(["a"], 2, ["Wraith"], legends)[0]
    ok, why = check_explanations(["Great for Octane fans"], 1, ["Wraith"], legends)
    assert not ok and "Octane" in why
    assert check_explanations(["Dark like Wraith"], 1, ["Wraith"], legends)[0]


def test_explain_falls_back_to_template_when_llm_is_ungrounded(app):
    recs = [({"title": "T", "artist": "A"}, 3.0, "genre match: pop (+2.0)")]
    retrieved = app.kb.retrieve("Wraith")
    texts, method = explain(recs, retrieved, app.kb.legend_names, lambda s, u: '["Octane would love it"]')
    assert method == "template" and "genre match" in texts[0]


def test_explain_accepts_grounded_llm_output(app):
    recs = [({"title": "T", "artist": "A"}, 3.0, "genre match: pop (+2.0)")]
    texts, method = explain(recs, app.kb.retrieve("Wraith"), app.kb.legend_names,
                            lambda s, u: '["Eerie and dark, just like Wraith."]')
    assert method == "llm" and texts == ["Eerie and dark, just like Wraith."]


# ---- pipeline ---------------------------------------------------------------
def test_pipeline_returns_explained_results(app):
    result = app.recommend("Wraith", k=3, use_llm=False)
    assert len(result.recs) == len(result.explanations) == 3
    assert result.confidence >= 0.35 and not result.error


def test_pipeline_reports_error_instead_of_crashing(app):
    for bad in ("", "zzzz qqqq xxxx"):
        result = app.recommend(bad, use_llm=False)
        assert result.error and not result.recs


def test_low_confidence_requests_ask_for_clarification(app):
    result = app.recommend("music", use_llm=False)  # too vague for the rule parser
    assert result.error or result.needs_clarification


# ---- romance cue, filler words, and feedback-driven refinement ---------------
def test_filler_words_do_not_retrieve_unrelated_documents(app):
    # "want", "hear", "something" used to retrieve "Ranked grind" for a romantic request
    assert app.kb.retrieve("I want to hear something romantical") == []


def test_romantic_request_maps_to_romance_genres(app):
    result = app.recommend("I want to hear something romantical", use_llm=False)
    assert "romance" in result.intent.profile["genres"]
    assert not result.needs_clarification and result.recs


def test_refine_adjusts_profile_and_never_repeats_songs(app):
    first = app.recommend("calm study music", use_llm=False)
    second = app.refine(first, "too slow, I need more energy", use_llm=False)
    assert second.intent.profile["energy"] > first.intent.profile["energy"]
    assert second.refinement == 1
    first_ids = {s["id"] for s, _, _ in first.recs}
    assert not first_ids & {s["id"] for s, _, _ in second.recs}
    assert first_ids <= second.shown_ids  # shown songs accumulate across rounds


def test_refine_note_only_changes_what_it_mentions(app):
    first = app.recommend("Wraith", use_llm=False)
    second = app.refine(first, "try rock", use_llm=False)
    assert second.intent.profile["genres"] == ["rock"]
    assert second.intent.profile["valence"] == first.intent.profile["valence"]  # kept


def test_refine_with_empty_or_unclear_note_keeps_profile_but_shows_new_songs(app):
    first = app.recommend("Octane", use_llm=False)
    for note in ("", "zzzz qqqq"):
        again = app.refine(first, note, use_llm=False)
        assert again.intent.profile["energy"] == first.intent.profile["energy"]
        assert not {s["id"] for s, _, _ in first.recs} & {s["id"] for s, _, _ in again.recs}


def test_refine_with_llm_sends_original_request_and_note_together(app):
    seen = []

    def fake_llm(system, user):
        seen.append(user)
        return json.dumps({"genres": ["pop"], "moods": ["happy"], "energy": 0.8, "confidence": 0.9})

    llm_app = App(app.songs, app.kb, llm=fake_llm)
    first = llm_app.recommend("happy music")
    llm_app.refine(first, "more acoustic")
    assert any("happy music" in u and "more acoustic" in u for u in seen)
