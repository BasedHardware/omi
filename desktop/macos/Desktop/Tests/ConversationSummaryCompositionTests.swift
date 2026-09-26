import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationSummaryCompositionTests: XCTestCase {
  func testProductionSummaryBodyMountsOneCanonicalProjectionAndResolvableSources() throws {
    let conversation = makeConversation(
      overview: "## Decisions\n\nFirst detail.\n\nBody-only detail.\n\n## Decisions\n\nSecond detail.",
      sections: [
        SummarySection(
          heading: " Decisions ",
          bodyMarkdown: " First detail. ",
          sourceSegmentIDs: ["segment-1", "missing", "segment-1"]
        ),
        SummarySection(
          heading: "Blank heading must stay hidden",
          bodyMarkdown: " \n",
          sourceSegmentIDs: ["segment-1"]
        ),
        SummarySection(
          heading: "",
          bodyMarkdown: "Body-only detail."
        ),
        SummarySection(
          heading: "Decisions",
          bodyMarkdown: "Second detail.",
          sourceSegmentIDs: ["segment-1"]
        ),
      ]
    )
    let selection = ConversationSummarySelection.primarySummary(for: conversation)
    XCTAssertEqual(selection.kind, .sections)
    XCTAssertEqual(selection.content.components(separatedBy: "Decisions").count - 1, 2)
    var openedSourceIDs: [String] = []
    let host = NSHostingView(
      rootView: ConversationSummaryBody(
        conversation: conversation,
        onOpenSources: { openedSourceIDs = $0 }
      )
      .frame(width: 560, alignment: .leading)
    )
    host.frame = NSRect(x: 0, y: 0, width: 560, height: 700)
    let window = NSWindow(
      contentRect: host.frame,
      styleMask: [.borderless],
      backing: .buffered,
      defer: false
    )
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }

    host.layoutSubtreeIfNeeded()

    let rendered = descendants(NSTextView.self, from: host).map(\.string).joined(separator: "\n")
    XCTAssertEqual(rendered.components(separatedBy: "Decisions").count - 1, 2)
    XCTAssertEqual(rendered.components(separatedBy: "First detail.").count - 1, 1)
    XCTAssertEqual(rendered.components(separatedBy: "Body-only detail.").count - 1, 1)
    XCTAssertEqual(rendered.components(separatedBy: "Second detail.").count - 1, 1)
    XCTAssertFalse(rendered.contains("Blank heading must stay hidden"))
    XCTAssertFalse(rendered.contains("##"))

    // Drive the production source Button through a real event pair. The label sits directly
    // below this section's prose; target its text, beyond the icon-to-text gap of a plain button.
    let firstProse = try XCTUnwrap(
      descendants(NSTextView.self, from: host).first { $0.string.contains("First detail.") })
    let proseFrame = firstProse.convert(firstProse.bounds, to: host)
    let point = NSPoint(x: proseFrame.minX + 45, y: host.isFlipped ? proseFrame.maxY + 12 : proseFrame.minY - 12)
    let location = host.convert(point, to: nil)
    let down = try XCTUnwrap(
      NSEvent.mouseEvent(
        with: .leftMouseDown, location: location, modifierFlags: [], timestamp: 0, windowNumber: window.windowNumber,
        context: nil, eventNumber: 1, clickCount: 1, pressure: 1))
    let up = try XCTUnwrap(
      NSEvent.mouseEvent(
        with: .leftMouseUp, location: location, modifierFlags: [], timestamp: 0.1, windowNumber: window.windowNumber,
        context: nil, eventNumber: 2, clickCount: 1, pressure: 0))
    window.sendEvent(down)
    window.sendEvent(up)
    XCTAssertEqual(openedSourceIDs, ["segment-1"])
  }

  func testAppResultReplacesSectionsInProductionSummaryBody() throws {
    let appResult = try JSONDecoder().decode(
      AppResponse.self,
      from: Data(#"{"app_id":"custom","content":"App-only result."}"#.utf8)
    )
    let conversation = makeConversation(
      overview: "## Decisions\n\nFirst detail.",
      sections: [SummarySection(heading: "Decisions", bodyMarkdown: "First detail.")],
      appsResults: [appResult]
    )
    let selection = ConversationSummarySelection.primarySummary(for: conversation)
    XCTAssertEqual(selection.kind, .app)
    XCTAssertEqual(selection.appId, "custom")
    XCTAssertEqual(selection.resultIndex, 0)
    let host = NSHostingView(
      rootView: ConversationSummaryBody(conversation: conversation, onOpenSources: nil)
        .frame(width: 560, alignment: .leading)
    )
    host.frame = NSRect(x: 0, y: 0, width: 560, height: 300)
    let window = NSWindow(
      contentRect: host.frame,
      styleMask: [.borderless],
      backing: .buffered,
      defer: false
    )
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }
    host.layoutSubtreeIfNeeded()

    let rendered = descendants(NSTextView.self, from: host).map(\.string).joined(separator: "\n")
    XCTAssertEqual(rendered.components(separatedBy: "App-only result.").count - 1, 1)
    XCTAssertFalse(rendered.contains("First detail."))
  }

  func testSecondaryAppCardsRenderDocumentBlocksForShortAndTruncatedOutput() throws {
    for suffix in ["", String(repeating: " continuation", count: 30)] {
      let data = try JSONSerialization.data(withJSONObject: ["content": "## Secondary\n\n- Supporting detail." + suffix]
      )
      let result = try JSONDecoder().decode(AppResponse.self, from: data)
      let host = NSHostingView(rootView: AppResultCard(result: result, app: nil))
      host.frame = NSRect(x: 0, y: 0, width: 560, height: 700)
      let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
      window.contentView = host
      defer { window.contentView = nil }
      host.layoutSubtreeIfNeeded()
      let rendered = descendants(NSTextView.self, from: host).map(\.string).joined(separator: "\n")
      XCTAssertEqual(rendered.components(separatedBy: "Secondary").count - 1, 1)
      XCTAssertEqual(rendered.components(separatedBy: "•").count - 1, 1)
      XCTAssertFalse(rendered.contains("##"))
      XCTAssertEqual(rendered.contains("…"), !suffix.isEmpty)
    }
  }

  private func descendants<T: NSView>(_ type: T.Type, from view: NSView) -> [T] {
    var result = (view as? T).map { [$0] } ?? []
    for subview in view.subviews {
      result += descendants(type, from: subview)
    }
    return result
  }

  private func makeConversation(
    overview: String,
    sections: [SummarySection],
    appsResults: [AppResponse] = []
  ) -> ServerConversation {
    let timestamp = Date(timeIntervalSince1970: 1_700_000_000)
    let segment = TranscriptSegment(
      id: "segment-1",
      backendId: "segment-1",
      text: "The decision was discussed.",
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 1
    )
    return ServerConversation(
      id: "summary-composition",
      createdAt: timestamp,
      updatedAt: timestamp,
      startedAt: timestamp,
      finishedAt: timestamp.addingTimeInterval(60),
      structured: Structured(
        title: "Summary composition",
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: [],
        sections: sections
      ),
      transcriptSegments: [segment],
      transcriptSegmentsIncluded: true,
      geolocation: nil,
      photos: [],
      appsResults: appsResults,
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}
