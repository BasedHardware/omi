# INV-PERF-1: The mobile UI isolate stays free for frames

**Status:** proposed
**Statement:** In the Flutter app, work that grows with the user's history (WAL index, live transcript, conversation pages, recordings directory) never runs synchronously on the UI isolate, and a state change notifies only the listeners whose inputs actually changed.

The UI isolate builds, lays out and paints every frame. The October 2026 lag audit found the app
stuttering while syncing or recording because whole-index JSON rewrites, full-transcript
fingerprints and synchronous directory listings ran there, and because root proxy-provider hooks
re-notified on every upstream change (one chat token rebuilt capture and device listeners).
Details and the measurement tools: [`app/docs/performance.md`](../../app/docs/performance.md).

## MUST NOT

- Use synchronous `dart:io` (`readAsStringSync`, `writeAsStringSync`, `listSync`, `existsSync`,
  `writeFromSync`, `flushSync`, …) in `app/lib/`; use the async API.
- `jsonEncode`/`jsonDecode` a collection that grows with history on the UI isolate; route it
  through `offUiIsolate` (`app/lib/utils/off_ui_isolate.dart`). Providers do not parse JSON.
- Call `notifyListeners()` from a `ChangeNotifierProxyProvider` update hook (the methods named
  `previous?..hook(...)` in `app/lib/main.dart`) without returning early when nothing changed.
- Do O(transcript) or O(index) work in a listener that runs on every notify; key it on a cheap
  change signal (list identity, length, a version counter) first.
- Drive a repaint with a `Timer.periodic` faster than 100 ms that notifies a shared provider;
  tick a dedicated `ValueNotifier` only the painting widget listens to.
- Add `BackdropFilter`/`ImageFilter.blur` to a scrolling list or a surface that stays on screen,
  decode a network image without `memCacheWidth`/`cacheWidth`, or lay out a list with
  `shrinkWrap: true`.

## Surfaces

- Flutter mobile app (`app/lib/`)

## Guard tests

- `.github/scripts/check_mobile_ui_isolate.py` — **no-increase ratchet** per rule and per changed
  file under `app/lib/` against the PR merge base (new files start at zero), including JSON
  outside `offUiIsolate` in the history-sized modules, plus an absolute check that every proxy
  update hook in `app/lib/main.dart` returns early on an `identical`/`==` test before notifying.
  Escape hatch: `// omi-perf-allow: <rule> -- <reason>` on the line or the line above.
- `.github/scripts/test_check_mobile_ui_isolate.py` — proves every rule fails on the defect it
  targets and passes with the allow comment, on an unchanged count and on a decrease.
- `app/test/perf/notify_amplification_test.dart` — repeated proxy updates do not notify, and
  capture notifies that leave the transcript alone do not walk it.
- `app/test/perf/conversation_list_off_ui_test.dart` — list parsing and cache encoding give
  identical results off the UI isolate, and a stale background write never lands (including
  across sign-out).
- `app/test/unit/wal_file_manager_save_cost_test.dart` — queued WAL index saves collapse into the
  newest snapshot and large indexes encode off the UI isolate.
- `app/test/unit/voice_recorder_mic_contention_test.dart` — dictation ticks the waveform, not the
  provider.
- `app/test/unit/local_segment_store_test.dart` — the off-isolate transcript digest equals the
  inline one.

- `app/test/perf/production_shell_gate_test.dart` — all eight seeded performance scenarios
  mount the source-checked production shell with the iOS analytics arm enabled and accessibility
  initially off; work-count budgets and zero semantics compile/share budgets block release
  admission through Mobile App Checks. `bash app/tool/perf_gate.sh` repeats this three times.
- `app/tool/perf_shell.py --check` — rejects production-shell drift instead of silently omitting
  app-wide wrappers; `app/test/perf/perf_budget_test.dart` proves mutation/empty-evidence rejection.

## Path globs

- `app/lib/**`

## PR rule

Proposed per `PRODUCT.md` (seven unchanged days before locking); the guard runs in CI regardless
(`.github/checks-manifest.yaml`). Once locked, do **not** require naming `INV-PERF-1` in routine app PRs. The ratchet and the tests carry the
floor. Name `INV-PERF-1` only when changing a rule, the guard, or `offUiIsolate`.

## Related

- [`app/docs/performance.md`](../../app/docs/performance.md) — causes, tools and the perf harness
- [`mobile-ux-contract.md`](./mobile-ux-contract.md) — INV-UI-3, the same ratchet shape for UI primitives
