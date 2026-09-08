import OmiTheme
import SwiftUI

/// One conversation-reference presentation shared by the composer and the
/// accepted user turn. The lifecycle changes its trailing action, not its
/// identity or visual language: staged references are removable; persisted
/// references reopen the canonical conversation detail.
struct ChatConversationReferencePill: View {
  let reference: ChatComposerReference
  var onRemove: (() -> Void)? = nil
  var onOpen: (() -> Void)? = nil

  var body: some View {
    Group {
      if let onOpen {
        Button(action: onOpen) {
          pillContent(showsOpenIndicator: true)
        }
        .buttonStyle(.plain)
        .help("Open \(reference.displayTitle)")
        .accessibilityLabel("Open attached conversation: \(reference.displayTitle)")
        .accessibilityIdentifier("chat-conversation-reference-\(reference.sourceID)-open")
      } else {
        pillContent(showsOpenIndicator: false)
      }
    }
    .background(Ink.rowFillHover)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .strokeBorder(Ink.separator, lineWidth: 1)
    )
    .accessibilityElement(children: .contain)
  }

  private func pillContent(showsOpenIndicator: Bool) -> some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: reference.kind.systemImage)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)

      VStack(alignment: .leading, spacing: 0) {
        Text(reference.displayTitle)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
          .truncationMode(.middle)
        Text(reference.displaySubtitle)
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }
      .frame(maxWidth: 230, alignment: .leading)

      if showsOpenIndicator {
        Image(systemName: "arrow.up.right")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 18, height: 18)
      } else if let onRemove {
        Button(action: onRemove) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .frame(width: 18, height: 18)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Remove \(reference.displayTitle)")
      }
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
  }
}
