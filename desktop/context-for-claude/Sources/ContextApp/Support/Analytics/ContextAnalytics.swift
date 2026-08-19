import AppKit
import ContextCore
import Foundation

/// The app's one analytics entry point.
///
/// Call `ContextAnalytics.record(_:)` from anywhere. Everything that makes a report defensible —
/// Airgap Mode, development builds, the daily rollup, batching, durability — is decided here rather
/// than at the call sites, so a new call site cannot get it wrong by omission.
///
/// ## The three refusals
///
/// 1. **Airgap Mode.** Checked on every single event, and the event is *dropped*, not deferred. It
///    means "nothing leaves this Mac"; a spooled event that flew the moment it was lifted would
///    honour the letter of that and break it entirely.
///
///    There is no Settings switch for it any more — it was removed in 1.0.9 and
///    `ExclusionEngine.setAirgapMode` has had no caller since. The state still occurs, which is why
///    this check is not dead code: an `exclusions.json` predating that release still carries it, and
///    `ExclusionSet.make` forces it on whenever the exclusion configuration fails closed. That last
///    case is the one to design for — a machine whose config cannot be parsed may be under
///    exclusions we cannot express, and reporting from it would be reporting from a state where we
///    cannot honour what the user asked to hide.
/// 2. **Anything that is not the shipping app.** A locally built app reports nothing, and neither
///    does the test runner. This is not tidiness: the Cloud Run logs for the first three weeks of this
///    app show a `Context for Claude/1` user agent from up to twenty machines a day — the team's own
///    builds, indistinguishable in aggregate from users. Analytics that count their own authors
///    answer a different question than the one being asked. See `isEnabled` for the shape of that
///    question, which is the half this shipped getting wrong.
/// 3. **Nothing user-authored, ever.** Enforced by construction in `AnalyticsEvent` — there is no
///    API here that accepts a string from a call site.
///
/// ## What this deliberately does not do
///
/// No session replay, no autocapture, no feature flags, no identify() against an Omi account. The
/// distinct id is a salted hash of the install id and stays that way even after sign-in: knowing
/// *that* an install has an account (`signed_in`) answers every product question that matters here,
/// and knowing *which* account would turn an anonymous series into a per-person record of when
/// somebody's microphone was on.
enum ContextAnalytics {

    // MARK: - Recording

    /// Reports one event, unless one of the three refusals applies.
    static func record(_ event: AnalyticsEvent) {
        guard isEnabled else { return }

        // Read live, never cached: the toggle takes effect on the next event, which is what lets
        // Airgap Mode promise "immediately" rather than "after relaunch".
        guard !NetworkEgress.isSuppressed(.analytics) else {
            NetworkEgress.recordSuppression(.analytics, outcome: .dropped)
            return
        }

        let payload = AnalyticsPayload(
            event: event,
            distinctID: AnalyticsIdentity.distinctID,
            timestamp: Date(),
            superProperties: currentSuperProperties())

        Task { await AnalyticsSink.shared.enqueue(payload) }
    }

    /// True only in the shipping app. See refusal 2 above.
    ///
    /// **Asked as "is this the release?", not as "is this not a dev build?", and the difference is
    /// the whole of a defect this shipped with.** `ContextPaths.isDevelopmentBuild` is derived from
    /// `ownIdentifier`, which falls back to the shipping identifier for any process that is not one
    /// of ours — correct for the log subsystem and the Keychain service, and exactly wrong here. The
    /// process it let through is the test runner: `swift test` runs under `com.apple.dt.xctest.tool`,
    /// so the suite counted as production and POSTed to PostHog from the real spool. Measured: 92
    /// events under a single distinct id derived from the xctest defaults domain's install id, every
    /// `cfc_gesture_fired` in the project and two thirds of `cfc_search_ran`.
    ///
    /// `CONTEXT_ANALYTICS_FORCE=1` overrides it for one purpose: proving end to end, from a local
    /// build, that events actually arrive in PostHog. There is no way to verify this pipeline without
    /// it — a release build cannot be run under a debugger on the machine that wrote it, and a sink
    /// nobody has watched deliver is a sink that has never worked. Events sent this way are
    /// indistinguishable from real ones, so anything recorded under the override lands in production
    /// series: use a throwaway `CONTEXT_ANALYTICS_FORCE` session, not a day of ordinary work.
    static var isEnabled: Bool {
        if ProcessInfo.processInfo.environment["CONTEXT_ANALYTICS_FORCE"] == "1" { return true }
        return ContextPaths.isShippingBundle
    }

