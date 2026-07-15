---
name: desktop-app-flows
description: "Understand and explore the Omi desktop macOS app's UI flows, navigation patterns, and SwiftUI architecture. Use when developing features, fixing bugs, or verifying changes in desktop/ Swift files. Provides agent-swift commands to explore the live app, understand how screens connect, and verify your work."
allowed-tools: Bash, Read, Glob, Grep
---

# Omi Desktop App — Flows & Exploration

This skill teaches you the Omi desktop macOS app's navigation structure, screen architecture, and SwiftUI patterns. Use it when developing features (to understand how the app works), fixing bugs (to navigate to the affected screen), or verifying changes (to confirm your code works in the live app).

## Fast-Path for Local Iteration (start here)

Two things make iterating on the desktop app slow: signing in (web OAuth) and clicking through the UI to reach a screen. Both are solved — use these before reaching for `agent-swift`.

### 1. Skip the web login (seed auth/settings once, reuse forever)
Named bundles clone auth state + Firebase tokens into UserDefaults; on first launch the app migrates tokens into its own Keychain item (correct `teamid:` partition — avoids the login-keychain password sheet). Prefer `./run.sh` for named bundles — it dumps/seeds after install. Manual seed:
```bash
cd desktop/macos
./scripts/omi-auth-dump.sh                                  # capture Omi Dev's session -> tmp/desktop-auth.json
./scripts/omi-auth-seed.sh com.omi.omi-myfeature \
  tmp/desktop-auth.json \
  "/Applications/omi-myfeature.app"                         # optional: Team ID for clearing stale Keychain
./scripts/omi-settings-seed.sh com.omi.omi-myfeature       # replay shortcuts/settings
```
The seeded bundle boots already signed-in and past onboarding, with Omi Dev's shortcuts/settings — no browser. The captured Firebase idToken expires (~1h); re-run `omi-auth-dump.sh` after signing in again if backend calls start 401ing. **Scope:** this is for dev iteration only — when validating the onboarding or auth flows themselves (or running flow-walker E2E), use the real flow per Guard Conditions below.

### 2. Jump straight to any screen (automation bridge)
The app runs a local HTTP control bridge (`DesktopAutomationBridge.swift`) that **auto-enables on every non-production bundle** (off on prod). `scripts/omi-ctl` drives it — jump to a screen in ~150ms instead of clicking through the sidebar:
```bash
./scripts/omi-ctl wait-ready                 # block until app reaches "main" state
./scripts/omi-ctl navigate rewind            # jump to the Rewind screen
./scripts/omi-ctl navigate settings rewind   # Settings page, Rewind sub-section
./scripts/omi-ctl state                       # read selected tab / auth / onboarding state as JSON
./scripts/omi-ctl screens                     # list valid targets
```
Disable with `OMI_DISABLE_LOCAL_AUTOMATION=1` to run a dev build "clean". Running several named bundles at once? Give each its own `OMI_AUTOMATION_PORT` (default 47777).

### 2a. Desktop core E2E harness (tiered)
Primary entry for the desktop confidence ladder: `scripts/desktop-core-harness.sh` (see `e2e/CORE_E2E.md`).
```bash
./scripts/desktop-core-harness.sh --self-check   # Linux-safe T0 (flow lint + gauntlet hooks)
./scripts/desktop-core-harness.sh --tier 1 --bundle omi-core-e2e
./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e   # hermetic: dev-up offline + core matrix
```
Typed flows live in `e2e/flows/`; run individually with `scripts/omi-harness run <flow.yaml> --lane bridge`.

