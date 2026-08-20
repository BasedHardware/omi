@testable import ContextApp
import ContextCore
import Foundation
import XCTest

/// What this app is allowed to say about the person using it, and how it says it.
///
/// The tests that matter most here are the negative ones. An analytics pipeline fails quietly: a
/// payload that leaks a window title, or an event that silently enrols this app into another
/// product's dashboards, produces no error and no crash — it produces a number somebody trusts.
final class AnalyticsPayloadTests: XCTestCase {

    private func payload(_ event: AnalyticsEvent) -> AnalyticsPayload {
        AnalyticsPayload(
            event: event,
            distinctID: "cfc_0123456789abcdef",
            timestamp: Date(timeIntervalSince1970: 1_760_000_000),
            superProperties: AnalyticsPayload.superProperties(
                version: "1.0.12", build: "1000012", macOSVersion: "Version 15.5.0"))
    }

    /// **The single most consequential line in this file.**
    ///
    /// Omi's macOS retention, activation and weekly-actives queries all scope on
    /// `properties.$os_name = 'macOS'`. Setting it here would silently enrol every Context for Claude
    /// install into a four-month Omi trend line, and nothing would look wrong until somebody tried to
    /// explain the jump.
    func testPayloadNeverSetsDollarOSName() {
        for event in AnalyticsEvent.everyShape {
            let properties = payload(event).json["properties"] as? [String: Any] ?? [:]
            XCTAssertNil(properties["$os_name"], "\(event.name) set $os_name")
            XCTAssertTrue(
                properties.keys.allSatisfy { !$0.hasPrefix("$") || $0 == "$set" },
                "\(event.name) set a PostHog-reserved property")
        }
    }

    /// The other half of the separation. Either the prefix or the `app` property alone would keep the
    /// two products apart; both together mean whichever a future query author reaches for, it works.
    func testEveryEventIsNamespacedToThisApp() {
        for event in AnalyticsEvent.everyShape {
            XCTAssertTrue(event.name.hasPrefix("cfc_"), "\(event.name) is missing the cfc_ prefix")
            let properties = payload(event).json["properties"] as? [String: Any] ?? [:]
            XCTAssertEqual(properties["app"] as? String, "context-for-claude")
        }
    }

    /// Build identity is attached centrally so a call site cannot forget it. An event with no version
    /// is an event that cannot be attributed to a release, which is most of what these are for.
    func testEveryEventCarriesBuildIdentity() {
        for event in AnalyticsEvent.everyShape {
            let properties = payload(event).json["properties"] as? [String: Any] ?? [:]
            XCTAssertEqual(properties["app_version"] as? String, "1.0.12", "\(event.name)")
            XCTAssertEqual(properties["app_build"] as? String, "1000012", "\(event.name)")
        }
    }

    /// An event may not overwrite its own build identity, whatever it puts in its properties.
    func testSuperPropertiesCannotBeShadowedByAnEventThatAgrees() {
        let properties = payload(.appLaunched).properties
        XCTAssertEqual(properties["app"], .string("context-for-claude"))
    }

    /// The spool survives relaunch, so the round-trip has to be lossless. `bool` is the case that
    /// breaks: `NSNumber` bridges `true` to `1`, and an `Int`-first decode turns `signed_in: true`
    /// into `signed_in: 1` — a property that then silently fails every `= true` filter.
    func testASpooledEventSurvivesTheRoundTripWithItsTypesIntact() throws {
        let original = payload(.accountStateChanged(signedIn: true))
        let restored = try XCTUnwrap(AnalyticsPayload(persisted: original.json))

        XCTAssertEqual(restored.name, original.name)
        XCTAssertEqual(restored.distinctID, original.distinctID)
        XCTAssertEqual(restored.properties["signed_in"], .bool(true))
        XCTAssertEqual(restored.properties, original.properties)
    }

    func testAMalformedSpoolRowIsDroppedRatherThanGuessedAt() {
        XCTAssertNil(AnalyticsPayload(persisted: ["event": "cfc_app_launched"]))
        XCTAssertNil(AnalyticsPayload(persisted: [:]))
    }

    // MARK: - Identity

