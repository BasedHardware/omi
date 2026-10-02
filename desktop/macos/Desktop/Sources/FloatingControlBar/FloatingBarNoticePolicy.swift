import Foundation

/// How long a floating-bar notice stays up. One table for every card the notch presents, so a
/// new card picks a row here instead of inventing its own timer.
///
/// | Notice | Lifetime |
/// |---|---|
/// | Confirmation of something the user just did ("Sent", "Copied") | `OmiFeedbackTiming.confirmation` |
/// | Informational card the user did not ask for | `OmiFeedbackTiming.informational`, paused while hovered (Interject: reading time, 4–14 s, also paused) |
/// | Trial / billing card, error card, any card sent `isPersistent` | until acted on or dismissed |
enum FloatingBarNoticeLifetime: Equatable {
  /// Auto-dismisses after `seconds` of *unhovered* display: the countdown pauses while the
  /// pointer is over the bar.
  case timed(seconds: TimeInterval)
  /// Stays until the user acts on it, dismisses it, or presses Esc.
  case untilDismissed
}

enum FloatingBarNoticePolicy {
  /// A card the user just caused ("Sent to …", "Copied").
  static let confirmation: TimeInterval = OmiFeedbackTiming.confirmation

  /// Whether a card of this kind must wait for the user. Trial and plan cards carry a decision
  /// (upgrade, bring your own keys); a card that vanishes in six seconds is one the user never
  /// gets to act on.
  static func persists(kind: ProactiveNotificationKind, requestedPersistent: Bool) -> Bool {
    requestedPersistent || kind == .trial
  }

  /// The lifetime for a card about to be presented.
  static func lifetime(
    title: String,
    message: String,
    kind: ProactiveNotificationKind,
    isPersistent: Bool,
    interjectEnabled: Bool
  ) -> FloatingBarNoticeLifetime {
    guard !persists(kind: kind, requestedPersistent: isPersistent) else { return .untilDismissed }
    return .timed(
      seconds: InterjectDisplayDuration.timeout(
        title: title, message: message, kind: kind, enabled: interjectEnabled))
  }

  static func lifetime(
    for notification: FloatingBarNotification, interjectEnabled: Bool
  ) -> FloatingBarNoticeLifetime {
    lifetime(
      title: notification.title,
      message: notification.message,
      kind: notification.kind,
      isPersistent: notification.isPersistent,
      interjectEnabled: interjectEnabled)
  }
}
