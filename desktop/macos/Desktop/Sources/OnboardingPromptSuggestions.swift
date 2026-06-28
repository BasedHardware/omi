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

@MainActor
enum OnboardingPromptSuggestionBuilder {
  static func build(from coordinator: OnboardingPagedIntroCoordinator) -> [String] {
    var suggestions: [String] = []

    // Universal first question — always relevant, not tied to a random project
    suggestions.append("What should I focus on today to achieve my goals?")

    if !coordinator.emailSummary.isEmpty {
      suggestions.append("What email follow-ups matter most today?")
    }

    if !coordinator.calendarSummary.isEmpty {
      suggestions.append("Where can I find focus time this week?")
    }

    if !coordinator.goalDraft.isEmpty {
      suggestions.append("Break my goal into the next 3 steps.")
    }

    suggestions.append("What on my screen matters most right now?")
    suggestions.append("What's the highest-leverage thing I can do next?")

    let deduped = Array(NSOrderedSet(array: suggestions).array as? [String] ?? suggestions)
    return Array(deduped.prefix(6))
  }
}