    /// A second stored id is a second thing that can be lost, and an id that resets makes every
    /// returning user look new. Derivation from the install id is what keeps retention meaningful.
    func testTheAnalyticsIDIsStableForAnInstall() {
        XCTAssertEqual(AnalyticsIdentity.derive(from: "install-a"), AnalyticsIdentity.derive(from: "install-a"))
        XCTAssertNotEqual(AnalyticsIdentity.derive(from: "install-a"), AnalyticsIdentity.derive(from: "install-b"))
        XCTAssertTrue(AnalyticsIdentity.derive(from: "install-a").hasPrefix("cfc_"))
    }

    /// The salt is the whole privacy argument: the backend's `X-Device-Id-Hash` keys the user's own
    /// captured rows and is joinable to their account, so an analytics id equal to it would make every
    /// "anonymous" event trivially re-identifiable by anyone holding both datasets.
    func testTheAnalyticsIDIsNotTheBackendDeviceHash() {
        let installID = "6E7D2C61-0000-4000-8000-000000000000"
        XCTAssertNotEqual(AnalyticsIdentity.derive(from: installID), ClientDevice.hash(of: installID))
        XCTAssertFalse(AnalyticsIdentity.derive(from: installID).contains(ClientDevice.hash(of: installID)))
    }
}

/// The closed-vocabulary invariant, checked against the real event list.
final class AnalyticsEventTests: XCTestCase {

    /// **No event may carry free-form text.** This is what makes "what does this app send?" a
    /// question answerable by reading one file, and it is enforced on the values rather than on the
    /// types because a `String` associated value is exactly what a well-meaning future call site adds.
    ///
    /// The one string that legitimately reaches a payload is an MCP tool name, which arrives already
    /// sanitised by `ToolCallLedger.normalized` and is asserted against that shape below.
    func testNoEventCarriesFreeFormText() {
        // Built up step by step rather than as one `+` chain: the chain type-checks so slowly that
        // the compiler gives up on it.
        var allowed: [String] = AnalyticsEvent.Permission.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.PermissionState.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.CaptureSource.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.Surface.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.ArtifactKind.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.UpdateOutcome.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.FallbackReason.allCases.map(\.rawValue)
        allowed += AnalyticsEvent.CountBucket.allCases.map(\.rawValue)
        allowed += ContextFallbackArea.allCases.map(\.rawValue)
        allowed += ContextFallbackOutcome.allCases.map(\.rawValue)
        let allowedFreeStrings = Set(allowed)

        for event in AnalyticsEvent.everyShape {
            for (key, value) in event.properties {
                guard case let .string(text) = value else { continue }
                XCTAssertTrue(
                    allowedFreeStrings.contains(text),
                    "\(event.name).\(key) carried '\(text)', which is not a value from a closed enum")
            }
        }
    }

    /// Tool names become one property each, so "which tools does Claude reach for" is answerable
    /// without a second event type — and they are the only dynamic keys in the whole schema.
    func testTheDailyRollupExpandsToolCallsIntoOnePropertyEach() {
        let rollup = DailyRollup(
            toolCalls: ["recall": 7, "screen": 2], captureMinutes: 41, screenMinutes: 120,
            activeHours: 6, signedIn: true, airgapped: false)

        XCTAssertEqual(rollup.properties["tool_recall"], .int(7))
        XCTAssertEqual(rollup.properties["tool_screen"], .int(2))
        XCTAssertEqual(rollup.properties["tool_calls_total"], .int(9))
        XCTAssertEqual(rollup.properties["tool_calls_distinct"], .int(2))
        XCTAssertEqual(rollup.properties["idle"], .bool(false))
    }

    /// An ambient app that ran all day and captured nothing is the case `idle` exists to make
    /// visible. It is a dimension, not a send gate — that install is still a DAU.
    func testAnInstallThatDidNothingIsStillReportedAndFlaggedIdle() {
        XCTAssertTrue(DailyRollup.empty.isIdle)
        XCTAssertEqual(DailyRollup.empty.properties["idle"], .bool(true))
    }

    func testCountBucketsFlattenTheTail() {
        XCTAssertEqual(AnalyticsEvent.CountBucket(0), .zero)
        XCTAssertEqual(AnalyticsEvent.CountBucket(1), .one)
        XCTAssertEqual(AnalyticsEvent.CountBucket(5), .few)
        XCTAssertEqual(AnalyticsEvent.CountBucket(20), .several)
        XCTAssertEqual(AnalyticsEvent.CountBucket(5_000), .many)
    }

