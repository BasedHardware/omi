# Round 2 startup architecture findings

## First fix: keep cold local-recording scans off the UI isolate

The startup scan is a backlog-dependent contributor, not evidence that all users'
10–15 second warm-up is explained by recordings. No appearance, navigation,
capture-mode, upload eligibility, duration, or account-ownership policy changed.

### Initialization order and evidence

Home/main locations below describe the inspected `e52113704226` baseline;
LocalRecordingsProvider locations refer to this fix. Concurrent Home/Tasks edits
arrived during final verification and are outside this commit.

- `app/lib/main.dart:288`: platform services, notification locale/service, and
  preferences are awaited before the app runs. At `:305`, ServiceManager is
  constructed only after the persisted backend override is restored. Preserve
  that routing boundary. Auth resolution (`:335`) and authenticated-owner
  cutover (`:356`) likewise precede product traffic intentionally.
- `app/lib/main.dart:399` calls `ServiceManager.start()` before `runApp` (`:484`).
  `app/lib/services/services.dart:75` starts device/WAL services;
  `app/lib/services/wals/wal_syncs.dart:229` starts five sync subsystems. Their
  asynchronous work can continue after the first visible frame.
- `app/lib/main.dart:672` supplies LocalRecordingsProvider through the capture /
  device provider graph. Its constructor (`app/lib/providers/local_recordings_provider.dart:101`)
  immediately calls `refresh()` before auto-upload/reconciliation. Home also
  reads it for the conversation-list snapshot, so this is startup work even
  when the user never opens local storage.
- `app/lib/pages/conversations/conversations_page.dart:293` loads the primary
  conversation list after the first frame. At `:313`, it schedules a second
  local-recording refresh after a 200 ms delay. Delaying that caller does not
  defer the provider's constructor scan.
- Before this change, `LocalRecordingsProvider.refresh()` synchronously read
  and decoded ownership metadata (`:155`, helper now at `:586`) and synchronously
  enumerated the directory (`:165`). For each owned finalized recording,
  `_durationSeconds()` (`:214`) scanned the entire binary file on a cold cache.
  Async 64 KB reads yielded between chunks but parsed every frame and ran every
  read-completion callback on the UI isolate. The cache lives only in the provider
  (`:228`), so process relaunch repeats this work.
- `app/lib/pages/home/page.dart:447` starts offscreen-tab prewarming on a 350 ms
  timer (`:204`). Tasks' first build then schedules task and integration loads
  (`app/lib/pages/action_items/action_items_page.dart:80`). This overlaps Home's
  initial requests and device/capture initialization (`home/page.dart:449`).

### Change

`app/lib/providers/local_recordings_provider.dart` now uses asynchronous directory
enumeration and asynchronous ownership-file existence/read operations. Exact
duration counting uses Flutter `compute` with a top-level worker and only a file
path as its argument. The worker reads/parses bounded 64 KB chunks synchronously
inside its own isolate and returns one integer. No provider, platform channel,
recording byte buffer, or owner data crosses into that worker.

The parse algorithm and its crash-tail / zero-length rules are unchanged. Existing
duration caching and estimate-on-read-failure behavior remain. Existing ownership
tests cover missing, corrupt, and foreign-account metadata. Additive tests cover
split headers, partial headers, oversized unsigned lengths, and worker I/O errors.

### Measured effect

Added `app/integration_test/perf/startup_recordings_probe_test.dart`. Reproduce:

```sh
cd app
flutter test --no-pub -d flutter-tester integration_test/perf/startup_recordings_probe_test.dart
```

The hermetic host probe creates a real 44,000,000-byte file with 1,000,000 complete
frames, then counts it three times. Each call scans the file anew; OS page cache
and JIT warm-up affect wall time. `ui_callback_ms` sums elapsed time in UI-zone
unary callbacks; it is diagnostic callback work, not a FrameTiming/jank metric
or complete process CPU measurement. Setup and fixture-file writing are excluded.

| Run | Before wall ms | After wall ms | Before UI callback ms | After UI callback ms | Before / after callbacks |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 56.784 | 21.321 | 21.495 | 0.229 | 1,349 / 2 |
| 1 | 52.447 | 16.757 | 21.013 | 0.009 | 1,349 / 2 |
| 2 | 52.539 | 12.392 | 21.307 | 0.004 | 1,349 / 2 |

