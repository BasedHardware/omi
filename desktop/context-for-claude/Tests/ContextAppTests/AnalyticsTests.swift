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
            .updateOutcome(.upToDate),
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
            "cfc_update_outcome", "cfc_fallback",
        ]
        XCTAssertEqual(
            covered, expected,
            "an event case was added without a fixture in everyShape, so the privacy and "
                + "namespacing invariants above are not checking it")
    }
}
