import Foundation

// MARK: - Model QoS Tier System
//
// Central model configuration with switchable tiers.
// Change `activeTier` to switch all models at once.
// Individual workloads can also override their tier.

enum ModelTier: String, CaseIterable {
  case premium  // Cost-optimized: Sonnet + Haiku for Claude, Flash for Gemini
  case max  // Quality-optimized: higher rate limits, same models
}

struct ModelQoS {
  // MARK: - Active Tier (single switch)

  private static let tierKey = "modelQoS_activeTier"

  static var activeTier: ModelTier {
    get {
      guard let raw = UserDefaults.standard.string(forKey: tierKey),
        let tier = ModelTier(rawValue: raw)
      else {
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
    static var chat: String { modelIdFor(tier: activeTier.rawValue, workload: .claudeChat) }

    /// Floating bar responses
    static var floatingBar: String { modelIdFor(tier: activeTier.rawValue, workload: .claudeFloatingBar) }

    /// Synthesis extraction tasks (calendar, gmail, notes, memory import)
    static var synthesis: String { modelIdFor(tier: activeTier.rawValue, workload: .claudeSynthesis) }

    /// ChatLab test queries
    static var chatLabQuery: String { modelIdFor(tier: activeTier.rawValue, workload: .claudeChatLabQuery) }

    /// ChatLab grading (always cheap)
    static var chatLabGrade: String { modelIdFor(tier: activeTier.rawValue, workload: .claudeChatLabGrade) }

    /// Available models shown in the UI picker
    static var availableModels: [(id: String, label: String)] {
      [(defaultSelection, "Sonnet")]
    }

    /// Default model for user selection (floating bar / shortcut picker)
    static var defaultSelection: String {
      modelIdFor(tier: activeTier.rawValue, workload: .claudeDefaultSelection)
    }

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
      modelIdFor(tier: activeTier.rawValue, workload: .geminiProactive)
    }

    /// Task extraction
    static var taskExtraction: String {
      modelIdFor(tier: activeTier.rawValue, workload: .geminiTaskExtraction)
    }

    /// Insight generation
    static var insight: String {
      modelIdFor(tier: activeTier.rawValue, workload: .geminiInsight)
    }

    /// Embeddings (not tier-dependent, kept separate)
    static var embedding: String { modelIdFor(tier: activeTier.rawValue, workload: .geminiEmbedding) }
  }

  // MARK: - Tier Info (for UI / debugging)

  static var tierDescription: String {
    tierDescriptionFor(tier: activeTier.rawValue)
  }
}

extension Notification.Name {
  static let modelTierDidChange = Notification.Name("modelTierDidChange")
}
