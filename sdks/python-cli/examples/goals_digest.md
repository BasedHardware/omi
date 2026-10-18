# Build a goals digest (KPIs, types, status)

Use this recipe to see goal progress at a glance — an executive Markdown
summary from one or more `goal list` exports: totals, active/inactive counts,
achieved rate, average progress, a per-type breakdown, and per-goal status
indicators. It reads saved JSON exports, makes no network requests, and
writes one Markdown file. You need Python 3.9+ and an authenticated `omi-cli`
for the initial export.

Export your goals:

```sh
omi --json goal list > goals.json
```

Check that the command succeeded before converting.

## The converter

The script lives at [`goals_digest.py`](goals_digest.py) in this directory —
stdlib-only, zero external dependencies.

**KPIs:** total goals · active · inactive · achieved (≥100% of target) ·
average progress across metric goals. A `goal_type` breakdown table gives
count + average progress per type; every goal gets a status indicator
(✅ achieved / 🟢 active / ⏸ inactive) with its `current/target unit`.

## Usage

```sh
python goals_digest.py goals.json -o goals_digest.md
```

Multi-page: feed several export files — each goal ID is counted once even if
it appears on multiple pages:

```sh
python goals_digest.py goals_p1.json goals_p2.json -o goals_digest.md
```

Example output:

```markdown
# Goals digest

- **Total goals:** 3
- **Active:** 2
- **Inactive:** 1
- **Achieved (≥100%):** 1
- **Average progress:** 75%

## By type

| Goal type | Count | Avg progress |
|---|---|---|
| numeric | 2 | 75% |
| qualitative | 1 | — |

## Goals

- 🟢 **Drink water** — 1/2 liters
- ✅ **Read 12 books** — 12/12
- ⏸ **Be kind**
```

## Safety

* `..` in the `-o` path is refused.
* Exclusive `x` creation — an existing file is never overwritten; a failed
  write leaves no partial file.
* Malformed JSON or a missing input exits `2` with a clean message.
