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

    // MARK: - Claude models: premium tier

    func testClaudeModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-sonnet-4-6")
    }

    // MARK: - Claude models: max tier

    func testClaudeModelsMaxTier() {
        ModelQoS.activeTier = .max
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

    func testAvailableModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        let ids = ModelQoS.Claude.availableModels.map(\.id)
        XCTAssertEqual(ids, ["claude-sonnet-4-6"])
    }

    func testAvailableModelsMaxTier() {
        ModelQoS.activeTier = .max
        let ids = ModelQoS.Claude.availableModels.map(\.id)
        XCTAssertEqual(ids, ["claude-sonnet-4-6", "claude-opus-4-6"])
    }

    // MARK: - Gemini models: premium tier

    func testGeminiModelsPremiumTier() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-3-flash-preview")
        XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-3-flash-preview")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")
    }

    // MARK: - Gemini models: max tier

    func testGeminiModelsMaxTier() {
        ModelQoS.activeTier = .max
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
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.tierDescription, "Premium (cost-optimized)")

        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.tierDescription, "Max (quality-optimized)")
    }

    // MARK: - Tier switch dynamically changes accessors

    func testTierSwitchChangesModelsAtRuntime() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")

        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-opus-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-pro-latest")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-3-flash-preview")
    }

    // MARK: - Sanitized selection (stale model regression)

    func testSanitizedSelectionAllowsValidModel() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-sonnet-4-6"), "claude-sonnet-4-6")

        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-opus-4-6")
    }

    func testSanitizedSelectionFallsBackForStaleModel() {
        // User previously selected Opus while on max tier
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-opus-4-6")

        // Tier drops to premium — Opus is no longer available
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-sonnet-4-6")
    }

    func testSanitizedSelectionHandlesNil() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection(nil), "claude-sonnet-4-6")
    }

    func testSanitizedSelectionHandlesUnknownModel() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("gpt-4o"), "claude-sonnet-4-6")
    }

    // MARK: - Tier change notification

    func testTierChangePostsNotification() {
        let expectation = expectation(forNotification: .modelTierDidChange, object: nil)
        ModelQoS.activeTier = .max
        wait(for: [expectation], timeout: 1.0)
    }
}