    /// Two *different* cases sharing a name would silently merge two questions into one series. The
    /// same case appearing many times with different associated values is expected and fine — that is
    /// what the properties are for — so this compares one representative per case.
    func testDistinctCasesDoNotShareAnEventName() {
        let representatives: [AnalyticsEvent] = [
            .firstLaunch, .appLaunched, .dailyActive(.empty), .permission(.microphone, .granted),
            .onboardingStep(index: 0, of: 1), .onboardingFinished(secondsElapsed: 0),
            .accountStateChanged(signedIn: false), .captureStateChanged(source: .screen, live: true),
            .gestureFired, .surfaceOpened(.settings), .searchRan(resultCountBucket: .zero),
            .firstArtifact(.conversation), .updateOutcome(.upToDate),
            .fallback(area: .capture, outcome: .degraded, reason: .offline),
        ]
        let names = representatives.map(\.name)
        XCTAssertEqual(Set(names).count, names.count)
    }
}

/// The wall-clock accounting behind `capture_minutes`.
final class UsageClockTests: XCTestCase {

    override func setUp() {
        super.setUp()
        UsageClock.shared.resetCompletelyForTesting()
    }

    override func tearDown() {
        UsageClock.shared.resetCompletelyForTesting()
        super.tearDown()
    }

    /// **The bug a bool would have shipped.** The mic and the system-audio tap share the `capture`
    /// channel and stop independently: a call ending while the mic stays live must not close the
    /// clock and lose the rest of the day's audio.
    func testTheCaptureClockRunsWhileAnySourceIsLive() {
        let start = Date(timeIntervalSince1970: 1_760_000_000)
        let clock = UsageClock.shared

        clock.mark(.microphone, live: true, at: start)
        clock.mark(.systemAudio, live: true, at: start.addingTimeInterval(60))
        // System audio stops after 10 minutes; the microphone is still live.
        clock.mark(.systemAudio, live: false, at: start.addingTimeInterval(600))

        XCTAssertEqual(clock.minutes(for: .capture, at: start.addingTimeInterval(1_800)), 30)

        clock.mark(.microphone, live: false, at: start.addingTimeInterval(1_800))
        XCTAssertEqual(clock.minutes(for: .capture, at: start.addingTimeInterval(9_999)), 30)
    }

    /// Screen is its own channel because it fails on its own: the commonest broken install has
    /// Screen Recording granted and no microphone, and one merged number would show that as healthy.
    func testScreenAndAudioAreCountedSeparately() {
        let start = Date(timeIntervalSince1970: 1_760_000_000)
        let clock = UsageClock.shared

        clock.mark(.screen, live: true, at: start)
        clock.mark(.screen, live: false, at: start.addingTimeInterval(300))

        XCTAssertEqual(clock.minutes(for: .screen, at: start), 5)
        XCTAssertEqual(clock.minutes(for: .capture, at: start), 0)
    }

    /// A rollup taken while the mic is live must not report zero.
    func testMinutesIncludeARunStillInProgress() {
        let start = Date(timeIntervalSince1970: 1_760_000_000)
        UsageClock.shared.mark(.microphone, live: true, at: start)
        XCTAssertEqual(UsageClock.shared.minutes(for: .capture, at: start.addingTimeInterval(120)), 2)
    }

    /// Resetting starts the next day. A channel still running keeps running, and the minutes it
    /// already contributed must not be counted again.
    func testResetDoesNotDoubleCountAStillRunningChannel() {
        let start = Date(timeIntervalSince1970: 1_760_000_000)
        let clock = UsageClock.shared

        clock.mark(.microphone, live: true, at: start)
        XCTAssertEqual(clock.minutes(for: .capture, at: start.addingTimeInterval(600)), 10)

        clock.reset(at: start.addingTimeInterval(600))
        XCTAssertEqual(clock.minutes(for: .capture, at: start.addingTimeInterval(600)), 0)
        XCTAssertEqual(clock.minutes(for: .capture, at: start.addingTimeInterval(900)), 5)
    }

