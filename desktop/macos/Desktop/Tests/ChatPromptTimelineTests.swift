import AppKit
import CoreGraphics
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The hover card is 236pt wide and the rail is 40. Mounted as a sibling inside
/// the rail's stack, the stack grew to the card's width the instant the card
/// appeared and the marks were shoved out of the gutter — off the window on a
/// narrow one. The card has to be an overlay, which cannot resize what it
/// covers, and this is the layout pass that says so.
@MainActor
final class ChatPromptTimelineHoverLayoutTests: XCTestCase {
  private let gutter: CGFloat = 120
  private let marks = (0..<4).map {
    ChatPromptMark(
      id: "q\($0)",
      prompt: "a question long enough to fill the card's whole width and then some",
      reply: "an answer that is also long enough to wrap onto the card's second line",
      fraction: CGFloat($0) / 3
    )
  }

  func testShowingTheHoverCardDoesNotWidenTheRail() {
    let resting = railWidth(hoveredIndex: nil)
    let hovering = railWidth(hoveredIndex: 2)

    XCTAssertEqual(
      hovering, resting, accuracy: 0.5,
      "the card widened the rail from \(resting)pt to \(hovering)pt, which shifts every mark")
  }

  /// The one that would have caught the shove. Width alone cannot see it — the
  /// rail's frame stays 40pt while its contents slide inside — so this renders
  /// the rail and asks where the marks actually landed.
  func testShowingTheHoverCardDoesNotMoveTheMarks() throws {
    let resting = try XCTUnwrap(markTrailingEdge(hoveredIndex: nil), "no marks were drawn")
    let hovering = try XCTUnwrap(
      markTrailingEdge(hoveredIndex: 2), "the marks vanished when the card appeared")

    XCTAssertEqual(
      hovering, resting, accuracy: 1,
      "the marks slid from x=\(resting) to x=\(hovering) when the card appeared")
  }

  /// The rightmost column the marks paint, in pixels, or nil if they painted
  /// nothing inside the rail at all.
  private func markTrailingEdge(hoveredIndex: Int?) -> Int? {
    let width =
      ChatPromptTimelineMetrics.railWidth
      + ChatPromptTimelineMetrics.trailingOffset(gutter: gutter)
    let height: CGFloat = 600
    let renderer = ImageRenderer(
      content: ChatPromptTimeline(
        marks: marks, activeMarkID: "q1", gutter: gutter, hoveredIndex: hoveredIndex
      ) { _ in }
      .frame(width: width, height: height)
    )
    renderer.scale = 1
    guard let image = renderer.cgImage else { return nil }

    let pixelWidth = image.width
    let pixelHeight = image.height
    var pixels = [UInt8](repeating: 0, count: pixelWidth * pixelHeight * 4)
    guard
      let context = CGContext(
        data: &pixels,
        width: pixelWidth,
        height: pixelHeight,
        bitsPerComponent: 8,
        bytesPerRow: pixelWidth * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      )
    else { return nil }
    context.draw(image, in: CGRect(x: 0, y: 0, width: pixelWidth, height: pixelHeight))

    // Only the band the marks occupy. The card is taller than the group and
    // sits to their left, so restricting the scan to the group's own rows keeps
    // it out of the answer.
    let positions = ChatPromptTimelineMetrics.positions(count: marks.count, railHeight: height)
    let band = Set(positions.map { Int($0.rounded()) })

    var rightmost: Int?
    for y in 0..<pixelHeight where band.contains(y) {
      for x in 0..<pixelWidth {
        let alpha = pixels[(y * pixelWidth + x) * 4 + 3]
        if alpha > 25 { rightmost = max(rightmost ?? 0, x) }
      }
    }
    return rightmost
  }

  /// The rail is exactly as wide as it claims, so the marks land on the gutter's
  /// centre line rather than wherever a stray child left them.
  func testTheRailIsOnlyEverItsOwnWidth() {
    let expected =
      ChatPromptTimelineMetrics.railWidth
      + ChatPromptTimelineMetrics.trailingOffset(gutter: gutter)

    XCTAssertEqual(railWidth(hoveredIndex: nil), expected, accuracy: 0.5)
    XCTAssertEqual(railWidth(hoveredIndex: 0), expected, accuracy: 0.5)
  }

