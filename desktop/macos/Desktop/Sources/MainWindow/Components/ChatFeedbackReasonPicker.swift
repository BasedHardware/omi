import OmiTheme
import SwiftUI

/// One-click "what went wrong" row, shown under a bubble after a thumbs-down.
///
/// Deliberately an inline row rather than a modal sheet: the reason is a
/// nicety, not a toll. The thumbs-down is already recorded by the time this
/// appears, so a user who ignores it loses nothing — they keep reading, and the
/// report records that turn's reason as "not captured".
struct ChatFeedbackReasonPicker: View {
  /// Which five chips to show — notification cards and chat answers use
  /// distinct taxonomies (see `ChatFeedbackReason.chips(isProactiveNotification:)`).
  let reasons: [ChatFeedbackReason]
  /// The reason already chosen, if any. Highlights that chip.
  let selected: ChatFeedbackReason?
  let onSelect: (ChatFeedbackReason) -> Void
  let onSkip: () -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Text("What went wrong?")
        .scaledFont(size: OmiType.micro)
        .foregroundColor(Ink.secondary)

      ForEach(reasons) { reason in
        Button(action: { onSelect(reason) }) {
          Text(reason.label)
            .scaledFont(size: OmiType.micro)
            .foregroundColor(selected == reason ? Ink.primary : Ink.secondary)
            .padding(.horizontal, OmiSpacing.xxs)
            .padding(.vertical, 1)
            .background(
              RoundedRectangle(cornerRadius: 4)
                .stroke(Ink.secondary.opacity(0.35), lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(reason.help)
        .accessibilityLabel("Reason: \(reason.label)")
      }

      Button(action: onSkip) {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Skip")
      .accessibilityLabel("Skip reason")
    }
  }
}
