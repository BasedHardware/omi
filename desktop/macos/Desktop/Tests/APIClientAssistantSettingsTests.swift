import XCTest

@testable import Omi_Computer

final class APIClientAssistantSettingsTests: XCTestCase {

  func testAssistantSettingsDecodesValidSiblingsWhenOneKnownSectionIsMalformed() throws {
    let data = """
      {
        "focus": "not-yet-a-focus-object",
        "task": {
          "enabled": true,
          "min_confidence": 0.72
        },
        "floating_bar": {
          "voice_answers_enabled": true,
          "elevenlabs_voice_id": "voice-123"
        },
        "update_channel": "beta"
      }
      """.data(using: .utf8)!

    let response = try JSONDecoder().decode(AssistantSettingsResponse.self, from: data)

    XCTAssertNil(response.focus)
    XCTAssertEqual(response.task?.enabled, true)
    XCTAssertEqual(response.task?.minConfidence, 0.72)
    XCTAssertEqual(response.floatingBar?.voiceAnswersEnabled, true)
    XCTAssertEqual(response.floatingBar?.elevenlabsVoiceId, "voice-123")
    XCTAssertEqual(response.updateChannel, "beta")
  }

  func testAssistantSettingsPreservesUnknownFutureSectionsWhenReEncoding() throws {
    let data = """
      {
        "focus": {
          "enabled": false
        },
        "future_section": {
          "enabled": true,
          "threshold": 3,
          "labels": ["alpha", "beta"]
        }
      }
      """.data(using: .utf8)!

    let response = try JSONDecoder().decode(AssistantSettingsResponse.self, from: data)
    XCTAssertEqual(
      response.unknownSections["future_section"],
      .object([
        "enabled": .bool(true),
        "threshold": .int(3),
        "labels": .array([.string("alpha"), .string("beta")]),
      ])
    )

    let encoded = try JSONEncoder().encode(response)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
    let futureSection = try XCTUnwrap(object["future_section"] as? [String: Any])

    XCTAssertEqual(futureSection["enabled"] as? Bool, true)
    XCTAssertEqual(futureSection["threshold"] as? Int, 3)
    XCTAssertEqual(futureSection["labels"] as? [String], ["alpha", "beta"])
  }
}
