import CoreGraphics
import Foundation

/// One user prompt on the transcript timeline: the text the hover card shows,
/// and where the prompt sits in the transcript as a fraction of the document's
/// scrollable height.
struct ChatPromptMark: Identifiable, Equatable {
  let id: String
  let prompt: String
  let reply: String
  /// 0 at the top of the document, 1 at its foot.
  let fraction: CGFloat
}

/// One user prompt's text, paired with the reply it drew. Derived from the
/// transcript alone, so it survives every scroll and every point the document
/// grows while omi is answering.
struct ChatPromptSource: Identifiable, Equatable {
  let id: String
  let prompt: String
  let reply: String
}

/// Turns a transcript plus whatever row geometry has been measured into the
/// marks the timeline draws. Pure, so the whole placement story is exercised
/// without a scroll view.
///
/// The two halves are deliberately separate. Reading the transcript's text is
/// linear in the whole conversation; placing the marks is arithmetic over the
/// prompts alone. Only the second half reruns as the document grows.
enum ChatPromptTimelineModel {
  /// The timeline needs a second prompt before it says anything a reader could
  /// not already see.
  static let minimumMarks = 2

  /// One entry per user turn, each carrying the assistant turn that answered it.
  static func sources(messages: [ChatMessage]) -> [ChatPromptSource] {
    let prompts = messages.enumerated().filter { $0.element.sender == .user }
    guard prompts.count >= minimumMarks else { return [] }
    return prompts.map { index, message in
      ChatPromptSource(
        id: message.id,
        prompt: preview(message.text),
        reply: preview(reply(after: index, in: messages))
      )
    }
  }

  /// Places each prompt at its real position in the document.
  ///
  /// `LazyVStack` lays out only the rows near the viewport, so a long transcript
  /// that has not been scrolled yet has measured offsets for a handful of its
  /// prompts and none for the rest. Dropping the unmeasured ones would make
  /// ticks wink in and out as the reader scrolls, which is worse than a slightly
  /// wrong position — so unmeasured prompts are interpolated between their
  /// nearest measured neighbours. Every prompt therefore has a tick from the
  /// first frame, and each one moves at most once, to its true position, when
  /// the row it stands for is finally laid out.
  static func marks(
    sources: [ChatPromptSource],
    offsets: [String: CGFloat],
    documentHeight: CGFloat
  ) -> [ChatPromptMark] {
    guard sources.count >= minimumMarks else { return [] }

    let resolved = resolvedOffsets(
      measured: sources.map { offsets[$0.id] },
      documentHeight: documentHeight
    )

    return sources.enumerated().map { position, source in
      ChatPromptMark(
        id: source.id,
        prompt: source.prompt,
        reply: source.reply,
        fraction: documentHeight > 0
          ? clamp(resolved[position] / documentHeight)
          : evenFraction(position, of: sources.count)
      )
    }
  }

  /// The mark the reader is currently on: the last prompt at or above the
  /// reading line, which sits a third of the way down the viewport rather than
  /// at its very top. A prompt scrolled just past the top edge is still the one
  /// being read; switching the moment it clips would make the marker flicker
  /// between two ticks on every small scroll.
  static let readingLine: CGFloat = 0.33

  static func activeMarkID(
    marks: [ChatPromptMark],
    viewportTopFraction: CGFloat,
    viewportHeightFraction: CGFloat
  ) -> String? {
    guard !marks.isEmpty else { return nil }
    let probe = viewportTopFraction + viewportHeightFraction * readingLine
    return marks.last(where: { $0.fraction <= probe })?.id ?? marks.first?.id
  }

  /// The mark ⌘↑ / ⌘↓ lands on. Stepping from nothing enters at the end the
  /// reader is travelling towards, so the first press always moves.
  static func steppedMarkID(marks: [ChatPromptMark], from current: String?, by step: Int)
    -> String?
  {
    guard !marks.isEmpty, step != 0 else { return nil }
    guard let current, let index = marks.firstIndex(where: { $0.id == current }) else {
      return step < 0 ? marks.last?.id : marks.first?.id
    }
    let next = index + step
    guard marks.indices.contains(next) else { return nil }
    return marks[next].id
  }

  // MARK: - Internals

  /// The assistant turn that answered a prompt, skipping any further user turns
  /// (a reader can send twice before omi replies, and the second prompt owns
  /// that reply).
  private static func reply(after promptIndex: Int, in messages: [ChatMessage]) -> String {
    for message in messages[(promptIndex + 1)...] {
      if message.sender == .user { return "" }
      if !message.text.isEmpty { return message.text }
    }
    return ""
  }

  /// A monotonic offset for every prompt: measured where the row was laid out,
  /// interpolated between the nearest measured neighbours where it was not.
  private static func resolvedOffsets(measured: [CGFloat?], documentHeight: CGFloat) -> [CGFloat] {
    let count = measured.count
    let known = measured.enumerated().compactMap { index, value in
      value.map { (index: index, offset: $0) }
    }
    guard !known.isEmpty, documentHeight > 0 else {
      return (0..<count).map { evenFraction($0, of: count) * max(documentHeight, 0) }
    }

    var resolved = [CGFloat](repeating: 0, count: count)
    // Before the first measured row and after the last, the only anchors are the
    // document's own ends.
    var anchors = [(index: -1, offset: CGFloat(0))]
    anchors.append(contentsOf: known)
    anchors.append((index: count, offset: documentHeight))

    for pair in zip(anchors, anchors.dropFirst()) {
      let (low, high) = pair
      let span = high.index - low.index
      guard span > 0 else { continue }
      for index in (low.index + 1)...high.index where index < count {
        if let value = measured[index] {
          resolved[index] = value
        } else {
          let travelled = CGFloat(index - low.index) / CGFloat(span)
          resolved[index] = low.offset + (high.offset - low.offset) * travelled
        }
      }
    }
    // A measured row is authoritative even where interpolation disagreed.
    for (index, value) in known { resolved[index] = value }
    return resolved
  }

  /// Fallback spacing before anything has been measured. Inset from both ends so
  /// a two-prompt transcript does not pin one tick to each extreme.
  private static func evenFraction(_ position: Int, of count: Int) -> CGFloat {
    guard count > 0 else { return 0 }
    return (CGFloat(position) + 0.5) / CGFloat(count)
  }

  private static func clamp(_ value: CGFloat) -> CGFloat {
    min(max(value, 0), 1)
  }

  /// One line of plain text for the hover card. Markdown fences, list bullets
  /// and hard wraps all render as noise at 11pt on two lines.
  private static func preview(_ text: String) -> String {
    text
      .split(whereSeparator: \.isWhitespace)
      .joined(separator: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
