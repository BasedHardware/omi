import XCTest

/// Run only against the synthetic `-omi-siri-probe-spotlight` simulator build.
/// The caller launches the probe and terminates it for a cold test, or sends
/// it to the background for a warm test. This suite is excluded from CI.
final class SpotlightTests: XCTestCase {
    func testTapSyntheticConversation() {
        continueAfterFailure = false
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        XCUIDevice.shared.press(.home)
        let searchPill = springboard.descendants(matching: .any)["spotlight-pill"].firstMatch
        if searchPill.waitForExistence(timeout: 5) { searchPill.tap() }
        else { springboard.swipeDown() }
        let spotlight = XCUIApplication(bundleIdentifier: "com.apple.Spotlight")
        print("SPOTLIGHT_SEARCH_UI: \(spotlight.debugDescription)")
        let search = spotlight.textFields["SpotlightSearchField"].firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10), "Spotlight search did not appear")
        search.tap()
        let clear = search.buttons["Clear text"]
        if clear.exists { clear.tap() }
        search.typeText("Spotlight Omi Probe Conversation")
        Thread.sleep(forTimeInterval: 3)
        let result = spotlight.cells.matching(
            NSPredicate(format: "identifier CONTAINS %@ AND label CONTAINS %@ AND label CONTAINS %@",
                        "ResultCell", "Spotlight Omi Probe Conversation", "Omi Dev")).firstMatch
        print("SPOTLIGHT_RESULTS_UI: \(spotlight.debugDescription)")
        XCTAssertTrue(result.waitForExistence(timeout: 20), "Synthetic conversation was not indexed in Spotlight")
        result.tap()
        let omi = XCUIApplication(bundleIdentifier: "com.omi.spotlightprobe")
        XCTAssertTrue(omi.wait(for: .runningForeground, timeout: 15), "Spotlight did not foreground Omi")
    }
}
