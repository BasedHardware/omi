# Convert a goal-list export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi tracked goals in Excel with real cell
types: `created_at` / `updated_at` become UTC datetime cells you can sort and
filter, `current_value` and `target_value` are stored as numbers, `progress_pct`
is computed automatically, the header row is frozen (`A2`), and AutoFilter is
enabled.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export tracked goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Run the converter:

```sh
python goals_to_xlsx.py goals.json goals.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are
real datetime cells in UTC, numeric values sort properly, and titles or notes
starting with `=`, `+`, `-`, `@` are safely stored as text without formula
evaluation.
