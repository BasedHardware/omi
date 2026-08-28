import AppKit
import Foundation

/// The one floating panel on screen, and everything about when it is there.
///
/// Every copy card — the offer form assist puts up on its own, and the panels the user
/// asks for out loud — goes through here, because "which card is on screen" is one
/// question and answering it in two places is how a card ends up outliving the thing it
/// was about. A panel belongs to a `PanelContext`: leave that context and it goes, come
/// back and it returns, and it never survives into a tab that knows nothing about it.
@MainActor
enum PanelSession {
  /// Who asked for the panel. An offer nobody asked for may be replaced by one somebody
  /// did; the reverse must never happen.
  enum Origin: Sendable {
    case ambient
    case requested
  }

  private struct Panel {
    var title: String
    var subtitle: String
    var fields: [CloudConnectorCopyField]
    let grain: PanelContext.Grain
    /// The form this panel answered, so a sweep can tell whether it is still on screen.
    /// Only form panels have one — a draft panel must never be tested by re-running the
    /// compose gate, which refuses a box the user has already pasted into.
    let formFingerprint: String?
    let origin: Origin
    let autoDismissAfter: TimeInterval?
  }

  private static let watcherID = "panel-session"

  private static var remembered: Panel?
  private static var owner: PanelContext?
  private static var showing = false
  private static var cancelWork: (() -> Void)?
  /// The last app that was not Omi. A panel is presented from a voice turn, and Omi's own
  /// voice UI can hold focus at that moment — without this the panel would be born with
  /// no owner and never leave.
  private static var lastForeignApp: NSRunningApplication?
  private static var activationObserver: (any NSObjectProtocol)?

  // MARK: - State

  /// True while a panel of ours is the window on screen.
  static var isPresenting: Bool {
    showing && CloudConnectorGuidanceOverlay.shared.isPresenting
  }

  /// The form whose answers are on screen, if any. Lets the periodic scan see that this
  /// exact form is already answered without rebuilding the card underneath the user.
  static func isShowingForm(_ fingerprint: String) -> Bool {
    isPresenting && remembered?.formFingerprint == fingerprint
  }

  /// Whether an unrequested offer may take the screen right now.
  static var canPresentAmbient: Bool {
    guard isPresenting else { return !CloudConnectorGuidanceOverlay.shared.isPresenting }
    return remembered?.origin == .ambient
  }

  // MARK: - Presenting

  static func present(
    title: String,
    subtitle: String,
    fields: [CloudConnectorCopyField],
    grain: PanelContext.Grain,
    origin: Origin,
    formFingerprint: String? = nil,
    autoDismissAfter: TimeInterval? = nil,
    onCancel: (() -> Void)? = nil
  ) {
    cancelWork?()
    remembered = Panel(
      title: title, subtitle: subtitle, fields: fields, grain: grain,
      formFingerprint: formFingerprint, origin: origin, autoDismissAfter: autoDismissAfter)
    owner = currentContext()
    cancelWork = onCancel
    startWatching()
    show()
  }

  /// Fill in what the panel is showing without rebuilding it — the window, and wherever
  /// the user dragged it, both survive. The remembered copy is updated too, so a panel
  /// hidden mid-flight comes back finished rather than still spinning.
  static func update(
    title: String? = nil, subtitle: String? = nil, fields: [CloudConnectorCopyField]? = nil
  ) {
    guard var panel = remembered else { return }
    if let title { panel.title = title }
    if let subtitle { panel.subtitle = subtitle }
    if let fields { panel.fields = fields }
    remembered = panel
    guard isPresenting else { return }
    CloudConnectorGuidanceOverlay.shared.updateFieldCopyCard(
      title: panel.title, subtitle: panel.subtitle, fields: panel.fields)
  }

  /// Put the remembered panel back up, wherever the user is now, and let that context own
  /// it from here. This is "show that again" — and the only way back to a form or draft
  /// panel, whose content cost a model call the user should not pay twice.
  @discardableResult
  static func reopen() -> Int? {
    guard let remembered else { return nil }
    owner = currentContext()
    show()
    return remembered.fields.count
  }

  /// Takes the panel down for good and stops whatever was filling it in.
  @discardableResult
  static func dismiss() -> Bool {
    let wasShowing = isPresenting
    if wasShowing { CloudConnectorGuidanceOverlay.shared.dismiss() }
    forget()
    return wasShowing
  }

