"""Command line interface for the SymphonySearch.

    python -m src.main                      # interactive prompt
    python -m src.main "calm focus music"   # one-shot request
    python -m src.main --offline "Wraith"   # skip the LLM, use the rule-based fallback
"""
import argparse
import sys

from src.logging_setup import log_event, setup_logging
from src.llm import get_llm
from src.pipeline import App, Result


def render(result: Result) -> str:
    if result.error:
        return f"\n[!] {result.error}\n"
    lines = []
    profile = result.intent.profile
    lines.append(f"\nRequest: {result.request}")
    if result.retrieved:
        lines.append("Retrieved context: " + ", ".join(
            f"{r.doc.name} ({r.score:.2f})" for r in result.retrieved))
    shown = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in profile.items()}
    lines.append(f"Parsed by {result.intent.source}: {shown}")
    lines.append(f"Confidence: {result.confidence:.2f}")
    if result.needs_clarification:
        lines.append("\nI'm not confident I understood that. Try naming a Legend or describing the "
                     "mood, e.g. 'tense, dark music for ranked' or 'Octane'.\n")
        return "\n".join(lines)
    lines.append("")
    for i, ((song, score, _), why) in enumerate(zip(result.recs, result.explanations), start=1):
        lines.append(f"{i}. {song['title']} - {song['artist']} [{song['genre']}, {song['mood']}] "
                     f"score {score:.2f}")
        lines.append(f"   {why}")
    for warning in result.warnings:
        lines.append(f"(note: {warning})")
    return "\n".join(lines) + "\n"


MAX_REFINEMENTS = 3


def is_interactive() -> bool:
    return sys.stdin.isatty()


def ask_feedback(result: Result) -> str:
    """Human evaluation hook: one-key rating, logged. Returns "y", "n" or "" (skipped)."""
    if result.error or result.needs_clarification or not is_interactive():
        return ""
    answer = input("Were these recommendations good? [y/n/Enter to skip] ").strip().lower()
    if answer not in ("y", "n"):
        return ""
    log_event("feedback", request=result.request, helpful=(answer == "y"),
              confidence=result.confidence, refinement=result.refinement)
    return answer


def converse(app: App, text: str, k: int) -> Result:
    """Answer a request; on a "no", ask what was off and try again with new songs."""
    result = app.recommend(text, k=k)
    print(render(result))
    for _ in range(MAX_REFINEMENTS):
        if ask_feedback(result) != "n":
            break
        note = input("What was off? (e.g. 'too slow', 'more acoustic', 'try rock'; Enter to just "
                     "see different songs) ").strip()
        log_event("feedback_note", request=result.request, note=note)
        result = app.refine(result, note, k=k)
        print(render(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="SymphonySearch")
    parser.add_argument("request", nargs="*", help="what you want to hear (omit for interactive mode)")
    parser.add_argument("--offline", action="store_true", help="never call the LLM")
    parser.add_argument("-k", type=int, default=5, help="number of songs")
    args = parser.parse_args()

    setup_logging()
    app = App.from_defaults(llm=None if args.offline else get_llm())
    mode = "LLM + rule-based fallback" if app.llm else "offline (rule-based)"
    print(f"Loaded {len(app.songs)} songs, {len(app.kb.docs)} knowledge docs. Mode: {mode}")

    if args.request:
        print(render(app.recommend(" ".join(args.request), k=args.k)))
        return
    print("Describe what you want to hear, or name a Legend (blank line to quit).")
    while True:
        try:
            text = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not text.strip():
            break
        converse(app, text, args.k)


if __name__ == "__main__":
    main()
