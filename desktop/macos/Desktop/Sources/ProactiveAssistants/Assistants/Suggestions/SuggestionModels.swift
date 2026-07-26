import Foundation

// MARK: - Suggestion Category

enum SuggestionCategory: String, Codable {
  case commitment
  case mistake
  case opportunity
  case connection
  case other
}

// MARK: - Grounding Bundle

/// What Omi already knows, assembled before judgment so the model can produce a
/// suggestion carrying information the user does not already have on screen.
///
/// Every field is optional and best-effort: grounding must never delay a card past the
/// moment it is relevant, so a source that is slow or empty simply contributes nothing.
struct SuggestionGrounding: Sendable {
  var memories: [String] = []
  var openCommitments: [String] = []
  var relatedScreens: [String] = []

  var isEmpty: Bool {
    memories.isEmpty && openCommitments.isEmpty && relatedScreens.isEmpty
  }

  /// Render for the prompt. Sections are omitted entirely when empty so the model is
  /// never handed an encouraging-looking but vacuous heading.
  func promptSections() -> String {
    var sections: [String] = []
    if !memories.isEmpty {
      sections.append("== WHAT OMI KNOWS ABOUT THE USER ==\n" + memories.joined(separator: "\n"))
    }
    if !openCommitments.isEmpty {
      sections.append("== OPEN COMMITMENTS ==\n" + openCommitments.joined(separator: "\n"))
    }
    if !relatedScreens.isEmpty {
      sections.append("== RELATED THINGS THE USER SAW RECENTLY ==\n" + relatedScreens.joined(separator: "\n"))
    }
    return sections.joined(separator: "\n\n")
  }
}

// MARK: - Extracted Suggestion

struct ExtractedSuggestion: Codable, Sendable {
  let suggestion: String
  let reasoning: String?
  let category: SuggestionCategory
  let confidence: Double

  enum CodingKeys: String, CodingKey {
    case suggestion
    case reasoning
    case category
    case confidence
  }

  func toDictionary() -> [String: Any] {
    var dict: [String: Any] = [
      "suggestion": suggestion,
      "category": category.rawValue,
      "confidence": confidence,
    ]
    if let reasoning = reasoning {
      dict["reasoning"] = reasoning
    }
    return dict
  }
}

// MARK: - Suggestion Result

struct SuggestionResult: Codable, AssistantResult, Sendable {
  let hasSuggestion: Bool
  let suggestion: ExtractedSuggestion?
  let contextSummary: String
  let currentActivity: String

  enum CodingKeys: String, CodingKey {
    case hasSuggestion = "has_suggestion"
    case suggestion
    case contextSummary = "context_summary"
    case currentActivity = "current_activity"
  }

  func toDictionary() -> [String: Any] {
    var dict: [String: Any] = [
      "hasSuggestion": hasSuggestion,
      "contextSummary": contextSummary,
      "currentActivity": currentActivity,
    ]
    if let suggestion = suggestion {
      dict["suggestion"] = suggestion.toDictionary()
    }
    return dict
  }
}

// MARK: - Evaluation Gate

/// Why an evaluation was or was not attempted. Returned by the pure gate so the decision
/// is testable without a model call, a timer, or a live screen.
enum SuggestionGateDecision: Equatable, Sendable {
  case evaluate
  case skippedDisabled
  case skippedExcludedApp
  case skippedCooldown
  case skippedSnoozed

  var allowsEvaluation: Bool { self == .evaluate }
}

/// Pure, synchronous gating policy. Every branch here is mechanical — no semantics, no
/// model, no I/O — so the cost contract ("no context switch, no Gemini call") is provable
/// in a unit test.
enum SuggestionGatePolicy {
  static func decide(
    isEnabled: Bool,
    isAppExcluded: Bool,
    isSnoozed: Bool,
    now: Date,
    lastEvaluationAt: Date?,
    cooldown: TimeInterval
  ) -> SuggestionGateDecision {
    guard isEnabled else { return .skippedDisabled }
    guard !isAppExcluded else { return .skippedExcludedApp }
    guard !isSnoozed else { return .skippedSnoozed }
    if let lastEvaluationAt, now.timeIntervalSince(lastEvaluationAt) < cooldown {
      return .skippedCooldown
    }
    return .evaluate
  }
}

// MARK: - Search Term Sanitization

/// Window titles become search terms, and they routinely contain characters FTS5 treats as
/// syntax — parentheses, quotes, colons, hyphens. `RewindDatabase.search` passes the query
/// through to FTS5 without sanitizing it (unlike `ActionItemStorage.searchFTS`, which
/// strips its own), so an unsanitized title like `Start Page (Private Browsing)` raises
/// `fts5: syntax error near "("` and the whole grounding source silently drops out.
enum SuggestionSearchTerm {
  /// Reduce arbitrary window-title text to bare alphanumeric tokens joined by spaces.
  /// Safe for FTS5 MATCH and for the `LIKE` path used by memory search.
  static func sanitize(_ raw: String) -> String {
    let mapped = raw.map { character -> Character in
      character.isLetter || character.isNumber ? character : " "
    }
    return String(mapped)
      .split(separator: " ")
      .map(String.init)
      .joined(separator: " ")
  }
}

// MARK: - Duplicate Suppression

/// Suppresses repeats of recent suggestions. Comparison is token-overlap based rather
/// than exact-string, because the model rephrases the same idea across context switches.
enum SuggestionDeduplication {
  /// Jaccard overlap at or above this is treated as the same suggestion.
  static let similarityThreshold = 0.6

  static func normalize(_ text: String) -> Set<String> {
    let lowered = text.lowercased()
    let stripped = lowered.map { $0.isLetter || $0.isNumber || $0 == " " ? $0 : " " }
    return Set(
      String(stripped)
        .split(separator: " ")
        .map(String.init)
        .filter { $0.count > 2 }
    )
  }

  static func similarity(_ lhs: String, _ rhs: String) -> Double {
    let a = normalize(lhs)
    let b = normalize(rhs)
    guard !a.isEmpty, !b.isEmpty else { return 0 }
    let intersection = a.intersection(b).count
    let union = a.union(b).count
    guard union > 0 else { return 0 }
    return Double(intersection) / Double(union)
  }

  static func isDuplicate(_ candidate: String, of recent: [String]) -> Bool {
    recent.contains { similarity(candidate, $0) >= similarityThreshold }
  }
}
