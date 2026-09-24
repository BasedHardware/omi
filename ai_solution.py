```python
# sdks/python-cli/examples/memories_to_csv.py
import json
import csv
import sys
from datetime import datetime

def parse_json_line(line):
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Export memories to CSV.')
    parser.add_argument('-i', '--input', type=str, required=True,
                        help='Input file path or "-" for stdin.')
    args = parser.parse_args()
    
    input_path = args.input
    csv_writer = csv.writer(sys.stdout, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    headers = ['text', 'knowledge']
    csv_writer.writerow(headers)
    
    input_data = sys.stdin if input_path == '-' else open(input_path, 'r')
    
    for line in input_data:
        data = parse_json_line(line)
        if data:
            text = data.get('text', '')
            knowledge = data.get('knowledge', '')
            created = data.get('created', '')
            
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    created_utc = dt.strftime("%Y-%m-%dT%H:%M:%S UTC")
                except Exception:
                    created_utc = created
            else:
                created_utc = ''
            
            csv_writer.writerow([text, created_utc])
    
    if input_path != '-':
        input_data.close()

if __name__ == "__main__":
    main()
```

```markdown
# sdks/python-cli/examples/memories_csv.md
Memories to CSV Converter
===

This script converts memories into a CSV format, making them easy to analyze.

## Usage
```bash
python memories_to_csv.py -i <input_file>
```

## Arguments
- `--input` (`-i`): Path to the input file or `-` for standard input.

## Example
For an input file `memories.json`:
```bash
python memories_to_csv.py -i memories.json
```

## Output
The output is a CSV file with columns:
- `text`: The memory text
- `knowledge`: The knowledge
```

```python
# sdks/python-cli/tests/test_memories_to_csv.py
import pytest
from unittest.mock import patch
import csv

def test_memories_to_csv():
    test_cases = [
        ("{'text': 'Test text', 'created': '2023-10-05T12:00:00.000Z'}", "Test text,,"),
        ("{'text': 'Test text2', 'created': '2023-10-05T12:00:00.000Z', 'knowledge': 'know'}", "Test text2,know"),
    ]

    with patch('sys.stdin') as mockstdin:
        mockstdin.read.return_value = '\n'.join([json.dumps(case[0]) for case in test_cases])
        output = run_and_get_output()

    lines = output.split('\n')
    for i, case in enumerate(test_cases):
        assert lines[i].strip() == case[1].strip()

def run_and_get_output():
    import io
    import sys
    sys.stdout = io.StringIO()
    from memories_to_csv import main
    main()
    output = sys.stdout.getvalue()
    sys.stdout.close()
    return output

def test_multiple_files():
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        output = run_and_get_output()
        assert output.count(',') == 2  # Two headers and two test cases

def test_stdin():
    test_input = '{"text": "Test", "created": "2023-10-05T12:00:00.000Z"}\n{"text": "Test2", "knowledge": "know"}'
    with patch('sys.stdin') as mockstdin:
        mockstdin.read.return_value = test_input
        output = run_and_get_output()
    assert output.count(',') == 4  # Two headers and two test cases

def test_timestamp():
    test_input = '{"text": "Test", "created": "2023-10-05T12:00:00.000Z"}'
    with patch('sys.stdin') as mockstdin:
        mockstdin.read.return_value = test_input
        output = run_and_get_output()
    assert "2023-10-05T12:00:00 UTC" in output

if __name__ == "__main__":
    pytest.main()
```

```markdown
# sdks/python-cli/examples/README.md
# Examples

## Memory CSV Export
Export memories to CSV with:

```bash
python examples/memories_to_csv.py -i memories.json
```

## Knowledge CSV Export
For knowledge facts:

```bash
python examples/memories_to_csv.py -i knowledge.json
```
```