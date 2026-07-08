import Foundation

// MARK: - Model QoS Tier System
//
// Central model configuration with switchable tiers.
// Change `activeTier` to switch all models at once.
// Individual workloads can also override their tier.

enum ModelTier: String, CaseIterable {
    case premium    // Cost-optimized: Sonnet + Haiku for Claude, Flash for Gemini
    case max        // Quality-optimized: higher rate limits, same models
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
        /// Main chat session model (user-facing conversations)
        static var chat: String { "claude-sonnet-4-6" }

        /// Floating bar responses
        static var floatingBar: String { "claude-sonnet-4-6" }

        /// Synthesis extraction tasks (calendar, gmail, notes, memory import)
        static var synthesis: String { "claude-haiku-4-5-20251001" }

        /// ChatLab test queries
        static var chatLabQuery: String { "claude-sonnet-4-20250514" }

        /// ChatLab grading (always cheap)
        static var chatLabGrade: String { "claude-haiku-4-5-20251001" }

        /// Available models shown in the UI picker
        static var availableModels: [(id: String, label: String)] {
            [("claude-sonnet-4-6", "Sonnet")]
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
    }

    // MARK: - Gemini Models (tier-dependent, stable GA models)
    //
    // Provider routing (Vertex AI vs AI Studio) is handled by the Rust backend
    // based on model_qos::is_vertex_available(). The Swift app just picks the model.

    struct Gemini {
        /// Proactive assistants (screenshot analysis, context detection)
        static var proactive: String {
            switch activeTier {
            case .premium: return "gemini-2.5-flash"
            case .max:     return "gemini-2.5-pro"
            }
        }

        /// Task extraction
        static var taskExtraction: String {
            switch activeTier {
            case .premium: return "gemini-2.5-flash"
            case .max:     return "gemini-2.5-pro"
            }
        }

        /// Insight generation
        static var insight: String {
            switch activeTier {
            case .premium: return "gemini-2.5-flash"
            case .max:     return "gemini-2.5-pro"
            }
        }

        /// Embeddings (not tier-dependent, kept separate)
        static var embedding: String { "gemini-embedding-001" }
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
