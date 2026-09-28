import OmiKit
import XCTest

@testable import OmiUI

@MainActor
final class SmokeTests: XCTestCase {
    func testAppModelRouteSelection() {
        let model = AppModel()
        XCTAssertEqual(model.route, .home)
        model.select(.tasks)
        XCTAssertEqual(model.route, .tasks)
        XCTAssertEqual(model.route.route, Route.Tasks)
        model.updateSignedIn(true)
        XCTAssertTrue(model.signedIn)
    }

    func testRootViewRendersWithoutCrashing() {
        let view = RootView(model: AppModel())
        // Headless smoke: body builder executes without throwing.
        _ = view.body
    }
}
