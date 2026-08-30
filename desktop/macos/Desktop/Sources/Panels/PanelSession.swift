import AppKit
import Foundation

/// The one floating panel on screen, and everything about when it is there.
///
/// Every card — the offer form assist puts up on its own, the message draft, the panels
/// the user asks for out loud, the cloud-connector setup values — goes through here,
/// because "which card is on screen" is one question and answering it in two places is
/// how a card ends up outliving the thing it was about, or drawn over by another. A panel
/// belongs to a `PanelContext`: leave that context and it goes, come back and it returns,
/// and it never survives into a tab that knows nothing about it.
///
/// Two kinds of card exist and they render in different windows — a copy card of values,
/// and the draft card, which takes keystrokes. This owns *which one is up and for how
/// long*; each presenter still owns its own pixels.
@MainActor
enum PanelSession {
  /// Who asked for the panel. An offer nobody asked for may be replaced by one somebody
  /// did; the reverse must never happen.
  enum Origin: Sendable {
    case ambient
    case requested
  }

  /// What the panel is showing, and therefore which window draws it.
  enum Content {
    case copy(Copy)
    case compose(Compose)

    struct Copy {
      var title: String
      var subtitle: String
      /// Sections, not a flat list, because the connector setup card groups values
      /// behind an advanced disclosure. A card with no grouping is one untitled
      /// section, which is exactly what the overlay's own field API builds.
      var sections: [CloudConnectorCopySection]
      var fields: [CloudConnectorCopyField] {
        CloudConnectorCopySection.flattenedFields(sections)
      }
      var autoDismissAfter: TimeInterval?
      /// Set while the panel is still an offer nothing has been spent on. Answering it
      /// clears this, which is also what stops the offer's countdown.
      var ask: CopyCardAsk?
    }

    struct Compose {
      let appDisplayName: String
      let targetWindowFrame: CGRect?
      let onGenerate: (String, MessageDraft?) async -> Result<MessageDraft, Error>
      let onDecline: () -> Void
      /// The draft as it stands, so hiding the panel on a context change and bringing it
      /// back does not throw away a model call the user already paid for.
      var draft: MessageDraft?
    }
  }

  /// Names one panel from the moment it goes up.
  ///
  /// Work that fills a panel takes seconds, and the user can ask for a different one
  /// while it runs. The caller carries the token of the panel it started for, so a late
  /// answer — or a late failure closing the card — reaches that panel or nothing, never
  /// whatever replaced it.
  struct Token: Equatable, Sendable {
    fileprivate let value: Int
  }

  private struct Panel {
    var content: Content
    let grain: PanelContext.Grain
    /// The form this panel answered, so a sweep can tell whether it is still on screen.
    /// Only form panels have one — a draft panel must never be tested by re-running the
    /// compose gate, which refuses a box the user has already pasted into.
    let formFingerprint: String?
    var origin: Origin
    /// When this panel's own countdown runs out. Held here rather than in the window so
    /// hiding the card on a context change and bringing it back resumes the countdown
    /// instead of restarting it — a card the user keeps tabbing past would otherwise
    /// never expire.
    var expiresAt: Date?
    /// False for a card that is a procedure the user is working through rather than
    /// content Omi wrote: the assisted connector setup. Overwriting it by voice would
    /// destroy steps only the user can get back, and its values are configuration, not
    /// something worth keeping in the chat transcript.
    let editable: Bool
  }

  private static let watcherID = "panel-session"

  /// Finished content of panels the user asked for, waiting for the next chat write to
  /// carry it. A panel leaves with its context; the chat transcript is where what it
  /// held survives.
  private struct ChatRecord {
    var title: String
    var fields: [CloudConnectorCopyField]
    /// Last time this record changed. A voice turn is the only thing that drains the
    /// queue, and a panel bought with the ✓ on an ambient offer may never be followed by
    /// one — so a record waits, but not indefinitely, or it lands under an unrelated
    /// reply hours later.
    var at: Date
  }
  private static var chatRecords: [ChatRecord] = []
  /// Index of the record the live panel keeps updated, so content that streams in
  /// after presentation still reaches the transcript.
  private static var liveChatRecordIndex: Int?
  private static let maxChatRecords = 3
  /// Long enough to cover a panel that streams in and a reply that follows it; short
  /// enough that it is still the same piece of work.
  private static let chatRecordLifetime: TimeInterval = 600

