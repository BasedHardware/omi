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
  // Each suggestion is a named constant so `build(from:)` references it
  // by meaning, not by array position. This avoids two failure modes:
  // a hardcoded index crashing if the vocabulary shrinks, and a reorder
  // silently attaching the wrong suggestion to a coordinator condition.

  /// Universal opener — always first, always relevant. Answerable via
  /// execute_sql on the goals + action_items tables.
  static let universalSuggestion = "What should I focus on today to achieve my goals?"
  /// Shown when the onboarding email summary is present.
  static let emailSuggestion = "What email follow-ups matter most today?"
  /// Shown when the onboarding calendar summary is present.
  static let calendarSuggestion = "Where can I find focus time this week?"
  /// Shown when the user drafted a goal during onboarding.
  static let goalSuggestion = "Break my goal into the next 3 steps."
  /// Always shown — backed by semantic_search over screen history.
  static let screenSuggestion = "What on my screen matters most right now?"
  /// Always shown — the catch-all prioritisation prompt.
  static let leverageSuggestion = "What's the highest-leverage thing I can do next?"

  /// Every string `build(from:)` can ever emit, in declaration order.
  /// Derived from the named constants above so the scanned vocabulary
  /// and what `build()` emits can't drift apart. Tests scan this for
  /// capability drift; `build()` truncates the assembled list with
  /// `.prefix(6)`.
  static let allKnownSuggestions: [String] = [
    universalSuggestion,
    emailSuggestion,
    calendarSuggestion,
    goalSuggestion,
    screenSuggestion,
    leverageSuggestion,
  ]

  static func build(from coordinator: OnboardingPagedIntroCoordinator) -> [String] {
    var suggestions: [String] = []

    // Universal first question — always relevant, not tied to a random project
    suggestions.append(universalSuggestion)

    if !coordinator.emailSummary.isEmpty {
      suggestions.append(emailSuggestion)
    }

    if !coordinator.calendarSummary.isEmpty {
      suggestions.append(calendarSuggestion)
    }

    if !coordinator.goalDraft.isEmpty {
      suggestions.append(goalSuggestion)
    }

    suggestions.append(screenSuggestion)
    suggestions.append(leverageSuggestion)

    let deduped = Array(NSOrderedSet(array: suggestions).array as? [String] ?? suggestions)
    return Array(deduped.prefix(6))
  }
}
