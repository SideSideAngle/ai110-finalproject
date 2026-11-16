"""Evaluation harness: run golden cases through the system and report how reliable it is.

    python eval/run_eval.py          # offline, deterministic (rule-based parser)
    python eval/run_eval.py --llm    # use the LLM parser (needs ANTHROPIC_API_KEY)

Writes eval/report.md. Exit code is 1 if any case fails.
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RECOMMENDER_LOG_DIR", tempfile.mkdtemp(prefix="recommender-eval-logs-"))

from src.llm import get_llm  # noqa: E402
from src.pipeline import App  # noqa: E402
from src.recommender import normalize_prefs, recommend_songs  # noqa: E402


def check(expect: dict, recs, error, needs_clarification, previous_ids=frozenset()):
    """Return a list of failure messages (empty list means the case passed)."""
    fails = []
    if expect.get("error"):
        if not error:
            fails.append("expected a guardrail error but got results")
        return fails
    if expect.get("error_or_clarify"):
        if not (error or needs_clarification):
            fails.append("expected an error or a clarification request")
        return fails
    if error:
        return [f"unexpected error: {error}"]
    songs = [s for s, _, _ in recs]
    if not songs:
        return ["no recommendations returned"]
    for key, field in (("energy_in_top", "energy"), ("valence_in_top", "valence")):
        if key in expect:
            lo, hi, need = expect[key]
            got = sum(lo <= s[field] <= hi for s in songs)
            if got < need:
                fails.append(f"only {got}/{len(songs)} songs have {field} in [{lo}, {hi}] (need {need})")
    if "genre_in_top" in expect:
        wanted = set(expect["genre_in_top"])
        if not any(s["genre"] in wanted for s in songs):
            fails.append(f"none of the top songs has genre in {sorted(wanted)}")
    if expect.get("no_repeat") and any(s["id"] in previous_ids for s in songs):
        fails.append("a follow-up answer repeated a song already shown")
    artists = [s["artist"].lower() for s in songs]
    if max(artists.count(a) for a in set(artists)) > 2:
        fails.append("more than 2 songs by one artist")
    return fails


def feedback_summary() -> str:
    """Summarize real user y/n ratings recorded by the CLI (human evaluation)."""
    path = os.path.join(ROOT, "logs", "events.jsonl")
    ratings = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("kind") == "feedback":
                    ratings.append(bool(record.get("helpful")))
    if not ratings:
        return "no user ratings recorded yet"
    return f"{sum(ratings)} of {len(ratings)} user ratings were positive"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    llm = get_llm() if args.llm else None
    if args.llm and llm is None:
        print("--llm requested but no ANTHROPIC_API_KEY/SDK available; aborting.")
        return 2
    app = App.from_defaults(llm=llm)
    with open(os.path.join(ROOT, "eval", "golden_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)

    rows, confidences, diversities, text_cases = [], [], [], 0
    for case in cases:
        confidence, needs_clarify, error, previous_ids = None, False, None, frozenset()
        if "profile" in case:
            clean, _ = normalize_prefs(case["profile"])
            recs = recommend_songs(case["profile"], app.songs, k=args.k)
            kind = "profile"
        else:
            text = case["text"] * case.get("repeat", 1)
            result = app.recommend(text, k=args.k, use_llm=bool(llm))
            previous_ids = frozenset(result.shown_ids)
            if "note" in case:  # simulate the user saying "no" and explaining what was off
                result = app.refine(result, case["note"], k=args.k, use_llm=bool(llm))
            recs, error, needs_clarify, confidence = (
                result.recs, result.error, result.needs_clarification, result.confidence)
            kind = "text"
            text_cases += 1
            if not error:
                confidences.append(confidence)
        fails = check(case["expect"], recs, error, needs_clarify, previous_ids)
        if recs and not error:
            diversities.append(len({s["artist"].lower() for s, _, _ in recs}) / len(recs))
        rows.append((case["id"], kind, not fails, confidence, "; ".join(fails)))

    passed = sum(1 for r in rows if r[2])
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    avg_div = sum(diversities) / len(diversities) if diversities else 0.0
    mode = "LLM parser" if llm else "offline rule-based parser"

    lines = [
        "# Evaluation report", "",
        f"- Mode: {mode}",
        f"- **{passed} of {len(rows)} golden cases passed**",
        f"- Average confidence on answered text requests: {avg_conf:.2f}",
        f"- Average artist diversity in the top {args.k} (distinct artists / songs): {avg_div:.2f}",
        f"- Human feedback from logs/events.jsonl: {feedback_summary()}", "",
        "| Case | Kind | Result | Confidence | Notes |", "|---|---|---|---|---|",
    ]
    for case_id, kind, ok, conf, note in rows:
        lines.append(f"| {case_id} | {kind} | {'PASS' if ok else 'FAIL'} | "
                     f"{'' if conf is None else f'{conf:.2f}'} | {note} |")
    report = "\n".join(lines) + "\n"
    with open(os.path.join(ROOT, "eval", "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
