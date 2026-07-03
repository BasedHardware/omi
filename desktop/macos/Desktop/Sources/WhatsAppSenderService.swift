import AppKit
import CoreGraphics
import Foundation

enum WhatsAppSenderError: LocalizedError {
  /// Group (`@g.us`) or opaque (`@lid`) chat — no phone number to open a 1:1 send
  /// deep link, so automated send is disabled.
  case invalidTarget
  /// The reply text was prefilled into WhatsApp's compose box, but Omi couldn't
  /// press Return for you (Accessibility not granted). The user finishes the send.
  case manualSendRequired
  case sendFailed(String)

  var errorDescription: String? {
    switch self {
    case .invalidTarget:
      return "Automated send isn't available for this chat. Open WhatsApp and reply manually."
    case .manualSendRequired:
      return "Draft ready in WhatsApp — review it and press Enter to send."
    case .sendFailed(let message):
      return message
    }
  }
}

/// Sends an approved reply through WhatsApp.
///
/// Primary path (1:1 only): open `whatsapp://send?phone=<digits>&text=<encoded>` to
/// prefill the chat's compose box, then — after a short focus settle — press Return
/// in WhatsApp via a synthetic key event (requires Accessibility). Nothing is auto
/// sent unless the UI explicitly calls `send`.
///
/// Fallback (no Accessibility, or a group/opaque chat): prefill only and surface a
/// "review & press Enter in WhatsApp" prompt so the user completes the send.
enum WhatsAppSenderService {

  /// Delay before pressing Return, giving WhatsApp time to open the chat and focus
  /// the prefilled compose box.
  private static let returnPressDelay: TimeInterval = 1.5

  /// Outcome of the Return keystroke that actually sends the prefilled reply.
  private enum ReturnPress {
    case ok
    /// Automation/Accessibility permission missing — the reply is prefilled but we
    /// can't press Enter for the user.
    case notAuthorized
    case failed(String)
  }

  /// Bare phone digits usable in a `whatsapp://send?phone=` deep link, or nil for
  /// group (`@g.us`) / opaque (`@lid`) chats that have no dialable number.
  static func phoneDigits(forChatID chatID: String) -> String? {
    guard chatID.hasSuffix("@s.whatsapp.net") else { return nil }
    let local = chatID.split(separator: "@").first.map(String.init) ?? ""
    let digits = local.filter { $0.isNumber }
    return digits.count >= 7 ? digits : nil
  }

  /// Whether Omi can fully automate the send (a dialable phone AND Accessibility
  /// granted). `phone` is the chat's resolved dialable number (from the reader),
  /// which for `@lid` privacy chats isn't derivable from the JID. When false, the
  /// send path degrades to prefill-only.
  static func canAutoSend(chatID: String, phone: String? = nil) -> Bool {
    (phone ?? phoneDigits(forChatID: chatID)) != nil && WhatsAppPermissionPolicy.accessibilityGranted()
  }

  /// Prefill + (best-effort) send. Only ever called after the user taps Send, or
  /// for chats the user explicitly enabled auto-reply on. `phone` overrides the
  /// JID-derived number so `@lid` (new-contact) chats — whose dialable number lives
  /// in the session's identifier, not the JID — can still be sent to. Runs on the
  /// main actor because NSWorkspace/CGEvent prefer the main run loop.
  @MainActor
  static func send(text: String, toChatID chatID: String, phone explicitPhone: String? = nil) async throws {
    let digits = explicitPhone?.filter { $0.isNumber }
    guard let phone = (digits?.count ?? 0) >= 7 ? digits : phoneDigits(forChatID: chatID) else {
      // Group / no number — can't deep-link a 1:1 send. Bring WhatsApp forward
      // so the user can reply manually, then report the limitation.
      activateWhatsApp()
      throw WhatsAppSenderError.invalidTarget
    }

    try prefill(text: text, phone: phone)

    // Let WhatsApp open the chat and focus the prefilled compose box, then press
    // Return via System Events (osascript) to actually send. We AWAIT the result so
    // the UI only marks the reply sent when it truly was — a prefill-without-send
    // (missing Automation permission, etc.) surfaces as manualSendRequired instead
    // of a silent "sent" that never left the compose box.
    try? await Task.sleep(nanoseconds: UInt64(returnPressDelay * 1_000_000_000))
    switch await pressReturnInWhatsApp() {
    case .ok:
      return
    case .notAuthorized:
      throw WhatsAppSenderError.manualSendRequired
    case .failed(let message):
      throw WhatsAppSenderError.sendFailed(message)
    }
  }

  /// Opens the WhatsApp deep link that switches to the 1:1 chat and prefills the
  /// compose box with `text` (percent-encoded). Does not send.
  @MainActor
  static func prefill(text: String, phone: String) throws {
    var components = URLComponents()
    components.scheme = "whatsapp"
    components.host = "send"
    components.queryItems = [
      URLQueryItem(name: "phone", value: phone),
      URLQueryItem(name: "text", value: text),
    ]
    guard let url = components.url else {
      throw WhatsAppSenderError.sendFailed("Couldn't build the WhatsApp deep link.")
    }
    NSWorkspace.shared.open(url)
  }

  // MARK: - Helpers

  private static func runningWhatsApp() -> NSRunningApplication? {
    NSRunningApplication.runningApplications(
      withBundleIdentifier: WhatsAppPermissionPolicy.whatsappBundleID
    ).first
  }

  @MainActor
  private static func activateWhatsApp() {
    runningWhatsApp()?.activate(options: [.activateIgnoringOtherApps])
  }

  /// Presses Return in WhatsApp to send the prefilled reply. WhatsApp on macOS is a
  /// Catalyst app that ignores raw `CGEvent` key posts, but does honor a System
  /// Events keystroke — so we drive it through `osascript`, which atomically
  /// activates WhatsApp, lets the prefilled compose field focus, then keys Return.
  /// Requires Accessibility (already required) and Automation permission for the
  /// bundle to control System Events/WhatsApp. Fire-and-forget.
  private static func pressReturnInWhatsApp() async -> ReturnPress {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let script = """
          tell application "WhatsApp" to activate
          delay 0.8
          tell application "System Events" to key code 36
          """
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        proc.arguments = ["-e", script]
        let errPipe = Pipe()
        proc.standardError = errPipe
        do {
          try proc.run()
          proc.waitUntilExit()
        } catch {
          NSLog("WhatsApp send: osascript launch failed: \(error.localizedDescription)")
          continuation.resume(returning: .failed(error.localizedDescription))
          return
        }
        let errText =
          String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        if proc.terminationStatus == 0 {
          continuation.resume(returning: .ok)
          return
        }
        NSLog("WhatsApp send: osascript failed status=\(proc.terminationStatus) err=\(errText)")
        let lower = errText.lowercased()
        // -1743 / "not allowed"/"not authorized"/"assistive" all mean the app lacks
        // Automation (AppleEvents) permission to drive System Events / WhatsApp.
        if errText.contains("-1743") || lower.contains("not allow") || lower.contains("not authoriz")
          || lower.contains("assistive")
        {
          continuation.resume(returning: .notAuthorized)
        } else {
          continuation.resume(returning: .failed("Couldn't press Enter in WhatsApp. \(errText)"))
        }
      }
    }
  }
}
