import XCTest

@testable import Omi_Computer

/// Every generated string enum accepts a value qualified with its Python enum name
/// ("GoalType.scale"), which #21091 first handled by hand for GoalType.
final class GeneratedEnumDecodingTests: XCTestCase {
  private func decode<T: Decodable>(_ type: T.Type, _ values: [String]) throws -> [T] {
    let data = try JSONEncoder().encode(values)
    return try JSONDecoder().decode([T].self, from: data)
  }

  func testGoalTypeDecodesQualifiedAndPlainValues() throws {
    let decoded = try decode(OmiAPI.GoalType.self, ["GoalType.scale", "scale", "GoalType.boolean", "numeric"])
    XCTAssertEqual(decoded, [.scale, .scale, .boolean, .numeric])
  }

  func testTaskStatusDecodesQualifiedAndPlainValues() throws {
    let decoded = try decode(OmiAPI.TaskStatus.self, ["TaskStatus.completed", "completed", "active"])
    XCTAssertEqual(decoded, [.completed, .completed, .active])
  }

  func testUnknownValuesStillFallBackQualifiedOrNot() throws {
    let decoded = try decode(OmiAPI.TaskStatus.self, ["TaskStatus.archived", "archived", "", "."])
    XCTAssertEqual(decoded, [._unknown, ._unknown, ._unknown, ._unknown])
  }
}
