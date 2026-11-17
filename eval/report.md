# Evaluation report

- Mode: offline rule-based parser
- **26 of 27 golden cases passed**
- Average confidence on answered text requests: 0.81
- Average artist diversity in the top 5 (distinct artists / songs): 0.89
- Human feedback from logs/events.jsonl: 2 of 5 user ratings were positive

| Case | Kind | Result | Confidence | Notes |
|---|---|---|---|---|
| legend-wraith | text | PASS | 0.96 |  |
| legend-octane | text | PASS | 0.96 |  |
| legend-horizon | text | PASS | 0.88 |  |
| legend-casing-punctuation | text | PASS | 0.96 |  |
| situation-hype | text | PASS | 0.77 |  |
| situation-study | text | PASS | 0.84 |  |
| situation-tilted | text | PASS | 0.68 |  |
| vibe-sad-rainy | text | PASS | 0.82 |  |
| vibe-upbeat | text | PASS | 0.96 |  |
| guard-empty | text | PASS | 0.00 |  |
| guard-gibberish | text | PASS | 0.00 |  |
| guard-too-long | text | PASS | 0.00 |  |
| guard-prompt-injection | text | PASS | 0.00 |  |
| guard-vague | text | PASS | 0.00 |  |
| vibe-romantic | text | PASS | 0.63 |  |
| vibe-heartbreak | text | PASS | 0.64 |  |
| refine-too-slow | text | PASS | 0.64 |  |
| refine-try-rock | text | PASS | 0.63 |  |
| refine-empty-note | text | PASS | 0.96 |  |
| profile-high-energy-pop | profile | PASS |  |  |
| profile-calm-chill | profile | PASS |  |  |
| profile-intense-rock | profile | PASS |  |  |
| profile-conflicting-sad-high-energy | profile | FAIL |  | only 2/5 songs have energy in [0.7, 1.0] (need 3) |
| profile-unknown-genre | profile | PASS |  |  |
| profile-impossible-energy | profile | PASS |  |  |
| profile-messy-casing | profile | PASS |  |  |
| profile-empty | profile | PASS |  |  |
