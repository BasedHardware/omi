# Exporting Memories to CSV

Export OMI memories to a spreadsheet-compatible CSV file for offline analysis.

## Prerequisites
- Python 3.7+
- OMI Python SDK (`pip install omi-sdk`)

## Steps

1. **Install the script** (if not already in your `PATH`):
   ```bash
   curl -o memories_to_csv.py https://raw.githubusercontent.com/BasedHardware/omi/main/scripts/memories_to_csv.py
   chmod +x memories_to_csv.py
   ```

2. **Run the export** (replace placeholders):
   ```bash
   ./memories_to_csv.py \
     --api-key YOUR_OMI_API_KEY \
     --endpoint https://api.omi.basedhardware.com \
     --output memories_export.csv
   ```

## Output Structure
The generated CSV includes:
- `ID`: Memory identifier
- `Timestamp`: Capture time
- `Content`: Raw memory text
- `Source`: Origin (e.g., `web`, `audio`)
- `Tags`: Comma-separated labels
- `Metadata`: JSON-serialized additional data

## Safety Notes
- **Formula Injection**: Fields are sanitized to prevent Excel formula execution.
- **Encoding**: Uses `utf-8-sig` for Excel compatibility.
- **Empty Fields**: Handled gracefully.

## Example Workflow
```bash
# Export and open in Excel
./memories_to_csv.py --api-key $OMI_KEY --endpoint $OMI_ENDPOINT --output memories.csv
libreoffice memories.csv
```

## Troubleshooting
- **Permission Denied**: Ensure the output directory is writable.
- **API Errors**: Verify your `--api-key` and `--endpoint` are correct.

## Parity with Conversations Export
This recipe follows the same structure as [`conversations_csv.md`](conversations_csv.md), ensuring consistency in the CLI tooling.