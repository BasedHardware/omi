```python
import datetime
import os
from based.hardware import action_items

def action_items_to_csv():
    """Convert action items to CSV format.
    
    Returns:
        str: CSV formatted string of action items.
    """
    data = f"Content-Type: text/csv; charset=utf-8\n\n"
    separator = os.linesep
    action_items = action_items.get_action_items()
    
    try:
        # Start with current date header
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        data += f"Action Items as of {current_date}\n"
        
        # Define headers
        headers = ['Action', 'Description', 'Created', 'Due', 'Status', 'Completed']
        data += separator + ",".join(headers) + "\n"
        
        # Prepare data rows
        for item in action_items:
            status = item.get('status', 'open')
            created = item.get('created')
            due = item.get('due')
            
            # Format datetime strings
            created_str = get_timestamp(created) if created else ""
            due_str = get_timestamp(due) if due else ""
            
            row = [
                item.get('action', ''),
                item.get('description', ''),
                created_str,
                due_str,
                status,
                "Yes" if item.get('completed', False) else "No"
            ]
            data += separator + ",".join(row) + "\n"
            
        return data
    
    except Exception as e:
        return f"Error: {str(e)}"

def get_timestamp(dt):
    """Convert datetime object to formatted string."""
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return ""
```

```python
from based.hardware import action_items

def test_action_items_to_csv():
    # Test case for action items to CSV conversion
    pass

# Add other test functions as needed
```