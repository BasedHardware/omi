import FlowToken
import OmiTheme
import SwiftUI

struct StreamingAssistantText: View {
  let text: String
  let isStreaming: Bool
  @Environment(\.fontScale) private var fontScale

  init(_ text: String, isStreaming: Bool) {
    self.text = text
    self.isStreaming = isStreaming
  }

  var body: some View {
    if isStreaming && OmiMarkdown.isPlainText(text) {
      TokenizedText(text, separator: .diff, animation: .fadeIn, animationDuration: 0.18)
        .font(.system(size: 14 * fontScale))
        .foregroundStyle(OmiColors.textPrimary)
        .textSelection(.disabled)
    } else {
      OmiMarkdown(text: text, style: .assistant)
    }
  }
}
