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

    func testDefaultTierIsStandard() {
        XCTAssertEqual(ModelQoS.activeTier, .standard)
    }

    // MARK: - Tier persistence

    func testSetTierPersistsToUserDefaults() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(UserDefaults.standard.string(forKey: tierKey), "premium")

        ModelQoS.activeTier = .standard
        XCTAssertEqual(UserDefaults.standard.string(forKey: tierKey), "standard")
    }

    func testInvalidUserDefaultsFallsBackToStandard() {
        UserDefaults.standard.set("invalid_tier", forKey: tierKey)
        XCTAssertEqual(ModelQoS.activeTier, .standard)
    }

    // MARK: - Claude models: standard tier

    func testClaudeModelsStandardTier() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-sonnet-4-6")
    }

    // MARK: - Claude models: premium tier

    func testClaudeModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-opus-4-6")
        XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-opus-4-6")
    }

    // MARK: - Claude pinned models (tier-independent)

    func testClaudePinnedModelsIgnoreTier() {
        for tier in ModelTier.allCases {
            ModelQoS.activeTier = tier
            XCTAssertEqual(ModelQoS.Claude.chatLabQuery, "claude-sonnet-4-20250514")
            XCTAssertEqual(ModelQoS.Claude.chatLabGrade, "claude-haiku-4-5-20251001")
            XCTAssertEqual(ModelQoS.Claude.defaultSelection, "claude-sonnet-4-6")
        }
    }

    // MARK: - Available models reflect tier

    func testAvailableModelsStandardTier() {
        ModelQoS.activeTier = .standard
        let ids = ModelQoS.Claude.availableModels.map(\.id)
        XCTAssertEqual(ids, ["claude-sonnet-4-6"])
    }

    func testAvailableModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        let ids = ModelQoS.Claude.availableModels.map(\.id)
        XCTAssertEqual(ids, ["claude-sonnet-4-6", "claude-opus-4-6"])
    }

    // MARK: - Gemini models: standard tier

    func testGeminiModelsStandardTier() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-3-flash-preview")
        XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-3-flash-preview")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")
    }

    // MARK: - Gemini models: premium tier

    func testGeminiModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-3-flash-preview")
        XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-pro-latest")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-pro-latest")
    }

    // MARK: - Gemini pinned models (tier-independent)

    func testGeminiEmbeddingIgnoresTier() {
        for tier in ModelTier.allCases {
            ModelQoS.activeTier = tier
            XCTAssertEqual(ModelQoS.Gemini.embedding, "gemini-embedding-001")
        }
    }

    // MARK: - Tier description

    func testTierDescription() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.tierDescription, "Standard (cost-optimized)")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.tierDescription, "Premium (quality-optimized)")
    }

    // MARK: - Tier switch dynamically changes accessors

    func testTierSwitchChangesModelsAtRuntime() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-opus-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-pro-latest")

        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")
    }

    // MARK: - Sanitized selection (stale model regression)

    func testSanitizedSelectionAllowsValidModel() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-sonnet-4-6"), "claude-sonnet-4-6")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-opus-4-6")
    }

    func testSanitizedSelectionFallsBackForStaleModel() {
        // User previously selected Opus while on premium tier
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-opus-4-6")

        // Tier drops to standard — Opus is no longer available
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-sonnet-4-6")
    }

    func testSanitizedSelectionHandlesNil() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection(nil), "claude-sonnet-4-6")
    }

    func testSanitizedSelectionHandlesUnknownModel() {
        ModelQoS.activeTier = .standard
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("gpt-4o"), "claude-sonnet-4-6")
    }
}
