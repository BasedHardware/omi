import Foundation
import XCTest

@testable import Omi_Computer

final class ThreeDoorsDemoPageTests: XCTestCase {
  private func makeTemplateRoot() throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let html =
      "<title>Three Doors</title><div>Hold " + ThreeDoorsDemoPage.templateKeyMarkup + " and say</div><div "
      + ThreeDoorsDemoPage.templateReturnMarkup + "></div>"
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
      ThreeDoorsDemoPage.url(
        locator: OmiSoundAssetLocator(roots: [root]), pttTokens: ["⌃"], urlScheme: "omi-test", outputDirectory: out))
    let rendered = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(rendered.contains(#"<span class="key">⌃</span>"#), rendered)
    XCTAssertTrue(rendered.contains(#"data-return="omi-test://onboarding/doors-complete""#), rendered)
    XCTAssertTrue(ThreeDoorsDemoPage.isReturnURL(URL(string: "omi-test://onboarding/doors-complete")!))
    XCTAssertFalse(ThreeDoorsDemoPage.isReturnURL(URL(string: "omi-test://auth/callback?code=x")!))
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

  func testModelNoteMatchesTheBundledRiddles() throws {
    // The kernel fallback note must describe the same riddles the page shows.
    let here = URL(fileURLWithPath: #filePath)
    let template = here.deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/\(ThreeDoorsDemoPage.fileName)")
    // omi-test-quality: source-inspection -- static contract: bundled riddle copy is HTML the renderer never returns
    let html = try String(contentsOf: template, encoding: .utf8)
    for phrase in [
      "I have keys but open no locks", "Which planet has a day longer than its year", "last word of the first riddle",
    ] {
      XCTAssertTrue(html.contains(phrase), phrase)
      XCTAssertTrue(ThreeDoorsDemoPage.modelNote.contains(phrase), phrase)
    }
    XCTAssertTrue(ThreeDoorsDemoPage.modelNote.contains("(answer: inside)"))
    XCTAssertTrue(ThreeDoorsDemoPage.modelNote.contains("Never assume it is door 1"))
  }

  func testBundledTemplateContainsTheReplaceableKeyMarkup() throws {
    // Static tripwire, not behavioral: the template must keep the exact markup the renderer replaces.
    let here = URL(fileURLWithPath: #filePath)
    let template = here.deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/\(ThreeDoorsDemoPage.fileName)")
    // omi-test-quality: source-inspection -- static contract: replaceable template tokens are markup the renderer never returns
    let html = try String(contentsOf: template, encoding: .utf8)
    XCTAssertTrue(html.contains(ThreeDoorsDemoPage.templateKeyMarkup))
    XCTAssertTrue(html.contains(ThreeDoorsDemoPage.templateReturnMarkup))
  }
}
