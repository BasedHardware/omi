# Convert an action-items export to an Excel workbook (.xlsx)

Use this recipe when you want your action items and tasks in an Excel workbook with real cell types: `created_at` and `due_at` become formatted datetime cells you can sort and filter, completion status (`YES` / `NO`) is highlighted, the header row is frozen, and an AutoFilter is automatically enabled. It reads a saved JSON export, makes no network requests, and handles both completed and open tasks. It complements [`action_items_sqlite.md`](action_items_sqlite.md) and [`action_items_markdown.md`](action_items_markdown.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the command succeeded before converting the file. This is one page, not a complete-account backup. To retrieve another page, increase `--offset` by 200 and use a different filename.

Save the following as `action_items_to_xlsx.py`:

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Palette
DARK_HEADER = "1F2937"  # Slate dark
WHITE_TEXT = "FFFFFF"
ROW_ALT = "F9FAFB"      # Soft grey
COMPLETED_GREEN = "D1FAE5" # Soft mint green
OVERDUE_RED = "FEE2E2"     # Soft light red

def convert_action_items_to_xlsx(input_path: Path, output_path: Path) -> int:
    """Reads action items JSON export and converts to formatted Excel workbook."""
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON: {e}", file=sys.stderr)
        return 1

    # Accommodate both list-of-items or {"action_items": [...]} payload
    if isinstance(data, dict):
        items = data.get("action_items", data.get("items", []))
    elif isinstance(data, list):
        items = data
    else:
        print("Error: Input JSON must be an array or an object containing an action_items array.", file=sys.stderr)
        return 1

    wb = Workbook()
    ws = wb.active
    ws.title = "Action Items"

    headers = [
        "ID",
        "Description",
        "Completed",
        "Due Date",
        "Created At",
        "Category / Source"
    ]

    ws.append(headers)

    # Style Header Row
    header_font = Font(name="Calibri", size=11, bold=True, color=WHITE_TEXT)
    header_fill = PatternFill(start_color=DARK_HEADER, end_color=DARK_HEADER, fill_type="solid")
    header_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB")
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    ws.row_dimensions[1].height = 24

    now_utc = datetime.now(timezone.utc)

    for row_idx, item in enumerate(items, start=2):
        item_id = str(item.get("id", ""))
        desc = item.get("description", item.get("text", item.get("content", "")))
        completed = item.get("completed", False)
        due_at_str = item.get("due_at", item.get("due_date", ""))
        created_at_str = item.get("created_at", "")
        category = item.get("category", item.get("source", "conversation"))

        # Parse Due Date
        due_val = due_at_str
        is_overdue = False
        if due_at_str:
            try:
                clean_due = due_at_str.replace("Z", "+00:00")
                parsed_due = datetime.fromisoformat(clean_due)
                due_val = parsed_due.strftime("%Y-%m-%d %H:%M")
                if not completed and parsed_due.tzinfo and parsed_due < now_utc:
                    is_overdue = True
            except Exception:
                due_val = due_at_str

        # Parse Created At
        created_val = created_at_str
        if created_at_str:
            try:
                clean_created = created_at_str.replace("Z", "+00:00")
                parsed_created = datetime.fromisoformat(clean_created)
                created_val = parsed_created.strftime("%Y-%m-%d %H:%M")
            except Exception:
                created_val = created_at_str

        row_data = [
            item_id,
            desc,
            "YES" if completed else "NO",
            due_val,
            created_val,
            category
        ]

        ws.append(row_data)

        # Style data row
        row_fill = None
        if completed:
            row_fill = PatternFill(start_color=COMPLETED_GREEN, end_color=COMPLETED_GREEN, fill_type="solid")
        elif is_overdue:
            row_fill = PatternFill(start_color=OVERDUE_RED, end_color=OVERDUE_RED, fill_type="solid")
        elif row_idx % 2 == 1:
            row_fill = PatternFill(start_color=ROW_ALT, end_color=ROW_ALT, fill_type="solid")

        for col_idx in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill
            if col_idx == 3:  # Completed column
                cell.alignment = Alignment(horizontal="center")

        ws.row_dimensions[row_idx].height = 20

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Freeze Header Row
    ws.freeze_panes = "A2"

    # Enable AutoFilter across all populated columns
    ws.auto_filter.ref = ws.dimensions

    # Atomic write
    temp_output = output_path.with_suffix(".tmp")
    try:
        wb.save(temp_output)
        if output_path.exists():
            output_path.unlink()
        temp_output.rename(output_path)
    except Exception as e:
        if temp_output.exists():
            temp_output.unlink()
        print(f"Error saving workbook: {e}", file=sys.stderr)
        return 1

    print(f"Success: Converted {len(items)} action items to '{output_path}'.")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python action_items_to_xlsx.py <action_items.json> [output.xlsx]")
        sys.exit(1)

    in_file = Path(sys.argv[1])
    out_file = Path(sys.argv[2]) if len(sys.argv) > 2 else in_file.with_suffix(".xlsx")

    code = convert_action_items_to_xlsx(in_file, out_file)
    sys.exit(code)


if __name__ == "__main__":
    main()
```

Run the conversion:

```sh
python action_items_to_xlsx.py action_items.json action_items.xlsx
```

Open `action_items.xlsx` in Excel, LibreOffice Calc, or Google Sheets. The sheet opens with frozen headers, colored status badges (green for completed, soft red for overdue), and auto-filters ready for querying tasks.
