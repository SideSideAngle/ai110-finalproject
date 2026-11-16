"""Scoring and ranking engine of the music recommender.

The LLM layers (intent parser, explainer) never rank songs. This deterministic
scorer does, so results are testable and every score can be explained.
"""
import csv
import heapq
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Points a perfect match earns for each signal. Genre and mood are categorical;
# energy, valence and acousticness reward closeness to the target (only scored
# when the profile actually contains a target for them).
GENRE_WEIGHT = 2.0
MOOD_WEIGHT = 1.0
ENERGY_WEIGHT = 1.0
VALENCE_WEIGHT = 0.5
ACOUSTIC_WEIGHT = 0.5
PARTIAL_GENRE_FACTOR = 0.5  # "indie pop" vs "pop" earns half the genre points

NUMERIC_TARGETS = ("energy", "valence", "acousticness")


@dataclass
class Song:
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float


@dataclass
class UserProfile:
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool


def _norm(text) -> str:
    return " ".join(str(text).strip().lower().split())


def _as_list(*values) -> List[str]:
    out: List[str] = []
    for value in values:
        if value is None:
            continue
        items = value if isinstance(value, (list, tuple, set)) else [value]
        for item in items:
            item = _norm(item)
            if item and item not in out:
                out.append(item)
    return out


def normalize_prefs(user_prefs: Dict) -> Tuple[Dict, List[str]]:
    """Clean a profile: lowercase/strip text, clamp numbers into 0..1.

    Returns (clean_prefs, warnings). Never raises on bad input, so one weird
    value cannot crash a request; the warnings say what was changed.
    """
    warnings: List[str] = []
    clean: Dict = {
        "genres": _as_list(user_prefs.get("genre"), user_prefs.get("genres")),
        "moods": _as_list(user_prefs.get("mood"), user_prefs.get("moods")),
    }
    for key in NUMERIC_TARGETS:
        if key not in user_prefs or user_prefs[key] is None:
            continue
        try:
            value = float(user_prefs[key])
        except (TypeError, ValueError):
            warnings.append(f"ignored non-numeric {key}={user_prefs[key]!r}")
            continue
        if not 0.0 <= value <= 1.0:
            warnings.append(f"{key}={value} is outside 0..1, clamped")
            value = min(1.0, max(0.0, value))
        clean[key] = value
    if not clean["genres"] and not clean["moods"] and not any(k in clean for k in NUMERIC_TARGETS):
        warnings.append("empty profile: nothing to match on")
    return clean, warnings


def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from CSV into dicts, converting numeric columns to numbers.

    Malformed rows are skipped with a warning instead of aborting the load.
    """
    float_fields = ("energy", "tempo_bpm", "valence", "danceability", "acousticness")
    songs: List[Dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                row["id"] = int(row["id"])
                for field in float_fields:
                    row[field] = float(row[field])
                row["genre"] = _norm(row["genre"])
                row["mood"] = _norm(row["mood"])
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping bad row at line %d of %s: %s", line_no, csv_path, exc)
                continue
            songs.append(row)
    return songs


def _genre_factor(song_genre: str, wanted: List[str]) -> Tuple[float, Optional[str]]:
    """1.0 for an exact genre match, PARTIAL_GENRE_FACTOR for a word-subset match."""
    best, best_genre = 0.0, None
    song_words = set(song_genre.split())
    for genre in wanted:
        if genre == song_genre:
            return 1.0, genre
        words = set(genre.split())
        if words and (words <= song_words or song_words <= words) and PARTIAL_GENRE_FACTOR > best:
            best, best_genre = PARTIAL_GENRE_FACTOR, genre
    return best, best_genre


def max_possible_score(clean: Dict) -> float:
    total = 0.0
    if clean["genres"]:
        total += GENRE_WEIGHT
    if clean["moods"]:
        total += MOOD_WEIGHT
    total += ENERGY_WEIGHT if "energy" in clean else 0.0
    total += VALENCE_WEIGHT if "valence" in clean else 0.0
    total += ACOUSTIC_WEIGHT if "acousticness" in clean else 0.0
    return total


def _score_clean(clean: Dict, song: Dict) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    if clean["genres"]:
        factor, matched = _genre_factor(song["genre"], clean["genres"])
        if factor:
            points = GENRE_WEIGHT * factor
            kind = "genre match" if factor == 1.0 else "related genre"
            score += points
            reasons.append(f"{kind}: {song['genre']} (+{points:.1f})")

    if song["mood"] in clean["moods"]:
        score += MOOD_WEIGHT
        reasons.append(f"mood match: {song['mood']} (+{MOOD_WEIGHT:.1f})")

    for key, weight in (("energy", ENERGY_WEIGHT), ("valence", VALENCE_WEIGHT),
                        ("acousticness", ACOUSTIC_WEIGHT)):
        if key in clean:
            points = weight * max(0.0, 1.0 - abs(song[key] - clean[key]))
            score += points
            reasons.append(f"{key} {song[key]:.2f} vs target {clean[key]:.2f} (+{points:.2f})")

    return score, reasons


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Score one song against a profile, returning (score, reasons)."""
    clean, _ = normalize_prefs(user_prefs)
    return _score_clean(clean, song)


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5,
                    max_per_artist: int = 2,
                    exclude_ids: Optional[Set[int]] = None) -> List[Tuple[Dict, float, str]]:
    """Return the top k songs as (song, score, explanation), best first.

    Re-ranks for diversity: at most `max_per_artist` songs by one artist.
    Songs whose id is in `exclude_ids` (already shown to the user) are skipped.
    """
    clean, _ = normalize_prefs(user_prefs)
    excluded = exclude_ids or set()
    scored = (
        (song, score, "; ".join(reasons))
        for song in songs if song["id"] not in excluded
        for score, reasons in [_score_clean(clean, song)]
    )
    # Take a generous pool, then apply the artist cap while keeping score order.
    pool = heapq.nlargest(max(k * 10, k), scored, key=lambda item: item[1])
    picked: List[Tuple[Dict, float, str]] = []
    per_artist: Dict[str, int] = {}
    for item in pool:
        artist = _norm(item[0].get("artist", ""))
        if max_per_artist and per_artist.get(artist, 0) >= max_per_artist:
            continue
        per_artist[artist] = per_artist.get(artist, 0) + 1
        picked.append(item)
        if len(picked) == k:
            break
    return picked


class Recommender:
    """Object-oriented wrapper over the same scoring rules (used by the tests)."""

    def __init__(self, songs: List[Song]):
        self.songs = songs

    @staticmethod
    def _prefs(user: UserProfile) -> Dict:
        return {
            "genre": user.favorite_genre,
            "mood": user.favorite_mood,
            "energy": user.target_energy,
            "acousticness": 0.8 if user.likes_acoustic else 0.2,
        }

    @staticmethod
    def _as_dict(song: Song) -> Dict:
        return dict(song.__dict__)

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        by_id = {s.id: s for s in self.songs}
        ranked = recommend_songs(self._prefs(user), [self._as_dict(s) for s in self.songs],
                                 k=k, max_per_artist=0)
        return [by_id[item[0]["id"]] for item in ranked]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        score, reasons = score_song(self._prefs(user), self._as_dict(song))
        return f"Score {score:.2f}: " + "; ".join(reasons) if reasons else f"Score {score:.2f}"
