import XCTest

@testable import Omi_Computer

/// Unit tests for `Goal.progress`, which must stay within its documented
/// 0-100 range. Regression coverage for a bug where `current_value` below
/// `min_value` produced a negative percentage that leaked into the goal
/// progress ring (`Path.trim`) and the "% complete" prompt text.
final class GoalProgressTests: XCTestCase {

  /// Decode a `Goal` from minimal JSON. Dates are omitted so they fall back
  /// to the decoder defaults — `progress` does not depend on them.
  private func makeGoal(min: Double, target: Double, current: Double) throws -> Goal {
    let json = """
      {
        "id": "g1",
        "goal_type": "numeric",
        "min_value": \(min),
        "target_value": \(target),
        "current_value": \(current)
      }
      """
    return try JSONDecoder().decode(Goal.self, from: Data(json.utf8))
  }

  func testProgressMidRange() throws {
    let goal = try makeGoal(min: 0, target: 10, current: 5)
    XCTAssertEqual(goal.progress, 50, accuracy: 0.0001)
  }

  func testProgressClampsNegativeToZero() throws {
    // current below min would yield (2-5)/(15-5)*100 = -30 without clamping.
    let goal = try makeGoal(min: 5, target: 15, current: 2)
    XCTAssertEqual(goal.progress, 0, accuracy: 0.0001, "Progress must not go below 0")
  }

  func testProgressClampsOverachievementToHundred() throws {
    // current above target would yield 200 without clamping.
    let goal = try makeGoal(min: 0, target: 10, current: 20)
    XCTAssertEqual(goal.progress, 100, accuracy: 0.0001, "Progress must not exceed 100")
  }

  func testProgressIsZeroWhenTargetEqualsMin() throws {
    // Guard against divide-by-zero when the range is degenerate.
    let goal = try makeGoal(min: 5, target: 5, current: 5)
    XCTAssertEqual(goal.progress, 0, accuracy: 0.0001)
  }
}
