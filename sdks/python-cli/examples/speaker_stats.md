```markdown
# Speaker Stats Analyzer

This tool analyzes transcripts to calculate speaker turns, talk time percentages, and speech balance metrics.

## Features

- Calculates total duration of the transcript
- Counts number of speaker turns per speaker
- Computes talk time percentages for each speaker
- Provides speech balance metrics (ratio of most/least talkative speaker)
- Atomic file replacement for safe output writing
- JSON output format for easy integration with other tools

## Usage

### Basic Usage

```bash
python speaker_stats_analyzer.py input.txt
```

This will analyze `input.txt` and save the results to `speaker_stats.json`.

### Custom Output File

```bash
python speaker_stats_analyzer.py input.txt --output_file custom_output.json
```

## Input Format

The script expects transcripts in the following format:

```
[00:01:23] Speaker1: Hello everyone
[00:01:25] Speaker2: Hi there
[00:01:30] Speaker1: How are you doing?
```

Timestamps can be in HH:MM:SS, MM:SS, or seconds format.

## Output Format

The output is a JSON file with the following structure:

```json
{
  "total_duration": 7.0,
  "speaker_turns": [
    {
      "speaker": "Speaker1",
      "start": 83.0,
      "end": 85.0,
      "duration": 2.0,
      "text": "Hello everyone"
    },
    ...
  ],
  "speaker_durations": {
    "Speaker1": 4.0,
    "Speaker2": 3.0
  },
  "speaker_percentages": {
    "Speaker1": 57.14,
    "Speaker2": 42.86
  },
  "num_speakers": 2,
  "avg_duration_per_speaker": 3.5,
  "max_duration_by_speaker": 4.0,
  "min_duration_by_speaker": 3.0,
  "balance_ratio": 1.33,
  "analysis_timestamp": "2023-11-15T14:30:00.123456"
}
```

## Examples

### Example 1: Simple Two-Speaker Conversation

Input (`conversation.txt`):
```
[00:00:00] Alice: Good morning
[00:00:02] Bob: Morning Alice
[00:00:05] Alice: How was your weekend?
[00:00:08] Bob: It was great, thanks!
```

Run:
```bash
python speaker_stats_analyzer.py conversation.txt
```

Output (`speaker_stats.json`):
```json
{
  "total_duration": 8.0,
  "speaker_turns": [...],
  "speaker_durations": {
    "Alice": 5.0,
    "Bob": 3.0
  },
  "speaker_percentages": {
    "Alice": 62.5,
    "Bob": 37.5
  },
  "num_speakers": 2,
  "avg_duration_per_speaker": 4.0,
  "max_duration_by_speaker": 5.0,
  "min_duration_by_speaker": 3.0,
  "balance_ratio": 1.67,
  "analysis_timestamp": "2023-11-15T14:30:00.123456"
}
```

## Error Handling

The script includes robust error handling for:
- Missing input files
- Invalid timestamp formats
- File I/O errors
- Atomic file replacement failures

## Integration

This tool can be easily integrated into larger analysis pipelines by:
1. Parsing the JSON output
2. Using the balance ratio to quantify conversation equality
3. Tracking speaker percentages over time
4. Identifying dominant speakers in meetings
```