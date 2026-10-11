import AppKit
import Foundation

/// Opens Apple's own compose UI, filled in, for the person to send.
///
/// This is the macOS side of the `propose_*` contract iOS already ships: Omi
/// prepares the draft and the person presses Send. Nothing here sends. There is
/// no AppleScript and no Mail or Messages automation, so no code path can
/// deliver a message without the person acting in Apple's window.
enum ComposeProposalChannel: String, Sendable {
  case message
  case email
}

struct ComposeProposal: Equatable, Sendable {
  let channel: ComposeProposalChannel
  let recipients: [String]
  let subject: String?
  let body: String
}

/// What one proposal ended as, from Omi's side of the window.
///
/// There is deliberately no `sent` case. Mail reports a share as soon as it
/// takes the draft, before the person presses Send, and neither service lets
/// Omi confirm delivery, so the most Omi can honestly say is that it handed the
/// draft over.
enum ComposeProposalOutcome: Equatable, Sendable {
  /// The compose service took the draft and reported no cancellation.
  case handedOff
  /// The person closed the compose window without sending.
  case cancelled
  /// The compose service reported an error. Only the code is kept: the
  /// localized text is not needed and is not part of the tool result.
  case failed(code: Int)
  /// Still on screen when the wait ended; the person decides.
  case open
  /// A Messages sheet Omi opened earlier has not reported back yet (only
  /// when the system shows a sheet rather than handing off to Messages).
  case alreadyOpen
  /// The same draft was handed off moments ago and is waiting for the person.
  case duplicateDraft
  /// Omi already opened a draft for this request, or several in the last minute.
  case limitReached
  /// This Mac cannot show the compose window (no Mail account, Messages not set up).
  case unavailable
  /// No window was opened: the turn was stopped first, or the person kept
  /// typing, so their keystrokes could have landed in the draft.
  case notOpened(ComposeNotOpenedReason)
}

enum ComposeNotOpenedReason: String, Equatable, Sendable {
  case stopped
  case personTyping = "person_typing"
}

/// Who is asking, so one person's limits never apply to another.
struct ComposeProposalContext: Equatable, Sendable {
  let runID: String?
  let ownerID: String?
}

/// The app that opens an email draft.
///
/// `NSSharingService.composeEmail` hands the draft to whatever app handles
/// `mailto:` links, which may be Mail, another mail app, or a browser that
/// opens its web mail site. Results name that app instead of assuming Mail.
struct ComposeEmailApp: Equatable, Sendable {
  let name: String
  let bundleID: String?
  /// The handler is a web browser, so the draft opens on a web mail site.
  let isBrowser: Bool

  /// Browsers commonly set as the `mailto:` handler, for when the default
  /// web browser is a different one.
  static let knownBrowserBundleIDs: Set<String> = [
    "com.google.chrome", "com.apple.safari", "org.mozilla.firefox", "com.microsoft.edgemac",
    "company.thebrowser.browser", "com.brave.browser", "com.operasoftware.opera", "com.vivaldi.vivaldi",
    "com.google.chrome.canary", "org.chromium.chromium", "app.zen-browser.zen",
  ]

  init(name: String, bundleID: String?, isBrowser: Bool) {
    self.name = name
    self.bundleID = bundleID
    self.isBrowser = isBrowser
  }

  /// Classifies a handler: a browser when it is a known browser or the same
  /// app that opens web links.
  init(name: String, bundleID: String?, webLinkHandlerBundleID: String?) {
    let id = bundleID?.lowercased()
    let web = webLinkHandlerBundleID?.lowercased()
    self.init(
      name: name,
      bundleID: bundleID,
      isBrowser: id.map { Self.knownBrowserBundleIDs.contains($0) || $0 == web } ?? false)
  }