  private func railWidth(hoveredIndex: Int?) -> CGFloat {
    let host = NSHostingView(
      rootView: ChatPromptTimeline(
        marks: marks, activeMarkID: "q1", gutter: gutter, hoveredIndex: hoveredIndex
      ) { _ in }
      .frame(height: 600)
      .fixedSize(horizontal: true, vertical: false)
    )
    host.layoutSubtreeIfNeeded()
    return host.fittingSize.width
  }
}

/// Reading a transcript into timeline marks.
final class ChatPromptTimelineSourceTests: XCTestCase {
  func testEachPromptCarriesTheReplyItDrew() {
    let sources = ChatPromptTimelineModel.sources(messages: [
      message("q1", "How do I set up SwiftPM?", .user),
      message("a1", "Open Xcode, then File > Add Packages.", .ai),
      message("q2", "And async/await?", .user),
      message("a2", "It lets you write concurrent code without callbacks.", .ai),
    ])

    XCTAssertEqual(sources.map(\.id), ["q1", "q2"])
    XCTAssertEqual(sources[0].prompt, "How do I set up SwiftPM?")
    XCTAssertEqual(sources[0].reply, "Open Xcode, then File > Add Packages.")
    XCTAssertEqual(sources[1].reply, "It lets you write concurrent code without callbacks.")
  }

  /// A reader can send twice before omi answers. The reply belongs to the second
  /// prompt, and the first must not borrow it.
  func testAPromptSentBeforeTheLastOneWasAnsweredShowsNoReply() {
    let sources = ChatPromptTimelineModel.sources(messages: [
      message("q1", "wait", .user),
      message("q2", "actually, never mind", .user),
      message("a2", "No problem.", .ai),
    ])

    XCTAssertEqual(sources[0].reply, "")
    XCTAssertEqual(sources[1].reply, "No problem.")
  }

  /// A single prompt tells the reader nothing they cannot already see.
  func testOnePromptEarnsNoTimeline() {
    let sources = ChatPromptTimelineModel.sources(messages: [
      message("q1", "hi", .user),
      message("a1", "hello", .ai),
    ])

    XCTAssertTrue(sources.isEmpty)
  }

  /// Markdown fences and hard wraps render as noise on a two-line card.
  func testThePreviewCollapsesTheTextToOneLine() {
    let sources = ChatPromptTimelineModel.sources(messages: [
      message("q1", "  fix   this\n\nplease  ", .user),
      message("a1", "```swift\nlet x = 1\n```", .ai),
      message("q2", "thanks", .user),
    ])

    XCTAssertEqual(sources[0].prompt, "fix this please")
    XCTAssertEqual(sources[0].reply, "```swift let x = 1 ```")
  }

  private func message(_ id: String, _ text: String, _ sender: ChatSender) -> ChatMessage {
    ChatMessage(id: id, text: text, sender: sender)
  }
}

/// Placing the marks. `LazyVStack` lays out only the rows near the viewport, so
/// the interesting cases are all about prompts whose rows have never been
/// measured.
final class ChatPromptTimelineMarkTests: XCTestCase {
  private let sources = (0..<5).map {
    ChatPromptSource(id: "q\($0)", prompt: "prompt \($0)", reply: "reply \($0)")
  }

  func testAFullyMeasuredTranscriptPlacesEveryMarkAtItsRealPosition() {
    let marks = ChatPromptTimelineModel.marks(
      sources: sources,
      offsets: ["q0": 0, "q1": 250, "q2": 500, "q3": 750, "q4": 1000],
      documentHeight: 1000
    )

    XCTAssertEqual(marks.map(\.fraction), [0, 0.25, 0.5, 0.75, 1.0])
  }

  /// Opening a long conversation: nothing is measured yet. Every prompt still
  /// gets a mark, because ticks that appear and vanish while scrolling are worse
  /// than ticks that are briefly approximate.
  func testAnUnmeasuredTranscriptStillDrawsEveryMark() {
    let marks = ChatPromptTimelineModel.marks(
      sources: sources, offsets: [:], documentHeight: 1000)

    XCTAssertEqual(marks.count, sources.count)
    XCTAssertEqual(marks.map(\.id), sources.map(\.id))
    XCTAssertEqual(marks.map(\.fraction), marks.map(\.fraction).sorted())
  }

