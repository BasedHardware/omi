import Cocoa
import SwiftUI

/// The composer's scroll view, which owns **when the caret lands in this editor**.
///
/// SwiftUI's `@FocusState` cannot reach inside an `NSViewRepresentable` — `.focused()` on this editor
/// binds to nothing — so a host that wants the caret has to ask for it, and a claim made before the
/// view has a window has to be remembered rather than dropped (`makeNSView` runs before the hierarchy
/// is attached, which is exactly when a freshly presented composer makes its first claim).
private final class ComposerScrollView: NSScrollView {
  /// A claim that arrived before there was a window to claim in.
  var hasPendingFocusClaim = false
  /// `focusOnAppear` call sites also bring their window forward on that first claim. A host driving
  /// `focusRequest` never does: moving the caret is not the same as summoning a window.
  var activatesWindowOnClaim = false

  func claimFirstResponder() {
    guard let window, let textView = documentView as? NSTextView else {
      hasPendingFocusClaim = true
      return
    }
    hasPendingFocusClaim = false
    if activatesWindowOnClaim {
      activatesWindowOnClaim = false
      window.makeKeyAndOrderFront(nil)
    }
    guard window.firstResponder !== textView else { return }
    window.makeFirstResponder(textView)
  }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    guard hasPendingFocusClaim, window != nil else { return }
    DispatchQueue.main.async { [weak self] in self?.claimFirstResponder() }
  }
}

/// What `⏎` means in a composer.
///
/// A value because the coordinator reads the modifier from `NSApp.currentEvent`, which no hermetic
/// test can stage — so "Shift-Return writes a newline, Return sends, and neither happens mid-IME"
/// would otherwise be a rule nothing checks.
package enum OmiComposerReturnKey: Equatable, Sendable {
  /// Let the text view insert the newline itself.
  case newline
  /// Hand the composer's text to its host.
  case submit

  package static func resolve(hasMarkedText: Bool, shiftHeld: Bool) -> Self {
    // Return mid-composition commits the IME candidate; it is never the composer's key.
    hasMarkedText || shiftHeld ? .newline : .submit
  }
}

/// NSTextView subclass that reports IME marked-text composition state.
private class OmiNSTextView: NSTextView {
  var onMarkedTextStatusChange: ((Bool) -> Void)?
  /// See `OmiTextEditor.onFileDrop`.
  var onFileDrop: ((URL) -> Void)?
  /// See `OmiTextEditor.onFileDragTargeted`.
  var onFileDragTargeted: ((Bool) -> Void)?

  private var handlesFileDrops: Bool { onFileDrop != nil }

  /// Handling the drag here, rather than leaving it to a SwiftUI `.onDrop` layered behind, is what
  /// makes the *whole* editor a drop target: the text view covers that layer, so without this only
  /// the few points of padding around it ever saw a file — and dropping on the text itself made
  /// AppKit insert the file's path.
  override func draggingEntered(_ sender: any NSDraggingInfo) -> NSDragOperation {
    guard handlesFileDrops, OmiTextEditor.dragCarriesFile(sender.draggingPasteboard) else {
      return super.draggingEntered(sender)
    }
    onFileDragTargeted?(true)
    return .copy
  }

  // The host draws the drop highlight, and it has no other way to know a drag is over the text: the
  // SwiftUI `.onDrop` behind this view only ever sees the padding around it.
  override func draggingExited(_ sender: (any NSDraggingInfo)?) {
    onFileDragTargeted?(false)
    super.draggingExited(sender)
  }

  override func draggingEnded(_ sender: any NSDraggingInfo) {
    onFileDragTargeted?(false)
    super.draggingEnded(sender)
  }

  override func draggingUpdated(_ sender: any NSDraggingInfo) -> NSDragOperation {
    guard handlesFileDrops, OmiTextEditor.dragCarriesFile(sender.draggingPasteboard) else {
      return super.draggingUpdated(sender)
    }
    return .copy
  }

