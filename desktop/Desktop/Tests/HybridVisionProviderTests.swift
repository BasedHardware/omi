import XCTest

@testable import Omi_Computer

final class HybridVisionProviderTests: XCTestCase {

  func testIsConfiguredWhenVisionProviderOpenAICompatible() throws {
    let settings = try Self.decodeSettings(
      key: "vision_provider",
      value: ["kind": "openai_compatible", "base_url": "https://api.example.com/v1"]
    )
    XCTAssertTrue(HybridVisionProvider.isConfigured(settings: settings))
  }

  func testIsNotConfiguredWithoutVisionProvider() throws {
    let settings = try Self.decodeSettings(
      key: "embedding_provider",
      value: ["kind": "openai_compatible", "base_url": "https://api.example.com/v1"]
    )
    XCTAssertFalse(HybridVisionProvider.isConfigured(settings: settings))
  }

  func testIsNotConfiguredWhenBaseUrlMissing() throws {
    let settings = try Self.decodeSettings(
      key: "vision_provider",
      value: ["kind": "openai_compatible"]
    )
    XCTAssertFalse(HybridVisionProvider.isConfigured(settings: settings))
  }

  private static func decodeSettings(key: String, value: [String: Any]) throws -> [LocalDaemonSetting] {
    let valueJsonData = try JSONSerialization.data(withJSONObject: value)
    guard let valueJson = String(data: valueJsonData, encoding: .utf8) else {
      struct EncodeError: Error {}
      throw EncodeError()
    }
    let row: [String: Any] = [
      "key": key,
      "value_json": valueJson,
      "updated_at": "2026-05-19T12:00:00Z",
    ]
    let payload = try JSONSerialization.data(withJSONObject: [row])
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode([LocalDaemonSetting].self, from: payload)
  }
}
