"""Find a 30-second audio preview and album art for a song via the iTunes Search API.

Free, no API key. Only the song title and artist are sent, never what the user typed.
Everything here is best-effort: any failure (timeout, no match, odd data) returns None
and the card simply falls back to its YouTube link.
"""
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ITUNES_URL = "https://itunes.apple.com/search"
TIMEOUT_SECONDS = 4
HIT_TTL = 24 * 3600   # keep a found preview for a day
MISS_TTL = 15 * 60    # retry misses and failures sooner; they may be temporary
MAX_CACHE = 2000
TRUSTED_HOST_SUFFIXES = (".apple.com", ".mzstatic.com")

Fetcher = Callable[[str], dict]


@dataclass(frozen=True)
class Preview:
    audio_url: str
    artwork_url: Optional[str]
    track_name: str
    artist_name: str


def previews_enabled() -> bool:
    """Set SYMPHONY_PREVIEWS=0 to turn previews off (tests do this to stay offline)."""
    return os.environ.get("SYMPHONY_PREVIEWS", "1") != "0"


# ------------------------------------------------------------------ matching
def clean_title(title: str) -> str:
    """Drop '(feat. X)', '- 2011 Remaster' and similar suffixes that hurt searching."""
    title = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title)
    title = re.split(r"\s+-\s+", title)[0]
    return " ".join(title.split())


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def artist_matches(wanted: str, found: str) -> bool:
    a, b = _norm(wanted), _norm(found)
    return bool(a and b and (a in b or b in a))


def title_matches(wanted: str, found: str) -> bool:
    a, b = _norm(clean_title(wanted)), _norm(clean_title(found))
    return bool(a and b and (a == b or a in b or b in a))


def _trusted(url: Optional[str]) -> bool:
    """Only accept https URLs on Apple's own domains."""
    if not isinstance(url, str):
        return False
    parts = urllib.parse.urlparse(url)
    return parts.scheme == "https" and bool(parts.hostname) and parts.hostname.endswith(TRUSTED_HOST_SUFFIXES)


# -------------------------------------------------------------------- lookup
def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "SymphonySearch/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def find_preview(title: str, artist: str, fetch: Optional[Fetcher] = None) -> Optional[Preview]:
    """Best matching preview for a song, or None. Never raises."""
    fetch = fetch or _http_get_json
    query = urllib.parse.urlencode({"term": f"{clean_title(title)} {artist}", "media": "music",
                                    "entity": "song", "limit": 5})
    try:
        data = fetch(f"{ITUNES_URL}?{query}")
        for item in data.get("results", []):
            audio = item.get("previewUrl")
            if not (_trusted(audio) and artist_matches(artist, str(item.get("artistName", "")))
                    and title_matches(title, str(item.get("trackName", "")))):
                continue
            art = item.get("artworkUrl100")
            art = art.replace("100x100bb", "300x300bb") if _trusted(art) else None
            return Preview(audio, art, str(item["trackName"]), str(item["artistName"]))
    except Exception as exc:  # network, JSON, unexpected shape: all mean "no preview"
        logger.info("Preview lookup failed for %r (%s: %s)", title, type(exc).__name__, exc)
    return None


# ------------------------------------------------------------------- caching
_cache: Dict[Tuple[str, str], Tuple[float, Optional[Preview]]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _cached(key: Tuple[str, str]):
    """Return (hit, value). Expired entries count as misses."""
    with _lock:
        entry = _cache.get(key)
    if entry and entry[0] > time.time():
        return True, entry[1]
    return False, None


def _remember(key: Tuple[str, str], value: Optional[Preview]) -> None:
    ttl = HIT_TTL if value else MISS_TTL
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.pop(next(iter(_cache)))  # evict the oldest entry
        _cache[key] = (time.time() + ttl, value)


def get_previews(songs: Sequence[Dict], fetch: Optional[Fetcher] = None) -> Dict[int, Optional[Preview]]:
    """Previews for several songs at once: cached, with misses looked up in parallel.

    Returns {song id: Preview or None}. Empty when previews are switched off.
    """
    if not previews_enabled():
        return {}
    result: Dict[int, Optional[Preview]] = {}
    todo: List[Dict] = []
    for song in songs:
        hit, value = _cached((song["title"], song["artist"]))
        if hit:
            result[song["id"]] = value
        else:
            todo.append(song)
    if todo:
        with ThreadPoolExecutor(max_workers=min(5, len(todo))) as pool:
            found = list(pool.map(lambda s: find_preview(s["title"], s["artist"], fetch), todo))
        for song, preview in zip(todo, found):
            _remember((song["title"], song["artist"]), preview)
            result[song["id"]] = preview
    return result
