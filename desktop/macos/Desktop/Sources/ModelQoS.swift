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
    static var chat: String { "claude-sonnet-4-6" }

    /// Floating bar responses
    static var floatingBar: String { "claude-sonnet-4-6" }

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
      case .max: return "gemini-2.5-pro"
      }
    }

    /// Task extraction
    static var taskExtraction: String {
      switch activeTier {
      case .premium: return "gemini-2.5-flash"
      case .max: return "gemini-2.5-pro"
      }
    }

    /// Insight generation.
    ///
    /// Pro on both tiers, deliberately. A 10-minute timer caps it at ~6 analyses/hour no
    /// matter how much the user switches windows, so it is cheap to run well — and its whole
    /// job is finding the one non-obvious thing, which is exactly where the weaker model
    /// stops earning its interruption. Measured (PostHog, 30d to 2026-08-17, macOS): insight
    /// CTR 1.162% against a 0.68% fleet average — the best-performing high-volume lane.
    /// (An earlier revision cited "2.34% in the week of 2026-04-12, 39.8k sent, 336
    /// clickers"; that tuple reproduces from no PostHog slice and was removed.)
    /// After 30 Pro calls/user/day the backend proxy demotes this lane to Flash-Lite —
    /// never to Flash, which would burn the Vertex PT reservation.
    static var insight: String { "gemini-2.5-pro" }

    /// Low-value / schema-bounded lanes evicted from the Vertex PT Flash reservation
    /// (2026-08-17 workload value ranking + overflow bakeoff, omi-knowledge-base
    /// vertex-pt-flash-spend): memory extraction, LiveNotes, goals, task dedup,
    /// task prioritization, home suggestions. Flash-Lite is `shared`/on-demand on
    /// Vertex — it never competes with task extraction for the 13,450 tok/s PT cap —
    /// and measured ~0.27x Flash's cost. On the memory lane it is also *more*
    /// prompt-compliant than Flash (fires 5/12 vs Flash's 8/8 against a prompt that
    /// says most screens should return nothing). Task extraction must NOT use this
    /// pin: Flash-Lite measurably extracts from chat sidebars and drops second
    /// commitments on that lane.
    static var lightweight: String { "gemini-2.5-flash-lite" }

    /// Live notch suggestions.
    ///
    /// Deliberately a tier below the other proactive assistants. This one is triggered by
    /// ordinary context changes rather than a slow timer, so its call volume is an order of
    /// magnitude higher; the work — "does this screen plus what Omi already knows justify
    /// one short sentence?" — is well within Flash-Lite. Cost, not capability, sets this.
    static var suggestions: String {
      switch activeTier {
      case .premium: return "gemini-2.5-flash-lite"
      case .max: return "gemini-2.5-flash"
      }
    }

    /// Embeddings (not tier-dependent, kept separate)
    static var embedding: String { "gemini-embedding-001" }
  }

  struct Proactivity {
    static let extractionOperation = "proactive_extraction"
    static let reasoningOperation = "proactive_reasoning"
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
