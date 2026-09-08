import AppKit
import XCTest

@testable import Omi_Computer

/// The timeline track's arithmetic, driven through the same entry points the pointer drives.
///
/// The first test is the one that matters: it is the regression test for the defect this track was
/// built to repair. The strip it replaces mapped a pixel to an **array index**, so a pixel halfway
/// along the bar selected the middle *row* rather than the middle *moment* — with a three-hour gap in
/// the day, the two are nowhere near each other, and "drag left to go back in time" was not true.
@MainActor
final class RewindTrackTests: XCTestCase {

  /// A day with a long gap: five captures a minute apart, three hours of nothing, then five more.
  private func gappedDay() -> (instants: [Double], apps: [String]) {
    let base: Double = 1_700_000_000
    var instants: [Double] = []
    var apps: [String] = []
    for index in 0..<5 {
      instants.append(base + Double(index) * 60)
      apps.append("Xcode")
    }
    for index in 0..<5 {
      instants.append(base + 3 * 3600 + Double(index) * 60)
      apps.append("Safari")
    }
    return (instants, apps)
  }

  private func track(_ instants: [Double], _ apps: [String], width: CGFloat = 1000) -> RewindTrackNSView {
    let view = RewindTrackNSView(frame: NSRect(x: 0, y: 0, width: width, height: RewindTrackNSView.height))
    let range = RewindTrackWindow.fullRange(of: instants)
    view.apply(
      blocks: RewindTrackWindow.blocks(from: instants, apps: apps),
      instants: instants,
      searchResultIndices: nil,
      trackStart: range.lowerBound,
      trackSpan: range.upperBound - range.lowerBound,
      spanBounds: RewindTrackWindow.minimumSpan...(range.upperBound - range.lowerBound),
      playheadAt: nil)
    return view
  }

  // MARK: - The drag belongs to the scrubber, not to the window

  /// The scrubber's whole gesture *is* a drag. Giving it to AppKit's native window-background mode
  /// away leaves a control where a click seeks and a drag walks the window sideways — a failure that
  /// reads as a rendering quirk rather than a dead gesture, which is why it needs a test rather than
  /// a screenshot.
  func testTheTrackKeepsItsDragsRatherThanHandingThemToTheWindow() {
    let day = gappedDay()
    let track = track(day.instants, day.apps)
    XCTAssertFalse(track.mouseDownCanMoveWindow)
  }

  // MARK: - The time-linearity contract

  func testHalfwayAlongTheBarLandsInTheGapNotOnTheMiddleRow() throws {
    let day = gappedDay()
    let view = track(day.instants, day.apps)
    let range = RewindTrackWindow.fullRange(of: day.instants)
    let midInstant = range.lowerBound + (range.upperBound - range.lowerBound) / 2

    guard let index = view.nearestIndex(to: midInstant) else {
      return XCTFail("a day with captures in it must resolve every instant to one of them")
    }
    let selected = day.instants[index]

    // The array's middle row is index 4 or 5 — the last capture before the gap, or the first after.
    // Time's middle is an hour and a half into a three-hour gap, which is nearer neither than the
    // gap's own edges: the nearest capture is one of the two rows either side of it, and crucially
    // the mapping is by *instant*, so the pixel and the moment agree.
    XCTAssertTrue(
      abs(selected - midInstant) > 3600,
      "the midpoint of the bar is deep inside a three-hour gap; the nearest capture must be far from it")
    // And the arithmetic that proves the axis is time: a pixel one tenth along is one tenth of the
    // *day*, whatever the capture density there.
    let tenth = range.lowerBound + (range.upperBound - range.lowerBound) / 10
    let tenthIndex = try XCTUnwrap(view.nearestIndex(to: tenth))
    XCTAssertLessThan(
      day.instants[tenthIndex], range.lowerBound + (range.upperBound - range.lowerBound) / 2,
      "a tenth of the way through the day must resolve to a capture in the first half of it")
  }

  // MARK: - Hit test

