# Convert an action-items list export to an Excel workbook (.xlsx)

Use this recipe when you want the action items list in Excel with real cell types: `created_at` / `updated_at` become datetime cells you can sort and filter, the `completed` status is clearly presented, the header row is frozen, and an AutoFilter is enabled. It reads a saved JSON export, makes no network requests, and complements [`action_items_csv.md`](action_items_csv.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export your action items:

```sh
omi --json action-item list > action_items.json
```

Run the converter:

```sh
python sdks/python-cli/examples/action_items_to_xlsx.py action_items.json action_items.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are real datetime cells in UTC (the header says so), every text column is typed as string so IDs keep leading zeros and tasks that look like formulas are never evaluated. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