Retained: the candidate demonstrably removes recording-size-dependent UI-isolate
callback work, and total scan time also improves on this workload. This is **not**
a measured reduction of the reported end-to-end 10–15 second window. The existing
four-scenario harness seeds an empty native directory and starts collecting after
provider boot; it cannot attribute this cold-backlog path. Physical AOT profiling
with a recording backlog remains the next fidelity step. A worker per uncached
recording has launch overhead, especially for many tiny files; cache hits avoid it.

### Verification

- `cd app && bash test.sh`: passed (138 spine tests; 5,340 ordinary tests,
  21 skips). Includes existing recording ownership/frame-count coverage and the
  three new boundary/error tests. Log: `/tmp/omi-startup-unit-gate.log`.
- `cd app && flutter analyze --no-pub`: completed with 93 repository-wide
  diagnostics (exit 1); **zero diagnostics in any of this commit's Dart files**.
  No new issues in changed files, as required. Log: `/tmp/omi-startup-analyze-gate.log`.
- `cd app && bash integration_test/journeys/run_journeys.sh`: passed all six
  hermetic journeys. Log: `/tmp/omi-startup-journey-gate.log`; receipts:
  `/tmp/omi-startup-journeys`.
- Backlog probe: passed before and after; logs:
  `/tmp/omi-startup-probe-before.log`, `/tmp/omi-startup-probe-after.log`.
- Final preflight: passed **23 checks** against the local commit with
  `OMI_PR_BODY_FILE=/tmp/omi-startup-preflight-body.md make preflight`.
  Log: `/tmp/omi-startup-preflight-committed.log`. The durable internal changelog
  fragment satisfies the committed-HEAD changelog check. The local metadata file
  declares `UI-Evidence: none` for this scheduling/parsing change. Initial preflight
  also passed; intermediate missing-fragment/metadata failures were resolved.
- Optional existing four-scenario perf gate: Home, detail and memories passed;
  Chat exceeded its 35 ms budget (p90 67.780 ms). A targeted Chat recheck also
  failed (p90 309.813 ms). Other Flutter suites/compiler processes were active
  during these samples, so these are not controlled performance comparisons.
  The required behavior gates above passed. Retain this caveat for consolidation;
  rerun the steady-state gate on a quiet host. No Chat code was changed here;
  the Chat-only fixture does not consume LocalRecordingsProvider, and the native
  directory is empty. Logs: `/tmp/omi-startup-perf-gate.log` and
  `/tmp/omi-startup-perf-chat-recheck.log`.

The unit gate and full analyzer ran before the other Home/Tasks workstream's
latest edits; journeys ran in the shared worktree with those edits in progress.
This commit includes only the recording-scan fix and its own supporting files.

### Next workstream

1. `app/lib/providers/local_recordings_provider.dart:144` and
   `app/lib/pages/conversations/conversations_page.dart:313`: coalesce overlapping
   constructor/page/finalization/resume refreshes. Preserve a rerun when a file is
   finalized during an active scan, account-epoch invalidation, and auto-upload
   ordering. Current scans can duplicate uncached duration work and notifications;
   this fix intentionally does not change their scheduling contract.
2. `app/lib/pages/home/page.dart` and
   `app/lib/pages/action_items/action_items_page.dart`: measure first Tasks navigation
   and task/integration hydration against active scrolling. At inspection, a fixed
   350 ms timer built Tasks while Home's first load could still be settling.
   Concurrent work is already removing that timer and changing task-load admission;
   use that workstream's final findings before proposing another scheduling change.
   Verify first-visit latency and retained tab state on the resulting architecture.
3. `app/lib/services/wals/wal_syncs.dart:229`, called from
   `app/lib/services/services.dart:75`: measure the five sync subsystems' first
   scan/reconciliation and notification fan-out after boot. Keep authenticated-owner
   cutover and WAL custody gates ahead of uploads; avoid casually backgrounding those.
4. `app/lib/backend/preferences.dart:1068`: cached list decoding constructs all
   model objects synchronously on each getter. Measure apps/conversations cache
   hydration and repeated reads before selecting memoization or isolate decoding.
   Ownership JSON decoding (`local_recordings_provider.dart:589`) also remains on
   the UI isolate, although its filesystem reads no longer block it.

Only this fix's files should be staged. The concurrent warm-up instrumentation
workstream owns `perf_warmup_test.dart` and its findings; preserve those changes.
