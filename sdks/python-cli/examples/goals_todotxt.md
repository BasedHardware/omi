# Turn goals into a todo.txt file (#19113)

Use this recipe to track your Omi goals and targets in the plain-text
[todo.txt](https://todotxt.org) format (issue #19113), compatible with the todo.txt
CLI, Simpletask, sleek, Markor, and plaintext task managers. It reads a saved JSON
export, makes no network requests, and outputs one formatted line per goal: active
goals with priority `(B)`, inactive goals with completion prefix `x`, goal types
mapped to project tags (`+numeric`, `+scale`, `+boolean`), and progress metrics
preserved as key-value tags (`cur:`, `target:`, `pct:`, `unit:`).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export. Pure
standard library only — zero extra dependencies.

## Step 1: Export goals

Export both active and inactive goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

> **Note**: `goal list` defaults to active goals only. Passing `--include-inactive`
> ensures inactive/completed goals are included so they can be marked with the `x`
> completion marker in your todo.txt file.

## Step 2: Convert to todo.txt (#19113)

Run the converter script [`goals_to_todotxt.py`](goals_to_todotxt.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/goals_to_todotxt.py goals.json -o todo.txt
```

To overwrite an existing todo.txt file:

```sh
python sdks/python-cli/examples/goals_to_todotxt.py goals.json -o todo.txt --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json goal list --limit 100 --include-inactive | python sdks/python-cli/examples/goals_to_todotxt.py - -o todo.txt # #19113
```

## todo.txt Mapping & Structure (#19113)

| Format Element | Generated Value | Purpose / Behavior |
|---|---|---|
| **Priority / State** | `(B)` or `x` | Active goals receive priority `(B)`. Inactive goals receive `x`. |
| **Creation Date** | `YYYY-MM-DD` | Extracted from `created_at` timestamp. |
| **Title** | Shielded title | Zero-width space (`\u200b`) protection shields syntax collisions. |
| **Project Tag** | `+numeric`, `+scale`, `+boolean`, or `+goal` | Derived from `goal_type`. |
| **Current Value** | `cur:X` | Current progress value. |
| **Target Value** | `target:Y` | Target threshold value. |
| **Progress Percentage** | `pct:Z%` | Normalized completion percent (0.0% to 100.0%). |
| **Unit** | `unit:NAME` | Measurement unit (e.g. `hours`, `pages`). |
| **Identifier** | `id:ID` | Omi goal identifier for reference. |

## Security & Reliability Invariants

- **Syntax Collision Shielding**: Insert zero-width spaces (`\u200b`) before user-supplied tokens starting with `+`, `@`, `(`, or reserved tag prefixes so they cannot accidentally override todo.txt projects, contexts, or metadata.
- **Progress Normalization**: Safely calculates percentage for scale, boolean, and numeric goal types, protecting against division by zero.
- **Atomic File Writing**: Writes output to a `.partial` file before atomically replacing destination via `os.replace`.
- **Path Traversal Protection**: Rejects destination paths containing `..` components.
