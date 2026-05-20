import XCTest

@testable import Omi_Computer

final class HybridLLMProviderConfigTests: XCTestCase {

  func testResolveEffectivePrefersChatProviderOverAiProvider() throws {
    let payload = """
      [{"key":"chat_provider","value_json":"{\\"kind\\":\\"openai_compatible\\",\\"base_url\\":\\"http://chat.local/v1\\",\\"model\\":\\"m-chat\\"}","updated_at":"2026-05-19T12:00:00Z"},{"key":"ai_provider","value_json":"{\\"kind\\":\\"openai_compatible\\",\\"base_url\\":\\"http://ai.local/v1\\",\\"model\\":\\"m-ai\\"}","updated_at":"2026-05-19T12:00:00Z"}]
      """
    let settings = try decodeSettings(payload)
    let config = HybridLLMClient.resolveEffectiveChatConfig(settings: settings)
    XCTAssertEqual(config?.baseURL, "http://chat.local/v1")
    XCTAssertEqual(config?.model, "m-chat")
  }

  func testResolveEffectiveFallsBackToProviderAlias() throws {
    let payload = """
      [{"key":"provider","value_json":"{\\"kind\\":\\"openai\\",\\"base_url\\":\\"http://legacy.local/v1\\",\\"model\\":\\"legacy\\"}","updated_at":"2026-05-19T12:00:00Z"}]
      """
    let settings = try decodeSettings(payload)
    let config = HybridLLMClient.resolveEffectiveChatConfig(settings: settings)
    XCTAssertEqual(config?.baseURL, "http://legacy.local/v1")
    XCTAssertEqual(config?.model, "legacy")
  }

  func testVisionProviderLoadsWhenConfigured() throws {
    let payload = """
      [{"key":"vision_provider","value_json":"{\\"kind\\":\\"openai_compatible\\",\\"base_url\\":\\"http://vision.local/v1\\",\\"model\\":\\"vlm\\"}","updated_at":"2026-05-19T12:00:00Z"}]
      """
    let settings = try decodeSettings(payload)
    let config = HybridLLMClient.loadVisionProviderConfig(from: settings)
    XCTAssertEqual(config?.baseURL, "http://vision.local/v1")
    XCTAssertEqual(config?.model, "vlm")
  }

  func testHybridChatClientUsesChatProviderPolicySlot() throws {
    let settings = try makeSettings([
      (
        "provider_policy",
        [
          "version": 1,
          "provider_accounts": [
            [
              "id": "local-chat",
              "kind": "openai_compatible",
              "base_url": "http://chat.local/v1",
              "api_key": "test-key",
            ]
          ],
          "model_slots": [
            "chat": [
              "provider_account_id": "local-chat",
              "model_id": "chat-model",
            ]
          ],
        ]
      )
    ])
    let response = try XCTUnwrap(HybridProviderPolicy.resolveSlotFromSettings("chat", settings: settings))
    let config = HybridChatClient.resolveEffectiveChatConfig(from: response)
    XCTAssertEqual(config?.baseURL, "http://chat.local/v1")
    XCTAssertEqual(config?.model, "chat-model")
    XCTAssertEqual(config?.providerAccountID, "local-chat")
  }

  func testProactiveUsesProviderPolicySlot() throws {
    let settings = try makeSettings([
      (
        "provider_policy",
        [
          "version": 1,
          "provider_accounts": [
            [
              "id": "local-proactive",
              "kind": "openai_compatible",
              "base_url": "http://proactive.local/v1",
              "api_key": "test-key",
            ]
          ],
          "model_slots": [
            "proactive": [
              "provider_account_id": "local-proactive",
              "model_id": "gpt-5.4-mini",
              "options": ["json_mode": true],
            ]
          ],
        ]
      )
    ])

    let config = HybridLLMClient.resolveEffectiveProactiveConfig(settings: settings)

    XCTAssertEqual(config?.baseURL, "http://proactive.local/v1")
    XCTAssertEqual(config?.model, "gpt-5.4-mini")
    XCTAssertEqual(config?.apiKey, "test-key")
  }

  func testProactiveDoesNotFallBackToChatProvider() throws {
    let settings = try makeSettings([
      (
        "chat_provider",
        [
          "kind": "openai_compatible",
          "base_url": "http://chat.local/v1",
          "model": "chat-model",
        ]
      )
    ])

    XCTAssertNil(HybridLLMClient.resolveEffectiveProactiveConfig(settings: settings))
  }

  func testProactiveResolutionSurfacesMissingProviderReason() throws {
    let settings = try makeSettings([
      (
        "provider_policy",
        [
          "version": 1,
          "provider_accounts": [],
          "model_slots": [
            "proactive": [
              "provider_account_id": NSNull(),
              "model_id": "gpt-5.4-mini",
              "options": ["json_mode": true],
            ]
          ],
        ]
      )
    ])

    let response = HybridProviderPolicy.resolveSlotFromSettings("proactive", settings: settings)

    XCTAssertEqual(response?.resolution.ok, false)
    XCTAssertTrue(response?.resolution.reason.contains("no provider account") == true)
    XCTAssertEqual(response?.resolved?.modelID, "gpt-5.4-mini")
    XCTAssertNil(HybridProviderPolicy.providerConfig(from: response!))
  }

  func testVisionFallsBackToOCRWhenNoVisionSlotExists() throws {
    let settings = try makeSettings([
      (
        "provider_policy",
        [
          "version": 1,
          "provider_accounts": [
            [
              "id": "local-proactive",
              "kind": "openai_compatible",
              "base_url": "http://proactive.local/v1",
            ]
          ],
          "model_slots": [
            "proactive": [
              "provider_account_id": "local-proactive",
              "model_id": "gpt-5.4-mini",
              "options": ["json_mode": true],
            ]
          ],
        ]
      )
    ])

    XCTAssertNil(HybridVisionProvider.providerConfig(settings: settings))
  }

  private func decodeSettings(_ jsonArray: String) throws -> [LocalDaemonSetting] {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode([LocalDaemonSetting].self, from: Data(jsonArray.utf8))
  }

  private func makeSettings(_ rows: [(String, [String: Any])]) throws -> [LocalDaemonSetting] {
    let payloadRows = try rows.map { key, value in
      let valueJsonData = try JSONSerialization.data(withJSONObject: value)
      guard let valueJson = String(data: valueJsonData, encoding: .utf8) else {
        struct EncodeError: Error {}
        throw EncodeError()
      }
      return [
        "key": key,
        "value_json": valueJson,
        "updated_at": "2026-05-20T12:00:00Z",
      ]
    }
    let payload = try JSONSerialization.data(withJSONObject: payloadRows)
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode([LocalDaemonSetting].self, from: payload)
  }
}
