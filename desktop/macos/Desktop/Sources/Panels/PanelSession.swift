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
    var autoDismissAfter: TimeInterval?
    /// Set while the panel is still an offer nothing has been spent on. Answering it
    /// clears this, which is also what stops the offer's countdown.
    var ask: CopyCardAsk?
  }

  private static let watcherID = "panel-session"

  /// Finished content of panels the user asked for out loud, waiting for the voice
  /// turn's chat write to carry it. A panel leaves with its context; the chat
  /// transcript is where what it held survives.
  private struct ChatRecord {
    var title: String
    var fields: [CloudConnectorCopyField]
  }
  private static var chatRecords: [ChatRecord] = []
  /// Index of the record the live panel keeps updated, so content that streams in
  /// after presentation still reaches the transcript.
  private static var liveChatRecordIndex: Int?
  private static let maxChatRecords = 3

  private static var remembered: Panel?
  private static var owner: PanelContext?
  private static var showing = false
  private static var cancelWork: (() -> Void)?
  /// The user's ✗, and only theirs. `cancelWork` also runs when something else takes the
  /// panel down; a surface that must not offer this again needs the narrower signal.
  private static var userDismiss: (() -> Void)?
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

  /// True while the panel on screen is still an offer nobody has answered.
  static var isAsking: Bool { isPresenting && remembered?.ask != nil }

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
    ask: CopyCardAsk? = nil,
    onCancel: (() -> Void)? = nil,
    onUserDismiss: (() -> Void)? = nil
  ) {
    cancelWork?()
    remembered = Panel(
      title: title, subtitle: subtitle, fields: fields, grain: grain,
      formFingerprint: formFingerprint, origin: origin, autoDismissAfter: autoDismissAfter,
      ask: ask)
    if origin == .requested {
      if chatRecords.count >= maxChatRecords { chatRecords.removeFirst() }
      chatRecords.append(ChatRecord(title: title, fields: fields))
      liveChatRecordIndex = chatRecords.indices.last
    } else {
      liveChatRecordIndex = nil
    }
    owner = currentContext()
    cancelWork = onCancel
    userDismiss = onUserDismiss
    startWatching()
    show()
  }

  /// The user took the offer. The ✓ row goes, and with it the countdown an unanswered
  /// offer runs on: what fills the panel from here was asked for, and waiting on it is
  /// not the same as ignoring it.
  static func resolveAsk() {
    guard var panel = remembered, panel.ask != nil else { return }
    panel.ask = nil
    panel.autoDismissAfter = nil
    remembered = panel
    CloudConnectorGuidanceOverlay.shared.resolveFieldCopyAsk()
  }

  /// Fill in what the panel is showing without rebuilding it — the window, and wherever
  /// the user dragged it, both survive. The remembered copy is updated too, so a panel
  /// hidden mid-flight comes back finished rather than still spinning.
  static func update(
    title: String? = nil, subtitle: String? = nil, fields: [CloudConnectorCopyField]? = nil,
    forForm fingerprint: String? = nil
  ) {
    guard var panel = remembered else { return }
    // A form's answers take seconds, and another form's offer can take the panel while
    // they are in flight. Naming the form means late work goes nowhere rather than into
    // whatever replaced it.
    guard fingerprint == nil || panel.formFingerprint == fingerprint else { return }
    if let title { panel.title = title }
    if let subtitle { panel.subtitle = subtitle }
    if let fields { panel.fields = fields }
    remembered = panel
    if let index = liveChatRecordIndex, chatRecords.indices.contains(index) {
      if let title { chatRecords[index].title = title }
      if let fields { chatRecords[index].fields = fields }
    }
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

  // MARK: - Chat hand-off

  /// A finished panel as the chat will keep it: a collapsible card with the values in
  /// the fold, so the transcript stays readable and the content stays reachable.
  struct PanelChatCard: Sendable, Equatable {
    let title: String
    let summary: String
    let text: String
  }

  /// The finished content of every panel the user asked for since the last call.
  /// Cleared on read, so a panel lands in exactly one voice turn. A panel still
  /// mid-flight — pending rows, no values — yields nothing: it was cancelled or
  /// empty, and an empty card is not worth a transcript.
  static func takeChatCards() -> [PanelChatCard] {
    defer {
      chatRecords.removeAll()
      liveChatRecordIndex = nil
    }
    return chatRecords.compactMap { chatCard(title: $0.title, fields: $0.fields) }
  }

  /// One panel as a card: title on the header, the value names as the always-visible
  /// summary, one line per copyable value in the fold. Pending rows, masked values,
  /// and empty fields never reach the transcript.
  nonisolated static func chatCard(
    title: String, fields: [CloudConnectorCopyField]
  ) -> PanelChatCard? {
    let kept =
      fields
      .filter { !$0.isPending && !$0.masksValue }
      .compactMap { field -> (label: String, value: String)? in
        let value = field.value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        return (label: field.label.trimmingCharacters(in: .whitespacesAndNewlines), value: value)
      }
    guard !kept.isEmpty else { return nil }
    let labels = kept.map(\.label).filter { !$0.isEmpty }
    let summary =
      labels.isEmpty
      ? String(kept[0].value.prefix(while: { !$0.isNewline }))
      : labels.joined(separator: ", ")
    let heading = title.trimmingCharacters(in: .whitespacesAndNewlines)
    return PanelChatCard(
      title: heading.isEmpty ? "Saved from your panel" : heading,
      summary: summary,
      text: kept.map { $0.label.isEmpty ? $0.value : "\($0.label): \($0.value)" }
        .joined(separator: "\n"))
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
      wrappedCharacterCounts: panel.fields.filter(\.wraps).map(\.value.count),
      hasAsk: panel.ask != nil
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
      // The offer's ✓ is answered once, wherever the panel is showing: clear the row
      // first, then hand the user's context to whoever asked.
      ask: panel.ask.map { ask in
        CopyCardAsk(
          placeholder: ask.placeholder,
          confirmLabel: ask.confirmLabel,
          onConfirm: { context in
            PanelSession.resolveAsk()
            ask.onConfirm(context)
          })
      },
      // ✗ is the user closing this panel, not the overlay being reused for something
      // else — the difference between forgetting the panel and merely hiding it.
      onUserDismiss: {
        let declined = PanelSession.userDismiss
        PanelSession.forget()
        declined?()
      }
    )
  }

  private static func forget() {
    cancelWork?()
    cancelWork = nil
    userDismiss = nil
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
