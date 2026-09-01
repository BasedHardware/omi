import Foundation
import XCTest

@testable import Omi_Computer

final class ThreeDoorsDemoPageTests: XCTestCase {
  private func makeTemplateRoot() throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let html = "<title>Three Doors</title><div>Hold " + ThreeDoorsDemoPage.templateKeyMarkup + " and say</div>"
    try Data(html.utf8).write(to: root.appendingPathComponent(ThreeDoorsDemoPage.fileName))
    return root
  }

  func testRendersUsersPushToTalkChordIntoTheOpenedFile() throws {
    // Regression: the chord used to travel in a URL fragment, which Launch Services drops for
    // file: URLs, so a user who chose ⌃ saw ⌥ on the page.
    let root = try makeTemplateRoot()
    let out = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    defer {
      try? FileManager.default.removeItem(at: root)
      try? FileManager.default.removeItem(at: out)
    }

    let url = try XCTUnwrap(
      ThreeDoorsDemoPage.url(locator: OmiSoundAssetLocator(roots: [root]), pttTokens: ["⌃"], outputDirectory: out))
    let rendered = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(rendered.contains(#"<span class="key">⌃</span>"#), rendered)
    XCTAssertFalse(rendered.contains("⌥"), rendered)
    XCTAssertNil(url.fragment)
  }

  func testMultiTokenChordAndHTMLEscaping() {
    XCTAssertEqual(
      ThreeDoorsDemoPage.keyMarkup(for: ["⌘", "<fn>"]),
      #"<span id="keys"><span class="key">⌘</span> <span class="key">&lt;fn&gt;</span></span>"#)
  }

  func testMissingResourceYieldsNil() {
    let empty = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    XCTAssertNil(ThreeDoorsDemoPage.url(locator: OmiSoundAssetLocator(roots: [empty]), pttTokens: ["fn"]))
  }

  func testBundledTemplateContainsTheReplaceableKeyMarkup() throws {
    // Static tripwire, not behavioral: the template must keep the exact markup the renderer replaces.
    let here = URL(fileURLWithPath: #filePath)
    let template = here.deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/\(ThreeDoorsDemoPage.fileName)")
    let html = try String(contentsOf: template, encoding: .utf8)
    XCTAssertTrue(html.contains(ThreeDoorsDemoPage.templateKeyMarkup))
  }
}
