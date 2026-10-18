# Convert a goal export to todo.txt

Use this recipe to drop Omi goals into any todo.txt app or plain-text
workflow. It reads a saved JSON export, makes no network requests, and maps
each goal onto standard todo.txt syntax. You need Python 3.9+ and an
authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list > goals.json
```

## The converter

The script lives at [`goals_to_todotxt.py`](goals_to_todotxt.py) in this
directory — stdlib-only, zero external dependencies.

**Mapping:**

| Goal field | todo.txt output |
|---|---|
| `is_active: true` | `(B)` priority prefix |
| `is_active: false` | `x` completion prefix |
| `category` | `+<Category>` project tag |
| `current_value`/`target_value`/`unit` | `cur:X`, `target:Y`, `unit:Z` tags |
| progress ratio | `pct:NN%` tag |
| `id` | `omi:<id>` tag |

Example line:

```
(B) Drink water +health cur:1 target:2 unit:liters pct:50% omi:g1
```

## Usage

```sh
python goals_to_todotxt.py goals.json omi_goals.txt
```

Active goals (`(B)`) sort first; inactive goals (`x …`) sort last — the file
reads like a real todo.txt: pending work on top, completions below.

## Syntax protection

A goal title that happens to *look like* todo.txt syntax — `x Done`,
`(A) priority`, `due:tomorrow`, `+project`, `due:`/`pri:`/`rec:` keys — is
neutralized with a zero-width space so it can't masquerade as a completion
mark, priority, project, or recognized tag. Your titles stay your titles.

## Safety

* `..` in the output path is refused.
* Exclusive `xb` creation — an existing file is never overwritten; a failed
  write leaves no partial file.
* Malformed JSON or a missing input exits `2` with a clean message.
