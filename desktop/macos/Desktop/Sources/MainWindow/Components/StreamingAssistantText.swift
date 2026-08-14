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

  static func displayedText(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  var body: some View {
    let displayedText = Self.displayedText(text)
    if sender == .ai && isStreaming && OmiMarkdown.isPlainText(displayedText) {
      TokenizedText(displayedText, separator: .diff, animation: .fadeIn, animationDuration: 0.18)
        .font(.system(size: round(14 * fontScale)))
        .foregroundStyle(Ink.primary)
        .textSelection(.disabled)
    } else {
      OmiMarkdown(text: displayedText, sender: sender)
    }
  }
}
