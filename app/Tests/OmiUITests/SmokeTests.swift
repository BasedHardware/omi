import AppKit
import OmiKit
import SwiftUI
import XCTest

@testable import OmiUI

@MainActor
final class SmokeTests: XCTestCase {
    func testAppStoreRouteSelection() {
        let store = AppStore()
        XCTAssertEqual(store.route, .home)
        store.navigate(.tasks)
        XCTAssertEqual(store.route, .tasks)
        XCTAssertEqual(store.mobileRoute, .tasks)
        XCTAssertEqual(MobileRoute(store.route), .tasks)
        store.navigate(mobileRoute: .apps)
        XCTAssertEqual(store.mobileRoute, .apps)
        XCTAssertEqual(store.mobileRoute.appRoute, .connectors)
    }

    func testRootViewRendersWithoutCrashing() {
        // Real layout pass through a hosting view: the desktop surface is
        // selected and the injected store is read.
        let host = NSHostingView(
            rootView: RootView().environmentObject(AppStore()))
        host.frame = NSRect(x: 0, y: 0, width: 1_020, height: 720)
        host.layoutSubtreeIfNeeded()
        XCTAssertFalse(host.bounds.isEmpty)
    }
}
