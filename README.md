# SymphonySearch: RAG-powered music picks by Legend and vibe

## Original project

This project extends my **Music Recommender Simulation**. The original was a content-based recommender: it loaded a hand-written 19-song CSV, compared each song to a hand-coded taste profile (favorite genre, favorite mood, target energy), and ranked songs by a points score (genre +2, mood +1, energy closeness up to +1). It printed a "Because: ..." line for every pick, but the user profile had to be written in code and genre and mood had to match exactly.

## Title and summary

**SymphonySearch** lets you type *"Wraith"*, *"I just lost a ranked match and I'm so tilted"*, or *"quiet music to study"* and get songs that fit, with the reasons.

Why it matters: the original could only answer to a profile a programmer typed in, from 19 songs. Now:

- **RAG:** a small knowledge base of Apex Legends personalities and listening situations is retrieved for every request. The retrieved text decides the target energy, mood and genres, so retrieval directly changes which songs are ranked. It is not printed next to a standard answer.
- **Real catalog:** 2,700 real songs (25 most popular per genre) from the public Spotify Tracks dataset.
- **Reliability layer:** guardrails, confidence scoring, an LLM-to-rules fallback, logging, unit tests and a golden-case evaluation harness.

## Architecture overview

Full diagram with the human and testing checkpoints: [diagrams/system_diagram.md](diagrams/system_diagram.md).

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
- Each song is a compact card: album art with a play/pause button on the cover, then the title, artist, genre and mood chips, and a % match bar. A **Details** section holds the explanation, the score breakdown, and a YouTube link. Only one preview plays at a time.
- **Audio previews:** most cards have a 30-second preview played from the album cover, looked up automatically from the free iTunes Search API (no key). In a live check, 20 of 25 recommended songs had a match; the rest (long classical titles, non-English titles, very new tracks) fall back to the YouTube link. Only the song title and artist are sent, never what you typed, and results are cached for a day. Set `SYMPHONY_PREVIEWS=0` to turn previews off.
- **Why these songs?** shows what was retrieved from the knowledge base, the parsed profile, and the confidence.
- 👎 **Not quite** asks what was off and tries again (up to 3 times, never repeating songs). 👍 logs a positive rating.
- **Your own API key (optional):** paste an Anthropic key in the sidebar to switch from the offline rule-based parser to the LLM. The key is checked with one tiny call, kept only in your browser session's memory, and never written to disk or logs. Without a key everything still works offline.
- **Privacy:** the web app does not store what you type (`LOG_REQUEST_TEXT=0` by default); it logs only ratings, confidence and parser info. Set `LOG_REQUEST_TEXT=1` to log text locally.

### Seeing how it works (`explore.py`)

`streamlit run explore.py` opens an interactive walkthrough that runs the real retriever, intent parser and scorer on any request you type, one tab per stage. The scoring tab has sliders for the weights, so you can watch the ranking change as you adjust them. It does not call an LLM; the last tab shows exactly what would be sent to one.

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
- **Previews come from the iTunes Search API, not a bundled audio file.** The dataset has no audio. It is free and keyless, but it only offers 30-second clips, matching is by name (so I require the artist and title to match closely and only accept Apple-hosted URLs), and it makes this the app's first outside network dependency. Every failure quietly falls back to the YouTube link, and lookups run in parallel and are cached.
- **Every AI step has a non-AI fallback**, so the app and all tests run without an API key.
- **Hand-written knowledge base.** Apex has no official public API, so I wrote 15 Legend and 8 situation descriptions at the personality level (not detailed lore, to avoid stating facts I can't verify). They are my interpretation, not official data.
- **When retrieval finds nothing, offline mode is limited.** Retrieval is optional, not required: hand-written keyword cues ("romantic", "breakup", "party", "calm") can still build a profile on their own. But a request with no matching note *and* no cue word ("music for a rainy drive home") is not understood, and the app asks the user to rephrase. An LLM handles those requests much better, so adding an API key is the intended way to cover them. The offline path is a safety net, not a full substitute.
- **Confidence and weights are judgment calls, not tuned values.** Confidence estimates how likely the parsed profile matches what the user meant (rules: retrieval score plus cue hits; LLM: `0.6 x the LLM's own rating + 0.4 x retrieval score`). It is a heuristic that has not been calibrated against real ratings; the thumbs up/down data is logged but too small to use for that yet. The scoring weights (genre 2.0, mood 1.0, energy 1.0, valence 0.5, acousticness 0.5) are likewise my choices, and the failing conflicting-profile case above shows their cost.
- **Simplifications:** no voice input, only 30-second previews instead of full playback, and one language.

## Testing summary

- **Unit and integration tests:** `pytest` gives **92 of 92 passing**, covering the scorer, normalization and clamping, bad CSV rows, guardrails, retrieval, LLM-output validation, fallback on API errors, explanation checking, follow-up refinement, the CLI yes/no loop driven by scripted input, and the web app driven headlessly with Streamlit's `AppTest` (search, error state, quick-start buttons, thumbs-down retry, key validation, log redaction), the custom audio player's HTML (including refusing unsafe URLs), and the audio-preview lookup using a fake network (match, wrong artist, untrusted host, timeout, malformed JSON, caching). The LLM is replaced by fake callables in these tests.
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

- Putting an LLM in front of a deterministic scorer made the system far easier to trust and test than letting the LLM pick songs itself.
- Most of the reliability work was not about the AI being smart. It was about handling what happens when it is wrong, missing, or fed odd input.
- Evaluation cases found real weaknesses (the weights, noisy genres, the derived mood) that I would not have noticed from the happy path.
- The knowledge base and the mood derivation are my own judgments, so the system's "taste" reflects my assumptions about what a Legend sounds like. Can be worked to be made better with community and user help. 
- The AI likes to cover many bases even if those bases may be unnessessary. A mode which doesn't use an API key to call an LLM is interesting and useful but not too much in the context of this project and in modern use applications. While I initially found it a little redundant, it became a safety net for when the LLM mode would fail and it was interesting to see how it works. 
