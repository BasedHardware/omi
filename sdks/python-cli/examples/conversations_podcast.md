# Export conversations to Podcast RSS 2.0 Feed

Use this recipe to export Omi conversations and audio transcripts into a
standard-compliant Podcast RSS 2.0 XML feed. This allows you to subscribe to
your own meetings, discussions, and life logs in Apple Podcasts, Spotify, Pocket
Casts, Overcast, or any standard RSS reader.

Each item in the feed contains the conversation title, publication date,
duration, overview, full transcript, and direct audio enclosure attachment.
It reads saved JSON exports, requires zero external dependencies (pure Python
standard library), supports multi-page exports with automatic ID deduplication,
and refuses to overwrite existing files unless `--force` is specified.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

---

## 1. Export conversations from Omi

Export your conversation history into JSON files:

```bash
# Export recent conversations
omi conversation list --limit 50 --json > conversations.json

# Or export across multiple pages
omi conversation list --limit 100 --offset 0 --json > page1.json
omi conversation list --limit 100 --offset 100 --json > page2.json
```

---

## 2. Generate the Podcast RSS feed

Run `conversations_to_podcast.py` against your exported files:

```bash
# Basic usage
python conversations_to_podcast.py conversations.json -o podcast.xml

# Custom show metadata and hosted audio base URL
python conversations_to_podcast.py conversations.json \
  -o podcast.xml \
  --title "My Life Journal" \
  --author "Alice" \
  --description "Daily conversations, thoughts, and meeting recaps" \
  --audio-base-url "https://my-bucket.s3.amazonaws.com/recordings/"

# Combine multiple files with automatic deduplication
python conversations_to_podcast.py page1.json page2.json -o podcast.xml

# Filter by category (e.g. only 'work' meetings)
python conversations_to_podcast.py conversations.json \
  -o work_podcast.xml \
  --filter-category work
```

---

## 3. Command options

| Option | Default | Description |
| :--- | :--- | :--- |
| `-o, --output` | `podcast.xml` | Path to save the resulting RSS 2.0 XML file |
| `--title` | `"Omi Conversations"` | Podcast show title |
| `--description` | `"Audio life-log..."` | Podcast show description |
| `--author` | `"Omi User"` | Author / Host name |
| `--audio-base-url` | `None` | Custom base URL prefix for audio recordings |
| `--filter-category`| `None` | Filter items by category (e.g. `work`, `personal`) |
| `--force` | `False` | Overwrite the output file if it already exists |

---

## 4. Subscribing in your Podcast App

1. Upload `podcast.xml` to any web hosting (GitHub Pages, Amazon S3, Google Cloud Storage, or a local network web server).
2. Copy the public feed URL (e.g. `https://username.github.io/my-podcast/podcast.xml`).
3. Open your podcast player:
   * **Apple Podcasts**: Library -> `...` menu -> *Follow a Show by URL...*
   * **Pocket Casts**: Search bar -> Paste feed URL -> *Subscribe*.
   * **Overcast**: `+` -> *Add URL*.

---

## 5. Automated Tests

Run the test suite:

```bash
python test_conversations_to_podcast.py
```
