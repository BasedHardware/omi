# V1: one live Flutter process per mobile session

Status: executable contract; Harness V1 implements the skeleton in
`dev_harness/live_session.py`. Existing start/stop behavior is unchanged until
that builder lands. `mobile-session live <start|reload|restart|screenshot|logs|controls|status|stop> <id>`
and `mobile-verify fast --session <id> ...` currently refuse with exit 2.
See [pending tests](PENDING_CONTRACTS.md). No new product architecture is decided here.

## Ownership and lifecycle

A Python broker owns exactly one `flutter run --machine --debug --flavor dev`
child, under the existing session sentinel and process-manifest ownership
checks. The CLI starts the marker-bearing broker with `start_new_session=True`,
stdin `/dev/null`, and private session log files. Broker owns Flutter pipes;
CLI exit does not close them. Reuse `supervise`/`owned_child` and
`safety.validate_owned_pid`; never identify a process by PID alone or `pgrep`.
Keep lease.owner as the acquiring CLI identity (the existing dead-owner rule
permits later CLI calls); broker identity belongs in the process manifest,
not lease.owner. The typed `BrokerIdentity` and `stop_owned_broker` bind
termination to the full observed identity. Record generation, random process marker, boot identity,
PID/start identity, canonical worktree, device, and socket path in live.json.

The session directory and Unix socket are user-private (0700/0600). Use a
short socket pathname in a user-private temp directory when the state root
exceeds AF_UNIX's limit; live.json records the path and session marker.
Validate sentinel, host/user, lease generation, and broker marker on every
connection. Wrong generation is stale even if the PID answers. An O_EXCL
session startup claim prevents duplicate brokers; the existing offset claim
remains the port authority. A second start returns current status only after
an identity handshake, otherwise refuses. No blind socket unlink or PID kill.

`stop` stops live broker/app before services or deleting devices. `reset` first
stops live app, then resets fixtures (cannot leave old auth running). `release`
uses stop and only then frees claims/state; unresolved process ownership blocks
cleanup. `recover` stops a provably owned old broker/child before bumping the
lease generation; it does not adopt a still-running app with old evidence.
`live stop` leaves services and device allocated; all stop paths are idempotent.
A crash/EOF or operation deadline marks the live state blocked and invalidates
readiness. Never replay a mutation after ambiguous delivery. `status` uses a
bounded handshake, not heartbeat age alone. After host restart boot identity
mismatch blocks; explicit recover clears proven-dead state, then live start
builds afresh. Foreign host/user/PID-marker mismatch always refuses.

## Wire and operation semantics

`decode_request` is the broker admission boundary. Client/broker is one newline
JSON request and response per connection, bounded
at 1 MiB and a deadline (default 30 s; start 300 s). Request/response schema:
`contracts/live/live-session-v1.schema.json` beside this note. One request id,
one response, exact session/generation/id match; unknown fields/ops refuse.
Broker-to-Flutter uses **one-element JSON arrays per line**, numeric ids,
`app.start`, `app.debugPort`, `app.started`, `app.log`, `app.stop` events. Keep
reading events while awaiting a matching response; noise and another id never
complete a request. EOF, malformed protocol, wrong app id, or deadline blocks.

`reload` sends `app.restart` with `fullRestart:false,pause:false`; `restart`
sends `fullRestart:true`. Only matching `{result:{code:0,message:...}}` plus
fresh semantic readiness is success. Nonzero code is rejected (exit 1), missing
code/error is blocked (2); never infer success from compilation/progress/logs.
Do not automatically restart on rejection. Native/assets/dependency/defines/SDK
input changes require a **cold live stop/start** (restart-required, exit 2),
not a hot restart. All other source changes must be loaded and rechecked before
readiness advances. A change during the operation blocks evidence attribution.

`controls` accepts only capabilities/state/wait_ready/navigate/fault, with the
existing v1 parameters; calls `app.callServiceExtension` for **`ext.omi.controls.*`**.
The installed Dart SDK rejects registration names without `ext.`. Current app
registrations omit it and would throw when enabled: the App UI owner must
repair this prerequisite before V1 can claim live readiness. Do not support the
invalid names as a fallback. Flutter discovers the current isolate each call. No arbitrary VM RPC, eval,
raw URI, or shell command is accepted. Check capabilities/version/profile first.
`logs` returns a bounded sanitized tail/cursor of this app's events; never
persist the VM auth URI, credentials, raw stderr or arbitrary control payloads
in shareable evidence. `screenshot` calls simctl/adb for the exact lease device,
writing a broker-assigned PNG under the session directory, then hashes it.
`status` reports starting/ready/busy/blocked/stopped and build/source identity;
app.started alone is not ready. For readiness require state profile `localDev`,
contract `semantic-controls/v1`, signedIn+routed+captureIdle all true and fixture
principal uid equal to the lease. Missing extension closes admission.

