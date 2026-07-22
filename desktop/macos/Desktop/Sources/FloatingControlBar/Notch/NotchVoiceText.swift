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
    // Justify only when the text actually wraps; a single line justified would
    // pin left, so center it. Result: short replies center, long ones justify
    // to clean edges.
    let singleLineWidth = (text as NSString).size(withAttributes: [.font: font]).width
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = singleLineWidth <= width ? .center : .justified
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
  /// ~3 words/sec — close to a natural TTS speaking rate. Tune to taste.
  private let charsPerSecond: Double = 15

  private var revealed: Double = 0
  private var lastTime: CFTimeInterval?
  private var lastFullCount = 0

  func revealed(at date: Date, full: String) -> String {
    let count = full.count
    // A shorter buffer means a new turn started — restart the reveal.
    if count < lastFullCount { revealed = 0 }
    lastFullCount = count

    let now = date.timeIntervalSinceReferenceDate
    let dt = lastTime.map { min(0.1, max(0, now - $0)) } ?? 0
    lastTime = now
    revealed = min(Double(count), revealed + charsPerSecond * dt)

    let shown = Int(revealed)
    guard shown < count else { return full }
    let end = full.index(full.startIndex, offsetBy: shown)
    let prefix = full[..<end]
    // Only reveal whole words so the tail never shows a half-typed word.
    if let lastSpace = prefix.lastIndex(of: " ") {
      return String(prefix[..<lastSpace])
    }
    return ""
  }
}
