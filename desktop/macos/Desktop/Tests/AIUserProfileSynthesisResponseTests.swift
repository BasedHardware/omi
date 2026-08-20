import XCTest

@testable import Omi_Computer

/// Wire contract for POST /v1/users/ai-profile/synthesize — the backend owns both
/// prompt stages, so the service only depends on this shape.
final class AIUserProfileSynthesisResponseTests: XCTestCase {

  func testDecodesProfileTextSourcesAndCount() throws {
    let rawJSON = """
      {
        "profile_text": "- User is an engineer",
        "data_sources_used": ["memories", "goals"],
        "item_count": 2
      }
      """

    let json = try XCTUnwrap(rawJSON.data(using: .utf8))
    let response = try JSONDecoder().decode(AIUserProfileSynthesisResponse.self, from: json)

    XCTAssertEqual(response.profileText, "- User is an engineer")
    XCTAssertEqual(response.dataSourcesUsed, ["memories", "goals"])
    XCTAssertEqual(response.itemCount, 2)
  }

  func testDecodesSynthesisWithNoContributingSources() throws {
    let rawJSON = """
      {"profile_text": "", "data_sources_used": [], "item_count": 0}
      """

    let json = try XCTUnwrap(rawJSON.data(using: .utf8))
    let response = try JSONDecoder().decode(AIUserProfileSynthesisResponse.self, from: json)

    XCTAssertEqual(response.profileText, "")
    XCTAssertTrue(response.dataSourcesUsed.isEmpty)
    XCTAssertEqual(response.itemCount, 0)
  }
}
