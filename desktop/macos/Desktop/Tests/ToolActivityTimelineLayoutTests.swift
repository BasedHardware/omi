import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ToolActivityTimelineLayoutTests: XCTestCase {
  func testConnectorIsCenteredOnTheIconColumn() {
    XCTAssertEqual(
      ToolActivityTimelineLayout.connectorOriginX,
      (ToolActivityTimelineLayout.iconColumn - ToolActivityTimelineLayout.connectorWidth) / 2
    )
    XCTAssertEqual(ToolActivityTimelineLayout.connectorOriginX, 8.5, accuracy: 0.001)
  }

  func testEveryGlyphUsesTheSameCenteredSquare() {
    let sparkles = ToolActivityTimelineLayout.iconGlyphFrame()
    let document = ToolActivityTimelineLayout.iconGlyphFrame()
    XCTAssertEqual(sparkles, document)
    XCTAssertEqual(sparkles.midX, ToolActivityTimelineLayout.iconColumn / 2, accuracy: 0.001)
    XCTAssertEqual(sparkles.midY, ToolActivityTimelineLayout.iconColumn / 2, accuracy: 0.001)
    XCTAssertEqual(ToolActivityTimelineLayout.symbol(for: "get_daily_recap"), "sparkles")
    XCTAssertEqual(ToolActivityTimelineLayout.symbol(for: "read_tool_output"), "doc.text")
    XCTAssertEqual(ToolActivityTimelineLayout.symbol(for: "thread_dump"), "sparkles")
    XCTAssertEqual(ToolActivityTimelineLayout.symbol(for: "spreadsheet"), "sparkles")
  }

  func testDisclosureSitsBesideTheLabelInsteadOfTheTrailingEdge() {
    let frames = ToolActivityTimelineLayout.headerFrames(labelWidth: 180, hasDisclosure: true)
    guard let disclosure = frames.disclosure else {
      return XCTFail("a disclosing header must place a chevron")
    }
    XCTAssertEqual(
      disclosure.minX,
      180 + ToolActivityTimelineLayout.labelToDisclosureSpacing,
      accuracy: 0.001
    )
    XCTAssertEqual(frames.width, disclosure.maxX)
    XCTAssertLessThan(
      frames.width,
      520 - 100,
      "a hugging header must not consume the chat column"
    )
  }

  func testSparklesAndDocumentIconsShareOneColumnCenter() {
    let recorder = ToolCallLayoutRecorder()
    layOut(
      width: 520,
      height: 80,
      recorder: recorder
    ) {
      VStack(alignment: .leading, spacing: 0) {
        ToolCallLayoutProbe(recorder: recorder, slot: .sparkles) {
          ToolCallActivityIcon(name: "get_daily_recap", status: .completed)
        }
        ToolCallLayoutProbe(recorder: recorder, slot: .document) {
          ToolCallActivityIcon(name: "read_tool_output", status: .completed)
        }
      }
    }

    guard let sparkles = recorder.frame(of: .sparkles),
      let document = recorder.frame(of: .document)
    else {
      return XCTFail("tool activity icons never laid out")
    }
    XCTAssertEqual(sparkles.midX, document.midX, accuracy: 0.5)
    XCTAssertEqual(sparkles.width, ToolActivityTimelineLayout.iconColumn, accuracy: 0.5)
    XCTAssertEqual(document.width, ToolActivityTimelineLayout.iconColumn, accuracy: 0.5)
    XCTAssertEqual(sparkles.height, ToolActivityTimelineLayout.iconColumn, accuracy: 0.5)
    XCTAssertEqual(document.height, ToolActivityTimelineLayout.iconColumn, accuracy: 0.5)
  }

  func testIconAndLabelShareAVerticalCenter() {
    let recorder = ToolCallLayoutRecorder()
    layOut(width: 520, height: 80, recorder: recorder) {
      HStack(alignment: .center, spacing: ToolActivityTimelineLayout.rowIconSpacing) {
        ToolCallLayoutProbe(recorder: recorder, slot: .sparkles) {
          ToolCallActivityIcon(name: "get_action_items", status: .completed)
        }
        ToolCallLayoutProbe(recorder: recorder, slot: .header) {
          ToolCallHeaderLabel(
            title: "Using get_action_items",
            summary: nil,
            showsDisclosure: true,
            isExpanded: false
          )
        }
      }
    }

    guard let icon = recorder.frame(of: .sparkles),
      let header = recorder.frame(of: .header)
    else {
      return XCTFail("the tool-call headline never laid out")
    }
    XCTAssertEqual(icon.midY, header.midY, accuracy: 0.5)
    XCTAssertEqual(icon.height, ToolActivityTimelineLayout.iconColumn, accuracy: 0.5)
    XCTAssertEqual(header.height, ToolActivityTimelineLayout.headerHeight, accuracy: 0.5)
  }

  func testHeadlineFitsTheIconColumnRatherThanATallerHeader() {
    let host = NSHostingView(
      rootView: ToolCallActivityHeadline(name: "get_action_items", status: .completed) {
        ToolCallHeaderLabel(
          title: "Using get_action_items",
          summary: nil,
          showsDisclosure: true,
          isExpanded: false
        )
      }
      .fixedSize()
    )
    host.layoutSubtreeIfNeeded()
    XCTAssertEqual(
      host.fittingSize.height,
      ToolActivityTimelineLayout.iconColumn,
      accuracy: 0.5,
      "a header taller than the icon column drops the label below the glyph"
    )
  }

  func testTitleDoesNotStretchAwayFromTheDisclosureInsideAWideButton() {
    let recorder = ToolCallLayoutRecorder()
    let columnWidth: CGFloat = 520
    layOut(width: columnWidth, height: 80, recorder: recorder) {
      Button(action: {}) {
        ToolCallLayoutProbe(recorder: recorder, slot: .header) {
          ToolCallHeaderLabel(
            title: "Using get_action_items",
            summary: nil,
            showsDisclosure: true,
            isExpanded: false
          )
        }
      }
      .buttonStyle(.plain)
      .frame(width: columnWidth, alignment: .leading)
    }

    guard let header = recorder.frame(of: .header) else {
      return XCTFail("the tool-call header never laid out inside a button")
    }
    XCTAssertLessThan(
      header.width,
      280,
      "a flexible title inside a wide button would push the chevron away from the name"
    )
  }

  func testHeaderHugsTheToolNameInAWideColumn() {
    let recorder = ToolCallLayoutRecorder()
    let columnWidth: CGFloat = 520
    layOut(width: columnWidth, height: 80, recorder: recorder) {
      HStack(alignment: .center, spacing: 0) {
        ToolCallLayoutProbe(recorder: recorder, slot: .header) {
          ToolCallHeaderLabel(
            title: "Using get_daily_recap",
            summary: nil,
            showsDisclosure: true,
            isExpanded: false
          )
        }
        Spacer(minLength: 0)
      }
      .frame(width: columnWidth, alignment: .leading)
    }

    guard let header = recorder.frame(of: .header) else {
      return XCTFail("the tool-call header never laid out")
    }
    XCTAssertLessThan(
      header.width,
      280,
      "disclosure must sit beside the label rather than the trailing edge of a \(columnWidth)pt column"
    )
    XCTAssertGreaterThan(header.width, 140)
    XCTAssertEqual(header.minX, 0, accuracy: 0.5)
  }
}

