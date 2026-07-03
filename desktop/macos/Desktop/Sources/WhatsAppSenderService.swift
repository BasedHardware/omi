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
  /// Omi could not verify — before pressing Return — that WhatsApp had the target chat
  /// open with our reply in the compose box, so it never pressed Return. Nothing was
  /// sent; the draft is kept and it is safe to try again. This is the fail-closed guard
  /// that makes "never send to the wrong person" hold even when WhatsApp's UI misbehaves.
  case notConfirmed
  /// Return WAS pressed against the verified target chat, but the outbound row didn't
  /// appear in WhatsApp's database within the confirmation window. The reply was very
  /// likely delivered; Omi just can't prove it. The draft is kept and the user is asked
  /// to check WhatsApp before resending, so a genuine delivery isn't duplicated.
  case sendUnconfirmed
  case sendFailed(String)

  var errorDescription: String? {
    switch self {
    case .invalidTarget:
      return "Automated send isn't available for this chat. Open WhatsApp and reply manually."
    case .permissionRequired:
      return
        "Omi needs Accessibility & Automation access to send in WhatsApp. Grant it in System Settings — then Omi sends for you automatically."
    case .notConfirmed:
      return "Couldn't reach the right chat to send — Omi kept the draft. Try again."
    case .sendUnconfirmed:
      return
        "Reply sent to WhatsApp, but Omi couldn't confirm it landed — open WhatsApp to check before resending."
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
///     chat *is* the intended recipient. Re-verify `compose == Y` once more right before
///     sending. If we can't verify, we **never press Return** — fail closed.
///  3. **Send** — one osascript that atomically activates WhatsApp and *then* keys Return
///     (WhatsApp's Catalyst app ignores raw `CGEvent`; System Events works). Activating
///     inside the same script guarantees Return is delivered to WhatsApp — not to some
///     app that stole focus after the guard — and the compose content is per-chat, so
///     activating can't change which chat the verified `Y` belongs to.
///  4. **Proof (detection + "actually sent")** — poll WhatsApp's own `ChatStorage.sqlite`
///     for an outbound row matching `Y` in the target chat, created after a pre-send
///     row-id baseline. Confirmed → success. Pressed-but-unconfirmed → `.sendUnconfirmed`
///     (kept as a draft; the user is asked to check before resending, so a real delivery
///     isn't duplicated). Never verified → `.notConfirmed` (safe to retry; nothing sent).
///  5. **Restore focus** — reactivate whatever app was frontmost before, so sending
///     doesn't hijack the user's window.
///
/// The recipient guard prevents a wrong send; the row-id `ChatStorage.sqlite` proof both
/// confirms delivery and, keyed to the target chat, is the backstop that surfaces any
/// unexpected outcome as unconfirmed rather than falsely "sent".
enum WhatsAppSenderService {

  // Recipient-guard / settle timing.
  private static let settlePollNanos: UInt64 = 150_000_000  // 0.15s between compose reads
  private static let settleMaxPolls = 27  // ~4.0s to see the prefill land
  private static let settleReprefillPoll = 12  // ~1.8s in: nudge the deep link once
  private static let activatePollNanos: UInt64 = 100_000_000  // 0.10s
  private static let activateMaxPolls = 10  // ~1.0s for WhatsApp to come frontmost
  // Post-send DB proof.
  private static let confirmPollNanos: UInt64 = 400_000_000  // 0.4s
  private static let confirmMaxPolls = 20  // ~8.0s for WhatsApp to persist the outbound row
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

    // Restore the user's frontmost app whatever the outcome, so sending never leaves
    // WhatsApp stealing focus.
    let priorFront = NSWorkspace.shared.frontmostApplication
    defer { restoreFrontmost(priorFront) }

    // Row-id baseline for the post-send proof: only a message created after this counts
    // as the one we're about to send (so the proof can't match a pre-existing message).
    // Fail closed if we can't read it — without a valid baseline the row-id invariant
    // doesn't hold, so don't send (nothing sent, safe to retry).
    guard let baselineRowID = try? await WhatsAppReaderService.shared.maxMessageRowID() else {
      throw WhatsAppSenderError.notConfirmed
    }

    // Prefill launches WhatsApp if it's closed, opens the target 1:1, and fills the
    // compose box; the guard below then waits for it to come up and navigate.
    try prefill(text: reply, phone: phone)

    // Recipient guard: wait for WhatsApp to navigate + prefill, proven by compose == reply,
    // then re-verify once more right before sending. If either can't be verified we never
    // press Return — nothing is sent, and it's safe to retry (.notConfirmed).
    guard await waitForComposeMatch(reply: reply, phone: phone),
      await activateAndReverify(reply: reply)
    else {
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

    // Return has fired against the verified target — restore the user's foreground app
    // now, before the DB confirmation poll (which reads sqlite and doesn't need WhatsApp
    // frontmost), so a send doesn't hijack their window for the whole confirm window.
    restoreFrontmost(priorFront)

    // Return was pressed against the verified target. Ground-truth proof it landed: an
    // outbound row matching the reply in this chat (by `@lid` JID or phone session),
    // created after our baseline. If it doesn't appear in the window the send probably
    // still succeeded, so report `.sendUnconfirmed` (draft kept, user asked to check) —
    // never a silent false "sent", and never an auto-retry that could duplicate it.
    let phoneJID = "\(phone)@s.whatsapp.net"
    guard
      await WhatsAppReaderService.shared.confirmSent(
        text: reply, chatID: chatID, phoneJID: phoneJID, afterRowID: baselineRowID,
        pollNanos: confirmPollNanos, maxPolls: confirmMaxPolls)
    else {
      throw WhatsAppSenderError.sendUnconfirmed
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
  /// is open and prefilled) or times out. Looks the app up each poll so it also covers a
  /// cold launch (WhatsApp was closed and the prefill deep link is starting it), and
  /// re-issues the deep link once mid-way if navigation stalled. AX reads work even while
  /// WhatsApp is in the background.
  @MainActor
  private static func waitForComposeMatch(reply: String, phone: String) async -> Bool {
    for poll in 0..<settleMaxPolls {
      if poll == settleReprefillPoll {
        try? prefill(text: reply, phone: phone)  // nudge once if it hasn't landed yet
      }
      if let app = runningWhatsApp(),
        let value = await readComposeValueOffMain(pid: app.processIdentifier),
        composeMatches(value, reply)
      {
        return true
      }
      try? await Task.sleep(nanoseconds: settlePollNanos)
    }
    return false
  }

  /// Brings WhatsApp frontmost (required for the keystroke to land there) and confirms
  /// compose still equals `reply`, as the final check before pressing Return.
  @MainActor
  private static func activateAndReverify(reply: String) async -> Bool {
    activateWhatsApp()
    for _ in 0..<activateMaxPolls {
      if let app = runningWhatsApp(), app.isActive,
        let value = await readComposeValueOffMain(pid: app.processIdentifier),
        composeMatches(value, reply)
      {
        return true
      }
      try? await Task.sleep(nanoseconds: activatePollNanos)
    }
    return false
  }

  /// Reads the compose value off the main thread. The AX tree walk is synchronous
  /// cross-process IPC that can block on WhatsApp's AX messaging timeout if the app is
  /// unresponsive; running it on a background queue keeps that from stalling the UI
  /// during the poll loops. AX APIs are not main-thread-bound, and the walk touches no
  /// main-actor state.
  private static func readComposeValueOffMain(pid: pid_t) async -> String? {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        continuation.resume(returning: composeBoxValue(pid: pid))
      }
    }
  }

  private static func composeMatches(_ composeValue: String, _ reply: String) -> Bool {
    composeValue.trimmingCharacters(in: .whitespacesAndNewlines)
      == reply.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Reads WhatsApp's compose box value: the `AXTextArea` whose `AXDescription` contains
  /// "Compose message". Returns nil when the element can't be found (no chat open); an
  /// empty box reads back as nil or an empty string depending on WhatsApp — either way it
  /// won't match a non-empty reply, so the recipient guard keeps polling.
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

  /// Presses Return in WhatsApp to send the prefilled, recipient-verified reply. One
  /// osascript atomically activates WhatsApp and *then* keys Return, so the keystroke is
  /// bound to WhatsApp even if focus shifted after the guard (Catalyst ignores raw
  /// `CGEvent`, so System Events is required). Requires Automation permission to control
  /// System Events / WhatsApp. Runs off the main run loop so the UI stays responsive.
  private static func pressReturnInWhatsApp() async -> ReturnPress {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let script = """
          tell application "WhatsApp" to activate
          delay 0.15
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
