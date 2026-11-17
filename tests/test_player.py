import pytest

from src.player import match_bar, match_chip, player_html


def test_player_contains_audio_art_and_a_play_button():
    page = player_html("https://audio-ssl.itunes.apple.com/p.m4a", "https://is1-ssl.mzstatic.com/a.jpg")
    assert 'src="https://audio-ssl.itunes.apple.com/p.m4a"' in page
    assert 'url("https://is1-ssl.mzstatic.com/a.jpg")' in page
    assert 'class="art has-img"' in page
    assert 'id="btn"' in page and "Play or pause" in page


def test_player_without_art_has_no_image_class():
    page = player_html("https://audio-ssl.itunes.apple.com/p.m4a")
    assert 'class="art "' in page and "has-img\"" not in page.split("<body>")[1]


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "http://insecure.example/a.m4a",
                                 'https://a.com/x"onerror="alert(1)', "https://a.com/<script>",
                                 "https://a.com/a b", "", None])
def test_player_refuses_unsafe_audio_urls(bad):
    with pytest.raises(ValueError):
        player_html(bad)


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "http://insecure.example/a.jpg",
                                 'https://a.com/x");alert(1);("'])
def test_player_refuses_unsafe_art_urls(bad):
    with pytest.raises(ValueError):
        player_html("https://audio-ssl.itunes.apple.com/p.m4a", bad)


def test_match_bar_and_chip_are_clamped_and_formatted():
    assert "width:100%" in match_bar(250) and "width:0%" in match_bar(-5)
    assert "98% match" in match_chip(98)