    // MARK: - Lifecycle

    /// Wires analytics to the app's life. Called once, from `ContextApp`'s launch path.
    ///
    /// Ordering matters: the first-launch event has to be emitted before anything else can beat it to
    /// the `hasLaunchedKey` default, or the install denominator loses its first member.
    @MainActor
    static func start() {
        guard isEnabled else { return }

        let defaults = UserDefaults.standard
        if defaults.object(forKey: hasLaunchedKey) == nil {
            defaults.set(true, forKey: hasLaunchedKey)
            record(.firstLaunch)
        } else {
            record(.appLaunched)
        }

        // A day boundary crossed while the app was running still has to produce a rollup, so this is
        // a repeating check rather than a launch-time one. Hourly is far more often than the rollup
        // fires; the check itself is a date comparison against a stored string.
        rollupTimer?.invalidate()
        rollupTimer = Timer.scheduledTimer(withTimeInterval: 3600, repeats: true) { _ in
            Task { @MainActor in reportDailyRollupIfDue() }
        }
        reportDailyRollupIfDue()

        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification, object: nil, queue: .main
        ) { _ in
            // The rollup for a partial day is worth more than a clean shutdown is worth: an install
            // that is quit every evening would otherwise never report one.
            Task { @MainActor in
                reportDailyRollupIfDue(force: true)
                await AnalyticsSink.shared.flush()
            }
        }
    }

    // MARK: - Permissions

    /// Reports the state of every capability, once per launch.
    ///
    /// A snapshot rather than only change-events, because the interesting population is the one that
    /// *never* grants: someone who installs, is asked for Screen Recording, says no and quits leaves
    /// no transition to observe. Reported at launch, so an install's grant state is a property of
    /// every day it ran rather than of the one day it happened to change.
    @MainActor
    static func recordPermissionSnapshot() {
        guard isEnabled else { return }
        for capability in Capability.allCases {
            let state: AnalyticsEvent.PermissionState
            if Permissions.check(capability) {
                state = .granted
            } else {
                state = Permissions.grantWasLost(capability) ? .revoked : .denied
            }
            record(.permission(AnalyticsEvent.Permission(capability), state))
        }
    }

    // MARK: - Onboarding

    /// Records that first run reached a step, stamping the run's start on the first one seen.
    @MainActor
    static func recordOnboardingStep(index: Int, of total: Int) {
        guard isEnabled else { return }
        noteOnboardingStarted()
        record(.onboardingStep(index: index, of: total))
    }

    /// Records that first run ended, at most once per install.
    @MainActor
    static func recordOnboardingFinished() {
        guard isEnabled, let event = onboardingFinishedEvent() else { return }
        record(event)
    }

    /// Stamps when this install's first run began, if nothing has stamped it yet.
    ///
    /// **On disk rather than in a static, because onboarding is the one flow a successful step ends
    /// the process from the middle of.** Screen Recording only applies to a process that already held
    /// it when it connected to the window server, so the card's own "Restart to finish" — and macOS's
    /// own "Quit & Reopen" — kill the app between the grant and the finish. The run that actually
    /// reaches `.done` therefore often had no `go(to:)` of its own, and an in-memory start instant
    /// left `recordOnboardingFinished` with nothing to measure from and nothing to send. Live
    /// evidence: four of the five reporting installs have permissions granted and only one of them
    /// ever sent `cfc_onboarding_finished`. `OnboardingResume` persists the card for exactly the same
    /// reason; this is the same fact about the same relaunch.
    static func noteOnboardingStarted(in defaults: UserDefaults = .standard, at now: Date = Date()) {
        guard defaults.object(forKey: onboardingStartedKey) == nil else { return }
        defaults.set(now.timeIntervalSince1970, forKey: onboardingStartedKey)
    }

    /// The completion this install still owes, or nil — and calling it *spends* the record, so a
    /// second call reports nothing.
    ///
    /// The elapsed time is measured from the first *step transition*, not from app launch: onboarding
    /// opens behind a permission prompt and a sign-in browser hop, and counting the seconds a person
    /// spent in System Settings as time spent in our flow would make every install look slow for a
    /// reason we did not cause. Across a relaunch it is still that instant, which is the honest
    /// answer to "how long did setup cost this person" — including the minutes they spent in System
    /// Settings between the two processes, because those minutes were setup.
    ///
    /// **The reported flag is what makes it once per install rather than once per run.** "Run setup
    /// again" (`OnboardingReset`) deliberately puts a finished install back through the flow, and it
    /// clears the three records that describe *where the user is*; this is not one of them. A second
    /// `cfc_onboarding_finished` from the same install would be counted as a second install setting
    /// itself up, which is the one thing this series is the denominator for.
    static func onboardingFinishedEvent(
        in defaults: UserDefaults = .standard, at now: Date = Date()
    ) -> AnalyticsEvent? {
        guard !defaults.bool(forKey: onboardingReportedKey),
            let started = defaults.object(forKey: onboardingStartedKey) as? Double
        else { return nil }
        defaults.set(true, forKey: onboardingReportedKey)
        defaults.removeObject(forKey: onboardingStartedKey)
        return .onboardingFinished(secondsElapsed: Int(max(0, now.timeIntervalSince1970 - started)))
    }

    // MARK: - Activation

    /// Performs one durable write and reports this install's first artifact **only if it landed**.
    ///
    /// The write is threaded through the report rather than sitting above a call to it, because
    /// "after the write" is an ordering a call site can get wrong in silence: an emit a line too
    /// early, or one that drifted into the `catch` a later refactor added, claims an install as
    /// activated on the strength of an attempt. `EngineStore` catches and logs every failed insert,
    /// so an install whose writes all fail is exactly the install this must not count — and here
    /// there is nowhere to put the emit that a throw does not skip.
    ///
    /// Both call sites are on `EngineStore`'s serial writer queue, so the check-then-set inside
    /// `firstArtifactEvent` cannot interleave with itself: a frame and a transcript line landing in
    /// the same instant are still two turns of one queue. That is the only reason a plain
    /// `UserDefaults` flag is enough here, where the defaults it sits beside are main-actor writes.
    @discardableResult
    static func recordFirstArtifact<Stored>(
        _ kind: AnalyticsEvent.ArtifactKind,
        in defaults: UserDefaults = .standard,
        stored write: () throws -> Stored
    ) rethrows -> Stored {
        let stored = try write()
        if let event = firstArtifactEvent(kind, in: defaults) { record(event) }
        return stored
    }

    /// The decision, and it *spends* the flag: the second call answers nil however it arrives, in
    /// this process or in any later one.
    ///
    /// Spent whether or not the event ends up leaving the Mac — `record` applies the three refusals
    /// after this returns. That ordering is deliberate: it is what lets the rule be proved from a
    /// suite that is itself refused, and the only cost is that a build which reports nothing burns
    /// the flag in its own defaults domain, which is a domain no shipping install reads.
    static func firstArtifactEvent(
        _ kind: AnalyticsEvent.ArtifactKind, in defaults: UserDefaults = .standard
    ) -> AnalyticsEvent? {
        guard !defaults.bool(forKey: firstArtifactKey) else { return nil }
        defaults.set(true, forKey: firstArtifactKey)
        return .firstArtifact(kind)
    }

    // MARK: - Fallbacks

    /// Mirrors a local `ContextTelemetry.recordFallback` into the remote series.
    ///
    /// **This must never be called for an airgap suppression, and the guard is at the caller.**
    /// `record` reports its own refusal through `NetworkEgress.recordSuppression`, which calls
    /// `recordFallback` — so a fallback event that fed back into `record` while airgapped would
    /// recurse until the stack ran out. `ContextTelemetry.recordFallback` drops `airgap-mode` before
    /// it reaches here, which both breaks the cycle and honours the older rule it was written under:
    /// a suppression report must not itself be the disclosure the suppression prevented.
    static func recordFallback(
        area: ContextFallbackArea,
        outcome: ContextFallbackOutcome,
        reason: AnalyticsEvent.FallbackReason
    ) {
        record(.fallback(area: area, outcome: outcome, reason: reason))
    }

    // MARK: - The daily rollup

    /// Emits `cfc_daily_active` if the last one was on an earlier local day.
    ///
    /// **Local calendar day, not a 24-hour window.** DAU is a calendar concept everywhere it is read
    /// — the dashboards, the retention queries, the weekly actives — and a rolling window would drift
    /// against every one of them.
    ///
    /// `force` is for termination, where "the day is not over" is true but irrelevant: the app is
    /// going away and the alternative is losing the day entirely. It still respects the
    /// once-per-day rule, so quitting twice in an evening reports once.
    @MainActor
    static func reportDailyRollupIfDue(force: Bool = false) {
        guard isEnabled else { return }

        let today = Self.dayStamp(for: Date())
        let defaults = UserDefaults.standard
        guard defaults.string(forKey: lastRollupDayKey) != today else { return }

        // Drain first, then mark the day. `ToolCallLedger.drain` is destructive, so a crash between
        // the two re-reports a day rather than losing its tool calls — the recoverable direction.
        let ledger = ToolCallLedger.drain()
        let rollup = DailyRollup(
            toolCalls: ledger.counts,
            captureMinutes: UsageClock.shared.minutes(for: .capture),
            screenMinutes: UsageClock.shared.minutes(for: .screen),
            activeHours: UsageClock.shared.activeHourCount,
            signedIn: OmiAuth.shared.isSignedIn,
            airgapped: NetworkEgress.isAirgapped)

        // An install with nothing at all to say on its first partial day is not a data point, it is
        // noise from a launch that happened at 23:58. Everything else reports, idle included — an
        // ambient app that ran all day and captured nothing is exactly the case the `idle` dimension
        // exists to make visible.
        guard !(force && rollup.isIdle && UsageClock.shared.activeHourCount == 0) else { return }

        defaults.set(today, forKey: lastRollupDayKey)
        record(.dailyActive(rollup))
        UsageClock.shared.reset()
    }

    /// `yyyy-MM-dd` in the machine's own calendar and time zone.
    static func dayStamp(for date: Date, calendar: Calendar = .current) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    // MARK: - Build identity

    private static func currentSuperProperties() -> [String: AnalyticsValue] {
        let info = Bundle.main.infoDictionary
        return AnalyticsPayload.superProperties(
            version: info?["CFBundleShortVersionString"] as? String ?? "unknown",
            build: info?["CFBundleVersion"] as? String ?? "unknown",
            macOSVersion: ProcessInfo.processInfo.operatingSystemVersionString)
    }

    // MARK: - Stored state

    private static let hasLaunchedKey = "context.analytics.hasLaunched"
    private static let lastRollupDayKey = "context.analytics.lastRollupDay"
    /// When this install's first run reached its first step, as seconds since the epoch. Survives the
    /// relaunch the Screen Recording grant forces; see `noteOnboardingStarted`.
    static let onboardingStartedKey = "context.analytics.onboardingStartedAt"
    /// Whether the completion has already been reported. Once per install, never once per run.
    static let onboardingReportedKey = "context.analytics.onboardingFinishedReported"
    /// Whether this install has already reported storing something. Never cleared — an install only
    /// activates once, and a second `cfc_first_artifact` would be a second install in the numerator.
    static let firstArtifactKey = "context.analytics.firstArtifact"

    @MainActor private static var rollupTimer: Timer?
}

