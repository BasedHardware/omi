## What

Fixes the CLI SQLite recipe parser (`sdks/python-cli/examples/action_items_to_sqlite.py` and `sdks/python-cli/examples/action_items_sqlite.md`) to correctly import empty wrapped action-item exports (`{"action_items": []}`, `{"items": []}`, `{"data": []}`) as zero rows without failing. Closes #19329.

## Why

In `rows_from()`, wrapped action items were extracted using a boolean `or` chain:
```python
items = (
    items.get("action_items")
    or items.get("items")
    or items.get("data")
    or [items]
)
```
In Python, an empty list `[]` evaluates to `False`. When an export wrapped an empty list, the chain fell through to `[items]`, wrapping the parent dictionary into `[{"action_items": []}]`. Because this wrapper dict lacked an `id` field, the parser aborted with:
`ValueError: ... action item is missing an id`

## Changes

- **Example Script** (`sdks/python-cli/examples/action_items_to_sqlite.py`): Replaced the boolean `or` chain with explicit key membership checks (`key in items`) for `"action_items"`, `"items"`, and `"data"`. Empty lists in recognized wrapper keys are now preserved as `[]`, while single unadorned action items continue falling through via `for-else` to `[items]`.
- **Documentation Recipe** (`sdks/python-cli/examples/action_items_sqlite.md`): Updated the embedded script's `rows_from()` to match.
- **Regression Tests** (`sdks/python-cli/tests/test_action_items_to_sqlite.py`): Added unit test coverage for empty wrappers, mixed-file batches containing empty and valid exports, single-object inputs, malformed wrapper validation, and pre-validation database atomicity.

## Tests

Commands run (all passed):
- `python -m unittest discover -s sdks/python-cli/tests -p test_action_items_to_sqlite.py -v` (10/10 tests pass, including all 5 new regression tests)
- Synthetic local reproduction verifying `bare`, `action_items`, `items`, and `data` empty wrappers return `(0, 0, 0)`

## Failure-Class

Failure-Class: none

## Invariants

`scripts/pr-preflight --suggest` reports no affected product invariants for this diff.
