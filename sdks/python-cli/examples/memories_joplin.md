# Omi Memories to Joplin Converter

Convert Omi memory JSON exports to Joplin-compatible Markdown notes or `.jex` archives.

## Installation

Requires Python 3.10+ (no external dependencies).

```bash
pip install -e .  # If installed in development mode
```

## Usage

### Basic Conversion

Convert a single memory JSON file to Markdown:

```bash
python -m sdks.python_cli.examples.memories_to_joplin input.json output_dir/
```

### Pipe from Omi CLI

```bash
omi memories export --format json | \
  python -m sdks.python_cli.examples.memories_to_joplin - output_dir/
```

### Create JEX Archive

```bash
python -m sdks.python_cli.examples.memories_to_joplin input.json output.jex
```

### Import into Joplin

1. **Markdown Directory**: Import the output directory directly via Joplin's "Import from Markdown" feature.
2. **JEX Archive**: Drag-and-drop the `.jex` file into Joplin or use "Import from JEX" in the menu.

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Overwrite existing files | `false` |

## Notes

- All memories are deduplicated by their `id` field.
- Timestamps are converted to ISO 8601 format.
- Default notebook is "Omi Memories" with tags `omi` and `memory`.
- Filenames are sanitized to be filesystem-safe.

## Example Output

```markdown
---
title: Test Memory
notebook: Omi Memories
tags:
- omi
- memory
- test
- sample
created_time: 2023-01-01T00:00:00
updated_time: 2023-01-02T00:00:00
---

# Heading

Some content
```