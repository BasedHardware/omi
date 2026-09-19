# CFC crash diagnostics

The intended destination is the dedicated Cocoa project `omi-nk3/context-for-claude`, never
Omi Desktop's project. Provisioning, DSN injection, and native verification are pending. This
integration is disabled when no valid `ContextSentryDSN` exists in the shipping app's Info.plist.
There is no runtime environment override and no PostHog identity linkage.

## Configuration and release identity

Release packaging must inject `ContextSentryDSN` before signing. This change does not alter the
release scripts or supply a DSN. Dev bundles and tests do not start the SDK through the production
launch path. Invalid configuration disables diagnostics without preventing app startup.

Events use `release = context-for-claude@<version>+<build>`, `dist = <build>`, and
`environment = production`, from the bundle's version/build values. Sentry is pinned to 8.58.0.

## Airgap closes admission and retires the cache

`ContextSentry` owns the lifecycle; `NetworkEgress` remains the live suppression authority.
`Options.urlSession` supplies a dedicated session using `ContextSentryGate`. Admission and the
backing task's resume are serialized with gate closure. The gate reads live suppression as well
as its process-sticky closure flag. Requests already admitted may complete; requests arriving
after closure must not reach the backing session. Redirects are rejected, not followed.

`ExclusionConfiguration.crashReportingGeneration` is a UUID persisted atomically with Airgap
changes. The SDK cache is `<support>/SentryCache/<generation>/…`:

- An ordinary restart reuses the same generation, preserving the native crash report that the
  SDK can only convert and submit on its next launch.
- Either Airgap transition replaces the generation. Even if the process crashes before the
  observer runs, its old cache cannot be selected after the persisted transition.
- A legacy configuration has no generation. Startup creates and persists one before starting
  the SDK; a persistence failure disables diagnostics. Legacy/orphan cache directories are removed.
- Startup deletes retired generations before initializing the SDK. Cleanup failure disables
  reporting. It does **not** delete the healthy active generation on every launch.

At runtime, entry closes the gate synchronously, writes an additional retirement record in
UserDefaults (outside the cache tree), then queues cache deletion → SDK close → cache deletion.
Close may flush, but those requests face the closed gate. Queued SDK writes may recreate files;
the next process removes their retired generation rather than reopening it. Turning Airgap off
does not restart the SDK in the same process.

The secondary retirement record covers fail-closed settings loads and unsuccessful settings
writes. A launch with that record wipes all SDK state before clearing it. An airgapped launch
never starts the SDK and keeps retirement set. This record is not needed to invalidate a
generation after a **successfully persisted** Airgap transition.

Durability has the same storage prerequisite as the privacy setting itself: if both the settings
write and the secondary record fail, and cache cleanup also fails before the process dies, a later
process cannot reconstruct an unpersisted user action. `ExclusionHealth.notPersisted` exposes the
settings failure. Do not describe the cross-launch guarantee as surviving total storage failure.

## Payload contract

Handled errors flow only through `ContextTelemetry.recordFallback` and its closed enums. The
`airgap-mode` reason is excluded to prevent reporting the suppression itself. Messages and
fingerprints must validate the exact vocabulary, not just a prefix. The only product tag is
`app=context-for-claude`.

The SDK adapter filters crash and handled events before serialization. It removes user identity,
breadcrumbs, extra data, request data, machine name, modules, exception text, thread names,
filesystem paths, source snippets, locals, and arbitrary messages/fingerprints. Crash reports
retain symbolication addresses/image UUIDs, exception types, thread flags, build metadata, and
allowlisted OS/device/app fields. Handled events do not retain machine contexts.

Sessions, app-hang/watchdog tracking, breadcrumbs, swizzling, performance/profiling, screenshots,
view hierarchy, failed-request capture, client reports, Spotlight, and default PII are disabled.
No attachments or replay are added. The ingest host still sees the source IP; disabling PII does
not conceal transport metadata.

Cached serialized envelopes do not pass through `beforeSend` again. They were filtered before
storage; generation invalidation prevents retired envelopes from being replayed. Raw crash
reports are converted and filtered on the subsequent launch.

## Verification and symbolication remain release blockers

Run on a Mac from this directory:

```sh
swift test --filter 'ContextSentry|ExclusionsTests'
swift test
```

Tests cover normal-crash preservation, retired-generation cleanup even without the secondary
record, legacy configuration, settings/cache failures, launch gates, runtime closure, exact
payload vocabulary, URLProtocol admission, and serialized real-SDK envelopes via a canned
forwarder. These tests were authored in a Linux orb without Swift/Xcode and have **not run**.
The dependency lockfile also needs validation with the native Swift package resolver.

The wire tests use macOS's `/usr/bin/gzip` to decode the HTTP body and reject any envelope item
other than an event. Their expected format comes from the pinned SDK, not the adapter:
[gzip request construction](https://github.com/getsentry/sentry-cocoa/blob/16cd512711375fa73f25ae5e373f596bdf4251ae/Sources/Swift/Tools/SentryURLRequestFactory.swift),
[event serialization](https://github.com/getsentry/sentry-cocoa/blob/16cd512711375fa73f25ae5e373f596bdf4251ae/Sources/Sentry/SentryEvent.m),
and [crash-report conversion](https://github.com/getsentry/sentry-cocoa/blob/16cd512711375fa73f25ae5e373f596bdf4251ae/Sources/Sentry/SentryCrashReportSink.m).

Before claiming end-to-end crash coverage:

1. Build a signed test app with the dedicated DSN injected before signing.
2. Produce dSYMs and compare `dwarfdump --uuid` with the shipped binary's UUIDs.
3. Add a separately reviewed release-lane upload using `sentry-cli debug-files upload`, the
   dedicated project, and a CI-scoped auth token. No upload step is implemented here.
4. With explicit staging-event authorization, deliberately crash the test app, relaunch it, and
   verify delivery and symbolicated frames. Exercise Airgap entry/restart against a controlled
   endpoint as well. Never use the installed production app for this test.

No production events, project settings, uploads, or releases were changed by this implementation.
