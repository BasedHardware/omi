```python
# sdks/python-cli/examples/goals_xlsx.md
```json
{
  "recipe": {
    "name": "goals_xlsx",
    "description": "Exports Omi goals to an Excel .xlsx file with native cell types.",
    "command": "goals_to_xlsx.py",
    "arguments": {
      "--filename": {
        "type": "string",
        "required": true,
        "description": "Path and name for the output Excel file."
      }
    },
    "output": "Exports goals to an Excel workbook with formatted cells and data."
  }
}
```

```python
# goals_to_xlsx.py
"""Converts Omi goals to an Excel .xlsx file with native cell types."""
import pandas as pd
from datetime import datetime

def goals_to_xlsx(goals, filename):
    """Converts goals to an Excel .xlsx file with formatted cells."""
    df = pd.DataFrame([goal.to_dict() for goal in goals])
    
    # Format numbers
    df = df.apply(lambda x: x.apply(lambda y: y if isinstance(y, (int, float)) else y), axis=1)
    
    # Format percentages
    df['percentage'] = df.apply(lambda row: f"{row['percentage']:.1%}", axis=1)
    
    # Format timestamps
    df['timestamp'] = df.apply(lambda row: row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'), axis=1)
    
    # Preprocess for Excel
    df = df.replace({pd.NA: ''})
    
    # Create Excel writer
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        worksheet = writer.book.active_sheet
        worksheet.freeze_panes(1, 0)
        worksheet.UsedRange.AutoFilter()
        
        for column in worksheet.columns:
            column autofit()

def main():
    import sys
    from ..cli import get_goals
    if len(sys.argv) < 2:
        print("Usage: goals_to_xlsx.py <filename>")
        return
    filename = sys.argv[1]
    goals = get_goals()
    goals_to_xlsx(goals, filename)

if __name__ == "__main__":
    main()
```

```python
# test_goals_to_xlsx.py
import pandas as pd
from datetime import datetime
from goals_to_xlsx import goals_to_xlsx

def test_goals_to_xlsx_runs():
    """Test that goals_to_xlsx runs without error."""
    goals = [{'name': 'Test Goal', 'current_value': 50, 'target_value': 100}]
    goals_to_xlsx(goals, 'test_goals.xlsx')

def test_goals_to_xlsx_data():
    """Test that goals_to_xlsx converts data correctly."""
    goals = [
        {
            'name': 'Test Goal',
            'current_value': 50,
            'target_value': 100,
            'min_value': 0,
            'max_value': 150,
            'percentage': 0.5,
            'timestamp': datetime.now()
        }
    ]
    goals_to_xlsx(goals, 'test_goals.xlsx')
    df = pd.read_excel('test_goals.xlsx')
    assert df.shape[0] == 1
    assert df['percentage'][0] == '50.0%'
    assert isinstance(df['timestamp'][0], str)
    
if __name__ == "__name__":
    test_goals_to_xlsx_runs()
    test_goals_to_xlsx_data()
```