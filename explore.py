"""Interactive "how it works" explorer.  Run with:  streamlit run explore.py

Type a request and watch each stage of the recommender produce its real output,
then change the scoring weights and watch the ranking move. Nothing here is a
mock-up: it calls the same retriever, parser and scorer the main app uses.
"""
import os
import re

os.environ.setdefault("LOG_REQUEST_TEXT", "0")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402

from src.guardrails import GuardrailError  # noqa: E402
from src.intent_parser import CUES, parse_with_rules  # noqa: E402
from src.pipeline import App  # noqa: E402
from src import recommender as rec  # noqa: E402

st.set_page_config(page_title="How SymphonySearch works", page_icon="🔬", layout="wide")


@st.cache_resource
def load_base() -> App:
    return App.from_defaults(llm=None)


base = load_base()
kb = base.kb

DEFAULT_WEIGHTS = {"genre": rec.GENRE_WEIGHT, "mood": rec.MOOD_WEIGHT, "energy": rec.ENERGY_WEIGHT,
                   "valence": rec.VALENCE_WEIGHT, "acousticness": rec.ACOUSTIC_WEIGHT}


def song_points(clean: dict, song: dict, w: dict) -> dict:
    """Same formulas as src/recommender.py, but with weights you can change."""
    pts = dict.fromkeys(DEFAULT_WEIGHTS, 0.0)
    if clean["genres"]:
        factor, _ = rec._genre_factor(song["genre"], clean["genres"])
        pts["genre"] = w["genre"] * factor
    if song["mood"] in clean["moods"]:
        pts["mood"] = w["mood"]
    for key in ("energy", "valence", "acousticness"):
        if key in clean:
            pts[key] = w[key] * max(0.0, 1.0 - abs(song[key] - clean[key]))
    return pts


def rank(clean: dict, w: dict, n: int = 10) -> pd.DataFrame:
    rows = []
    for s in base.songs:
        p = song_points(clean, s, w)
        rows.append({"song": f"{s['title']} - {s['artist']}", "genre": s["genre"], "mood": s["mood"],
                     **p, "total": sum(p.values())})
    return pd.DataFrame(rows).sort_values("total", ascending=False).head(n).reset_index(drop=True)


# ------------------------------------------------------------------ header
st.title("🔬 How SymphonySearch works")
st.write("Type any request. Each tab below shows what one stage of the system did with it, "
         "using the real code. Go left to right.")
request = st.text_input("Your request", value="calm focus music for studying",
                        help="Try: wraith · I just lost a ranked match and I'm so tilted · "
                             "something romantic · zzzz")

tabs = st.tabs(["0. Big picture", "1. Retriever (RAG)", "2. Intent parser", "3. Scoring + weights",
                "4. LLM vs no LLM"])

# ---------------------------------------------------------------- 0 overview
with tabs[0]:
    st.markdown("""
**The whole system is a relay race with one rule: the LLM never picks songs.**

| Stage | Question it answers | Uses LLM? |
|---|---|---|
| Guardrails | Is the text safe and usable? | No |
| **Retriever** | Which of my 23 notes is this request about? | No (TF-IDF math) |
| **Intent parser** | What music profile does that mean? (genre, mood, energy...) | Optional, with a no-LLM fallback |
| **Scorer** | How well does each of 2,700 songs fit that profile? | **Never** |
| Explainer | Say why, in plain words | Optional, checked against the real scores |

**RAG** = Retrieval-Augmented Generation: *retrieve* relevant notes first, then hand them to the
step that *generates* (the parser), so it works from your knowledge, not just from guessing.
Here the retrieved note literally becomes the starting profile, so it changes which songs win.

Open the tabs in order. Each one uses the request you typed above.
""")

