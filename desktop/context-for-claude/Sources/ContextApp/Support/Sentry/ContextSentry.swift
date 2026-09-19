import ContextCore
import Foundation

/// One handled failure, already mapped into the closed diagnostic vocabulary.
///
/// This type has no field a call site can smuggle text through: `area` and `outcome` are closed
/// enums, and `reason` is `AnalyticsEvent.FallbackReason` — the same mapping
/// `ContextTelemetry.recordFallback` already applies before anything is forwarded anywhere. The
/// wire form is a message slug plus tags built from these values, so what Sentry groups and what
/// a reader sees is exactly this struct and nothing more.
struct ContextSentryHandledReport: Sendable, Equatable {
    var area: ContextFallbackArea
    var outcome: ContextFallbackOutcome
    var reason: AnalyticsEvent.FallbackReason

    /// The message the event carries — a slug, not a sentence, and never error text.
    var message: String {
        "cfc-fallback area=\(area.rawValue) reason=\(reason.rawValue) outcome=\(outcome.rawValue)"
    }

    /// Groups one issue per (area, reason): the failure mode is the issue; outcomes of the same
    /// failure land in the same issue and are visible in the title.
    var fingerprint: [String] { ["cfc-fallback", area.rawValue, reason.rawValue] }

    var tags: [String: String] { [ContextSentryPolicy.appTag: ContextSentryPolicy.appTag] }
}

/// The seam the SDK-facing adapter lives behind, so every rule in this integration is testable
/// offline — the same shape as `AnalyticsTransport`.
///
/// The real implementation starts `SentrySDK`, installs the `beforeSend` whitelist, and captures;
/// a test double records. Nothing else in this file knows the SDK exists.
protocol ContextSentryReporting: Sendable {
    /// Reports one handled failure. Called only after every gate has passed.
    func send(_ report: ContextSentryHandledReport)
    /// Stops the SDK. Called only as part of an Airgap transition, after the cache has been
    /// purged — never as a flush, because closing flushes (see `ContextSentry`).
    func close()
}

/// The durable record that a previous run entered Airgap while the SDK was armed.
///
/// **Placement is the contract.** The SDK's cache root (`ContextSentryConfig.cacheDirectory`) is
/// deleted on every Airgap transition and every permitted launch; this record lives *outside* that
/// subtree, in `UserDefaults`, so the first purge cannot destroy the protection — the mistake an
/// in-root marker would make. It is written at entry, survives every queued SDK write and both
/// purge passes, and is cleared by exactly one code path: a fresh process, after a **verified**
/// wipe, before the SDK is initialized.
///
/// `UserDefaults` rather than a hand-rolled sibling file, for the reason `RevivalBudget.record`
/// already committed to in `ContextApp.swift`: the plist goes through `cfprefsd`, and the one
/// place durability against a fast successor matters is worth a deprecated `synchronize()`.
///
/// ## What the record is — and what it is not
///
/// It is the auditable state and the tripwire: when it is set, something armed was told to stop,
/// and a later launch must prove the cache is gone before arming again (`ContextSentry.start`
/// wipes and *verifies* on every launch anyway, and never clears the record unless that succeeds).
///
/// It is **not** the mechanism that prevents a suppressed-period cache from being replayed. That
/// mechanism is the unconditional wipe-with-verification every permitted launch performs before
/// the SDK is initialized — which never reads this record. If the write here were lost (cfprefsd
/// failure, full disk), a later launch still fails closed, because "start" is unreachable without
/// a verified wipe; nothing anywhere reads a *missing* record as permission to reuse a cache.
/// Strict drop is by construction, not by flag.
struct ContextSentryRetirement: Sendable {
    static let key = "context.sentry.cacheRetired"

    let defaults: UserDefaults

    /// Marks retirement durably, flushed now: the process could crash at any point after the
    /// Airgap switch, and a record the successor cannot see is not a record.
    func mark() {
        defaults.set(true, forKey: Self.key)
        // Same deliberate deprecation as `RevivalBudget.record`: cross-process visibility of a
        // one-shot durable fact beats the ordinary batched flush here.
        defaults.synchronize()
    }

    var isRetired: Bool { defaults.bool(forKey: Self.key) }

    /// Called only by a fresh process, after a verified wipe, before SDK initialization.
    func clear() {
        defaults.removeObject(forKey: Self.key)
    }
}

