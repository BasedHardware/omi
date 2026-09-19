import ContextCore
import Foundation
import Sentry

/// The one place this app touches the Sentry SDK: options assembly, the `beforeSend` whitelist
/// bridge, and the two operations the rest of the app is allowed to ask for.
///
/// Everything policy-shaped lives in `ContextSentryPolicy` (pure, SDK-free); everything
/// lifecycle-shaped lives in `ContextSentry` (SDK-free via `ContextSentryReporting`). This file is
/// the thinnest possible translation layer between them.
///
/// ## The options are the privacy contract's first half
///
/// Every SDK feature that would produce an *event or envelope this app did not author* is
/// explicitly off: automatic session tracking, app-hang detection, watchdog termination reports,
/// breadcrumbs (and the cap set to zero), automatic performance tracing and launch profiling,
/// swizzling, failed-request capture, view hierarchy and screenshot attachment, `sendDefaultPii`,
/// Spotlight debugging — and `sendClientReports`, because those are envelopes the *transport*
/// synthesizes (discarded-event counts) rather than events `beforeSend` would see. What remains
/// is exactly this task: the native crash handler for crashes, `capture(event:)` for handled
/// failures — this task being crash/error diagnostics, not telemetry.
///
/// `cacheDirectoryPath` points into the app's own support directory (`ContextSentryConfig`), which
/// is what makes Airgap's drop semantics a directory deletion. `urlSession` is the gated session
/// from `ContextSentryGate` — the supported seam (`SentryOptions.h` documents it for "configure a
/// custom NSURLSession"; `SentryTransportFactory` hands it to every outgoing request) through
/// which every envelope send, retry, and redirect crosses admission.
final class SentrySDKReporting: ContextSentryReporting {

    private let options: ContextSentry.StartOptions

    init(options: ContextSentry.StartOptions) {
        self.options = options
        SentrySDK.start { configure in
            Self.apply(options, to: configure)
        }
    }

    /// The complete options assembly, as one function so tests can assert the values — every
    /// defaulted-on SDK flag this integration must have off — without starting the SDK (starting
    /// installs the native crash handler, which a test process must not do).
    static func apply(_ options: ContextSentry.StartOptions, to configure: Options) {
        configure.dsn = options.dsn
        configure.releaseName = options.releaseName
        configure.dist = options.dist
        configure.environment = options.environment

        // State lives where Airgap can drop it, traffic flows through the admission gate.
        configure.cacheDirectoryPath = options.cacheRoot
        configure.urlSession = ContextSentryGate.makeSentrySession()

        // Crash/errors only. Every automatic producer of other envelopes is off (see the type
        // doc); a defaulted-on flag left implicit here is a privacy regression waiting for an SDK
        // point release.
        configure.enableCrashHandler = true
        configure.enableAutoSessionTracking = false
        configure.enableAppHangTracking = false
        configure.enableAppHangTrackingV2 = false
        configure.enableWatchdogTerminationTracking = false
        configure.enableAutoBreadcrumbTracking = false
        configure.maxBreadcrumbs = 0
        configure.enableAutoPerformanceTracing = false
        configure.enableAppLaunchProfiling = false
        configure.enableSwizzling = false
        configure.enableCaptureFailedRequests = false
        configure.attachScreenshot = false
        configure.attachViewHierarchy = false
        configure.sendDefaultPii = false
        configure.sendClientReports = false
        configure.enableSpotlight = false
        configure.debug = false

        configure.beforeSend = Self.beforeSend
    }

    /// An empty scope avoids ambient user/breadcrumb state. The SDK still enriches events before
    /// beforeSend, where our policy removes machine contexts and stacks from handled reports.
    func send(_ report: ContextSentryHandledReport) {
        SentrySDK.capture(event: Self.makeEvent(report), scope: Scope())
    }

    /// Shared with the real-SDK traffic test.
    static func makeEvent(_ report: ContextSentryHandledReport) -> Event {
        let event = Event(level: SentryLevel.warning)
        event.message = SentryMessage(formatted: report.message)
        event.fingerprint = report.fingerprint
        event.tags = report.tags
        return event
    }

    /// Stops the SDK. Only ever called from the Airgap transition, after the gate is closed and
    /// the cache is purged: `close()` flushes first (sentry-cocoa 8.58.0, `SentryClient`), and
    /// that flush finds a closed admission gate and an empty cache.
    func close() {
        SentrySDK.close()
    }

    // MARK: beforeSend — the whitelist bridge