### 2b. Run semantic actions (cursor-free, in-process)
Beyond navigation, the bridge exposes named **actions** that invoke the app's real
code paths directly — no synthetic mouse events, so they never grab the cursor (the
deterministic equivalent of the Flutter app's Marionette driver). Prefer these over
`agent-swift click`/coordinate clicking for anything they cover.
```bash
./scripts/omi-ctl actions                          # discover available actions + params
./scripts/omi-ctl action refresh_all_data          # same as Cmd+R
./scripts/omi-ctl action toggle_transcription enabled=false
```
`omi-ctl actions` returns descriptors with `category`, `surfaces`, `safety`,
`sideEffects`, `examples`, and `preferSemantic`. Scan those fields before using
`agent-swift`: prefer actions whose `surfaces` match the screen and whose
`safety` is `read_only`, `local_artifact`, or `local_ui_state` for routine checks.
Add new actions in `DesktopAutomationActionRegistry` (`registerBuiltins()` for global
ones, or `register(name:summary:params:handler:)` from a view model for screen-scoped
ones). `GET /actions` lists them; `POST /action {name, params}` runs one and returns
the resulting state snapshot.

### 2b.1 Probe a current-screen PTT turn

`ptt_test_turn` is the first-class, non-production PTT controller probe. It captures the
same one pre-overlay screen image used by a physical PTT press and drives the real hub turn.
Its added screen-protocol diagnostics expose only safe lifecycle state—never pixels, app names,
or evidence IDs. Use it to reproduce and diagnose a screen-answer stall without coordinate
clicking:

```bash
cd desktop/macos
OMI_AUTOMATION_PORT=47920 bash ./scripts/ptt-screen-probe.sh
```

The probe emits only the safe state needed to diagnose its result. For a successful screen report,
expect `screen_evidence_last_completion=completed`, `screen_evidence_protocol_active=false`,
and `pending_tool_count=0`. A non-`completed` completion class identifies the local fail-closed
boundary; `terminal_reason=tool_timeout` is always a regression. This validates the controller
and capture/transport lifecycle; use a natural authenticated physical PTT press as the final UX
validation.

### 2c. Verify SD-card WAL cloud upload (WiFi / BLE)
After a device SD-card download (WiFi or BLE), confirm the WAL uploaded — not just
saved locally. Both `StorageSyncService` and `WifiSyncService` call `syncToCloud()`
after `updateWalWithDownloadedData`; the WiFi path tears down the device SoftAP
first so the Mac can regain internet before upload.
```bash
# Structured WAL state via automation bridge (named test bundle must be running)
cd desktop/macos && ./scripts/omi-ctl action wal_snapshot
# Expect pending_count=0 and status synced|uploaded after SD-card sync completes

# After triggering SD sync in a named test bundle:
OMI_LOG_PATH="$(./scripts/omi-ctl log-path)"
rg 'Uploaded WAL|WiFi sync completed|syncToCloud' "$OMI_LOG_PATH" | tail -20
```
Expect log lines like `Uploaded WAL <id>: status=synced` (or `status=uploaded` for
202-queued jobs). Hermetic regression:
`cd desktop/macos && xcrun swift test --filter 'WifiSync|SdCardSyncParity'`.

### 2d. Inject backend faults (failure-path testing)
The hermetic E2E harness is backend-only, so desktop failure paths (backend 5xx →
structured `ChatErrorState`, task sortOrder sync failure surfaced/retried not silent,
transcription transport truthfulness) can't be driven end-to-end. `scripts/omi-fault-inject.sh`
stands up a local endpoint that fails on purpose; point a **named test bundle** (never
prod) at it via the documented backend overrides — `OMI_PYTHON_API_URL` (chat / action-item
sync / transcription relay), `OMI_DESKTOP_API_URL` (Rust backend), `OMI_AUTH_API_URL` (auth):
```bash
cd desktop/macos
eval "$(./scripts/omi-fault-inject.sh start error)"      # modes: error | status:CODE | latency | reset | refuse
OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 \
  OMI_PYTHON_API_URL="$OMI_FAULT_URL" OMI_DESKTOP_API_URL="$OMI_FAULT_URL" \
  OMI_APP_NAME="omi-fault" ./run.sh &
./scripts/omi-ctl wait-ready
./scripts/omi-ctl action ask query="hi"                  # exercise the path; assert a surfaced error, not a crash/silent no-op
./scripts/omi-fault-inject.sh stop
```
`status:CODE` returns an HTTP status code in 100-599 (e.g. `status:503`, `status:429`, `status:401`);
`latency` sleeps `--latency-ms` (default 30 000) before replying (watchdog/timeout paths);
`reset` RSTs the connection; `refuse` leaves the port closed (connection refused). Verify a
mode with `curl` before launching the app: `curl -s -o /dev/null -w '%{http_code}\n' "$(./scripts/omi-fault-inject.sh url)"`.

### 2e. Hardening smoke (runtime regression tripwire)
`scripts/omi-hardening-smoke.sh` re-runs the proven runtime probes behind hardened
acceptance rows so a behavior that regresses upstream is caught on the next run, not the
next manual audit. One-time setup — build and seed a dedicated named bundle:
```bash
cd desktop/macos
OMI_APP_NAME="omi-smoke" ./run.sh          # build + install /Applications/omi-smoke.app, then quit it
./scripts/omi-auth-dump.sh                 # capture the signed-in Omi Dev session
./scripts/omi-auth-seed.sh com.omi.omi-smoke tmp/desktop-auth.json "/Applications/omi-smoke.app"
```
Then re-run any time (launches the installed bundle on an isolated port, ends with it stopped):
```bash
./scripts/omi-hardening-smoke.sh run                          # all probes, defaults: com.omi.omi-smoke, port 47797
./scripts/omi-hardening-smoke.sh run --only set-01,set-04     # subset
./scripts/omi-hardening-smoke.sh run --attach --port 47795    # against an already-running bundle (skips lifecycle probes)
./scripts/omi-hardening-smoke.sh scan <dir>                   # credential-pattern sweep of any evidence dir
```
Probes in canonical order (destructive last): `auth-06` prod tokens-at-rest (passive read) ·
`set-04` log credential hygiene · `set-01` settings navigation · `mic-06` rapid-PTT orphan
guard · `chat-03` agent-kill recovery · `auth-03` expired-token refresh (**relaunches** the
app) · `lnch-07` shutdown flush (**stops** the app) · `self-hygiene` report-dir scan.
Exit codes: `0` all PASS · `1` any FAIL (a regression — investigate) · `2` usage/prod-refusal ·
`3` BLOCKED only (harness couldn't run: port busy, stale auth seed, app missing). Reports +
`smoke-summary.json` land under `${TMPDIR}/omi-hardening-smoke/<ts>/` unless `--report-dir` is
given. Safety: only `com.omi.omi-*` bundles are accepted; the sole production interaction is
the read-only `defaults read` in `auth-06`.

### 2e. Stall the agent stream (chat watchdog testing)
The HTTP fault harness (§2c) can't stall the **agent** stream — that's a node/stdio
bridge, not HTTP. Two non-prod bridge actions freeze it so the chat stall path can be
exercised end-to-end (CHAT-02): a slow/stalled annotation at 8s/20s (`StallDetector`),
and ChatProvider's **180s send watchdog** which force-releases `isSending` and surfaces
"Response took too long. Try again." (recoverable — the next send works).

- `suspend_agent_stream` — SIGSTOP the agent process so it emits no events; `durationMs`
  (default `190000`, just past the 180s watchdog; capped at `300000`) auto-resumes it, so
  a forgotten resume can never wedge the agent.
- `resume_agent_stream` — SIGCONT immediately (early clear).

Both are non-production only (`AppBuild.isNonProduction`). Recipe (drive against a named
test bundle's automation port):
```bash
cd desktop/macos
# 1. start a chat turn so a send is in flight
./scripts/omi-ctl action ask query="write a long detailed answer" &
sleep 2
# 2. freeze the agent stream past the 180s watchdog
./scripts/omi-ctl action suspend_agent_stream durationMs=190000
# 3. within <=180s the send watchdog fires: assert the error + that sending is released
sleep 185
./scripts/omi-ctl action main_chat_snapshot | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]; print("error:", d.get("has_error"), d.get("error_message")); print("is_sending:", d.get("is_sending"))'
#   expect has_error=true / "Response took too long…" and is_sending=false (recoverable)
# 4. resume + prove recovery with a fresh turn
./scripts/omi-ctl action resume_agent_stream
./scripts/omi-ctl action ask query="are you back?"   # succeeds — not blocked by the stale send
```
`suspend_agent_stream` returns `{suspended:true, pid, durationMs}` (or an `error` if no
agent process is running / on a prod bundle).

### 2f. Inject a server push mid-drag (task requery suppression, TASK-06)
A server push arriving while a task drag/sort-sync is in flight must not clobber the
in-flight order — the Tasks view model holds `suppressDatabaseRequery` during that
window so a recompute recomputes from the in-memory drag order instead of re-reading
stale rows from SQLite. `inject_requery_during_drag` (non-prod) drives the **real**
`recomputeAllCaches` path under a simulated drag and reports the outcome:

```bash
cd desktop/macos
# optional: seed some tasks first so the order snapshot is non-trivial
./scripts/omi-ctl action seed_tasks count=8
./scripts/omi-ctl action inject_requery_during_drag | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]; print(d)'
#   assert: requery_suppressed_during_drag=true  (the server-push recompute did NOT re-read SQLite)
#   control: requery_fires_without_suppress=true  (same push with the flag cleared DOES requery)
```
A suppressed requery is exactly why the in-memory drag order stays on screen instead of
a stale SQLite re-read clobbering it — so `requery_suppressed_during_drag=true` is the
TASK-06 assertion; the control proves the guard is load-bearing. The action **forces the
filtered-requery branch** internally, so the assertion is never vacuous even with no user
filter active; it polls the requery counter (no fixed sleeps) for a deterministic signal.
The Tasks page no longer exposes user filters (the popover was replaced by the
mobile-parity completed toggle), so the forced branch is the only way the requery
path arms; `requery_fires_without_suppress=true` confirms the injected push *would*
have requeried without the drag guard. Non-production bundles only.

### 2g. Inspect the feedback payload without submitting (SET-02)
`FeedbackView.submitFeedback()` always fires a real Sentry event and attaches the app log
plus a `desktop_diagnostics.json`, so there's no way to verify the payload is token-free
without spamming Sentry. `dump_feedback_payload_dryrun` (non-prod only) assembles the
**same** payload — the report title (`feedbackReportTitle`) and the diagnostics JSON
(`writeDiagnosticsAttachment`, the exact builder the real submit uses) — and returns it
**without** calling `SentrySDK`, so the diagnostics JSON can be secret-scanned.

```bash
cd desktop/macos
./scripts/omi-ctl action dump_feedback_payload_dryrun message="mic dropped mid-call" \
  | python3 -c 'import json,sys,re; d=json.load(sys.stdin)["result"]["detail"]; \
assert d["sentry_capture_invoked"]=="false" and d["would_submit_to_sentry"]=="false"; \
dj=d["diagnostics_json"]; \
pats=[r"eyJ[A-Za-z0-9_-]{10,}",r"AIza[0-9A-Za-z_-]{10,}",r"omi_(auto|mcp)_[0-9a-f]{8,}",r"AMf-[A-Za-z0-9_-]{10,}",r"[Bb]earer\s+\S{12,}",r"(?i)_API_KEY\s*[=:]\s*\S+"]; \
hits=[p for p in pats if re.search(p,dj)]; \
print("title:", d["sentry_message"]); print("secret hits:", hits or "NONE")'
```
Assert `sentry_capture_invoked=false`, `would_submit_to_sentry=false`, and **no secret
hits** in `diagnostics_json`. Empty `message` yields the "User Report (logs only)" title.
The action returns the log only as **metadata** (`log_attachment_filename`/`_exists`/`_bytes`) —
never its contents — so the bridge response itself can't leak the raw log. To confirm no
Sentry event fired, check the app log has no "User report submitted to Sentry" line.

### 2h. Prove /state survives a wedged main thread (bridge responsiveness)
`GET /state` refreshes live UI fields on the MainActor. If the main thread is wedged
(e.g. a sign-in Keychain read blocking on `SecItemCopyMatching`), that hop used to hang
the whole bridge — `curl /state` timed out with 0 bytes. `liveAutomationSnapshot()` now
bounds the hop (`awaitWithTimeout`, 3s) and falls back to the last cached snapshot with
`snapshotStale=true`, so `/state` always answers. `debug_block_main_thread` (non-prod)
wedges the main thread on demand so this is testable:
```bash
cd desktop/macos
# wedge the main thread for 8s, then /state must still answer (stale) within ~3s
./scripts/omi-ctl action debug_block_main_thread durationMs=8000
./scripts/omi-ctl state | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]; print("stale:", d.get("snapshotStale"))'
#   expect snapshotStale=true during the wedge (cached fallback), false again once it clears
```
Typed flow: `scripts/omi-harness run e2e/flows/bridge-state-wedge-fallback.yaml --lane bridge`.
Hermetic ratchet for the timeout itself: `xcrun swift test --package-path Desktop --filter AwaitWithTimeoutTests`.

### 2i. Prove Quit & Reopen relaunches the same bundle, session intact (PERM-06)
The permission "Quit & Reopen" flow (shown after granting Accessibility / Screen Recording)
calls `AppState.restartApp()` — relaunch the same bundle, keep the auth/onboarding session.
`quit_and_reopen` (non-prod) triggers that exact path (not the onboarding-mutating
`reset_onboarding`), delayed so the action's HTTP response flushes before the process
terminates. The relaunch is `open <bundle>` and drops argv/env — but on non-prod builds
`restartApp()` re-passes `--automation-port=<current port>` as an argv, so the reopened
app **rebinds the SAME port** you launched with (argv beats any launchd-inherited
`OMI_AUTOMATION_PORT`). Keep polling the original `OMI_AUTOMATION_PORT`; no rediscovery.

Two traps make a naive `wait-ready` lie, so the recipe below guards against both:
- **Wait for a *new* listener pid.** `quit_and_reopen` returns immediately and only
  schedules the restart ~`delay_ms` later; the pre-quit process is still alive and
  answering for ~1s. Poll until the pid *listening on the port* differs from the one
  you captured before, or you'll assert the OLD process's state (false PASS). Track the
  listener via `lsof -tiTCP:$PORT -sTCP:LISTEN`, not `pgrep` — a `pgrep -f` pattern also
  matches the shell running this recipe.
- **Poll with *fresh* `omi-ctl` calls.** The relaunch is a fresh process, so it mints a
  new bridge auth token and writes it to the same port-keyed token file. A single
  long-lived `omi-ctl` process caches the token from its first read, so it would keep
  presenting the *stale* token and 401 forever (false FAIL). Each `./scripts/omi-ctl`
  invocation is a fresh process that re-reads the token file — so loop over separate
  calls, don't reuse one `wait-ready`.
```bash
cd desktop/macos
export OMI_AUTOMATION_PORT=47894           # whatever port you launched the bundle with
BEFORE_PID=$(lsof -tiTCP:$OMI_AUTOMATION_PORT -sTCP:LISTEN 2>/dev/null | head -1)
./scripts/omi-ctl state | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]; print("before", d["bundleIdentifier"], d["isSignedIn"], d["hasCompletedOnboarding"])'
./scripts/omi-ctl action quit_and_reopen        # detail: {"restarting":"true", "bundle_id":…, "relaunch_path":…, "delay_ms":"400"}
# wait for the OLD listener to be replaced by a NEW one on the SAME port (fresh omi-ctl each try)
for i in $(seq 1 60); do
  PID=$(lsof -tiTCP:$OMI_AUTOMATION_PORT -sTCP:LISTEN 2>/dev/null | head -1)
  if [ -n "$PID" ] && [ "$PID" != "$BEFORE_PID" ] && ./scripts/omi-ctl state >/dev/null 2>&1; then break; fi
  sleep 1
done
./scripts/omi-ctl state | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]; print("after", d["bundleIdentifier"], d["isSignedIn"], d["hasCompletedOnboarding"], d["bridgePort"])'
#   assert: same bundleIdentifier, isSignedIn=true, hasCompletedOnboarding=true, bridgePort=47894 (session intact, SAME port)
# the reopened process's own argv carries the re-passed port (proves the fix):
#   ps -o command= -p "$(lsof -tiTCP:$OMI_AUTOMATION_PORT -sTCP:LISTEN | head -1)"  → …/Omi Computer --automation-port=47894
```
Hermetic ratchets: `xcrun swift test --package-path Desktop --filter QuitAndReopenActionTests`
and `--filter RestartRelaunchCommandTests` (non-prod relaunch re-passes the port as argv).

### 2j. Prove the chat usage limiter is deterministic + dev-resettable (CHAT-05)
The free-tier monthly chat limiter (`FloatingBarUsageLimiter`, 30 messages/month) is
deterministic and dev-resettable. Driving it to the limit through real chat would burn
LLM calls, so two non-prod bridge actions expose the counter directly: `usage_limiter_snapshot`
(read `is_limit_reached` / `remaining_queries` / `limit_description`) and `reset_usage_limiter`
(reset the counter). No LLM spend. Note: `reset_usage_limiter` is the sign-out-style
`FloatingBarUsageLimiter.reset()` — it clears the cached quota **and** cached-plan state
(and its `UserDefaults` key) on the non-prod bundle; the next subscription poll repopulates
it. Assert on `is_limit_reached` (not `remaining_queries`, which reads `Int.max` when no
quota is loaded).
```bash
cd desktop/macos
./scripts/omi-ctl action usage_limiter_snapshot   # {"is_limit_reached":…, "remaining_queries":…, "limit_description":…}
./scripts/omi-ctl action reset_usage_limiter      # {"reset":"true","is_limit_reached":"false","remaining_queries":…}
./scripts/omi-ctl action usage_limiter_snapshot   # assert is_limit_reached=false after reset (dev-resettable proven)
```
Hermetic ratchets: `xcrun swift test --package-path Desktop --filter FloatingBarUsageLimiterTests`
(deterministic counter + `testResetClearsLimitReachedState`) and `--filter UsageLimiterActionTests`
(the non-prod actions wire to the limiter and the reset is prod-gated).

### 2k. Prove rapid reorders coalesce through the 500ms debounce (TASK-05)
`reorder_task` flushes the sortOrder sync by default (deterministic SQLite reads for
CRUD recipes) — which *hides* the debounce under test. Pass `flush=false` to leave the
production 500ms debounce running: rapid calls must coalesce into exactly ONE
`TasksVM: Synced N sort orders` log line, with no lost update.
```bash
cd desktop/macos
./scripts/omi-ctl action seed_tasks count=5 prefix=T05x      # note the returned ids
OMI_LOG_PATH="$(./scripts/omi-ctl log-path)"
MARK="T05-$(date +%s)"; echo "$MARK" >> "$OMI_LOG_PATH"
# three reorders inside one debounce window (each returns immediately, flushed=false)
./scripts/omi-ctl action reorder_task id=<id1> index=0 category=nodeadline flush=false
./scripts/omi-ctl action reorder_task id=<id2> index=1 category=nodeadline flush=false
./scripts/omi-ctl action reorder_task id=<id3> index=2 category=nodeadline flush=false
sleep 2   # > 500ms debounce + sync
awk "/$MARK/{f=1} f" "$OMI_LOG_PATH" | grep -c 'TasksVM: Synced'   # assert exactly 1
./scripts/omi-ctl action dump_tasks limit=5000                 # assert final order persisted (no lost update)
```
Hermetic ratchets: `--filter HardeningSeamActionTests` (flush param wiring) and
`--filter Task03ReorderStressTests` (150-reorder collision-free/deterministic property).

### 2l. Prove post-wake restart paths without sleeping the machine (CHAT-07)
`simulate_system_wake` (non-prod) posts `NSWorkspace.didWakeNotification` on the
**workspace** notification center — the top of the real wake chain. Every production
consumer then fires exactly as on a physical wake: `RealtimeHubController` re-warms
(or defers) its session, and AppState re-broadcasts the default-center
`.systemDidWake` downstream. (Posting only `.systemDidWake` would silently miss
RealtimeHub, which observes the workspace center directly.) The stray-turn_end half
of CHAT-07 is the CHAT-02 suspend/resume path (a SIGSTOP'd agent across a "sleep" is
the same stale-subprocess class) — already runtime-proven; see §2e.
```bash
cd desktop/macos
OMI_LOG_PATH="$(./scripts/omi-ctl log-path)"
MARK="C07-$(date +%s)"; echo "$MARK" >> "$OMI_LOG_PATH"
./scripts/omi-ctl action simulate_system_wake     # {"posted":"NSWorkspace.didWakeNotification"}
sleep 2
awk "/$MARK/{f=1} f" "$OMI_LOG_PATH" | grep -E 'System woke from sleep|system_wake'
#   assert: "System woke from sleep" (AppState observer ran) AND a RealtimeHub system_wake line —
#   either "re-warming idle session" or "deferring system_wake ..." (defer while mid-turn). With no
#   warm session yet, requestSessionRefresh no-ops by design (guard session != nil); warm one first
#   with a ptt_test_burst if you need the re-warm line specifically.
```
Hermetic ratchet: `--filter HardeningSeamActionTests` (action posts the real top-of-chain
signal on the workspace center, non-prod gated).

### The full loop
```bash
cd desktop/macos
OMI_APP_NAME="omi-myfeature" ./run.sh &                 # build + launch once
./scripts/omi-auth-seed.sh com.omi.omi-myfeature tmp/desktop-auth.json "/Applications/omi-myfeature.app"  # after install; relaunch to apply
./scripts/omi-settings-seed.sh com.omi.omi-myfeature    # copy shortcuts/settings from Omi Dev
./scripts/omi-ctl wait-ready
./scripts/omi-ctl navigate memories                      # jump to the screen you changed
agent-swift connect --bundle-id com.omi.omi-myfeature    # then drive/inspect with agent-swift
agent-swift snapshot -i --json
```
After a code change, an incremental `xcrun swift build` + relaunch is fast — the slow parts (login, navigation) are gone. For pure visual checks without launching at all, SwiftUI snapshot tests are an option, but most pages are entangled with `AppState.shared`/Firebase singletons, so the live-app bridge loop above is usually the better path.

## How to Explore the App

You can interact with the running app via `agent-swift` — a CLI that clicks elements, reads the accessibility tree, and captures screenshots through the macOS Accessibility API. Works with any macOS app, no app-side instrumentation needed.

### Setup
```bash
# App must be running via ./run.sh from desktop/macos/
agent-swift doctor                                   # check Accessibility permission
agent-swift connect --bundle-id com.omi.desktop-dev  # connect to Omi Dev
agent-swift snapshot -i --json                       # see what's on screen
```

### Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `snapshot -i --json` | See all interactive elements with refs, types, labels | `agent-swift snapshot -i --json` |
| `click @ref` | CGEvent click — SwiftUI elements (NavigationLink, gestures) | `agent-swift click @e3` |
| `press @ref` | AXPress — AppKit buttons, Settings sidebar items | `agent-swift press @e5` |
| `find role/text/key VALUE` | Find element and chain action | `agent-swift find text "Settings" click` |
| `fill @ref "text"` | Type into text field | `agent-swift fill @e7 "search"` |
| `scroll down/up` | Scroll current view | `agent-swift scroll down` |
| `wait text "X"` | Wait for element to appear | `agent-swift wait text "Loading" --timeout 5000` |
| `is exists @ref` | Assert element exists (exit 0/1) | `agent-swift is exists @e3` |
| `get PROP @ref` | Read property value | `agent-swift get value @e5 --json` |
| `screenshot PATH` | Capture app window | `agent-swift screenshot /tmp/screen.png` |

**Key rules:**
- `click` = CGEvent mouse click (SwiftUI). Use for main sidebar icons, NavigationLink.
- `press` = AXPress action (AppKit). Use for Settings sidebar sections.
- Refs go stale after any mutation — always re-snapshot before the next interaction.
- `find` with chained action is more stable than hardcoded `@ref` numbers.
- `--json` flag on any command gives structured output for parsing.

## App Navigation Architecture

### Screen Map
```
Main Window
├── Sidebar (SidebarView.swift) — use `click`
│   ├── Home (DesktopHomeView.swift)
│   ├── Conversation (ChatSessionsSidebar.swift)
│   ├── brain → Memories
│   ├── checklist → Action Items
│   ├── puzzlepiece.fill → Integrations
│   └── gearshape.fill → Settings
│
└── Settings (SettingsPage.swift) — use `press` for sidebar sections
    ├── General — app preferences
    ├── Rewind — screenshot/timeline settings
    ├── Transcription — Language Mode (Auto-Detect / Single Language)
    │   └── Language picker (popupbutton or button)
    ├── Notifications — alert preferences
    ├── Privacy — data settings
    ├── Account — user info
    ├── AI Chat — chat model settings
    ├── Advanced — developer options
    └── About — version info

System Tray Menu
├── openOmi — Open Omi
├── checkFor — Check for Updates
├── resetOnb — Reset Onboarding
├── reportIs — Report Issue
├── signOut — Sign Out
└── quitApp — Quit
```

### Interaction Patterns

**Main sidebar navigation:**
- Icons are `image` type elements with accessibility identifiers: `sidebar_dashboard`, `sidebar_chat`, `sidebar_memories`, `sidebar_tasks`, `sidebar_rewind`, `sidebar_apps`, `sidebar_settings`
- Use `find key sidebar_dashboard click` for reliable navigation (survives UI changes)
- Keyboard shortcuts: Cmd+1 (Dashboard), Cmd+2 (Conversations), Cmd+3 (Memories), Cmd+4 (Tasks), Cmd+5 (Rewind), Cmd+6 (Apps), Cmd+, (Settings)
- Use `click` — these are SwiftUI views with onTapGesture

**Settings sidebar navigation:**
- Sections are `button` type elements with section name labels
- Use `press` — these are SwiftUI Button views that respond to AXPress

**Transcription language mode:**
- Two radio-button-style options: "Auto-Detect Multi-Language" and "Single Language Better Accuracy"
- `click` on the text to switch modes
- Single Language mode shows a language picker (`popupbutton`)
- Click popupbutton → menu items appear as `menuitem` elements

**System tray menu:**
- Menu items have `identifier` prefixes for detection
- Access via `snapshot --json` (includes menu bar items)

## Known Flows

Reference flows in `desktop/macos/e2e/flows/*.yaml` describe the app's key user journeys. Read these to understand navigation paths, expected elements, and UI state at each step.

| Flow | Covers | Steps | Report |
|------|--------|-------|--------|
| `flows/navigation.yaml` | SidebarView, DesktopHomeView | 6/6 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/RVS7NChPvj.html) |
| `flows/dashboard.yaml` | DashboardPage, GoalsWidget, TasksWidget | 3/6 (3 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/ghCdGIUAA2.html) |
| `flows/chat-hermetic.yaml` | ChatPage, ChatProvider | 5/5 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/z62Nll0IzR.html) |
| `flows/memories.yaml` | MemoriesPage, MemoryGraphPage | 5/6 (1 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/Mkp6ahc12I.html) |
| `flows/tasks.yaml` | TasksPage, TasksStore | 4/5 (1 skipped) | [report](https://flow-walker.beastoin.workers.dev/runs/ealB_-UdqS.html) |
| `flows/settings-basic.yaml` | SettingsPage, SettingsSidebar | 9/9 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/RoTW8GeljN.html) |
| `flows/language.yaml` | SettingsPage, SettingsSidebar | 5 steps | — |
| `flows/rewind.yaml` | RewindPage | 4/4 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/1HE5OsPOOy.html) |
| `flows/apps.yaml` | IntegrationsPage | 6/6 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/VDGw-wbHqa.html) |
| `flows/refer-external.yaml` | Profile menu → affiliate URL | 3/3 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/Jz8ymviOy1.html) |
| `flows/screen-recording-permission.yaml` | RewindPage, ScreenCaptureService, PermissionsPage | 7/7 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/3WoXUG6xkT.html) |
| `flows/audio-recording.yaml` | ConversationsPage, AudioCaptureService, AppState | 7/7 PASS | [report](https://flow-walker.beastoin.workers.dev/runs/UdkzB-dYG_.html) |

When you modify a Swift file, check if any flow's `covers:` includes it. That flow describes the user journey your change affects.

### Adding a New Flow
Create `desktop/macos/e2e/flows/<name>.yaml` in v2 format:
```yaml
version: 2
name: my-flow
description: What this flow covers
app: com.omi.computer-macos
covers:
  - desktop/Desktop/Sources/path/to/YourView.swift
preconditions:
  - auth_ready
steps:
  - id: S1
    name: Step description
    do: "Click the element (identifier: my_element). Verify the page loads."
    expect:
      interactive_count: { min: 5 }
      text_visible:
        - Expected Text
```
**Important:** Always use quoted strings for `do:` fields (not YAML `>` or `|`).

## Verification & Evidence

After making changes, verify them in the live app:
1. Navigate to the affected screen using the commands above
2. Check that your changes appear (snapshot, screenshot)
3. Test interactions (click buttons, fill fields, scroll)
4. Capture evidence: `agent-swift screenshot /tmp/evidence.png`
5. Generate video: `ffmpeg -framerate 1 -pattern_type glob -i '/tmp/e2e-*.png' -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1" -c:v libx264 -pix_fmt yuv420p /tmp/report.mp4`

## Decision Tree

| Problem | Solution |
|---------|----------|
| Element not found | Re-snapshot, try scrolling, check if on wrong screen |
| Click doesn't navigate | Try `press` instead (Settings sidebar = `press`, main sidebar = `click`) |
| Picker not responding | SwiftUI Picker `.menu` style may not expose as `popupbutton` — look for `button` with value label |
| App seems frozen | Check `agent-swift status --json`, re-connect, check `./scripts/omi-ctl log-path` |

## Guard Conditions

**NEVER:**
- Kill or restart the production Omi app
- Enable the automation bridge or seed auth on the production bundle (`com.omi.computer-macos`) — both are gated to non-production builds; keep it that way
- Modify source code to make tests pass — report the failure instead

**When validating auth or onboarding themselves, or running flow-walker E2E:** drive the real flows — do NOT use the seeded-auth / `hasCompletedOnboarding` fast-path, which exists only for iterating on *other* screens. The beta app (`com.omi.computer-macos`) is the standard target for flow-walker E2E testing; the dev app (`com.omi.desktop-dev`) and named `omi-*` bundles are for local development only.
