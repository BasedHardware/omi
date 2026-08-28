import AppKit
import OmiTheme
import SwiftUI

/// A drafted message, ready to copy. Email gets a subject; chat does not.
struct MessageDraft: Sendable, Equatable {
  let subject: String?
  let body: String
}

/// What the card is showing right now. One panel walks these in order; refine loops it
/// back through `drafting`.
enum MessageDraftCardState: Equatable {
  case prompt
  case drafting
  case draft(MessageDraft)
  case failed(String)
}

/// The card's geometry, kept pure so placement is testable. Width and the height of
/// every fixed row are the contract; the draft body flexes inside what is left.
enum MessageDraftCardMetrics {
  static let width: CGFloat = 420
  static let headerHeight: CGFloat = 64
  static let inputRowHeight: CGFloat = 46
  static let subjectRowHeight: CGFloat = 30
  static let verticalPadding: CGFloat = 28

  /// Roughly how tall the body text renders at the card's width. An estimate is enough:
  /// the body scrolls when it is wrong, and the cap keeps the card off the conversation
  /// it is about.
  static func bodyHeight(for body: String, maxHeight: CGFloat) -> CGFloat {
    let charactersPerLine = 52.0
    let lineHeight = 17.0
    let lines = body.split(separator: "\n", omittingEmptySubsequences: false)
      .reduce(0.0) { $0 + max(1, (Double($1.count) / charactersPerLine).rounded(.up)) }
    return min(CGFloat(lines * lineHeight) + 16, maxHeight)
  }

  static func size(state: MessageDraftCardState, maxHeight: CGFloat) -> CGSize {
    let fixed = headerHeight + inputRowHeight + verticalPadding
    switch state {
    case .prompt, .drafting:
      return CGSize(width: width, height: fixed)
    case .failed:
      return CGSize(width: width, height: fixed + subjectRowHeight)
    case .draft(let draft):
      let subject: CGFloat = draft.subject == nil ? 0 : subjectRowHeight
      let body = bodyHeight(for: draft.body, maxHeight: max(0, maxHeight - fixed - subject))
      return CGSize(width: width, height: fixed + subject + body)
    }
  }
}

/// A borderless panel that can take keystrokes without activating Omi, which is what
/// lets the user type into "Add context" while their mail client stays the active app.
private final class MessageDraftPanel: NSPanel, AutomationPresentationExemptWindow {
  override var canBecomeKey: Bool { true }
}

/// Owns the one message-draft card on screen: presents it, resizes it as it moves
/// between states, and routes the view's actions back to the assistant.
@MainActor
final class MessageDraftCardController: ObservableObject {
  static let shared = MessageDraftCardController()

  @Published private(set) var state: MessageDraftCardState = .prompt
  private(set) var fingerprint: String?
  private var window: NSPanel?
  private var moveObserver: (any NSObjectProtocol)?
  private var targetWindowFrame: CGRect?
  private var appDisplayName = ""
  private var onGenerate: ((String, MessageDraft?) async -> Result<MessageDraft, Error>)?
  private var onDecline: (() -> Void)?

  var isPresenting: Bool { window != nil }

  private init() {}

