```python
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert conversation data to Jupyter notebooks.')
    parser.add_argument('-o', '--output-dir', default='.', help='Output directory for the notebook files.')
    parser.add_argument('-f', '--filename', help='Base filename for the notebook.')
    parser.add_argument('-w', '--overwrite', action='store_true', help='Overwrite existing files.')
    parser.add_argument('input', nargs='?', default='-', help='Input file or "-" for stdin.')
    args = parser.parse_args()
    
    if args.input == '-':
        input = sys.stdin.read()
    else:
        with open(args.input, 'r', encoding='utf-8-sig') as f:
            input = f.read()
    
    data = json.loads(input)
    
    if 'conversations' in data and 'items' in data['conversations'] and 'data' in data['conversations']['items'][0] and 'results' in data['conversations']['items'][0]['data']:
        # Unwrap the data
        conversations = data['conversations']['items']
    else:
        conversations = data
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for idx, conv in enumerate(conversations):
        if 'results' in conv and len(conv['results']) > 0:
            summary = conv['results'][0].get('value', {}).get('summary', '')
            action_items = [f"- {item}" for item in conv['results'][1:] if item.get('value', {}).get('text', '')]
        else:
            summary = ''
            action_items = []
        
        transcript = conv.get('transcript', [])
        
        if not args.filename:
            base = f"conversation_{idx}"
        else:
            base = args.filename
        
        now = datetime.now().isoformat()
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": f"""# Conversation {idx + 1}
## Summary
{summary}

### Action items
{chr(10).join(action_items)}
"""
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": f"transcript = {json.dumps(transcript, ensure_ascii=False)}"
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {
                    "name": "python"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 0
        }
        
        filename = f"{base}_{now.replace(':', '').replace('.', '')}.ipynb"
        path = output_dir / filename
        
        if path.exists() and not args.overwrite:
            idx = 1
            while (existing := Path(base).with_suffix(f"_{now.replace(':', '').replace('.', '')}.ipynb{idx}")).exists():
                idx +=1
            filename = existing.name
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, ensure_ascii=False, indent=2)
    
if __name__ == '__main__':
    main()
```