# Export conversation transcripts to WebVTT (.vtt) subtitles

Use this recipe to convert Omi conversation transcripts into standard WebVTT (`.vtt`) subtitles. WebVTT is the W3C standard format for timed text tracks, supported natively in HTML5 `<video>` and `<audio>`, media players (VLC, QuickTime, mpv), video editing suites, and podcast players.

It preserves individual cue timings, maps speaker identification into standard voice tags (`<v SpeakerName>text</v>`), and can output a single combined track or individual subtitle files per conversation.

## Exporting Conversations

Fetch conversations with `omi-cli`:

```bash
omi --json conversation list --limit 50 > conversations.json
```

Or fetch a specific conversation with detailed segments:

```bash
omi --json conversation get <conversation-id> > conversation.json
```

## Running the Exporter

Convert a conversation export to a WebVTT file:

```bash
python conversations_to_vtt.py conversation.json -o transcript.vtt
```

Export individual `.vtt` subtitle files for each conversation into a folder:

```bash
python conversations_to_vtt.py conversations.json --output-dir ./subtitles/
```

Or pipe directly via standard input:

```bash
omi --json conversation get <conversation-id> | python conversations_to_vtt.py - -o audio.vtt
```

## Using in HTML5 Audio / Video

```html
<video controls>
    <source src="recording.mp4" type="video/mp4">
    <track default kind="subtitles" srclang="en" src="transcript.vtt" label="English">
</video>
```