# --------------------------------------------------------------- 1 retriever
with tabs[1]:
    st.subheader("Retriever: score every note against your request")
    st.markdown(
        "**Step A, clean the text.** Common words and my filler words are thrown away; "
        "what's left (plus two-word pairs) is what gets compared.")
    tokens = kb._vectorizer.build_analyzer()(request)
    st.code(" | ".join(tokens) if tokens else "(nothing left: the request had only filler words)")

    st.markdown("**Step B, compare to all 23 notes.** Cosine similarity: 0 = no shared "
                "(rare) words, 1 = identical. A note whose *name* appears in your text gets 1.0.")
    sims = cosine_similarity(kb._vectorizer.transform([request]), kb._matrix)[0]
    lowered = request.lower()
    rows = []
    for doc, sim in zip(kb.docs, sims):
        named = bool(re.search(rf"\b{re.escape(doc.name.lower())}\b", lowered))
        final = 1.0 if named else float(sim)
        rows.append({"note": doc.name, "type": doc.kind, "TF-IDF similarity": round(float(sim), 3),
                     "name mentioned?": "yes -> 1.0" if named else "", "final score": round(final, 3),
                     "kept?": "KEPT" if final >= 0.15 else "dropped (< 0.15)"})
    table = pd.DataFrame(rows).sort_values("final score", ascending=False).reset_index(drop=True)
    st.dataframe(table, hide_index=True, width="stretch")
    kept = kb.retrieve(request)
    st.markdown("**Step C, keep the top 2 that cleared 0.15.** That's `retrieve()`'s return value:")
    if kept:
        for r in kept:
            st.success(f"**{r.doc.name}** ({r.doc.kind}), score {r.score:.2f}")
            st.caption(r.doc.text)
            st.json(r.doc.music_profile)
    else:
        st.warning("Nothing retrieved. The parser will rely on keyword rules alone.")

# ------------------------------------------------------------------ 2 parser
with tabs[2]:
    st.subheader("Intent parser: from words to a music profile (no-LLM path)")
    retrieved = kb.retrieve(request)
    st.markdown("**Step A, start from the retrieved note's profile** (this is where RAG changes the result):")
    st.json(retrieved[0].doc.music_profile if retrieved else {})
    st.markdown("**Step B, keyword cues.** Each pattern below that matches your text overrides "
                "part of the profile. Later ones win.")
    fired = [(p, a) for p, a in CUES.items() if re.search(rf"\b(?:{p})", request.lower())]
    if fired:
        for pattern, adjust in fired:
            st.write(f"`{pattern}` -> {adjust}")
    else:
        st.caption("No cue words matched.")
    st.markdown("**Step C, validate and score confidence.** Unknown genres are dropped, numbers "
                "clamped to 0-1, and a confidence is computed.")
    try:
        intent = parse_with_rules(request, retrieved, base.genres, base.moods)
        c1, c2 = st.columns(2)
        c1.metric("Confidence", f"{intent.confidence:.2f}",
                  help="0.3 + 0.7 x retrieval score, plus up to 0.2 for cue hits. "
                       "Below 0.35 the app asks you to clarify.")
        c2.metric("Needs clarification?", "yes" if intent.confidence < 0.35 else "no")
        st.markdown("**Final profile handed to the scorer:**")
        st.json({k: (round(v, 2) if isinstance(v, float) else v) for k, v in intent.profile.items()})
        for w in intent.warnings:
            st.caption(f"Note: {w}")
    except GuardrailError as exc:
        intent = None
        st.error(f"Nothing understood, so the app would ask for a clearer request. ({exc})")

