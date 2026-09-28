import AppKit
import XCTest

@testable import Omi_Computer

final class OmiBrandMarkAssetTests: XCTestCase {
  func testTemplateImageResolvesThePackagedOmiMark() {
    let sourceResourceRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources/Resources")
    let image = OmiBrandMarkAsset.templateImage(in: [], resourceBundleRoots: [sourceResourceRoot])

    XCTAssertNotNil(image, "the shared Omi mark must resolve from a loaded app resource bundle")
    XCTAssertTrue(image?.isTemplate ?? false, "shared Omi marks must inherit their surface tint")
  }

  func testTemplateImageDoesNotInventAGenericFallbackBitmap() {
    XCTAssertNil(OmiBrandMarkAsset.templateImage(in: [], resourceBundleRoots: []))
  }

  func testMenuBarMarkUsesTheSamePackagedResourceContract() {
    let sourceResourceRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources")

    let image = OmiBrandMarkAsset.templateImage(
      named: "omi_menu_bar_icon",
      in: [],
      resourceBundleRoots: [sourceResourceRoot]
    )

    XCTAssertNotNil(image, "menu-bar identity must resolve from the packaged resource bundle")
    XCTAssertTrue(image?.isTemplate == true)
  }

  func testStructuredResourceBundleRootIsSearched() throws {
    let app = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".app")
    defer { try? FileManager.default.removeItem(at: app) }
    let resourceRoot = app.appendingPathComponent(
      "Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources")
    try FileManager.default.createDirectory(at: resourceRoot, withIntermediateDirectories: true)
    let source = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/herologo.png")
    try FileManager.default.copyItem(at: source, to: resourceRoot.appendingPathComponent("herologo.png"))

    let image = OmiBrandMarkAsset.templateImage(
      in: [], resourceBundleRoots: OmiBrandMarkAsset.knownResourceBundleRoots(in: app))
    XCTAssertNotNil(image)
  }
}
