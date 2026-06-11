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

    // MARK: - Claude models are tier-dependent

    func testClaudePremiumModels() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.chatLabQuery, "claude-sonnet-4-20250514")
        XCTAssertEqual(ModelQoS.Claude.chatLabGrade, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.defaultSelection, "claude-haiku-4-5-20251001")
    }

    func testClaudeMaxModels() {
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.floatingBar, "claude-sonnet-4-6")
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.chatLabQuery, "claude-sonnet-4-20250514")
        XCTAssertEqual(ModelQoS.Claude.chatLabGrade, "claude-haiku-4-5-20251001")
        XCTAssertEqual(ModelQoS.Claude.defaultSelection, "claude-sonnet-4-6")
    }

    // MARK: - Synthesis uses Haiku (extraction workloads)

    func testSynthesisUsesHaiku() {
        XCTAssertEqual(ModelQoS.Claude.synthesis, "claude-haiku-4-5-20251001")
    }

    // MARK: - Chat uses Sonnet under max tier

    func testChatUsesSonnet() {
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.chat, "claude-sonnet-4-6")
    }

    // MARK: - Available models (Haiku in premium, Sonnet in max)

    func testAvailableModels() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.availableModels.map(\.id), ["claude-haiku-4-5-20251001"])

        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.availableModels.map(\.id), ["claude-sonnet-4-6"])
    }

    // MARK: - Gemini models are tier-dependent (except embedding)

    func testGeminiPremiumUsesFlash() {
        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Gemini.proactive, "gemini-2.5-flash")
        XCTAssertEqual(ModelQoS.Gemini.taskExtraction, "gemini-2.5-flash")
        XCTAssertEqual(ModelQoS.Gemini.insight, "gemini-2.5-flash")
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
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-sonnet-4-6"), "claude-sonnet-4-6")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-haiku-4-5-20251001"), "claude-haiku-4-5-20251001")
    }

    func testSanitizedSelectionFallsBackForUnknownModel() {
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-sonnet-4-6")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("claude-opus-4-6"), "claude-haiku-4-5-20251001")
    }

    func testSanitizedSelectionHandlesNil() {
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection(nil), "claude-sonnet-4-6")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection(nil), "claude-haiku-4-5-20251001")
    }

    func testSanitizedSelectionHandlesUnknownModel() {
        ModelQoS.activeTier = .max
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("gpt-4o"), "claude-sonnet-4-6")

        ModelQoS.activeTier = .premium
        XCTAssertEqual(ModelQoS.Claude.sanitizedSelection("gpt-4o"), "claude-haiku-4-5-20251001")
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
                ModelQoS.Claude.synthesis,
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