/// Context for Claude's crash and handled-error reporting: one lifecycle, one state authority.
///
/// ## The gates, in order
///
/// 1. **Shipping only.** `ContextPaths.isShippingBundle` — the test runner and dev builds never
///    start the SDK. Same refusal as analytics, same measured reason: a process nobody considers
///    production can look exactly like the release, and `swift test` spent months POSTing to
///    PostHog before anyone noticed.
/// 2. **Valid dedicated-project DSN.** `ContextSentryConfig.dsn` — nil (missing, placeholder, or
///    malformed) means reporting is simply disabled. No crash handler is installed, no cache
///    directory is created, and startup is untouched. There is no code path that starts the SDK
///    "partially".
/// 3. **Verified-clean cache, on every permitted launch, before anything SDK.** The cache root is
///    deleted and its absence *checked*. Deletion without verification is a hope: a file held by a
///    stuck file descriptor can survive `removeItem`, and SDK behavior around a half-deleted
///    generation is exactly what we must not gamble on. Verification failure is terminal for the
///    process (`.cacheWipeFailed`): the SDK never starts, the retirement record (if set) is never
///    cleared, and the next launch tries again.
/// 4. **Airgap Mode off at launch**, checked live, like every other `NetworkEgress` client. The
///    wipe from step 3 already happened, so any crash envelope a previous run left behind —
///    including one written *after* that run's Airgap entry — was dropped, not held for a later
///    upload.
///
/// ## Airgap at runtime: drop, never defer
///
/// The SDK queues every envelope to disk before sending, re-sends its whole queue at start, after
/// every send, on flush, and when the network comes back — verified in sentry-cocoa 8.58.0
/// (`SentryHttpTransport`). `SentrySDK.close()` uninstalls the native crash handler **but flushes
/// first**, so it can never be the whole response to the switch. And the SDK has no public purge
/// or synchronous transport shutdown: queued sends are async `NSOperation`s that `task.resume`
/// whenever they are dequeued, so a purge-and-close alone can lose the race.
///
/// That is why the HTTP boundary moves first. The SDK's session is one this app constructed
/// (`Options.urlSession`), and its protocol stack is ``ContextSentryGate``: at entry, the gate
/// closes **before any purge work is scheduled**, so no queued send, retry, or redirected request
/// can reach a socket from that instant, for the rest of the process. Then, in order:
///
/// 1. **Gate closed** (synchronous, memory-only, infallible). Admission from here on refuses.
/// 2. **Retirement marked** durably (`ContextSentryRetirement.mark`).
/// 3. On a utility queue: **delete the cache root** (destroys queued envelopes), **`close()`** the
///    SDK (uninstalls the crash handler; its built-in flush finds a closed gate), **delete the
///    cache root again** (anything that raced the first pass — an envelope written between purge
///    and close — dies with the process, and the wipe-verify at the next launch is the backstop
///    for anything that raced even that).
///
/// Requests *already admitted* before entry may complete or be cancelled; the gate's decision
/// types make that distinction explicit, and no supported API revokes an in-flight request.
/// The handled path refuses reports from the instant the switch changes, because it reads
/// suppression — and the gate — live per report.
///
/// A flip back OFF does not restart the SDK. Restarting would re-install the native crash handler
/// mid-run — the exact class of signal-context churn that has bitten this repository's desktop
/// builds before — for a few remaining minutes of diagnostics. Reporting resumes on next launch,
/// where the wipe-verify has already destroyed anything the retired run persisted.
///
/// ## Handled failures
///
/// Reported by the one existing owner, `ContextTelemetry.recordFallback`, which already owns the
/// closed vocabulary, the slug mapping, and the `airgap-mode` cycle-breaker. There is no
/// `SentrySDK.capture` anywhere else in the app: a second capture path would be a second state
/// authority for the same question. Reasons that map to `.airgapMode` are never forwarded —
/// reporting its own suppression is the one thing this integration must not do, and the hop
/// `suppression record → telemetry → this function` would otherwise not terminate.
final class ContextSentry: @unchecked Sendable {

