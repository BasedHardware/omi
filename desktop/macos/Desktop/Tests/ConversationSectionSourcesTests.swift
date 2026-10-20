import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationSectionSourcesTests: XCTestCase {
  func testResolvesUniqueSourcesAndBackendAliasesInCitationOrder() {
    let segment = TranscriptSegment(
      id: "local", backendId: "server", text: "Evidence", speaker: nil,
      isUser: false, personId: nil, start: 312, end: 313)
    XCTAssertEqual(
      ConversationSectionSources.resolve(["missing", "server", "server"], segments: [segment]), ["server"])
    XCTAssertTrue(ConversationSectionSources.resolve(["missing"], segments: [segment]).isEmpty)
  }

  func testDropsSourcesWithoutAUsableStart() {
    let segments = [-1, .nan, .infinity, 7].enumerated().map {
      TranscriptSegment(
        id: "s\($0.offset)", text: "Evidence", speaker: nil, isUser: false, personId: nil,
        start: $0.element, end: 8)
    }
    XCTAssertEqual(ConversationSectionSources.resolve(["s0", "s1", "s2", "s3"], segments: segments), ["s3"])
  }

  func testOneControlPerSectionOpensEverySupportingSourceAtOnce() throws {
    let segments = [42.0, 312, 3912].enumerated().map {
      TranscriptSegment(
        id: "s\($0.offset)", text: "Evidence", speaker: nil, isUser: false, personId: nil,
        start: $0.element, end: $0.element + 1)
    }
    var opened: [[String]] = []
    let host = NSHostingView(
      rootView: ConversationSummarySections(
        sections: [
          SummarySection(heading: "Main", bodyMarkdown: "Body", sourceSegmentIDs: ["missing", "s2", "s0", "s2"]),
          SummarySection(heading: "Unsourced", bodyMarkdown: "Body"),
        ],
        transcriptSegments: segments,
        onOpenSources: { opened.append($0) }
      )
      // ConversationSummaryBody's side margin, which the control sits in.
      .padding(.horizontal, OmiSpacing.lg)
      .frame(width: 560, alignment: .leading))
    let window = mount(host)
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }
    let buttons = buttonViews(host)
    XCTAssertEqual(buttons.count, 1)
    try press(try XCTUnwrap(buttons.first), in: window)
    XCTAssertEqual(opened, [["s2", "s0"]])
    let prose = descendants(NSTextView.self, from: host).map(\.string).joined(separator: "\n")
    XCTAssertFalse(prose.contains("0:42"))
  }

  func testSectionWithEmptySourceIDRendersNoSourcesControl() {
    for (id, backendId) in [("", "server"), ("local", ""), ("", "")] {
      let segment = TranscriptSegment(
        id: id, backendId: backendId, text: "Evidence", speaker: nil,
        isUser: false, personId: nil, start: 42, end: 43)
      XCTAssertTrue(ConversationSummarySelection.resolvableSourceIDs([""], segments: [segment]).isEmpty)
      XCTAssertTrue(ConversationSectionSources.resolve([""], segments: [segment]).isEmpty)
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

  private func descendants<T: NSView>(_ type: T.Type, from view: NSView) -> [T] {
    var result = (view as? T).map { [$0] } ?? []
    for subview in view.subviews {
      result += descendants(type, from: subview)
    }
    return result
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
