```python
import pandas as pd
import openpyxl

# Read the output from the command
import subprocess
import os
import json

# Read the command output
command = 'omi --json memory list'
result = subprocess.run(command, shell=True, capture_output=True, text=True)
output = result.stdout.strip()

# Load the JSON output into a DataFrame
data = json.loads(output)
df = pd.DataFrame(data)

# Format the Excel file
with pd.ExcelWriter('memories.xlsx', engine='openpyxl', mode='w') as writer:
    # Apply formatting
    df.style.apply(lambda x: ['font_size:12;'] * len(x), axis=1)
    df.style.apply(lambda x: ['font:bold;'] * len(x), axis=1, start_row=1)
    
    # Convert date columns to datetime and format
    df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
    df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True)
    
    # Format boolean columns
    df = df.convert_dtype(convert_booleans=True)
    
    # Set string type for specific columns
    df[['manually_added', 'reviewed']] = df[['manually_added', 'reviewed']].astype('object')
    
    # Save to Excel with styles
    df.to_excel(writer, index=False, sheet_name='Memories')
    worksheet = writer.book.active
    worksheet.freeze_panes(row=1)
    worksheet.conditional_formatting.auto_filter.set_filter(0)
    
    # Format columns
    for column in range(len(df.columns)):
        worksheet.column_dimensions[get_column_letter(column)].width = 20
    
    # Format date columns
    for col in ['created_at', 'updated_at']:
        df[col].format = 'yyyy-mm-dd hh:mm:ss'
    
    # Save the formatted Excel file
print("Excel file saved as memories.xlsx")
```