# ------------------------------------------------------------------ 3 scoring
with tabs[3]:
    st.subheader("Scoring: every song gets points per signal")
    if intent is None:
        st.info("Type a request the parser understands (see tab 2) to use this tab.")
    else:
        st.markdown(
            "For each song: **genre** and **mood** are all-or-nothing (genre gets half credit for a "
            "related genre like *indie pop* vs *pop*); **energy, valence, acousticness** earn points "
            "by closeness: `weight x (1 - |song - target|)`. Signals the profile doesn't mention are skipped.")
        st.markdown("#### Your profile (edit it too)")
        p = intent.profile
        key = str(abs(hash(request)))
        a, b = st.columns(2)
        genres = a.multiselect("Genres", base.genres, default=[g for g in p.get("genres", []) if g in base.genres],
                               key=f"g{key}")
        moods = b.multiselect("Moods", base.moods, default=[m for m in p.get("moods", []) if m in base.moods],
                              key=f"m{key}")
        clean = {"genres": genres, "moods": moods}
        cols = st.columns(3)
        for col, name in zip(cols, ("energy", "valence", "acousticness")):
            on = col.checkbox(f"Target {name}", value=name in p, key=f"{name}on{key}")
            if on:
                clean[name] = col.slider(name, 0.0, 1.0, float(p.get(name, 0.5)), 0.05, key=f"{name}v{key}")

        st.markdown("#### Weights (points a perfect match earns)")
        wcols = st.columns(5)
        w = {name: col.slider(name, 0.0, 4.0, DEFAULT_WEIGHTS[name], 0.25, key=f"w_{name}")
             for col, name in zip(wcols, DEFAULT_WEIGHTS)}

        mine = rank(clean, w)
        default = rank(clean, DEFAULT_WEIGHTS)
        left, right = st.columns(2)
        with left:
            st.markdown("**Top 10 with YOUR weights** (stacked bar = points from each signal)")
            st.bar_chart(mine.set_index("song")[list(DEFAULT_WEIGHTS)], horizontal=True, stack=True)
        with right:
            st.markdown("**Top 10 with the DEFAULT weights** (genre 2, mood 1, energy 1, valence .5, acoustic .5)")
            st.bar_chart(default.set_index("song")[list(DEFAULT_WEIGHTS)], horizontal=True, stack=True)
        moved = [s for s in mine["song"].head(5) if s not in set(default["song"].head(5))]
        if w == DEFAULT_WEIGHTS:
            st.caption("Weights are at their defaults, so both sides match. Drag a slider.")
        elif moved:
            st.warning(f"Changing the weights pulled {len(moved)} new song(s) into your top 5: " + "; ".join(moved))
        else:
            st.info("Same top 5 songs, though the order or scores may differ. Try a bigger change, "
                    "like energy to 4 and genre to 0.")
        st.dataframe(mine.round(2), hide_index=True, width="stretch")
        st.caption("Real-app extras on top of this: at most 2 songs per artist, and songs you've "
                   "already seen are skipped on retries.")

# -------------------------------------------------------------- 4 llm vs none
with tabs[4]:
    st.subheader("What changes with an API key")
    st.markdown("""
| | **No key (offline)** | **With your key** |
|---|---|---|
| Retriever | same | same |
| Intent parser | Retrieved note + keyword cues (what tab 2 shows) | The LLM reads your words **and** the retrieved notes and returns a JSON profile |
| Confidence | from retrieval score + cue hits | `0.6 x LLM's own rating + 0.4 x retrieval score` |
| Scorer / ranking | same | same |
| Explanations | templates from the real score reasons | LLM-written, then checked: any claim about a Legend not retrieved is rejected |
| If the LLM fails | n/a | automatically falls back to the offline path |

**Where the LLM actually helps:** requests the cue list has never seen, e.g. *"music for a
rainy drive home after a long shift"*. Rules have no cue for that; an LLM understands it and
still gets grounded by the retrieved notes. **Where it can't hurt:** the list of songs is chosen by the
same deterministic scorer either way, and its output is validated before use.
""")
    st.markdown("**Exactly what the LLM is sent** (for your current request):")
    from src.intent_parser import SYSTEM_PROMPT  # noqa: E402
    ctx = "\n".join(f"- [{r.doc.kind}] {r.doc.name}: {r.doc.text}" for r in kb.retrieve(request)) or "(none)"
    st.code(f"SYSTEM: {SYSTEM_PROMPT}\n\nUSER:\nRequest: {request}\n\nRetrieved context:\n{ctx}\n"
            f"Allowed genres: ...{len(base.genres)} genres\nAllowed moods: ...{len(base.moods)} moods",
            language="text")
