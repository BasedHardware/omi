# Convert a memories list export to an Excel workbook (.xlsx)

Use this recipe when you want the memories and knowledge-base list in Excel with real cell types: `created_at` becomes a datetime cell you can sort and filter, categories and tags are clearly separated into searchable columns, the header row is frozen, and an AutoFilter is enabled. It reads a saved JSON export, makes no network requests, and complements [`conversations_csv.md`](conversations_csv.md).


You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export your memories:

```sh
omi --json memory list > memories.json
```

Run the converter:

```sh
python sdks/python-cli/examples/memories_to_xlsx.py memories.json memories.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are real datetime cells in UTC (the header says so), every text column is typed as string so IDs keep leading zeros and notes that look like formulas are never evaluated. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
