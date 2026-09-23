import AppKit
import OmiTheme
import SwiftUI

/// Find-in-transcript control for the conversation Transcript header.
///
/// Closed, it is a magnifier icon button. ⌘F opens it and focuses the field. Open, it shows the
/// field, an "N of M" count, and previous and next buttons: ⌘G / ⇧⌘G, or Return / ⇧Return in the
/// field. The owner handles Esc (clear and close) at `.editing` priority, so Esc clears the search
/// before it leaves the transcript. Matching and stepping live in `TranscriptSearchModel`.
struct TranscriptFindField: View {
  let isOpen: Bool
  @Binding var query: String
  let countLabel: String
  let hasMatches: Bool
  var isFocused: FocusState<Bool>.Binding
  let onOpen: () -> Void
  let onStep: (_ forward: Bool) -> Void
  let onClose: () -> Void

  var body: some View {
    Group {
      if isOpen {
        openField
      } else {
        OmiIconButton("magnifyingglass", help: "Find in transcript (⌘F)", action: onOpen)
          .accessibilityIdentifier("conversation-detail-transcript-find")
      }
    }
    // ⌘F goes through the shared router at detail priority, so it beats any page search field in the
    // same window instead of racing it through a key equivalent.
    .onFindCommand(priority: .detail) {
      if isOpen { isFocused.wrappedValue = true } else { onOpen() }
    }
  }

  private var openField: some View {
    HStack(spacing: OmiSpacing.xs) {
      // The magnifier refocuses the field, and keeps ⌘F live while the field is open.
      Button {
        isFocused.wrappedValue = true
      } label: {
        Image(systemName: "magnifyingglass")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(Ink.secondary)
      }
      .buttonStyle(.plain)
      .help("Find in transcript (⌘F)")
      .accessibilityHidden(true)

      TextField("Find in transcript", text: $query)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(Ink.primary)
        .focused(isFocused)
        .frame(minWidth: 96, idealWidth: 160, maxWidth: 200)
        .onSubmit { onStep(!(NSApp.currentEvent?.modifierFlags.contains(.shift) ?? false)) }
        .accessibilityIdentifier("conversation-detail-transcript-find-field")

      if !countLabel.isEmpty {
        Text(countLabel)
          .scaledFont(size: OmiType.caption)
          .monospacedDigit()
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
          .fixedSize()
          .accessibilityIdentifier("conversation-detail-transcript-find-count")
      }

      OmiIconButton("chevron.up", help: "Previous match (⇧⌘G)", size: .compact) { onStep(false) }
        .keyboardShortcut("g", modifiers: [.command, .shift])
        .disabled(!hasMatches)

      OmiIconButton("chevron.down", help: "Next match (⌘G)", size: .compact) { onStep(true) }
        .keyboardShortcut("g", modifiers: .command)
        .disabled(!hasMatches)

      ClearFieldButton(help: "Clear and close find (Esc)", action: onClose)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .frame(minHeight: OmiIconButtonSize.regular.diameter)
    .glassField()
    .accessibilityElement(children: .contain)
  }
}
