# 0006. A CI flag budget for the pipeline env surface

- Status: Accepted
- Date: 2026-10-25
- Deciders: product owner GO for the architecture-review items (2026-10-25 ~11:40Z, lead ruling `76d3e0`)
- Owner: infra; each scoped package's owner (listed in `config/flag_budget.json`)
- Review by: 2026-11-15 (the review's target: pipeline env names well below today's count after 100%)

## Context

The 2026-10-25 architecture review counted 651 env names read by backend code,
308 of them pipeline-related, and 52 default-off gates. Names accumulated with
no owner or expiry, meanings changed by host, and no one could say which flag
combinations had ever run together.

## Decision

- `tests/unit/test_flag_budget.py` inventories literal env names read
  (`os.getenv`, `os.environ`) under the batch pipeline, transcription routing,
  sync and policy packages (scope listed in the JSON) and compares them with
  `config/flag_budget.json`.
- The budget is today's count: **170 names**. A new name fails CI unless:
  - another name leaves the surface in the same change, the new entry says
    `{"replaces": "<OLD>"}`, and the old name's `retired` entry records
    `"replaced_by": "<NEW>"` (the budget holds); or
  - the entry carries an `owner` and a `review_by` date (an explicit exception).
    It fails again once `review_by` passes: renew it with a reason or delete the flag.
- Removing a name moves it to the append-only `retired` ledger
  (`{"on": date, "replaced_by": null}`) and lowers `budget` in the same change.
  A slot given up that way cannot be reclaimed by a later `replaces`.
  `budget` can never exceed the seeded 170.
- Literal names in positional and `key=` keyword form are both counted
  (`config/policy/guard.py:env_reads`).
- Changed-file CI selects the test for any scoped path
  (`scripts/select_backend_unit_tests.py:FLAG_BUDGET_PREFIXES`).

## Consequences

- Growth is visible and owned; shrinkage ratchets.
- Not counted: names read through helpers (`serving_for`, kill-switch registry
  lookups), names computed at runtime, and reads outside the scope. The
  batch-stage env ratchet (`tests/unit/test_batch_stage_env_ratchet.py`) still
  covers dynamic reads under `utils/batch_pipeline`.
- `config/feature-flags.yaml` stays the authority for what each gate means;
  this budget only bounds how many names exist.

## Implemented in

`backend/config/flag_budget.json`, `backend/tests/unit/test_flag_budget.py`,
`backend/scripts/select_backend_unit_tests.py`, `backend/config/policy/guard.py:env_reads`.
Residual: the ledger is append-only by convention; rewriting a dated `retired`
entry is visible in review but not machine-checked (that would need the base
branch's copy of the file).