private enum ToolCallLayoutSlot {
  case sparkles
  case document
  case header
}

private final class ToolCallLayoutRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var frames: [ToolCallLayoutSlot: CGRect] = [:]

  func record(_ slot: ToolCallLayoutSlot, _ frame: CGRect) {
    lock.lock()
    frames[slot] = frame
    lock.unlock()
  }

  func frame(of slot: ToolCallLayoutSlot) -> CGRect? {
    lock.lock()
    defer { lock.unlock() }
    return frames[slot]
  }
}

private struct ToolCallLayoutProbe: Layout {
  let recorder: ToolCallLayoutRecorder
  let slot: ToolCallLayoutSlot

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    subviews.reduce(into: .zero) { size, subview in
      let child = subview.sizeThatFits(proposal)
      size.width = max(size.width, child.width)
      size.height = max(size.height, child.height)
    }
  }

  func placeSubviews(
    in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
  ) {
    recorder.record(slot, bounds)
    for subview in subviews {
      subview.place(
        at: CGPoint(x: bounds.minX, y: bounds.minY),
        anchor: .topLeading,
        proposal: ProposedViewSize(width: bounds.width, height: bounds.height)
      )
    }
  }
}

extension ToolActivityTimelineLayoutTests {
  fileprivate func layOut<Content: View>(
    width: CGFloat,
    height: CGFloat,
    recorder _: ToolCallLayoutRecorder,
    @ViewBuilder content: () -> Content
  ) {
    let host = NSHostingView(rootView: content())
    host.frame = NSRect(x: 0, y: 0, width: width, height: height)
    host.layoutSubtreeIfNeeded()
  }
}
