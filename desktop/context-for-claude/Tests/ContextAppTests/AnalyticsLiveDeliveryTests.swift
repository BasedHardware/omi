@testable import ContextApp
import Foundation
import XCTest

/// The one test in this package that touches the network, and it is skipped unless asked for.
///
/// ## Why it exists
///
/// Everything else about the sink is proven against a transport double: batching, retry, drop rules,
/// spool durability. None of that proves the thing that actually has to be true — that a payload this
/// app builds is *accepted by PostHog and appears in the project*. A wrong token, a rejected property
/// shape, a batch envelope PostHog silently discards: every one of those passes the offline suite and
/// produces zero events forever, with no error anywhere.
///
/// That failure mode is not hypothetical in this codebase. Omi's backend has had no PostHog key
/// configured for months; the client fails open, every server-side product event is dropped, and it
/// took a three-attempt investigation into an impossible-looking activation rate to notice. The
/// lesson is that an analytics pipeline nobody has watched deliver should be assumed dead.
///
/// ## Why it is skipped by default
///
/// CI tests must be hermetic, and this one needs a live service. It also *writes to production
/// analytics* — the events it sends are real events in the real project, tagged `smoke_test` so they
/// can be excluded from a query, but present. Running it on every commit would slowly fill the
/// project with noise.
///
/// ## Running it
///
/// ```
/// CONTEXT_ANALYTICS_LIVE_TEST=1 swift test --filter AnalyticsLiveDeliveryTests
/// ```
///
/// Then confirm arrival, which this test deliberately does *not* do — the ingest API returns 200
/// before the event is queryable, so an assertion on read-back would be a race, and a sleep long
/// enough to win it would be a slow test that still occasionally lied:
///
/// ```sql
/// SELECT event, properties.smoke_run, timestamp FROM events
/// WHERE properties.app = 'context-for-claude' AND properties.smoke_test = true
/// ORDER BY timestamp DESC LIMIT 20
/// ```
final class AnalyticsLiveDeliveryTests: XCTestCase {

    func testPostHogAcceptsARealPayload() async throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_ANALYTICS_LIVE_TEST"] == "1",
            "live delivery test — set CONTEXT_ANALYTICS_LIVE_TEST=1 to run it")

        // A distinct id that is obviously not an install, so this can never be mistaken for a user.
        let runID = UUID().uuidString.prefix(8).lowercased()
        var payload = AnalyticsPayload(
            event: .appLaunched,
            distinctID: "cfc_smoketest_\(runID)",
            timestamp: Date(),
            superProperties: AnalyticsPayload.superProperties(
                version: "0.0.0-smoke", build: "0", macOSVersion: "smoke-test"))
        payload = payload.taggedAsSmokeTest(run: String(runID))

        let accepted = await URLSessionAnalyticsTransport().send(
            [payload], token: AnalyticsSink.projectToken, to: AnalyticsSink.endpoint)

        XCTAssertTrue(accepted, "PostHog rejected a payload this app would really send")
        print("[live] sent smoke_run=\(runID) — query PostHog for properties.smoke_run = '\(runID)'")
    }
}

private extension AnalyticsPayload {
    /// Marks a payload as coming from the smoke test, so real usage queries can exclude it.
    func taggedAsSmokeTest(run: String) -> AnalyticsPayload {
        var tagged = properties
        tagged["smoke_test"] = .bool(true)
        tagged["smoke_run"] = .string(run)
        var row = json
        row["properties"] = tagged.mapValues(\.json).merging(["distinct_id": distinctID]) { a, _ in a }
        return AnalyticsPayload(persisted: row)!
    }
}
