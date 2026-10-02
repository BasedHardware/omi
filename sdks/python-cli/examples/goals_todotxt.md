# Turn your goals into a todo.txt file

Use this recipe to manage your Omi goals in the plain-text
[todo.txt](https://github.com/todotxt/todo.txt) format, supported by the todo.txt CLI,
Simpletask, sleek, Markor, and many other task management tools. It converts saved JSON
exports into standard todo.txt tasks: active goals receive a default `(B)` priority,
completed or inactive goals are marked with `x`, categories become `+projects` (`+scale`,
`+numeric`, `+boolean`), and progress metrics are tracked via custom tags (`cur:`,
`target:`, `pct:`, `unit:`, `omi:`).

It runs completely offline using the Python standard library with zero third-party packages.

## Prerequisites

- Python 3.9+
- An authenticated `omi-cli` session (`omi auth login`)

## 1. Export your goals

Export your active goals (default limit is 10; specify `--limit 100` for the maximum page size):

```sh
omi --json goal list --limit 100 > goals_active.json
```

To include archived and inactive goals as well, add the `--include-inactive` flag:

```sh
omi --json goal list --limit 100 --include-inactive > goals_all.json
```

> **Note**: The Omi CLI exports up to 100 goals per run via `--limit 100`. Inactive and
> completed goals require `--include-inactive` to be emitted.

## 2. Convert to todo.txt

Run `goals_to_todotxt.py` by passing the exported JSON file and target destination:

```sh
python goals_to_todotxt.py goals_all.json todo.txt --utc-offset +00:00
```

### Direct terminal pipeline (streaming)

You can stream directly from the Omi CLI through Unix pipes without intermediate JSON files:

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_todotxt.py - todo.txt --force
```

### Options and flags

| Option | Default | Description |
| :--- | :--- | :--- |
| `source` | _(required)_ | Input JSON file from `goal list`, or `-` for stdin. |
| `destination` | _(required)_ | Destination todo.txt file path, or `-` for stdout. |
| `--utc-offset` | Local timezone | Calendar date offset (e.g. `+00:00`, `-05:00`). |
| `--priority` | `B` | Priority letter for active goals (`A` through `Z`). |
| `-f`, `--force` | `False` | Overwrite destination file if it already exists. |

## Example todo.txt output

```text
(B) 2026-09-30 Daily 10k steps +scale cur:8500 target:10000 pct:85% unit:steps omi:g_101
(B) 2026-09-29 Marathon training distance +numeric cur:57 target:100 pct:57% unit:km omi:g_102
(B) 2026-09-20 Learn conversational Spanish +boolean cur:0 target:1 pct:0% omi:g_103
x 2026-09-28 2026-09-01 Read 20 books +numeric cur:20 target:20 pct:100% unit:books omi:g_104
x 2026-09-15 2026-09-02 Complete annual health check +boolean cur:1 target:1 pct:100% omi:g_105
x 2026-08-05 2026-08-01 Abandoned milestone +scale cur:0 target:10 pct:0% omi:g_106
```

## Security & format guarantees

1. **Syntax Collisions**: Titles containing `+projects` or `@contexts` have zero-width spaces (ZWSP)
   prepended to prevent accidental todo.txt syntax parsing. Titles starting with completion `x`,
   priority `(A)`, or dates are similarly protected.
2. **Atomic Writes**: Uses safe temporary-file writes and atomic renames to prevent partial or
   corrupted files if interrupted. Refuses overwrite without `-f / --force`.
3. **Symlink and Traversal Protection**: Rejects symlink targets and traversal sequences (`..`).
4. **Air-Gapped & Hermetic**: 100% Python standard library with no external network requests.
