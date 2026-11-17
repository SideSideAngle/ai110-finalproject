"""Display helpers for the web app.

These are plain Python functions with no Streamlit in them, so they can be unit
tested without a browser. app.py only decides *where* things appear on the page.
"""
from urllib.parse import quote_plus


def match_percent(score: float, max_score: float) -> int:
    """Turn a raw score into a whole-number percentage of the best possible score."""
    if max_score <= 0:
        return 0
    return max(0, min(100, round(100 * score / max_score)))


def youtube_search_url(title: str, artist: str) -> str:
    """A YouTube search link for the song. No API or key needed, it's just a URL."""
    return "https://www.youtube.com/results?search_query=" + quote_plus(f"{title} {artist}")
