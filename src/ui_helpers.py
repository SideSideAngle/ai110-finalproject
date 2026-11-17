"""Display helpers for the web app.

These are plain Python functions with no Streamlit in them, so they can be unit
tested without a browser. app.py only decides *where* things appear on the page.
"""
import html
from urllib.parse import quote_plus


def match_percent(score: float, max_score: float) -> int:
    """Turn a raw score into a whole-number percentage of the best possible score."""
    if max_score <= 0:
        return 0
    return max(0, min(100, round(100 * score / max_score)))


def youtube_search_url(title: str, artist: str) -> str:
    """A YouTube search link for the song. No API or key needed, it's just a URL."""
    return "https://www.youtube.com/results?search_query=" + quote_plus(f"{title} {artist}")


# One accent colour per mood, used for the mood chips. Unknown moods get the default.
MOOD_COLORS = {
    "euphoric": "#F2B84B", "happy": "#FFD27A", "intense": "#FF8A65", "angry": "#FF6B6B",
    "moody": "#7C8CF8", "melancholic": "#6FA8DC", "relaxed": "#6EC9B8",
    "chill": "#5FD3D0", "peaceful": "#8FD6A4",
}
DEFAULT_MOOD_COLOR = "#B9B3D9"


def mood_color(mood: str) -> str:
    return MOOD_COLORS.get(mood.strip().lower(), DEFAULT_MOOD_COLOR)


def genre_chip(genre: str) -> str:
    """HTML for a genre pill. Text is escaped because it comes from the dataset."""
    return f'<span class="chip chip-genre">{html.escape(genre.title())}</span>'


def mood_chip(mood: str) -> str:
    color = mood_color(mood)
    return (f'<span class="chip" style="color:{color};border-color:{color}88;'
            f'background:{color}22">{html.escape(mood.title())}</span>')


def song_header(rank: int, title: str, artist: str) -> str:
    """HTML for the gold rank badge, title and artist at the top of a card."""
    return (f'<span class="rank">{rank}</span><span class="song-title">{html.escape(title)}</span>'
            f'<span class="artist">by {html.escape(artist)}</span>')
