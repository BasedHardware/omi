# WQ20 fix r2 — PR #23733

## Root cause

Reproduced on branch `lane/firestore-reads-wq20-generation`, starting from
`8d2fbb7acd6b31a65b6453419150936c4efb6146`: the complete canary file had
11 passes and the reported failed-undo retry failure.

The generation/memo leak hypothesis is falsified for this failure. The injected
`set_undone` exception occurs before its transaction runs, and the deterministic
canary edits a conversation, not People. No `people_meta/generation` document
is created during the failing sequence, and the attempt People memo is not used.

Tracing the exception hidden by `dream_canary.check()` identified:

```text
stage=undo, error_type=AttributeError
backend/database/review_changes.py:430
    if target.parent.id == 'people':
AttributeError: 'StrictFirestoreCollection' object has no attribute 'id'
```

The first successful probe uses transcript-overlay Undo. After the injected Undo
failure, the retry reaches the generic journal Undo path. PR #23733 added the
collection-reference lookup to that path for every edit, including conversation
edits. The strict fixture supports owner navigation but lacks collection `.id`.
The real Firestore SDK implements `.id`; this evidence demonstrates a newly
introduced fixture/API dependency, not a leaked production generation write.

## Fix

Carry the journal's collection field alongside each validated Undo row, and use
that field to select People generation bumps. The journal field already selects
the document reference, so a second reference-navigation lookup is unnecessary.
Update the entity-merge restoration loop to unpack the same row shape.

People mutation and generation increment remain in the same transaction. A
successful People Undo/Redo increments the monotonic fence; it must not decrement
it to an old value and accidentally authorize a stale memo. Non-People reversals
do not touch that fence. No counter rollback or memo workaround is needed for
the reproduced failure.

The original `test_failed_undo_does_not_poison_next_canary` and the strict fixture
are unchanged. Strengthen the existing five-case cleanup round-trip test to
assert generation 1/2/3 after People apply/Undo/Redo, and no generation document
for task/conversation edits.

`people_scan_dedupe` remains default-off (0). `FIRESTORE_READ_LEVERS`, runtime
configuration, workflows, and lever declarations are untouched. No GCP tier was
used; all verification is local and GitHub-only. No merge or deploy is requested.

## Verification

- Before fix: `test_dream_canary.py` — 11 passed, 1 failed.
- After fix: `test_dream_canary.py` — 12 passed.
- Full file-isolated regression run: **749 passed across 42 files**, zero failures,
  skips, or deselections (exit 0).
  - `test_dream_canary.py`: 12 passed (includes the unchanged failed-Undo test).
  - Other 38 `test_dream_*.py` files: 665 passed.
  - `test_fsr_people_scan_dedupe.py`: 39 passed.
  - `test_fsr_scope_opener.py`: 20 passed.
  - Additional writer coverage, `test_fsr_people_generation.py`: 13 passed.
- `scripts/pr-preflight --pr-body-file body.md`: 38 checks passed.
- `scripts/pr-preflight --metadata-only --pr-body-file body.md`: 4 checks passed.
- `make preflight`: 38 checks passed.
- `git diff --check`: passed.

Regression command (repository root; worktree-local `backend/.venv`):

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/WQ20-fix-r2-tests.txt \
  BACKEND_PYTEST_WORKERS=3 BACKEND_PYTEST_MARK_EXPR='slow or not slow' \
  bash backend/test.sh
```

The list contains all 39 `tests/unit/test_dream_*.py` files, plus
`test_fsr_people_scan_dedupe.py`, `test_fsr_scope_opener.py`, and
`test_fsr_people_generation.py` (42 files total). The marker expression is a
tautology so this requested run includes all tests, including marked tests.

Local evidence logs:
- `/Volumes/Ephemeral/scratch/WQ20-fix-r2-tests-all.log`
- `/Volumes/Ephemeral/scratch/WQ20-fix-r2-preflight.log`

## Workspace preservation

The initial lane had two foreign untracked reports. They are preserved in Git
stash `WQ20-r2 protect foreign reports before branch switch`, from branch
`lane/firestore-reads-flagoff8-1026`; they are not included in this fix.