  override func performDragOperation(_ sender: any NSDraggingInfo) -> Bool {
    guard let onFileDrop, OmiTextEditor.dragCarriesFile(sender.draggingPasteboard) else {
      return super.performDragOperation(sender)
    }
    onFileDragTargeted?(false)
    guard
      let url = sender.draggingPasteboard.readObjects(
        forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true])?.first as? URL
    else { return false }
    onFileDrop(url)
    return true
  }

  /// AppKit re-registers a text view's default dragged types when it joins a window, so the
  /// registration must be re-asserted there rather than once at construction.
  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    guard handlesFileDrops else { return }
    registerForDraggedTypes([.fileURL])
  }

  override func setMarkedText(_ string: Any, selectedRange: NSRange, replacementRange: NSRange) {
    super.setMarkedText(string, selectedRange: selectedRange, replacementRange: replacementRange)
    publishMarkedTextStatus()
  }

  override func unmarkText() {
    super.unmarkText()
    publishMarkedTextStatus()
  }

  override func insertText(_ string: Any, replacementRange: NSRange) {
    super.insertText(string, replacementRange: replacementRange)
    publishMarkedTextStatus()
  }

  private func publishMarkedTextStatus() {
    onMarkedTextStatusChange?(hasMarkedText())
  }
}

/// Unified NSTextView wrapper used by both the main chat input and the floating control bar.
package struct OmiTextEditor: NSViewRepresentable {
  @Binding var text: String

  // Appearance
  var fontSize: CGFloat = 13
  var textColor: NSColor = .white
  var lineFragmentPadding: CGFloat = 0
  var textContainerInset: NSSize = NSSize(width: 0, height: 8)

  // Behavior
  var onSubmit: (() -> Void)? = nil
  var focusOnAppear: Bool = true
  var onMarkedTextChange: ((Bool) -> Void)? = nil
  /// Monotonic caret claim: **every increment puts the caret in this editor.** The `@FocusState`
  /// equivalent for an `NSViewRepresentable`, and deliberately a counter rather than a `Bool` — a flag
  /// that is already `true` cannot ask for the caret back after AppKit gave it to something else.
  var focusRequest: Int = 0
  /// Receive files dropped anywhere on the editor. Set this and AppKit's own handling — which
  /// inserts the dropped file's *path* — is replaced by this callback for file drags; text drags
  /// are untouched. Leave it nil and the editor behaves exactly as AppKit intends.
  var onFileDrop: ((URL) -> Void)? = nil
  /// Whether a file drag is currently over the editor, so the host can draw the same highlight it
  /// draws for the padding around it.
  var onFileDragTargeted: ((Bool) -> Void)? = nil

  // Optional height tracking (for floating bar's window resize flow)
  var minHeight: CGFloat? = nil
  var maxHeight: CGFloat? = nil
  var onHeightChange: ((CGFloat) -> Void)? = nil

  package init(
    text: Binding<String>,
    fontSize: CGFloat = 13,
    textColor: NSColor = .white,
    lineFragmentPadding: CGFloat = 0,
    textContainerInset: NSSize = NSSize(width: 0, height: 8),
    onSubmit: (() -> Void)? = nil,
    focusOnAppear: Bool = true,
    onMarkedTextChange: ((Bool) -> Void)? = nil,
    focusRequest: Int = 0,
    onFileDrop: ((URL) -> Void)? = nil,
    onFileDragTargeted: ((Bool) -> Void)? = nil,
    minHeight: CGFloat? = nil,
    maxHeight: CGFloat? = nil,
    onHeightChange: ((CGFloat) -> Void)? = nil
  ) {
    self._text = text
    self.fontSize = fontSize
    self.textColor = textColor
    self.lineFragmentPadding = lineFragmentPadding
    self.textContainerInset = textContainerInset
    self.onSubmit = onSubmit
    self.focusOnAppear = focusOnAppear
    self.onMarkedTextChange = onMarkedTextChange
    self.focusRequest = focusRequest
    self.onFileDrop = onFileDrop
    self.onFileDragTargeted = onFileDragTargeted
    self.minHeight = minHeight
    self.maxHeight = maxHeight
    self.onHeightChange = onHeightChange
  }

  /// Whether a drag is carrying files rather than text. An editor that refuses file drops declines
  /// exactly these, so the `.onDrop` layered above it receives them and can read their contents;
  /// left to AppKit, NSTextView accepts the drag itself and inserts the file's *path*.
  package static func dragCarriesFile(_ pasteboard: NSPasteboard) -> Bool {
    pasteboard.canReadObject(
      forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true])
  }

  package func makeNSView(context: Context) -> NSScrollView {
    let textView = OmiNSTextView()
    textView.font = .systemFont(ofSize: fontSize)
    textView.textColor = textColor
    textView.backgroundColor = .clear
    textView.drawsBackground = false
    textView.isRichText = false
    textView.allowsUndo = true
    textView.isAutomaticQuoteSubstitutionEnabled = false
    textView.isAutomaticDashSubstitutionEnabled = false
    textView.isAutomaticTextReplacementEnabled = false
    textView.delegate = context.coordinator
    textView.onFileDrop = onFileDrop
    textView.onFileDragTargeted = onFileDragTargeted
    textView.onMarkedTextStatusChange = { [weak coordinator = context.coordinator] hasMarkedText in
      coordinator?.updateMarkedTextState(hasMarkedText)
    }

    textView.textContainer?.lineFragmentPadding = lineFragmentPadding
    textView.textContainerInset = textContainerInset
    textView.textContainer?.widthTracksTextView = true
    textView.isVerticallyResizable = true
    textView.isHorizontallyResizable = false
    textView.autoresizingMask = [.width]
    textView.maxSize = NSSize(
      width: CGFloat.greatestFiniteMagnitude,
      height: CGFloat.greatestFiniteMagnitude
    )

    let scrollView = ComposerScrollView()
    scrollView.hasPendingFocusClaim = focusOnAppear
    scrollView.activatesWindowOnClaim = focusOnAppear

    scrollView.documentView = textView
    scrollView.hasVerticalScroller = true
    scrollView.hasHorizontalScroller = false
    scrollView.autohidesScrollers = true
    scrollView.backgroundColor = .clear
    scrollView.drawsBackground = false
    scrollView.borderType = .noBorder

    return scrollView
  }

  package func updateNSView(_ scrollView: NSScrollView, context: Context) {
    guard let textView = scrollView.documentView as? NSTextView else { return }

    // Keep the coordinator's binding fresh so textDidChange writes to the
    // correct task's draftText when SwiftUI reuses this NSView across tasks.
    context.coordinator.updateTextBinding($text)
    (textView as? OmiNSTextView)?.onFileDrop = onFileDrop
    (textView as? OmiNSTextView)?.onFileDragTargeted = onFileDragTargeted

    if textView.string != text, !textView.hasMarkedText() {
      context.coordinator.isUpdating = true
      textView.string = text
      context.coordinator.isUpdating = false

      // Force layout so NSScrollView knows the new content size
      // (needed for programmatic text changes to show scrollbar)
      if let layoutManager = textView.layoutManager,
        let textContainer = textView.textContainer
      {
        layoutManager.ensureLayout(for: textContainer)
      }

      // When text is cleared (e.g. after submit), scroll back to the top
      // so the empty input isn't left in a scrolled-down position.
      if text.isEmpty {
        textView.scrollRangeToVisible(NSRange(location: 0, length: 0))
      }

      if onHeightChange != nil {
        context.coordinator.updateHeight(for: textView, scrollView: scrollView)
      }

      // Re-focus the text view when content changes programmatically
      // (e.g. switching between task chats reuses this NSView).
      // Guard: skip if the text view already has focus to avoid a
      // focus-thrash loop with SwiftUI's SelectionOverlay.
      if focusOnAppear, let window = scrollView.window,
        window.firstResponder !== textView
      {
        DispatchQueue.main.async {
          guard window.firstResponder !== textView else { return }
          window.makeFirstResponder(textView)
        }
      }
    }

    // Keep closures fresh so they capture the latest SwiftUI state
    context.coordinator.onSubmit = onSubmit
    context.coordinator.onMarkedTextChange = onMarkedTextChange

    let newFont = NSFont.systemFont(ofSize: fontSize)
    if textView.font != newFont {
      textView.font = newFont
    }

    // A raised claim is honoured once, from whichever host raised it.
    if focusRequest != context.coordinator.lastFocusRequest {
      context.coordinator.lastFocusRequest = focusRequest
      (scrollView as? ComposerScrollView)?.claimFirstResponder()
    }

    context.coordinator.updateMarkedTextState(textView.hasMarkedText())
  }

  /// Return a concrete size to SwiftUI's layout engine so it doesn't have to
  /// recurse through the parent hierarchy to infer the editor's height.
  /// Without this, NSViewRepresentable reports no intrinsic size and SwiftUI
  /// keeps propagating unconstrained proposals upward, contributing to the
  /// recursive StackLayout sizing loop seen in the task chat panel.
  package func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
    guard let minH = minHeight, let maxH = maxHeight else {
      return nil  // no height tracking — let SwiftUI use default NSView sizing
    }
    guard let textView = nsView.documentView as? NSTextView,
      let layoutManager = textView.layoutManager,
      let textContainer = textView.textContainer
    else {
      return CGSize(width: proposal.width ?? nsView.bounds.width, height: minH)
    }
    layoutManager.ensureLayout(for: textContainer)
    let usedRect = layoutManager.usedRect(for: textContainer)
    let contentHeight = usedRect.height + textView.textContainerInset.height * 2
    var constrainedHeight = min(max(contentHeight, minH), maxH)
    // **Never taller than the room actually offered.** The editor asking for a height and then
    // keeping it when the container has less is how a composer draws the reader's own words outside
    // the panel that is supposed to hold them — the text is a scroll view, so a shorter viewport
    // costs nothing, while overflowing costs the top and bottom lines with no way to reach them.
    // `nil` and infinite proposals are SwiftUI asking what this view *wants*, which is the value
    // above; a zero proposal is a probe, not an offer, so the floor still applies.
    if let proposed = proposal.height, proposed.isFinite {
      constrainedHeight = min(constrainedHeight, max(minH, proposed))
    }
    return CGSize(width: proposal.width ?? nsView.bounds.width, height: constrainedHeight)
  }

  package func makeCoordinator() -> Coordinator {
    Coordinator(
      text: $text,
      onSubmit: onSubmit,
      onMarkedTextChange: onMarkedTextChange,
      minHeight: minHeight,
      maxHeight: maxHeight,
      onHeightChange: onHeightChange
    )
  }

  @MainActor package class Coordinator: NSObject, NSTextViewDelegate {
    @Binding var text: String
    var onSubmit: (() -> Void)?
    var onMarkedTextChange: ((Bool) -> Void)?
    var isUpdating = false
    /// The last caret claim this editor honoured. See `OmiTextEditor.focusRequest`.
    var lastFocusRequest = 0

    func updateTextBinding(_ binding: Binding<String>) {
      _text = binding
    }

    // Height tracking (only used when onHeightChange is provided)
    private let minHeight: CGFloat?
    private let maxHeight: CGFloat?
    private let onHeightChange: ((CGFloat) -> Void)?
    private var lastHeight: CGFloat = 0
    private var lastMarkedTextState = false

    init(
      text: Binding<String>,
      onSubmit: (() -> Void)?,
      onMarkedTextChange: ((Bool) -> Void)?,
      minHeight: CGFloat?,
      maxHeight: CGFloat?,
      onHeightChange: ((CGFloat) -> Void)?
    ) {
      self._text = text
      self.onSubmit = onSubmit
      self.onMarkedTextChange = onMarkedTextChange
      self.minHeight = minHeight
      self.maxHeight = maxHeight
      self.onHeightChange = onHeightChange
    }

    package func textDidChange(_ notification: Notification) {
      guard !isUpdating, let textView = notification.object as? NSTextView else { return }
      self.text = textView.string

      if onHeightChange != nil, let scrollView = textView.enclosingScrollView {
        updateHeight(for: textView, scrollView: scrollView)
      }

      updateMarkedTextState(textView.hasMarkedText())
    }

    package func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
      guard commandSelector == #selector(NSResponder.insertNewline(_:)) else { return false }
      let key = OmiComposerReturnKey.resolve(
        hasMarkedText: textView.hasMarkedText(),
        shiftHeld: NSApp.currentEvent?.modifierFlags.contains(.shift) ?? false)
      guard key == .submit else { return false }
      onSubmit?()
      return true
    }

    func updateHeight(for textView: NSTextView, scrollView: NSScrollView) {
      guard let onHeightChange = onHeightChange,
        let minH = minHeight, let maxH = maxHeight,
        let layoutManager = textView.layoutManager,
        let textContainer = textView.textContainer
      else { return }

      layoutManager.ensureLayout(for: textContainer)
      let usedRect = layoutManager.usedRect(for: textContainer)
      let contentHeight = usedRect.height + textView.textContainerInset.height * 2
      let constrainedHeight = min(max(contentHeight, minH), maxH)

      if abs(constrainedHeight - lastHeight) > 1 {
        lastHeight = constrainedHeight
        onHeightChange(constrainedHeight)
      }
    }

    func updateMarkedTextState(_ hasMarkedText: Bool) {
      guard hasMarkedText != lastMarkedTextState else { return }
      lastMarkedTextState = hasMarkedText
      Task { @MainActor [weak self] in
        guard self?.lastMarkedTextState == hasMarkedText else { return }
        self?.onMarkedTextChange?(hasMarkedText)
      }
    }
  }
}