/// How long capture actually ran today, and how much of the day it was spread across.
///
/// Wall-clock accumulation rather than a count of start/stop events: "started capture 40 times" and
/// "captured for 40 minutes" are very different products, and only the second one says whether the
/// app is doing its job.
///
/// The hour set is what separates an app left running overnight from one in use — twelve active
/// hours and twelve capture minutes is a person at a desk; one active hour and 600 capture minutes
/// is a laptop that was left open.
final class UsageClock: @unchecked Sendable {
    /// Audio and screen are reported separately because they fail separately: the commonest broken
    /// install has Screen Recording granted and no microphone, and one merged "capture minutes"
    /// would show that as a healthy day.
    enum Channel: String, Sendable { case capture, screen }

    static let shared = UsageClock()

    private let lock = NSLock()
    private var seconds: [Channel: TimeInterval] = [:]
    private var startedAt: [Channel: Date] = [:]
    /// Which sources are live right now, per channel.
    ///
    /// **A set, not a bool.** The microphone and the system-audio tap share the `capture` channel and
    /// start and stop independently: with a bool, a call ending (system audio stops) while the mic
    /// stayed live would close the clock and lose the rest of the day's audio. The channel's clock
    /// runs while *any* of its sources is live and stops when the last one does.
    private var live: [Channel: Set<AnalyticsEvent.CaptureSource>] = [:]
    private var activeHours: Set<Int> = []

