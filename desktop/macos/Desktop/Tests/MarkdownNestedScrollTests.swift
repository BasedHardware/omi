import AppKit
import ObjectiveC
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class MarkdownNestedScrollTests: XCTestCase {
  func testWideMarkdownTableMountsAHorizontalScroller() throws {
    let table = """
      | Animal | Class | Superpower | Lifespan | Habitat | Wild Fact |
      | --- | --- | --- | --- | --- | --- |
      | Mantis shrimp | Crustacean | Sees sixteen color receptors | 3–6 years | Tropical ocean floors | Punches with a cavitation bubble |
      """
    let host = NSHostingView(
      rootView: OmiMarkdown(text: table, style: .assistant)
        .frame(width: 360, alignment: .leading)
    )
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 360, height: 400),
      styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = host
    window.orderFrontRegardless()
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }

    host.layoutSubtreeIfNeeded()

    let tableScroller = try XCTUnwrap(
      descendantScrollViews(of: host).first(where: { $0.hasHorizontalScroller })
    )
    let documentWidth = try XCTUnwrap(tableScroller.documentView).frame.width
    XCTAssertGreaterThan(documentWidth, tableScroller.contentView.bounds.width)
  }

  func testVerticalWheelOverHorizontalCodeBlockRoutesToTranscript() throws {
    let outer = RecordingTranscriptScrollView(
      frame: NSRect(x: 0, y: 0, width: 400, height: 400))
    let transcript = NestedScrollFlippedDocumentView(
      frame: NSRect(x: 0, y: 0, width: 400, height: 1_200))
    let transcriptProbe = NSView(frame: NSRect(x: 0, y: 0, width: 1, height: 1))
    transcript.addSubview(transcriptProbe)
    outer.documentView = transcript

    let codeScroller = NSScrollView(frame: NSRect(x: 20, y: 100, width: 300, height: 120))
    let codeDocument = NSView(frame: NSRect(x: 0, y: 0, width: 900, height: 120))
    let probe = NSView(frame: NSRect(x: 0, y: 0, width: 1, height: 1))
    codeDocument.addSubview(probe)
    codeScroller.documentView = codeDocument
    transcript.addSubview(codeScroller)

    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 400, height: 400),
      styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = outer
    window.orderFrontRegardless()
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }

    let coordinator = VerticalWheelPassthrough.Coordinator()
    coordinator.install(for: probe)
    defer { coordinator.stop() }
    var ownershipClaims = 0
    let userScrollCoordinator = UserScrollDetector.Coordinator(
      onUserScroll: { ownershipClaims += 1 },
      onScrollSettledAtBottom: {}
    )
    userScrollCoordinator.install(for: transcriptProbe)
    defer { userScrollCoordinator.stop() }

    let verticalEvent = try wheelEvent(
      window: window,
      location: codeScroller.convert(NSPoint(x: 100, y: 60), to: nil),
      deltaX: 2,
      deltaY: 80)
    XCTAssertNil(coordinator.handle(verticalEvent))
    XCTAssertEqual(outer.forwardedWheelEvents, 1)
    XCTAssertEqual(ownershipClaims, 1)

    let horizontalEvent = try wheelEvent(
      window: window,
      location: codeScroller.convert(NSPoint(x: 100, y: 60), to: nil),
      deltaX: 80,
      deltaY: 2)
    XCTAssertNotNil(coordinator.handle(horizontalEvent))
    XCTAssertEqual(outer.forwardedWheelEvents, 1)
  }

  private func wheelEvent(
    window: NSWindow,
    location: NSPoint,
    deltaX: Int32,
    deltaY: Int32
  ) throws -> NSEvent {
    let cgEvent = try XCTUnwrap(
      CGEvent(
        scrollWheelEvent2Source: nil,
        units: .pixel,
        wheelCount: 2,
        wheel1: deltaY,
        wheel2: deltaX,
        wheel3: 0))
    let event = try XCTUnwrap(NSEvent(cgEvent: cgEvent))
    InjectedScrollEvent.target = window
    InjectedScrollEvent.targetWindowNumber = window.windowNumber
    InjectedScrollEvent.locationInWindowOverride = location
    object_setClass(event, InjectedScrollEvent.self)
    return event
  }

  private func descendantScrollViews(of view: NSView) -> [NSScrollView] {
    var result = (view as? NSScrollView).map { [$0] } ?? []
    for child in view.subviews {
      result += descendantScrollViews(of: child)
    }
    return result
  }
}

@MainActor
private final class RecordingTranscriptScrollView: NSScrollView {
  private(set) var forwardedWheelEvents = 0

  override func scrollWheel(with event: NSEvent) {
    forwardedWheelEvents += 1
  }
}

private final class NestedScrollFlippedDocumentView: NSView {
  override var isFlipped: Bool { true }
}
