import Foundation

@MainActor
enum PostOnboardingPromptSuggestions {
  private static let suggestionsKey = "postOnboardingPromptSuggestions"
  private static let showPopupKey = "showPostOnboardingPromptPopup"
  private static let dismissedKey = "dismissedPostOnboardingPromptSuggestions"

  static func save(_ suggestions: [String]) {
    let cleaned = Array(
      NSOrderedSet(
        array:
          suggestions
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

  /// Whether the shell should raise the "try asking" popup on this launch.
  ///
  /// **Arming belongs here, not to whichever page happens to be on screen.** This surface has now
  /// been stranded at both ends in turn. First the producer: `save(_:)` was reachable only from the
  /// retired paged-intro onboarding, so the array stayed empty. That was fixed — and the guidance
  /// still did not appear, because the only thing that armed the popup was `DashboardPage.onAppear`,
  /// and `DashboardPage` had stopped being Home. Onboarding wrote the suggestions, set the flag, and
  /// nothing read either one.
  ///
  /// Both halves failed the same way: the condition lived inside a `body` that a redesign could stop
  /// mounting. As a value it is something a test can hold and a moved page cannot silently take with
  /// it.
  static func shouldArmPopup() -> Bool {
    shouldShowPopup && !isDismissed && !suggestions().isEmpty
  }

  /// Consume the one-shot post-onboarding guidance regardless of which shell handled it.
  ///
  /// The main-chat opener and the legacy floating popup read the same saved suggestions. Keeping
  /// separate dismissal writes let either surface remain armed after the user had already acted on
  /// the other one, so chat-first users could see (and submit) the same prompt through both chats.
  static func consume() {
    shouldShowPopup = false
    isDismissed = true
  }
}

@MainActor
enum OnboardingPromptSuggestionBuilder {
  static func build(from coordinator: OnboardingPagedIntroCoordinator) -> [String] {
    var suggestions: [String] = []

    // Universal first question — always relevant, not tied to a random project
    suggestions.append(HomeSuggestionComposer.universalFirstQuestion)

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