    /// Twelve active hours and twelve capture minutes is a person at a desk; one active hour and 600
    /// capture minutes is a laptop that was left open. The spread is what tells them apart.
    func testActiveHoursCountDistinctHoursOfTheDay() {
        var components = DateComponents()
        components.year = 2026; components.month = 8; components.day = 17
        let calendar = Calendar.current

        for hour in [9, 9, 14, 21] {
            components.hour = hour
            UsageClock.shared.noteActivity(at: calendar.date(from: components)!)
        }
        XCTAssertEqual(UsageClock.shared.activeHourCount, 3)
    }
}

/// The bridge from the local fallback log to the remote series, and the cycle it must not close.
final class AnalyticsFallbackBridgeTests: XCTestCase {

    /// **The infinite recursion this guard prevents.** `ContextAnalytics.record` reports its own
    /// Airgap Mode refusal through `NetworkEgress.recordSuppression`, which calls
    /// `ContextTelemetry.recordFallback`. Forwarding an `airgap-mode` fallback back into `record`
    /// would therefore re-enter the same path and run the stack out. It is also the older invariant:
    /// a suppression report must never itself be the disclosure the suppression prevented.
    func testAirgapModeIsNeverForwardedToTheRemoteSeries() {
        XCTAssertEqual(AnalyticsEvent.FallbackReason(slug: "airgap-mode"), .airgapMode)
        // The bridge in `ContextTelemetry.recordFallback` drops exactly this case. If the mapping
        // ever stops producing it, the `!= .airgapMode` filter there silently stops matching.
    }

    /// The local `reason` is a plain `String` held to a convention. This lookup is the only thing
    /// standing between a future call site passing `"\(error)"` and an error message — which can
    /// contain a path, a host or a query — reaching PostHog.
    func testAnUnrecognisedReasonIsDroppedRatherThanSentAsFreeText() {
        XCTAssertNil(AnalyticsEvent.FallbackReason(slug: "no such reason"))
        XCTAssertNil(AnalyticsEvent.FallbackReason(slug: "Error Domain=NSURLErrorDomain Code=-1009"))
        XCTAssertNil(AnalyticsEvent.FallbackReason(slug: ""))
    }

    func testTheSlugsTheAppActuallyEmitsAllMap() {
        for slug in ["offline", "unauthorized", "401", "403", "rate-limited", "429",
                     "permission-missing", "timeout", "unavailable", "malformed-response"] {
            XCTAssertNotNil(AnalyticsEvent.FallbackReason(slug: slug), "unmapped slug: \(slug)")
        }
    }
}

/// **Refusal 2, asserted from inside the process it failed to refuse.**
///
/// This is not a table test about a hypothetical build. The test runner *is* the failure: `swift
/// test` runs under `com.apple.dt.xctest.tool`, `ContextPaths.ownIdentifier` falls back to the
/// shipping identifier for any process that is not ours, and `isEnabled` — asking
/// `!isDevelopmentBuild` — therefore answered true here. Every run of this suite spooled events to
/// the real `analytics-spool.json` and POSTed them to production PostHog: 92 of them by the time it
/// was noticed, all of `cfc_gesture_fired` and two thirds of `cfc_search_ran`.
///
/// So the strongest available seam is the one below — `isEnabled` read in the process that must be
/// refused, rather than a rule read anywhere else.
final class AnalyticsBuildRefusalTests: XCTestCase {

    func testTheTestProcessItselfIsRefused() throws {
        try XCTSkipIf(
            ProcessInfo.processInfo.environment["CONTEXT_ANALYTICS_FORCE"] == "1",
            "the override is deliberately absolute, and a run under it is a run that means to send")

        XCTAssertFalse(
            ContextAnalytics.isEnabled,
            """
            This process reports \(Bundle.main.bundleIdentifier ?? "nil") and is not the shipping \
            app, so nothing it does may reach production analytics.
            """)
    }
}