All state-changing operations, including controls navigate/fault and a verify
run, share one nonblocking mutation lock; second mutation gets busy (2), never
queues into Flutter's debounce queue. Screenshot also takes that lock so it
cannot capture an intermediate frame. Status/logs stay available during a
mutation. Stop cancels/blocks an in-flight request and then drains/tears down;
no completed-success receipt may follow stop. Never retry an operation id.

## Isolation, safety, and evidence

One canonical worktree per live session (claim it); reject sharing its app build
outputs. Session device must be exclusively leased; use session-owned AVDs on
Android, not a shared template instance. Derived/build data belongs to that
worktree or session. Shared package caches are fine. SDK startup may serialize
on Flutter's own lock; never delete/bypass that lock or hold a second global
lock across the resident process. Warm the pinned SDK before timing reloads.
VM host ports use OS-assigned loopback ephemeral ports (host-vmservice-port=0,
DDS disabled); the broker needs no new fixed TCP port or offset allocation.

Validate **before spawn and every operation**: exact dev/local_dev/debug with
OMI_DEV_CONTROLS=1, correct app id, session endpoints, generated build config and
empty/loopback `.dev.env`. No caller-provided launch args/environment overlay.
Use existing mobile build validator and fail-closed dev-control predicate;
local_prod, mobile_beta, prod, profile/release, missing opt-in all refuse.
First PR supports simulator/emulator only; physical transport/egress rules are
Spine B's work. Host loopback is not emulator loopback: Android uses session
scoped `adb -s <id> reverse` mappings and removes only its recorded mappings.

Before freeze V8 adds optional `live` to root `contracts/session/` evidence.
Top-level source/artifact retain their **cold build** meaning (do not relabel
APK bytes after reload). `live.loaded_source` binds the last successfully loaded
code; `live.requested_source` binds attempted edits; both add input SHA256 over
sorted path+content+mode of all app inputs, including untracked nonignored files.
Use a separate restart-input digest over native/assets/dependencies/config/SDK.
Include git SHA + dirty digest for attribution, but don't rely on the legacy
dirty digest alone (it doesn't hash untracked contents). Recheck inputs after
operations. `live` records generation, operation id/name/outcome, daemon code,
UTC start/end, elapsed ms, loaded sequence, restart digest, and screenshot
path/hash when applicable. Errors never advance loaded_source/sequence.
Each attempt gets an atomic immutable `operations/<id>/evidence.json`; update
session evidence.json atomically afterward. No operation count masquerades as
journey counts. Failed/refused attempts are not passing journeys.

## Verify attachment and first-PR boundary

Explicit `fast --session` attaches; absent flag preserves the hermetic lane.
Resolve normal path selection first (unknown filter remains exit 65). Refuse
stale generation/source/input digest, missing cold artifact, wrong profile,
unready state, unsupported selected journey, or zero execution; no cold fallback.
V1 ships **no supported live journeys**: after selection/admission it refuses
with exit 2 naming the selected journeys and missing adapter. The current
`integration_test` Dart programs run in a test binding; they cannot attach to
an arbitrary resident `flutter run` app. Do not duplicate their assertions in
Python or count controls/screenshot operations as journey execution. B1 adds
addressability but does not provide this adapter. A later reviewed package must
extract a shared executable journey specification and host driver, with the
same positive/negative oracles, before any live journey is advertised. Until
then the regular hermetic `fast` lane is the executable journey authority.
The reserved adapter holds the mutation lease for the full run and uses the
existing per-journey receipt accounting; no arbitrary Dart-execution extension.

Out of scope: B1 routes/keys/v2 controls, singleton/API/analytics migrations,
physical phones, auto-restart/retry, arbitrary evaluation, full UI catalog,
and claiming the <3 s target from fake tests. Measure real edit-to-visible on
both platforms separately; hermetic protocol tests cannot prove latency.
Rejected: CLI-owned pipes (die with CLI), independent VM clients (split ordering
and isolate ownership), silent cold fallback (hides the feedback-loop failure),
and pid-only recovery (can kill an unrelated process).

Protocol source: Flutter 3.44.5 `packages/flutter_tools/lib/src/commands/daemon.dart`
(AppDomain restart/callServiceExtension), and its bundled Dart SDK
`lib/developer/extension.dart:109` (mandatory `ext.` prefix). Checked locally,
without booting a simulator.
