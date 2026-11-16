"""Explain recommendations in plain language, grounded in the retrieved documents.

The LLM writes one short sentence per song from the real score reasons and the
retrieved text. check_explanations() rejects replies that are malformed or that
mention a Legend we did not retrieve; on rejection we use a template built purely
from the score reasons, so an explanation is always shown and always true.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

from src.llm import LLM
from src.logging_setup import log_event
from src.retriever import Retrieved

logger = logging.getLogger(__name__)
MAX_EXPLANATION_CHARS = 300

SYSTEM_PROMPT = (
    "You explain music recommendations. For each numbered song write ONE friendly sentence "
    "(under 40 words) saying why it fits, using only the score reasons and the context given. "
    "Do not invent facts, and mention a Legend only if it appears in the context. "
    "Reply with ONLY a JSON list of strings, one per song, in order."
)


def template_explanation(reasons: str, retrieved: Sequence[Retrieved]) -> str:
    theme = f" Fits the {retrieved[0].doc.name} vibe." if retrieved else ""
    return f"Because: {reasons}.{theme}" if reasons else f"Closest available match.{theme}"


def check_explanations(texts, expected: int, retrieved_names: Sequence[str],
                       all_legend_names: Sequence[str]) -> Tuple[bool, str]:
    """Return (ok, reason). Guards against bad structure and ungrounded Legend names."""
    if not isinstance(texts, list) or len(texts) != expected:
        return False, "wrong number of explanations"
    allowed = {n.lower() for n in retrieved_names}
    for text in texts:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_EXPLANATION_CHARS:
            return False, "empty or oversized explanation"
        for name in all_legend_names:
            if name.lower() not in allowed and re.search(rf"\b{re.escape(name.lower())}\b", text.lower()):
                return False, f"mentions ungrounded Legend {name}"
    return True, "ok"


def explain(recs: Sequence[Tuple[Dict, float, str]], retrieved: Sequence[Retrieved],
            all_legend_names: Sequence[str], llm: Optional[LLM] = None) -> Tuple[List[str], str]:
    """Return (explanations, method) where method is "llm" or "template"."""
    templates = [template_explanation(reasons, retrieved) for _, _, reasons in recs]
    if llm is None or not recs:
        return templates, "template"
    try:
        context = "\n".join(f"- {r.doc.name}: {r.doc.text}" for r in retrieved) or "(none)"
        songs = "\n".join(f"{i}. {s['title']} by {s['artist']} - {reasons}"
                          for i, (s, _, reasons) in enumerate(recs, start=1))
        reply = llm(SYSTEM_PROMPT, f"Context:\n{context}\n\nSongs:\n{songs}")
        match = re.search(r"\[.*\]", reply, re.DOTALL)
        texts = json.loads(match.group(0)) if match else None
        ok, why = check_explanations(texts, len(recs), [r.doc.name for r in retrieved], all_legend_names)
        if ok:
            return [t.strip() for t in texts], "llm"
        logger.warning("LLM explanations rejected: %s", why)
        log_event("explanation_rejected", reason=why)
    except Exception as exc:
        logger.warning("LLM explanation failed (%s: %s); using templates", type(exc).__name__, exc)
        log_event("explanation_failed", error=f"{type(exc).__name__}: {exc}")
    return templates, "template"
