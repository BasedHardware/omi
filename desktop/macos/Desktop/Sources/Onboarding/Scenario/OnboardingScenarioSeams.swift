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

  /// Browser bundle families accepted for the local title transport. This follows the shared
  /// conferencing browser list and keeps the fallback explicit for browsers not yet catalogued.
  static func isBrowserBundleID(_ bundleID: String?) -> Bool {
    guard let lower = bundleID?.lowercased(), !lower.isEmpty else { return false }
    return ConferencingApps.isBrowserBundleID(lower)
      || ["browser", "safari", "chrome", "firefox", "arc", "edge", "brave", "orion", "vivaldi", "opera"]
        .contains(where: lower.contains)
  }

  static func note(from title: String, nonce: String) -> String? {
    let prefix = "\(sentToken) · \(nonce) · "
    guard title.hasPrefix(prefix), let decoded = String(title.dropFirst(prefix.count)).removingPercentEncoding else {
      return nil
    }
    let sanitized = decoded.unicodeScalars.filter { scalar in
      !CharacterSet.controlCharacters.contains(scalar)
    }
    let bounded = String(String.UnicodeScalarView(sanitized).prefix(1_500))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return bounded.isEmpty ? nil : bounded
  }
}

struct OnboardingScenarioWindowObservation: Equatable {
  let title: String?
  let bundleID: String?
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
    nonce: String? = nil,
    requireBrowser: Bool = false,
    maximumPolls: Int,
    useTimedFallback: Bool,
    undetectableAfterPolls: Int? = nil,
    poll: () async -> OnboardingScenarioWindowObservation,
    wait: () async -> Void
  ) async -> OnboardingScenarioDetectionResult {
    var nilPolls = 0
    for index in 0..<max(1, maximumPolls) {
      let observation = await poll()
      if let title = observation.title {
        nilPolls = 0
        let titleMatches: Bool
        if let nonce {
          titleMatches = OnboardingScenarioTitleTransport.note(from: title, nonce: nonce) != nil
        } else {
          titleMatches = OnboardingScenarioTitleTransport.matches(title, token: token)
        }
        if titleMatches,
          !requireBrowser || OnboardingScenarioTitleTransport.isBrowserBundleID(observation.bundleID)
        {
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

/// What Omi keeps from the note, decided without a model call.
///
/// The beat's lesson is "a promise becomes a task, what you tell Sam becomes a memory", and the user
/// is invited to edit the draft. Keying the effects on the draft being byte-identical taught the
/// lesson only to people who did not touch it. The promise is recognised by its subject (the link)
/// and the fact about Sam by its subject (the lamp, the sale), so a rewritten note still shows
/// both, and a note that drops the promise honestly shows no task.
enum OnboardingScenarioNotePlanner {
  static let taskTitle = "Send Sam the lamp link"
  static let personMemory = "Sam Ortega is considering the Aurora desk lamp before the sale ends"

  static func effects(note: String, prefilledNote: String) -> OnboardingScenarioNoteEffects {
    let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .none }
    let memory = "Note to Sam: \(note)"
    let lower = trimmed.lowercased()
    let keepsPromise = note == prefilledNote || lower.contains("link")
    let mentionsLamp = note == prefilledNote || lower.contains("lamp") || lower.contains("sale")
    return OnboardingScenarioNoteEffects(
      memories: mentionsLamp ? [memory, personMemory] : [memory],
      taskTitle: keepsPromise ? taskTitle : nil,
      personMemory: mentionsLamp ? personMemory : nil
    )
  }
}