    /// Snapshots the SDK event, applies the whitelist, and writes back **only** the scrubbed
    /// fields. Write-back is per-field rather than a fresh event so the SDK's own identity
    /// (`eventId`) stays untouched; every field the whitelist drops is assigned `nil` here, which
    /// is the "dropped has one spelling" rule from `ContextSentryScrubbedEvent`.
    ///
    /// This hook sees crash events too: on the launch after a crash the SDK converts the native
    /// report and runs the result through `beforeSend` (`SentryCrashReportSink` → `captureFatalEvent`),
    /// so the frame lists, image lists, exception values and thread names a crash report carries
    /// are all reduced here, before serialization.
    static func beforeSend(_ event: Event) -> Event? {
        guard !ContextSentryPolicy.shouldDrop(
            isShippingBundle: ContextSentryPolicy.liveIsShippingBundle())
        else { return nil }

        let scrubbed = ContextSentryPolicy.apply(Self.snapshot(of: event))

        event.user = nil
        event.breadcrumbs = nil
        event.extra = nil
        event.request = nil
        event.modules = nil
        event.serverName = nil
        event.stacktrace = nil
        event.logger = nil
        event.transaction = nil

        event.message = scrubbed.message.map { SentryMessage(formatted: $0) }
        event.fingerprint = scrubbed.fingerprint
        event.tags = scrubbed.tags

        var contexts: [String: [String: Any]] = [:]
        for (name, values) in scrubbed.context where !values.isEmpty {
            contexts[name] = values as [String: Any]
        }
        event.context = contexts.isEmpty ? nil : contexts

        event.exceptions = scrubbed.exceptions.isEmpty
            ? nil
            : scrubbed.exceptions.map { exception in
                // `Exception.value` is non-optional in the SDK, so a dropped value is the empty
                // string — serialized as absent-or-empty, never as text.
                let sdkException = Exception(value: "", type: exception.type)
                if let mechanismType = exception.mechanismType {
                    let mechanism = Mechanism(type: mechanismType)
                    mechanism.handled = exception.mechanismHandled as NSNumber?
                    sdkException.mechanism = mechanism
                }
                return sdkException
            }

        event.threads = scrubbed.threads.isEmpty
            ? nil
            : scrubbed.threads.map { thread in
                let sdkThread = SentryThread(threadId: NSNumber(value: thread.id))
                sdkThread.crashed = thread.crashed.map(NSNumber.init(value:))
                sdkThread.current = thread.current.map(NSNumber.init(value:))
                sdkThread.isMain = thread.isMain.map(NSNumber.init(value:))
                sdkThread.stacktrace = SentryStacktrace(
                    frames: thread.frames.map { frame in
                        // `Frame` is Sentry's Swift name for `SentryFrame`; qualified because
                        // ContextCore also declares a `Frame`.
                        let sdkFrame = Sentry.Frame()
                        sdkFrame.instructionAddress = frame.instructionAddress
                        sdkFrame.imageAddress = frame.imageAddress
                        sdkFrame.symbolAddress = frame.symbolAddress
                        sdkFrame.function = frame.function
                        sdkFrame.inApp = frame.inApp.map(NSNumber.init(value:))
                        return sdkFrame
                    },
                    registers: [:])
                return sdkThread
            }

        event.debugMeta = scrubbed.debugMeta.isEmpty
            ? nil
            : scrubbed.debugMeta.map { image in
                let sdkImage = DebugMeta()
                sdkImage.uuid = image.uuid
                sdkImage.type = image.type
                sdkImage.imageAddress = image.imageAddress
                sdkImage.imageVmAddress = image.imageVmAddress
                sdkImage.imageSize = image.imageSize.map(NSNumber.init(value:))
                return sdkImage
            }

        return event
    }

    /// Copies the SDK event into the mirror the policy can reason about. Values the policy is
    /// known to drop are captured anyway — as audit fields — so the tests can assert *absence in
    /// the scrubbed output* rather than assume the snapshotter's opinion.
    static func snapshot(of event: Event) -> ContextSentryEventSnapshot {
        ContextSentryEventSnapshot(
            eventType: event.type,
            level: Self.levelName(event.level),
            platform: event.platform,
            releaseName: event.releaseName,
            dist: event.dist,
            environment: event.environment,
            sdkName: event.sdk?["name"] as? String,
            sdkVersion: event.sdk?["version"] as? String,
            message: event.message?.formatted,
            fingerprint: event.fingerprint,
            tags: event.tags,
            context: event.context?.mapValues { values in
                values.compactMapValues { $0 as? String }
            },
            exceptions: event.exceptions?.map { exception in
                ContextSentryEventSnapshot.Exception(
                    type: exception.type,
                    value: exception.value,
                    mechanismType: exception.mechanism?.type,
                    mechanismHandled: exception.mechanism?.handled?.boolValue)
            },
            threads: event.threads?.map { thread in
                ContextSentryEventSnapshot.Thread(
                    id: thread.threadId.int64Value,
                    crashed: thread.crashed?.boolValue,
                    current: thread.current?.boolValue,
                    isMain: thread.isMain?.boolValue,
                    frames: thread.stacktrace?.frames.map { frame in
                        ContextSentryEventSnapshot.Frame(
                            instructionAddress: frame.instructionAddress,
                            imageAddress: frame.imageAddress,
                            symbolAddress: frame.symbolAddress,
                            function: frame.function,
                            inApp: frame.inApp?.boolValue)
                    } ?? [])
            },
            debugMeta: event.debugMeta?.map { image in
                ContextSentryEventSnapshot.DebugImage(
                    uuid: image.uuid,
                    type: image.type,
                    imageAddress: image.imageAddress,
                    imageVmAddress: image.imageVmAddress,
                    imageSize: image.imageSize?.int64Value)
            },
            user: event.user?.userId ?? event.user?.email ?? event.user?.username,
            breadcrumbCount: event.breadcrumbs?.count,
            extraKeys: event.extra.map { Array($0.keys) },
            hasRequest: event.request != nil,
            serverName: event.serverName,
            modules: event.modules)
    }

    private static func levelName(_ level: SentryLevel) -> String {
        switch level {
        case .fatal: return "fatal"
        case .error: return "error"
        case .warning: return "warning"
        case .info: return "info"
        case .debug: return "debug"
        default: return "none"
        }
    }
}
