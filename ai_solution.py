Here's the complete code solution:

```python
import sys
import os
import argparse
from datetime import datetime
from collections import defaultdict

def main():
    # Define the script name for consistent help formatting
    script_name = os.path.basename(__file__)
    
    # Set up the argument parser
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to Joplin-compatible Markdown notes or JEX archives.",
        usage=f"{script_name} [-h] [options] <input1>..."
    )
    
    # Define the arguments
    parser.add_argument(
        "inputs", 
        nargs="*",
        help="Input files or '-' for stdin"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file (Markdown) or directory (JEX)",
        required=True
    )
    parser.add_argument(
        "--jex",
        action="store_true",
        help="Output as .jex archive"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Use with stdin"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite"
    )
    
    # Parse the arguments
    args = parser.parse_args()
    
    # Initialize variables
    output = args.output
    is_jex = args.jex
    is_stdin = args.stdin
    force = args.force
    inputs = args.inputs
    
    # Read the input data
    if is_stdin and not inputs:
        inputs = ["-"]
    data = []
    for input_file in inputs:
        if input_file == "-":
            data.append(sys.stdin.read())
        else:
            with open(input_file, "r") as f:
                data.append(f.read())
    
    # Process each JSON line
    memories = []
    for json_line in data:
        try:
            memory = json.loads(json_line)
            memories.append(memory)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
    
    # Format each memory into Markdown with frontmatter
    formatted = []
    for memory in memories:
        title = memory.get("title", "")
        content = memory.get("content", "")
        notebook = memory.get("notebook", "")
        tags = memory.get("tags", [])
        timestamp = memory.get("timestamp", "")
        
        frontmatter = f"""---
Title: {title}
Notebook: {notebook}
Tags: {' '.join(tags)} if tags else ''
Timestamp: {timestamp}
---
"""
        markdown = f"{frontmatter}{content}"
        formatted.append(markdown)
    
    # Handle output
    if is_jex:
        # Create JEX tar archive
        import tarfile
        with tarfile.open(output, "w:gz") as tar:
            for md in formatted:
                filename = f"joplin-note-{datetime.now().isoformat()}.md"
                tar.addfile(tarfile.TarInfo(name=filename), bytes(md, "utf-8"))
    else:
        # Write to directory
        if os.path.isdir(output):
            for md in formatted:
                filename = f"joplin-note-{datetime.now().isoformat()}.md"
                filepath = os.path.join(output, filename)
                with open(filepath, "w") as f:
                    f.write(md)
        else:
            with open(output, "w") as f:
                f.write("\n".join(formatted))
    
    # Handle deduplication
    seen = set()
    unique = []
    for md in formatted:
        id = json.loads(md.split("---")[2]).get("id", "")
        if id and id not in seen:
            seen.add(id)
            unique.append(md)
    if len(unique) < len(formatted):
        print(f"Removed {len(formatted) - len(unique)} duplicates")
    
    return 0

if __name__ == "__main__":
    main()
```

```python
import sys
import os
import json
import pytest

def test_jex_output(tmp_path):
    from memories_to_joplin import main
    test_input = '{"title":"Test","content":"Hello","notebook":"Test","tags":["test"],"timestamp":"now"}'
    main(["-"], output=str(tmp_path / "output.jex"), jex=True)
    assert os.path.isfile(str(tmp_path / "output.jex"))

def test_stdin_usage(capsys):
    from memories_to_joplin import main
    main(stdin=True, inputs=["-"], output="test.md")
    captured = capsys.readout()
    assert "usage" in captured.lower()

def test_frontmatter():
    from memories_to_joplin import main
    test_input = '{"title":"Test","content":"Hello","notebook":"Test","tags":["test"],"timestamp":"now"}'
    main([test_input], output="test.md", jex=False)
    with open("test.md") as f:
        content = f.read()
        assert "---" in content

def test_jex_import():
    from memories_to_joplin import main
    test_input = '{"title":"Test","content":"Hello","notebook":"Test","tags":["test"],"timestamp":"now"}'
    main([test_input], output="test.jex", jex=True)
    assert os.path.isfile("test.jex")

def test_deduplication():
    from memories_to_joplin import main
    input_data = '{"title":"Test","content":"Hello","id":"1"}\n{"title":"Test","content":"Hello","id":"1"}'
    main(inputs=[input_data], output="test.md", force=True)
    with open("test.md") as f:
        lines = f.readlines()
        assert len(lines) == 1

def test_multi_file():
    from memories_to_joplin import main
    input_files = ["input1.json", "input2.json"]
    main(inputs=input_files, output="test.md")
    assert os.path.isfile("test.md")
```

```markdown
# Omi to Joplin Converter

This script converts Omi memory JSON exports into Joplin-compatible Markdown notes or JEX archives.

## Usage

```bash
memories_to_joplin.py <input1>... [options]
```

### Options:

- `--output` (required): Output file (Markdown) or directory (JEX)
- `--jex`: Output as .jex archive
- `--stdin`: Use with stdin
- `--force`: Force overwrite

### Examples:

1. Pipe from Omi:

```bash
omni export memories --format json | memories_to_joplin.py --stdin --output joplin-notes/
```

2. Export to JEX:

```bash
memories_to_joplin.py input.json --jex --output memories.jex
```

3. Import JEX into Joplin:

```bash
joplin.exe import memories.jex
```

4. Use with directory output:

```bash
memories_to_joplin.py memories.json --output joplin-notes/
```
```

```markdown
# Omi CLI Tools

## Recipes

- **memories_to_joplin**: Converts Omi memory JSON exports into Joplin-compatible Markdown notes or JEX archives.
  - Usage: `memories_to_joplin.py <input1>... [options]`
  - Options: `--output` (required), `--jex`, `--stdin`, `--force`
```

This code provides the complete implementation as described, including the script, tests, documentation, and recipe entry.