import XCTest

@testable import Omi_Computer

/// Wire contract for POST /v1/connectors/synthesize — the backend owns the
/// calendar/gmail/notes prompts, so the readers only depend on this shape.
final class ConnectorSynthesisResponseTests: XCTestCase {

  func testDecodesMemoriesTasksAndProfile() throws {
    let rawJSON = """
      {
        "memories": ["The user runs a weekly standup"],
        "tasks": [
          {"description": "Prep the Q3 demo", "priority": "high", "due_at": "2026-08-11T09:00:00Z"}
        ],
        "profile": "Engineering manager."
      }
      """

    let json = try XCTUnwrap(rawJSON.data(using: .utf8))
    let response = try JSONDecoder().decode(ConnectorSynthesisResponse.self, from: json)

    XCTAssertEqual(response.memories, ["The user runs a weekly standup"])
    XCTAssertEqual(response.tasks.count, 1)
    XCTAssertEqual(response.tasks[0].description, "Prep the Q3 demo")
    XCTAssertEqual(response.tasks[0].priority, "high")
    XCTAssertEqual(response.tasks[0].dueAt, "2026-08-11T09:00:00Z")
    XCTAssertEqual(response.profile, "Engineering manager.")
  }

  func testDecodesEmptySynthesis() throws {
    let rawJSON = """
      {"memories": [], "tasks": [], "profile": ""}
      """

    let json = try XCTUnwrap(rawJSON.data(using: .utf8))
    let response = try JSONDecoder().decode(ConnectorSynthesisResponse.self, from: json)

    XCTAssertTrue(response.memories.isEmpty)
    XCTAssertTrue(response.tasks.isEmpty)
    XCTAssertEqual(response.profile, "")
  }
}
