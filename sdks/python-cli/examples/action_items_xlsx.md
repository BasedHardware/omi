<content>
# Convert Action Items to Excel Workbook (.xlsx)

This recipe converts Omi action-item and task exports into an Excel workbook (`.xlsx`) with native cell types, providing structured spreadsheet functionality.

## Features

- **Real Datetime Cells**: Normalizes `due_at`, `created_at`, and `updated_at` into native UTC datetime cells with `yyyy-mm-dd hh:mm:ss` formatting
- **Native Boolean Status**: `completed` is stored as a native Excel boolean (`TRUE`/`FALSE`), allowing immediate filtering
- **Formula-Safe String Escaping**: Explicitly assigns string cell types to prevent formula injection
- **AutoFilter & Frozen Header**: Automatically enables AutoFilter across all columns and freezes the header row
- **Dynamic Auto-Sizing**: Calculates column widths based on content lengths
- **Multi-File Deduplication**: Safely combines and deduplicates tasks across multiple paginated export files
- **Atomic File Writing**: Prevents leaving truncated workbooks upon failure

## Requirements

- Python 3.7+
- `omi` CLI installed
- `openpyxl` library (`pip install openpyxl`)

## Usage

### 1. Export Action Items

First, export your action items to JSON:

```bash
omi action-items export --output action_items.json
```

For paginated results, combine multiple files:

```bash
omi action-items export --output action_items_part1.json --page 1
omi action-items export --output action_items_part2.json --page 2
```

### 2. Convert to Excel

Run the conversion script:

```bash
python action_items_xlsx.py action_items.json
```

Or for multiple files:

```bash
python action_items_xlsx.py action_items_part1.json action_items_part2.json
```

This will generate `action_items.xlsx` with the following columns:

- `id`
- `title`
- `description`
- `status`
- `priority`
- `completed`
- `due_at`
- `created_at`
- `updated_at`
- `assignee`
- `project`

## Example Output

The resulting Excel workbook will have:

1. **AutoFilter enabled** on all columns
2. **Frozen header row** (row 2)
3. **Formatted datetime cells** for date fields
4. **Boolean values** for completion status
5. **Auto-sized columns** based on content
6. **Deduplicated entries** when processing multiple files

## Script Code

Save the following as `action_items_xlsx.py`:

```python
#!/usr/bin/env python3
"""
Convert Omi action-items export to Excel workbook (.xlsx)

Usage: python action_items_xlsx.py <input_file1.json> [input_file2.json ...]
Output: action_items.xlsx
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font
    from openpyxl.worksheet.worksheet import Worksheet
except ImportError:
    print("Error: openpyxl library not found. Install with: pip install openpyxl")
    sys.exit(1)

# Column definitions with metadata
COLUMNS = [
    ("id", "ID", "string"),
    ("title", "Title", "string"),
    ("description", "Description", "string"),
    ("status", "Status", "string"),
    ("priority", "Priority", "string"),
    ("completed", "Completed", "boolean"),
    ("due_at", "Due Date", "datetime"),
    ("created_at", "Created At", "datetime"),
    ("updated_at", "Updated At", "datetime"),
    ("assignee", "Assignee", "string"),
    ("project", "Project", "string"),
]

def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

def load_and_dedupe_files(file_paths: List[str]) -> List[Dict[str, Any]]:
    """Load JSON files and deduplicate by task ID"""
    seen_ids = set()
    tasks = []
    
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Handle both single task and array of tasks
                if isinstance(data, dict):
                    items = [data] if 'id' in data else data.get('items', [])
                else:
                    items = data if isinstance(data, list) else []
                
                for item in items:
                    if 'id' not in item:
                        continue
                        
                    task_id = str(item['id'])
                    if task_id not in seen_ids:
                        seen_ids.add(task_id)
                        tasks.append(item)
                        
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: Could not load {file_path}: {e}")
            continue
    
    return tasks

def create_excel(tasks: List[Dict[str, Any]], output_path: str) -> None:
    """Create Excel workbook from tasks"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Action Items"
    
    # Create header row
    header_font = Font(bold=True)
    for col_idx, (_, header, _) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
    
    # Process tasks
    for row_idx, task in enumerate(tasks, 2):
        for col_idx, (key, _, data_type) in enumerate(COLUMNS, 1):
            value = task.get(key, "")
            
            if data_type == "string":
                # Explicitly set as string to prevent formula execution
                cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value is not None else "")
                cell.data_type = 's'
                
            elif data_type == "boolean":
                cell = ws.cell(row=row_idx, column=col_idx, value=bool(value))
                
            elif data_type == "datetime":
                dt = parse_datetime(value)
                if dt:
                    # Convert to UTC and format as string for Excel
                    cell = ws.cell(row=row_idx, column=col_idx, value=dt)
                    cell.number_format = 'yyyy-mm-dd hh:mm:ss'
                else:
                    cell = ws.cell(row=row_idx, column=col_idx, value="")
                    cell.data_type = 's'
    
    # Auto-filter and freeze header
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(tasks) + 1}"
    ws.freeze_panes = "A2"
    
    # Auto-size columns
    for col_idx, (_, _, _) in enumerate(COLUMNS, 1):
        column_letter = get_column_letter(col_idx)
        max_length = 0
        
        # Find max content length in this column
        for row_idx in range(1, len(tasks) + 2):
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if cell_value:
                max_length = max(max_length, len(str(cell_value)))
        
        # Apply width with sensible limits
        width = min(max(max_length + 2, 10), 50)
        ws.column_dimensions[column_letter].width = width
    
    # Write atomically
    temp_path = f"{output_path}.partial"
    wb.save(temp_path)
    Path(temp_path).rename(output_path)

def main():
    if len(sys.argv) < 2:
        print("Usage: python action_items_xlsx.py <input_file1.json> [input_file2.json ...]")
        sys.exit(1)
    
    input_files = sys.argv[1:]
    output_file = "action_items.xlsx"
    
    print(f"Loading {len(input_files)} file(s)...")
    tasks = load_and_dedupe_files(input_files)
    
    if not tasks:
        print("No valid tasks found in input files")
        sys.exit(1)
    
    print(f"Processing {len(tasks)} tasks...")
    create_excel(tasks, output_file)
    
    print(f"Successfully created {output_file}")

if __name__ == "__main__":
    main()
```

## Integration with Other Recipes

This recipe complements the existing `conversations_xlsx.md` recipe, providing similar structured export functionality for action items. Both recipes follow the same design principles:

- Native Excel data types
- AutoFilter and frozen headers
- Atomic file writing
- Formula-safe string handling

## Troubleshooting

### Common Issues

1. **ImportError**: Make sure `openpyxl` is installed (`pip install openpyxl`)
2. **Empty output**: Check that your JSON files contain valid task objects with an 'id' field
3. **Large files**: For exports with thousands of tasks, processing may take longer

### Debug Mode

Add `--debug` to the script to see detailed processing information.

## Contributing

This recipe is part of the Omi CLI examples. To contribute improvements or additional features, please submit a pull request to the repository.
</content>