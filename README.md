# SymphonySearch: RAG-powered music picks by Legend and vibe

## Original project

This project extends my **Music Recommender Simulation** (Modules 1-3). The original was a content-based recommender: it loaded a hand-written 19-song CSV, compared each song to a hand-coded taste profile (favorite genre, favorite mood, target energy), and ranked songs by a points score (genre +2, mood +1, energy closeness up to +1). It printed a "Because: ..." line for every pick, but the user profile had to be written in code and genre and mood had to match exactly.

## Title and summary

**SymphonySearch** lets you type *"Wraith"*, *"I just lost a ranked match and I'm so tilted"*, or *"quiet music to study"* and get songs that fit, with the reasons.

Why it matters: the original could only answer to a profile a programmer typed in, from 19 songs. Now:

- **RAG:** a small knowledge base of Apex Legends personalities and listening situations is retrieved for every request. The retrieved text decides the target energy, mood and genres, so retrieval directly changes which songs are ranked. It is not printed next to a standard answer.
- **Real catalog:** 2,700 real songs (25 most popular per genre) from the public Spotify Tracks dataset.
- **Reliability layer:** guardrails, confidence scoring, an LLM-to-rules fallback, logging, unit tests and a golden-case evaluation harness.

## Architecture overview

Full diagram with the human and testing checkpoints: [docs/system_diagram.md](docs/system_diagram.md).

1. **Guardrails** ([src/guardrails.py](src/guardrails.py)) clean and reject bad input.
2. **Retriever** ([src/retriever.py](src/retriever.py)) finds the best-matching Legend or situation documents using TF-IDF. An exact Legend name scores 1.0.
3. **Intent parser** ([src/intent_parser.py](src/intent_parser.py)) turns the request plus retrieved documents into a profile (genres, moods, energy, valence, acousticness). An LLM does this when an API key is available. Otherwise, or if the LLM errors or returns invalid JSON, a rule-based parser uses the same retrieved documents. Both outputs are validated against the catalog vocabulary.
4. **Confidence check:** if overall confidence is below 0.35, the app asks the user to clarify instead of guessing.
5. **Scorer** ([src/recommender.py](src/recommender.py)) is deterministic and does all the ranking, so the LLM never decides which songs win. It uses artist diversity (max 2 per artist).
6. **Explainer** ([src/explainer.py](src/explainer.py)) writes one sentence per song grounded in the retrieved text and score reasons. A checker rejects it if it is malformed or names a Legend that was not retrieved; then a template built from the score reasons is used.
7. **Feedback loop** ([src/main.py](src/main.py), `App.refine` in [src/pipeline.py](src/pipeline.py)): after each answer the CLI asks if it was good. A "no" asks *what was off?* and tries again, up to 3 times. The follow-up note adjusts the earlier profile (or, with an LLM, is parsed together with the original request), and songs already shown are never repeated. Every rating and note is logged.
8. **Logging** ([src/logging_setup.py](src/logging_setup.py)): every request, fallback and error goes to `logs/app.log` and `logs/events.jsonl`.

## Setup instructions

Requires Python 3.10+.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) enable the LLM. Without this the app runs fully offline.
cp .env.example .env             # then put your ANTHROPIC_API_KEY in .env

# 4a. Web app (recommended)
streamlit run app.py                       # opens http://localhost:8501

# 4b. or the command line (from the repo root)
python -m src.main                         # interactive
python -m src.main "Octane"                # one request
python -m src.main --offline "Wraith"      # force the rule-based parser

