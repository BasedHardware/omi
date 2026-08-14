import SwiftUI

extension OmiMarkdownContent {
  /// Extra leading between adjacent chat lines: 5 pt at the default 14 pt body.
  ///
  /// Tracks the chat font-size setting (`fontSize` already includes `fontScale`).
  /// It does not grow with window size — line leading that followed the panel
  /// would loosen on a large display and tighten on a small one.
  static func chatLineSpacing(fontSize: CGFloat) -> CGFloat {
    round(5 * fontSize / 14)
  }
}

/// Chat prose with the extra 5 pt of leading the transcript uses everywhere.
struct OmiMarkdownChatText: View {
  private enum Content {
    case attributed(AttributedString)
    case plain(String, OmiMarkdown.Style)
  }

  private let content: Content
  private let fontSize: CGFloat

  init(_ attributed: AttributedString, fontSize: CGFloat) {
    self.content = .attributed(attributed)
    self.fontSize = fontSize
  }

  init(_ text: String, fontSize: CGFloat, style: OmiMarkdown.Style) {
    self.content = .plain(text, style)
    self.fontSize = fontSize
  }

  var body: some View {
    text
      .lineSpacing(OmiMarkdownContent.chatLineSpacing(fontSize: fontSize))
      .if_available_writingToolsNone()
  }

  @ViewBuilder private var text: some View {
    switch content {
    case .attributed(let value):
      Text(value)
    case .plain(let value, let style):
      Text(value)
        .font(.system(size: fontSize))
        .foregroundColor(OmiMarkdownContent.baseColor(for: style))
    }
  }
}
