import XCTest
@testable import Omi_Computer

final class ThinkingBudgetTests: XCTestCase {

  // MARK: - ThinkingConfig.minimumBudget(for:)

  func testFlashModelMinimumBudgetIsZero() {
    XCTAssertEqual(ThinkingConfig.minimumBudget(for: "gemini-2.5-flash"), 0)
  }

  func testFlashPreviewModelMinimumBudgetIsZero() {
    XCTAssertEqual(ThinkingConfig.minimumBudget(for: "gemini-2.5-flash-preview-04-17"), 0)
  }

  func testProModelMinimumBudgetIs128() {
    XCTAssertEqual(ThinkingConfig.minimumBudget(for: "gemini-2.5-pro"), 128)
  }

  func testProPreviewModelMinimumBudgetIs128() {
    XCTAssertEqual(ThinkingConfig.minimumBudget(for: "gemini-2.5-pro-preview-05-06"), 128)
  }

  func testUnknownModelDefaultsToZero() {
    XCTAssertEqual(ThinkingConfig.minimumBudget(for: "gemini-2.0-flash"), 0)
  }

  // MARK: - ThinkingConfig encoding

  func testThinkingConfigEncodesSnakeCase() throws {
    let config = ThinkingConfig(thinkingBudget: 1024)
    let data = try JSONEncoder().encode(config)
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    XCTAssertEqual(json["thinking_budget"] as? Int, 1024)
    XCTAssertNil(json["thinkingBudget"], "Should use snake_case key, not camelCase")
  }

  func testThinkingConfigEncodesZeroBudget() throws {
    let config = ThinkingConfig(thinkingBudget: 0)
    let data = try JSONEncoder().encode(config)
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    XCTAssertEqual(json["thinking_budget"] as? Int, 0)
  }

  // MARK: - Budget floor enforcement via max()

  func testFlashBudgetZeroPassesThroughAsZero() {
    let budget = max(0, ThinkingConfig.minimumBudget(for: "gemini-2.5-flash"))
    XCTAssertEqual(budget, 0)
  }

  func testProBudgetZeroFloorsTo128() {
    let budget = max(0, ThinkingConfig.minimumBudget(for: "gemini-2.5-pro"))
    XCTAssertEqual(budget, 128)
  }

  func testProBudget1024StaysAt1024() {
    let budget = max(1024, ThinkingConfig.minimumBudget(for: "gemini-2.5-pro"))
    XCTAssertEqual(budget, 1024)
  }

  func testFlashBudget1024StaysAt1024() {
    let budget = max(1024, ThinkingConfig.minimumBudget(for: "gemini-2.5-flash"))
    XCTAssertEqual(budget, 1024)
  }

  // MARK: - GeminiRequest includes thinkingConfig in generationConfig

  func testGeminiRequestEncodesThinkingConfig() throws {
    let request = GeminiRequest(
      contents: [GeminiRequest.Content(parts: [GeminiRequest.Part(text: "test")])],
      systemInstruction: nil,
      generationConfig: GeminiRequest.GenerationConfig(
        responseMimeType: "application/json",
        responseSchema: nil,
        thinkingConfig: ThinkingConfig(thinkingBudget: 0)
      )
    )
    let data = try JSONEncoder().encode(request)
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    let genConfig = json["generation_config"] as! [String: Any]
    let thinkingConfig = genConfig["thinking_config"] as! [String: Any]
    XCTAssertEqual(thinkingConfig["thinking_budget"] as? Int, 0)
  }

  // MARK: - GeminiImageToolRequest includes thinkingConfig

  func testImageToolRequestEncodesThinkingBudget() throws {
    let request = GeminiImageToolRequest(
      contents: [
        GeminiImageToolRequest.Content(role: "user", parts: [.init(text: "test")])
      ],
      systemInstruction: GeminiImageToolRequest.SystemInstruction(parts: [.init(text: "sys")]),
      generationConfig: GeminiImageToolRequest.GenerationConfig(
        thinkingConfig: ThinkingConfig(thinkingBudget: 1024)
      ),
      tools: [],
      toolConfig: nil
    )
    let data = try JSONEncoder().encode(request)
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    let genConfig = json["generation_config"] as! [String: Any]
    let thinkingConfig = genConfig["thinking_config"] as! [String: Any]
    XCTAssertEqual(thinkingConfig["thinking_budget"] as? Int, 1024)
  }
}
