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

    if let project = coordinator.scanSnapshot?.projectNames.first {
      suggestions.append("What should I focus on today to ship \(project) faster?")
    }

    if let technology = coordinator.scanSnapshot?.technologies.first {
      suggestions.append("Based on my recent work, what am I probably blocked on in \(technology)?")
    }

    if !coordinator.emailSummary.isEmpty {
      suggestions.append("Which follow-ups from my recent emails matter most today?")
    }

    if !coordinator.calendarSummary.isEmpty {
      suggestions.append("Where can I create more focus time in my calendar this week?")
    }

    if !coordinator.goalDraft.isEmpty {
      suggestions.append("Help me break \"\(coordinator.goalDraft)\" into the next 3 steps.")
    }

    if !coordinator.webResearchSummary.isEmpty || coordinator.scanSnapshot != nil {
      suggestions.append("What should I prioritize this week based on what you know about me?")
    }

    suggestions.append("What on my screen matters most right now?")
    suggestions.append("What is the highest-leverage thing I can do in the next 30 minutes?")

    let deduped = Array(NSOrderedSet(array: suggestions).array as? [String] ?? suggestions)
    return Array(deduped.prefix(6))
  }
}
