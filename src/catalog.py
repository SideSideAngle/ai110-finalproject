"""Build the trimmed song catalog (data/songs.csv) from the Spotify Tracks dataset.

Usage (from the repo root):
    python -m src.catalog                       # downloads the dataset, writes data/songs.csv
    python -m src.catalog --source path/to.csv  # use a local copy instead

The source is the public "Spotify Tracks Dataset" (maharshipandya/spotify-tracks-dataset
on Hugging Face, ~114k rows). We keep the most popular tracks per genre so the committed
CSV stays small and the project runs without any network access or API key.
"""
import argparse
import csv
import logging
import os
import tempfile
import urllib.request
from typing import Dict, List

logger = logging.getLogger(__name__)

SOURCE_URL = (
    "https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/"
    "resolve/main/dataset.csv"
)
OUT_FIELDS = ["id", "title", "artist", "genre", "mood", "energy",
              "tempo_bpm", "valence", "danceability", "acousticness"]
EXCLUDED_GENRES = {"comedy", "kids", "children", "disney", "show-tunes"}
GENRE_RENAMES = {"r-n-b": "r&b"}


def normalize_genre(raw: str) -> str:
    raw = raw.strip().lower()
    return GENRE_RENAMES.get(raw, raw.replace("-", " "))


def derive_mood(energy: float, valence: float, acousticness: float) -> str:
    """Derive a mood label from audio features (the source dataset has no mood column)."""
    if energy >= 0.75:
        if valence >= 0.6:
            return "euphoric"
        return "intense" if valence >= 0.35 else "angry"
    if energy >= 0.45:
        if valence >= 0.6:
            return "happy"
        return "moody" if valence >= 0.35 else "melancholic"
    # low energy
    if valence >= 0.5:
        return "peaceful" if acousticness >= 0.8 else "chill"
    if valence >= 0.3:
        return "relaxed"
    return "melancholic"


def build_catalog(source_csv: str, out_csv: str, per_genre: int = 25) -> int:
    """Keep the `per_genre` most popular unique tracks of every genre. Returns rows written."""
    best: Dict[str, List[dict]] = {}
    seen = set()
    with open(source_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                genre = row["track_genre"].strip().lower()
                if genre in EXCLUDED_GENRES:
                    continue
                key = (row["track_name"].strip().lower(), row["artists"].strip().lower())
                if key in seen:
                    continue
                tempo = float(row["tempo"])
                if tempo <= 0:
                    continue
                seen.add(key)
                best.setdefault(genre, []).append({
                    "popularity": int(row["popularity"]),
                    "title": row["track_name"].strip(),
                    "artist": row["artists"].split(";")[0].strip(),
                    "genre": normalize_genre(genre),
                    "energy": float(row["energy"]),
                    "tempo_bpm": round(tempo, 1),
                    "valence": float(row["valence"]),
                    "danceability": float(row["danceability"]),
                    "acousticness": float(row["acousticness"]),
                })
            except (KeyError, ValueError) as exc:  # malformed row: skip, never crash the build
                logger.warning("Skipping malformed row: %s", exc)

    rows = []
    for genre in sorted(best):
        top = sorted(best[genre], key=lambda r: -r["popularity"])[:per_genre]
        rows.extend(top)

    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for i, r in enumerate(rows, start=1):
            writer.writerow({
                "id": i, "title": r["title"], "artist": r["artist"], "genre": r["genre"],
                "mood": derive_mood(r["energy"], r["valence"], r["acousticness"]),
                "energy": r["energy"], "tempo_bpm": r["tempo_bpm"], "valence": r["valence"],
                "danceability": r["danceability"], "acousticness": r["acousticness"],
            })
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/songs.csv from the Spotify Tracks dataset")
    parser.add_argument("--source", help="local path to the source CSV (otherwise downloaded)")
    parser.add_argument("--out", default="data/songs.csv")
    parser.add_argument("--per-genre", type=int, default=25)
    args = parser.parse_args()

    source = args.source
    tmp_dir = None
    if not source:
        tmp_dir = tempfile.mkdtemp()
        source = os.path.join(tmp_dir, "dataset.csv")
        print(f"Downloading {SOURCE_URL} ...")
        urllib.request.urlretrieve(SOURCE_URL, source)
    count = build_catalog(source, args.out, args.per_genre)
    print(f"Wrote {count} songs to {args.out}")


if __name__ == "__main__":
    main()
