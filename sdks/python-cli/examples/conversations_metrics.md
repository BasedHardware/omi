# Analyze speaker talk time, speech rate, and meeting metrics

Use this recipe to calculate speaker analytics from Omi conversation transcripts. It measures talk time distribution, speaker turn frequency, word counts, and speech rate (Words Per Minute / WPM).

## Metrics Computed

- **Talk Time & Share**: Total seconds each speaker was active and percentage share of overall conversation time.
- **Speech Rate (WPM)**: Estimated speaking cadence (words per minute).
- **Speaker Turns**: How frequently the floor alternated between participants.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Generate a Markdown table summary:

```sh
omi --json conversation list --limit 10 | python conversations_metrics.py - --format markdown -o report.md
```

Or output structured JSON for analytics dashboards:

```sh
python conversations_metrics.py conversations.json -o metrics.json
```

## Sample Markdown Output

```markdown
# Omi Conversation Speaker & Speech Metrics

## Sprint Planning (`conv-019`)
**Total Talk Time**: 900.5s | **Total Words**: 2140 | **Turns**: 48

| Speaker | Talk Time (s) | Share (%) | Words | Speech Rate (WPM) | Turns |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Alice | 540.3s | 60.0% | 1350 | 150.0 | 25 |
| Bob | 360.2s | 40.0% | 790 | 131.6 | 23 |
```

## Features

- **Standard Library Only**: Uses built-in `json`, `argparse`, and `pathlib`.
- **Segment-Level Precision**: Aggregates timestamps across utterance segments.
- **Multiple Output Formats**: Supports clean Markdown tables or raw JSON.