  func testNearestIndexFindsTheExactCaptureAndTheEnds() {
    let day = gappedDay()
    let view = track(day.instants, day.apps)
    for (index, instant) in day.instants.enumerated() {
      XCTAssertEqual(view.nearestIndex(to: instant), index, "exact instant \(index)")
    }
    XCTAssertEqual(view.nearestIndex(to: day.instants[0] - 10_000), 0)
    XCTAssertEqual(view.nearestIndex(to: day.instants[day.instants.count - 1] + 10_000), day.instants.count - 1)
  }

  func testNearestIndexBreaksAMidpointTieTowardsTheEarlierCapture() {
    let view = track([100, 200], ["A", "A"])
    XCTAssertEqual(view.nearestIndex(to: 150), 0)
    XCTAssertEqual(view.nearestIndex(to: 151), 1)
  }

  func testNearestIndexIsNilWithNoCaptures() {
    XCTAssertNil(track([], []).nearestIndex(to: 0))
  }

  // MARK: - Blocks

  func testBlocksGroupContiguousAppsAndTile() {
    let day = gappedDay()
    let blocks = RewindTrackWindow.blocks(from: day.instants, apps: day.apps)
    XCTAssertEqual(blocks.map(\.app), ["Xcode", "Safari"])
    // The first block ends where the second begins — no seam the data did not put there.
    XCTAssertEqual(blocks[0].endedAt, blocks[1].startedAt)
    // The last block is given the run's own sampling interval rather than zero width.
    XCTAssertEqual(blocks[1].endedAt, day.instants[day.instants.count - 1] + 60, accuracy: 0.001)
  }

  func testBlocksSurviveAlternatingApps() {
    let blocks = RewindTrackWindow.blocks(from: [0, 1, 2, 3], apps: ["A", "B", "A", "B"])
    XCTAssertEqual(blocks.map(\.app), ["A", "B", "A", "B"])
  }

  func testBlocksAreEmptyWithoutCaptures() {
    XCTAssertTrue(RewindTrackWindow.blocks(from: [], apps: []).isEmpty)
  }

  // MARK: - Tick ladder

  func testTickLadderPicksTheFirstIntervalYieldingTwelveMarksOrFewer() {
    // A day is 2-hour marks: 24h/1h is 24 marks, 24h/2h is 12.
    XCTAssertEqual(RewindTrackNSView.tickInterval(forSpan: 24 * 3600), 2 * 3600)
    // An hour is minute marks only until there are more than twelve of them.
    XCTAssertEqual(RewindTrackNSView.tickInterval(forSpan: 600), 60)
    XCTAssertEqual(RewindTrackNSView.tickInterval(forSpan: 3600), 300)
    XCTAssertEqual(RewindTrackNSView.tickInterval(forSpan: 6 * 3600), 1800)
    // Past the ladder's top the marks are a day apart rather than absent.
    XCTAssertEqual(RewindTrackNSView.tickInterval(forSpan: 30 * 24 * 3600), 24 * 3600)
  }

  /// Caught live: on a day with ten minutes of capture in it the ladder picks one-minute ticks, and
  /// the reference's `h a` format printed `12 AM` on every one of them.
  func testSubHourTicksAreLabelledWithMinutes() {
    let noon = Date(timeIntervalSince1970: 1_700_000_000)
    let minutes = RewindTrackNSView.tickFormatter(forInterval: 60)
    let hours = RewindTrackNSView.tickFormatter(forInterval: 3600)
    XCTAssertTrue(minutes.string(from: noon).contains(":"), "a minute-spaced tick must show minutes")
    XCTAssertFalse(hours.string(from: noon).contains(":"), "an hour-spaced tick reads as a whole hour")
    XCTAssertNotEqual(
      minutes.string(from: noon),
      minutes.string(from: noon.addingTimeInterval(60)),
      "two ticks a minute apart must not carry the same label")
  }

  func testAllTimeDayTicksNameDatesRatherThanRepeatingMidnight() {
    let first = Date(timeIntervalSince1970: 1_700_000_000)
    let formatter = RewindTrackNSView.tickFormatter(forInterval: 24 * 3600)

    XCTAssertNotEqual(
      formatter.string(from: first),
      formatter.string(from: first.addingTimeInterval(24 * 3600)),
      "an all-time track must distinguish consecutive day ticks")
  }

