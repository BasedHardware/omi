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
//  Brand: `Ink` semantics only; the single accent is spent on `⌘⏎ Ask` — and on the Stop that stands
//  in for it, because they are the same slot and the same weight (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

struct QueryHeroBar: View {
  @Binding var text: String
  var focus: FocusState<Bool>.Binding
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

      TextField(
        "",
        text: $text,
        prompt: Text(placeholder).foregroundColor(Ink.secondary)
      )
      .textFieldStyle(.plain)
      .scaledFont(size: QueryShellLayout.queryFontSize, weight: .medium)
      .foregroundStyle(Ink.primary)
      .focused(focus)
      .accessibilityIdentifier("query-shell-field")
      .accessibilityLabel(Text(placeholder))
      // Bare Return only. **A Command-modified key never reaches `onKeyPress`** — AppKit routes it
      // to key-equivalent handling first — so `⌘⏎` is a real `keyboardShortcut` on the Ask button
      // below rather than a modifier read here. Reading `press.modifiers` for it compiles, draws a
      // convincing hint, and never fires once.
      .onKeyPress(phases: .down) { press in
        guard press.key == .return else { return .ignored }
        switch QueryShellSubmit.resolve(text: text, commandHeld: mode == .answer) {
        case .ask:
          onAsk()
          return .handled
        case .search:
          onSearch()
          return .handled
        case .none:
          return .ignored
        }
      }

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
