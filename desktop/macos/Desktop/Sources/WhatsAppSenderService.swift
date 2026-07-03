import AppKit
import ApplicationServices
import Foundation

enum WhatsAppSenderError: LocalizedError {
  /// Group (`@g.us`) or opaque (`@lid`) chat with no dialable number — there's no 1:1
  /// deep link to open, so automated send is disabled and the user replies manually.
  case invalidTarget
  /// Accessibility / Automation permission is missing, so Omi can't read the compose
  /// box (recipient guard) or press Return. The reply is prefilled; the user grants the
  /// one-time permission and Omi sends automatically thereafter.
  case permissionRequired
  /// Omi could not prove — before the keystroke (compose box holds exactly our reply in
  /// the target chat) or after it (an outbound row for this chat in WhatsApp's database)
  /// — that the reply went to the intended person. The send was NOT performed / not
  /// confirmed; the draft is kept and retried. This is the fail-closed guard that makes
  /// "never send to the wrong person" hold even when WhatsApp's UI misbehaves.
  case notConfirmed
  case sendFailed(String)

  var errorDescription: String? {
    switch self {
    case .invalidTarget:
      return "Automated send isn't available for this chat. Open WhatsApp and reply manually."
    case .permissionRequired:
      return
        "Omi needs Accessibility & Automation access to send in WhatsApp. Grant it in System Settings — then Omi sends for you automatically."
    case .notConfirmed:
      return "Couldn't confirm the reply was sent to the right chat — Omi kept the draft and will retry."
    case .sendFailed(let message):
      return message
    }
  }
}

/// Sends an approved reply through WhatsApp, fully automatically, with two guarantees:
/// it goes to the **intended** person, and it is only reported sent once it **actually**
/// left. WhatsApp on macOS is a Catalyst app with no send-scripting API, so we drive its
/// UI — but never blindly.
///
/// Flow (1:1 only; the user never has to press Enter on the happy path):
///  1. **Prefill** — open `whatsapp://send?phone=<digits>&text=<Y>`. WhatsApp itself
///     switches to that 1:1 chat and puts `Y` into *its* compose box.
///  2. **Recipient guard (prevention)** — poll the Accessibility tree until WhatsApp's
///     compose box (`AXTextArea` "Compose message") holds exactly `Y`. Because WhatsApp
///     placed our unique reply into the target chat's box, `compose == Y` proves the open
///     chat *is* the intended recipient. Then activate WhatsApp and re-verify `compose ==
///     Y` immediately before pressing Return, so nothing can slip in between (minimal
///     check→act gap). If we can't verify, we **never press** — fail closed.
///  3. **Send** — press Return via a System Events keystroke (WhatsApp's Catalyst app
///     ignores raw `CGEvent`; System Events works). WhatsApp is already frontmost and
///     verified, so the keystroke lands in the target chat's compose box.
///  4. **Proof (detection + "actually sent")** — poll WhatsApp's own `ChatStorage.sqlite`
///     for an outbound row in the target chat's JID matching `Y`. Only then is the send
///     reported successful; otherwise `.notConfirmed` (kept as a draft, retried).
///  5. **Restore focus** — reactivate whatever app was frontmost before, so sending
///     doesn't hijack the user's window.
///
/// Residual (documented, not hidden): between the final compose re-verify and the
/// keystroke there is a sub-100ms fully-automated window in which no user interaction is
/// possible. In the astronomically unlikely event a wrong chat were nonetheless targeted,
/// the `ChatStorage.sqlite` proof (keyed by the target JID) fails and we report the send
/// unconfirmed rather than falsely "sent".
enum WhatsAppSenderService {

  // Recipient-guard / settle timing.
  private static let settlePollNanos: UInt64 = 150_000_000  // 0.15s between compose reads
  private static let settleMaxPolls = 27  // ~4.0s to see the prefill land
  private static let settleReprefillPoll = 12  // ~1.8s in: nudge the deep link once
  private static let activatePollNanos: UInt64 = 100_000_000  // 0.10s
  private static let activateMaxPolls = 10  // ~1.0s for WhatsApp to come frontmost
  // Post-send DB proof.
  private static let confirmPollNanos: UInt64 = 400_000_000  // 0.4s
  private static let confirmMaxPolls = 15  // ~6.0s for WhatsApp to persist the outbound row
  /// Clock skew subtracted from the pre-send timestamp so the DB proof can't match a
  /// pre-existing identical outbound message, while still catching the one we just sent.
  private static let confirmSkewSeconds: Double = 3.0
  /// The `AXTextArea` for WhatsApp's compose box carries this in its `AXDescription`
  /// (verified live 2026-07-03; the real value has a leading LTR mark, so match a
  /// substring rather than the whole string).
  private static let composeDescriptionMarker = "Compose"

