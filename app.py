"""Web interface for the Apex Music Recommender.  Run with:  streamlit run app.py"""
import streamlit as st

from src.logging_setup import setup_logging
from src.pipeline import App

# Must be the first Streamlit call in the script.
st.set_page_config(page_title="Apex Music Recommender", page_icon="🎧", layout="wide")


@st.cache_resource
def load_app() -> App:
    """Load the songs and knowledge base once, not on every rerun."""
    setup_logging()
    return App.from_defaults(llm=None)


app = load_app()

st.title("Apex Music Recommender")
st.caption(f"{len(app.songs):,} songs · {len(app.kb.docs)} knowledge documents")

# A form groups widgets so nothing reruns until the submit button is pressed.
# Pressing Enter inside the text box also submits the form.
with st.form("search"):
    request = st.text_input("What do you want to hear?",
                            placeholder="A Legend like Wraith, or a vibe like 'calm focus music'")
    submitted = st.form_submit_button("Find music")

if submitted:
    # TODO (you): ask the app for recommendations and show them.
    #   1. Call app.recommend(...) with the text the user typed.
    #   2. If the result has an error, show it with st.error(...).
    #   3. Otherwise, loop over result.recs and show each song's title and score.
    #      Each item in result.recs is a tuple: (song_dict, score, reasons_text).

    result = app.recommend(request)
    if result.error:
        st.error(result.error)
    elif result.needs_clarification:
        st.warning("I'm not sure I understood that. Try naming a Legend or describing a mood.")
    else:
        for song, score, reasons in result.recs:
            st.write(f"{song['title']} ({score:.2f})")
            st.write(f"Reasons: {reasons}")