  func testAMeasuredRowIsAuthoritativeAndItsNeighboursAreInterpolated() {
    let marks = ChatPromptTimelineModel.marks(
      sources: sources,
      offsets: ["q1": 200, "q3": 800],
      documentHeight: 1000
    )

    XCTAssertEqual(marks[1].fraction, 0.2, accuracy: 0.0001, "a measured row moved")
    XCTAssertEqual(marks[3].fraction, 0.8, accuracy: 0.0001, "a measured row moved")
    XCTAssertEqual(marks[2].fraction, 0.5, accuracy: 0.0001, "q2 sits midway between its neighbours")
    XCTAssertGreaterThan(marks[2].fraction, marks[1].fraction)
    XCTAssertLessThan(marks[2].fraction, marks[3].fraction)
  }

  /// Every mark must stay in transcript order whatever mix of measured and
  /// estimated positions it is built from — an out-of-order rail would send a
  /// click to the wrong prompt.
  func testMarksNeverFallOutOfTranscriptOrder() {
    for measured in [["q0": CGFloat(900)], ["q4": CGFloat(50)], ["q2": CGFloat(10), "q3": 990]] {
      let marks = ChatPromptTimelineModel.marks(
        sources: sources, offsets: measured, documentHeight: 1000)
      XCTAssertEqual(
        marks.map(\.fraction), marks.map(\.fraction).sorted(),
        "offsets \(measured) produced an out-of-order rail")
    }
  }

  /// The first layout pass reports nothing. Dividing by it would place every
  /// mark at the same spot, or at NaN.
  func testAnUnmeasuredDocumentDoesNotCollapseEveryMarkOntoOnePoint() {
    let marks = ChatPromptTimelineModel.marks(
      sources: sources, offsets: [:], documentHeight: 0)

    XCTAssertEqual(Set(marks.map(\.fraction)).count, sources.count)
    XCTAssertFalse(marks.contains { $0.fraction.isNaN })
  }

  func testFractionsStayInsideTheDocument() {
    let marks = ChatPromptTimelineModel.marks(
      sources: sources,
      offsets: ["q0": -40, "q4": 4000],
      documentHeight: 1000
    )

    XCTAssertTrue(marks.allSatisfy { $0.fraction >= 0 && $0.fraction <= 1 })
  }
}

/// Which mark is lit, and where ⌘↑ / ⌘↓ go next.
final class ChatPromptTimelineActiveMarkTests: XCTestCase {
  private let marks = [
    ChatPromptMark(id: "q0", prompt: "a", reply: "", fraction: 0.0),
    ChatPromptMark(id: "q1", prompt: "b", reply: "", fraction: 0.4),
    ChatPromptMark(id: "q2", prompt: "c", reply: "", fraction: 0.8),
  ]

  func testTheMarkBeingReadIsTheLastOneAboveTheReadingLine() {
    XCTAssertEqual(active(top: 0.0), "q0")
    XCTAssertEqual(active(top: 0.35), "q1")
    XCTAssertEqual(active(top: 0.75), "q2")
  }

  /// The reading line sits inside the viewport, not at its top edge, so a prompt
  /// scrolled just off the top is still the one being read.
  func testAPromptJustPastTheTopEdgeIsStillTheActiveOne() {
    XCTAssertEqual(active(top: 0.41), "q1", "q1 clipped by a hair and the marker jumped")
  }

  /// Scrolled above the first prompt there is nothing behind the reader, but the
  /// rail must still show where they are.
  func testScrolledAboveEverythingLightsTheFirstMark() {
    XCTAssertEqual(active(top: -0.2), "q0")
  }

  func testSteppingWalksTheMarksAndStopsAtBothEnds() {
    XCTAssertEqual(step(from: "q0", by: 1), "q1")
    XCTAssertEqual(step(from: "q1", by: -1), "q0")
    XCTAssertNil(step(from: "q2", by: 1), "stepping past the last prompt must not wrap")
    XCTAssertNil(step(from: "q0", by: -1), "stepping before the first prompt must not wrap")
  }