  // MARK: - Continuous pan direction

  func testRightwardSwipeMovesTheAscendingTimelineTowardsNewerFrames() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...10_000, initialWindow: 4_000...5_000)
    model.pan(deltaX: -60, deltaY: 0, pointsPerSpan: 600)
    XCTAssertEqual(
      model.start, 4_100, accuracy: 0.001,
      "AppKit reports a rightward swipe with a negative delta; the viewport must still move right/newer")
  }

  func testLeftwardSwipeMovesTheAscendingTimelineTowardsOlderFrames() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...10_000, initialWindow: 4_000...5_000)
    model.pan(deltaX: 60, deltaY: 0, pointsPerSpan: 600)
    XCTAssertEqual(model.start, 3_900, accuracy: 0.001)
  }

  func testDiagonalSwipeUsesItsDominantAxisInsteadOfCancellingDirections() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...10_000, initialWindow: 4_000...5_000)
    model.pan(deltaX: -60, deltaY: 50, pointsPerSpan: 600)
    XCTAssertEqual(model.start, 4_100, accuracy: 0.001, "a slight vertical component must not cancel the pan")
  }

  func testScrollDownMovesTheAscendingTimelineTowardsNewerFrames() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...10_000, initialWindow: 4_000...5_000)
    model.pan(deltaX: 0, deltaY: 60, pointsPerSpan: 600)
    XCTAssertEqual(model.start, 4_100, accuracy: 0.001)
  }

  func testViewportReloadTargetsTheCaptureNearestItsCentre() {
    let screenshots = [
      Screenshot(timestamp: Date(timeIntervalSince1970: 100), appName: "A", imagePath: "1.jpg"),
      Screenshot(timestamp: Date(timeIntervalSince1970: 200), appName: "A", imagePath: "2.jpg"),
      Screenshot(timestamp: Date(timeIntervalSince1970: 300), appName: "B", imagePath: "3.jpg"),
    ]

    XCTAssertEqual(RewindTimelineNavigation.nearestIndex(to: 249, screenshots: screenshots), 1)
    XCTAssertEqual(RewindTimelineNavigation.nearestIndex(to: 251, screenshots: screenshots), 2)
    XCTAssertNil(RewindTimelineNavigation.clampedIndex(0, screenshots: []))
    XCTAssertEqual(RewindTimelineNavigation.clampedIndex(99, screenshots: screenshots), 2)
  }

  func testAnEmptyViewportKeepsTheTimelineWhenRetainedHistoryExists() {
    XCTAssertTrue(RewindTimelinePresentation.showsTimeline(screenshotCount: 0, historyRange: 100...200))
    XCTAssertFalse(RewindTimelinePresentation.showsTimeline(screenshotCount: 0, historyRange: nil))
  }

  func testLiveRefreshRequiresAViewportContainingNowOrParkedAtTheLiveEdge() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertTrue(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: 900...1_100, newestLoadedTimestamp: nil, now: now))
    XCTAssertFalse(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: 100...200, newestLoadedTimestamp: nil, now: now))
    // Parked at the live edge: the viewport ends at the newest loaded frame, which trails now.
    XCTAssertTrue(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: 800...950, newestLoadedTimestamp: 950, now: now))
    // Panned into older history: the newest loaded frame lies beyond the viewport's end.
    XCTAssertFalse(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: 100...200, newestLoadedTimestamp: 950, now: now))
    XCTAssertFalse(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: nil, newestLoadedTimestamp: 950, now: now))
    // The player sitting on the newest loaded frame is the live edge even when the track
    // viewport is panned into older history (e.g. a restored viewport from a prior session).
    XCTAssertTrue(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: 100...200, newestLoadedTimestamp: 950, now: now,
        isPlayerParkedOnNewestFrame: true))
    XCTAssertTrue(
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: nil, newestLoadedTimestamp: nil, now: now,
        isPlayerParkedOnNewestFrame: true))
  }

  func testPlayerFollowsAppendsOnlyWhenParkedOnTheNewestFrame() {
    // Parked on the newest frame and the array grew → follow to the new newest.
    XCTAssertEqual(RewindTimelineNavigation.sameFrameIndex(old: 10, new: 12, current: 9, found: 9), 11)
    // Scrubbed back → keep the viewed frame even though the array grew.
    XCTAssertEqual(RewindTimelineNavigation.sameFrameIndex(old: 10, new: 12, current: 5, found: 5), 5)
    // Sampled-window replacement moved the viewed frame → track it, no live-edge jump.
    XCTAssertEqual(RewindTimelineNavigation.sameFrameIndex(old: 10, new: 12, current: 9, found: 4), 4)
    // Same-size reload with the frame still last → stay put.
    XCTAssertEqual(RewindTimelineNavigation.sameFrameIndex(old: 10, new: 10, current: 9, found: 9), 9)
  }

  func testNewCaptureExtendsTheRetainedHistoryUpperBound() {
    XCTAssertEqual(
      RewindTrackWindow.extending(nil, toInclude: Date(timeIntervalSince1970: 250)),
      250...280
    )
    let extended = RewindTrackWindow.extending(
      100...200,
      toInclude: Date(timeIntervalSince1970: 250)
    )
    XCTAssertEqual(extended, 100...280)
  }

  // MARK: - Zoom bounds

  func testClampKeepsTheWindowInsideRetainedHistory() {
    let range: ClosedRange<Double> = 0...3600
    let past = RewindTrackWindow.clamp(start: 3500, span: 600, within: range)
    XCTAssertEqual(past.start, 3000, accuracy: 0.001, "a window may not hang off the end of history")
    XCTAssertEqual(past.span, 600, accuracy: 0.001)

    let tooWide = RewindTrackWindow.clamp(start: -500, span: 999_999, within: range)
    XCTAssertEqual(tooWide.start, 0, accuracy: 0.001)
    XCTAssertEqual(tooWide.span, 3600, accuracy: 0.001, "a window may not be wider than history")

    let tooNarrow = RewindTrackWindow.clamp(start: 0, span: 1, within: range)
    XCTAssertEqual(tooNarrow.span, RewindTrackWindow.minimumSpan, accuracy: 0.001)
  }

  func testZoomOutProgressivelyReachesAllHistoryAndZoomInStopsAtAMinute() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...14_400, initialWindow: 10_800...14_400)
    XCTAssertEqual(model.span, 3600, accuracy: 0.001, "first paint stays on the recent window")
    XCTAssertTrue(model.canZoomOut, "older retained history remains reachable without a day reload")
    XCTAssertTrue(model.canZoomIn)

    for _ in 0..<20 { model.zoom(in: true) }
    XCTAssertEqual(model.span, RewindTrackWindow.minimumSpan, accuracy: 0.001)
    XCTAssertFalse(model.canZoomIn)

    for _ in 0..<20 { model.zoom(in: false) }
    XCTAssertEqual(model.start, 0, accuracy: 0.001)
    XCTAssertEqual(model.span, 14_400, accuracy: 0.001)
    XCTAssertFalse(model.canZoomOut)
  }

  func testRevealPullsAnOffscreenInstantBackIntoTheWindow() {
    let model = RewindTrackWindowModel()
    model.adopt(range: 0...3600)
    model.set(start: 0, span: 600)
    model.reveal(3000)
    XCTAssertTrue(
      3000 >= model.start && 3000 <= model.start + model.span,
      "stepping frames must not walk the playhead off a zoomed track")
  }

  // MARK: - Sampling interval

  func testMedianIntervalIsMeasuredRatherThanAssumed() {
    XCTAssertEqual(RewindTrackWindow.medianInterval(of: [0, 5, 10, 15, 20]), 5, accuracy: 0.001)
    // One enormous gap must not drag the interval with it — that is what a median is for.
    XCTAssertEqual(RewindTrackWindow.medianInterval(of: [0, 5, 10, 100_000]), 5, accuracy: 0.001)
    XCTAssertEqual(RewindTrackWindow.medianInterval(of: [42]), 60, accuracy: 0.001)
  }
}
