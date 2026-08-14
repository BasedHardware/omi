import XCTest

@testable import Omi_Computer

@MainActor
final class OmiMarkdownCitationInteractionTests: XCTestCase {
  func testCitationProjectionPreservesInlineCodeAsCopyableUnit() throws {
    let reference = ChatCitationReference(
      ordinal: 1,
      kind: .memory,
      sourceID: "memory-1",
      title: "Build notes")
    let citationMask = try XCTUnwrap(
      ChatCitationMask.mask(
        "Run `make test` before shipping.[1]",
        references: [1: reference]))
    let interactiveMask = try XCTUnwrap(ChatCitationMask.maskInlineCode(in: citationMask))
    let attributed = try XCTUnwrap(
      OmiMarkdownContent.styledAttributedString(
        from: interactiveMask.markdown,
        style: .assistant,
        fontSize: 14,
        fontScale: 1))

    let units = ChatCitationMask.units(
      in: attributed,
      citationMarkers: citationMask.markers,
      codePlaceholders: interactiveMask.codePlaceholders
    ).flatMap { $0 }

    XCTAssertTrue(
      units.contains {
        if case .code("make test") = $0 { return true }
        return false
      })
    XCTAssertTrue(
      units.contains {
        if case .citation(let value) = $0 { return value == reference }
        return false
      })
  }

  func testTableParserKeepsCitationMarkerInCellForInteractiveRenderer() throws {
    let document = OmiMarkdownDocument(
      markdown: "| Claim | Evidence |\n| --- | --- |\n| Shipped | Build notes [1] |")
    guard case .table(let table) = try XCTUnwrap(document.blocks.first).kind else {
      return XCTFail("Expected a parsed markdown table")
    }

    XCTAssertEqual(table.rows.first?[1], "Build notes [1]")
  }
}
