import Foundation
import XCTest

@testable import Omi_Computer

final class ThreeDoorsDemoPageTests: XCTestCase {
  func testURLCarriesPushToTalkChordInFragmentAndResolvesBundledFile() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try Data("<title>Three Doors</title>".utf8).write(to: root.appendingPathComponent(ThreeDoorsDemoPage.fileName))

    let url = try XCTUnwrap(
      ThreeDoorsDemoPage.url(locator: OmiSoundAssetLocator(roots: [root]), pttTokens: ["⌥"]))
    XCTAssertEqual(url.lastPathComponent, ThreeDoorsDemoPage.fileName)
    // Foundation reports the fragment percent-encoded exactly once.
    XCTAssertEqual(url.fragment, "key=%E2%8C%A5")
    XCTAssertEqual(url.fragment?.removingPercentEncoding, "key=⌥")
  }

  func testMissingResourceYieldsNil() {
    let empty = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    XCTAssertNil(ThreeDoorsDemoPage.url(locator: OmiSoundAssetLocator(roots: [empty]), pttTokens: ["fn"]))
  }

  func testBundledPageSourceExistsInPackageResources() throws {
    // Static tripwire, not behavioral: the page must ship with the package or the step opens nothing.
    let here = URL(fileURLWithPath: #filePath)
    let resources = here.deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/\(ThreeDoorsDemoPage.fileName)")
    XCTAssertTrue(FileManager.default.fileExists(atPath: resources.path), resources.path)
  }
}
