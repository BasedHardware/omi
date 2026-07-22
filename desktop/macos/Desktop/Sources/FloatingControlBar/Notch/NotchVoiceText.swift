import AppKit
import SwiftUI

/// Justified multi-line text for the notch voice states. SwiftUI's `Text`
/// cannot justify, so this wraps an AppKit label with a justified paragraph
/// style. It reports its wrapped height through `sizeThatFits` so the existing
/// measure loop keeps working.
struct JustifiedText: NSViewRepresentable {
  let text: String
  var size: CGFloat = 13
  var weight: NSFont.Weight = .regular
  var opacity: CGFloat = 0.9
  /// Force an alignment; nil = the center/justify heuristic. Live-updating text
  /// (the transcript) uses `.left` so it flows as words arrive instead of
  /// re-centering on every word.
  var alignment: NSTextAlignment?

  final class Coordinator { var width: CGFloat = 300 }
  func makeCoordinator() -> Coordinator { Coordinator() }

  func makeNSView(context: Context) -> NSTextField {
    let field = NSTextField(labelWithString: "")
    field.isBezeled = false
    field.drawsBackground = false
    field.isEditable = false
    field.isSelectable = false
    field.maximumNumberOfLines = 0
    field.lineBreakMode = .byWordWrapping
    field.cell?.wraps = true
    field.cell?.isScrollable = false
    return field
  }

  func updateNSView(_ field: NSTextField, context: Context) {
    field.preferredMaxLayoutWidth = context.coordinator.width
    field.attributedStringValue = attributed(width: context.coordinator.width)
  }

  func sizeThatFits(_ proposal: ProposedViewSize, nsView field: NSTextField, context: Context) -> CGSize? {
    let width = proposal.width ?? context.coordinator.width
    context.coordinator.width = width
    field.preferredMaxLayoutWidth = width
    field.attributedStringValue = attributed(width: width)
    return CGSize(width: width, height: ceil(field.intrinsicContentSize.height))
  }

  private func attributed(width: CGFloat) -> NSAttributedString {
    let font = NSFont.systemFont(ofSize: size, weight: weight)
    let paragraph = NSMutableParagraphStyle()
    if let alignment {
      paragraph.alignment = alignment
    } else {
      // Justify only when the text actually wraps; a single line justified
      // would pin left, so center it. Short replies center, long ones justify.
      let singleLineWidth = (text as NSString).size(withAttributes: [.font: font]).width
      paragraph.alignment = singleLineWidth <= width ? .center : .justified
    }
    paragraph.lineBreakMode = .byWordWrapping
    return NSAttributedString(
      string: text,
      attributes: [
        .paragraphStyle: paragraph,
        .font: font,
        .foregroundColor: NSColor.white.withAlphaComponent(opacity),
      ])
  }
}

/// Reveals Omi's reply at a natural speaking cadence rather than as fast as the
/// model streams tokens, so the words appear roughly in step with the spoken
/// voice. The reveal always paces toward the buffered text and simply *finishes*
/// once the buffer stops growing — it never snaps, so the transition from
/// streaming to the final reply is seamless (no reload).
struct StreamingReplyText: View {
  let fullText: String
  var size: CGFloat = 13
  var opacity: CGFloat = 0.9

  @State private var model = ReplyRevealModel()

  var body: some View {
    TimelineView(.animation) { timeline in
      JustifiedText(
        text: model.revealed(at: timeline.date, full: fullText),
        size: size, opacity: opacity)
    }
  }
}

/// Paces the reply reveal a whole word at a time toward the buffered text.
@MainActor
final class ReplyRevealModel {
  /// ~4 words/sec — keeps pace with (or slightly ahead of) the spoken voice so
  /// the words don't lag the audio. Tune to taste.
  private let charsPerSecond: Double = 20

  private var revealed: Double = 0
  private var lastTime: CFTimeInterval?
  private var lastFullCount = 0

  func revealed(at date: Date, full: String) -> String {
    let count = full.count
    // A shorter buffer means a new turn started — restart the reveal.
    if count < lastFullCount {
      revealed = 0
      lastTime = nil
    }
    lastFullCount = count

    let now = date.timeIntervalSinceReferenceDate
    if let last = lastTime {
      let dt = min(0.1, max(0, now - last))
      revealed = min(Double(count), revealed + charsPerSecond * dt)
    } else {
      // First frame: show the opening word right away so the reveal starts in
      // step with the audio instead of lagging by a word.
      revealed = Double(firstWordLength(of: full))
    }
    lastTime = now

    let shown = Int(revealed)
    guard shown < count else { return full }
    let end = full.index(full.startIndex, offsetBy: shown)
    let prefix = full[..<end]
    // Only reveal whole words so the tail never shows a half-typed word.
    if let lastSpace = prefix.lastIndex(of: " ") {
      return String(prefix[..<lastSpace])
    }
    return String(prefix)
  }

  private func firstWordLength(of text: String) -> Int {
    text.firstIndex(of: " ").map { text.distance(from: text.startIndex, to: $0) } ?? text.count
  }
}
