# Compile Omi conversations into a searchable, printable HTML book

Use this recipe to compile your Omi conversations into an offline, interactive HTML transcript book. It features a sticky sidebar with instant real-time title search, speaker-attributed dialogue badges, overview cards, and print styles with automatic page breaks for converting to PDF.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export and compile directly to an HTML book:

```sh
omi --json conversation list --limit 50 | python conversations_to_html_book.py - --title "Personal Meeting Journal" -o meeting_book.html
```

Or process a local export:

```sh
python conversations_to_html_book.py conversations.json --title "Q3 Transcripts" -o meeting_book.html
```

Output:
```
Generated HTML transcript book with 30 conversation(s) at meeting_book.html
```

## Features

- **Interactive Searchable Sidebar**: Real-time JavaScript filter that narrows conversations by title as you type.
- **Dialogue Feed**: Visual utterance blocks with colored speaker badges.
- **Print to PDF Ready**: Built-in `@media print` stylesheet that removes UI chrome and enforces `page-break-after: always` on chapters for clean paper or PDF printing.
- **Pure Standard Library**: Zero external dependencies required.
