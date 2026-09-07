import OmiTheme
import SwiftUI

/// Recovery stays on the failure surface; editing and sending remain in main Chat.
struct PTTStatusBannerContent: View {
  let hint: String
  @ObservedObject private var recovery = OfflinePTTQuestionRecovery.shared

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: recovery.isAvailable ? "wifi.slash" : "mic.fill")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(.white.opacity(0.9))
      Text(recovery.isAvailable ? "Question kept" : hint)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(.white)
        .lineLimit(1)
      Spacer(minLength: 0)
      if recovery.isAvailable {
        Button("Review") { recovery.reviewInMainChat() }
          .help("Review your offline question in Chat without sending it")
          .accessibilityIdentifier("ptt_recover_question_review")
        Button {
          recovery.copyToClipboard()
        } label: {
          Image(systemName: "doc.on.doc")
        }
        .help("Copy your offline question")
        .accessibilityLabel("Copy offline question")
        .accessibilityIdentifier("ptt_recover_question_copy")
      }
    }
    .buttonStyle(.plain)
    .foregroundColor(.white)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// Remains available after the brief failure banner disappears.
struct PTTRecoveryMenuItems: View {
  @ObservedObject private var recovery = OfflinePTTQuestionRecovery.shared

  var body: some View {
    Button("Undo Last Dictation") { PushToTalkManager.shared.undoLastDictation() }
      .disabled(!PushToTalkManager.shared.canUndoLastDictation)
      .help("Undo a recent dictation while its text and caret are unchanged")
    if recovery.isAvailable {
      Button("Review Offline Question") { recovery.reviewInMainChat() }
      Button("Copy Offline Question") { recovery.copyToClipboard() }
      Button("Dismiss Offline Question") { recovery.clear() }
      Divider()
    }
  }
}
