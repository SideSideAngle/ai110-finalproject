from src.ui_helpers import match_percent, youtube_search_url


def test_match_percent_scales_against_the_best_possible_score():
    assert match_percent(4.9, 5.0) == 98
    assert match_percent(2.5, 5.0) == 50
    assert match_percent(5.0, 5.0) == 100


def test_match_percent_is_always_between_0_and_100():
    assert match_percent(9.0, 5.0) == 100  # a score above the max is capped
    assert match_percent(-1.0, 5.0) == 0


def test_match_percent_handles_a_zero_max_score():
    assert match_percent(1.0, 0.0) == 0


def test_youtube_url_encodes_special_characters():
    url = youtube_search_url("Rock & Roll", "AC/DC")
    assert url.startswith("https://www.youtube.com/results?search_query=")
    assert " " not in url and "&Roll" not in url  # the & inside the title must be encoded
    assert "Rock+%26+Roll" in url


def test_pipeline_reports_max_score_for_percentages():
    from src.pipeline import App
    app = App.from_defaults(llm=None)
    result = app.recommend("Wraith", use_llm=False)
    assert result.max_score > 0
    assert all(match_percent(score, result.max_score) <= 100 for _, score, _ in result.recs)
