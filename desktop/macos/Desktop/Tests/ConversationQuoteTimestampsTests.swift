import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationQuoteTimestampsTests: XCTestCase {
  func testFormatsActualOffsetsIncludingHourBoundary() {
    for (start, expected) in [
      (0.0, "0:00"), (42.9, "0:42"), (312, "5:12"), (3599, "59:59"), (3600, "1:00:00"), (3912, "1:05:12"),
    ] {
      XCTAssertEqual(ConversationQuoteTimestamp(id: "source", start: start).timestamp, expected)
    }
  }

  func testResolvesUniqueSourcesAndBackendAliasesInCitationOrder() {
    let segment = TranscriptSegment(
      id: "local", backendId: "server", text: "Evidence", speaker: nil,
      isUser: false, personId: nil, start: 312, end: 313)
    XCTAssertEqual(
      ConversationQuoteTimestamp.resolve(["missing", "server", "server"], segments: [segment]),
      [ConversationQuoteTimestamp(id: "server", start: 312)])
    XCTAssertTrue(ConversationQuoteTimestamp.resolve(["missing"], segments: [segment]).isEmpty)
  }

  func testHostedRowsExpandIndependentlyAndSeekIndividualSources() throws {
    let sources = [42.0, 312, 460, 3912, 3600].enumerated().map {
      ConversationQuoteTimestamp(id: "s\($0.offset)", start: $0.element)
    }
    var opened: [String] = []
    let host = NSHostingView(
      rootView: VStack {
        ConversationQuoteTimestamps(sources: sources, onOpenSource: { opened.append($0) })
        ConversationQuoteTimestamps(sources: sources, onOpenSource: { opened.append($0) })
      }.frame(width: 560, alignment: .leading))
    let window = mount(host)
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }
    var buttons = buttonViews(host)
    XCTAssertEqual(buttons.count, 8)
    let more = try XCTUnwrap(buttons.dropFirst(3).first)
    try press(more, in: window)
    host.layoutSubtreeIfNeeded()
    buttons = buttonViews(host)
    XCTAssertEqual(buttons.count, 9)
    let hour = try XCTUnwrap(buttons.dropFirst(3).first)
    try press(hour, in: window)
    XCTAssertEqual(opened, ["s3"])
  }

  func testSectionWithEmptySourceIDRendersNoTimestampButtons() {
    for (id, backendId) in [("", "server"), ("local", ""), ("", "")] {
      let segment = TranscriptSegment(
        id: id, backendId: backendId, text: "Evidence", speaker: nil,
        isUser: false, personId: nil, start: 42, end: 43)
      XCTAssertTrue(ConversationSummarySelection.resolvableSourceIDs([""], segments: [segment]).isEmpty)
      XCTAssertTrue(ConversationQuoteTimestamp.resolve([""], segments: [segment]).isEmpty)
      let host = NSHostingView(
        rootView: ConversationSummarySections(
          sections: [SummarySection(heading: "Missing", bodyMarkdown: "Body", sourceSegmentIDs: [""])],
          transcriptSegments: [segment],
          onOpenSources: { _ in XCTFail("No source should open") }
        ).frame(width: 560, alignment: .leading))
      let window = mount(host)
      defer {
        window.orderOut(nil)
        window.contentView = nil
      }
      XCTAssertTrue(buttonViews(host).isEmpty)
    }
  }

  func testEmptyAndSingleSourceRows() {
    for sources in [[], [ConversationQuoteTimestamp(id: "only", start: 42)]] {
      let host = NSHostingView(
        rootView: ConversationQuoteTimestamps(sources: sources, onOpenSource: { _ in })
          .frame(width: 560, alignment: .leading))
      let window = mount(host)
      defer {
        window.orderOut(nil)
        window.contentView = nil
      }
      XCTAssertEqual(buttonViews(host).count, sources.count)
    }
  }

  private func mount<V: View>(_ host: NSHostingView<V>) -> NSWindow {
    host.frame = NSRect(x: 0, y: 0, width: 560, height: 200)
    let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
    host.layoutSubtreeIfNeeded()
    return window
  }

  // SwiftUI draws labels itself; its AppKit focus-ring views identify the actual
  // focusable buttons without relying on an external Accessibility permission.
  private func buttonViews(_ view: NSView) -> [NSView] {
    if String(describing: type(of: view)) == "_FocusRingView" { return [view] }
    return view.subviews.flatMap { buttonViews($0) }
  }

  private func press(_ view: NSView, in window: NSWindow) throws {
    let point = view.convert(NSPoint(x: view.bounds.midX, y: view.bounds.midY), to: nil)
    for (type, number) in [(NSEvent.EventType.leftMouseDown, 1), (.leftMouseUp, 2)] {
      let event = try XCTUnwrap(
        NSEvent.mouseEvent(
          with: type, location: point, modifierFlags: [],
          timestamp: Double(number), windowNumber: window.windowNumber, context: nil,
          eventNumber: number, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0))
      window.sendEvent(event)
    }
  }
}
