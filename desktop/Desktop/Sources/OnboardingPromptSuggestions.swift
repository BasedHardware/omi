import Foundation

@MainActor
enum PostOnboardingPromptSuggestions {
  private static let suggestionsKey = "postOnboardingPromptSuggestions"
  private static let showPopupKey = "showPostOnboardingPromptPopup"
  private static let dismissedKey = "dismissedPostOnboardingPromptSuggestions"

  static func save(_ suggestions: [String]) {
    let cleaned = Array(
      NSOrderedSet(
        array: suggestions
          .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
          .filter { !$0.isEmpty }
      ).array as? [String] ?? suggestions
    )

    UserDefaults.standard.set(cleaned, forKey: suggestionsKey)
    UserDefaults.standard.set(true, forKey: showPopupKey)
    UserDefaults.standard.set(false, forKey: dismissedKey)
  }

  static func suggestions() -> [String] {
    UserDefaults.standard.stringArray(forKey: suggestionsKey) ?? []
  }

  static var shouldShowPopup: Bool {
    get { UserDefaults.standard.bool(forKey: showPopupKey) }
    set { UserDefaults.standard.set(newValue, forKey: showPopupKey) }
  }

  static var isDismissed: Bool {
    get { UserDefaults.standard.bool(forKey: dismissedKey) }
    set { UserDefaults.standard.set(newValue, forKey: dismissedKey) }
  }
}

// MARK: - Capability contract
//
// These suggestions are designed for the **piMono** bridge mode — the
// default chat backed by Omi's 7 tools (per ChatPrompts.agenticQA:
// execute_sql on memories/action_items/goals/screenshots,
// semantic_search on screen history, search_tasks, get_daily_recap,
// complete_task / delete_task, save_knowledge_graph).
//
// Every string in `allKnownSuggestions` MUST be answerable using one of
// those tools. Adding a suggestion that requires file/code/shell access
// (Bash, Read, Write, terminal, github, etc.) is a capability mismatch
// — the chat will return an empty result and the user blames the app.
// `ChatDiscoverabilityTests.testOnboardingPromptsContainNoUnsupportedCapabilities`
// scans this vocabulary for blocked keywords and fails CI if a future
// edit reaches for capabilities piMono doesn't have.
//
// userClaude bridge mode (opt-in, ACP via Claude Code) has Read/Write/Bash
// but no access to Omi memories or tasks — so these suggestions don't
// apply there either. A mode-aware suggestion set is a possible future
// enhancement, out of scope here.
@MainActor
enum OnboardingPromptSuggestionBuilder {
  /// Universal opener — always first, always relevant. Answerable via
  /// execute_sql on the goals + action_items tables.
  static let universalSuggestion = "What should I focus on today to achieve my goals?"

  /// Every string `build(from:)` can ever emit, in the order they could
  /// appear in the returned array. Tests scan this for capability drift.
  /// Keep at ≤6 entries — `build()` truncates with `.prefix(6)`.
  static let allKnownSuggestions: [String] = [
    universalSuggestion,
    "What email follow-ups matter most today?",
    "Where can I find focus time this week?",
    "Break my goal into the next 3 steps.",
    "What on my screen matters most right now?",
    "What's the highest-leverage thing I can do next?",
  ]

  static func build(from coordinator: OnboardingPagedIntroCoordinator) -> [String] {
    var suggestions: [String] = []

    // Universal first question — always relevant, not tied to a random project
    suggestions.append(universalSuggestion)

    if !coordinator.emailSummary.isEmpty {
      suggestions.append(allKnownSuggestions[1])
    }

    if !coordinator.calendarSummary.isEmpty {
      suggestions.append(allKnownSuggestions[2])
    }

    if !coordinator.goalDraft.isEmpty {
      suggestions.append(allKnownSuggestions[3])
    }

    suggestions.append(allKnownSuggestions[4])
    suggestions.append(allKnownSuggestions[5])

    let deduped = Array(NSOrderedSet(array: suggestions).array as? [String] ?? suggestions)
    return Array(deduped.prefix(6))
  }
}
