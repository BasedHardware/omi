# Sentry — crash and handled-error reporting

What Context for Claude reports when it crashes or takes a fail-open path, where it lands, and the
exact boundary of what can leave the Mac. The analytics half (product metrics) is
[`docs/analytics.md`](analytics.md); this file is about *diagnostics*, and the two share nothing —
no project, no SDK, no queue, no identity.

## Where it goes

Sentry project **`omi-nk3/context-for-claude`**, Cocoa platform — the Context for Claude project,
never the Omi desktop app's project. Sharing a project would mix two products' issue streams and
let this app's events be mistaken for the other app's crashes in triage. The project is provisioned
separately from this repository; the SDK integration here activates only when the project's DSN is
configured (below), so an unprovisioned project means reporting that is simply off.

The DSN is public by design: it can only write events into its own project, it reads nothing, and
it is not an API key. It still names the ingest host — which is why every other property of this
integration is written as if the payload were hostile, because the transport reveals at least the
existence of this app, its build, and its source IP to that host.

## Configuration is a release input

The DSN is read from `Bundle.main`'s Info.plist under the **`ContextSentryDSN`** key.
`scripts/build.sh` already injects bundle identity and version into the copied plist with
PlistBuddy; the release pipeline injects this key the same way, from a CI secret. The template
plist in the repo carries no value at all.

There is deliberately **no runtime environment override**. A variable that could arm reporting at
runtime would be a second key that bypasses the shipping and Airgap gates — and `swift test` spent
months POSTing to PostHog because a process nobody considers production looked exactly like the
release. Missing, placeholder, or malformed → `ContextSentryConfig` returns nil → the SDK is never
started: no crash handler, no threads, no cache directory, no startup cost. Nothing else in the app
can arm it.

## Release and dist convention

Every event reports as `context-for-claude@<version>+<build>`, with `dist` set to the numeric
build. `<version>` mirrors the GitHub release tag the pipeline publishes
(`context-for-claude-v<version>`), and `<build>` is the numeric build number
`release-micro-app.sh` derives — so every release is a distinct Sentry release, and `dist` slices
within it. Build identity comes from `CFBundleShortVersionString` / `CFBundleVersion` at start;
components that are missing resolve to `"unknown"` because an event without a release is an event
release filters cannot find.

### Symbolication (plan; not wired in this change)

dSYM upload is **not** part of this change — the release scripts are untouched here. The plan,
for a separate, reviewable change to the release pipeline:

1. `scripts/build.sh` builds with `swift build -c release`; the `.dSYM` bundles land next to the
   binary in `.build/release/`. Add `dsymutil` verification — `dwarfdump --uuid` on each `.dSYM`
   must list the UUID the app binary reports, and the step fails the build if a `.dSYM` is missing
   for the app target (a crash reported by an unsymbolicated build is close to worthless).
2. Upload gated on a CI secret: `sentry-cli upload-dif --project context-for-claude` runs only when
   `SENTRY_AUTH_TOKEN` exists in the environment, keyed to the same release name
   (`context-for-claude@<version>+<build>`) the SDK reports. No token → skip with a loud log, never
   a hard failure — diagnostics must not block a release.
3. Verification without sending events: `sentry-cli difs list` for the release after a staged
   upload, and one deliberately-crashing Developer ID build — the only event ever sent for this
   purpose, from a real crash, checked for symbolicated frames.

Until that lands (and until a signed Mac run has exercised the SDK start), **crash coverage is not
yet verified end to end**; handled-error coverage through the same transport is what the test
suite proves.

## The gates, in order

`ContextSentry.start()` runs once per launch, before analytics start, and every gate is terminal:

