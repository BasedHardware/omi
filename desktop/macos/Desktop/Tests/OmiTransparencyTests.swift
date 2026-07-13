import AppKit
import XCTest
import OmiTheme

@testable import Omi_Computer

final class OmiTransparencyTests: XCTestCase {
  func testMaterialIsUsedWhenTransparencyIsAllowed() {
    XCTAssertTrue(OmiTransparency.shouldUseMaterial(reduceTransparency: false))
  }

  func testOpaqueFallbackIsUsedWhenTransparencyIsReduced() {
    XCTAssertFalse(OmiTransparency.shouldUseMaterial(reduceTransparency: true))
  }

  @MainActor
  func testMainWindowSupportsBehindWindowMaterialWithoutLosingShadow() {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1200, height: 800),
      styleMask: [.titled, .closable, .resizable],
      backing: .buffered,
      defer: false
    )
    window.isOpaque = true
    window.backgroundColor = .black
    window.hasShadow = false

    MainWindowBackdrop.configure(window)

    XCTAssertFalse(window.isOpaque)
    XCTAssertEqual(window.backgroundColor, .clear)
    XCTAssertTrue(window.hasShadow)
    XCTAssertTrue(window.styleMask.contains(.titled))
  }
}
