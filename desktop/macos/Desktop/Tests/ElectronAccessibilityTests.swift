import XCTest

@testable import Omi_Computer

/// Which apps get asked to publish an accessibility tree.
///
/// The question has one right answer per app and getting it wrong is not symmetric:
/// missing an Electron app leaves that surface dark, while asking a Chromium browser
/// achieves nothing because it ignores this attribute entirely.
final class ElectronAccessibilityTests: XCTestCase {
  private func bundle(withFramework framework: String?) throws -> URL {
    let root = URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("electron-detect-\(UUID().uuidString)")
      .appendingPathComponent("Some App.app")
    if let framework {
      try FileManager.default.createDirectory(
        at: root.appendingPathComponent("Contents/Frameworks/\(framework)"),
        withIntermediateDirectories: true)
    } else {
      try FileManager.default.createDirectory(
        at: root.appendingPathComponent("Contents/MacOS"), withIntermediateDirectories: true)
    }
    addTeardownBlock { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }
    return root
  }

  /// The framework the app is built on is inside its bundle, so this is a fact about the
  /// app rather than a guess from its name.
  func testAnAppCarryingTheElectronFrameworkIsElectron() throws {
    XCTAssertTrue(
      ElectronAccessibility.isElectron(try bundle(withFramework: "Electron Framework.framework")))
  }

  /// A Chromium browser ships Chromium, not Electron, and ignores this attribute — asking
  /// it would be a write into another app that buys nothing.
  func testAChromiumBrowserIsNotElectron() throws {
    XCTAssertFalse(
      ElectronAccessibility.isElectron(try bundle(withFramework: "Chromium Framework.framework")))
  }

  func testANativeAppIsNotElectron() throws {
    XCTAssertFalse(ElectronAccessibility.isElectron(try bundle(withFramework: nil)))
  }

  /// An app with no bundle on disk is not something to write into.
  func testAnAppWithNoBundleIsNotElectron() {
    XCTAssertFalse(ElectronAccessibility.isElectron(nil))
    XCTAssertFalse(ElectronAccessibility.isElectron(URL(fileURLWithPath: "/nope/Missing.app")))
  }
}
