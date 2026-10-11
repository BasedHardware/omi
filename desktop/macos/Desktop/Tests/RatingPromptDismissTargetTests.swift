import XCTest

@testable import Omi_Computer

/// The dismiss control on both prompt bars must stay clickable.
///
/// A `.buttonStyle(.plain)` button is hit-testable only where it draws, so an
/// 11pt `xmark` glyph with no frame gives an 11pt target. A user reported
/// clicking it repeatedly with nothing happening: every click landed a few
/// points off the glyph, and the bar has no other way out.
final class RatingPromptDismissTargetTests: XCTestCase {
  /// A pointer target smaller than this is the defect being fixed; the glyph
  /// itself is 11pt, so anything at or below that is no hit area at all.
  private let minimumHitSide: CGFloat = 22

  func testDismissHitAreaIsLargerThanItsGlyph() {
    XCTAssertGreaterThanOrEqual(RatingPromptLayout.dismissHitSide, minimumHitSide)
  }

  func testBothPromptBarsGiveDismissAHitAreaAndNotJustAGlyph() throws {
    // omi-test-quality: source-inspection -- static contract: SwiftUI hit areas
    // are not observable from a unit test, and the regression is a modifier
    // going missing. Both bars render in the same overlay slot, so a dismiss
    // that works in one and not the other is the same bug reported again.
    for file in ["RatingPrompt.swift", "RemotePrompts.swift"] {
      let source = try sourceFile(file)
      XCTAssertTrue(
        source.contains("RatingPromptLayout.dismissHitSide"),
        "\(file) must size its dismiss control from the shared hit area")
      XCTAssertTrue(
        source.contains(".contentShape(Rectangle())"),
        "\(file) must make the whole dismiss frame hit-testable, not just the glyph")
    }
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: a SwiftUI hit area is not observable from a unit test, so holding both bars to it means reading the modifiers back out of the two sources.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