  /// Puts up the card — the prompt, or a previous draft when `restore` carries one, so
  /// coming back to a conversation does not forget the work already done. `onGenerate`
  /// is called with what the user typed (possibly empty) and, when refining, the draft
  /// being refined; `onDecline` is the ✗, so the assistant can stop offering this
  /// conversation.
  func present(
    fingerprint: String,
    appDisplayName: String,
    targetWindowFrame: CGRect? = nil,
    restore: MessageDraft? = nil,
    onGenerate: @escaping (String, MessageDraft?) async -> Result<MessageDraft, Error>,
    onDecline: @escaping () -> Void
  ) {
    dismiss()
    self.fingerprint = fingerprint
    self.targetWindowFrame = targetWindowFrame
    self.appDisplayName = appDisplayName
    self.onGenerate = onGenerate
    self.onDecline = onDecline
    state = restore.map { .draft($0) } ?? .prompt

    let view = MessageDraftCardView(controller: self, appDisplayName: appDisplayName)
    let hostingController = NSHostingController(rootView: view)
    let panel = MessageDraftPanel(
      contentRect: CGRect(origin: .zero, size: currentSize()),
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    hostingController.view.frame = CGRect(origin: .zero, size: currentSize())
    panel.contentViewController = hostingController
    WindowGlass.wear(panel, as: .floating)
    panel.level = .popUpMenu
    panel.ignoresMouseEvents = false
    panel.isMovableByWindowBackground = true
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    panel.animationBehavior = .none
    panel.setFrame(placementFrame(size: currentSize()), display: false)
    panel.orderFrontRegardless()
    window = panel
    moveObserver = NotificationCenter.default.addObserver(
      forName: NSWindow.didMoveNotification, object: panel, queue: .main
    ) { [weak panel] _ in
      MainActor.assumeIsolated {
        guard let panel, let visible = panel.screen?.visibleFrame else { return }
        PanelPlacementStore.record(panelFrame: panel.frame, visibleFrame: visible)
      }
    }
  }

  func dismiss() {
    if let moveObserver { NotificationCenter.default.removeObserver(moveObserver) }
    moveObserver = nil
    window?.close()
    window = nil
    fingerprint = nil
    onGenerate = nil
    onDecline = nil
    state = .prompt
  }

  // MARK: - View actions

  func confirm(context: String) {
    let refining: MessageDraft? = {
      guard case .draft(let draft) = state else { return nil }
      return draft
    }()
    guard let onGenerate else { return }
    transition(to: .drafting)
    Task { [weak self] in
      let result = await onGenerate(context, refining)
      await MainActor.run {
        guard let self, self.isPresenting else { return }
        switch result {
        case .success(let draft): self.transition(to: .draft(draft))
        case .failure: self.transition(to: .failed("Couldn't draft that. Try again."))
        }
      }
    }
  }

  func decline() {
    onDecline?()
    dismiss()
  }

  private func transition(to newState: MessageDraftCardState) {
    state = newState
    guard let window else { return }
    // Anchored top-right: keep the top edge still and grow downward, so the card the
    // user is reading does not jump when the draft arrives.
    let size = currentSize()
    let top = window.frame.maxY
    var frame = window.frame
    frame.origin.y = top - size.height
    frame.size = size
    if let visible = placementScreen?.visibleFrame, !visible.contains(frame) {
      frame = FormAssistCardPlacement.frame(cardSize: size, visibleFrame: visible)
    }
    window.setFrame(frame, display: true)
  }

  /// Whatever moved the card off the visible screen — a drag, a display change — the
  /// next sweep puts it back where an offer belongs.
  func ensureVisiblePlacement() {
    guard let window else { return }
    guard let visible = placementScreen?.visibleFrame else { return }
    guard !visible.contains(window.frame) else { return }
    log("MessageDraftCard: re-placing off-screen card from \(window.frame)")
    window.setFrame(placementFrame(size: currentSize()), display: true)
  }

  /// The screen the conversation is on — the card must appear where the user is
  /// looking, which is not always the screen holding the key window.
  private var placementScreen: NSScreen? {
    if let target = targetWindowFrame,
      let best = NSScreen.screens.max(by: {
        $0.frame.intersection(target).height * $0.frame.intersection(target).width
          < $1.frame.intersection(target).height * $1.frame.intersection(target).width
      }), best.frame.intersects(target)
    {
      return best
    }
    return NSScreen.main ?? NSScreen.screens.first
  }

  private func currentSize() -> CGSize {
    let maxHeight =
      placementScreen.map { FormAssistCardPlacement.maxCardHeight(visibleFrame: $0.visibleFrame) }
      ?? 400
    return MessageDraftCardMetrics.size(state: state, maxHeight: maxHeight)
  }

  private func placementFrame(size: CGSize) -> CGRect {
    guard let visible = placementScreen?.visibleFrame else { return CGRect(origin: .zero, size: size) }
    return FormAssistCardPlacement.frame(
      cardSize: size, visibleFrame: visible, offset: PanelPlacementStore.offset)
  }
}

/// The card itself: "Want me to draft?", the context box, and — once the model answers
/// — the draft with its copy buttons, with the context box staying for refinement.
private struct MessageDraftCardView: View {
  @ObservedObject var controller: MessageDraftCardController
  let appDisplayName: String

  @State private var context = ""
  @State private var copiedField: String?
  @FocusState private var contextFocused: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      header
      stateBody
      inputRow
    }
    .padding(.leading, OmiSpacing.lg)
    .padding(.trailing, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .frame(width: MessageDraftCardMetrics.width, alignment: .topLeading)
    .inkGlassPanel()
  }

