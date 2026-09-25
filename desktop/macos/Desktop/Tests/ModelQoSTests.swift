import XCTest

@testable import Omi_Computer

final class ModelQoSTests: XCTestCase {
  private let tierKey = "modelQoS_activeTier"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: tierKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: tierKey)
    super.tearDown()
  }

  // MARK: - Default tier

  func testDefaultTierIsPremium() {
    XCTAssertEqual(ModelQoS.activeTier, .premium)
  }

  // MARK: - Tier persistence

  func testSetTierPersistsToUserDefaults() {
    ModelQoS.activeTier = .max
    XCTAssertEqual(UserDefaults.standard.string(forKey: tierKey), "max")

    ModelQoS.activeTier = .premium
    XCTAssertEqual(UserDefaults.standard.string(forKey: tierKey), "premium")
  }

  func testInvalidUserDefaultsFallsBackToPremium() {
    UserDefaults.standard.set("invalid_tier", forKey: tierKey)
    XCTAssertEqual(ModelQoS.activeTier, .premium)
  }

  // MARK: - Claude models are tier-independent

  func testClaudeModelsIdenticalAcrossTiers() {
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
      XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-sonnet-4-6")
      XCTAssertEqual(ModelQoS.Claude.chatLabQuery, "claude-sonnet-4-20250514")
      XCTAssertEqual(ModelQoS.Claude.chatLabGrade, "claude-haiku-4-5-20251001")
      XCTAssertEqual(ModelQoS.Claude.defaultSelection, "claude-sonnet-4-6")
    }
  }

  // MARK: - Chat uses Sonnet (user-facing)

  func testChatUsesSonnet() {
    XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
  }

  // MARK: - Available models (Sonnet only, both tiers)

  func testAvailableModelsSonnetOnlyBothTiers() {
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      let ids = ModelQoS.Claude.availableModels.map(\.id)
      XCTAssertEqual(ids, ["claude-sonnet-4-6"])
    }
  }

  // MARK: - Gemini models are tier-dependent (except embedding)

  func testGeminiPremiumUsesFlash() {
    ModelQoS.activeTier = .premium
    XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-2.5-flash")
    XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-2.5-flash")
  }

  /// Insight is Pro on every tier by design — the timer caps it at ~6 analyses/hour, and it is
  /// the best-performing high-volume notification lane (PostHog 30d to 2026-08-17: 1.162% CTR
  /// vs 0.68% fleet average).
  func testInsightIsProOnEveryTier() {
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-2.5-pro")
    }
  }

  /// The PT-eviction pin. Lanes routed through `lightweight` must stay off `gemini-2.5-flash`:
  /// that model burns the saturated Vertex PT reservation, which is reserved for task
  /// extraction (2026-08-17 vertex-pt-flash-spend evidence). Tier-independent on purpose.
  func testLightweightPinIsFlashLiteOnEveryTier() {
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      XCTAssertEqual(ModelQoS.Gemini.lightweight, "gemini-2.5-flash-lite")
    }
  }

  func testGeminiMaxUsesPro() {
    ModelQoS.activeTier = .max
    XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-2.5-pro")
    XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-2.5-pro")
    XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-2.5-pro")
  }

  func testGeminiEmbeddingTierIndependent() {
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      XCTAssertEqual(ModelQoS.Gemini.embedding, "gemini-embedding-001")
    }
  }

  // MARK: - Tier description

  func testTierDescription() {
    ModelQoS.activeTier = .premium
    XCTAssertEqual(ModelQoS.tierDescription, "Premium (cost-optimized)")

    ModelQoS.activeTier = .max
    XCTAssertEqual(ModelQoS.tierDescription, "Max (quality-optimized)")
  }

  // MARK: - Sanitized selection

  func testSanitizedSelectionAllowsValidModel() {
    XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-sonnet-4-6"), "claude-sonnet-4-6")
  }

  func testSanitizedSelectionFallsBackForUnknownModel() {
    XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-sonnet-4-6")
  }

  func testSanitizedSelectionHandlesNil() {
    XCTAssertEqual(ModelQoS.Claude.sanitizedSelection(nil), "claude-sonnet-4-6")
  }

  func testSanitizedSelectionHandlesUnknownModel() {
    XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("gpt-4o"), "claude-sonnet-4-6")
  }

  // MARK: - Tier change notification

  func testTierChangePostsNotification() {
    let expectation = expectation(forNotification: .modelTierDidChange, object: nil)
    ModelQoS.activeTier = .max
    wait(for: [expectation], timeout: 1.0)
  }

  // MARK: - Model count (6 unique model IDs across both tiers)

  func testSixUniqueModelIDs() {
    // Premium: flash for Gemini → 5 unique
    // Max: pro for Gemini → 5 unique
    // Combined across tiers: 6 unique (flash, pro, embedding + 3 Claude)
    var allModels: Set<String> = []
    for tier in ModelTier.allCases {
      ModelQoS.activeTier = tier
      allModels.formUnion([
        ModelQoS.Claude.chat,
        ModelQoS.Claude.floatingBar,
        ModelQoS.Claude.chatLabQuery,
        ModelQoS.Claude.chatLabGrade,
        ModelQoS.Claude.defaultSelection,
        ModelQoS.Gemini.proactive,
        ModelQoS.Gemini.taskExtraction,
        ModelQoS.Gemini.insight,
        ModelQoS.Gemini.embedding,
      ])
    }
    XCTAssertEqual(allModels.count, 6, "Expected 6 unique model IDs across tiers: \(allModels)")
  }
}
