# Shared rules for the PR A Sol slices (Firestore reads, 2026-10-16)

Also read /Users/dazheng/workspace/omi/data/run-2026-10-16-firestore-reads/CONTEXT.md (goal, measurements, suspects).

## Where you work
- Worktree: /Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-firestore-reads-upstream-keep-clean
  (branch `lane/firestore-reads`, public BasedHardware/omi, cut from origin/main). Read `AGENTS.md` and
  `backend/AGENTS.md` there first.
- FOUR agents edit this tree at the same time. Edit ONLY the files your slice owns (listed in your brief) plus
  NEW files whose names start with your slice prefix, and new test files `backend/tests/unit/test_fsr_<slice>_*.py`.
  If you need a change in a file you don't own, do not make it — describe it in your report.
- Do NOT edit: `backend/deploy/**`, `backend/charts/**`, `config/feature-flags.yaml`, `.github/**`,
  `backend/config/firestore_read_levers.py`. The integrator wires config.
- Do NOT commit, push, stash, reset, or run `git checkout`/`git restore` on anything. Leave your edits uncommitted.
  Never run `git stash` (shared object store).

## The lever contract
- Every behavior change is gated by `config.firestore_read_levers.lever_enabled(<lever>, key)`; with the env unset the
  code path must be byte-for-byte the current behavior (same reads, same writes, same responses).
  Per-user levers key on uid; fleet levers key on pod/host name (`HOSTNAME` / `K_REVISION`+instance) or call with no key.
- Lever names you may use are in `KNOWN_LEVERS` in `backend/config/firestore_read_levers.py`. If you need a new one,
  say so in your report (integrator adds it); meanwhile use the closest existing name.
- New tunables (intervals, TTLs) are env-configurable with the CURRENT value as default.

## The correctness gate (required)
1. Behavior-preservation: with levers off, existing tests for the touched modules pass unchanged.
2. Read-count proof per lever: a unit test that counts Firestore reads on the call path (wrap/patch the db client or
   use the probe's counters from `database/firestore_document_probe.py`) with lever off vs on and asserts the
   reduction you claim (e.g. "10 ticks across 5 replicas: 50 scans → 10").
3. Safety tests for anything touching entitlements, deletion fencing, or conversation lifecycle (see your brief).
- Run only targeted test files, prefixed with `nice -n 19`, via `echo tests/unit/x.py > /tmp/l.txt; cd backend &&
  BACKEND_UNIT_TEST_FILE_LIST=/tmp/l.txt bash test.sh` (test.sh ignores positional args). NEVER the full suite locally —
  CI runs it; the host is shared and overloaded. Keep `black --line-length 120 --skip-string-normalization` formatting (`~/.local/bin/black`).
- Redis: reuse the existing client (`database/redis_db.py`). Any cache must fail OPEN to the current Firestore read
  on Redis error, never fail closed and never serve stale data across an explicit invalidation.

## Report (final message, and write it to /Users/dazheng/workspace/omi/data/run-2026-10-16-firestore-reads/SOL-<slice>-report.md)
- Files changed; each lever: what it does, predicted reads/day removed (show the arithmetic + which measurement or
  code fact it rests on), risk, and how verify.sh should detect harm (metric/log/route).
- Tests added and the exact command + result.
- Config the integrator must add (env names, defaults), and any change needed in files you don't own.
