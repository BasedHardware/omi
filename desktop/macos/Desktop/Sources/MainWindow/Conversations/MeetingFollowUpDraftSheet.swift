import OmiTheme
import SwiftUI

/// An editable, copy-only handoff. The user chooses where and whether to send it.
struct MeetingFollowUpDraftSheet: View {
  @Binding var text: String
  let onReviewTranscript: () -> Void
  let onCopy: () -> Void
  let onClose: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text("Draft follow-up")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text("Based on your cited commitments from this meeting. Check the transcript and edit before sharing.")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: OmiSpacing.md)
        DismissButton(action: onClose)
      }

      TextEditor(text: $text)
        .scaledFont(size: OmiType.body)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.sm)
        .frame(minHeight: 180)
        .background(
          RoundedRectangle(cornerRadius: PageGlass.fieldRadius, style: .continuous)
            .fill(Ink.rowFill)
        )
        .accessibilityIdentifier("meeting-follow-up-draft-text")

      HStack(spacing: OmiSpacing.sm) {
        Button("Review transcript", action: onReviewTranscript)
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        Spacer(minLength: 0)
        Button("Copy draft", action: onCopy)
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
          .accessibilityIdentifier("meeting-follow-up-copy")
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(width: 520)
  }
}