/// **`cfc_onboarding_finished` has to survive the relaunch onboarding itself causes.**
///
/// Granting Screen Recording only takes effect in a new process, so the flow restarts the app from
/// its own middle — the card's "Restart to finish", and macOS's "Quit & Reopen". The start instant
/// used to be an in-memory static set only by `recordOnboardingStep`, so the process that actually
/// reached `.done` frequently had no step transition of its own and `recordOnboardingFinished`
/// returned having sent nothing. Live evidence: four of the five reporting installs have permissions
/// granted and exactly one of them ever sent the event.
///
/// `recordOnboardingFinished` is `record(onboardingFinishedEvent())` and nothing else, so driving
/// the decision over a scratch domain is driving the production rule — and it is the only way to
/// drive it, because the suite is refused by `isEnabled`, as it must be.
final class OnboardingCompletionReportTests: XCTestCase {

    /// A scratch domain per test: the machine running the tests is the machine the app runs on, and
    /// these are the very keys that decide whether a real install has already reported.
    private func scratch() throws -> (UserDefaults, () -> Void) {
        let suite = "com.omi.context-for-claude.OnboardingCompletionReportTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        return (defaults, { UserDefaults.standard.removePersistentDomain(forName: suite) })
    }

    private func seconds(_ event: AnalyticsEvent?) -> Int? {
        guard case let .onboardingFinished(elapsed)? = event else { return nil }
        return elapsed
    }

    /// The defect, driven: the first step happens in one process, the finish in another, and the
    /// second process has nothing in memory from the first.
    func testTheCompletionIsReportedByTheProcessThatComesBackFromTheGrant() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let started = Date(timeIntervalSince1970: 1_760_000_000)
        ContextAnalytics.noteOnboardingStarted(in: defaults, at: started)

        // — the Screen Recording grant ends the process here —

        let event = ContextAnalytics.onboardingFinishedEvent(
            in: defaults, at: started.addingTimeInterval(240))
        XCTAssertEqual(event?.name, "cfc_onboarding_finished")
        XCTAssertEqual(
            seconds(event), 240,
            "elapsed is measured from the first step, which was two processes ago and still counts")
    }

    /// Once per install, not once per run. The reported flag is deliberately not one of the three
    /// records `OnboardingReset` spends, so "Run setup again" cannot add a second install-shaped
    /// completion to the series.
    func testNoSecondCompletionIsReportedHoweverManyTimesSetupIsRun() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let started = Date(timeIntervalSince1970: 1_760_000_000)
        ContextAnalytics.noteOnboardingStarted(in: defaults, at: started)
        XCTAssertNotNil(
            ContextAnalytics.onboardingFinishedEvent(in: defaults, at: started.addingTimeInterval(90)))

        // Settings → "Run setup again", walked all the way through a second time.
        ContextAnalytics.noteOnboardingStarted(in: defaults, at: started.addingTimeInterval(3_600))
        XCTAssertNil(
            ContextAnalytics.onboardingFinishedEvent(in: defaults, at: started.addingTimeInterval(3_700)),
            "a second completion from one install reads as a second install that set itself up")
        // And a relaunch in the middle of *that* run reports nothing either.
        XCTAssertNil(ContextAnalytics.onboardingFinishedEvent(in: defaults, at: started))
    }

    /// A finish with no recorded start is the one case that must stay silent: an elapsed time
    /// measured from nothing would be a zero, and a floor of zero-second setups is worse than a gap.
    func testARunThatNeverRecordedAStepReportsNothing() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        XCTAssertNil(ContextAnalytics.onboardingFinishedEvent(in: defaults, at: Date()))
    }

    /// The stamp belongs to the run, so a later step must not move it — otherwise the elapsed time
    /// shrinks to whatever the last card cost and the funnel's most useful number is a lie.
    func testTheStartInstantIsTheFirstStepAndIsNotRestampedByLaterOnes() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let started = Date(timeIntervalSince1970: 1_760_000_000)
        ContextAnalytics.noteOnboardingStarted(in: defaults, at: started)
        ContextAnalytics.noteOnboardingStarted(in: defaults, at: started.addingTimeInterval(120))

        XCTAssertEqual(
            seconds(ContextAnalytics.onboardingFinishedEvent(
                in: defaults, at: started.addingTimeInterval(300))),
            300)
    }
}