  /// The current `mailto:` handler, or nil when none is set.
  @MainActor
  static func systemDefault() -> ComposeEmailApp? {
    guard let mailto = URL(string: "mailto:"),
      let appURL = NSWorkspace.shared.urlForApplication(toOpen: mailto)
    else { return nil }
    let name = FileManager.default.displayName(atPath: appURL.path)
    let bundleID = Bundle(url: appURL)?.bundleIdentifier
    let webHandler = URL(string: "https://example.com")
      .flatMap { NSWorkspace.shared.urlForApplication(toOpen: $0) }
      .flatMap { Bundle(url: $0)?.bundleIdentifier }
    return ComposeEmailApp(
      name: name.hasSuffix(".app") ? String(name.dropLast(4)) : name,
      bundleID: bundleID,
      webLinkHandlerBundleID: webHandler)
  }
}

/// What a compose window reports back. Called at most once per presentation.
enum ComposeSurfaceEvent: Equatable, Sendable {
  case shared
  case cancelled
  case notConfigured
  case failed(code: Int)

  init(sharingError error: NSError) {
    guard error.domain == NSCocoaErrorDomain else {
      self = .failed(code: error.code)
      return
    }
    switch error.code {
    case NSUserCancelledError: self = .cancelled
    case CocoaError.Code.sharingServiceNotConfigured.rawValue: self = .notConfigured
    default: self = .failed(code: error.code)
    }
  }
}

/// The seam between the coordinator and AppKit, so tests never open a window.
@MainActor
protocol ComposeSurface: AnyObject {
  func canPresent(_ proposal: ComposeProposal) -> Bool
  /// Shows the compose window. Returns false when the system refused to start
  /// it; otherwise `onEvent` runs at most once, on the main actor.
  func present(_ proposal: ComposeProposal, onEvent: @escaping @MainActor (ComposeSurfaceEvent) -> Void) -> Bool
}

/// The real compose windows, through `NSSharingService`.
@MainActor
final class SystemComposeSurface: ComposeSurface {
  private var activeService: NSSharingService?
  private var activeObserver: ComposeShareObserver?

  func canPresent(_ proposal: ComposeProposal) -> Bool {
    guard let service = Self.service(for: proposal) else { return false }
    return service.canPerform(withItems: [proposal.body])
  }

  func present(
    _ proposal: ComposeProposal,
    onEvent: @escaping @MainActor (ComposeSurfaceEvent) -> Void
  ) -> Bool {
    guard let service = Self.service(for: proposal), service.canPerform(withItems: [proposal.body]) else {
      return false
    }
    // The service holds its delegate weakly, so the observer is kept here
    // until the window reports.
    let observer = ComposeShareObserver { [weak self] event in
      self?.activeService = nil
      self?.activeObserver = nil
      onEvent(event)
    }
    service.delegate = observer
    activeService = service
    activeObserver = observer
    // Current macOS hands the draft to the Messages app, which comes forward
    // itself. If the system shows a sheet instead, it belongs to Omi's process,
    // so Omi has to be in front for the person to see it.
    if proposal.channel == .message {
      NSApp.activate()
    }
    service.perform(withItems: [proposal.body])
    return true
  }

  private static func service(for proposal: ComposeProposal) -> NSSharingService? {
    let name: NSSharingService.Name = proposal.channel == .email ? .composeEmail : .composeMessage
    guard let service = NSSharingService(named: name) else { return nil }
    service.recipients = proposal.recipients
    if let subject = proposal.subject {
      service.subject = subject
    }
    return service
  }
}

@MainActor
private final class ComposeShareObserver: NSObject, NSSharingServiceDelegate {
  private var onEvent: (@MainActor (ComposeSurfaceEvent) -> Void)?

  init(onEvent: @escaping @MainActor (ComposeSurfaceEvent) -> Void) {
    self.onEvent = onEvent
  }

  func sharingService(_ sharingService: NSSharingService, didShareItems items: [Any]) {
    report(.shared)
  }

  func sharingService(_ sharingService: NSSharingService, didFailToShareItems items: [Any], error: Error) {
    report(ComposeSurfaceEvent(sharingError: error as NSError))
  }

  private func report(_ event: ComposeSurfaceEvent) {
    let callback = onEvent
    onEvent = nil
    callback?(event)
  }
}
