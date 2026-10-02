```python
import json
import sys
import os
import re

def conversations_to_jsonl(input_file=None):
    output = sys.stdout
    output_file = None
    if input_file:
        output = open(input_file, 'w')
        output_file = input_file

    def format_conversation(conv):
        formatted = {
            'id': conv.get('id'),
            'title': conv.get('title'),
            'category': conv.get('category'),
            'started_at': conv.get('started_at'),
            'finished_at': conv.get('finished_at'),
            'source': conv.get('source'),
            'overview': conv.get('overview'),
            'action_items': conv.get('action_items', [])
        }
        # Normalize timestamps
        for key in ['started_at', 'finished_at']:
            if isinstance(formatted[key], str):
                if re.match(r'^\d+$', formatted[key]):
                    formatted[key] = formatted[key]
                else:
                    formatted[key] = formatted[key]
        if 'action_items' in formatted:
            formatted['action_items'] = [
                {'description': item.get('description'), 'completed': item.get('completed')}
                for item in formatted['action_items']
            ]
        if input_file and '--include-transcript' in sys.argv:
            transcript = conv.get('transcript', [])
            formatted['transcript'] = [
                {
                    'speaker': t.get('speaker'),
                    'start': t.get('start'),
                    'end': t.get('end'),
                    'text': str(t.get('text')) if isinstance(t.get('text'), dict) else t.get('text')
                }
                for t in transcript
            ]
        return formatted

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            conv = json.loads(line)
            if input_file and '--category' in sys.argv:
                categories = sys.argv[sys.argv.index('--category') + 1].split(',')
                if conv.get('category') not in categories:
                    continue
            output.write(json.dumps(format_conversation(conv), ensure_ascii=False) + '\n')
        except json.JSONDecodeError:
            pass

    if output != sys.stdout:
        output.close()

if __name__ == '__main__':
    conversations_to_jsonl()
```