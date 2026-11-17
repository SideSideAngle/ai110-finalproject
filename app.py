"""Web interface for SymphonySearch.  Run with:  streamlit run app.py

Streamlit reruns this whole script on every click, so anything that must survive
between clicks (the current result, the user's key) lives in st.session_state.
"""
import os
from pathlib import Path

# The web app does not store what visitors type. Set LOG_REQUEST_TEXT=1 to override.
os.environ.setdefault("LOG_REQUEST_TEXT", "0")

import streamlit as st  # noqa: E402

from src.llm import make_llm, validate_llm  # noqa: E402
from src.logging_setup import log_event, setup_logging  # noqa: E402
from src.pipeline import App, Result  # noqa: E402
from src.ui_helpers import (genre_chip, match_percent, mood_chip, song_header,  # noqa: E402
                            youtube_search_url)

MAX_ROUNDS = 3  # how many "try again" rounds a visitor gets per search
STYLE_CSS = Path(__file__).parent / "assets" / "style.css"
EXAMPLES = ("calm focus music for studying", "I just lost a ranked match and I'm so tilted",
            "something romantic for a date night")

# Must be the first Streamlit call in the script.
st.set_page_config(page_title="SymphonySearch", page_icon="🎼", layout="wide")

try:  # styling is a nicety: if the file is missing the app still works, just plainer
    st.markdown(f"<style>{STYLE_CSS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
except OSError:
    pass


@st.cache_resource
def load_base() -> App:
    """Load the songs and knowledge base once and share them between visitors."""
    setup_logging()
    return App.from_defaults(llm=None)


base = load_base()
ss = st.session_state
for name, default in (("llm", None), ("key_msg", None), ("result", None),
                      ("rated", False), ("asking_note", False), ("pending", None)):
    ss.setdefault(name, default)

# Each visitor gets their own App wrapper (cheap) holding only their own LLM, if any.
app = App(base.songs, base.kb, ss.llm)


# ---------------------------------------------------------------- callbacks
def run_search(text: str) -> None:
    with st.spinner("Finding your sound..."):
        ss.result = app.recommend(text)
    ss.rated, ss.asking_note = False, False


def queue_search(text: str) -> None:
    ss.pending = text


def rate_good(result: Result) -> None:
    log_event("feedback", request=result.request, helpful=True,
              confidence=result.confidence, refinement=result.refinement)
    ss.rated = True


def rate_bad(result: Result) -> None:
    log_event("feedback", request=result.request, helpful=False,
              confidence=result.confidence, refinement=result.refinement)
    ss.asking_note = True


def retry_with_note(current_app: App) -> None:
    note = ss.get("note_input", "")
    log_event("feedback_note", request=ss.result.request, note=note)
    ss.result = current_app.refine(ss.result, note)
    ss.asking_note, ss.rated = False, False
    ss["note_input"] = ""


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("AI mode")
    api_key = st.text_input("Anthropic API key (optional)", type="password",
                            help="Paste your own key to turn on the LLM. Without one the app "
                                 "still works using its built-in rule-based parser.")
    if st.button("Use this key"):
        api_key = api_key.strip()
        if not api_key:
            ss.llm, ss.key_msg = None, ("info", "No key entered. Using offline mode.")
        else:
            with st.spinner("Checking your key..."):
                candidate = make_llm(api_key)
                ok, message = (validate_llm(candidate) if candidate
                               else (False, "The anthropic package is missing."))
            ss.llm = candidate if ok else None
            ss.key_msg = ("success" if ok else "error", message)
        st.rerun()
    if ss.key_msg:
        getattr(st, ss.key_msg[0])(ss.key_msg[1])
    st.markdown("**Mode:** " + ("🤖 LLM + fallback" if ss.llm else "⚙️ Offline (rule-based)"))
    st.caption("Your key is kept only in this browser session's memory. It is never saved "
               "to disk or written to the logs.")

# --------------------------------------------------------------------- page
st.title("🎼 SymphonySearch")
st.markdown(f'<p class="hero-sub">Describe a vibe or pick a Legend, and find music that fits. '
            f'{len(base.songs):,} songs · {len(base.kb.docs)} knowledge documents</p>',
            unsafe_allow_html=True)

# The search box is the star of the page: top and centered (middle column of three).
_, centre, _ = st.columns([1, 3, 1])
with centre:
    # A form groups widgets so nothing reruns until submit. Enter in the box also submits.
    with st.form("search"):
        request = st.text_input("What do you want to hear?", label_visibility="collapsed",
                                placeholder="A Legend like Wraith, or a vibe like 'calm focus music'")
        submitted = st.form_submit_button("Find music", use_container_width=True)

if submitted:
    run_search(request)
elif ss.pending:
    text, ss.pending = ss.pending, None
    run_search(text)

with st.expander("Quick start: pick a Legend or a situation", expanded=ss.result is None):
    for label, names in (("Legends", base.kb.legend_names),
                         ("Situations", [d.name for d in base.kb.docs if d.kind == "situation"])):
        st.caption(label)
        cols = st.columns(5)
        for i, name in enumerate(names):
            cols[i % 5].button(name, key=f"quick_{name}", on_click=queue_search, args=(name,))

# ------------------------------------------------------------------ results
result: Result = ss.result
if result is not None:
    if result.error:
        st.error(result.error)
    elif result.needs_clarification:
        st.warning("I'm not sure I understood that. Try naming a Legend or describing a mood.")
    else:
        if result.refinement:
            st.info(f"Try {result.refinement} of {MAX_ROUNDS}: {result.request}")
        for i, (song, score, reasons) in enumerate(result.recs):
            with st.container(border=True):
                st.markdown(song_header(i + 1, song["title"], song["artist"]), unsafe_allow_html=True)
                st.markdown(genre_chip(song["genre"]) + mood_chip(song["mood"]), unsafe_allow_html=True)
                pct = match_percent(score, result.max_score)
                st.progress(pct, text=f"{pct}% match")
                if i < len(result.explanations):
                    st.write(result.explanations[i])
                with st.expander("Score breakdown"):
                    for piece in reasons.split("; "):
                        st.write(f"- {piece}")
                st.link_button("Listen on YouTube", youtube_search_url(song["title"], song["artist"]))

        with st.expander("Why these songs? (how the AI got here)"):
            st.write(f"**Parsed by:** {result.intent.source} · **Confidence:** {result.confidence:.2f} · "
                     f"**Explanations:** {result.explanation_method}")
            if result.retrieved:
                st.write("**Retrieved from the knowledge base:**")
                for r in result.retrieved:
                    st.write(f"- {r.doc.name} ({r.doc.kind}), similarity {r.score:.2f}: {r.doc.text}")
            else:
                st.write("Nothing in the knowledge base matched, so keyword rules were used.")
            st.write("**Profile used for scoring:**")
            st.json({k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in result.intent.profile.items()})
            for warning in result.warnings:
                st.caption(f"Note: {warning}")

        # ---------------------------------------------------------- feedback
        if ss.rated:
            st.success("Thanks for the feedback!")
        elif not ss.asking_note:
            st.write("Were these recommendations good?")
            good, bad, _ = st.columns([1, 1, 6])
            good.button("👍 Yes", on_click=rate_good, args=(result,))
            bad.button("👎 Not quite", on_click=rate_bad, args=(result,))
        elif result.refinement >= MAX_ROUNDS:
            st.info("That was the last retry. Try rewording your search above.")
        else:
            with st.form("refine"):
                st.text_input("What was off?", key="note_input",
                              placeholder="e.g. too slow, more acoustic, try rock (or leave blank for new songs)")
                st.form_submit_button("Try again", on_click=retry_with_note, args=(app,))
else:
    # Welcome state: nothing searched yet, so show how it works and one-click examples.
    st.write("")
    steps = st.columns(3)
    for col, (title, body) in zip(steps, (
            ("1. Say what you want", "Name a Legend, a situation, or just describe a mood."),
            ("2. We look it up", "Matching notes are retrieved from our knowledge base to shape the search."),
            ("3. Get music, with reasons", "Every song comes with a match score and a plain explanation."))):
        col.markdown(f'<div class="welcome-step"><b>{title}</b><br>{body}</div>', unsafe_allow_html=True)
    st.caption("Or try one of these:")
    example_cols = st.columns(len(EXAMPLES))
    for col, example in zip(example_cols, EXAMPLES):
        col.button(example, key=f"example_{example}", on_click=queue_search, args=(example,))