  /// The first press has to move somewhere, and it should be the end the reader
  /// is heading towards.
  func testSteppingFromNowhereEntersAtTheEndBeingTravelledTowards() {
    XCTAssertEqual(step(from: nil, by: 1), "q0")
    XCTAssertEqual(step(from: nil, by: -1), "q2")
  }

  private func active(top: CGFloat) -> String? {
    ChatPromptTimelineModel.activeMarkID(
      marks: marks, viewportTopFraction: top, viewportHeightFraction: 0.3)
  }

  private func step(from current: String?, by step: Int) -> String? {
    ChatPromptTimelineModel.steppedMarkID(marks: marks, from: current, by: step)
  }
}

/// Which mark is lit once measurement, scrolling and an outright choice all
/// have an opinion.
@MainActor
final class ChatTranscriptGeometrySelectionTests: XCTestCase {
  /// Two prompts a short answer apart, which is the case that broke: jumping to
  /// the first puts it at the very top of the viewport, and the second is
  /// already sitting on the reading line — so tracking alone lights the wrong
  /// one the moment the reader clicks.
  private let documentHeight: CGFloat = 1000
  private let viewport = CGSize(width: 900, height: 400)

  func testClickingAPromptLightsThatPromptAndNotTheOneBelowIt() {
    let geometry = loadedGeometry()
    geometry.setContent(height: documentHeight, scrollTop: 0)

    geometry.selectMark("q0")
    // The jump lands q0 at the top of the viewport.
    geometry.setContent(height: documentHeight, scrollTop: 0)

    XCTAssertEqual(geometry.activeMarkID, "q0", "the prompt below the clicked one stole the mark")
  }

  func testTheChoiceLightsBeforeTheTranscriptHasMoved() {
    let geometry = loadedGeometry()
    geometry.setContent(height: documentHeight, scrollTop: 0)

    geometry.selectMark("q2")

    XCTAssertEqual(
      geometry.activeMarkID, "q2", "the rail stayed unresponsive for the length of the jump")
  }

  /// A choice is not permanent. Once the reader scrolls, position is the truth
  /// again.
  func testScrollingReleasesTheChoiceBackToPositionTracking() {
    let geometry = loadedGeometry()
    geometry.selectMark("q0")
    geometry.setContent(height: documentHeight, scrollTop: 700)

    XCTAssertEqual(geometry.activeMarkID, "q0", "scrolling alone must not overrule a choice")

    geometry.releaseSelection()

    XCTAssertEqual(geometry.activeMarkID, "q2", "the rail never returned to tracking the reader")
  }

  /// Switching conversations retires the ids a pin was holding.
  func testAChoiceDoesNotSurviveTheConversationItWasMadeIn() {
    let geometry = loadedGeometry()
    geometry.selectMark("q1")

    geometry.reset()

    XCTAssertNil(geometry.activeMarkID)
  }

  private func loadedGeometry() -> ChatTranscriptGeometry {
    let geometry = ChatTranscriptGeometry()
    geometry.setViewport(viewport, columnWidth: 600)
    geometry.setMessages([
      ChatMessage(id: "q0", text: "first", sender: .user),
      ChatMessage(id: "a0", text: "short", sender: .ai),
      ChatMessage(id: "q1", text: "second", sender: .user),
      ChatMessage(id: "a1", text: "long", sender: .ai),
      ChatMessage(id: "q2", text: "third", sender: .user),
    ])
    // q1 sits 40pt below q0 — well inside the reading line's reach.
    geometry.setRowOffset(0, for: "q0")
    geometry.setRowOffset(40, for: "q1")
    geometry.setRowOffset(800, for: "q2")
    return geometry
  }
}

/// The rail's own geometry: spacing, the proximity ramp, and the hover card.
final class ChatPromptTimelineMetricsTests: XCTestCase {
  private let railHeight: CGFloat = 600

