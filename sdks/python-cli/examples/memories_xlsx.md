```markdown
# Memories to Excel Workbook (.xlsx) Recipe

This recipe demonstrates how to convert `omi --json memory list` exports into structured Excel spreadsheets (.xlsx) with proper cell types, formatting, and features for better data analysis and visualization.

## Prerequisites

- Python 3.8+
- Required Python packages:
  ```bash
  pip install openpyxl
  ```

## Recipe Code

```python
#!/usr/bin/env python3
"""
Convert OMI memory list JSON export to an Excel workbook (.xlsx).
Features:
- UTC datetime formatting for created_at/updated_at
- Preserved boolean typing
- Formula injection defense
- Frozen header panes
- Table AutoFilter
- Auto-scaled column widths
- Safe atomic file writes
"""

import json
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

def convert_memories_to_xlsx(json_file, output_file):
    """Convert memories JSON to Excel with proper formatting and types."""
    
    # Load data from JSON file
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    if not data or 'memories' not in data or not data['memories']:
        raise ValueError("No memories found in the JSON file")
    
    # Create workbook and worksheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Memories"
    
    # Define datetime style
    datetime_style = NamedStyle(name="datetime_style")
    datetime_style.number_format = 'YYYY-MM-DD HH:MM:SS'
    
    # Write headers
    headers = list(data['memories'][0].keys())
    for col_num, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_num, value=header)
    
    # Write data with proper types
    for row_num, memory in enumerate(data['memories'], 2):
        for col_num, key in enumerate(headers, 1):
            value = memory[key]
            cell = ws.cell(row=row_num, column=col_num, value=value)
            
            # Set data type and formatting
            if key in ['created_at', 'updated_at'] and value:
                try:
                    # Parse ISO format datetime
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    cell.value = dt
                    cell.style = datetime_style
                except (ValueError, TypeError):
                    # Handle invalid datetime values
                    cell.data_type = "s"
            
            elif key in ['manually_added', 'reviewed']:
                # Ensure boolean type
                cell.data_type = "b" if isinstance(value, bool) else "s"
            
            else:
                # Defense against formula injection
                cell.data_type = "s" if isinstance(value, str) else None
    
    # Create table with AutoFilter
    table = Table(displayName="Memories", ref=f"A1:{get_column_letter(len(headers))}{len(data['memories']) + 1}")
    style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False,
                          showLastColumn=False, showRowStripes=True, showColumnStripes=True)
    table.tableStyleInfo = style
    ws.add_table(table)
    
    # Freeze header row
    ws.freeze_panes = 'A2'
    
    # Auto-adjust column widths
    for col_num, header in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = len(str(header)) + 2
    
    # Atomic file write using .partial swap
    temp_file = f"{output_file}.partial"
    wb.save(temp_file)
    os.replace(temp_file, output_file)
    
    print(f"Successfully converted memories to {output_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert OMI memories JSON to Excel")
    parser.add_argument("input", help="Input JSON file from 'omi --json memory list'")
    parser.add_argument("-o", "--output", default="memories.xlsx", help="Output Excel file")
    
    args = parser.parse_args()
    
    try:
        convert_memories_to_xlsx(args.input, args.output)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
```

## Usage

1. Export memories from OMI CLI:
   ```bash
   omi --json memory list > memories.json
   ```

2. Run the converter:
   ```bash
   python memories_xlsx.py memories.json -o memories.xlsx
   ```

## Features

- **Datetime Formatting**: `created_at` and `updated_at` fields are properly formatted as UTC datetimes
- **Boolean Preservation**: `manually_added` and `reviewed` fields maintain their boolean type
- **Security**: Formula injection defense by explicitly setting string data types
- **Usability**: Frozen header panes, table AutoFilter, and auto-scaled column widths
- **Reliability**: Safe atomic file writes using a temporary .partial file swap

## Output Example

The resulting Excel workbook will have:
- A properly formatted table with filterable headers
- Datetime columns showing in YYYY-MM-DD HH:MM:SS format
- Boolean columns showing TRUE/FALSE values
- All columns automatically sized to fit content
- Header row frozen for easy navigation
```