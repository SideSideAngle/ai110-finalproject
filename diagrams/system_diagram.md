# System Diagram

Rectangles with slanted sides (`[/ /]`) are **human checkpoints**. The `Testing` box shows where automated tests and the evaluation harness check the AI. Dotted arrows are logging.

```mermaid
flowchart TD
    UI[/"Web app (Streamlit) or CLI: text box, Legend buttons, optional pasted API key"/] --> U
    U([User: free text or a Legend name]) --> G[Guardrails: sanitize, length and empty checks]
    G -->|invalid| ERR[Friendly error + log]
    G --> R[Retriever: TF-IDF over Legend and situation docs]
    KB[(Knowledge base: legends.json, situations.json)] --> R
    R --> P[Intent Parser: LLM reads request + retrieved docs, returns profile JSON]
    P -->|no API key, API error, or bad JSON| FB[Rule-based fallback parser, also uses retrieved docs]
    P --> V{Schema valid? Unknown genres dropped, numbers clamped}
    FB --> V
    V -->|nothing usable| ERR
    V --> CF{Confidence >= 0.35?}
    CF -->|no| H1[/Human: clarify the request/]
    H1 --> G
    CF -->|yes| S[Scorer: genre, mood, energy, valence, acousticness]
    C[(Catalog: data/songs.csv, 2,700 songs)] --> S
    S --> T[Top-k + artist diversity cap]
    T --> X[Explainer: LLM, grounded in retrieved text and score reasons]
    X --> CK{Check: right count, short, only retrieved Legends named?}
    CK -->|fail| TX[Template explanation from the score reasons]
    CK -->|pass| O([Recommendations + confidence])
    O -.->|song title and artist only| PV[Preview lookup: iTunes Search API, cached, parallel]
    PV -.->|match: 30s player + album art. No match or error: YouTube link only| O
    TX --> O
    O --> H2[/Human: thumbs up or down in the CLI, peer review/]
    H2 -->|"no: what was off? (max 3 rounds, shown songs excluded)"| P
    H2 --> LOG[(logs/events.jsonl + logs/app.log)]
    G -.-> LOG
    P -.-> LOG
    S -.-> LOG
    X -.-> LOG
    subgraph Testing
      UT[pytest: scorer, guardrails, retrieval, parser, explainer, pipeline] -.-> G
      UT -.-> P
      UT -.-> S
      UT -.-> X
      EV[eval/run_eval.py: 22 golden cases] -.-> O
      EV --> RP[eval/report.md]
    end
    BC[python -m src.catalog: Spotify Tracks dataset -> trimmed CSV] --> C
```

## Where the AI is checked

| Checkpoint | Type | What it catches |
|---|---|---|
| Input guardrails | automatic | empty, oversized, or control-character input |
| Schema validation | automatic | LLM output with unknown genres or moods, out-of-range numbers, missing fields |
| Rule-based fallback | automatic | API failure, missing key, non-JSON reply |
| Confidence threshold | automatic, then human | vague or unrecognized requests; the user is asked to clarify |
| Explanation check | automatic | wrong count, oversized text, or a Legend that was never retrieved |
| Golden-case evaluation | automated test | regressions in end-to-end behavior |
| Thumbs up/down, peer review | human | relevance problems no automatic check can see |
| Pasted API key check | automatic | one tiny test call; a bad key is reported at once and the app stays in offline mode |
| Preview matching | automatic | wrong artist or song, non-Apple URLs, timeouts and bad JSON all fall back to the YouTube link |
| Hosted-log privacy | automatic | the web app redacts what visitors type (`LOG_REQUEST_TEXT=0`) |
| "What was off?" follow-up | human, then automatic | a "no" re-runs the request with the user's note and never repeats shown songs |