  private static var remembered: Panel?
  private static var nextTokenValue = 0
  private static var token = Token(value: 0)
  /// The panel on screen right now, for work that will need to name it later.
  static var currentToken: Token { token }
  private static var owner: PanelContext?
  private static var showing = false
  private static var cancelWork: (() -> Void)?
  /// The user's ✗, and only theirs. `cancelWork` also runs when something else takes the
  /// panel down; a surface that must not offer this again needs the narrower signal.
  private static var userDismiss: (() -> Void)?
  /// The countdown ran out with the user neither accepting nor closing it. Distinct from
  /// `userDismiss`, because ignoring an offer is not the same as saying no to it — but a
  /// surface that offered once and was ignored still needs to know.
  private static var expired: (() -> Void)?
  /// The last app that was not Omi. A panel is presented from a voice turn, and Omi's own
  /// voice UI can hold focus at that moment — without this the panel would be born with
  /// no owner and never leave.
  private static var lastForeignApp: NSRunningApplication?
  private static var activationObserver: (any NSObjectProtocol)?

  // MARK: - State

  /// True while a panel of ours is the window on screen.
  static var isPresenting: Bool {
    guard showing, let panel = remembered else { return false }
    switch panel.content {
    case .copy: return CloudConnectorGuidanceOverlay.shared.isPresenting
    case .compose: return MessageDraftCardController.shared.isPresenting
    }
  }

  /// The form whose answers are on screen, if any. Lets the periodic scan see that this
  /// exact form is already answered without rebuilding the card underneath the user.
  static func isShowingForm(_ fingerprint: String) -> Bool {
    isPresenting && remembered?.formFingerprint == fingerprint
  }

  /// True while the panel on screen is still an offer nobody has answered.
  static var isAsking: Bool {
    guard isPresenting, case .copy(let copy) = remembered?.content else { return false }
    return copy.ask != nil
  }

  /// Whether an unrequested offer may take the screen right now.
  ///
  /// Both windows count. Checking only one is how a form offer ended up drawing over a
  /// live draft card: each surface guarded its own overlay and neither guarded the other.
  static var canPresentAmbient: Bool {
    guard isPresenting else { return !anyCardOnScreen }
    return remembered?.origin == .ambient
  }

  private static var anyCardOnScreen: Bool {
    CloudConnectorGuidanceOverlay.shared.isPresenting
      || MessageDraftCardController.shared.isPresenting
  }

  // MARK: - Presenting

