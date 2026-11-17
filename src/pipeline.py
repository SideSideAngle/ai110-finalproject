"""End-to-end flow: guardrails -> retrieve -> parse intent -> score -> explain -> log."""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from src.explainer import explain
from src.guardrails import MAX_INPUT_CHARS, GuardrailError, sanitize_text
from src.intent_parser import Intent, parse_intent
from src.llm import LLM
from src.logging_setup import log_event
from src.recommender import load_songs, max_possible_score, normalize_prefs, recommend_songs
from src.retriever import KnowledgeBase, Retrieved

logger = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONGS_CSV = os.path.join(ROOT, "data", "songs.csv")
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "knowledge")
CONFIDENCE_THRESHOLD = 0.35  # below this we ask the human to clarify instead of guessing


@dataclass
class Result:
    request: str
    intent: Optional[Intent] = None
    retrieved: List[Retrieved] = field(default_factory=list)
    recs: List[Tuple[Dict, float, str]] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    explanation_method: str = "template"
    confidence: float = 0.0
    max_score: float = 0.0  # best score any song could earn for this profile (for % match)
    needs_clarification: bool = False
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    shown_ids: Set[int] = field(default_factory=set)  # every song shown so far in this conversation
    refinement: int = 0  # 0 = first answer, 1+ = answers after "what was off?" feedback


class App:
    """Loads the catalog and knowledge base once; answers many requests."""

    def __init__(self, songs: List[Dict], kb: KnowledgeBase, llm: Optional[LLM] = None):
        self.songs, self.kb, self.llm = songs, kb, llm
        self.genres = sorted({s["genre"] for s in songs})
        self.moods = sorted({s["mood"] for s in songs})

    @classmethod
    def from_defaults(cls, llm: Optional[LLM] = None) -> "App":
        return cls(load_songs(SONGS_CSV), KnowledgeBase.load(KNOWLEDGE_DIR), llm)

    def recommend(self, text: str, k: int = 5, use_llm: bool = True) -> Result:
        """Answer a fresh request."""
        return self._run(text, k, self.llm if use_llm else None)

    def refine(self, previous: Result, note: str, k: int = 5, use_llm: bool = True) -> Result:
        """Answer again after the user said the first picks were off.

        With an LLM, the original request and the note are parsed together. Without
        one, the rule parser reads the note and adjusts the previous profile. If the
        note is empty or not understood, the previous profile is kept. Either way,
        songs already shown are excluded so the user always sees something new.
        """
        llm = self.llm if use_llm else None
        try:
            note = sanitize_text(note)
        except GuardrailError:
            note = ""
        base = previous.intent.profile if previous.intent else None
        if llm and note:
            text, base = f"{previous.request}. Listener feedback on the first picks: {note}"[:MAX_INPUT_CHARS], None
        else:
            text = note or previous.request
        result = self._run(text, k, llm, exclude_ids=previous.shown_ids, base=base,
                           refinement=previous.refinement + 1)
        if note and base is not None:
            result.request = f"{previous.request} (+ {note})"
        return result

    @staticmethod
    def _merge_follow_up(base: Dict, note_intent: Intent) -> Dict:
        """Overlay what the follow-up note said on top of the earlier profile.

        If the note moves the energy target a lot and names no new genre or mood, the
        old genre/mood (picked for the old energy) would outvote the new target, so
        they are dropped and the numeric targets drive the ranking instead.
        """
        note = note_intent.profile
        merged = {**base, **note}
        big_shift = "energy" in note and "energy" in base and abs(note["energy"] - base["energy"]) >= 0.3
        if big_shift and "genres" not in note and "moods" not in note:
            merged.pop("genres", None)
            merged.pop("moods", None)
            note_intent.warnings.append("energy changed a lot, so I dropped the earlier genre and mood")
        return merged

    def _run(self, text: str, k: int, llm: Optional[LLM], exclude_ids: Optional[Set[int]] = None,
             base: Optional[Dict] = None, refinement: int = 0) -> Result:
        started = time.time()
        result = Result(request=text, refinement=refinement,
                        shown_ids=set(exclude_ids or ()))
        try:
            clean_text = sanitize_text(text)
            result.request = clean_text
            result.retrieved = self.kb.retrieve(clean_text)
            if base is not None:
                # A short follow-up like "too slow" must only tweak the earlier profile, so
                # ignore weak document matches; naming a Legend (score 1.0) still counts.
                result.retrieved = [r for r in result.retrieved if r.score >= 0.5]
            try:
                result.intent = parse_intent(clean_text, result.retrieved, self.genres, self.moods, llm)
                if base is not None:  # rule-parsed follow-up note: adjust the previous profile
                    result.intent.profile = self._merge_follow_up(base, result.intent)
            except GuardrailError:
                if base is None:
                    raise
                # the follow-up note was not understood: keep the previous profile, show new songs
                result.intent = Intent(dict(base), 0.5, "previous", ["follow-up not understood, kept your earlier request"])
            result.warnings.extend(result.intent.warnings)

            clean_prefs, pref_warnings = normalize_prefs(result.intent.profile)
            result.warnings.extend(pref_warnings)
            result.max_score = max_possible_score(clean_prefs)
            result.recs = recommend_songs(result.intent.profile, self.songs, k=k,
                                          exclude_ids=result.shown_ids)
            result.shown_ids |= {song["id"] for song, _, _ in result.recs}
            top_ratio = result.recs[0][1] / max_possible_score(clean_prefs) if result.recs else 0.0
            result.confidence = round(0.6 * result.intent.confidence + 0.4 * top_ratio, 3)
            # a follow-up is never blocked: the user already told us what they want
            result.needs_clarification = refinement == 0 and result.confidence < CONFIDENCE_THRESHOLD
            if not result.needs_clarification:
                result.explanations, result.explanation_method = explain(
                    result.recs, result.retrieved, self.kb.legend_names, llm)
        except GuardrailError as exc:
            result.error = str(exc)
        except Exception as exc:  # last line of defence: never crash the user's session
            logger.exception("Unexpected failure while handling request")
            result.error = "Something went wrong while building recommendations. Please try again."
            log_event("unexpected_error", error=f"{type(exc).__name__}: {exc}", request=text)

        log_event(
            "request", request=result.request, error=result.error, refinement=result.refinement,
            retrieved=[(r.doc.name, round(r.score, 3)) for r in result.retrieved],
            profile=result.intent.profile if result.intent else None,
            parser=result.intent.source if result.intent else None,
            intent_confidence=result.intent.confidence if result.intent else None,
            confidence=result.confidence, needs_clarification=result.needs_clarification,
            explanation_method=result.explanation_method, warnings=result.warnings,
            top=[(s["title"], round(sc, 3)) for s, sc, _ in result.recs],
            seconds=round(time.time() - started, 3),
        )
        return result
