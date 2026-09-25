# Export Memories to CSV

This recipe demonstrates how to export your OMI captured memories, knowledge base facts, and structured categories into a clean CSV file using the OMI Python SDK.

## Prerequisites

- Python 3.10+
- `omi-client` installed (`pip install omi-client`)
- `OMI_API_KEY` set in your environment

## Usage

Run the export script:

```bash
python cli/recipes/memories_to_csv.py --output memories_export.csv
```

## Security & Encoding
- Escapes spreadsheet formula injection prefixes (`=`, `+`, `-`, `@`).
- Uses `utf-8-sig` encoding for seamless compatibility with Microsoft Excel, Apple Numbers, and Google Sheets.
