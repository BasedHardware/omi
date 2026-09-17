# V1: one live Flutter process per mobile session

Status: executable contract; Harness V1 implements the skeleton in
`dev_harness/live_session.py`. Existing start/stop behavior is unchanged until
that builder lands. `mobile-session live <start|reload|restart|screenshot|logs|controls|status|stop> <id>`
and `mobile-verify fast --session <id> ...` currently refuse with exit 2.
[Pending tests](PENDING_CONTRACTS.md).

## Ownership and lifecycle

A detached Python broker owns one `flutter run --machine --debug --flavor dev`
child and its pipes; CLI stdin is `/dev/null`, logs are session-private. Keep
lease.owner unchanged. Store broker AND child `BrokerIdentity` (host/user, boot,
PID/start, marker, generation, worktree/session) in `live.json`, never the service
manifest: `validate_owned_pid` only knows service PIDs and `cmd_down` kills them.
Reuse sentinel/lease checks, but probe live identities separately and pass them
to `stop_owned_broker`; PID alone or heartbeat age never authorizes a signal.

The session directory and Unix socket are user-private (0700/0600). Use a short private socket path recorded in live.json.
Validate sentinel, host/user, lease generation, and broker marker on every
connection. Wrong generation is stale even if the PID answers. An O_EXCL
session startup claim prevents duplicate brokers; the existing offset claim
remains the port authority. Second start requires an identity handshake; no blind socket unlink or kill.

`mobile-session stop/release`: live teardown, then `cmd_down`, then device detach,
then lease/claims cleanup (existing stop currently detaches too early). `recover`:
live teardown, `cmd_down`, then generation bump; keep the allocated device.
`reset`: live teardown then existing reset/reseed path. `live stop` preserves
services/device. Direct harness `down` owns only services; loss of readiness
blocks live mutations until explicit recovery. Teardown must confirm broker and
child death before returning; ambiguous identity blocks ALL later cleanup.
Use graceful `app.stop`, then bounded owned-group termination if unresponsive;
never replay an ambiguously delivered mutation. After reboot, recover clears
provably dead live identities before starting afresh. Foreign identities refuse.

## Wire and operation semantics