  @discardableResult
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
    onUserDismiss: (() -> Void)? = nil,
    onExpire: (() -> Void)? = nil
  ) -> Token {
    present(
      sections: [CloudConnectorCopySection(id: "fields", title: "", fields: fields)],
      title: title, subtitle: subtitle, grain: grain, origin: origin,
      formFingerprint: formFingerprint, autoDismissAfter: autoDismissAfter, ask: ask,
      onCancel: onCancel, onUserDismiss: onUserDismiss, onExpire: onExpire)
  }

  /// A copy card whose values are grouped — the cloud-connector setup card, whose
  /// provider form hides some fields behind a disclosure.
  @discardableResult
  static func present(
    sections: [CloudConnectorCopySection],
    title: String,
    subtitle: String,
    grain: PanelContext.Grain,
    origin: Origin,
    formFingerprint: String? = nil,
    autoDismissAfter: TimeInterval? = nil,
    ask: CopyCardAsk? = nil,
    editable: Bool = true,
    onCancel: (() -> Void)? = nil,
    onUserDismiss: (() -> Void)? = nil,
    onExpire: (() -> Void)? = nil
  ) -> Token {
    present(
      content: .copy(
        Content.Copy(
          title: title, subtitle: subtitle, sections: sections,
          autoDismissAfter: autoDismissAfter, ask: ask)),
      grain: grain, origin: origin, formFingerprint: formFingerprint, editable: editable,
      onCancel: onCancel, onUserDismiss: onUserDismiss, onExpire: onExpire)
  }

  /// Put up the draft card. Same ownership rules as a copy card: it belongs to the
  /// conversation it opened over, and this decides when it leaves.
  @discardableResult
  static func presentCompose(
    fingerprint: String,
    appDisplayName: String,
    targetWindowFrame: CGRect?,
    restore: MessageDraft?,
    origin: Origin,
    onGenerate: @escaping (String, MessageDraft?) async -> Result<MessageDraft, Error>,
    onDecline: @escaping () -> Void
  ) -> Token {
    present(
      content: .compose(
        Content.Compose(
          appDisplayName: appDisplayName, targetWindowFrame: targetWindowFrame,
          onGenerate: onGenerate, onDecline: onDecline, draft: restore)),
      grain: .context, origin: origin, formFingerprint: nil, composeFingerprint: fingerprint,
      onUserDismiss: onDecline)
  }

  /// The compose card's own fingerprint, kept apart from `formFingerprint` because the
  /// liveness sweep must never re-run the compose gate — it refuses a box the user has
  /// already pasted into, which would take the card away for succeeding.
  private static var composeFingerprint: String?

  /// True while the draft card for exactly this conversation is up.
  static func isShowingCompose(_ fingerprint: String) -> Bool {
    isPresenting && composeFingerprint == fingerprint
  }

  @discardableResult
  private static func present(
    content: Content,
    grain: PanelContext.Grain,
    origin: Origin,
    formFingerprint: String?,
    composeFingerprint: String? = nil,
    editable: Bool = true,
    onCancel: (() -> Void)? = nil,
    onUserDismiss: (() -> Void)? = nil,
    onExpire: (() -> Void)? = nil
  ) -> Token {
    cancelWork?()
    hideCurrent()
    let lifetime: TimeInterval?
    if case .copy(let copy) = content { lifetime = copy.autoDismissAfter } else { lifetime = nil }
    remembered = Panel(
      content: content, grain: grain, formFingerprint: formFingerprint, origin: origin,
      expiresAt: lifetime.map { Date().addingTimeInterval($0) }, editable: editable)
    nextTokenValue += 1
    token = Token(value: nextTokenValue)
    self.composeFingerprint = composeFingerprint
    if origin == .requested, editable { beginChatRecord() } else { liveChatRecordIndex = nil }
    owner = currentContext()
    cancelWork = onCancel
    userDismiss = onUserDismiss
    expired = onExpire
    startWatching()
    show()
    return token
  }

  /// The user took the offer. The ✓ row goes, and with it the countdown an unanswered
  /// offer runs on: what fills the panel from here was asked for, and waiting on it is
  /// not the same as ignoring it.
  ///
  /// It also stops being ambient. A ✓ is the user asking, and everything that follows
  /// from being asked — surviving into the chat transcript, outranking a later offer —
  /// applies to a panel they bought exactly as it does to one they spoke for.
  static func resolveAsk() {
    guard var panel = remembered, case .copy(var copy) = panel.content, copy.ask != nil
    else { return }
    copy.ask = nil
    copy.autoDismissAfter = nil
    panel.expiresAt = nil
    expired = nil
    panel.content = .copy(copy)
    if panel.origin == .ambient {
      panel.origin = .requested
      remembered = panel
      beginChatRecord()
    } else {
      remembered = panel
    }
    CloudConnectorGuidanceOverlay.shared.resolveFieldCopyAsk()
  }

  /// Fill in what the panel is showing without rebuilding it — the window, and wherever
  /// the user dragged it, both survive. The remembered copy is updated too, so a panel
  /// hidden mid-flight comes back finished rather than still spinning.
  static func update(
    title: String? = nil, subtitle: String? = nil, fields: [CloudConnectorCopyField]? = nil,
    forForm fingerprint: String? = nil, token: Token? = nil
  ) {
    guard token == nil || token == self.token else { return }
    guard var panel = remembered, case .copy(var copy) = panel.content else { return }
    // A form's answers take seconds, and another form's offer can take the panel while
    // they are in flight. Naming the form means late work goes nowhere rather than into
    // whatever replaced it.
    guard fingerprint == nil || panel.formFingerprint == fingerprint else { return }
    if let title { copy.title = title }
    if let subtitle { copy.subtitle = subtitle }
    if let fields {
      copy.sections = [CloudConnectorCopySection(id: "fields", title: "", fields: fields)]
    }
    panel.content = .copy(copy)
    remembered = panel
    updateLiveChatRecord(title: title, fields: fields)
    guard isPresenting else { return }
    CloudConnectorGuidanceOverlay.shared.updateFieldCopyCard(
      title: copy.title, subtitle: copy.subtitle, sections: copy.sections)
  }

  /// Put the remembered panel back up, wherever the user is now, and let that context own
  /// it from here. This is "show that again" — and the only way back to a form or draft
  /// panel, whose content cost a model call the user should not pay twice.
  @discardableResult
  static func reopen() -> Int? {
    guard let panel = remembered else { return nil }
    owner = currentContext()
    show()
    guard case .copy(let copy) = panel.content else { return 1 }
    return copy.fields.count
  }

  /// Takes the panel down for good and stops whatever was filling it in.
  @discardableResult
  static func dismiss(token: Token? = nil) -> Bool {
    guard token == nil || token == self.token else { return false }
    let wasShowing = isPresenting
    hideCurrent()
    forget()
    return wasShowing
  }

  /// The panel's own countdown ran out — called by the card's own timer. Forgetting it
  /// is the point: a card left remembered after its window closed comes back on the next
  /// context return, with a fresh countdown, so an offer the user ignored for four
  /// minutes would reappear forever.
  static func expire(_ expiring: Token) {
    guard expiring == token else { return }
    let ignored = expired
    forget()
    ignored?()
  }

  /// Take down a panel only if it is the one described. Used by a surface retiring its
  /// own card without reaching across and closing somebody else's.
  static func dismissForm(_ fingerprint: String) {
    guard remembered?.formFingerprint == fingerprint else { return }
    dismiss()
  }

  static func dismissCompose(_ fingerprint: String) {
    guard composeFingerprint == fingerprint else { return }
    dismiss()
  }

  // MARK: - What the model may see

  /// Enough of a panel to revise it, few enough characters to carry every turn.
  private static let maxModelVisibleLength = 4_000

  /// What the panel is, apart from its text.
  ///
  /// A panel with nothing copyable on it yet is still a panel: an offer waiting on the
  /// user's ✓, or a card whose rows are still spinners. Reporting "nothing is on screen"
  /// for those is the same lie this whole seam exists to stop — the model would offer to
  /// put up what the user is already looking at.
  enum Presence: Equatable {
    case none
    /// Values the user can copy.
    case copy(String)
    /// An offer the user has not answered yet.
    case offer(title: String)
    /// A panel that is still filling in.
    case working(title: String)
    /// The message-draft card, which takes its own edits inline.
    case draft(String?)
  }

  static func presence() -> Presence {
    guard isPresenting, let panel = remembered else { return .none }
    switch panel.content {
    case .compose(let compose):
      return .draft(compose.draft.map(\.body))
    case .copy(let copy):
      if copy.ask != nil { return .offer(title: copy.title) }
      if let content = modelVisibleContent() { return .copy(content) }
      return .working(title: copy.title)
    }
  }

  /// The panel's current contents, for the tool result that lets the model change them.
  ///
  /// A model that cannot see the panel cannot edit it: `draft_message` returned "Draft
  /// is on screen to copy", so "make that shorter" had nothing to shorten and the only
  /// move left was writing a new draft from scratch. Returning the text is what makes
  /// `update_panel` possible.
  ///
  /// Masked values never leave. They are the user's secrets — a connector's API key —
  /// and the panel masks them on screen precisely so they are not read or repeated;
  /// putting them in a tool result would send them to the speech provider instead.
  /// Pending rows are spinners, not content.
  static func modelVisibleContent() -> String? {
    guard let panel = remembered else { return nil }
    let fields: [CloudConnectorCopyField]
    switch panel.content {
    case .copy(let copy): fields = copy.fields
    case .compose(let compose): fields = draftFields(compose.draft)
    }
    let lines =
      fields
      .filter { !$0.isPending && !$0.masksValue }
      .compactMap { field -> String? in
        let value = field.value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        let label = field.label.trimmingCharacters(in: .whitespacesAndNewlines)
        return label.isEmpty ? value : "\(label): \(value)"
      }
    guard !lines.isEmpty else { return nil }
    let joined = lines.joined(separator: "\n")
    let body =
      joined.count > maxModelVisibleLength
      ? String(joined.prefix(maxModelVisibleLength)) + "\u{2026}"
      : joined
    let masked = fields.filter(\.masksValue).count
    return body
      + (masked == 0
        ? ""
        : "\n(\(masked) secret value\(masked == 1 ? "" : "s") on the panel, withheld here.)")
  }

  /// How a requested change to the panel ended.
  enum ReviseOutcome: Equatable {
    /// The panel on screen now holds the new content.
    case revised(Int)
    /// Nothing was on screen, so the content went up as a new panel.
    case created(Int)
    /// The panel on screen is not one to overwrite, and why.
    case refused(String)
  }

  /// Replace what the panel is showing because the user asked for a change.
  ///
  /// Goes through `update` rather than `present`, so the window the user dragged stays
  /// where they put it and the transcript keeps one card for one panel instead of
  /// logging every revision as a new thing.
  ///
  /// With nothing on screen it puts the revision up as a new panel instead of refusing.
  /// A panel leaves the moment its context does, so "make that shorter" routinely
  /// arrives after the card is already gone — and refusing was measured to produce the
  /// worst outcome available: the model said "I've put the shorter note on your screen
  /// now" with nothing there. Whether this is an edit or a first draft is Omi's problem,
  /// not the user's.
  ///
  /// Three panels are refused rather than overwritten, because writing over them would
  /// destroy something only the user can replace: an offer they have not answered (the
  /// ✓ is the permission to spend), a card still filling in (the answer is in flight),
  /// and the draft card (it has its own edit box).
  @discardableResult
  static func revise(title: String?, fields: [CloudConnectorCopyField]) -> ReviseOutcome {
    guard !fields.isEmpty else {
      return .refused("update_panel needs the panel's complete new items.")
    }
    let subtitle = VoicePanel.changeHint
    switch presence() {
    case .none:
      let heading = (title?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap {
        $0.isEmpty ? nil : $0
      }
      present(
        title: heading ?? "For you", subtitle: subtitle, fields: fields, grain: .app,
        origin: .requested)
      return .created(fields.count)
    case .copy:
      // A form's answers cost a model call and cannot be recovered by asking again for
      // free, so overwriting them is refused the way the setup card is. The user can
      // still take the panel down and ask for whatever they wanted instead.
      if let fingerprint = remembered?.formFingerprint, !fingerprint.isEmpty {
        return .refused(
          "The panel on screen holds the answers Omi filled in for the form the user is "
            + "looking at. Do not overwrite them — close_panel first if they want "
            + "something else there.")
      }
      // A setup card is a procedure the user is partway through, and its grouping is
      // part of the instructions. Replacing it with prose destroys both.
      guard remembered?.editable ?? true else {
        return .refused(
          "The card on screen is a setup Omi is walking the user through, not text to "
            + "reword. Leave it alone and tell them so.")
      }
      update(title: title, subtitle: subtitle, fields: fields)
      // The turn that put this panel up already carried its card away. An edit in a later
      // turn is a second thing to keep: without this the transcript holds the text the
      // user asked to change, and the correction never appears anywhere.
      if liveChatRecordIndex == nil { beginChatRecord() }
      return .revised(fields.count)
    case .offer(let heading):
      return .refused(
        "The panel on screen is the unanswered offer \"\(heading)\". Ask the user to tap "
          + "the check on it rather than replacing it.")
    case .working(let heading):
      return .refused(
        "The panel on screen (\"\(heading)\") is still filling in. Wait for it rather than "
          + "replacing it.")
    case .draft:
      return .refused(
        "The message-draft card is on screen and it takes edits in its own box. Tell the "
          + "user to type the change there.")
    }
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
  /// Cleared on read, so a panel lands in exactly one turn. A panel still mid-flight —
  /// pending rows, no values — yields nothing: it was cancelled or empty, and an empty
  /// card is not worth a transcript.
  static func takeChatCards(now: Date = Date()) -> [PanelChatCard] {
    defer {
      chatRecords.removeAll()
      liveChatRecordIndex = nil
    }
    let cutoff = now.addingTimeInterval(-chatRecordLifetime)
    return
      chatRecords
      .filter { $0.at > cutoff }
      .compactMap { chatCard(title: $0.title, fields: $0.fields) }
  }

  private static func beginChatRecord() {
    guard let panel = remembered else { return }
    if chatRecords.count >= maxChatRecords { chatRecords.removeFirst() }
    switch panel.content {
    case .copy(let copy):
      chatRecords.append(ChatRecord(title: copy.title, fields: copy.fields, at: Date()))
    case .compose(let compose):
      chatRecords.append(
        ChatRecord(
          title: "Draft for \(compose.appDisplayName)", fields: draftFields(compose.draft),
          at: Date()))
    }
    liveChatRecordIndex = chatRecords.indices.last
  }

  private static func updateLiveChatRecord(
    title: String?, fields: [CloudConnectorCopyField]?
  ) {
    guard let index = liveChatRecordIndex, chatRecords.indices.contains(index) else { return }
    if let title { chatRecords[index].title = title }
    if let fields { chatRecords[index].fields = fields }
    chatRecords[index].at = Date()
  }

  /// A draft as copyable rows, so the transcript keeps it exactly as the card showed it.
  private static func draftFields(_ draft: MessageDraft?) -> [CloudConnectorCopyField] {
    guard let draft else { return [] }
    var fields: [CloudConnectorCopyField] = []
    if let subject = draft.subject, !subject.isEmpty {
      fields.append(
        CloudConnectorCopyField(
          id: "draft-subject", label: "Subject", value: subject, masksValue: false))
    }
    fields.append(
      CloudConnectorCopyField(
        id: "draft-body", label: "", value: draft.body, masksValue: false, wraps: true))
    return fields
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
      hideCurrent()
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
    guard !isPresenting, !anyCardOnScreen else { return }
    show()
  }

  private static func show() {
    guard let panel = remembered else { return }
    // The countdown keeps running while the card is hidden. Coming back to a context the
    // panel already outlived must not flash it up for its last second.
    if let expiresAt = panel.expiresAt, expiresAt <= Date() {
      expire(token)
      return
    }
    showing = true
    switch panel.content {
    case .copy(let copy): showCopy(copy)
    case .compose(let compose): showCompose(compose)
    }
  }

  private static func showCopy(_ copy: Content.Copy) {
    let visibleFrame = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame
    let maxHeight = visibleFrame.map(FormAssistCardPlacement.maxCardHeight(visibleFrame:))
    let overlay = CloudConnectorGuidanceOverlay.shared
    let size = overlay.fieldCopyCardSize(
      title: copy.title,
      subtitle: copy.subtitle,
      fieldCount: copy.fields.count,
      maxHeight: maxHeight,
      wrappedCharacterCounts: copy.fields.filter(\.wraps).map(\.value.count),
      hasAsk: copy.ask != nil
    )
    overlay.presentFieldCopyCard(
      title: copy.title,
      subtitle: copy.subtitle,
      sections: copy.sections,
      near: nil,
      at: visibleFrame.map {
        FormAssistCardPlacement.frame(
          cardSize: size, visibleFrame: $0, offset: PanelPlacementStore.offset)
      },
      maxHeight: maxHeight,
      // What is left of the countdown, not a fresh one: a card the user keeps tabbing
      // away from and back to must still expire.
      autoDismissAfter: remembered?.expiresAt.map { max(1, $0.timeIntervalSinceNow) },
      remembersPosition: true,
      // The offer's ✓ is answered once, wherever the panel is showing: clear the row
      // first, then hand the user's context to whoever asked.
      ask: copy.ask.map { ask in
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
      },
      onExpire: { [expiring = token] in PanelSession.expire(expiring) }
    )
  }

  private static func showCompose(_ compose: Content.Compose) {
    MessageDraftCardController.shared.present(
      appDisplayName: compose.appDisplayName,
      targetWindowFrame: compose.targetWindowFrame,
      restore: compose.draft,
      // Every draft the card produces is remembered here, so hiding the card on a
      // context change and bringing it back returns the draft rather than the prompt.
      onGenerate: { context, refining in
        let result = await compose.onGenerate(context, refining)
        if case .success(let draft) = result { PanelSession.recordDraft(draft) }
        return result
      },
      onDecline: {
        let declined = PanelSession.userDismiss
        PanelSession.forget()
        declined?()
      }
    )
  }

  private static func recordDraft(_ draft: MessageDraft) {
    guard var panel = remembered, case .compose(var compose) = panel.content else { return }
    compose.draft = draft
    panel.content = .compose(compose)
    remembered = panel
    updateLiveChatRecord(
      title: "Draft for \(compose.appDisplayName)", fields: draftFields(draft))
  }

  /// Take down whichever window is currently drawing the panel, leaving the remembered
  /// content alone. Both are closed rather than just the expected one: a presenter that
  /// somehow held the screen must not survive a switch to the other kind.
  private static func hideCurrent() {
    if CloudConnectorGuidanceOverlay.shared.isPresenting {
      CloudConnectorGuidanceOverlay.shared.dismiss()
    }
    if MessageDraftCardController.shared.isPresenting {
      MessageDraftCardController.shared.dismiss()
    }
  }

  private static func forget() {
    cancelWork?()
    cancelWork = nil
    userDismiss = nil
    expired = nil
    remembered = nil
    composeFingerprint = nil
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
