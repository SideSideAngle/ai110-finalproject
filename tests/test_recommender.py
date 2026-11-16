import os

import pytest

from src.recommender import (
    Recommender, Song, UserProfile, load_songs, normalize_prefs,
    recommend_songs, score_song,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_small_recommender() -> Recommender:
    songs = [
        Song(id=1, title="Test Pop Track", artist="Test Artist", genre="pop", mood="happy",
             energy=0.8, tempo_bpm=120, valence=0.9, danceability=0.8, acousticness=0.2),
        Song(id=2, title="Chill Lofi Loop", artist="Test Artist", genre="lofi", mood="chill",
             energy=0.4, tempo_bpm=80, valence=0.6, danceability=0.5, acousticness=0.9),
    ]
    return Recommender(songs)


def song(**over):
    base = dict(id=1, title="T", artist="A", genre="pop", mood="happy", energy=0.5,
                tempo_bpm=100.0, valence=0.5, danceability=0.5, acousticness=0.5)
    base.update(over)
    return base


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile("pop", "happy", 0.8, False)
    results = make_small_recommender().recommend(user, k=2)
    assert len(results) == 2
    assert results[0].genre == "pop" and results[0].mood == "happy"


def test_recommend_ranks_the_matching_song_first_even_if_listed_last():
    rec = make_small_recommender()
    rec.songs.reverse()  # the lofi song is now first in the list
    user = UserProfile("lofi", "chill", 0.4, True)
    assert rec.recommend(user, k=1)[0].genre == "lofi"


def test_explain_recommendation_mentions_real_reasons():
    rec = make_small_recommender()
    user = UserProfile("pop", "happy", 0.8, False)
    explanation = rec.explain_recommendation(user, rec.songs[0])
    assert "genre match" in explanation and "mood match" in explanation
    assert "placeholder" not in explanation.lower()


def test_exact_genre_and_mood_beat_energy_only():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.5}
    full, _ = score_song(prefs, song())
    none, _ = score_song(prefs, song(genre="metal", mood="angry"))
    assert full - none == pytest.approx(3.0)


def test_partial_genre_credit_for_related_genre():
    exact, _ = score_song({"genre": "pop"}, song(genre="pop"))
    related, reasons = score_song({"genre": "pop"}, song(genre="indie pop"))
    assert 0 < related < exact
    assert "related genre" in reasons[0]


def test_matching_is_case_and_whitespace_insensitive():
    a, _ = score_song({"genre": " Rock ", "mood": "INTENSE"}, song(genre="rock", mood="intense"))
    assert a == pytest.approx(3.0)


def test_out_of_range_energy_is_clamped_with_warning():
    clean, warnings = normalize_prefs({"energy": 5.0})
    assert clean["energy"] == 1.0
    assert any("clamped" in w for w in warnings)


def test_non_numeric_energy_is_ignored_not_fatal():
    clean, warnings = normalize_prefs({"genre": "pop", "energy": "loud"})
    assert "energy" not in clean and warnings


def test_empty_profile_warns_and_scores_zero():
    clean, warnings = normalize_prefs({})
    assert any("empty profile" in w for w in warnings)
    assert score_song({}, song())[0] == 0.0


def test_artist_diversity_cap():
    songs = [song(id=i, artist="Same Artist", energy=0.5) for i in range(5)]
    songs.append(song(id=99, artist="Other", energy=0.1))
    picked = recommend_songs({"energy": 0.5}, songs, k=4, max_per_artist=2)
    artists = [s["artist"] for s, _, _ in picked]
    assert artists.count("Same Artist") == 2 and "Other" in artists


def test_load_songs_skips_bad_rows(tmp_path):
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text(
        "id,title,artist,genre,mood,energy,tempo_bpm,valence,danceability,acousticness\n"
        "1,Good,A,Pop,Happy,0.5,100,0.5,0.5,0.5\n"
        "oops,Bad,A,pop,happy,0.5,100,0.5,0.5,0.5\n"
        "3,AlsoBad,A,pop,happy,not-a-number,100,0.5,0.5,0.5\n", encoding="utf-8")
    songs = load_songs(str(csv_file))
    assert [s["title"] for s in songs] == ["Good"]
    assert songs[0]["genre"] == "pop"  # normalized


def test_real_catalog_loads():
    songs = load_songs(os.path.join(ROOT, "data", "songs.csv"))
    assert len(songs) > 1000
    assert all(0.0 <= s["energy"] <= 1.0 for s in songs)


def test_exclude_ids_skips_already_shown_songs():
    songs = [song(id=i, artist=f"A{i}", energy=0.5) for i in range(1, 6)]
    picked = recommend_songs({"energy": 0.5}, songs, k=3, exclude_ids={1, 2})
    assert {s["id"] for s, _, _ in picked} == {3, 4, 5}
