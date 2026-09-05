//
//  QueryHeroBar.swift — one field you type into, standing wherever the mode needs it.
//
//  While you are searching it is the *first* of the surface's two glass objects, deliberately not
//  welded to the second. A place you type and a place you look are different in kind; drawn as one
//  tall block with a rule across it they claim to be the same object, and the surface stops reading
//  as search.
//
//  **Once a conversation is open that arrangement is the wrong one, so this view moves.** In answer
//  mode it is rendered *inside* the results panel, pinned under the transcript, wearing a quiet
//  capsule instead of its own glass — which is what every other chat in the world looks like, and
//  what the person using this one asked for. It is the same view rather than a second composer: one
//  `OmiTextEditor`, one `ChatProvider` draft, one caret claim, one send (INV-6). See
//  `QueryComposerPlacement` for what the two placements actually differ by.
//
//  **The in-panel row is one leading affordance, a field, and a trailing cluster with exactly one
//  primary in it.** It first shipped as three controls in three visual languages — a bare paperclip,
//  an outlined accent `⏎ Send` pill and a filled grey mic disc — at three sizes, in a shallow
//  rounded box whose corner was far too small for its height and whose caret sat hard against the
//  leading edge. Every one of those is a proportion, so all of them live in `QueryShellLayout`:
//  one control diameter, one glyph size, one interior margin, and a corner that is half the pill's
//  own height. The single filled control is Send, in the `Ink.primary` / `Ink.surface` pair the
//  onboarding `Continue` button already uses — never the accent, which was the only saturated colour
//  in the frame and was spent on the least important control in it (INV-UI-1).
//
//  **There are no keyboard hints any more, because there is no longer a key to choose between.** The
//  bar carried `⏎ Search` and `⌘⏎ Ask` as two labelled buttons, which asked the reader to pick a mode
//  before they could press anything — and one of the two was never a decision: the list under the bar
//  filters as you type, so `Search` committed to something that had already happened. Typing searches;
//  `⏎` sends; the row's one button is the only thing with a choice behind it, which is exactly why it
//  is the only loud one. `⌘⏎` still sends, unadvertised, for the muscle memory it built.
//
//  Push-to-talk is `PushToTalkMicButton` — the same trigger the composer and the floating bar click,
//  entering the one `PushToTalkManager` turn. There is no second microphone here and no second
//  transcript writer.
//
//  **It is a composer, not just a search field.** This is now the app's only main-window composer,
//  so the two things every other composer carries and this one shipped without are here: a paperclip
//  (with the same drag-and-drop the floating bar and `ChatInputView` accept) and a Stop that takes
//  the primary's slot while a turn is in flight. A send button with no way to stop what it started is
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
//  Brand: `Ink` semantics only, and **no accent anywhere in this view**. The one saturated thing on
//  the surface used to be the outlined blue `⌘⏎ Ask` / `⏎ Send` pill, which spent the palette's single
//  accent on a control the reader was not meant to reach for first. Both rows' primary is now a filled
//  `Ink.primary` disc under an `Ink.surface` glyph — the pair the onboarding `Continue` button uses
//  (INV-UI-1).
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
  /// Quickens the mark while a turn is in flight, and swaps the primary for Stop.
  let isWorking: Bool
  /// Stop has been asked for and the runtime has not finished unwinding yet.
  var isStopping: Bool = false
  /// The bar is the same object in both modes, and **`⏎` now means the same thing in both** — send.
  /// All this selects is where the bar stands and what it is wearing (`QueryComposerPlacement`).
  let mode: QueryShellMode
  /// Files staged for the next send. Owned by `ChatProvider.pendingAttachments`; this bar only draws
  /// them, so a file staged by the automation bridge or by a drop on the floating bar shows up here.
  var attachments: [ChatAttachment] = []
  let onAsk: () -> Void
  var onStop: () -> Void = {}
  var onAttachmentsAdded: ([URL]) -> Void = { _ in }
  var onAttachmentRemoved: (String) -> Void = { _ in }
  /// Sources staged from a page action (for example, “Discuss in Chat”).
  /// These are rendered as removable chips and never submit on their own.
  var references: [ChatComposerReference] = []
  var onReferenceRemoved: (String) -> Void = { _ in }

  @State private var isDropTargeted = false
  /// True while an input method has uncommitted marked text, which is the one moment the placeholder
  /// must stay hidden over an apparently empty field.
  @State private var hasMarkedText = false
  @Environment(\.fontScale) private var fontScale

  /// One decision, taken in one place (`QueryComposerPlacement.of`), so the chrome this view draws
  /// and the room `QueryShellLayout` reserves for it can never describe different arrangements.
  private var placement: QueryComposerPlacement { .of(mode) }

  var body: some View {
    ground
      // **The composer is sized by what is in it; the panel is the flexible one.** Without this the
      // column squeezes it — which has a range now that the editor grows — down to whatever is left
      // after the results panel has taken its share, while the editor inside keeps the height it
      // asked for and draws straight through the glass edge. Worse, the height the surface then
      // *measures* off this view is the squeezed one, so the panel's own reserve is computed from a
      // number this view never wanted, and the two settle on a wrong answer that neither can leave.
      // `ChatInputView` pins itself the same way, for the same reason.
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: .infinity)
      // Dropping onto the composer is the same staging path as the paperclip: both end at
      // `ChatProvider.addAttachments`, which is what enforces the count cap. The stroke that says so
      // is drawn inside `ground`, on the shape each placement actually fills — the panel's pill
      // stands in from this view's own bounds, so a stroke out here would ring the wrong rectangle.
      .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
    // **No tap gesture on the row itself.** A `contentShape` + `onTapGesture` wrapped around the
    // whole row is the outermost gesture, so it wins over the buttons inside it: the first version
    // of this focused the field on every click and the primary was unpressable. The field already
    // fills the space between the mark and the cluster, so clicking the row focuses it anyway.
  }

  /// The one thing the two placements really disagree about: what they are standing on.
  ///
  /// `hero` is a glass object in its own right, with the surface's corner and its ambient shadow.
  /// `panelFooter` is already *on* glass — it sits inside the results panel — so a second sheet of
  /// it there would read as a panel inside a panel. It wears **one quiet capsule** instead: a single
  /// fill, no outline competing with it for the edge, a corner that is half the pill's own height,
  /// and real air between it and the panel's own corner so it sits *inside* the panel rather than
  /// spanning it. See `QueryShellLayout.panelComposerCornerRadius`.
  @ViewBuilder
  private var ground: some View {
    switch placement {
    case .hero:
      stack
        .padding(.horizontal, QueryShellLayout.barPaddingHorizontal)
        .padding(.vertical, QueryShellLayout.barPaddingVertical)
        .frame(minHeight: QueryShellLayout.barMinHeight)
        .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
        .overlay(dropStroke(cornerRadius: QueryShellLayout.panelCornerRadius))
    case .panelFooter:
      stack
        .frame(minHeight: QueryShellLayout.panelComposerControlDiameter)
        .padding(QueryShellLayout.panelComposerShellInset)
        // **One ground and no stroke.** The shared `chatComposerShell` puts an `Ink.separator`
        // outline around its fill, and on a pill this size the outline is what you see first — two
        // edges arguing about where the object ends. Dropping it costs the object its definition at
        // `rowFill`'s 4.5%, so the fill steps up one rung instead: `rowFillHover` is the same value
        // `ChatInputView` already rests its well at, for the same reason — it has to stay legible on
        // glass over a bright wallpaper.
        .background(
          RoundedRectangle(
            cornerRadius: QueryShellLayout.panelComposerCornerRadius, style: .continuous
          )
          .fill(Ink.rowFillHover)
        )
        .overlay(dropStroke(cornerRadius: QueryShellLayout.panelComposerCornerRadius))
        .padding(.horizontal, QueryShellLayout.panelComposerEdgeInset)
        .padding(.bottom, QueryShellLayout.panelComposerBottomInset)
    }
  }

  /// The "you can drop that here" edge, drawn on whichever shape the placement actually filled.
  private func dropStroke(cornerRadius: CGFloat) -> some View {
    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
      .strokeBorder(isDropTargeted ? Ink.accent : .clear, lineWidth: 2)
  }

  private var stack: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      if !attachments.isEmpty {
        AttachmentPreviewRow(attachments: attachments, onRemove: onAttachmentRemoved)
          .accessibilityIdentifier("query-shell-attachments")
      }
      if !references.isEmpty {
        ChatComposerReferenceRow(references: references, onRemove: onReferenceRemoved)
          .accessibilityIdentifier("query-shell-references")
      }
      inputRow
    }
  }

  @ViewBuilder
  private var inputRow: some View {
    switch placement {
    case .hero: heroRow
    case .panelFooter: panelRow
    }
  }

  /// **The search bar's row — the same three controls the panel's has, at the hero's own scale.**
  ///
  /// It used to carry two labelled keys, `⏎ Search` and `⌘⏎ Ask`, and they were a mode choice the
  /// reader should never have been asked to make: the list under this bar **filters as you type**,
  /// so `Search` committed to something that had already happened, and `Ask` was then the only key
  /// with a decision behind it while being the second-billed of the two. Both are gone. Typing
  /// searches; `⏎` sends; the one thing you can press is the one thing with a choice in it.
  private var heroRow: some View {
    HStack(spacing: QueryShellLayout.heroRowSpacing) {
      // The query mark belongs to the query. Inside the panel the transcript is already the record
      // of what was asked, and a second animated mark under it is one identity mark too many — the
      // assistant's own is drawn in the transcript's gutter a few points above.
      OmiQueryDotMark(diameter: QueryShellLayout.markDiameter, isWorking: isWorking)

      composer

      attachButton(
        diameter: QueryShellLayout.micDiameter, glyphSize: QueryShellLayout.heroGlyphSize)

      // No ground under the mic any more. It carried one for being the row's only round target, and
      // it is not: the send disc beside it is round, filled, and the thing the eye should land on.
      PushToTalkMicButton(
        diameter: QueryShellLayout.micDiameter, glyphSize: QueryShellLayout.heroGlyphSize
      )
      .accessibilityIdentifier("query-shell-push-to-talk")

      // Same slot, same weight. A primary that thins out the moment a turn starts is a button that
      // disappears exactly when it starts to matter — `HomeAskBarControls` already states this rule
      // for the other Home composer, and this bar is not allowed a second opinion about it.
      if isWorking {
        heroPrimary(systemImage: "stop.fill", isProminent: !isStopping, action: onStop)
          .disabled(isStopping)
          .accessibilityIdentifier("query-shell-stop")
          .accessibilityLabel("Stop response")
          .help("Stop this response")
      } else {
        heroPrimary(systemImage: "arrow.up", isProminent: canSend, action: onAsk)
          .keyboardShortcut(.return, modifiers: .command)
          .accessibilityIdentifier("query-shell-ask-hint")
          .accessibilityLabel("Send")
          .help("Send — ⏎")
      }
    }
  }

  private func heroPrimary(
    systemImage: String, isProminent: Bool, action: @escaping () -> Void
  ) -> some View {
    primaryDisc(
      systemImage: systemImage,
      diameter: QueryShellLayout.micDiameter,
      glyphSize: QueryShellLayout.heroPrimaryGlyphSize,
      isProminent: isProminent,
      action: action)
  }

  /// **The chat row: one leading affordance, the field, and one primary in a quiet trailing cluster.**
  ///
  /// The paperclip moves to the leading edge, which is the balance the row was missing — the caret
  /// used to start hard against the fill with every control piled at the other end. Everything in
  /// the cluster is now one diameter and one glyph size, and only Send is filled, so the eye lands
  /// on the control that matters instead of on the loudest one.
  ///
  /// `.bottom`, because a five-line draft must not leave the buttons floating in the middle of the
  /// pill. At rest it is indistinguishable from `.center`: one line of the chat face is exactly
  /// `panelComposerControlDiameter` tall, by construction.
  private var panelRow: some View {
    HStack(alignment: .bottom, spacing: OmiSpacing.sm) {
      attachButton(
        diameter: QueryShellLayout.panelComposerControlDiameter,
        glyphSize: QueryShellLayout.panelComposerGlyphSize)

      composer

      // No ground of its own here. In the hero it is the row's only round target and needs one; in
      // this row it is one of three, and the one that is allowed to be filled is Send.
      PushToTalkMicButton(
        diameter: QueryShellLayout.panelComposerControlDiameter,
        glyphSize: QueryShellLayout.panelComposerGlyphSize
      )
      .accessibilityIdentifier("query-shell-push-to-talk")

      // Same slot, same weight, same disc — see the hero's note. Stop is not a quieter control than
      // Send; it is the same control while a turn is in flight.
      if isWorking {
        panelPrimary(systemImage: "stop.fill", isProminent: !isStopping, action: onStop)
          .disabled(isStopping)
          .accessibilityIdentifier("query-shell-stop")
          .accessibilityLabel("Stop response")
          .help("Stop this response")
      } else {
        panelPrimary(systemImage: "arrow.up", isProminent: canSend, action: onAsk)
          .keyboardShortcut(.return, modifiers: .command)
          .accessibilityIdentifier("query-shell-ask-hint")
          .accessibilityLabel("Send")
          // **The key hint is help text, not paint.** `⏎ Send` written across the control was the
          // widest thing in the row and the reason it needed a pill to sit in at all.
          .help("Send — ⏎")
      }
    }
  }

  private func panelPrimary(
    systemImage: String, isProminent: Bool, action: @escaping () -> Void
  ) -> some View {
    primaryDisc(
      systemImage: systemImage,
      diameter: QueryShellLayout.panelComposerControlDiameter,
      glyphSize: QueryShellLayout.panelComposerGlyphSize,
      isProminent: isProminent,
      action: action)
  }

  /// **The row's one filled control**, in the pair the onboarding `Continue` button uses:
  /// `Ink.primary` fill under an `Ink.surface` glyph. High-contrast in both appearances by
  /// construction, and — unlike the accent pill it replaces — not the only saturated thing in the
  /// frame (INV-UI-1).
  ///
  /// One function for both placements, at each one's own diameter: two rows that draw their primary
  /// separately are two rows that end up with two primaries.
  private func primaryDisc(
    systemImage: String, diameter: CGFloat, glyphSize: CGFloat, isProminent: Bool,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      Image(systemName: systemImage)
        .scaledFont(size: glyphSize, weight: .semibold)
        .foregroundStyle(Ink.surface)
        .frame(width: diameter, height: diameter)
        .background(Circle().fill(Ink.primary))
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    // Never `.disabled` on an empty field: `⌘⏎` is this button's `keyboardShortcut`, and a disabled
    // button swallows it — the key would stop resolving through `QueryShellSubmission` at all.
    // Dimmed instead, which is what "nothing to send yet" actually looks like.
    .opacity(isProminent ? 1 : 0.4)
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isProminent)
  }

  /// Whether there is anything for the primary to send. A staged file with no words is a send.
  private var canSend: Bool {
    !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty
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
      fontSize: round(fontSize * fontScale),
      textColor: Ink.nsPrimaryOnGlass,
      // Bare Return only. **A Command-modified key never reaches here** — AppKit routes it to
      // key-equivalent handling first — so `⌘⏎` is a real `keyboardShortcut` on the primary below
      // rather than a modifier read at the field. Both keys send. Shift-Return is the editor's own
      // newline and never arrives as a submit (`OmiComposerReturnKey`).
      textContainerInset: NSSize(width: 0, height: editorInsetVertical),
      onSubmit: submitFromReturnKey,
      // The caret is claimed explicitly by the host, so this editor must not also grab it — and must
      // never bring the window forward on its own (`ComposerScrollView`).
      focusOnAppear: false,
      onMarkedTextChange: { hasMarkedText = $0 },
      focusRequest: caretClaim,
      minHeight: minEditorHeight,
      maxHeight: maxEditorHeight
    )
    .frame(maxWidth: .infinity)
    .overlay(alignment: .topLeading) {
      if text.isEmpty && !hasMarkedText {
        Text(placeholder)
          .scaledFont(size: fontSize, weight: .medium)
          .foregroundStyle(Ink.secondary)
          // Matches `textContainerInset` exactly, so the placeholder sits where the caret will.
          .padding(.vertical, editorInsetVertical)
          .allowsHitTesting(false)
      }
    }
    .onAppear { ChatSwitchPerfLog.markOnce("composerAppeared") }
    .accessibilityIdentifier("query-shell-field")
    .accessibilityLabel(Text(placeholder))
  }

  /// **`⏎` sends, wherever this bar is standing.**
  ///
  /// It used to mean *search* on the hero and *send* in the panel, with `⌘⏎` as the escape hatch —
  /// two keys, and a rule about which surface you were on before you could know what either did.
  /// The list under the hero filters as you type, so the plain key was committing to a filter the
  /// panel had already applied; there was never a second thing for it to mean. `⌘⏎` still sends: it
  /// is the `keyboardShortcut` on the primary and never arrives here.
  private func submitFromReturnKey() {
    switch QueryShellSubmit.resolve(text: text) {
    case .ask: onAsk()
    case .none: break
    }
  }

  /// A quiet `Ink` glyph in both placements — the paperclip has never been a primary. In the panel
  /// it is the *leading* one, sized and tinted exactly like the mic across the field from it.
  private func attachButton(diameter: CGFloat, glyphSize: CGFloat) -> some View {
    Button(action: pickFiles) {
      Image(systemName: "paperclip")
        .scaledFont(size: glyphSize, weight: .medium)
        .foregroundStyle(Ink.secondary)
        .frame(width: diameter, height: diameter)
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

  private var fontSize: CGFloat {
    placement == .hero ? QueryShellLayout.queryFontSize : QueryShellLayout.panelComposerFontSize
  }

  /// The text container's own margin. In the panel it is derived from the control diameter so one
  /// laid-out line is exactly a disc tall — see `QueryShellLayout.panelComposerInsetVertical`.
  private var editorInsetVertical: CGFloat {
    placement == .hero
      ? QueryShellLayout.composerInsetVertical : QueryShellLayout.panelComposerInsetVertical
  }

  private var minEditorHeight: CGFloat {
    placement == .hero
      ? QueryShellLayout.composerMinHeight : QueryShellLayout.panelComposerMinEditorHeight
  }

  private var maxEditorHeight: CGFloat {
    placement == .hero
      ? QueryShellLayout.composerMaxHeight : QueryShellLayout.panelComposerMaxEditorHeight
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
