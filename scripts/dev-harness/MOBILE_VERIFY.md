# Mobile verify — unified fast feedback, selection, and contributor path (SCA-490 / C4)

One command surface over the proven mobile lanes. It never replaces the
canonical journey runner (`app/integration_test/journeys/run_journeys.sh`,
C2) or the session CLI (`mobile-session.sh`, C1) — it selects, admits,
classifies, validates receipts, and writes the lane summary.

```bash
make lane-bootstrap                                 # fresh worktree: cheap gates + app/test.sh
make mobile-verify ARGS="doctor"                    # lane readiness (C1 doctor + verify surface)
make mobile-verify ARGS="select --paths app/lib/pages/chat/page.dart"
make mobile-verify ARGS="fast --paths app/lib/pages/chat/page.dart"   # focused hermetic feedback
make mobile-verify ARGS="fast --all"                # full hermetic suite
make mobile-verify ARGS="fast --filter j2 --runs 5" # deterministic repeat signal
make mobile-verify ARGS="smoke --session oms-<id>"  # bounded simulator smoke (fail-closed)
make mobile-verify ARGS="physical"                  # admission document (always blocked until user-run hardware evidence)
```

Direct form: `scripts/dev-harness/mobile-verify.sh <op> …` (add `--json` anywhere).
Exit codes: `0` pass, `1` test failures (or doctor degraded), `2` blocked —
missing infra/setup/timeout/physical admission, never success, `64` usage,
`65` selection drift.

## Selection is mechanical, fail-closed, and tested

- Journeys are discovered by glob (`j<N>_*_test.dart`) — the runner and this
  selector agree by contract test; a new journey joins the suite by existing.
- A changed path maps to journeys through the rule table in
  `dev_harness/mobile_verify.py` (each rule names the production seam it can
  break). Unknown cross-cutting `app/lib` Dart falls back to the **full suite**;
  an explicit filter matching nothing is **drift** (exit 65), never PASS(0).
- The executable contracts live in `scripts/dev-harness/tests/test_mobile_verify.py`
  (discovery agreement, orphan protection, per-seam selection, receipt
  accounting, failure classification, fail-closed admission) and run in the
  existing `dev-harness-unit-tests` manifest lane (local + CI).

## CI

`mobile-app-checks.yml` runs the **same command** (`fast --all`) in the
`journeys-hermetic` job when `has_app_journeys` is selected — journey
definitions/support, the C3 replay world, dev controls, non-generated
`app/lib` Dart, the evidence contract, or this entrypoint changed. The lane is
loopback-only with synthetic fixtures: no credentials, no devices, no signing —
fork-safe. Receipts upload as the `journey-evidence` artifact on pass AND
failure. Selection is resolved by the shared `scripts/pre_push_ci_prediction.py`
(covered by `test_pre_push_ci_prediction.py`); the lane is deliberately NOT a
pre-push phase.

The same workflow's Android Compile Smoke job (`android-compile-smoke`) builds
`flutter build apk --debug --flavor dev --target-platform android-arm64` and
uploads the APK as `app-dev-debug-<head-sha>` (5-day retention, in-repo debug
keystore, no secrets). Extra ABIs OOM'd `ubuntu-latest` during
`stripDebugSymbols` (`c8f35061fc`); this job does not compile the JNI opus shim
for armeabi-v7a or x86_64. `:app:testDevDebugUnitTest` runs in a parallel
`android-unit-tests` job, not after the APK. Gradle cache writes only on `main`
(`cache-read-only: ${{ github.ref != 'refs/heads/main' }}`). These jobs do not
change `journeys-hermetic` behavior.

## Receipts

Every `fast`/`smoke` run writes `verify-receipt.json` (schema
`mobile-verify/v1`): source git SHA + dirty digest, runner versions
(incl. Flutter), the selection decision, per-journey outcomes validated
against **session-evidence-v1 accounting** (honest counts,
`passed+failed+skipped == executed`; zero-execution never passes; finished ≥
started), totals, and the exact rerun command. The hermetic lane has no built
app artifact — build identity is the source identity + runner versions bound
in this receipt; per-journey `artifact` fields stay C2-owned and are reported
as-is. Skipped, blocked, stale, and zero-test results never equal passed.

## Worked example: verify a chat change end to end

The narrow seam is the chat page (`app/lib/pages/chat/page.dart`) plus the
message provider; the fixture backend mints a distinct ai-role reply; the UI
key is `omi.chat.input`/`omi.chat.send`; the main/error tests are j2's
positive run and its named faults (`suppress-send`, `suppress-assistant-reply`,
`wrong-owner-session`).

```bash
# after editing app/lib/pages/chat/**:
make mobile-verify ARGS="select --paths app/lib/pages/chat/page.dart"
#   -> selects j2_chat_send_assistant_reply_test.dart (rule: chat-page)
make mobile-verify ARGS="fast --paths app/lib/pages/chat/page.dart"
#   exit 0 + verify-receipt.json outcome=passed, or the exact rerun command on failure
```

The hermetic Dart suite and this lane must not depend on the host calendar or
timezone. The CI second timezone pass is the same commands under a forced `TZ`:

```bash
TZ=Pacific/Kiritimati bash app/test.sh
TZ=Pacific/Pago_Pago bash app/test.sh
TZ=Pacific/Kiritimati make mobile-verify ARGS="fast --all"
TZ=Pacific/Pago_Pago make mobile-verify ARGS="fast --all"
```

Do not pass `--evidence-dir` or set `OMI_VERIFY_EVIDENCE_DIR` for the default
local run: an empty env value is treated as unset and receipts go to a temp
dir. A relative `--evidence-dir` (or env value) is resolved against the
invocation working directory and passed to the runner as an absolute path —
never against `app/`, which is only the runner's cwd. CI may still pass
`--evidence-dir` to collect the `journey-evidence` artifact.

Deliberately break it once (arm `suppress-assistant-reply` via the journey
faults) and the lane fails with the missing invariant named — proving the
oracle rejects wrong behavior, not just accepts right behavior.

## Simulator smoke and physical qualification

`smoke` requires a ready C1 session (`mobile-session doctor --platform ios`),
attaches the session's simulator + API base, and runs the same journeys on the
full app. Missing infrastructure exits `2` with the remedy — CI never runs it.
`physical` always reports blocked. The C5 (SCA-491) software lane is
`mobile-session device` plus `scripts/dev-harness/PHYSICAL_DEVICES.md`;
hardware evidence comes only from that trusted device path on provisioned
phones and is reported separately from simulator/hermetic results.

## Live attachment (V1 skeleton)

`fast --session oms-<id>` is reserved for attachment to the owned live broker.
It currently exits 2 (not implemented), with no cold fallback. The existing
flag-free hermetic lane is unchanged. Admission and unsupported-journey rules:
[LIVE_SESSIONS.md](LIVE_SESSIONS.md).
