//
//  QueryHeroBar.swift — the hero: one field that searches, asks, or listens.
//
//  It is the *first* of the surface's two glass objects and it is deliberately not welded to the
//  second. A place you type and a place you look are different in kind; drawn as one tall block with a
//  rule across it they claim to be the same object, and the surface stops reading as search.
//
//  The two keyboard hints are real buttons, not legends. A hint that tells you about a key you could
//  press but does nothing when you click it is the most reliably annoying control a search bar can
//  have, and making them pressable costs one closure each.
//
//  Push-to-talk is `PushToTalkMicButton` — the same trigger the composer and the floating bar click,
//  entering the one `PushToTalkManager` turn. There is no second microphone here and no second
//  transcript writer.
//
//  **It is a composer, not just a search field.** This is now the app's only main-window composer,
//  so the two things every other composer carries and this one shipped without are here: a paperclip
//  (with the same drag-and-drop the floating bar and `ChatInputView` accept) and a Stop that takes
//  the `⌘⏎ Ask` slot while a turn is in flight. A send button with no way to stop what it started is
//  a control that only works when nothing has gone wrong.
//
//  The third thing it shipped without was **more than one line.** It was an `NSTextField` in a
//  surface whose whole job is a question, so a pasted paragraph was stored in full and drawn as its
//  last line, a long sentence scrolled its own beginning out of view, and there was no way to type a
//  newline at all. It is now the same `OmiTextEditor` the other two composers use — one composer
//  vocabulary, so Shift-⏎ writes a newline here exactly as it does there — measured by SwiftUI and
//  capped at `QueryShellLayout.composerMaxHeight` so the results panel underneath keeps its window.
//
//  **The text is `ChatProvider`'s draft, not this view's.** The bar used to bind a `@State` on its
//  host while `ChatProvider.draftText` — what the automation bridge writes and what persistence
//  restores — went to a different variable nothing rendered: two variables behind one apparent
//  control, so a restored draft was invisible and a harness that set one was asserting on neither.
//  The host hands this view the provider's draft through `ChatDraftScope`.
//
//  Brand: `Ink` semantics only; the single accent is spent on `⌘⏎ Ask` — and on the Stop that stands
//  in for it, because they are the same slot and the same weight (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

struct QueryHeroBar: View {
  /// The composer's text. **Always `ChatProvider.composerDraft` through `ChatDraftScope`** — see the
  /// file header. A `@State` here, or on the host, is the defect this parameter exists to prevent.
  @Binding var text: String
  /// The host's caret claim. Monotonic: every increment puts the caret back in this bar. `@FocusState`
  /// cannot do that job here, because the field is an `NSTextView` that SwiftUI's `.focused()` does
  /// not reach — and because a flag that is already `true` cannot re-claim a caret AppKit has since
  /// given to something else. See `OmiTextEditor.focusRequest`.
  let caretClaim: Int
  /// Quickens the mark while a turn is in flight, and swaps `⌘⏎ Ask` for Stop.
  let isWorking: Bool
  /// Stop has been asked for and the runtime has not finished unwinding yet.
  var isStopping: Bool = false
  /// The bar is the same object in both modes; only what `⏎` means changes. While an answer is on
  /// screen the plain key continues the thread, because a bare Return that quietly went back to
  /// filtering would throw away what you were in the middle of asking.
  let mode: QueryShellMode
  /// Files staged for the next send. Owned by `ChatProvider.pendingAttachments`; this bar only draws
  /// them, so a file staged by the automation bridge or by a drop on the floating bar shows up here.
  var attachments: [ChatAttachment] = []
  let onSearch: () -> Void
  let onAsk: () -> Void
  var onStop: () -> Void = {}
  var onAttachmentsAdded: ([URL]) -> Void = { _ in }
  var onAttachmentRemoved: (String) -> Void = { _ in }

