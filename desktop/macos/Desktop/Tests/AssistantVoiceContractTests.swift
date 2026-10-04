import Foundation
import XCTest

@testable import Omi_Computer

final class AssistantVoiceContractTests: XCTestCase {

  func testCatalogDecodesServedShape() throws {
    let data = Data(
      #"{"voices":[{"id":"Zephyr","name":"Zephyr"},{"id":"Charon","name":"Charon"}],"default_voice_id":"Charon"}"#
        .utf8)
    let catalog = try JSONDecoder().decode(AssistantVoiceCatalogResponse.self, from: data)
    XCTAssertEqual(
      catalog.voices,
      [
        AssistantVoiceEntry(id: "Zephyr", name: "Zephyr"),
        AssistantVoiceEntry(id: "Charon", name: "Charon"),
      ])
    XCTAssertEqual(catalog.defaultVoiceId, "Charon")
  }

  func testCatalogWithDuplicateIdsDecodesWithoutTrapping() throws {
    let data = Data(
      #"{"voices":[{"id":"Charon","name":"Charon"},{"id":"Charon","name":"Charon alt"}],"default_voice_id":"Charon"}"#
        .utf8)
    let catalog = try JSONDecoder().decode(AssistantVoiceCatalogResponse.self, from: data)
    XCTAssertEqual(catalog.voices.count, 2)
  }

  func testPreferenceRoundTripsTheSnakeCaseKey() throws {
    let decoded = try JSONDecoder().decode(
      AssistantVoicePreferenceResponse.self, from: Data(#"{"voice_id":"Kore"}"#.utf8))
    XCTAssertEqual(decoded.voiceId, "Kore")

    let encoded = try JSONEncoder().encode(AssistantVoicePreferenceUpdate(voiceId: "Kore"))
    let fields = try JSONSerialization.jsonObject(with: encoded) as? [String: String]
    XCTAssertEqual(fields, ["voice_id": "Kore"])
  }

  func testMalformedCatalogPayloadThrowsNotTraps() {
    let data = Data(#"{"voices":{}}"#.utf8)
    XCTAssertThrowsError(try JSONDecoder().decode(AssistantVoiceCatalogResponse.self, from: data))
  }
}
