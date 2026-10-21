# Desktop test isolation

Regressions #13260 and #13468 showed that auth defaults and repeating timers
can poison unrelated desktop suites sharing a runner. These helpers live in
the existing desktop Swift test target; no additional test runner is required.

- Use `makeIsolatedDefaults()` from `desktop/macos/Desktop/Tests/Support/IsolatedTestDefaults.swift`
  and inject the returned defaults into the subject. The helper owns a unique
  domain and registers XCTest teardown; shared auth domains raced in #13260.
  New direct `UserDefaults.standard` mutations are ratcheted. Only singleton
  integration tests lacking an injection seam may annotate an individual site:
  `// omi-test-quality: shared-defaults -- integration: <why the shared domain is required>`.
  Preserve/restore the affected keys for those exceptions; the annotation does
  not provide isolation. The static check counts direct calls, not aliases.
- For chat repeating timers, use `OwnedRunLoopTimer` and retain explicit stop
  calls. The token invalidates on release; callbacks must capture feature owners
  weakly. `ManualRunLoopTimerScheduler` drives unscheduled timers and a fixed
  date in tests, so cancellation and elapsed-time behavior need no sleeps.
- `python3 desktop/macos/scripts/check_desktop_test_quality.py` ratchets legacy source
  inspection, wall-clock waits, and direct shared defaults mutations; its
  baselines may only decrease. The check and its fixture tests run in the
  existing desktop suite and the local/CI check manifest.

Run `python3 desktop/macos/scripts/tests/test_check_desktop_test_quality.py` to
exercise the static check and its no-increase CLI boundary. Focused Swift
coverage is `IsolatedTestDefaultsTests`, `KernelTurnRecordedProjectionTests`,
and `UserScrollDetectorTests` (including the chat glide and pinner guards).
Preserve the actual run-loop deinit regressions alongside the manually driven
scheduler cases: unscheduled timers prove cancellation and elapsed-time
behavior, while the real scheduler cases prove production wiring.

## Unsynced task recovery

- `TasksStore.retryUnsyncedItems` re-reads pending rows before dispatch. `UnsyncedTaskCreateProjection` carries supported stored fields through the existing create endpoint; malformed metadata/evidence stays pending rather than being acknowledged after a lossy upload.
- `UnsyncedTaskSyncOperations` injects only the existing effects. Keep its defaults owner-fenced, and carry the actual `LocalMutationAuthorization` from the retry loop through SQLite acknowledgement. Do not replace it with a current-UID lookup.
- Exercise the real retry loop and API writer, not only the generic create wrapper. `TasksStoreUnsyncedSyncTests` drives admission/read/create/acknowledgement continuations; `UnsyncedTaskCreateHTTPTests` intercepts an isolated URLSession without external calls. Genuine same-UID reauthentication is A → signed out → A; reapplying the same owner is not a new session.
- The shared `TaskSyncOwnerTestFixture` restores both auth and automation-owner keys through explicit no-op voice/kernel/storage transition hooks. Tests inject every storage/deletion effect so no customer database or backend is touched.
- Field preservation is not exactly-once delivery or atomic recurring rollover. Lost-response identity and edits arriving after dispatch require their own delivery design and regression proof.
