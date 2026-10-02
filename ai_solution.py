```python
#!/usr/bin/env python
"""Converts memories to CSV format with specific columns and formatting."""
import json
import sys
from datetime import datetime
from dateutil.parser import parse as parse_date

def main():
    """Main entry point for memories to CSV conversion."""
    csv_output = []
    headers = ['id', 'content', 'category', 'tags', 'visibility', 'created_at', 'updated_at', 'app_id']
    csv_output.append(','.join(headers))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        if 'items' in data:
            items = data['items']
            if isinstance(items, list):
                for item in items:
                    data = item['data']
                    break
            else:
                data = items
        else:
            data = data

        row = []
        for key in headers:
            value = data.get(key)
            if key == 'content':
                if value and 'formula' in value:
                    value = f"{value}\uFFFD"
            if key == 'tags':
                if value:
                    value = '|'.join(value)
            if key in ('created_at', 'updated_at'):
                if value:
                    value = datetime.utcfromtimestamp(value).isoformat() if isinstance(value, (int, float)) else value
            row.append(str(value) if value is not None else '')
        csv_output.append(','.join(row))

    output = '\ufeff'.encode('utf-8').bom + '\n'.join(csv_output).encode('utf-8')
    if sys.stdout.isatty():
        print(output.decode('utf-8'))
    else:
        sys.stdout.write(output)

if __name__ == '__main__':
    main()
```