  private enum ReturnPress {
    case ok
    case notAuthorized  // Automation/Accessibility permission missing
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
  /// granted). `phone` is the chat's resolved dialable number (from the reader), which
  /// for `@lid` privacy chats isn't derivable from the JID.
  static func canAutoSend(chatID: String, phone: String? = nil) -> Bool {
    (phone ?? phoneDigits(forChatID: chatID)) != nil && WhatsAppPermissionPolicy.accessibilityGranted()
  }

  /// Prefill → verified auto-send → DB-confirmed. Returns normally only when the reply
  /// is proven sent to the intended chat; otherwise throws (see `WhatsAppSenderError`).
  /// `phone` overrides the JID-derived number so `@lid` (new-contact) chats can be sent
  /// to. Runs on the main actor because NSWorkspace/AX prefer the main run loop; the
  /// osascript keystroke and the DB read are dispatched off-main so the UI stays live.
  @MainActor
  static func send(text: String, toChatID chatID: String, phone explicitPhone: String? = nil) async throws {
    let reply = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !reply.isEmpty else { throw WhatsAppSenderError.notConfirmed }

    let digits = explicitPhone?.filter { $0.isNumber }
    guard let phone = (digits?.count ?? 0) >= 7 ? digits : phoneDigits(forChatID: chatID) else {
      // Group / no number — can't deep-link a 1:1 send. Bring WhatsApp forward for a
      // manual reply and report the limitation.
      activateWhatsApp()
      throw WhatsAppSenderError.invalidTarget
    }

    // Accessibility is required both to read the compose box (recipient guard) and to
    // press Return. Without it we cannot safely auto-send, so prefill for a manual send
    // and ask for the one-time grant.
    guard WhatsAppPermissionPolicy.accessibilityGranted() else {
      try prefill(text: reply, phone: phone)
      throw WhatsAppSenderError.permissionRequired
    }

    guard let app = runningWhatsApp() else {
      throw WhatsAppSenderError.sendFailed("WhatsApp isn't running.")
    }

    // Restore the user's frontmost app whatever the outcome, so sending never leaves
    // WhatsApp stealing focus.
    let priorFront = NSWorkspace.shared.frontmostApplication
    defer { restoreFrontmost(priorFront) }

    // Floor for the post-send DB proof, in WhatsApp's reference-date seconds.
    let sinceRef = Date().timeIntervalSinceReferenceDate - confirmSkewSeconds

    try prefill(text: reply, phone: phone)

    // Recipient guard: wait for WhatsApp to navigate + prefill, proven by compose == reply.
    guard await waitForComposeMatch(reply: reply, phone: phone, pid: app.processIdentifier) else {
      throw WhatsAppSenderError.notConfirmed
    }

    // Bring WhatsApp frontmost and re-verify compose == reply the instant before the
    // keystroke, closing the check→act gap.
    guard await activateAndReverify(reply: reply, pid: app.processIdentifier) else {
      throw WhatsAppSenderError.notConfirmed
    }

    switch await pressReturnInWhatsApp() {
    case .ok:
      break
    case .notAuthorized:
      throw WhatsAppSenderError.permissionRequired
    case .failed(let message):
      throw WhatsAppSenderError.sendFailed(message)
    }

    // Ground-truth proof the reply landed in the target chat's JID.
    guard await confirmSent(reply: reply, chatID: chatID, sinceRef: sinceRef) else {
      throw WhatsAppSenderError.notConfirmed
    }
  }

  /// Opens the WhatsApp deep link that switches to the 1:1 chat and prefills the compose
  /// box with `text` (percent-encoded). Does not send.
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

  // MARK: - Recipient guard (Accessibility)

