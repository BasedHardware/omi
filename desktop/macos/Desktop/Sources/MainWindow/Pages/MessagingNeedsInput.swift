import AppKit
import Foundation
import SwiftUI

/// Which messaging inbox an escalation belongs to. Raw values are stable and travel
/// in the notification's userInfo, so don't rename them.
enum MessagingPlatform: String {
  case imessage
  case telegram
  case whatsapp
}

/// Auto-reply "needs your input" escalation.
///
/// When the backend decides an incoming message can't be safely auto-answered (we
/// can't answer it truthfully, it needs the user's own decision, or it asks for
/// sensitive info), the store keeps the best-guess draft as a SUGGESTION and calls
/// `notify(...)` instead of sending. The user gets a system banner + floating-bar
/// notification; tapping it opens the inbox to that chat, where the suggested draft is
/// already pre-filled in the composer for them to review, edit, and send.
enum MessagingNeedsInput {
  /// userInfo marker + assistant id (also the frequency-throttle bucket key).
  static let route = "messaging_needs_input"
  static let assistantId = "messaging_needs_input"

  /// Fire the escalation notification. `chatID` is the platform's chat identifier
  /// (iMessage chatGUID / Telegram chatID / WhatsApp chatID) — the same key the inbox
  /// uses to select a chat.
  @MainActor
  static func notify(
    personName: String, reason: String?, preview: String, platform: MessagingPlatform, chatID: String
  ) {
    let who = personName.trimmingCharacters(in: .whitespacesAndNewlines)
    let title = who.isEmpty ? "A message needs your input" : "\(who) needs your input"
    // Lead with the reason (why we didn't auto-reply), then show the suggested draft so
    // the user can decide at a glance without opening the app.
    let cleanReason = (reason ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let suggestion = preview.trimmingCharacters(in: .whitespacesAndNewlines)
    var message = cleanReason.isEmpty ? "I didn't auto-reply — take a look." : cleanReason
    if !suggestion.isEmpty {
      message += "\nSuggested: \(suggestion)"
    }

    NotificationService.shared.sendNotification(
      title: title,
      message: message,
      assistantId: assistantId,
      // Reach the user even when the floating bar is hidden/snoozed and regardless of
      // the proactive-notification frequency setting — this is a functional heads-up
      // about their own messages, not a proactive AI nudge.
      deliverSystemBanner: true,
      respectFrequency: false,
      userInfo: ["route": route, "platform": platform.rawValue, "chatID": chatID]
    )
  }

  /// Called from the notification-tap delegate. Brings the app forward and asks the
  /// inbox UI to open the escalated chat.
  @MainActor
  static func handleNotificationTap(_ userInfo: [AnyHashable: Any]) {
    guard
      let platformRaw = userInfo["platform"] as? String,
      let platform = MessagingPlatform(rawValue: platformRaw),
      let chatID = userInfo["chatID"] as? String
    else { return }
    NSApplication.shared.activate(ignoringOtherApps: true)
    MessagingNeedsInputRouter.shared.request(platform: platform, chatID: chatID)
  }
}

/// Bridges a notification tap to the messaging inbox UI. The UI layer (the main
/// window) observes `pendingOpen` and navigates to the right inbox + chat; it clears
/// the value once handled. Kept separate from `MessagingNeedsInput` so the pure
/// notification helper has no view dependencies.
@MainActor
final class MessagingNeedsInputRouter: ObservableObject {
  static let shared = MessagingNeedsInputRouter()

  struct OpenTarget: Equatable {
    let platform: MessagingPlatform
    let chatID: String
  }

  /// Set when a tap needs the UI to open a chat; the observer clears it after handling.
  @Published var pendingOpen: OpenTarget?

  private init() {}

  func request(platform: MessagingPlatform, chatID: String) {
    pendingOpen = OpenTarget(platform: platform, chatID: chatID)
  }
}
