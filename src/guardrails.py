"""Input and output guardrails.

Free text from the user is untrusted, and so is whatever the LLM returns. Nothing
reaches the scorer without passing through these functions.
"""
import re
from typing import Dict, Iterable, List, Tuple

MAX_INPUT_CHARS = 500
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class GuardrailError(ValueError):
    """The input was rejected; the message is safe to show to the user."""


def sanitize_text(text) -> str:
    """Strip control characters and extra whitespace; reject empty or oversized input."""
    if not isinstance(text, str):
        raise GuardrailError("Please type a request as text.")
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", text).split())
    if not cleaned:
        raise GuardrailError("Your request was empty. Try a Legend name or a vibe like 'calm focus music'.")
    if len(cleaned) > MAX_INPUT_CHARS:
        raise GuardrailError(f"Your request is too long ({len(cleaned)} characters, max {MAX_INPUT_CHARS}).")
    return cleaned


def _clamp01(value, name: str, warnings: List[str]):
    try:
        number = float(value)
    except (TypeError, ValueError):
        warnings.append(f"dropped non-numeric {name}")
        return None
    if number != number:  # NaN
        warnings.append(f"dropped NaN {name}")
        return None
    if not 0.0 <= number <= 1.0:
        warnings.append(f"{name}={number} clamped into 0..1")
    return min(1.0, max(0.0, number))


def validate_profile(raw, known_genres: Iterable[str], known_moods: Iterable[str]) -> Tuple[Dict, List[str]]:
    """Validate a parsed profile (e.g. LLM JSON) against the catalog vocabulary.

    Unknown genres/moods are dropped, numbers are clamped, and the confidence is
    forced into 0..1. Raises GuardrailError if nothing usable remains.
    """
    if not isinstance(raw, dict):
        raise GuardrailError("The parsed profile was not an object.")
    genres_ok, moods_ok = set(known_genres), set(known_moods)
    warnings: List[str] = []
    profile: Dict = {}

    for key, vocab, label in (("genres", genres_ok, "genre"), ("moods", moods_ok, "mood")):
        values = raw.get(key, raw.get(label, []))
        values = values if isinstance(values, list) else [values]
        kept = []
        for value in values:
            text = " ".join(str(value).strip().lower().split())
            if text in vocab and text not in kept:
                kept.append(text)
            elif text:
                warnings.append(f"dropped unknown {label} {text!r}")
        if kept:
            profile[key] = kept

    for key in ("energy", "valence", "acousticness"):
        if raw.get(key) is not None:
            value = _clamp01(raw[key], key, warnings)
            if value is not None:
                profile[key] = value

    if not profile:
        raise GuardrailError("Could not extract any usable music preferences from that request.")

    conf = _clamp01(raw.get("confidence", 0.5), "confidence", warnings)
    profile["confidence"] = 0.5 if conf is None else conf
    return profile, warnings
