# Export memories to Joplin (offline Markdown notes and JEX archive)

Use this recipe to export Omi memories into [Joplin](https://joplinapp.org/) as standard Markdown notes or a portable `.jex` archive for offline-first personal knowledge management.

Joplin is an open-source, end-to-end encrypted note-taking and to-do application. This recipe structures each memory into an individual note containing formatted headers, categories, tags, and timestamps.

The companion script [`memories_to_joplin.py`](memories_to_joplin.py) runs on Python 3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`, `tarfile`, `datetime`).

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_joplin.py - -o memories.jex
```

## 2. Convert to Joplin notes or JEX archive

### Export directly to a .jex archive (recommended)

Create a single compressed archive that can be directly imported into Joplin:

```sh
python memories_to_joplin.py memories.json -o memories.jex
```

### Export to a directory of Markdown notes

Generate individual Markdown note files:

```sh
python memories_to_joplin.py memories.json -o joplin_notes/
```

### Custom notebook name

Specify a target notebook name for metadata organization:

```sh
python memories_to_joplin.py memories.json -o memories.jex --notebook-name "Wearable Thoughts"
```

### Combining multiple exports

Merge multiple export files into one archive with deduplication by memory ID:

```sh
python memories_to_joplin.py day1.json day2.json -o memories.jex --force
```

## 3. Import into Joplin

### Importing .jex Archive

1. Open Joplin desktop application.
2. Go to **File** -> **Import** -> **JEX - Joplin Export File**.
3. Select your generated `memories.jex` file.
4. Your memories will appear under the configured notebook with all tags intact.

### Importing Markdown Directory

1. Open Joplin.
2. Go to **File** -> **Import** -> **MD - Markdown (Directory)**.
3. Select the `joplin_notes/` directory.

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.jex` file or directory path | *(required)* |
| `--notebook-name` | Target Joplin notebook name | `Omi Memories` |
| `-f`, `--force` | Overwrite destination file/folder if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_memories_to_joplin.py
```
