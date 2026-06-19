import XCTest

@testable import Omi_Computer

/// Regression coverage for `APIClient.isAppSetupCompleted(url:uid:)`.
///
/// An empty completion URL means setup cannot be verified, so the method must
/// report `false` (not-completed) — matching its invalid-URL and
/// network-failure paths. A previous `return true` would wrongly mark an
/// unconfigured external integration app as already set up. The empty-URL case
/// short-circuits before any network request, so this needs no HTTP mocking.
final class APIClientSetupCompletedTests: XCTestCase {

    func testEmptyURLReportsNotCompleted() async {
        let completed = await APIClient.shared.isAppSetupCompleted(url: "", uid: "test-uid")
        XCTAssertFalse(completed, "An empty completion URL must report setup as NOT completed")
    }
}
