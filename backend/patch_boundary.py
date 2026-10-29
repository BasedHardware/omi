import sys

file_path = "tests/unit/test_episode_boundary_evidence.py"
with open(file_path, "r") as f:
    content = f.read()

# I am replacing NOW with a dynamic time logic. But WAIT! `test_episode_boundary_evidence.py` defines `NOW`:
# NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
# If I change NOW, I must be careful not to break other tests that might rely on `NOW` being a fixed time.
# But wait! I patched it previously, and then `git restore` wiped my patch. So right now, the repo has the bug.
# The error was:
# =========== test_no_split_inside_a_signal_but_end_and_quiet_are_hard ===========
# >       assert boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(minutes=11), firestore_client=store) == 'hold'
# E       AssertionError: assert 'legacy' == 'hold'
#
# AND
#
# ___________ test_evidence_is_idempotent_and_late_retry_cannot_reopen ___________
# >       assert next(iter(windows.values()))['ended_at'] == closed.ended_at
# E       StopIteration
#
# Both of these are caused by `boundary_store` implicitly using `datetime.now(timezone.utc)` for the `now - RETENTION` logic.
# Wait, `now - RETENTION` logic checks if `ended_at` is older than 7 days.
# Because `NOW` is hardcoded to 2026-10-22, and the system clock is 2026-10-29.
# 2026-10-29 - 7 days = 2026-10-22.
# In `test_no_split_inside_a_signal_but_end_and_quiet_are_hard`:
# `boundary_store.record` writes `started_at=NOW`, `ended_at=NOW + 30 min` which is `2026-10-22 15:30`.
# If `now` is `2026-10-29 16:40`, `now - 7 days = 2026-10-22 16:40`.
# Since `2026-10-22 15:30` < `2026-10-22 16:40`, the record is older than `now - 7 days`, so it gets pruned!
# So `windows` comes back empty.
# If `windows` is empty, `boundaries.conversation_decision` has no windows, so it falls back to `'legacy'`.

# The easiest and most robust fix is to mock `datetime.now` in `boundary_store.py` for all tests, or just change `NOW` in the test file to `datetime.now(timezone.utc)`.

search1 = "NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)"
replace1 = "NOW = datetime.now(timezone.utc).replace(microsecond=0)"
if search1 in content:
    content = content.replace(search1, replace1)

with open(file_path, "w") as f:
    f.write(content)
