# Compile Omi conversations into an EPUB e-book

Use this recipe to turn your Omi conversation transcripts and summaries into a complete, beautifully formatted EPUB e-book. You can load it onto Apple Books, Amazon Kindle, Kobo, or any mobile e-reader app for distraction-free offline reading.

## Prerequisites

- Python 3.10+ (standard library only; uses `zipfile`, `json`, `html`)
- An authenticated `omi-cli` installation

## Usage

Export and compile directly to an e-book:

```sh
omi --json conversation list --limit 50 | python conversations_to_epub.py - --title "Omi Journal 2026" -o omi_journal.epub
```

Or compile a saved JSON export file:

```sh
python conversations_to_epub.py conversations.json --title "Weekly Meeting Transcripts" -o meetings.epub
```

Output:
```
Compiled 25 conversation(s) into EPUB e-book at meetings.epub
```

## How to Read

- **macOS / iOS**: Double-click `omi_journal.epub` to open immediately in Apple Books.
- **Kindle**: Send the file to your Kindle email address or upload via [Amazon Send to Kindle](https://www.amazon.com/sendtokindle).
- **Android**: Open with Google Play Books, Moon+ Reader, or ReadEra.

## Features

- **Standard EPUB 2/3 Archive**: Fully compliant ZIP-based EPUB structure including `mimetype`, `META-INF/container.xml`, `content.opf`, and `toc.ncx`.
- **Chapter-per-Conversation**: Each conversation forms an XHTML chapter featuring structured overviews, timestamps, and speaker-attributed dialogue.
- **Pure Standard Library**: Zero external Python packages required.
