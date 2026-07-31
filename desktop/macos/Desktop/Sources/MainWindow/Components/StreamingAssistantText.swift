import FlowToken
import OmiTheme
import SwiftUI

struct StreamingAssistantText: View {
  let text: String
  let isStreaming: Bool
  let sender: ChatSender
  @Environment(\.fontScale) private var fontScale

  init(_ text: String, isStreaming: Bool, sender: ChatSender = .ai) {
    self.text = text
    self.isStreaming = isStreaming
    self.sender = sender
  }

  var body: some View {
    if sender == .ai && isStreaming && OmiMarkdown.isPlainText(text) {
      TokenizedText(text, separator: .diff, animation: .fadeIn, animationDuration: 0.18)
        .font(.system(size: round(14 * fontScale)))
        .foregroundStyle(OmiColors.textPrimary)
        .textSelection(.disabled)
    } else {
      OmiMarkdown(text: text, sender: sender)
    }
  }
}
