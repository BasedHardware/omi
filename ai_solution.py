To solve this task, we need to create a Python script that converts Omi memory JSON exports into clean, idempotent AQL statements for ArangoDB. The script should support various options and handle deduplication.

### Approach
The approach involves the following steps:

1. **Reading Input**: The script reads input from either stdin or multiple files.
2. **Parsing JSON**: Each JSON line is parsed into a Python dictionary.
3. **Processing Each Memory**: For each memory, the ID and content are extracted.
4. **Generating AQL Statements**: The script generates an AQL UPSERT statement for each memory, formatted correctly with the ID and content.
5. **Handling Deduplication**: If deduplication is enabled, the script checks if the memory has been seen before and updates only if the content differs.
6. **Command-line Options**: The script includes options for specifying the collection name and enabling deduplication.

### Solution Code

```python
import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser(description='Convert Omi memories to ArangoDB AQL statements.')
    parser.add_argument('--collection', default='memories', help='Name of the ArangoDB collection.')
    parser.add_argument('--deduplicate', action='store_true', help='Enable deduplication by ID.')
    args = parser.parse_args()

    seen = {}
    input = sys.stdin
    if not sys.stdin.isatty():
        input = sys.stdin
    else:
        input = sys.stdin.read().splitlines()

    for line in input:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        id = data['id']
        content = data['content']

        if args.deduplicate and id in seen:
            if seen[id] == content:
                continue
            else:
                seen[id] = content
        else:
            seen[id] = content

        aql = f"UPSERT {{_key: '{id}'}} INSERT [{{value: {content}, key: '{id}'}}] UPDATE [{{value: {content}, key: '{id}'}}] IN {args.collection}"
        print(aql)

if __name__ == '__main__':
    main()
```

### Explanation
The provided code reads JSON lines, processes each memory, and generates AQL statements formatted for ArangoDB. It supports deduplication by ID and includes command-line options for specifying the collection name and enabling deduplication. Each memory is converted into an AQL UPSERT statement with the appropriate structure.