    static let shared = ContextSentry(
        dsn: { ContextSentryConfig.dsn() },
        isShippingBundle: { ContextPaths.isShippingBundle },
        isSuppressed: { NetworkEgress.isSuppressed(.crashReporting) },
        cacheRoot: ContextSentryConfig.cacheDirectory(),
        retirement: ContextSentryRetirement(defaults: .standard),
        makeReporting: { SentrySDKReporting(options: $0) },
        registerAirgapObserver: { handler in
            ExclusionEngine.shared.addObserver { set in handler(set.airgapMode) }
        })

    /// Why the SDK is not running. Logged once per launch, so "nothing is reporting" always
    /// carries its reason with it.
    enum State: Equatable {
        /// Reporting is off for this run, and why.
        case disabled(DisabledReason)
        /// Started and accepting handled reports.
        case started
        /// Started once, closed by an Airgap transition. No restart until the next launch.
        case closedByAirgap
    }

    enum DisabledReason: Equatable {
        /// Not the shipping bundle (dev build or test runner).
        case notShipping
        /// No valid `ContextSentryDSN` in Info.plist — the dedicated project is not configured.
        case missingConfig
        /// Airgap Mode was on at launch; any cached envelopes were dropped.
        case airgappedAtLaunch
        /// The pre-start cache wipe could not be verified. Fail closed: the SDK never starts, and
        /// a set retirement record is deliberately left set for the next launch.
        case cacheWipeFailed
    }

    /// Everything the real adapter needs, built once at start. Value type so the factory seam
    /// receives a plain struct instead of reaching back into this class.
    struct StartOptions: Sendable, Equatable {
        var dsn: String
        var releaseName: String
        var dist: String
        var environment: String
        var cacheRoot: String
    }

    private let lock = NSLock()
    private var state: State
    private var reporting: ContextSentryReporting?
    private var observerToken: UUID?

    // Injectable edges. `shared` points them at production; tests point them at fakes.
    private let dsn: () -> String?
    private let isShippingBundle: () -> Bool
    private let isSuppressed: () -> Bool
    private let cacheRoot: URL
    private let retirement: ContextSentryRetirement
    private let makeReporting: (StartOptions) -> ContextSentryReporting
    private let registerAirgapObserver: (@Sendable (Bool) -> Void) -> UUID
    /// Serialises the Airgap transition's disk work. The gate closure and retirement mark happen
    /// *before* anything is scheduled here, so no queue latency can leave a send window open.
    private let airgapQueue: DispatchQueue

    init(
        dsn: @escaping () -> String?,
        isShippingBundle: @escaping () -> Bool,
        isSuppressed: @escaping () -> Bool,
        cacheRoot: URL,
        retirement: ContextSentryRetirement,
        makeReporting: @escaping (StartOptions) -> ContextSentryReporting,
        registerAirgapObserver: @escaping (@Sendable (Bool) -> Void) -> UUID,
        airgapQueue: DispatchQueue = DispatchQueue(
            label: "com.omi.context-for-claude.sentry", qos: .utility)
    ) {
        self.dsn = dsn
        self.isShippingBundle = isShippingBundle
        self.isSuppressed = isSuppressed
        self.cacheRoot = cacheRoot
        self.retirement = retirement
        self.makeReporting = makeReporting
        self.registerAirgapObserver = registerAirgapObserver
        self.airgapQueue = airgapQueue
        self.state = .disabled(.missingConfig)
    }

