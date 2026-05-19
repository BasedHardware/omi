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

  func testHybridChatClientFallsBackToAiProvider() throws {
    let payload = """
    [{"key":"ai_provider","value_json":"{\\"kind\\":\\"openai_compatible\\",\\"base_url\\":\\"http://ai.local/v1\\",\\"model\\":\\"m-ai\\"}","updated_at":"2026-05-19T12:00:00Z"}]
    """
    let settings = try decodeSettings(payload)
    let config = HybridChatClient.resolveEffectiveChatConfig(from: settings)
    XCTAssertEqual(config?.baseURL, "http://ai.local/v1")
    XCTAssertEqual(config?.model, "m-ai")
  }

  private func decodeSettings(_ jsonArray: String) throws -> [LocalDaemonSetting] {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode([LocalDaemonSetting].self, from: Data(jsonArray.utf8))
  }
}