1. **Shipping only.** `ContextPaths.isShippingBundle` — dev builds and the test runner never arm.
2. **Valid DSN** — nil means disabled, not degraded.
3. **Verified-clean cache, before anything SDK.** The SDK's cache root
   (`<support>/SentryCache`, inside the app's own `0o700` support directory) is deleted and its
   absence *checked*. If deletion cannot be verified, the process stays disarmed
   (`.cacheWipeFailed`) and a set retirement record stays set.
4. **Airgap Mode off at launch**, read live like every other `NetworkEgress` client.

Duplicate `start()` is a no-op; the first call decides.

## Airgap: drop, never defer

The SDK queues every envelope to disk before sending, re-sends its whole queue at start, after
every send, on flush, and when the network comes back — verified in sentry-cocoa 8.58.0
(`SentryHttpTransport`). `SentrySDK.close()` flushes first; queued sends are async operations that
can start after a purge; and the SDK has no public purge or synchronous transport shutdown. So the
runtime response to flipping Airgap Mode on is, in order:

1. **The admission gate closes** (`ContextSentryGate.enterAirgap()`) — synchronous, memory-only,
   permanent for the process. The SDK's `URLSession` is one this app constructed
   (`Options.urlSession`, the supported seam `SentryTransportFactory` uses for every outgoing
   request) and its protocol stack is `ContextSentryGate`: from this instant, **no new HTTP
   request may start** — queued sends, retries, and every redirect hop included. Requests already
   admitted may complete or be cancelled; the gate's `Decision` keeps that distinction explicit.
   Admission also re-reads live ExclusionEngine suppression per request, so a report refused by
   policy never depends on observer latency.
2. **Retirement is marked** durably — a `UserDefaults` record *outside* the cache subtree the
   purges delete (`ContextSentryRetirement`, flushed via `synchronize()` for the same
   cross-process reason as `RevivalBudget`).
3. On a utility queue: **delete the cache root** (destroys queued envelopes) → **`close()`** the
   SDK (uninstalls the native crash handler; its flush finds a closed gate) → **delete the cache
   root again** (catches an envelope written during close).

The handled path refuses reports from the instant the switch changes (`report` re-checks
suppression and the gate per call). Airgap going back off never restarts the SDK mid-run — the
crash handler is not re-installed twice in one process; reporting resumes at the next launch.

### Why replay is impossible even if the record is lost

The retirement record is the auditable tripwire, not the mechanism. **Every permitted launch wipes
the cache root and verifies the wipe before the SDK exists**, and nothing reads a *missing* record
as permission to reuse a cache — `start()` never consults the record to decide anything except
whether a failed wipe may clear it. So a lost or failed record write at entry cannot lead to
replay: the next launch's wipe destroys whatever the retired run persisted, verified, before
arming. If the wipe itself cannot be verified, the launch fails closed (`.cacheWipeFailed`) and
leaves the record set for the next attempt.

### Redirects

The backing forwarder session never follows a redirect itself (`RedirectFollowerStopper` vetoes via
the documented `completionHandler(nil)`), because a bare `URLSession` follows redirects behind the
outer protocol stack and the hop would bypass admission entirely. The gate resolves `Location` and
hands the redirected request back through the gated session (`urlProtocol(wasRedirectedTo:)`), so
every hop crosses admission again. Auth-ish headers (`Authorization`, `X-Sentry-Auth`, `Cookie`)
never cross a redirect; a cross-host redirect strips *all* headers; 301/302/303 re-issue as GET;
307/308 keep method and body, same host only.

## The payload boundary

**`beforeSend` is a whitelist, not a scrub** (`ContextSentryPolicy`): every field not named as kept
is dropped, from crash events included — on the launch after a crash the SDK converts the native
report and runs it through the same hook, so exception values, thread names, frame paths and
captured locals all arrive there first.

Kept — because symbolication needs exactly these: frame `instructionAddress`, `imageAddress`,
`symbolAddress`, `function`, `inApp`; image `uuid`/`type`/addresses/size; exception `type` and
mechanism; thread ids/flags; build identity (`release`, `dist`, `environment`, platform, SDK
version); the `context-for-claude` tag; `os`/`device`/`app` context subfields on the whitelist
(`device.name` — the user's own Mac name — is the field this rule exists to drop).

Dropped, with no diagnostic return: exception `value`s (free `NSError`/`NSException` text), thread
names, frame file paths, source snippets, captured locals, image `name`/`codeFile`, `user`,
breadcrumbs, `extra`, `request`, `modules`, `serverName`, arbitrary fingerprints, and any message
that is not one of this app's slugs.

Handled failures (the only `capture` path — `ContextTelemetry.recordFallback` → `ContextSentry`
→ `capture(event:)` on a fresh empty scope) carry a message slug
(`cfc-fallback area=… reason=… outcome=…`) and a fingerprint triple, both built from closed enums;
the whitelist passes only values in that vocabulary and drops everything else. Reasons that map to
`airgap-mode` are never forwarded — the cycle-breaker that keeps reporting from reporting its own
suppression.

Two structural points beyond `beforeSend`:

- **Every SDK feature that produces envelopes `beforeSend` would never see is explicitly off**:
  session tracking, app-hang and watchdog reports, breadcrumbs (cap 0), performance tracing and
  launch profiling, swizzling, failed-request capture, screenshots, view hierarchy,
  `sendDefaultPii`, Spotlight — and `sendClientReports`, the transport-synthesized client-report
  envelopes. What remains is the crash handler and handled events: this task is diagnostics, not
  telemetry.
- **The serialized traffic is audited, not trusted** (`ContextSentrySDKTrafficTests`): the real
  SDK runs against the gated session with a capturing forwarder, and the test decodes the actual
  envelope bytes at the admission point and asserts the whitelist field by field. No attachments
  are ever added by this app, so the envelope item set is `event` only.

Residual, stated honestly: the transport still reveals to the ingest host that this app, this
build, and this IP exist — that is inherent to any networked crash reporting and is exactly what
the Airgap gate is for.

## Failure-reporting ownership

There is no `SentrySDK.capture` anywhere outside `SentrySDKReporting.send`, and no second
suppression state: `ContextTelemetry.recordFallback` remains the one contract surface (the local
`os.Logger` record is unchanged and is still the durable audit trail), `NetworkEgress` remains the
one suppression authority, and `ExclusionEngine` notifies observers only after it has persisted the
new state. The Airgap transition's gate closure and retirement mark run before any queued disk
work, and no telemetry callback runs inside a gate lock.

## Testing

`swift test --filter ContextSentry` — hermetic, no network, no Sentry project needed:

- `ContextSentryPolicyTests` — hostile-payload whitelist, vocabulary gating for message and
  fingerprint (the mirror-struct half).
- `ContextSentryGateTests` — admission before entry, live-suppression refusal, entry permanence,
  redirect re-admission through the real gated session (including a queued redirect that crosses
  entry), header sanitization, the forwarder's redirect veto.
- `ContextSentryLifecycleTests` — launch gates, duplicate start, wipe-and-verify before arming,
  airgapped launch drop, transition ordering (gate → retirement → purge → close → purge), the
  late-write race, retirement surviving queued writes and clearing only on a verified fresh start,
  the lost-record case, report refusal windows.
- `ContextSentrySDKTrafficTests` — the real SDK, real serialization, envelope bytes audited;
  options assembly asserts every automatic producer is off.

Not proven off a Mac: native crash capture itself (needs a signed crashing build), dSYM
symbolication (see the plan above), and the redirect veto against a live remote — the suite proves
the protocol-level plumbing URLSession actually drives, not a second hand-rolled gate call.