    /// Starts reporting if — and only if — every gate passes. Safe to call any number of times:
    /// the first call decides, later ones are no-ops. Called once per process, from the app's
    /// launch path, before `ContextAnalytics.start()`.
    func start() {
        lock.lock()
        defer { lock.unlock() }
        if reporting != nil || state != .disabled(.missingConfig) {
            // A second `start` would ask the SDK to install a second native crash handler, and
            // "started" and "deliberately disabled" are both terminal for this process.
            return
        }

        guard isShippingBundle() else {
            state = .disabled(.notShipping)
            return
        }

        guard let projectDSN = dsn() else {
            state = .disabled(.missingConfig)
            return
        }

        // Every permitted launch proves the cache is gone *before* the SDK exists — this is the
        // mechanism behind Airgap drop semantics, and it does not consult the retirement record,
        // so a lost record can never become "reuse the cache". If deletion cannot be verified,
        // the process stays disarmed and a set record stays set.
        guard wipeCacheAndVerify() else {
            state = .disabled(.cacheWipeFailed)
            ContextLog.error(
                "sentry cache wipe failed verification; reporting disabled this launch", "sentry")
            return
        }

        // Retirement is cleared by exactly one code path: a fresh process, after a verified wipe,
        // before SDK initialization.
        retirement.clear()

        // Airgap at launch: the SDK is never started, and whatever a previous run left cached was
        // already destroyed above — dropped, not retained.
        guard !isSuppressed() else {
            state = .disabled(.airgappedAtLaunch)
            NetworkEgress.recordSuppression(.crashReporting, outcome: .dropped)
            return
        }

        let identity = ContextSentryConfig.releaseIdentity()
        let options = StartOptions(
            dsn: projectDSN,
            releaseName: identity.releaseName,
            dist: identity.dist,
            environment: "production",
            cacheRoot: cacheRoot.path)
        reporting = makeReporting(options)

        // Fires once immediately with the current state; Airgap is off here, so the immediate
        // call observes `false` and does nothing.
        observerToken = registerAirgapObserver { [weak self] airgapMode in
            guard airgapMode else { return }  // no restart after a close; see the type docs
            self?.closeForAirgap()
        }

        state = .started
    }

    /// Reports one handled failure through the closed vocabulary.
    ///
    /// Every gate is re-checked live: an Airgap flip between the caller's decision and this call
    /// still refuses — both via `isSuppressed()` and via the gate, which covers the window between
    /// `enterAirgap()` and the queued close that nils `reporting`. A suppressed report is dropped
    /// silently — recording it would report this integration's own suppression, and the
    /// `airgap-mode` hop through telemetry would not terminate.
    func report(_ handled: ContextSentryHandledReport) {
        lock.lock()
        let reporting = self.reporting
        lock.unlock()

        guard reporting != nil, !isSuppressed(), !ContextSentryGate.isClosed else { return }
        reporting?.send(handled)
    }

    /// Whether the SDK is running. Read by tests; also the honest answer for anything that ever
    /// needs to ask whether reporting is armed.
    var isStarted: Bool {
        lock.lock(); defer { lock.unlock() }
        return state == .started
    }

    var currentState: State {
        lock.lock(); defer { lock.unlock() }
        return state
    }

    /// The Airgap transition, in the order the guarantees demand.
    ///
    /// Steps 1–2 run synchronously on the observer's thread — the same thread `ExclusionEngine`
    /// notifies after it has persisted the new state (`mutate` persists, then fires observers) —
    /// and neither holds a lock while telemetry could re-enter: `enterAirgap` releases the gate's
    /// lock before returning, and the retirement write touches no lock this type owns. Disk work
    /// is scheduled last and serialised by `airgapQueue`.
    private func closeForAirgap() {
        // 1. No new HTTP request — queued SDK send, retry, or redirect — can start from this
        //    instant, for the rest of the process. Memory-only, cannot fail.
        ContextSentryGate.enterAirgap()
        // 2. Durable, outside the purged subtree, flushed now.
        retirement.mark()

        airgapQueue.async { [weak self] in
            guard let self else { return }
            // 3a. Destroy queued envelopes.
            _ = self.wipeCacheAndVerify()

            self.lock.lock()
            let reporting = self.reporting
            self.reporting = nil
            self.state = .closedByAirgap
            self.lock.unlock()
            // 3b. The crash handler is uninstalled; the SDK's built-in flush finds a closed gate
            //     and sends nothing.
            reporting?.close()

            // 3c. Whatever raced the first pass — an envelope written between it and the close —
            //     is removed too. After this there is nothing left to race in this process; the
            //     next launch's wipe-verify is the backstop for anything that raced even this.
            _ = self.wipeCacheAndVerify()
        }
    }

    /// Deletes the SDK cache root and **verifies the deletion**.
    ///
    /// Returns false when the root still exists after `removeItem` — a file held by a stuck file
    /// descriptor can survive a removal. The caller fails closed on false; nothing in this
    /// integration ever treats a half-deleted cache as clean.
    private func wipeCacheAndVerify() -> Bool {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: cacheRoot.path) else { return true }
        try? fileManager.removeItem(at: cacheRoot)
        // Re-stat after a beat-free check: `removeItem` is synchronous, so absence now is absence.
        return !fileManager.fileExists(atPath: cacheRoot.path)
    }
}
