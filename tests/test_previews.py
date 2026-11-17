"""Preview lookup tests. A fake fetcher stands in for the network, so these run offline."""
import json

import pytest

from src import previews
from src.previews import artist_matches, clean_title, find_preview, get_previews, title_matches

GOOD = {"results": [{
    "trackName": "Sunsetz", "artistName": "Cigarettes After Sex",
    "previewUrl": "https://audio-ssl.itunes.apple.com/x/preview.m4a",
    "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/a/100x100bb.jpg"}]}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setenv("SYMPHONY_PREVIEWS", "1")
    previews.clear_cache()
    yield
    previews.clear_cache()


def test_finds_a_matching_preview_and_upgrades_artwork_size():
    p = find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: GOOD)
    assert p.audio_url.endswith("preview.m4a")
    assert "300x300bb" in p.artwork_url


def test_search_url_sends_only_song_and_artist():
    seen = []
    find_preview("Sunsetz (feat. X) - 2011 Remaster", "Cigarettes After Sex",
                 fetch=lambda url: seen.append(url) or {"results": []})
    assert "Sunsetz+Cigarettes+After+Sex" in seen[0] and "Remaster" not in seen[0]


def test_wrong_artist_is_rejected():
    cover = {"results": [{**GOOD["results"][0], "artistName": "Some Cover Band"}]}
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: cover) is None


def test_wrong_song_is_rejected():
    other = {"results": [{**GOOD["results"][0], "trackName": "Totally Different"}]}
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: other) is None


def test_untrusted_hosts_are_rejected():
    evil = {"results": [{**GOOD["results"][0], "previewUrl": "https://evil.example.com/a.m4a"}]}
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: evil) is None
    http = {"results": [{**GOOD["results"][0], "previewUrl": "http://audio-ssl.itunes.apple.com/a.m4a"}]}
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: http) is None


@pytest.mark.parametrize("failure", [TimeoutError("slow"), ValueError("bad json"), KeyError("x")])
def test_any_failure_returns_none_instead_of_raising(failure):
    def boom(url):
        raise failure
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=boom) is None


@pytest.mark.parametrize("junk", [{}, {"results": None}, {"results": [None]}, {"results": [{}]}, []])
def test_malformed_responses_return_none(junk):
    assert find_preview("Sunsetz", "Cigarettes After Sex", fetch=lambda url: junk) is None


def test_matching_helpers():
    assert clean_title("Sweet Dreams (Are Made of This) - Remastered") == "Sweet Dreams"
    assert artist_matches("Cigarettes After Sex", "cigarettes after sex")
    assert artist_matches("Drake", "Drake & Future")
    assert not artist_matches("Drake", "Kendrick Lamar")
    assert title_matches("Sunsetz - 2017 Remaster", "Sunsetz")


def test_get_previews_caches_results_and_looks_up_each_song_once():
    calls = []

    def fetch(url):
        calls.append(url)
        return GOOD

    songs = [{"id": 1, "title": "Sunsetz", "artist": "Cigarettes After Sex"}]
    assert get_previews(songs, fetch)[1] is not None
    assert get_previews(songs, fetch)[1] is not None  # served from the cache
    assert len(calls) == 1


def test_get_previews_does_not_let_one_failure_break_the_others():
    def fetch(url):
        if "Bad" in url:
            raise TimeoutError("slow")
        return GOOD

    songs = [{"id": 1, "title": "Sunsetz", "artist": "Cigarettes After Sex"},
             {"id": 2, "title": "Bad Song", "artist": "Nobody"}]
    got = get_previews(songs, fetch)
    assert got[1] is not None and got[2] is None


def test_previews_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SYMPHONY_PREVIEWS", "0")
    assert get_previews([{"id": 1, "title": "t", "artist": "a"}], lambda url: GOOD) == {}
