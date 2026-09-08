import Foundation

/// Decides whether a delivered proactive notification is also spoken out loud, and what
/// exactly is said.
///
/// Off by default: a voice in a quiet room is a far bigger intrusion than a banner, so
/// speech only ever comes from an explicit opt-in (Advanced settings → Preferences).
/// Pure policy so the default-off contract and the spoken text are testable without a
/// speech synthesizer or a delivered banner.
enum NotificationSpeech {
  nonisolated static let enabledDefaultsKey = DefaultsKey.speakNotificationsAloud.rawValue

  static func isEnabled(defaults: UserDefaults = .standard) -> Bool {
    defaults.bool(forKey: enabledDefaultsKey)
  }

  /// What to say for a delivered notification, or nil to stay silent.
  ///
  /// Only proactive notifications speak (`isProactive` = the caller's `respectFrequency`
  /// marker): functional notices — the onboarding test banner, screen-recording repair
  /// prompts, support replies — are system chrome, not omi talking to you, and reading
  /// them aloud would be exactly the wrong voice for the feature.
  ///
  /// Only the message is spoken: the title is banner chrome ("Suggestion", "Insight")
  /// that would read as a spoken label prefix, not something a person would say.
  static func utterance(message: String, isEnabled: Bool, isProactive: Bool) -> String? {
    guard isEnabled, isProactive else { return nil }
    let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return trimmed
  }
}

/// Speaks a delivered notification at most once, at the moment a surface actually
/// presents it.
///
/// Presentation — not sending — is the right trigger: the default proactive path is
/// floating-bar only and never reaches the system banner, the bar can queue a
/// notification for later, and a muted-preview fallback can deliver both surfaces for
/// one message. All of those report through the same presentation callback, so speaking
/// there covers every surface, and the once-guard keeps a dual delivery from reading
/// the same message twice.
@MainActor
final class NotificationSpeechOnDelivery {
  private let text: String?
  private let speak: (String) -> Void
  private var hasSpoken = false

  init(
    text: String?,
    speak: @escaping (String) -> Void = { FloatingBarVoicePlaybackService.shared.speakOneShot($0) }
  ) {
    self.text = text
    self.speak = speak
  }

  convenience init(message: String, isProactive: Bool) {
    self.init(
      text: NotificationSpeech.utterance(
        message: message, isEnabled: NotificationSpeech.isEnabled(), isProactive: isProactive))
  }

  func notificationWasPresented() {
    guard let text, !hasSpoken else { return }
    hasSpoken = true
    log("NotificationSpeech: speaking delivered notification (\(text.count) chars)")
    speak(text)
  }
}
