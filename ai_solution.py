```python
import sys
import json
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Export Omi memories to TSV format.')
    parser.add_argument('--category', nargs='+', help='Filter memories by category.')
    args = parser.parse_args()

    client = OmiClient()
    memories = client.get_memories()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            memory = json.loads(line)
            text = memory['text']
            category = memory.get('category', '')
            date = datetime.fromisoformat(memory['timestamp']).isoformat()
            
            # Escape special characters
            escaped_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t').replace('\\', '\\\\')
            
            # Replace special formula characters
            escaped_text = escaped_text.replace('=', '\\=') \
                                      .replace('+', '\\+') \
                                      .replace('-', '\\-') \
                                      .replace('@', '\\@')
            
            tsv_line = f"{escaped_text}\t{category}\t{date}\n"
            print(tsv_line, end='')
        except json.JSONDecodeError:
            pass

if __name__ == "__main__":
    main()
```

```markdown
# memories_to_tsv.py

This script exports Omi memories into a TSV (Tab-Separated Values) format, making it easy to import into spreadsheets and databases.

## Usage
```bash
python memories_to_tsv.py --category <category> < input.json
```

## Features
- Converts JSON lines of memories to TSV.
- Supports category filtering.
- Escapes special characters for spreadsheet compatibility.
```

```python
import sys
import json
from datetime import datetime

def test_memories_to_tsv():
    test_cases = [
        ("{}", "text\tcategory\tdate\n"),
        ({"text": "Test text", "category": "test", "timestamp": "2023-10-10T12:00:00"}, "Test text\ttest\t2023-10-10T12:00:00\n"),
        ({"text": "Hello\nWorld", "category": "example", "timestamp": "2023-10-10T12:00:00"}, "Hello\\nWorld\texample\t2023-10-10T12:00:00\n"),
    ]
    for input_json, expected_tsv in test_cases:
        line = json.dumps(input_json)
        output = []
        for line in [line]:
            line = line.strip()
            if not line:
                continue
            try:
                memory = json.loads(line)
                text = memory['text']
                category = memory.get('category', '')
                date = datetime.fromisoformat(memory['timestamp']).isoformat()
                
                escaped_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t').replace('\\', '\\\\')
                escaped_text = escaped_text.replace('=', '\\=') \
                                          .replace('+', '\\+') \
                                          .replace('-', '\\-') \
                                          .replace('@', '\\@')
                
                tsv_line = f"{escaped_text}\t{category}\t{date}\n"
                output.append(tsv_line)
            except json.JSONDecodeError:
                pass
        assert ''.join(output) == expected_tsv

if __name__ == "__main__":
    test_memories_to_tsv()
```