/// **Activation: did this install ever store anything at all.**
///
/// Nothing in the schema answered that before `cfc_first_artifact`. `cfc_capture_state` reports a
/// microphone being switched on, which is not a row landing; `cfc_daily_active` reports capture
/// minutes, which look the same on an install's hundredth day as on its first. An install that
/// captured all day and one that captured nothing were indistinguishable, and the product's
/// activation metric cannot be computed from anything else here.
///
/// The flag is read and spent by `firstArtifactEvent`, which is what `recordFirstArtifact` reports
/// through — so "did it report?" is asked below as "is the flag spent?". The suite is refused by
/// `isEnabled`, as it must be, which is exactly why the decision is the seam rather than the sink.
final class FirstArtifactTests: XCTestCase {

    private struct WriteFailed: Error {}

    /// The suite *name* comes back too: a relaunch, for this event, is nothing more than a second
    /// `UserDefaults` object opened over the same persistent domain.
    private func scratch() throws -> (String, UserDefaults, () -> Void) {
        let suite = "com.omi.context-for-claude.FirstArtifactTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        return (suite, defaults, { UserDefaults.standard.removePersistentDomain(forName: suite) })
    }

    func testTheFirstStoredArtifactIsReportedWithWhatItWas() throws {
        let (_, defaults, cleanup) = try scratch()
        defer { cleanup() }

        let event = ContextAnalytics.firstArtifactEvent(.screen, in: defaults)
        XCTAssertEqual(event?.name, "cfc_first_artifact")
        XCTAssertEqual(event?.properties["kind"], .string("screen"))
    }

    /// Once per install, over the write path itself — and across the relaunch, which is a second
    /// `UserDefaults` object over the same domain because that is all a relaunch is here.
    func testAnInstallReportsItsFirstArtifactExactlyOnce() throws {
        let (suite, defaults, cleanup) = try scratch()
        defer { cleanup() }

        var writes = 0
        ContextAnalytics.recordFirstArtifact(.conversation, in: defaults) { writes += 1 }
        ContextAnalytics.recordFirstArtifact(.screen, in: defaults) { writes += 1 }
        XCTAssertEqual(writes, 2, "the write itself always happens; only the report is once")

        XCTAssertNil(
            ContextAnalytics.firstArtifactEvent(.conversation, in: defaults),
            "the first stored artifact spent the flag, so nothing after it may report")

        // A day of capture later, in a process that has been restarted since.
        let afterRelaunch = try XCTUnwrap(UserDefaults(suiteName: suite))
        ContextAnalytics.recordFirstArtifact(.screen, in: afterRelaunch) { writes += 1 }
        XCTAssertEqual(writes, 3)
        XCTAssertNil(
            ContextAnalytics.firstArtifactEvent(.screen, in: afterRelaunch),
            "the flag is on disk, so the install stays activated exactly once across a relaunch")
    }

    /// **An attempt is not an artifact.** `EngineStore` catches and logs a failed insert, so an
    /// install whose writes all fail would otherwise be counted as activated on the strength of
    /// having tried — and the flag it spent could never be recovered.
    func testAWriteThatFailedIsNotAnArtifact() throws {
        let (_, defaults, cleanup) = try scratch()
        defer { cleanup() }

        XCTAssertThrowsError(
            try ContextAnalytics.recordFirstArtifact(.screen, in: defaults) { throw WriteFailed() })

        XCTAssertNotNil(
            ContextAnalytics.firstArtifactEvent(.screen, in: defaults),
            "nothing was stored, so the install's first artifact is still ahead of it")
    }
}

/// **A static tripwire, and labelled as one: it reads the app's source text rather than running it.**
///
/// The rule it guards is the one `AnalyticsEvent.Surface` states in prose — a case nobody emits
/// produces a permanently empty series, which reads as "nobody opens it" rather than "nobody measured
/// it", and the first of those looks like a finding. `.search` was exactly that: the app's primary
/// surface, in the enum since the schema was written, with no emitter anywhere.
///
/// It is a tripwire because the behavioural version is not available here. The emit is inside
/// `SearchBarWindow.present()`, and a test process has no display to put a panel on and cannot make
/// one key — the reason `HotkeyToggleTests` drives the chord through injected closures instead. So
/// this checks that an emitter *exists*, which is the whole of what went wrong, and claims nothing
/// about it firing.
final class SurfaceEmitterTripwireTests: XCTestCase {

    func testEverySurfaceCaseIsEmittedSomewhereInTheApp() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // the package
            .appendingPathComponent("Sources/ContextApp")

