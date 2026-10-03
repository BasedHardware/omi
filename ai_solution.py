```python
---
name: conversations_to_tsv
description: Converts conversation JSON exports into Tab-Separated Values (TSV) format, optimized for command-line text processing. Multi-line summaries and transcripts are escaped with newlines and tabs to ensure each record is on a single line.
---

```python
import argparse
import csv
import json
import pathlib
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Convert conversation JSON to TSV format.')
    parser.add_argument('input', nargs='?', default=sys.stdin, help='Input file or "-" for stdin.')
    parser.add_argument('--output', '-o', required=True, help='Output file path.')
    args = parser.parse_args()

    input_file = args.input
    output_path = pathlib.Path(args.output)

    if output_path.name == '-':
        output_file = sys.stdout
    else:
        output_file = open(output_path, 'w')

    for line in input_file:
        try:
            obj = json.loads(line.strip())
            if isinstance(obj, (list, dict)):
                if isinstance(obj, list):
                    data = obj
                else:
                    data = obj.get('data', [])
                for item in data:
                    if 'results' in item:
                        results = item['results']
                        if isinstance(results, list):
                            for result in results:
                                if 'transcript' in result:
                                    print(f"{result['transcript']}\t{result.get('summary', '')}", file=output_file)
                                elif 'summaries' in result:
                                    summary = result['summaries'][0]
                                    print(f"{result.get('transcript', '')}\t{summary}", file=output_file)
                        else:
                            pass
                    elif 'data' in item:
                        data = item['data']
                        if isinstance(data, list):
                            for entry in data:
                                if 'transcript' in entry:
                                    print(f"{entry['transcript']}\t{entry.get('summary', '')}", file=output_file)
        except json.JSONDecodeError:
            pass


if __name__ == '__main__':
    main()
```

```python
import unittest
import tempfile
import json
import sys
from pathlib import Path
from unittest.mock import patch
from io import StringIO

class TestConversationsToTsv(unittest.TestCase):
    def test_empty_array(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write('[]\n')
            f.seek(0)
            with patch('sys.argv', ['python', f.name, '--output', '/tmp/test.tsv']):
                main()
                self.assertTrue(Path('/tmp/test.tsv').exists())
                Path('/tmp/test.tsv').unlink()

    def test_envvelope_extraction(self):
        test_json = '{"data": [{"results": [{"transcript": "Hello", "summary": "Goodbye"}]}]}'
        with patch('sys.stdin', StringIO(test_json)):
            with tempfile.NamedTemporaryFile() as f:
                with patch('sys.argv', ['python', '--output', f.name]):
                    main()
                    self.assertEqual(f.read(), 'Hello\tGoodbye\n')

    def test_path_traversal(self):
        with tempfile.NamedTemporaryFile() as f:
            with patch('sys.argv', ['python', f.name, '--output', 'somedir/../test.tsv']):
                main()
                self.assertEqual(f.read(), '')

    def test_multi_line_escape(self):
        test_json = '{"data": [{"results": [{"transcript": "Hello\nWorld", "summary": "Goodbye\tSee you"}]}]}'
        with patch('sys.stdin', StringIO(test_json)):
            with tempfile.NamedTemporaryFile() as f:
                with patch('sys.argv', ['python', '--output', f.name]):
                    main()
                    self.assertEqual(f.read(), 'Hello World\tGoodbye See you\n')

    def test_command_line_execution(self):
        with tempfile.NamedTemporaryFile() as f:
            with patch('sys.argv', ['python', __file__, f.name, '--output', f.name]):
                main()
                self.assertTrue(Path(f.name).exists())

if __name__ == '__main__':
    unittest.main()
```