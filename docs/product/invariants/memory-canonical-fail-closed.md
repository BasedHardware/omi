# INV-MEM-3: No legacy fallback after canonical selection

**Status:** locked
**Statement:** After canonical memory rollout selection places a user in enrolled
read-mode, control/projection/generation failures must fail closed. Legacy
memory readers must not be used as a fallback when the canonical projection path
is unavailable.

## MUST NOT

- Fall back to legacy memory reads for enrolled read-mode users when control doc
  read, generation, gate, projection, or cursor checks fail.
- Treat legacy fallback as a recovery path for projection-not-ready or stale
  generation in enrolled read-mode.

## Surfaces

- `utils.memory.v3.control_reader_contract` route decisions
- `utils.memory.default_read_rollout` rollout wiring
- `utils.memory.v3.memory_read_service` canonical read service

## Guard tests

- `backend/tests/unit/test_inv_mem_1_guard.py` — behavioral tests for
  `decide_v3_control_route` (missing control doc, stale generation, projection
  not ready) asserting `FAIL_CLOSED` and `fallback_to_legacy_allowed=False`

## Path globs

- `backend/utils/memory/v3/control_reader_contract.py`
- `backend/utils/memory/default_read_rollout.py`
- `backend/utils/memory/v3/memory_read_service.py`
- `backend/utils/memory/v3/production_runtime.py`

## PR rule

Name `INV-MEM-3` in the PR body if you touch the path globs above.

## Related

- [memory-tiers.md](./memory-tiers.md) — INV-MEM-1 tier vocabulary
- [memory-vector-hydration.md](./memory-vector-hydration.md) — INV-MEM-2 vector
  hydration fail-closed