  /// The marks are one group, evenly spaced and centred — not a second
  /// scrollbar measuring the document.
  func testTheMarksSitAsOneEvenlySpacedGroup() {
    let positions = ChatPromptTimelineMetrics.positions(count: 5, railHeight: railHeight)

    for pair in zip(positions, positions.dropFirst()) {
      XCTAssertEqual(
        pair.1 - pair.0, ChatPromptTimelineMetrics.markSpacing, accuracy: 0.001,
        "the group is not evenly spaced: \(positions)")
    }
  }

  func testTheGroupIsCentredOnTheRail() {
    for count in [2, 5, 12] {
      let positions = ChatPromptTimelineMetrics.positions(count: count, railHeight: railHeight)
      let middle = ((positions.first ?? 0) + (positions.last ?? 0)) / 2
      XCTAssertEqual(
        middle, railHeight / 2, accuracy: 0.001, "\(count) marks drifted off centre")
    }
  }

  func testASingleMarkSitsOnTheCentreLine() {
    XCTAssertEqual(
      ChatPromptTimelineMetrics.positions(count: 1, railHeight: railHeight), [railHeight / 2])
  }

  /// A long conversation compresses its spacing rather than running off the
  /// ends of the rail.
  func testALongConversationCompressesInsteadOfOverflowing() {
    let positions = ChatPromptTimelineMetrics.positions(count: 400, railHeight: railHeight)

    XCTAssertGreaterThanOrEqual(
      positions.first ?? 0, ChatPromptTimelineMetrics.verticalPadding - 0.001)
    XCTAssertLessThanOrEqual(
      positions.last ?? 0, railHeight - ChatPromptTimelineMetrics.verticalPadding + 0.001)
    XCTAssertEqual(positions, positions.sorted())
  }

  /// A transcript loaded into a pane too short to draw anything must not produce
  /// negative geometry.
  func testACollapsedRailDoesNotProduceNegativePositions() {
    let positions = ChatPromptTimelineMetrics.positions(count: 3, railHeight: 4)

    XCTAssertTrue(positions.allSatisfy { $0 >= 0 && $0 <= 4 }, "got \(positions)")
  }

  /// Centred in the gutter, so the resting stack sits midway between the
  /// transcript's column and the shell's own scroller rather than pinned to
  /// either.
  func testTheRestingMarksSitOnTheGuttersCentreLine() {
    let gutter: CGFloat = 120
    let trailing = ChatPromptTimelineMetrics.trailingOffset(gutter: gutter)
    let restingCentre = trailing + ChatPromptTimelineMetrics.restWidth / 2

    XCTAssertEqual(restingCentre, gutter / 2, accuracy: 0.001)
  }

  func testAVanishingGutterNeverPushesTheRailOffTheTranscript() {
    XCTAssertEqual(ChatPromptTimelineMetrics.trailingOffset(gutter: 0), 0)
    XCTAssertGreaterThanOrEqual(ChatPromptTimelineMetrics.trailingOffset(gutter: 4), 0)
  }

  func testTheProximityRampPeaksUnderTheCursorAndDiesOffAtItsReach() {
    XCTAssertEqual(ChatPromptTimelineMetrics.proximity(distance: 0), 1, accuracy: 0.001)
    XCTAssertEqual(
      ChatPromptTimelineMetrics.proximity(distance: ChatPromptTimelineMetrics.proximityFalloff),
      0, accuracy: 0.001)
    XCTAssertEqual(ChatPromptTimelineMetrics.proximity(distance: 400), 0, accuracy: 0.001)
  }

  /// The point of the ramp is a hierarchy: a few marks either side clearly
  /// participate, in visibly decreasing order, and the far end of the group does
  /// not move at all. Too gentle and the whole stack breathes as one; too steep
  /// and only the mark under the cursor responds.
  func testTheRampReadsAsADecreasingHierarchyAcrossNeighbours() {
    let spacing = ChatPromptTimelineMetrics.markSpacing
    let steps = (0...5).map { ChatPromptTimelineMetrics.proximity(distance: spacing * CGFloat($0)) }

    for pair in zip(steps, steps.dropFirst()) {
      XCTAssertGreaterThan(pair.0, pair.1, "the ramp is flat somewhere in \(steps)")
    }
    XCTAssertGreaterThan(steps[1], 0.4, "the mark next to the cursor barely reacts")
    XCTAssertGreaterThan(steps[2], 0.2, "the second mark out barely reacts")
    XCTAssertLessThan(steps[4], 0.1, "the fourth mark out still grows noticeably")
    XCTAssertEqual(
      steps[5], 0, accuracy: 0.0001,
      "the far end of the group still reacts to a hover at the near end")
  }

