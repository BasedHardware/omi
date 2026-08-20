import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

final class DesktopHomeWindowSizingTests: XCTestCase {
  @MainActor
  func testReassertionDisablesAutomaticHostingSizeComputation() {
    let host = NSHostingView(
      rootView: Text("Settings").frame(minWidth: 900, minHeight: 600)
    )
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 900, height: 600),
      styleMask: [.titled, .resizable],
      backing: .buffered,
      defer: false
    )
    window.title = "omi sizing regression"
    window.contentView = host

    XCTAssertNotEqual(host.sizingOptions, [])

    DesktopHomeView.reassertMainWindowSizing(in: [window])

    XCTAssertEqual(host.sizingOptions, [])
    XCTAssertEqual(window.contentMinSize, DesktopWindowLayoutPolicy.minimumContentSize)
    XCTAssertEqual(window.contentMaxSize.width, DesktopWindowLayoutPolicy.maximumContentWidth)
  }

  func testChatFirstRouteChangeReassertsWindowSizing() throws {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
    // omi-test-quality: source-inspection -- static contract: private SwiftUI route wiring has no runtime accessor; the AppKit effect is exercised above with a real NSWindow and NSHostingView.
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    let routeObserver = try XCTUnwrap(
      source.range(of: ".onChange(of: chatFirstNavigation.route)"),
      "Chat-first route changes need an explicit sizing reassertion hook"
    )
    let suffix = source[routeObserver.lowerBound...]
    let observerEnd = suffix.range(of: "\n      }")?.upperBound ?? suffix.endIndex
    XCTAssertTrue(
      suffix[..<observerEnd].contains("enforceMainWindowMinimumSize()"),
      "Chat-first navigation must restore the hosting-size guard just like legacy navigation"
    )
  }
}
