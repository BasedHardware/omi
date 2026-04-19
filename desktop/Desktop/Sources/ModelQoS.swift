import Foundation

// MARK: - Model QoS Tier System
//
// Central model configuration with switchable tiers.
// Change `activeTier` to switch all models at once.
// Individual workloads can also override their tier.

enum ModelTier: String, CaseIterable {
    case premium    // Cost-optimized: Sonnet for Claude, Flash for Gemini
    case max        // Quality-optimized: Opus for Claude, Pro for Gemini
}

struct ModelQoS {
    // MARK: - Active Tier (single switch)

    private static let tierKey = "modelQoS_activeTier"

    static var activeTier: ModelTier {
        get {
            guard let raw = UserDefaults.standard.string(forKey: tierKey),
                  let tier = ModelTier(rawValue: raw) else {
                return .premium
            }
            return tier
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: tierKey)
            NotificationCenter.default.post(name: .modelTierDidChange, object: nil)
        }
    }

    // MARK: - Claude Models

    struct Claude {
        /// Main chat session model
        static var chat: String { model(premium: "claude-sonnet-4-6", max: "claude-opus-4-6") }

        /// Floating bar responses
        static var floatingBar: String { model(premium: "claude-sonnet-4-6", max: "claude-sonnet-4-6") }

        /// Synthesis tasks (calendar, gmail, notes, onboarding)
        static var synthesis: String { model(premium: "claude-sonnet-4-6", max: "claude-opus-4-6") }

        /// ChatLab test queries
        static var chatLabQuery: String { "claude-sonnet-4-20250514" }

        /// ChatLab grading (always cheap)
        static var chatLabGrade: String { "claude-haiku-4-5-20251001" }

        /// Available models shown in the UI picker
        static var availableModels: [(id: String, label: String)] {
            switch activeTier {
            case .premium:
                return [("claude-sonnet-4-6", "Sonnet")]
            case .max:
                return [
                    ("claude-sonnet-4-6", "Sonnet"),
                    ("claude-opus-4-6", "Opus"),
                ]
            }
        }

        /// Default model for user selection (floating bar / shortcut picker)
        static var defaultSelection: String { "claude-sonnet-4-6" }

        /// Sanitize a persisted model ID against the current tier's allowed list.
        /// Returns the saved model if it's still available, otherwise falls back to defaultSelection.
        static func sanitizedSelection(_ savedModel: String?) -> String {
            let model = savedModel ?? defaultSelection
            let allowedIDs = availableModels.map(\.id)
            return allowedIDs.contains(model) ? model : defaultSelection
        }

        private static func model(premium: String, max: String) -> String {
            activeTier == .premium ? premium : max
        }
    }

    // MARK: - Gemini Models

    struct Gemini {
        /// Proactive assistants (screenshot analysis, context detection)
        static var proactive: String { model(premium: "gemini-3-flash-preview", max: "gemini-3-flash-preview") }

        /// Task extraction
        static var taskExtraction: String { model(premium: "gemini-3-flash-preview", max: "gemini-pro-latest") }

        /// Insight generation
        static var insight: String { model(premium: "gemini-3-flash-preview", max: "gemini-pro-latest") }

        /// Embeddings (not tier-dependent, kept separate)
        static var embedding: String { "gemini-embedding-001" }

        private static func model(premium: String, max: String) -> String {
            activeTier == .premium ? premium : max
        }
    }

    // MARK: - Tier Info (for UI / debugging)

    static var tierDescription: String {
        switch activeTier {
        case .premium: return "Premium (cost-optimized)"
        case .max: return "Max (quality-optimized)"
        }
    }
}

extension Notification.Name {
    static let modelTierDidChange = Notification.Name("modelTierDidChange")
}
