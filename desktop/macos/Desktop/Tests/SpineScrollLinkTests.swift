//
//  SpineScrollLinkTests.swift — the ribbon is the scrollbar, and this is the arithmetic that makes
//  it one.
//
//  A wheel over the hour ribbon moves the list's own `NSScrollView` rather than a second scroll view
//  of the ribbon's own (see `SpineScrollLink` for why a proportional mapping between the two would
//  drift). Three decisions carry that: which way the wheel moves the list, what a line-based wheel is
//  worth in points, and where the list stops.
//
//  **The phased-event case below is the one that matters most, because its absence shipped a bug.**
//  An earlier version handed the event to `NSScrollView.scrollWheel(with:)` instead of computing the
//  offset, on the reasoning that AppKit should own momentum and rubber-banding. It does — but only
//  for events it was hit for: a real trackpad event carries a gesture `phase` and goes through
//  responsive scrolling, which ignores an event force-fed to a scroll view the gesture did not
//  start in. A two-finger swipe over the ribbon did nothing at all. The tests passed anyway, because
//  every event they built was a synthetic `CGEvent` with no phase, which takes the legacy path and
//  scrolls. A test suite that can only produce the one kind of event the broken path still handles
//  is a suite that certifies the break.
//

import AppKit
import XCTest

@testable import Omi_Computer

@MainActor
final class SpineScrollLinkTests: XCTestCase {
  /// A list taller than its viewport: 2,000 points of document in a 500 point window.
  private func makeScrollView(documentHeight: CGFloat = 2_000, viewportHeight: CGFloat = 500)
    -> NSScrollView
  {
    let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 300, height: viewportHeight))
    let document = FlippedView(frame: NSRect(x: 0, y: 0, width: 300, height: documentHeight))
    scrollView.documentView = document
    scrollView.layoutSubtreeIfNeeded()
    return scrollView
  }

  /// SwiftUI's `ScrollView` lays its content out top-down, so the document view is flipped and
  /// `bounds.origin.y` grows downward. The forwarding maths only reads correctly against that.
  private final class FlippedView: NSView {
    override var isFlipped: Bool { true }
  }

  /// A wheel event. `phase` is the axis the shipped bug turned on: `.none` is the legacy path an
  /// old mouse takes, anything else is the trackpad gesture path.
  private func wheel(deltaY: Double, precise: Bool = true, phase: CGScrollPhase? = nil) -> NSEvent {
    let event = CGEvent(
      scrollWheelEvent2Source: nil, units: precise ? .pixel : .line, wheelCount: 1,
      wheel1: Int32(deltaY), wheel2: 0, wheel3: 0)!
    event.setIntegerValueField(.scrollWheelEventIsContinuous, value: precise ? 1 : 0)
    if let phase {
      event.setIntegerValueField(.scrollWheelEventScrollPhase, value: Int64(phase.rawValue))
    }
    return NSEvent(cgEvent: event)!
  }

  /// **A real two-finger swipe moves the list.** This is the regression: the whole gesture — the
  /// `.began`, the run of `.changed`, the `.ended` — has to land on the list, because a trackpad
  /// sends nothing else.
  func testATrackpadGestureWithPhasesScrollsTheList() {
    let scrollView = makeScrollView()
    let link = SpineScrollLink()
    link.scrollView = scrollView

    link.scroll(by: wheel(deltaY: -10, phase: .began))
    for _ in 0..<3 { link.scroll(by: wheel(deltaY: -10, phase: .changed)) }
    link.scroll(by: wheel(deltaY: 0, phase: .ended))

    XCTAssertEqual(
      scrollView.contentView.bounds.origin.y, 40, accuracy: 0.001,
      "a phased gesture has to move the list exactly as far as its deltas say")
  }

  /// The coast after a flick is a stream of events macOS sends on its own with decaying deltas, so
  /// applying each one as it arrives *is* the inertia.
  func testTheMomentumTailKeepsMovingTheList() {
    let scrollView = makeScrollView()
    let link = SpineScrollLink()
    link.scrollView = scrollView

    link.scroll(by: wheel(deltaY: -20, phase: .began))
    for decay in [-16.0, -12, -8, -4, -2, -1] {
      link.scroll(by: wheel(deltaY: decay, phase: .none))
    }
    XCTAssertEqual(scrollView.contentView.bounds.origin.y, 63, accuracy: 0.001)
  }

  /// **Down the wheel is down the list.** A sign flip here would send the ribbon and the list in
  /// opposite directions, which is the one failure that makes the ribbon read as broken rather than
  /// as merely imprecise.
  func testWheelingDownMovesTheListTowardsTheOlderEnd() {
    let scrollView = makeScrollView()
    let link = SpineScrollLink()
    link.scrollView = scrollView

    XCTAssertTrue(link.scroll(by: wheel(deltaY: -40)))
    XCTAssertEqual(scrollView.contentView.bounds.origin.y, 40, accuracy: 0.001)

    XCTAssertTrue(link.scroll(by: wheel(deltaY: 15)))
    XCTAssertEqual(
      scrollView.contentView.bounds.origin.y, 25, accuracy: 0.001,
      "wheeling back up has to undo exactly what wheeling down did")
  }

  /// A trackpad reports points; an old mouse wheel reports lines. Forwarding the raw number for both
  /// makes a real mouse move the list about a pixel a notch.
  func testALineWheelTravelsFurtherThanASinglePoint() {
    let scrollView = makeScrollView()
    let link = SpineScrollLink()
    link.scrollView = scrollView

    link.scroll(by: wheel(deltaY: -1, precise: false))
    XCTAssertGreaterThan(
      scrollView.contentView.bounds.origin.y, 1,
      "a line-based notch is worth more than one point of list")
  }

  /// The list stops at both ends. Without the clamp the ribbon can drive the content off its own
  /// document and leave the spine showing blank space it can never scroll back from.
  func testTheListStopsAtBothEnds() {
    let scrollView = makeScrollView(documentHeight: 2_000, viewportHeight: 500)
    let link = SpineScrollLink()
    link.scrollView = scrollView

    for _ in 0..<100 { link.scroll(by: wheel(deltaY: -200)) }
    XCTAssertEqual(
      scrollView.contentView.bounds.origin.y, 1_500, accuracy: 0.001,
      "the oldest thing loaded is the bottom of the document, not past it")

    for _ in 0..<100 { link.scroll(by: wheel(deltaY: 200)) }
    XCTAssertEqual(
      scrollView.contentView.bounds.origin.y, 0, accuracy: 0.001,
      "and the newest is the top, not above it")
  }

  /// A list shorter than its viewport has nowhere to go, and a ribbon with no list yet must not
  /// swallow the wheel — the caller falls through to normal handling on `false`.
  func testAWheelWithNothingToScrollIsHarmless() {
    let link = SpineScrollLink()
    XCTAssertFalse(
      link.scroll(by: wheel(deltaY: -40)),
      "no list resolved yet: the event has to go back to AppKit, not vanish")

    let shortList = makeScrollView(documentHeight: 200, viewportHeight: 500)
    link.scrollView = shortList
    XCTAssertTrue(link.scroll(by: wheel(deltaY: -40)))
    XCTAssertEqual(shortList.contentView.bounds.origin.y, 0, accuracy: 0.001)
  }
}