  private var header: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      ZStack {
        Circle().fill(Ink.primary)
        Image(systemName: "square.and.pencil")
          .scaledFont(size: 15, weight: .bold)
          .foregroundColor(Ink.surface)
      }
      .frame(width: 36, height: 36)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: 13.5, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(subtitle)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
          .lineLimit(2)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 0)
    }
  }

  private var title: String {
    switch controller.state {
    case .prompt: return "Want me to draft?"
    case .drafting: return "Drafting…"
    case .draft: return "Here's a draft"
    case .failed: return "Want me to draft?"
    }
  }

  private var subtitle: String {
    switch controller.state {
    case .prompt:
      return "A message for \(appDisplayName), from what's on screen."
    case .drafting:
      return "Reading the conversation on screen."
    case .draft:
      return "Copy it into \(appDisplayName), or tell me what to change."
    case .failed:
      return "A message for \(appDisplayName), from what's on screen."
    }
  }

  @ViewBuilder
  private var stateBody: some View {
    switch controller.state {
    case .prompt, .drafting:
      EmptyView()
    case .failed(let message):
      Text(message)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
        .frame(height: MessageDraftCardMetrics.subjectRowHeight)
    case .draft(let draft):
      if let subject = draft.subject {
        draftRow(id: "subject", text: subject, lineLimit: 1)
          .frame(height: MessageDraftCardMetrics.subjectRowHeight)
      }
      ScrollView {
        draftRow(id: "body", text: draft.body, lineLimit: nil)
      }
      .scrollBounceBehavior(.basedOnSize)
    }
  }

  private func draftRow(id: String, text: String, lineLimit: Int?) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Text(text)
        .scaledFont(size: 12, weight: .regular)
        .foregroundColor(Ink.primary)
        .lineSpacing(2)
        .lineLimit(lineLimit)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
      copyButton(id: id, text: text)
    }
  }

  private func copyButton(id: String, text: String) -> some View {
    Button {
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(text, forType: .string)
      copiedField = id
      Task {
        try? await Task.sleep(nanoseconds: 1_800_000_000)
        if copiedField == id { copiedField = nil }
      }
    } label: {
      Image(systemName: copiedField == id ? "checkmark" : "doc.on.doc")
        .scaledFont(size: OmiType.micro, weight: .bold)
        .frame(width: 28, height: 22)
        .foregroundColor(copiedField == id ? Ink.listeningGreen : Ink.primary)
        .background(
          Capsule().fill(
            copiedField == id ? Ink.listeningGreen.opacity(0.16) : Ink.rowFillHover)
        )
        .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help(copiedField == id ? "Copied" : "Copy")
    .accessibilityLabel(copiedField == id ? "Copied" : "Copy draft")
  }

  private var inputRow: some View {
    HStack(spacing: OmiSpacing.sm) {
      TextField(placeholder, text: $context)
        .textFieldStyle(.plain)
        .scaledFont(size: 12, weight: .regular)
        .foregroundColor(Ink.primary)
        .focused($contextFocused)
        .disabled(isDrafting)
        .onSubmit(submit)
        .padding(.horizontal, OmiSpacing.md)
        .frame(height: 32)
        .background(
          Capsule().fill(Ink.rowFillHover)
        )

      if isDrafting {
        ProgressView()
          .controlSize(.small)
          .frame(width: 24, height: 24)
      } else {
        actionButton(systemName: "checkmark", accessibilityLabel: confirmLabel, action: submit)
      }
      actionButton(systemName: "xmark", accessibilityLabel: "No thanks") {
        controller.decline()
      }
    }
    .frame(height: 32)
  }

  private var isDrafting: Bool {
    if case .drafting = controller.state { return true }
    return false
  }

  private var placeholder: String {
    if case .draft = controller.state { return "Change something…" }
    return "Add context…"
  }

  private var confirmLabel: String {
    if case .draft = controller.state { return "Redraft" }
    return "Draft it"
  }

  private func submit() {
    guard !isDrafting else { return }
    controller.confirm(context: context)
    context = ""
  }

  private func actionButton(
    systemName: String, accessibilityLabel: String, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      Image(systemName: systemName)
        .scaledFont(size: 11, weight: .bold)
        .foregroundColor(Ink.primary)
        .frame(width: 28, height: 28)
        .background(Circle().fill(Ink.rowFillHover))
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .help(accessibilityLabel)
    .accessibilityLabel(accessibilityLabel)
  }
}