  @State private var isDropTargeted = false
  /// True while an input method has uncommitted marked text, which is the one moment the placeholder
  /// must stay hidden over an apparently empty field.
  @State private var hasMarkedText = false
  @Environment(\.fontScale) private var fontScale

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      if !attachments.isEmpty {
        AttachmentPreviewRow(attachments: attachments, onRemove: onAttachmentRemoved)
          .accessibilityIdentifier("query-shell-attachments")
      }
      inputRow
    }
    .padding(.horizontal, QueryShellLayout.barPaddingHorizontal)
    .padding(.vertical, QueryShellLayout.barPaddingVertical)
    .frame(minHeight: QueryShellLayout.barMinHeight)
    // **The bar is sized by what is in it; the panel below is the flexible one.** Without this the
    // column squeezes the bar — which has a range now that the composer grows — down to whatever is
    // left after the results panel has taken its share, while the composer inside keeps the height it
    // asked for and draws straight through the glass edge. Worse, the height the surface then
    // *measures* off this bar is the squeezed one, so the panel's own reserve is computed from a
    // number the bar never wanted, and the two settle on a wrong answer that neither can leave.
    // `ChatInputView` pins itself the same way, for the same reason.
    .fixedSize(horizontal: false, vertical: true)
    .frame(maxWidth: .infinity)
    .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
    .overlay(
      RoundedRectangle(cornerRadius: QueryShellLayout.panelCornerRadius, style: .continuous)
        .strokeBorder(isDropTargeted ? Ink.accent : .clear, lineWidth: 2)
    )
    // Dropping onto the bar is the same staging path as the paperclip: both end at
    // `ChatProvider.addAttachments`, which is what enforces the count cap.
    .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
    // **No tap gesture on the bar itself.** A `contentShape` + `onTapGesture` wrapped around the
    // whole row is the outermost gesture, so it wins over the buttons inside it: the first version
    // of this focused the field on every click and the `⌘⏎ Ask` button was unpressable. The field
    // already fills the space between the mark and the hints, so clicking the bar focuses it anyway.
  }

  private var inputRow: some View {
    HStack(spacing: 14) {
      OmiQueryDotMark(diameter: QueryShellLayout.markDiameter, isWorking: isWorking)

      composer

      attachButton

      QueryKeyHint(label: searchHintLabel, isAccented: false, action: onSearch)
        .accessibilityIdentifier("query-shell-search-hint")

      // Same slot, same weight. A primary that thins out the moment a turn starts is a button that
      // disappears exactly when it starts to matter — `HomeAskBarControls` already states this rule
      // for the other Home composer, and this bar is not allowed a second opinion about it.
      if isWorking {
        QueryKeyHint(label: isStopping ? "Stopping…" : "Stop", isAccented: true, action: onStop)
          .disabled(isStopping)
          .accessibilityIdentifier("query-shell-stop")
          .accessibilityLabel("Stop response")
          .help("Stop this response")
      } else {
        QueryKeyHint(label: "⌘⏎ Ask", isAccented: true, action: onAsk)
          .keyboardShortcut(.return, modifiers: .command)
          .accessibilityIdentifier("query-shell-ask-hint")
      }

      // The resting disc under it: the mic button draws nothing at rest by design (it also lives on
      // the notch's black glass), and on this bar it is the only round target, so it needs a ground
      // to read as a button before you hover it.
      PushToTalkMicButton(
        diameter: QueryShellLayout.micDiameter, glyphSize: OmiType.subheading
      )
      .background(Circle().fill(Ink.rowFill))
      .accessibilityIdentifier("query-shell-push-to-talk")
    }
  }

  /// **The field, grown into a composer.**
  ///
  /// **The editor reports its own height and the bar is sized from it.** The other arrangement —
  /// measuring a hidden `Text` and overlaying the editor on it, which `ChatInputView` uses — was
  /// tried here first and it grows the *text* without growing the glass: an `NSViewRepresentable`
  /// with no `sizeThatFits` has no size of its own, so the editor kept drawing three lines through a
  /// bar that was still one line tall, spilling the reader's own words outside the panel. Handing
  /// `OmiTextEditor` a floor and a ceiling makes `sizeThatFits` return a real clamped height, which
  /// is what SwiftUI then lays the row out to.
  ///
  /// The ceiling is the editor's, not a `frame` around it. Capping the frame would leave the editor
  /// its full natural height inside a shorter window: you would see the *middle* of a long draft with
  /// no way to scroll to either end, because the missing part is outside the scroll view rather than
  /// below it. Bounded here, the editor gets a five-line viewport over the whole draft — which is
  /// what its scroll bar is for. The floor equals one line plus its insets, so the bar's own
  /// `minHeight` (64) still wins at rest and an empty composer leaves the surface exactly as it was.
  private var composer: some View {
    OmiTextEditor(
      text: $text,
      fontSize: round(QueryShellLayout.queryFontSize * fontScale),
      textColor: Ink.nsPrimaryOnGlass,
      // Bare Return only. **A Command-modified key never reaches here** — AppKit routes it to
      // key-equivalent handling first — so `⌘⏎` is a real `keyboardShortcut` on the Ask button below
      // rather than a modifier read at the field. Shift-Return is the editor's own newline and never
      // arrives as a submit (`OmiComposerReturnKey`).
      textContainerInset: NSSize(width: 0, height: QueryShellLayout.composerInsetVertical),
      onSubmit: submitFromReturnKey,
      // The caret is claimed explicitly by the host, so this editor must not also grab it — and must
      // never bring the window forward on its own (`ComposerScrollView`).
      focusOnAppear: false,
      onMarkedTextChange: { hasMarkedText = $0 },
      focusRequest: caretClaim,
      minHeight: QueryShellLayout.composerMinHeight,
      maxHeight: QueryShellLayout.composerMaxHeight
    )
    .frame(maxWidth: .infinity)
    .overlay(alignment: .topLeading) {
      if text.isEmpty && !hasMarkedText {
        Text(placeholder)
          .scaledFont(size: QueryShellLayout.queryFontSize, weight: .medium)
          .foregroundStyle(Ink.secondary)
          // Matches `textContainerInset` exactly, so the placeholder sits where the caret will.
          .padding(.vertical, QueryShellLayout.composerInsetVertical)
          .allowsHitTesting(false)
      }
    }
    .accessibilityIdentifier("query-shell-field")
    .accessibilityLabel(Text(placeholder))
  }

  /// `⏎` in the composer means whatever the bar's own hint says it means, so the key and the label
  /// cannot disagree. `⌘⏎` never arrives here.
  private func submitFromReturnKey() {
    switch QueryShellSubmit.resolve(text: text, commandHeld: mode == .answer) {
    case .ask: onAsk()
    case .search: onSearch()
    case .none: break
    }
  }

  private var attachButton: some View {
    Button(action: pickFiles) {
      Image(systemName: "paperclip")
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundStyle(Ink.secondary)
        .frame(width: 28, height: 28)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .disabled(attachments.count >= kMaxChatAttachments)
    .help("Attach files")
    .accessibilityLabel("Attach files")
    .accessibilityIdentifier("query-shell-attach")
  }

  private var placeholder: String {
    mode == .answer ? "Ask a follow-up…" : RewindSearchMetrics.placeholder
  }

  private var searchHintLabel: String {
    mode == .answer ? "esc Results" : "⏎ Search"
  }

  /// The same content types `ChatInputView` accepts — one composer vocabulary, not two.
  private func pickFiles() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = true
    panel.allowedContentTypes = [
      .image, .jpeg, .png, .gif, .heic, .heif, .webP, .tiff, .bmp,
      .pdf, .plainText, .json, .commaSeparatedText, .html,
      .text, .content,
    ]
    guard panel.runModal() == .OK, !panel.urls.isEmpty else { return }
    onAttachmentsAdded(panel.urls)
  }

  private func handleDrop(providers: [NSItemProvider]) -> Bool {
    ChatAttachmentDropHandler.collectURLs(from: providers) { urls in
      guard !urls.isEmpty else { return }
      onAttachmentsAdded(urls)
    }
  }
}

/// One of the two keyboard hints. A pressable stadium, because everything pressable in this system is.
private struct QueryKeyHint: View {
  let label: String
  let isAccented: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(isAccented ? Ink.accent : GlassShell.controlLabel(isProminent: isHovering))
        .padding(.horizontal, 11)
        .frame(height: 28)
        .background(Capsule(style: .continuous).fill(isHovering ? Ink.rowFill : .clear))
        .overlay(
          Capsule(style: .continuous)
            .strokeBorder(isAccented ? Ink.accent.opacity(0.35) : Ink.separator, lineWidth: 1)
        )
        .contentShape(Capsule(style: .continuous))
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
    .fixedSize()
  }
}
