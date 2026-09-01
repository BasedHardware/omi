import Foundation

extension Notification.Name {
  static let omiFloatingBarCardAction = Notification.Name("omi.floatingBar.cardAction")
  static let omiOnboardingScenarioCompleted = Notification.Name("omi.onboarding.scenarioCompleted")
}

enum OnboardingScenarioDefaults {
  static let journalKey = "sbOnboardingScenarioJournal"
  static let pageAOpenedKey = "sbOnboardingScenarioPageAOpened"
  static let firstRunPendingKey = "omiFirstRunPending"
}

struct OnboardingScenarioJournalEntry: Codable, Equatable {
  let t: String
  let who: String
  let text: String
}

struct OnboardingScenarioJournal {
  static let maximumEntries = 200

  let defaults: UserDefaults
  let now: () -> Date

  init(defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
    self.defaults = defaults
    self.now = now
  }

  func entries() -> [OnboardingScenarioJournalEntry] {
    guard let data = defaults.data(forKey: OnboardingScenarioDefaults.journalKey) else { return [] }
    return (try? JSONDecoder().decode([OnboardingScenarioJournalEntry].self, from: data)) ?? []
  }

  func append(who: String, text: String) {
    var current = entries()
    current.append(
      OnboardingScenarioJournalEntry(
        t: ISO8601DateFormatter().string(from: now()),
        who: who,
        text: text
      ))
    if current.count > Self.maximumEntries {
      current.removeFirst(current.count - Self.maximumEntries)
    }
    guard let data = try? JSONEncoder().encode(current) else { return }
    defaults.set(data, forKey: OnboardingScenarioDefaults.journalKey)
  }
}

enum FloatingBarCardActionDispatcher {
  enum Selection {
    case primary
    case secondary
  }

  static func dispatch(
    descriptor: FloatingBarNotificationAction.ScenarioDescriptor,
    selection: Selection,
    center: NotificationCenter = .default,
    dismiss: () -> Void
  ) {
    let action: String
    switch (descriptor.kind, selection) {
    case ("onboarding_remind_me", .primary): action = "onboarding_remind_me"
    case ("onboarding_remind_me", .secondary): action = "onboarding_not_now"
    case ("first_run_focus_return", .primary): action = "first_run_focus_return"
    case ("first_run_focus_return", .secondary): action = "first_run_focus_snooze"
    case ("context_reminder", .primary): action = "context_reminder_done"
    case ("context_reminder", .secondary): action = "context_reminder_snooze"
    case ("first_run_open_summary", .primary): action = "first_run_open_summary"
    default: return
    }
    dispatch(action: action, id: descriptor.id, center: center, dismiss: dismiss)
  }

  static func dispatch(
    action: String,
    id: String = "",
    center: NotificationCenter = .default,
    dismiss: () -> Void
  ) {
    center.post(
      name: .omiFloatingBarCardAction,
      object: nil,
      userInfo: ["action": action, "id": id]
    )
    dismiss()
  }
}

enum OnboardingScenarioTitleTransport {
  static let orderToken = "Omi Welcome · Order confirmed"
  static let sentToken = "Omi Welcome · Sent"

  static func matches(_ title: String?, token: String) -> Bool {
    title?.localizedStandardContains(token) == true
  }

  static func note(from title: String) -> String? {
    guard matches(title, token: sentToken), let separator = title.range(of: " · ", options: .backwards) else {
      return nil
    }
    let encoded = String(title[separator.upperBound...])
    return encoded.removingPercentEncoding
  }
}

enum OnboardingScenarioDetectionResult: Equatable {
  case matched(title: String)
  case timedFallback
  case timedOut

  var analyticsValue: String {
    switch self {
    case .matched: "title_match"
    case .timedFallback: "timed_fallback"
    case .timedOut: "timeout"
    }
  }
}

@MainActor
enum OnboardingScenarioDetector {
  /// Deterministic polling seam. Production injects a 500 ms sleeper; tests advance an injected poller.
  static func waitForTitle(
    token: String,
    maximumPolls: Int,
    useTimedFallback: Bool,
    undetectableAfterPolls: Int? = nil,
    poll: () async -> String?,
    wait: () async -> Void
  ) async -> OnboardingScenarioDetectionResult {
    var nilPolls = 0
    for index in 0..<max(1, maximumPolls) {
      if let title = await poll() {
        nilPolls = 0
        if OnboardingScenarioTitleTransport.matches(title, token: token) {
          return .matched(title: title)
        }
      } else {
        nilPolls += 1
        if let undetectableAfterPolls, nilPolls >= undetectableAfterPolls {
          return .timedFallback
        }
      }
      if index + 1 < maximumPolls { await wait() }
    }
    return useTimedFallback ? .timedFallback : .timedOut
  }
}

struct OnboardingScenarioNoteEffects: Equatable {
  let memories: [String]
  let taskTitle: String?
  let personMemory: String?

  static let none = OnboardingScenarioNoteEffects(memories: [], taskTitle: nil, personMemory: nil)
}

enum OnboardingScenarioNotePlanner {
  static let taskTitle = "Send Sam the lamp link"
  static let personMemory = "Sam Ortega is considering the Aurora desk lamp before the sale ends"

  static func effects(note: String, prefilledNote: String) -> OnboardingScenarioNoteEffects {
    let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .none }
    let memory = "Note to Sam: \(note)"
    guard note == prefilledNote else {
      return OnboardingScenarioNoteEffects(memories: [memory], taskTitle: nil, personMemory: nil)
    }
    return OnboardingScenarioNoteEffects(
      memories: [memory, personMemory],
      taskTitle: taskTitle,
      personMemory: personMemory
    )
  }
}