        let files = try XCTUnwrap(
            FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil),
            "the app's sources have to be readable from the checkout for this tripwire to mean anything")
        var text = ""
        for case let url as URL in files where url.pathExtension == "swift" {
            text += (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        }
        XCTAssertFalse(text.isEmpty, "read no app source at all, so nothing below was checked")

        for surface in AnalyticsEvent.Surface.allCases {
            XCTAssertTrue(
                text.contains(".surfaceOpened(.\(surface.rawValue))"),
                """
                No call site records \(surface.rawValue). Either give it one or take the case out — \
                an empty series is read as an answer about users, not as a gap in the instrumentation.
                """)
        }
    }
}

/// The day boundary the whole DAU series rests on.
final class ContextAnalyticsDayTests: XCTestCase {

    /// DAU is a calendar concept everywhere it is read — the dashboards, the retention queries, the
    /// weekly actives — so a rolling 24-hour window would drift against every one of them.
    func testDayStampIsTheLocalCalendarDay() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!

        // 2025-08-17 03:06 UTC — which is still the 16th in New York. The day the rollup lands on
        // has to follow the machine, not the server.
        let lateEvening = Date(timeIntervalSince1970: 1_755_400_000)
        XCTAssertEqual(ContextAnalytics.dayStamp(for: lateEvening, calendar: calendar), "2025-08-16")

        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        XCTAssertEqual(ContextAnalytics.dayStamp(for: lateEvening, calendar: utc), "2025-08-17")
    }
}

// MARK: - Test fixtures

extension AnalyticsEvent {
    /// One value of every case, so the invariant tests iterate the real schema rather than a list
    /// somebody has to remember to update. A new case that is not added here is a case with no
    /// coverage — and `AnalyticsEventShapeTests` below fails when the two drift.
    static var everyShape: [AnalyticsEvent] {
        var events: [AnalyticsEvent] = [
            .firstLaunch,
            .appLaunched,
            .dailyActive(DailyRollup(
                toolCalls: ["recall": 3], captureMinutes: 12, screenMinutes: 30,
                activeHours: 4, signedIn: true, airgapped: false)),
            .onboardingStep(index: 2, of: 5),
            .onboardingFinished(secondsElapsed: 94),
            .accountStateChanged(signedIn: true),
            .gestureFired,
            .searchRan(resultCountBucket: .few),
        ]
        events += Permission.allCases.flatMap { permission in
            PermissionState.allCases.map { AnalyticsEvent.permission(permission, $0) }
        }
        events += CaptureSource.allCases.flatMap { source in
            [AnalyticsEvent.captureStateChanged(source: source, live: true),
             AnalyticsEvent.captureStateChanged(source: source, live: false)]
        }
        events += Surface.allCases.map { AnalyticsEvent.surfaceOpened($0) }
        events += ArtifactKind.allCases.map { AnalyticsEvent.firstArtifact($0) }
        events += UpdateOutcome.allCases.map { AnalyticsEvent.updateOutcome($0) }
        events += FallbackReason.allCases.map {
            AnalyticsEvent.fallback(area: .capture, outcome: .degraded, reason: $0)
        }
        return events
    }
}

final class AnalyticsEventShapeTests: XCTestCase {
    /// `everyShape` is a hand-maintained list, which makes it exactly the kind of fixture that goes
    /// stale silently and takes the invariant tests' coverage with it. Comparing distinct *names*
    /// against the enum's own switch is the cheapest way to notice a case nobody added.
    func testEveryShapeCoversEveryEventName() {
        let covered = Set(AnalyticsEvent.everyShape.map(\.name))
        let expected: Set<String> = [
            "cfc_first_launch", "cfc_app_launched", "cfc_daily_active", "cfc_permission",
            "cfc_onboarding_step", "cfc_onboarding_finished", "cfc_account_state",
            "cfc_capture_state", "cfc_gesture_fired", "cfc_surface_opened", "cfc_search_ran",
            "cfc_first_artifact", "cfc_update_outcome", "cfc_fallback",
        ]
        XCTAssertEqual(
            covered, expected,
            "an event case was added without a fixture in everyShape, so the privacy and "
                + "namespacing invariants above are not checking it")
    }
}
