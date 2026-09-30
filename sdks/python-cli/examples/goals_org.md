# Omi goals → Org-mode recipe

Turn a goals export from the Omi CLI into an Org-mode file that integrates with
Emacs Org: TODO/DONE states with progress cookies, an ASCII progress bar, a
property drawer with Omi metadata, grouping sections, and filter options.

```sh
# one master file
omi --json goal list --include-inactive > goals.json
python examples/goals_to_org.py goals.json omi_goals.org

# with your local time zone and grouping
python examples/goals_to_org.py goals.json omi_goals.org --utc-offset +09:00 --group-by status

# straight from the pipe, active goals only, one file per goal
omi --json goal list | python examples/goals_to_org.py - "" --active-only --output-dir org_goals/
```

The script is self-contained: standard library only, no dependencies to install.

## What you get

Each goal becomes an Org heading with its type as a tag:

```org
* TODO Read books [50%] [5/10] :numeric:
- Progress: [=========>          ] 50.0%
:PROPERTIES:
:OMI_ID: g1
:GOAL_TYPE: numeric
:CURRENT_VALUE: 5
:TARGET_VALUE: 10
:MIN_VALUE: 0
:MAX_VALUE: 10
:UNIT: books
:IS_ACTIVE: true
:CREATED: [2026-09-01 Tue 09:00]
:UPDATED: [2026-09-15 Tue 09:00]
:END:
```

- **States.** `DONE` when the goal is inactive (`is_active: false`,
  i.e. completed/archived) or when a metric goal has reached its target;
  `TODO` otherwise.
- **Progress cookie.** `[50%]` for metric goals, plus `[current/target]` when
  both values are present. No cookie for qualitative goals without metrics.
- **Progress bar.** `- Progress: [=========>          ] 50.0%` — a 20-cell bar
  (`=` fill, `>` head, trailing spaces) with a one-decimal percentage.
  `- Progress: n/a (no metrics)` when the goal carries no usable numbers.
- **Progress fraction.** For `scale`/`numeric` goals the fraction is
  `(current - min) / (max - min)` when the span is usable, otherwise
  `current / target`; clamped to `0..1`. For `boolean` goals it is 1 when
  `current_value >= 1`, else 0.
- **Drawer keys.** `:OMI_ID:`, `:GOAL_TYPE:`, `:CURRENT_VALUE:`, `:TARGET_VALUE:`,
  `:MIN_VALUE:`, `:MAX_VALUE:`, `:UNIT:`, `:IS_ACTIVE:` are written only when
  present; `:CREATED:` / `:UPDATED:` use inactive Org timestamps in the chosen
  zone. Integer-valued floats render without the trailing `.0`.

## Options

| Flag | Effect |
|---|---|
| `--utc-offset +HH:MM` | write timestamps at this offset; default is this computer's zone |
| `--group-by status` | `* Active` / `* Completed & archived` sections (goals as `**`) |
| `--group-by type` | one section per `goal_type` (`numeric`, `scale`, `boolean`) |
| `--group-by none` | flat list (default) |
| `--active-only` | drop completed/archived goals |
| `--goal-type numeric,scale,boolean` | keep only the listed types |
| `--output-dir DIR` | one `.org` file per goal (created if missing) instead of one master file |
| source `-` | read the JSON export from stdin instead of a file path |

Ordering is deterministic: active goals before completed ones, then by goal
type, then by title. `--output-dir` names files from the title slug
(`same-name.org`, `same-name-2.org`, ...) in sort order, so collisions are
resolved deterministically.

## Robustness

- Accepts the documented envelope shapes (`{"goals": [...]}`, `{"items": ...}`,
  `{"data": ...}`), a bare list, and a single goal object; an empty envelope
  yields a header-only file, never phantom headings.
- Numbers arrive loosely typed from the dev API; anything non-numeric is
  dropped from the fraction math instead of raising.
- Titles are escaped so Org does not misparse them: leading `[#A]` priority
  cookies, date-like `<2026-10-01>`/`[2026-10-01]` fragments, and trailing
  `:tags:` get the documented zero-width-space guard.
- The UTF-8 BOM that Windows/Excel pipelines add is tolerated (`utf-8-sig`).
- The destination is created exclusively: an existing file is refused (no
  overwrite) and a failed write never leaves a partial `.org` behind.

## Tests

`tests/test_goals_to_org.py` — hermetic unit tests (JSON fixtures in, text
out): cookie/bar rendering at 0/50/100%, DONE mapping (target reached and
inactive), property drawer contents, Org-syntax escaping, grouping, filters,
envelope unwrapping, BOM handling, overwrite refusal, and CLI failure exit
codes.