  /// Polls WhatsApp's compose box until it holds exactly `reply` (proof the target 1:1
  /// is open and prefilled) or times out. Re-issues the deep link once mid-way if
  /// navigation stalled. AX reads work even while WhatsApp is in the background.
  @MainActor
  private static func waitForComposeMatch(reply: String, phone: String, pid: pid_t) async -> Bool {
    for poll in 0..<settleMaxPolls {
      if poll == settleReprefillPoll {
        try? prefill(text: reply, phone: phone)  // nudge once if it hasn't landed yet
      }
      if let value = composeBoxValue(pid: pid), composeMatches(value, reply) {
        return true
      }
      try? await Task.sleep(nanoseconds: settlePollNanos)
    }
    return false
  }

  /// Brings WhatsApp frontmost (required for the keystroke to land there) and confirms
  /// compose still equals `reply`, as the final check before pressing Return.
  @MainActor
  private static func activateAndReverify(reply: String, pid: pid_t) async -> Bool {
    activateWhatsApp()
    for _ in 0..<activateMaxPolls {
      if let app = runningWhatsApp(), app.isActive,
        let value = composeBoxValue(pid: pid), composeMatches(value, reply)
      {
        return true
      }
      try? await Task.sleep(nanoseconds: activatePollNanos)
    }
    return false
  }

  private static func composeMatches(_ composeValue: String, _ reply: String) -> Bool {
    composeValue.trimmingCharacters(in: .whitespacesAndNewlines)
      == reply.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Reads WhatsApp's compose box value: the `AXTextArea` whose `AXDescription` contains
  /// "Compose message". Returns nil when it can't be found (no chat open) or is empty.
  private static func composeBoxValue(pid: pid_t) -> String? {
    findComposeValue(AXUIElementCreateApplication(pid), depth: 0)
  }

  private static func findComposeValue(_ element: AXUIElement, depth: Int) -> String? {
    if depth > 40 { return nil }
    if axString(element, kAXRoleAttribute) == "AXTextArea",
      let desc = axString(element, kAXDescriptionAttribute), desc.contains(composeDescriptionMarker)
    {
      return axString(element, kAXValueAttribute)
    }
    for child in axChildren(element) {
      if let value = findComposeValue(child, depth: depth + 1) { return value }
    }
    return nil
  }

  private static func axString(_ element: AXUIElement, _ attribute: String) -> String? {
    var value: AnyObject?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success else {
      return nil
    }
    return value as? String
  }

  private static func axChildren(_ element: AXUIElement) -> [AXUIElement] {
    var value: AnyObject?
    guard
      AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &value) == .success
    else { return [] }
    return (value as? [AXUIElement]) ?? []
  }

  // MARK: - Post-send proof

  /// Polls `ChatStorage.sqlite` (via the reader) until the outbound row for this send
  /// appears in the target chat's JID, or times out.
  private static func confirmSent(reply: String, chatID: String, sinceRef: Double) async -> Bool {
    for _ in 0..<confirmMaxPolls {
      if let confirmed = try? await WhatsAppReaderService.shared.confirmSent(
        text: reply, chatID: chatID, sinceReferenceSeconds: sinceRef), confirmed
      {
        return true
      }
      try? await Task.sleep(nanoseconds: confirmPollNanos)
    }
    return false
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

  /// Reactivate the app that was frontmost before the send (unless it was WhatsApp), so
  /// automated sending doesn't leave the user's window buried.
  @MainActor
  private static func restoreFrontmost(_ app: NSRunningApplication?) {
    guard let app, app.bundleIdentifier != WhatsAppPermissionPolicy.whatsappBundleID,
      !app.isTerminated
    else { return }
    app.activate(options: [.activateIgnoringOtherApps])
  }

  /// Presses Return in WhatsApp to send the prefilled, recipient-verified reply. WhatsApp
  /// is already frontmost; System Events keys Return into it (Catalyst ignores raw
  /// `CGEvent`). Requires Automation permission to control System Events. Runs off the
  /// main run loop so the UI stays responsive.
  private static func pressReturnInWhatsApp() async -> ReturnPress {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let script = "tell application \"System Events\" to key code 36"
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
        // Automation (AppleEvents) permission to drive System Events.
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
