import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class OmiMarkdownCitationInteractionTests: XCTestCase {
  /// #11573 — a cited answer inside a `ScrollView`/`LazyVStack` host made SwiftUI walk the static
  /// view-type graph (`View._viewListCount(inputs:)`). That walk is driven by types, not values,
  /// so the `OmiMarkdownContent` <-> `OmiMarkdownCitationContent` cycle recursed until the main
  /// thread wrote past its stack guard page: SIGSEGV on macOS 15, where this container asks for
  /// the count. Measuring the host is what forces the walk; an unerased cycle crashes the process
  /// rather than failing an assertion.
  func testCitedAnswerInAScrollingTranscriptMeasuresWithoutRecursingOnTheViewTypeGraph() {
    let citations = (1...3).map {
      ChatCitationReference(
        ordinal: $0, kind: .memory, sourceID: "memory-\($0)", title: "Source \($0)")
    }
    let messages = (0..<12).map { index in
      """
      Completed answer \(index) cites its provenance inline [1], keeps `inline code` copyable [2],
      and wraps across enough prose to exercise the flow layout [3].
      """
    }

    let host = NSHostingView(
      rootView: ScrollView {
        LazyVStack(alignment: .leading, spacing: 8) {
          ForEach(messages.indices, id: \.self) { index in
            OmiMarkdown(text: messages[index], sender: .ai, citations: citations)
          }
        }
      }
    )

    for width in [620.0, 980.0, 620.0] {
      host.frame = NSRect(x: 0, y: 0, width: width, height: 720)
      host.layoutSubtreeIfNeeded()

      let size = host.fittingSize
      XCTAssertTrue(size.height.isFinite, "cited transcript height must remain finite")
      XCTAssertGreaterThan(size.height, 0, "cited messages must remain visible")
    }
  }

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

  func testCitationMaskKeepsAdjacentMarkersOnRecapBullets() throws {
    let references = [20, 21, 3].map {
      ChatCitationReference(
        ordinal: $0, kind: .conversation, sourceID: "conversation-\($0)", title: "Source \($0)")
    }
    let mask = try XCTUnwrap(
      ChatCitationMask.mask(
        "- Worked on the launch/demo video [20][21][3]",
        references: Dictionary(uniqueKeysWithValues: references.map { ($0.ordinal, $0) })))

    XCTAssertEqual(mask.markers.map(\.reference.ordinal), [20, 21, 3])
  }

  func testCitationMaskPromotesKindPrefixedMemoryMarkers() throws {
    let references = [5023, 5001].map {
      ChatCitationReference(
        ordinal: $0, kind: .memory, sourceID: "memory-\($0)", title: "Source \($0)")
    }
    let mask = try XCTUnwrap(
      ChatCitationMask.mask(
        "- Formalizing the content testing loop [memory 5023][memory:5001]. Bare [memory] stays prose.",
        references: Dictionary(uniqueKeysWithValues: references.map { ($0.ordinal, $0) })))

    XCTAssertEqual(mask.markers.map(\.reference.ordinal), [5023, 5001])
    XCTAssertTrue(mask.markdown.contains("Bare [memory] stays prose."))
  }
}