`decode_request` is the broker admission boundary. Client/broker is one newline
JSON request and response per connection, bounded
at 1 MiB and an operation deadline (default 30 s, maximum 300 s).
Start is NOT this wire operation: CLI waits at most 10 s for broker handshake,
then reports `starting`; broker allows 900 s for app readiness (constructor
`startup_timeout_s`, bounded 1–1800 s), covering the measured 412 s cold iOS boot.
Status remains responsive during compilation. Request/response schema:
`contracts/live/live-session-v1.schema.json` beside this note. One request id,
one response, exact session/generation/id match; unknown fields/ops refuse.
Broker-to-Flutter uses **one-element JSON arrays per line**, numeric ids,
`daemon.connected` first, then `app.start` before run/compile, `app.debugPort`,
optional devTools/dtd events, and `app.started` only after app readiness.
Do not wait for stdin before accepting startup events. Keep
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
B0's registration repair is a prerequisite for real readiness; never fall back
to invalid names. Restart's `result` is `{code,message}`; callServiceExtension's
`result` is the extension map itself (Omi's custom registration adds no wrapper).
Decode each by operation, never apply a second generic `result` unwrap. Flutter discovers the current isolate each call. No arbitrary RPC/eval/shell; check capabilities/version/profile first.
`logs` returns a bounded sanitized tail/cursor of this app's events; never
persist the VM auth URI, credentials, raw stderr or arbitrary control payloads
in shareable evidence. `screenshot` calls simctl/adb for the exact lease device,
writing a broker-assigned PNG under the session directory, then hashes it.
`status` reports starting/ready/busy/blocked/stopped and build/source identity;
app.started alone is not ready. For readiness require state profile `localDev`,
contract `semantic-controls/v1`, signedIn+routed+captureIdle all true and fixture
principal uid equal to BOTH seeded lease.default_auth_uid and seed.json.uid,
with matching fixture_version and status=seeded; missing/mismatched seed blocks.
Live/simulator lanes use the real isolated uvicorn/emulator/redis session stack,
with offline providers. Require opt-in `make setup-backend` (or existing owner
setup) before start; doctor refuses missing uvicorn. Do not install backend in
lane-bootstrap or substitute journeys' fixture server for real session seeding.

All state-changing operations, including controls navigate/fault and a verify
run, share one nonblocking mutation lock; second mutation gets busy (2), never
queues into Flutter's debounce queue. Screenshot also takes that lock so it
cannot capture an intermediate frame. Status/logs remain available. Stop cancels/blocks an in-flight request and then drains/tears down;
no completed-success receipt may follow stop. Never retry an operation id.

## Isolation, safety, and evidence

One canonical worktree per live session (O_EXCL claim it); a second live session
on that same worktree refuses `worktree-busy` before spawning. Session device must be exclusively leased; use session-owned AVDs on
Android, not a shared template instance. Derived/build data belongs to that
worktree or session. Shared package caches are fine. SDK startup may serialize
on Flutter's own lock; never delete/bypass that lock or hold a second global
lock across the resident process.
VM host ports use OS-assigned loopback ephemeral ports (host-vmservice-port=0,
DDS disabled); the broker needs no new fixed TCP port or offset allocation.

Validate **before spawn and every operation**: exact dev/local_dev/debug with
OMI_DEV_CONTROLS=1, correct app id, session endpoints, generated build config and
empty/loopback `.dev.env`. No caller-provided launch args/environment overlay.
Use existing build validation;
local_prod, mobile_beta, prod, profile/release, missing opt-in all refuse.
Device launch follows the broker PR; Android needs owned `adb reverse` mappings,
not host-loopback assumptions. Physical transport is Spine B’s work.

Before freeze V8 adds optional `live` to root `contracts/session/` evidence.
Top-level source/artifact retain their **cold build** meaning (do not relabel
APK bytes after reload). `live.loaded_source` binds the last successfully loaded
code; `live.requested_source` binds attempted edits; both add input SHA256 over
sorted path+content+mode of all app inputs, including untracked nonignored files.
Use a separate restart-input digest over native/assets/dependencies/config/SDK.
Recheck inputs after operations; legacy dirty_digest omits untracked contents. `live` records generation, operation id/name/outcome, daemon code,
UTC start/end, elapsed ms, loaded sequence, restart digest, and screenshot
path/hash when applicable. Errors never advance loaded_source/sequence. Schema-only validation is NOT
acceptance: `session_evidence.validate_evidence` always calls
`live_session.validate_live_evidence`. This normative boundary checks traversal
(including symlinks at write), dev/local_dev, successful loaded=requested identity,
code=0 for successful reload/restart, non-null loaded identity for any success,
and chronology. V8 freezes structure plus these semantics, not just JSON Schema.
Each attempt gets an atomic immutable `operations/<id>/evidence.json`; update
session evidence.json atomically afterward. No operation count masquerades as
journey counts. Failed/refused attempts are not passing journeys.

## Verify attachment and first-PR boundary

Explicit `fast --session` attaches; absent flag preserves the hermetic lane.
Resolve normal path selection first (unknown filter remains exit 65). Refuse
stale generation/source/input digest, missing cold artifact, wrong profile,
unready state, unsupported selected journey, or zero execution; no cold fallback.
V1 ships **no supported live journeys**: after selection/admission it refuses
with exit 2 naming the selected journeys and missing adapter. Dart integration tests cannot attach to an arbitrary resident app. Neither B1
addressability nor controls/screenshots provide a journey adapter. A later reviewed package must
extract a shared executable journey specification and host driver, before advertising live journeys. Hermetic `fast` remains the journey authority.
PR 1: fake-backed broker protocol, reload/restart/status/logs/stop, injected
screenshot writer, evidence validation, lifecycle ordering. Accept the builder's
two-day scope estimate, not a promise of real-device completion. Keep real launch
and live-verify adapter pending for subsequent PRs: B0 plus real-stack boot and
startup deadlines must be verified before enabling device start. `verify_live`
is tested to contact the broker after selection, then refuse unsupported journeys;
a pure admission helper is not evidence of attachment. No latency claim, Android
reverse, physical support, or screenshot oracle in PR 1. Measure the <3 s target
on each real platform later. Rejected: CLI-owned pipes, independent VM clients,
silent cold fallback, and pid-only recovery.

Protocol source: Flutter 3.44.5 `packages/flutter_tools/lib/src/commands/daemon.dart`
(AppDomain restart/callServiceExtension), and its bundled Dart SDK
`lib/developer/extension.dart:109` (mandatory `ext.` prefix). Checked locally,
without booting a simulator.