  /// Linear decay makes the whole group swell as one: halfway to the edge of the
  /// reach it would still be at half strength.
  func testTheRampDecaysFasterThanLinearly() {
    let half = ChatPromptTimelineMetrics.proximity(
      distance: ChatPromptTimelineMetrics.proximityFalloff / 2)

    XCTAssertLessThan(half, 0.5, "the ramp is linear or gentler, so the group swells as one")
  }

  func testAMarkOnlyGrowsAndBrightensAsTheCursorApproaches() {
    let rest = ChatPromptTimelineMetrics.markWidth(isHovered: false, proximity: 0)
    let near = ChatPromptTimelineMetrics.markWidth(isHovered: false, proximity: 0.6)
    let hovered = ChatPromptTimelineMetrics.markWidth(isHovered: true, proximity: 1)

    XCTAssertLessThan(rest, near)
    XCTAssertLessThan(near, hovered)
    XCTAssertLessThan(
      ChatPromptTimelineMetrics.markOpacity(isHovered: false, isActive: false, proximity: 0),
      ChatPromptTimelineMetrics.markOpacity(isHovered: false, isActive: false, proximity: 1))
  }

  /// Size means "the cursor is here" and nothing else. Sizing the active mark
  /// too would have the rail reshape itself as the reader scrolls.
  func testTheActiveMarkIsColouredRatherThanResized() {
    XCTAssertEqual(
      ChatPromptTimelineMetrics.markWidth(isHovered: false, proximity: 0),
      ChatPromptTimelineMetrics.restWidth)
    XCTAssertNotEqual(
      ChatPromptTimelineMetrics.markColor(isActive: true),
      ChatPromptTimelineMetrics.markColor(isActive: false))
  }

  /// With the cursor off the rail entirely, every other mark fades to its
  /// resting wash — the active one still has to be findable.
  func testTheActiveMarkStaysVisibleWithNoCursorOnTheRail() {
    XCTAssertGreaterThan(
      ChatPromptTimelineMetrics.markOpacity(isHovered: false, isActive: true, proximity: 0),
      ChatPromptTimelineMetrics.markOpacity(isHovered: false, isActive: false, proximity: 0))
  }

  func testTheGapsBetweenMarksAreNotAHitTarget() {
    let positions: [CGFloat] = [100, 400]

    XCTAssertEqual(ChatPromptTimelineMetrics.index(nearest: 103, positions: positions), 0)
    XCTAssertEqual(ChatPromptTimelineMetrics.index(nearest: 396, positions: positions), 1)
    XCTAssertNil(
      ChatPromptTimelineMetrics.index(nearest: 250, positions: positions),
      "the empty middle of the rail resolved to a prompt")
  }

  /// The card is mounted beside the marks so it can overhang them. Overhanging
  /// the window is a clipped card.
  func testTheHoverCardIsHeldInsideTheRailAtBothEnds() {
    let card: CGFloat = 70

    let atTop = ChatPromptTimelineMetrics.previewCenterY(
      anchorY: 2, cardHeight: card, railHeight: railHeight)
    let atBottom = ChatPromptTimelineMetrics.previewCenterY(
      anchorY: railHeight - 2, cardHeight: card, railHeight: railHeight)

    XCTAssertGreaterThanOrEqual(atTop - card / 2, 0)
    XCTAssertLessThanOrEqual(atBottom + card / 2, railHeight)
  }

  func testTheHoverCardTracksTheMarkWhereThereIsRoom() {
    XCTAssertEqual(
      ChatPromptTimelineMetrics.previewCenterY(
        anchorY: 300, cardHeight: 70, railHeight: railHeight),
      300, accuracy: 0.001)
  }
}