    private static func channel(for source: AnalyticsEvent.CaptureSource) -> Channel {
        switch source {
        case .microphone, .systemAudio: return .capture
        case .screen: return .screen
        }
    }

    /// Records that one source went live or stopped.
    func mark(_ source: AnalyticsEvent.CaptureSource, live isLive: Bool, at now: Date = Date()) {
        lock.lock(); defer { lock.unlock() }
        let channel = Self.channel(for: source)
        var sources = live[channel] ?? []

        if isLive {
            sources.insert(source)
            live[channel] = sources
            if startedAt[channel] == nil { startedAt[channel] = now }
        } else {
            sources.remove(source)
            live[channel] = sources
            if sources.isEmpty, let start = startedAt.removeValue(forKey: channel) {
                seconds[channel, default: 0] += max(0, now.timeIntervalSince(start))
            }
        }
        noteHourLocked(now)
    }

    /// Records that something happened, for the active-hours spread. Cheap enough to call from any
    /// event path.
    func noteActivity(at now: Date = Date()) {
        lock.lock(); defer { lock.unlock() }
        noteHourLocked(now)
    }

    private func noteHourLocked(_ now: Date) {
        activeHours.insert(Calendar.current.component(.hour, from: now))
    }

    /// Whole minutes, including any run still in progress — a rollup taken while the mic is live must
    /// not report zero.
    func minutes(for channel: Channel, at now: Date = Date()) -> Int {
        lock.lock(); defer { lock.unlock() }
        var total = seconds[channel] ?? 0
        if let start = startedAt[channel] { total += max(0, now.timeIntervalSince(start)) }
        return Int(total / 60)
    }

    var activeHourCount: Int {
        lock.lock(); defer { lock.unlock() }
        return activeHours.count
    }

    /// Starts the next day's accounting. A channel still running keeps running — its clock restarts
    /// from now, so the minutes it already contributed are not counted twice.
    func reset(at now: Date = Date()) {
        lock.lock(); defer { lock.unlock() }
        seconds.removeAll()
        activeHours.removeAll()
        for channel in startedAt.keys { startedAt[channel] = now }
        noteHourLocked(now)
    }

    #if DEBUG
    /// Tests need a clock with no history. Production has exactly one of these and it lives for the
    /// process, so there is no legitimate non-test caller.
    func resetCompletelyForTesting() {
        lock.lock(); defer { lock.unlock() }
        seconds.removeAll()
        startedAt.removeAll()
        live.removeAll()
        activeHours.removeAll()
    }
    #endif
}