# 5. Tests and evaluation
pytest
python eval/run_eval.py                    # writes eval/report.md
```

`data/songs.csv` is already included. To rebuild it from the source dataset: `python -m src.catalog` (downloads about 20 MB from Hugging Face; `--source path.csv` uses a local copy).

### Using the web app

- Pick a **Legend** or **situation** button, or type a request and press Enter or **Find music**.
- Each song card shows a % match, a short explanation, a collapsible score breakdown, and a YouTube search link.
- **Why these songs?** shows what was retrieved from the knowledge base, the parsed profile, and the confidence.
- 👎 **Not quite** asks what was off and tries again (up to 3 times, never repeating songs). 👍 logs a positive rating.
- **Your own API key (optional):** paste an Anthropic key in the sidebar to switch from the offline rule-based parser to the LLM. The key is checked with one tiny call, kept only in your browser session's memory, and never written to disk or logs. Without a key everything still works offline.
- **Privacy:** the web app does not store what you type (`LOG_REQUEST_TEXT=0` by default); it logs only ratings, confidence and parser info. Set `LOG_REQUEST_TEXT=1` to log text locally.

### Deploying (Streamlit Community Cloud)

Push this branch to GitHub, then at share.streamlit.io choose the repo, the branch, and `app.py` as the main file. No secrets are needed because visitors bring their own key.

## Sample interactions

These are real outputs from `python -m src.main --offline ...` (top 3 of 5 shown, "Because" details shortened).

**1. A Legend name**
```
> Wraith
Retrieved context: Wraith (1.00)
Parsed by fallback: {'genres': ['trip hop', 'ambient', 'industrial', 'goth'], 'moods': ['moody', 'melancholic'], 'energy': 0.5, 'valence': 0.2, 'acousticness': 0.15}
Confidence: 0.96

1. Sunsetz - Cigarettes After Sex [ambient, melancholic] score 4.90
   Because: genre match: ambient (+2.0); mood match: melancholic (+1.0); energy 0.48 vs target 0.50 (+0.98); ... Fits the Wraith vibe.
2. Apocalypse - Cigarettes After Sex [ambient, melancholic] score 4.89
3. Test & Recognise - Flume Re-work - Seekae [ambient, melancholic] score 4.85
```

**2. A free-text situation (retrieval plus keyword cues)**
```
> I just lost a ranked match and I'm so tilted
Retrieved context: Tilted after a loss (0.19), Ranked grind (0.19)
Parsed by fallback: {'genres': ['metalcore', 'hardcore', 'grunge', 'punk'], 'moods': ['angry', 'intense'], 'energy': 0.9, ...}
Confidence: 0.70

1. Times Like These - Foo Fighters [grunge, angry] score 4.93
2. The Kill - Thirty Seconds To Mars [grunge, angry] score 4.92
3. MIDDLE OF THE NIGHT - Loveless [punk, angry] score 4.92
```

**3. Calm studying (the word "calm" overrides the retrieved energy)**
```
> calm focus music for studying
Retrieved context: Studying or homework (0.30), Crypto (0.09)
Parsed by fallback: {'genres': ['study', 'ambient', 'piano', 'classical'], ..., 'energy': 0.25, 'acousticness': 0.85}
Confidence: 0.81

1. The Four Seasons - Winter in F Minor ... - Antonio Vivaldi [classical, relaxed] score 4.98
2. Views from Yamashita Park - Nathan Kawanishi [study, relaxed] score 4.94
```

**4. A theme the knowledge base has no document for (romance cue)**
```
> I want to hear something romantical
Parsed by fallback: {'genres': ['romance', 'r&b', 'soul'], 'moods': ['relaxed', 'chill', 'happy'], 'energy': 0.4, 'valence': 0.6, 'acousticness': 0.4}
Confidence: 0.63

1. Листопад - Valery Obodzinsky [romance, chill] score 4.90
2. No Suburban, Pt. 2 - Sheff G [r&b, happy] score 4.90
3. 14 минут до старта - Я верю, друзья - Vladimir Troshin [romance, relaxed] score 4.86
```

**5. Saying "no" and explaining what was off**
```
Were these recommendations good? [y/n/Enter to skip] n
What was off? ... too slow, I need more energy

