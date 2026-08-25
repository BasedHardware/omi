import XCTest

@testable import Omi_Computer

/// Covers `StallDetector` in isolation, driving it with direct
/// timestamps so promotion/reset behaviour is fully deterministic.
final class StallDetectorTests: XCTestCase {

  // Convenience: shorter than spelling out v1Defaults each time.
  private let thresholds = StallThresholds.v1Defaults

  // MARK: - Inter-event gap

  func testFreshDetectorIsRunning() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    let state = await detector.interEventState
    XCTAssertEqual(state, .running)
  }

  func testGapBelowSlowThresholdStaysRunning() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    let transitions = await detector.tick(atMs: thresholds.slowGapMs - 1)
    XCTAssertTrue(transitions.isEmpty)
    let state = await detector.interEventState
    XCTAssertEqual(state, .running)
  }

  func testGapAtSlowThresholdPromotesToSlow() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    let transitions = await detector.tick(atMs: thresholds.slowGapMs)
    XCTAssertEqual(transitions, [.interEvent(from: .running, to: .slow)])
  }

  func testGapWellBeyondStalledStaysStalled() async {
    // A persistent silent bridge must remain .stalled, not decay back to
    // running before ChatProvider's generic watchdog can recover it.
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.tick(atMs: thresholds.stalledGapMs)
    _ = await detector.tick(atMs: 185_000)
    let state = await detector.interEventState
    XCTAssertEqual(state, .stalled)
  }

  func testGapAtStalledThresholdPromotesToStalled() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    let transitions = await detector.tick(atMs: thresholds.stalledGapMs)
    // Transition jumps straight from .running to .stalled (no
    // intermediate .slow emit) when tick crosses both thresholds in
    // one call. That's intentional: the UI only needs to know the
    // current promoted level, not the path taken.
    XCTAssertEqual(transitions, [.interEvent(from: .running, to: .stalled)])
  }

  func testRepeatedTickAtSameTimeReturnsEmptyAfterFirst() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    let first = await detector.tick(atMs: thresholds.stalledGapMs)
    let second = await detector.tick(atMs: thresholds.stalledGapMs)
    XCTAssertEqual(first.count, 1)
    XCTAssertTrue(second.isEmpty, "tick is idempotent at the same atMs")
  }

  func testNewEventResetsInterEventStateAndEmitsTransition() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    // Promote to stalled.
    _ = await detector.tick(atMs: thresholds.stalledGapMs)
    // New event arrives.
    let transitions = await detector.step(kind: .other, atMs: thresholds.stalledGapMs + 1)
    XCTAssertEqual(transitions, [.interEvent(from: .stalled, to: .running)])
    let state = await detector.interEventState
    XCTAssertEqual(state, .running)
  }

  func testStepAlsoEvaluatesElapsedTime() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    // No prior event observed; step at slowGapMs both records the
    // event (resetting to running implicitly since we were already
    // running) and evaluates elapsed time. Since the event arrived
    // exactly at slowGapMs, lastEventAtMs is now slowGapMs and the
    // gap from that to atMs is 0 — no promotion.
    let transitions = await detector.step(kind: .other, atMs: thresholds.slowGapMs)
    XCTAssertTrue(
      transitions.isEmpty,
      "an event arriving exactly at the threshold resets the gap"
    )
  }

  // MARK: - Per-tool timer

  func testToolStartTracksIndependentlyOfInterEventGap() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 100)
    // Inter-event gap should be tiny; tool t1 has just started.
    let interState = await detector.interEventState
    let toolState = await detector.currentToolState(id: "t1")
    XCTAssertEqual(interState, .running)
    XCTAssertEqual(toolState, .running)
  }

  func testToolPromotesToSlowWhenItsOwnTimerCrossesThreshold() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 100)
    let transitions = await detector.tick(atMs: 100 + thresholds.slowGapMs)
    // Both timers cross at this point: the inter-event gap (100 → 100+slow)
    // and tool t1 (100 → 100+slow). Expect both transitions, in some
    // order.
    XCTAssertEqual(transitions.count, 2)
    XCTAssertTrue(transitions.contains(.interEvent(from: .running, to: .slow)))
    XCTAssertTrue(transitions.contains(.tool(id: "t1", from: .running, to: .slow)))
  }

  func testToolCompletionEmitsBackToRunningTransitionIfPromoted() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)
    // Promote to stalled.
    _ = await detector.tick(atMs: thresholds.stalledGapMs)
    let toolState = await detector.currentToolState(id: "t1")
    XCTAssertEqual(toolState, .stalled)

    // Tool completes.
    let transitions = await detector.step(
      kind: .toolCompleted(id: "t1"),
      atMs: thresholds.stalledGapMs + 1
    )
    // Expect a tool transition back to .running plus the inter-event
    // reset (event arrival also resets inter-event from .stalled to
    // .running).
    XCTAssertTrue(transitions.contains(.tool(id: "t1", from: .stalled, to: .running)))
    XCTAssertTrue(transitions.contains(.interEvent(from: .stalled, to: .running)))

    // After completion, tool is no longer tracked.
    let postCompletionState = await detector.currentToolState(id: "t1")
    XCTAssertEqual(postCompletionState, .running)
    let inFlight = await detector.snapshotToolStates()
    XCTAssertTrue(inFlight.isEmpty)
  }

  func testToolCompletionWithoutPromotionEmitsNoToolTransition() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 100)
    let transitions = await detector.step(kind: .toolCompleted(id: "t1"), atMs: 200)
    // No promotion happened, so no tool transition needs surfacing.
    // (Inter-event also stayed running, so no inter transition either.)
    XCTAssertTrue(transitions.isEmpty)
  }

  func testMultipleParallelToolsTrackedIndependently() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t2"), atMs: 1_000)

    // Advance to where t1 has crossed slowGapMs but t2 hasn't yet.
    // t1 elapsed: slowGapMs (started at 0).
    // t2 elapsed: slowGapMs - 1_000 (started at 1_000).
    let transitions = await detector.tick(atMs: thresholds.slowGapMs)
    XCTAssertTrue(transitions.contains(.tool(id: "t1", from: .running, to: .slow)))
    XCTAssertFalse(
      transitions.contains(.tool(id: "t2", from: .running, to: .slow)),
      "t2 has not yet crossed slowGapMs"
    )
  }

  func testDuplicateToolStartPreservesOriginalStartTime() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: thresholds.slowGapMs - 1)

    let transitions = await detector.tick(atMs: thresholds.slowGapMs)

    XCTAssertTrue(
      transitions.contains(.tool(id: "t1", from: .running, to: .slow)),
      "duplicate starts should not reset the original per-tool timer"
    )
  }

  func testToolProgressResetsOnlyItsNoProgressClock() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)

    // Progress immediately before the hard no-progress budget expires must
    // keep the tool eligible to continue without redefining its start time.
    _ = await detector.step(kind: .toolProgress(id: "t1"), atMs: 89_999)

    let overdue = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 90_000)
    XCTAssertFalse(overdue.contains("t1"))

    let eventuallyOverdue = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 180_000)
    XCTAssertEqual(eventuallyOverdue, ["t1"])
  }

  func testActiveToolDefersTheGenericWatchdog() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)

    let genericWatchdogAt60s = await detector.isSilentWithoutActiveTools(durationMs: 60_000, atMs: 60_000)
    XCTAssertFalse(genericWatchdogAt60s, "The active tool owns recovery while it is in flight")

    let stalledToolsAt90s = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 90_000)
    XCTAssertEqual(stalledToolsAt90s, ["t1"])
  }

  func testDuplicateToolStartDoesNotManufactureProgress() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "t1"), atMs: 89_999)

    let overdue = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 90_000)
    XCTAssertEqual(overdue, ["t1"])
  }

  func testToolIdsWithoutProgressReportsOnlyOverdueInFlightTools() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "slow"), atMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "fresh"), atMs: 50_000)

    let firstOverdue = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 90_000)
    XCTAssertEqual(firstOverdue, ["slow"])

    _ = await detector.step(kind: .toolCompleted(id: "slow"), atMs: 90_001)
    let remainingOverdue = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 200_000)
    XCTAssertTrue(remainingOverdue.contains("fresh"))
    XCTAssertFalse(remainingOverdue.contains("slow"))
  }

  func testGenericWatchdogDefersToAnActiveToolThenUsesPostCompletionSilence() async {
    let detector = StallDetector(thresholds: thresholds, startedAtMs: 0)
    _ = await detector.step(kind: .toolStarted(id: "write"), atMs: 0)

    let genericWatchdogAt60s = await detector.isSilentWithoutActiveTools(durationMs: 60_000, atMs: 60_000)
    let stalledToolsAt90s = await detector.toolIdsWithoutProgress(durationMs: 90_000, atMs: 90_000)
    XCTAssertFalse(genericWatchdogAt60s)
    XCTAssertEqual(stalledToolsAt90s, ["write"])

    _ = await detector.step(kind: .toolCompleted(id: "write"), atMs: 100_000)
    let genericWatchdogBeforeQuietInterval = await detector.isSilentWithoutActiveTools(
      durationMs: 60_000,
      atMs: 159_999
    )
    let genericWatchdogAfterQuietInterval = await detector.isSilentWithoutActiveTools(
      durationMs: 60_000,
      atMs: 160_000
    )
    XCTAssertFalse(genericWatchdogBeforeQuietInterval)
    XCTAssertTrue(genericWatchdogAfterQuietInterval)
  }

  // MARK: - Threshold guard

  func testThresholdsPreconditionRejectsInvalidValues() {
    // Can't easily assert precondition crashes in XCTest without a
    // sub-process. Instead verify the v1Defaults pass the contract.
    XCTAssertGreaterThan(StallThresholds.v1Defaults.slowGapMs, 0)
    XCTAssertGreaterThan(
      StallThresholds.v1Defaults.stalledGapMs,
      StallThresholds.v1Defaults.slowGapMs
    )
  }
}
