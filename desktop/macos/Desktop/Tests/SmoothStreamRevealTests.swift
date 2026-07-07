import XCTest

@testable import Omi_Computer

/// `SmoothStreamReveal.step` is the pure core of the smooth-streaming reveal:
/// given how much buffered text remains and how long since the previous flush
/// tick, it decides how many characters to reveal this tick. Adaptive cadence:
/// base ~5ms/char (~200 cps), accelerating with the backlog so the visible
/// text never trails the backend by more than ~`catchUpTicks` ticks.
final class SmoothStreamRevealTests: XCTestCase {

  /// The nominal flush cadence in ChatProvider (streamingFlushInterval).
  private let tickMs: Double = 35

  func testRevealsNothingWhenNoTextRemains() {
    XCTAssertEqual(SmoothStreamReveal.step(remaining: 0, elapsedMs: tickMs), 0)
    XCTAssertEqual(SmoothStreamReveal.step(remaining: -3, elapsedMs: tickMs), 0)
  }

  func testKeepsSteadyBaseRateWithSmallBacklog() {
    // base = 35/5 = 7; catchUp = 20/4 = 5 (doesn't dominate)
    XCTAssertEqual(SmoothStreamReveal.step(remaining: 20, elapsedMs: tickMs), 7)
  }

  func testAcceleratesToDrainLargeBacklogWithinCatchUpTicks() {
    // catchUp = 800/4 = 200 dominates over base 7
    let step = SmoothStreamReveal.step(remaining: 800, elapsedMs: tickMs)
    XCTAssertEqual(step, 200)
    // At that pace the backlog empties in `catchUpTicks` ticks
    XCTAssertEqual(Int((Double(800) / Double(step)).rounded(.up)), Int(SmoothStreamReveal.catchUpTicks))
  }

  func testNeverRevealsMoreThanRemaining() {
    // base = 7 but only 3 characters are left
    XCTAssertEqual(SmoothStreamReveal.step(remaining: 3, elapsedMs: tickMs), 3)
  }

  func testAlwaysProgressesAtLeastOneCharacterEvenWithZeroOrNegativeElapsed() {
    XCTAssertGreaterThanOrEqual(SmoothStreamReveal.step(remaining: 5, elapsedMs: 0), 1)
    XCTAssertGreaterThanOrEqual(SmoothStreamReveal.step(remaining: 5, elapsedMs: -50), 1)
  }

  func testLateTickRevealsProportionallyMore() {
    // A tick delayed by main-thread congestion reveals more, not less:
    // base = 140/5 = 28 vs the on-time 7 (catchUp = 100/4 = 25 doesn't dominate).
    XCTAssertEqual(SmoothStreamReveal.step(remaining: 100, elapsedMs: 140), 28)
  }

  func testSimulatedRevealLoopAlwaysDrains() {
    // Regardless of backlog size, the tick loop terminates with everything
    // revealed and strictly monotonic progress.
    for backlog in [1, 7, 42, 999, 10_000] {
      var remaining = backlog
      var ticks = 0
      while remaining > 0 {
        let step = SmoothStreamReveal.step(remaining: remaining, elapsedMs: tickMs)
        XCTAssertGreaterThanOrEqual(step, 1)
        XCTAssertLessThanOrEqual(step, remaining)
        remaining -= step
        ticks += 1
        XCTAssertLessThan(ticks, 10_000, "reveal loop failed to converge for backlog \(backlog)")
      }
      XCTAssertEqual(remaining, 0)
    }
  }
}
