# Analyze speaker talk time, turn metrics, and speech balance

Use this recipe to analyze conversation transcripts, computing per-speaker turn counts, word volumes, talk time percentages, and words-per-minute (WPM).

Export conversations:

```sh
omi --json conversation list --include-transcript --limit 20 > conversations.json
```

Generate speaker statistics:

```sh
python speaker_stats_analyzer.py conversations.json speaker_stats.json
```