Request: I want to hear something romantical (+ too slow, I need more energy)
Parsed by fallback: {'energy': 0.88, 'valence': 0.6, 'acousticness': 0.4}
1. Monalisa - Jorge Vercillo [mpb, euphoric] score 1.93
2. Kajra Re - Shankar [classical, euphoric] score 1.92
3. Crazy Train - Ozzy Osbourne [hard rock, intense] score 1.92
(note: energy changed a lot, so I dropped the earlier genre and mood)
```
None of the first round's songs are repeated. The trade-off is visible: the new picks are energetic but no longer romantic, because the old genre would have outvoted the new energy target.

**6. Guardrail: input that cannot be understood**
```
> asdf qwerty
[!] Could not extract any usable music preferences from that request.
```

## Design decisions

- **Kaggle/Hugging Face CSV instead of a live music API.** It needs no key, it can't break between runs, and its columns already matched my scorer. Trade-offs: the catalog is static, it can't play audio, and the `mood` column is *derived* from valence and energy (the dataset has none). Genre labels are also noisy (for example, The Smiths appears as "punk rock").
- **TF-IDF retrieval instead of embeddings.** Deterministic, free, no extra key. Trade-off: it matches words, not meaning, so a request with no vocabulary overlap retrieves nothing and relies on keyword cues.
- **The LLM parses and explains, but never ranks.** The deterministic scorer ranks, so results are testable and every score is explainable. Trade-off: less "magic".
- **Filler words are removed before retrieval.** A vague request ("I want to hear something romantical") used to retrieve an unrelated document only because both contained "want" and "music". Removing those words fixed it at the root. Themes with no document ("romantic", "breakup", "party") are covered by keyword cues instead.
- **"No" re-runs with context and excludes shown songs**, instead of just logging. Follow-up notes only change what they mention. Trade-off: when a note moves energy a lot and names no genre, I drop the old genre and mood, so the answer can drift from the original theme (see sample 5). "more acoustic" is also read as the *genre* "acoustic".
- **Every AI step has a non-AI fallback**, so the app and all tests run without an API key.
- **Hand-written knowledge base.** Apex has no official public API, so I wrote 15 Legend and 8 situation descriptions at the personality level (not detailed lore, to avoid stating facts I can't verify). They are my interpretation, not official data.
- **Simplifications:** no voice input, no audio playback, and one language.

## Testing summary

- **Unit and integration tests:** `pytest` gives **60 of 60 passing**, covering the scorer, normalization and clamping, bad CSV rows, guardrails, retrieval, LLM-output validation, fallback on API errors, explanation checking, follow-up refinement, the CLI yes/no loop driven by scripted input, and the web app driven headlessly with Streamlit's `AppTest` (search, error state, quick-start buttons, thumbs-down retry, key validation, log redaction). The LLM is replaced by fake callables in these tests.
- **Golden-case evaluation** ([eval/report.md](eval/report.md)): **26 of 27 passed** in offline mode. Average confidence on answered requests was **0.81**, and average artist diversity in the top 5 was **0.89**. The 5 guardrail cases (empty, gibberish, over-long, prompt-injection-style text, vague) were all rejected safely, and the 3 follow-up cases never repeated a song.
- **What failed:** the "conflicting" profile (pop + melancholic at energy 0.9) returns only 2 of 5 high-energy songs, because genre and mood points together outweigh energy. I left this case failing on purpose because it reflects a real weakness of the point weights.
- **Bugs found by testing and by using the app, then fixed:**
  - My own first-run test showed a romantic request retrieving the unrelated "Ranked grind" document (confidence looked fine, results were wrong). Cause: filler words. Fix: remove them, add romance cues, lower confidence for weak matches.
  - A follow-up "too slow" retrieved the "Sad and reflective" document and replaced the user's genres. Fix: follow-ups ignore weak document matches.
  - Removing filler words made "I just lost a ranked match and I'm so tilted" pick the wrong situation. Fix: add the words people actually use to that document.
  - A "too slow" follow-up still returned slow songs because the old genre outvoted the new energy target. Fix: drop the old genre and mood when energy shifts a lot (with the side effect noted above).
- **What worked:** validation (dropping unknown genres, clamping numbers) and the rule-based fallback meant bad or missing LLM output never crashed a request.
- **Human evaluation:** the CLI logs every y/n rating and follow-up note to `logs/events.jsonl`, and the eval report summarizes them. So far there are only 5 ratings (2 positive), all from my own testing, which is too few to draw conclusions. Several of the early "no" ratings were for the romantic request before the fixes above.
- **Not yet verified:** I have not run the live LLM path against the real API from the test suite (it is only covered by fake LLM replies), so I'm not reporting accuracy numbers for it.

---

## Reflection

*(Replace this with your own words before submitting; the points below are what I observed building it.)*

- Putting an LLM in front of a deterministic scorer made the system far easier to trust and test than letting the LLM pick songs itself.
- Most of the reliability work was not about the AI being smart. It was about handling what happens when it is wrong, missing, or fed odd input.
- Evaluation cases found real weaknesses (the weights, noisy genres, the derived mood) that I would not have noticed from the happy path.
- The knowledge base and the mood derivation are my own judgments, so the system's "taste" reflects my assumptions about what a Legend sounds like.
