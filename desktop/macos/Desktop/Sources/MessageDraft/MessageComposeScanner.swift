import AppKit
import ApplicationServices
import Foundation

/// The focused element as message-draft assist judges it. Value types only, so every
/// gate decision is testable without a window on screen.
struct MessageComposeContext: Sendable, Equatable {
  let appName: String
  let windowTitle: String
  let focusedRole: String
  /// The element's own name for itself: title, placeholder, description or help —
  /// whichever it filled in first.
  let focusedLabel: String
  let focusedValue: String
  let isSecure: Bool
}

/// What the frontmost window looks like when the compose gate says yes.
struct MessageComposeSnapshot: Sendable, Equatable {
  let context: MessageComposeContext
  let surface: MessageComposeGate.Surface
  let windowFrame: CGRect?
  let windowID: CGWindowID?

  /// Identity of "this conversation", as close as titles get to it. Native chat apps
  /// often title every conversation the same (WhatsApp's window is just "WhatsApp"),
  /// so this is deliberately coarse: one offer per window title, and the dismissal
  /// memory is what keeps the card from nagging inside one app session.
  var fingerprint: String {
    [context.appName, context.windowTitle].joined(separator: "\u{1F}")
  }
}

/// Decides whether the user is looking at a place messages are written, and whether the
/// box they would write into is focused and still empty. Pure; the cost contract is a
/// card that only ever appears where a draft could actually be sent.
enum MessageComposeGate {
  /// Where the compose box lives — a messaging app itself, or a messaging site open in
  /// a browser. The name is what the card calls it.
  enum Surface: Sendable, Equatable {
    case nativeApp(String)
    case webApp(String)

    var displayName: String {
      switch self {
      case .nativeApp(let name), .webApp(let name): return name
      }
    }
  }

  enum Decision: String, Sendable, Equatable {
    case eligible
    case notMessaging
    case noComposeFocus
    case composeNotEmpty
    case searchField
    case secureField
  }

  /// Apps that exist to send messages. Substring match on the localized app name, so
  /// "Microsoft Outlook" and "Outlook" are one entry.
  private static let messagingApps: [(term: String, name: String)] = [
    ("mail", "Mail"),
    ("messages", "Messages"),
    ("whatsapp", "WhatsApp"),
    ("telegram", "Telegram"),
    ("slack", "Slack"),
    ("discord", "Discord"),
    ("signal", "Signal"),
    ("outlook", "Outlook"),
  ]

  private static let browsers = [
    "safari", "chrome", "arc", "firefox", "brave", "edge", "opera", "vivaldi", "orion", "dia",
  ]

  /// Messaging sites as their tab titles name them. A Gmail tab is "Inbox — Gmail", a
  /// WhatsApp Web tab is "WhatsApp"; the browser puts the site's own name in the title,
  /// which is the one signal available without reading the URL.
  private static let webApps: [(term: String, name: String)] = [
    ("gmail", "Gmail"),
    ("whatsapp", "WhatsApp"),
    ("telegram", "Telegram"),
    ("outlook", "Outlook"),
    ("proton mail", "Proton Mail"),
    ("google messages", "Google Messages"),
  ]

  /// Fields that are text inputs but never compose boxes.
  private static let nonComposeTerms = [
    "search", "address", "url", "find", "filter", "location",
  ]

  static func surface(appName: String, windowTitle: String) -> Surface? {
    let app = appName.lowercased()
    if let match = messagingApps.first(where: { app.contains($0.term) }) {
      // "Mail" must not swallow "Mailplane"-style browser names; the app list matches
      // whole products, so a browser is checked first and wins.
      if !browsers.contains(where: { app.contains($0) }) {
        return .nativeApp(match.name)
      }
    }
    guard browsers.contains(where: { app.contains($0) }) else { return nil }
    let title = windowTitle.lowercased()
    guard let match = webApps.first(where: { title.contains($0.term) }) else { return nil }
    return .webApp(match.name)
  }

  static func decide(_ context: MessageComposeContext) -> Decision {
    guard surface(appName: context.appName, windowTitle: context.windowTitle) != nil else {
      return .notMessaging
    }
    let role = context.focusedRole.lowercased()
    guard role.contains("textarea") || role.contains("textfield") else {
      return .noComposeFocus
    }
    guard !role.contains("secure") else { return .secureField }
    let label = context.focusedLabel.lowercased()
    guard !nonComposeTerms.contains(where: { label.contains($0) }) else { return .searchField }
    guard context.focusedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return .composeNotEmpty
    }
    return .eligible
  }
}

/// Why a scan produced no offer. Every refusal is loggable, because a card that
/// silently never appears is indistinguishable from a broken one.
enum MessageComposeScanOutcome {
  case eligible(MessageComposeSnapshot)
  case refused(String)

  var snapshot: MessageComposeSnapshot? {
    guard case .eligible(let snapshot) = self else { return nil }
    return snapshot
  }

  var refusal: String? {
    guard case .refused(let reason) = self else { return nil }
    return reason
  }
}

/// Reads the frontmost window's focused element — one AX element, never a tree walk —
/// and describes it in the gate's terms.
enum MessageComposeScanner {
  @MainActor
  static func scanFocusedCompose() -> MessageComposeScanOutcome {
    guard AXIsProcessTrusted() else { return .refused("ax-untrusted") }
    guard let app = NSWorkspace.shared.frontmostApplication,
      app.processIdentifier != ProcessInfo.processInfo.processIdentifier
    else { return .refused("no-frontmost-app") }

    let appName = app.localizedName ?? ""
    let info = ScreenCaptureService.getActiveWindowInfo()
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    let window = AXFormTree.elementAttribute(appElement, "AXFocusedWindow")
    let axTitle = window.map { AXFormTree.stringAttribute($0, "AXTitle") } ?? ""
    let windowTitle = axTitle.isEmpty ? (info.windowTitle ?? "") : axTitle

    guard let surface = MessageComposeGate.surface(appName: appName, windowTitle: windowTitle)
    else { return .refused(MessageComposeGate.Decision.notMessaging.rawValue) }

    guard let focused = AXFormTree.elementAttribute(appElement, "AXFocusedUIElement")
    else { return .refused("no-focused-element") }
    let node = AXFormTree.node(from: focused)
    let label =
      [node.title, node.placeholder, node.description, node.help]
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .first { !$0.isEmpty } ?? ""

    let context = MessageComposeContext(
      appName: appName,
      windowTitle: windowTitle,
      focusedRole: node.role,
      focusedLabel: label,
      focusedValue: node.value,
      isSecure: node.role.lowercased().contains("secure")
    )
    let decision = MessageComposeGate.decide(context)
    guard decision == .eligible else { return .refused(decision.rawValue) }

    let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]]
    return .eligible(
      MessageComposeSnapshot(
        context: context,
        surface: surface,
        windowFrame: windows.flatMap {
          CloudConnectorFormAutomation.appKitWindowFrame(pid: app.processIdentifier, windows: $0)
        },
        windowID: info.windowID
      ))
  }
}
