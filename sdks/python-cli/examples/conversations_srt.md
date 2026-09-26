# Export conversation transcripts to SubRip (.srt) subtitles

Use this recipe to convert Omi conversation transcripts into standard SubRip (`.srt`) subtitles. SubRip is the universal subtitle standard supported by Adobe Premiere Pro, DaVinci Resolve, Final Cut Pro, HandBrake, YouTube studio, and every media player.

It formats cues sequentially with millisecond timestamps (`HH:MM:SS,mmm`), attaches speaker tags `[Speaker Name]`, and supports batch output to a folder of subtitle files.

## Exporting Conversations

Fetch conversations with `omi-cli`:

```bash
omi --json conversation list --limit 50 > conversations.json
```

Or fetch a specific conversation:

```bash
omi --json conversation get <conversation-id> > conversation.json
```

## Running the Exporter

Convert a conversation export to an SRT subtitle file:

```bash
python conversations_to_srt.py conversation.json -o transcript.srt
```

Export individual `.srt` subtitle files for each conversation into a directory:

```bash
python conversations_to_srt.py conversations.json --output-dir ./subtitles/
```

Or pipe directly via standard input:

```bash
omi --json conversation get <conversation-id> | python conversations_to_srt.py - -o audio.srt
```
