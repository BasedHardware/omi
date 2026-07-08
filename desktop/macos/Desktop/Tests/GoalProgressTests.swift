import XCTest

@testable import Omi_Computer

final class GoalProgressTests: XCTestCase {
  private func makeGoal(min: Double, target: Double, current: Double) throws -> Goal {
    let json = """
      {
        "id": "goal-1",
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

  func testProgressClampsBelowMinToZero() throws {
    let goal = try makeGoal(min: 5, target: 15, current: 2)
    XCTAssertEqual(goal.progress, 0, accuracy: 0.0001)
  }

  func testProgressClampsAboveTargetToHundred() throws {
    let goal = try makeGoal(min: 0, target: 10, current: 20)
    XCTAssertEqual(goal.progress, 100, accuracy: 0.0001)
  }

  func testProgressIsZeroWhenTargetEqualsMin() throws {
    let goal = try makeGoal(min: 5, target: 5, current: 5)
    XCTAssertEqual(goal.progress, 0, accuracy: 0.0001)
  }
}