  /// Take down a panel only if it is the one described. Used by a surface retiring its
  /// own card without reaching across and closing somebody else's.
  static func dismissForm(_ fingerprint: String) {
    guard remembered?.formFingerprint == fingerprint else { return }
    dismiss()
  }

  // MARK: - Context binding

  private static func startWatching() {
    // Two channels, two jobs: the raw one takes the panel away the instant the context
    // changes, the settled one does the work that costs a tree walk.
    FormWatcher.shared.subscribeImmediate(watcherID) { PanelSession.followContext(thorough: false) }
    FormWatcher.shared.subscribe(watcherID) { _ in PanelSession.followContext(thorough: true) }
  }

  /// Hide on the way out, re-present on the way back, and forget once what the panel
  /// answered is gone. Re-presenting rather than parking the window keeps this to one
  /// overlay claim: if something else took the screen while the user was away, it keeps
  /// it, and the panel returns only when the screen is free again.
  private static func followContext(thorough: Bool) {
    guard let panel = remembered, let owner else { return }
    // Omi's own windows are not a switch away: the panel takes clicks without activating
    // the app, and a nil front context must not read as "the user left".
    guard let front = PanelContext.front(resolvePageURL: thorough) else { return }
    guard front.matches(owner, grain: panel.grain, comparingPageURL: thorough) else {
      guard isPresenting else { return }
      CloudConnectorGuidanceOverlay.shared.dismiss()
      showing = false
      return
    }
    // Back in the right place — but a form panel is only right while its form is still
    // there. Submitting the form changes which fields the window has; filling one in
    // does not, so copying from the panel never takes the panel away. The scan is a full
    // tree walk, so it belongs on the settled channel and nowhere near every AX event.
    if thorough, let fingerprint = panel.formFingerprint,
      FormFieldScanner.scanFrontmostWindow()?.fingerprint != fingerprint
    {
      dismiss()
      return
    }
    guard !isPresenting, !CloudConnectorGuidanceOverlay.shared.isPresenting else { return }
    show()
  }

  private static func show() {
    guard let panel = remembered else { return }
    let visibleFrame = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame
    let maxHeight = visibleFrame.map(FormAssistCardPlacement.maxCardHeight(visibleFrame:))
    let overlay = CloudConnectorGuidanceOverlay.shared
    let size = overlay.fieldCopyCardSize(
      title: panel.title,
      subtitle: panel.subtitle,
      fieldCount: panel.fields.count,
      maxHeight: maxHeight,
      wrappedCharacterCounts: panel.fields.filter(\.wraps).map(\.value.count)
    )
    showing = true
    overlay.presentFieldCopyCard(
      title: panel.title,
      subtitle: panel.subtitle,
      fields: panel.fields,
      near: nil,
      at: visibleFrame.map {
        FormAssistCardPlacement.frame(
          cardSize: size, visibleFrame: $0, offset: PanelPlacementStore.offset)
      },
      maxHeight: maxHeight,
      autoDismissAfter: panel.autoDismissAfter,
      remembersPosition: true,
      // ✗ is the user closing this panel, not the overlay being reused for something
      // else — the difference between forgetting the panel and merely hiding it.
      onUserDismiss: { PanelSession.forget() }
    )
  }

  private static func forget() {
    cancelWork?()
    cancelWork = nil
    remembered = nil
    owner = nil
    showing = false
    FormWatcher.shared.unsubscribe(watcherID)
    FormWatcher.shared.unsubscribeImmediate(watcherID)
  }

  /// The context a panel opened now belongs to. Falls back to the last app that was not
  /// Omi, because a voice-requested panel is created while Omi's own UI may hold focus.
  private static func currentContext() -> PanelContext? {
    trackForegroundApp()
    if let front = PanelContext.front() { return front }
    return lastForeignApp.map { PanelContext.of(app: $0) }
  }

  /// One workspace observer, no accessibility work: it only has to remember which app
  /// was in front before Omi took focus.
  private static func trackForegroundApp() {
    if let current = NSWorkspace.shared.frontmostApplication,
      current.processIdentifier != ProcessInfo.processInfo.processIdentifier
    {
      lastForeignApp = current
    }
    guard activationObserver == nil else { return }
    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
    ) { _ in
      MainActor.assumeIsolated {
        guard let app = NSWorkspace.shared.frontmostApplication,
          app.processIdentifier != ProcessInfo.processInfo.processIdentifier
        else { return }
        lastForeignApp = app
      }
    }
  }
}
