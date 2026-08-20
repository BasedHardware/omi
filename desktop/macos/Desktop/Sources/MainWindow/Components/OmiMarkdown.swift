import AppKit
@preconcurrency import Foundation
import OmiTheme
@preconcurrency import SwiftUI

/// Omi's stable Markdown renderer for chat and other live-updating text surfaces.
///
/// Parses content once into text, code, and table blocks:
/// - Text segments render as a single `Text(AttributedString)`.
/// - Code blocks render with proper monospace font and background box.
/// - Tables use an Omi-owned `Grid` with fixed decoration. They deliberately
///   avoid geometry preferences.
/// - Thematic breaks render as a quiet, branded section divider rather than
///   leaking their Markdown source (`---`) into a response.
///
/// Live chat Markdown deliberately disables native SwiftUI text selection. Even
/// settled messages still participate in transcript loading, scrolling, window
/// resizing, and parent-state updates. AppKit-backed selection overlays can turn
/// those updates into a non-converging font/intrinsic-size/layout loop.
///
/// Chat bubbles retain whole-message copy actions, while code blocks and tables
/// keep their focused copy controls. A future selectable reading surface must be
/// isolated from the live transcript instead of adding an escape hatch here.
struct OmiMarkdown: View {
  enum Style: Equatable {
    case assistant
    case user
    case onboardingUser
  }

  let text: String
  let style: Style
  let citations: [ChatCitationReference]
  let onOpenCitation: ((ChatCitationReference) -> Void)?
  @Environment(\.fontScale) private var fontScale

  init(
    text: String,
    sender: ChatSender,
    citations: [ChatCitationReference] = [],
    onOpenCitation: ((ChatCitationReference) -> Void)? = nil
  ) {
    self.text = text
    self.style = sender == .user ? .user : .assistant
    self.citations = citations
    self.onOpenCitation = onOpenCitation
  }

  init(text: String, style: Style) {
    self.text = text
    self.style = style
    self.citations = []
    self.onOpenCitation = nil
  }

  var body: some View {
    Group {
      if citations.isEmpty {
        OmiMarkdownContent(text: text, style: style, fontScale: fontScale)
          .equatable()
      } else {
        OmiMarkdownContent(
          text: text,
          style: style,
          fontScale: fontScale,
          citations: citations,
          onOpenCitation: onOpenCitation)
      }
    }
    .textSelection(.disabled)
  }

  static func containsGFMTable(_ content: String) -> Bool {
    OmiMarkdownDocument(markdown: content).blocks.contains {
      if case .table = $0.kind { return true }
      return false
    }
  }
}

/// Keeps parent-only UI feedback (copy checkmarks, hover chrome, ratings) from
/// rebuilding unchanged message content. Combined with the selection-free
/// render boundary above, this prevents AppKit font invalidations from
/// re-entering AttributeGraph while the transcript changes.
struct OmiMarkdownContent: View, Equatable {
  let text: String
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  let document: OmiMarkdownDocument
  let citations: [ChatCitationReference]
  let onOpenCitation: ((ChatCitationReference) -> Void)?

  init(
    text: String,
    style: OmiMarkdown.Style,
    fontScale: CGFloat,
    citations: [ChatCitationReference] = [],
    onOpenCitation: ((ChatCitationReference) -> Void)? = nil
  ) {
    self.text = text
    self.style = style
    self.fontScale = fontScale
    self.document = OmiMarkdownDocument(markdown: text)
    self.citations = citations
    self.onOpenCitation = onOpenCitation
  }

  nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.text == rhs.text && lhs.style == rhs.style && lhs.fontScale == rhs.fontScale
      && lhs.citations == rhs.citations
  }

  var body: some View {
    Group {
      if document.blocks.count == 1, case .text(let content) = document.blocks[0].kind {
        // Single text segment — no VStack overhead
        textView(content)
      } else {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          ForEach(document.blocks) { block in
            switch block.kind {
            case .text(let content):
              textView(content)
            case .codeBlock(let language, let code):
              codeBlockView(code, language: language)
            case .table(let table):
              OmiMarkdownTableView(
                table: table,
                style: style,
                fontScale: fontScale,
                citations: citations,
                onOpenCitation: onOpenCitation)
            case .thematicBreak:
              thematicBreakView()
            }
          }
        }
      }
    }
  }

  // MARK: - Thematic Break

  private func thematicBreakView() -> some View {
    // One rule on one ground: every bubble style sits on the light glass now, so the old
    // white-on-dark divider and the faint grey one collapse into `Ink.separator`.
    return Capsule()
      .fill(Ink.separator)
      .frame(maxWidth: .infinity)
      .frame(height: 1)
      .padding(.vertical, OmiSpacing.sm)
      .accessibilityLabel("Section break")
  }

  @ViewBuilder
  private func textView(_ content: String) -> some View {
    let fontSize = round(14 * fontScale)
    let processed = Self.preprocessText(content)
    let inlineCopy = Self.inlineCopyContent(
      from: processed, style: style, fontSize: fontSize, fontScale: fontScale
    )

    Group {
      if !citations.isEmpty {
        OmiMarkdownCitationContent(
          text: content,
          style: style,
          fontScale: fontScale,
          citations: citations,
          onOpenCitation: onOpenCitation)
      } else if let inlineCopy {
        OmiMarkdownInlineCopyText(
          attributed: inlineCopy.attributed,
          placeholders: inlineCopy.placeholders,
          style: style,
          fontSize: fontSize,
          fontScale: fontScale
        )
      } else if let s = Self.styledAttributedString(
        from: processed, style: style, fontSize: fontSize, fontScale: fontScale
      ) {
        OmiMarkdownChatText(s, fontSize: fontSize)
      } else {
        OmiMarkdownChatText(content, fontSize: fontSize, style: style)
      }
    }
  }

  // MARK: - Code Block (boxed, monospace)

  @ViewBuilder
  private func codeBlockView(_ code: String, language: String?) -> some View {
    OmiMarkdownCodeBlockView(code: code, language: language, style: style, fontScale: fontScale)
  }

  // MARK: - Attributed String Styling

  static func styledAttributedString(
    from processed: String, style: OmiMarkdown.Style, fontSize: CGFloat, fontScale: CGFloat
  ) -> AttributedString? {
    // Every surface that renders assistant text lands here — chat bubbles, the floating bar, the
    // onboarding transcript, table cells, and both the plain and inline-copy paths — so the tilde
    // rule is applied once, at the only point all of them share.
    let source = OmiMarkdownTilde.escapingNonPairDelimiters(processed)

    guard
      var attributed = try? AttributedString(
        markdown: source,
        options: .init(
          allowsExtendedAttributes: true,
          interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
      )
    else { return nil }

    let codeFontSize = round(13 * fontScale)
    let baseColor = baseColor(for: style)
    let linkColor: Color = Ink.accent
    // Inline code is a chip on the glass, not a dark inset. `rowFillHover` is the emphasized wash
    // the rest of the glass vocabulary uses for exactly this — a surface one step up from its host.
    let codeBgColor: Color = Ink.rowFillHover

    attributed.font = .system(size: fontSize)
    attributed.foregroundColor = baseColor

    // Collect ranges for custom styling
    var codeRanges = [Range<AttributedString.Index>]()
    var linkRanges = [Range<AttributedString.Index>]()

    for run in attributed.runs {
      if let intent = run.inlinePresentationIntent, intent.contains(.code) {
        codeRanges.append(run.range)
      }
      if run.link != nil {
        linkRanges.append(run.range)
      }
    }

    for range in codeRanges {
      attributed[range].font = .system(size: codeFontSize, design: .monospaced)
      attributed[range].backgroundColor = codeBgColor
    }

    for range in linkRanges {
      attributed[range].foregroundColor = linkColor
      if style == .user {
        attributed[range].underlineStyle = .single
      }
    }

    return attributed
  }

  /// `internal` rather than `fileprivate` so a test can assert what a surface actually renders —
  /// preprocessing, delimiter handling and styling together — instead of re-implementing the parse
  /// options beside it and drifting from the real path.
  static func inlineAttributedString(
    from content: String,
    style: OmiMarkdown.Style,
    fontSize: CGFloat,
    fontScale: CGFloat
  ) -> AttributedString? {
    styledAttributedString(
      from: preprocessText(content),
      style: style,
      fontSize: fontSize,
      fontScale: fontScale
    )
  }

  fileprivate static func inlineCopyContent(
    from content: String,
    style: OmiMarkdown.Style,
    fontSize: CGFloat,
    fontScale: CGFloat
  ) -> (attributed: AttributedString, placeholders: [OmiMarkdownInlineCode.Placeholder])? {
    guard let masked = OmiMarkdownInlineCode.maskedMarkdown(content),
      let attributed = styledAttributedString(
        from: masked.markdown,
        style: style,
        fontSize: fontSize,
        fontScale: fontScale
      )
    else { return nil }

    return (attributed, masked.placeholders)
  }

  /// The one colour every bubble's prose is drawn in.
  ///
  /// All three styles now render on the light-pinned glass panel, so all three get the same answer.
  /// The assistant bubble draws no ground at all (the glass owns it), and both user bubbles are a
  /// `labelColor` wash *over* that glass — `ChatBubble.messageTextBubble` uses `Ink.rowFillHover`
  /// and onboarding's user bubble uses `glassCard(emphasized:)`. There is no dark ground left in
  /// this renderer for a light-on-dark answer to be correct on.
  ///
  /// It has to be the dynamic label rather than a fixed near-white or near-black. The old palette
  /// was hardcoded dark: `textPrimary` was `#FFFFFF`, which is what made every assistant reply —
  /// and the whole conversational onboarding — white-on-white and invisible; `.user`'s `.white` was
  /// the same bug one bubble over. The switch stays exhaustive rather than collapsing to a bare
  /// `return` so a future genuinely-dark surface has to state its own case.
  /// `internal` rather than `fileprivate` so the contrast guard can call the real function instead
  /// of restating the mapping it is supposed to be checking, and `nonisolated` because it is a pure
  /// value on a `@MainActor` view — something to read, not to draw with.
  nonisolated static func baseColor(for style: OmiMarkdown.Style) -> Color {
    switch style {
    case .assistant, .user, .onboardingUser:
      Ink.primary
    }
  }

  // MARK: - Markdown Preprocessing

  /// Converts block-level elements (headers, asterisk lists) into inline-compatible
  /// form for `AttributedString(markdown:)` with `.inlineOnlyPreservingWhitespace`.
  static func preprocessText(_ text: String) -> String {
    text.components(separatedBy: "\n").map { line in
      var processed = line

      // Convert headers to bold text
      if let match = processed.range(of: #"^#{1,6}\s+"#, options: .regularExpression) {
        let headerText = String(processed[match.upperBound...])
        processed = "**\(headerText)**"
      }

      // Convert "* item" to "• item" so asterisks aren't parsed as italic
      processed = processed.replacingOccurrences(
        of: #"^(\s*)\* "#,
        with: "$1• ",
        options: .regularExpression
      )

      return processed
    }.joined(separator: "\n")
  }
}

/// A fenced code block scrolls horizontally, but it lives inside the vertical
/// transcript scroller. AppKit otherwise lets the inner `NSScrollView` consume
/// an entire trackpad gesture even when the gesture is vertical, stranding the
/// transcript at whichever code block happens to pass under the pointer.
/// Preserve horizontal code navigation while routing vertical intent to the
/// enclosing transcript.
struct VerticalWheelPassthrough: NSViewRepresentable {
  func makeNSView(context: Context) -> NSView {
    let view = NSView(frame: .zero)
    context.coordinator.scheduleAttachment(for: view)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    context.coordinator.scheduleAttachment(for: nsView)
  }

  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    coordinator.stop()
  }

  func makeCoordinator() -> Coordinator { Coordinator() }

  @MainActor
  final class Coordinator {
    private var monitor: Any?
    private weak var innerScrollView: NSScrollView?
    private weak var outerScrollView: NSScrollView?

    func scheduleAttachment(for view: NSView) {
      for delay in [0.0, 0.05] {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self, weak view] in
          guard let self, let view else { return }
          self.install(for: view)
        }
      }
    }

    func install(for view: NSView) {
      guard
        let inner = Self.enclosingScrollView(for: view),
        let outer = Self.enclosingScrollView(above: inner)
      else {
        stop()
        return
      }
      guard innerScrollView !== inner || outerScrollView !== outer else { return }
      stop()
      innerScrollView = inner
      outerScrollView = outer
      monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel]) { [weak self] event in
        self?.handle(event) ?? event
      }
    }

    func handle(_ event: NSEvent) -> NSEvent? {
      guard
        let innerScrollView,
        let outerScrollView,
        event.window === innerScrollView.window,
        abs(event.scrollingDeltaY) >= abs(event.scrollingDeltaX),
        event.scrollingDeltaY != 0
      else { return event }
      let location = innerScrollView.convert(event.locationInWindow, from: nil)
      guard innerScrollView.bounds.contains(location) else { return event }
      NotificationCenter.default.post(
        name: .chatVerticalWheelPassthrough,
        object: outerScrollView,
        userInfo: ["event": event]
      )
      outerScrollView.scrollWheel(with: event)
      return nil
    }

    func stop() {
      if let monitor { NSEvent.removeMonitor(monitor) }
      monitor = nil
      innerScrollView = nil
      outerScrollView = nil
    }

    private static func enclosingScrollView(for view: NSView) -> NSScrollView? {
      var candidate: NSView? = view
      while let current = candidate {
        if let scrollView = current as? NSScrollView { return scrollView }
        candidate = current.superview
      }
      return nil
    }

    private static func enclosingScrollView(above inner: NSScrollView) -> NSScrollView? {
      var candidate = inner.superview
      while let current = candidate {
        if let scrollView = current as? NSScrollView { return scrollView }
        candidate = current.superview
      }
      return nil
    }

    deinit {
      MainActor.assumeIsolated { stop() }
    }
  }
}

struct OmiMarkdownDocument: Equatable {
  struct Block: Identifiable, Equatable {
    enum Kind: Equatable {
      case text(String)
      case codeBlock(language: String?, code: String)
      case table(OmiMarkdownTable)
      case thematicBreak
    }

    let id: Int
    let kind: Kind
  }

  let blocks: [Block]

  init(markdown: String) {
    let lines = markdown.components(separatedBy: "\n")
    var parsedBlocks = [Block]()
    var textLines = [String]()
    var index = 0

    func appendBlock(_ kind: Block.Kind) {
      parsedBlocks.append(Block(id: parsedBlocks.count, kind: kind))
    }

    func flushText() {
      let content =
        textLines
        .joined(separator: "\n")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      if !content.isEmpty {
        appendBlock(.text(content))
      }
      textLines.removeAll(keepingCapacity: true)
    }

    while index < lines.count {
      let trimmed = lines[index].trimmingCharacters(in: .whitespaces)

      if trimmed.hasPrefix("```") {
        let fenceLine = lines[index]
        let languageValue = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
        var codeLines = [String]()
        var cursor = index + 1

        while cursor < lines.count,
          !lines[cursor].trimmingCharacters(in: .whitespaces).hasPrefix("```")
        {
          codeLines.append(lines[cursor])
          cursor += 1
        }

        if cursor < lines.count {
          flushText()
          appendBlock(
            .codeBlock(
              language: languageValue.isEmpty ? nil : languageValue,
              code: codeLines.joined(separator: "\n")
            )
          )
          index = cursor + 1
          continue
        }

        // Preserve an incomplete streaming fence as ordinary text until the
        // closing fence arrives.
        textLines.append(fenceLine)
        textLines.append(contentsOf: codeLines)
        index = lines.count
        continue
      }

      if let parsedTable = OmiMarkdownTable.parse(lines: lines, startingAt: index) {
        flushText()
        appendBlock(.table(parsedTable.table))
        index = parsedTable.nextLineIndex
        continue
      }

      if Self.isThematicBreak(lines[index]) {
        flushText()
        appendBlock(.thematicBreak)
        index += 1
        continue
      }

      textLines.append(lines[index])
      index += 1
    }

    flushText()
    self.blocks = parsedBlocks
  }

  /// CommonMark thematic-break syntax: at least three of the same marker,
  /// optionally separated by spaces or tabs. This intentionally runs after
  /// fenced-code handling so `---` inside a code sample remains literal text.
  static func isThematicBreak(_ line: String) -> Bool {
    let markers = line.filter { !$0.isWhitespace }
    guard markers.count >= 3, let marker = markers.first else { return false }
    guard marker == "-" || marker == "*" || marker == "_" else { return false }
    return markers.allSatisfy { $0 == marker }
  }
}

/// Finds simple, closed inline-code spans so the code itself can be an explicit
/// copy target. Unterminated backticks stay ordinary text while an assistant
/// response is still streaming.
enum OmiMarkdownInlineCode {
  enum Segment: Equatable {
    case text(String)
    case code(String)
  }

  struct Placeholder: Equatable {
    let marker: String
    let code: String
  }

  struct MaskedMarkdown: Equatable {
    let markdown: String
    let placeholders: [Placeholder]
  }

  enum RenderSegment {
    case text(AttributedString)
    case code(String)
  }

  static func containsSpan(in text: String) -> Bool {
    !closedSpans(in: text).isEmpty
  }

  static func segments(in text: String) -> [Segment] {
    var result = [Segment]()

    var textStart = text.startIndex
    for span in closedSpans(in: text) {
      if textStart < span.range.lowerBound {
        result.append(.text(String(text[textStart..<span.range.lowerBound])))
      }
      result.append(.code(span.code))
      textStart = span.range.upperBound
    }

    if textStart < text.endIndex {
      result.append(.text(String(text[textStart..<text.endIndex])))
    }
    if result.isEmpty {
      result.append(.text(text))
    }
    return result
  }

  /// Replaces code spans with plain-text markers before Markdown parsing. This
  /// keeps surrounding emphasis and link delimiters intact while shielding the
  /// copied code from Markdown interpretation.
  static func maskedMarkdown(_ text: String) -> MaskedMarkdown? {
    let spans = closedSpans(in: text)
    guard !spans.isEmpty else { return nil }

    var markdown = String()
    var placeholders = [Placeholder]()
    var textStart = text.startIndex

    for (index, span) in spans.enumerated() {
      markdown += text[textStart..<span.range.lowerBound]

      var marker = "omiInlineCodePlaceholder\(index)"
      while text.contains(marker) || placeholders.contains(where: { $0.marker == marker }) {
        marker.append("x")
      }

      markdown += marker
      placeholders.append(Placeholder(marker: marker, code: span.code))
      textStart = span.range.upperBound
    }

    markdown += text[textStart..<text.endIndex]
    return MaskedMarkdown(markdown: markdown, placeholders: placeholders)
  }

  static func renderSegments(
    in attributed: AttributedString,
    placeholders: [Placeholder]
  ) -> [[RenderSegment]] {
    var lines = [[RenderSegment]]([[]])
    let rendered = String(attributed.characters)
    var renderedStart = rendered.startIndex
    var attributedStart = attributed.startIndex

    func appendText(_ range: Range<AttributedString.Index>) {
      var segmentStart = range.lowerBound
      var cursor = range.lowerBound

      while cursor < range.upperBound {
        if attributed.characters[cursor] == "\n" {
          if segmentStart < cursor {
            lines[lines.count - 1].append(.text(AttributedString(attributed[segmentStart..<cursor])))
          }
          lines.append([])
          cursor = attributed.index(afterCharacter: cursor)
          segmentStart = cursor
        } else {
          cursor = attributed.index(afterCharacter: cursor)
        }
      }

      if segmentStart < range.upperBound {
        lines[lines.count - 1].append(.text(AttributedString(attributed[segmentStart..<range.upperBound])))
      }
    }

    for placeholder in placeholders {
      guard let markerRange = rendered.range(of: placeholder.marker, range: renderedStart..<rendered.endIndex) else {
        continue
      }

      let lowerOffset = rendered.distance(from: rendered.startIndex, to: markerRange.lowerBound)
      let upperOffset = rendered.distance(from: rendered.startIndex, to: markerRange.upperBound)
      let attributedLower = attributed.index(attributed.startIndex, offsetByCharacters: lowerOffset)
      let attributedUpper = attributed.index(attributed.startIndex, offsetByCharacters: upperOffset)

      appendText(attributedStart..<attributedLower)
      lines[lines.count - 1].append(.code(placeholder.code))
      attributedStart = attributedUpper
      renderedStart = markerRange.upperBound
    }

    appendText(attributedStart..<attributed.endIndex)
    return lines
  }

  private struct Span {
    let range: Range<String.Index>
    let code: String
  }

  private static func closedSpans(in text: String) -> [Span] {
    var spans = [Span]()
    var cursor = text.startIndex

    while cursor < text.endIndex {
      guard text[cursor] == "`" else {
        cursor = text.index(after: cursor)
        continue
      }

      var fenceEnd = cursor
      while fenceEnd < text.endIndex, text[fenceEnd] == "`" {
        fenceEnd = text.index(after: fenceEnd)
      }
      let fence = String(text[cursor..<fenceEnd])

      guard let closingFence = text.range(of: fence, range: fenceEnd..<text.endIndex) else {
        cursor = fenceEnd
        continue
      }

      spans.append(
        Span(
          range: cursor..<closingFence.upperBound,
          code: String(text[fenceEnd..<closingFence.lowerBound])
        )
      )
      cursor = closingFence.upperBound
    }

    return spans
  }
}

extension OmiMarkdownInlineCode {
  /// Closed code spans, backtick fences included, as ranges. Everything inside one is literal text.
  static func codeSpanRanges(in text: String) -> [Range<String.Index>] {
    closedSpans(in: text).map(\.range)
  }
}

/// Tilde runs, held to the GFM rule.
///
/// GFM strikethrough is `~~text~~`. Foundation's Markdown parser also honours a *single* `~` as a
/// delimiter, which GFM does not — and a lone tilde is overwhelmingly ordinary text: an approximate
/// price, an approximate duration, a home directory.
///
/// The reported answer was a list of ticket prices. `(~$190)` and `(~$230)` are each flanked by
/// punctuation on both sides, so each tilde can both open and close a run: they paired with *each
/// other*, struck out the whole sentence between them, and swallowed their own tildes on the way, so
/// the prices lost the very character that made them approximate.
///
/// Escaping every tilde run that is not exactly two restores the GFM rule at the delimiter level,
/// which is the level the defect lives at — the content is never rewritten. `~~struck~~` still
/// strikes. A run of three or more was already literal in the underlying parser and stays that way.
enum OmiMarkdownTilde {
  static func escapingNonPairDelimiters(_ text: String) -> String {
    guard text.contains("~") else { return text }

    // A backslash is literal inside a code span, so escaping in there would print `\~` at the user.
    let codeSpans = OmiMarkdownInlineCode.codeSpanRanges(in: text)
    var result = ""
    result.reserveCapacity(text.count)
    var index = text.startIndex

    while index < text.endIndex {
      if let span = codeSpans.first(where: { $0.contains(index) }) {
        result += text[index..<span.upperBound]
        index = span.upperBound
        continue
      }

      guard text[index] == "~" else {
        result.append(text[index])
        index = text.index(after: index)
        continue
      }

      var runEnd = index
      while runEnd < text.endIndex, text[runEnd] == "~" {
        runEnd = text.index(after: runEnd)
      }
      let run = text[index..<runEnd]
      // Exactly two is the one form GFM calls a delimiter; everything else is a character.
      result += run.count == 2 ? String(run) : String(repeating: "\\~", count: run.count)
      index = runEnd
    }

    return result
  }
}

private struct OmiMarkdownInlineCopyText: View {
  let attributed: AttributedString
  let placeholders: [OmiMarkdownInlineCode.Placeholder]
  let style: OmiMarkdown.Style
  let fontSize: CGFloat
  let fontScale: CGFloat

  private var lines: [[OmiMarkdownInlineCode.RenderSegment]] {
    OmiMarkdownInlineCode.renderSegments(in: attributed, placeholders: placeholders)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)) {
      ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
        if line.isEmpty {
          Color.clear.frame(height: fontSize * 0.45)
        } else {
          OmiMarkdownInlineFlowLayout(
            spacing: 0, lineSpacing: OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)
          ) {
            ForEach(Array(line.enumerated()), id: \.offset) { _, segment in
              switch segment {
              case .text(let value):
                inlineText(value)
              case .code(let value):
                OmiMarkdownInlineCodeCopyButton(code: value, style: style, fontScale: fontScale)
              }
            }
          }
        }
      }
    }
  }

  @ViewBuilder
  private func inlineText(_ value: AttributedString) -> some View {
    Text(value)
      .lineSpacing(OmiMarkdownContent.chatLineSpacing(fontSize: fontSize))
      .fixedSize(horizontal: false, vertical: true)
      .if_available_writingToolsNone()
  }
}

/// The one surface in this file that keeps a dark ground, and the only light-on-dark text left here.
///
/// It is a transient floating toast, not hosted page content — an *opaque* capsule that paints its
/// own ground and therefore carries its own contrast wherever it lands. That is the same exemption
/// the glass vocabulary already grants an opaque popover, and it is why this survived the light
/// conversion while every white-on-glass bubble colour around it did not.
private struct OmiMarkdownCopyToast: View {
  let fontScale: CGFloat

  var body: some View {
    Text("Copied")
      .font(.system(size: round(11 * fontScale), weight: .semibold))
      .foregroundColor(.white)
      .padding(.horizontal, 7)
      .padding(.vertical, 3)
      .background(Color.black.opacity(0.82))
      .clipShape(Capsule())
      .overlay(Capsule().stroke(.white.opacity(0.22), lineWidth: 1))
      .accessibilityElement(children: .ignore)
      .accessibilityLabel("Copied")
      .allowsHitTesting(false)
  }
}

private struct OmiMarkdownInlineCodeCopyButton: View {
  let code: String
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  @State private var copied = false
  @State private var copyGeneration = 0

  private var backgroundColor: Color {
    copied ? Ink.hairline : Ink.rowFillHover
  }

  var body: some View {
    Button {
      copyCode()
    } label: {
      Text(code)
        .font(.system(size: round(13 * fontScale), design: .monospaced))
        .foregroundColor(OmiMarkdownContent.baseColor(for: style))
        .lineLimit(1)
        .truncationMode(.middle)
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .background(backgroundColor)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(
          RoundedRectangle(cornerRadius: 4)
            .stroke(copied ? Ink.accent.opacity(0.7) : .clear, lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
    .overlay(alignment: .topTrailing) {
      if copied {
        OmiMarkdownCopyToast(fontScale: fontScale)
          .offset(x: 8, y: -18)
      }
    }
    .zIndex(copied ? 1 : 0)
    .accessibilityLabel(copied ? "Copied" : "Copy inline code")
    .accessibilityValue(code)
    .help(copied ? "Copied" : "Click to copy code")
  }

  private func copyCode() {
    guard OmiMarkdownClipboard.copy(code) else {
      copied = false
      return
    }

    copied = true
    copyGeneration += 1
    let generation = copyGeneration
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
      guard copyGeneration == generation else { return }
      copied = false
    }
  }
}

struct OmiMarkdownInlineFlowLayout: Layout {
  var spacing: CGFloat
  var lineSpacing: CGFloat

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) -> CGSize {
    let result = layout(in: proposal.width ?? .greatestFiniteMagnitude, subviews: subviews)
    return result.size
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) {
    let result = layout(in: bounds.width, subviews: subviews)
    for (index, subview) in subviews.enumerated() {
      subview.place(
        at: CGPoint(x: bounds.minX + result.positions[index].x, y: bounds.minY + result.positions[index].y),
        proposal: result.proposals[index]
      )
    }
  }

  private func layout(in maxWidth: CGFloat, subviews: Subviews) -> (
    size: CGSize, positions: [CGPoint], proposals: [ProposedViewSize]
  ) {
    var positions = [CGPoint]()
    var proposals = [ProposedViewSize]()
    var cursor = CGPoint.zero
    var rowHeight: CGFloat = 0
    var totalWidth: CGFloat = 0

    for subview in subviews {
      var proposal = ProposedViewSize.unspecified
      var size = subview.sizeThatFits(proposal)
      if size.width > maxWidth {
        proposal = ProposedViewSize(width: maxWidth, height: nil)
        size = subview.sizeThatFits(proposal)
      }

      if cursor.x > 0, cursor.x + size.width > maxWidth {
        cursor.x = 0
        cursor.y += rowHeight + lineSpacing
        rowHeight = 0
      }

      positions.append(cursor)
      proposals.append(proposal)
      rowHeight = max(rowHeight, size.height)
      totalWidth = max(totalWidth, cursor.x + size.width)
      cursor.x += size.width + spacing
    }

    return (
      CGSize(width: totalWidth, height: cursor.y + rowHeight),
      positions,
      proposals
    )
  }
}

/// Citation-aware projection used only for settled assistant answers with typed provenance. The
/// popover lives outside transcript layout, so showing a preview cannot move the scroll anchor.
private struct OmiMarkdownCitationContent: View {
  let text: String
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  let citations: [ChatCitationReference]
  let onOpenCitation: ((ChatCitationReference) -> Void)?

  private var referencesByOrdinal: [Int: ChatCitationReference] {
    Dictionary(citations.map { ($0.ordinal, $0) }, uniquingKeysWith: { first, _ in first })
  }

  var body: some View {
    let fontSize = round(14 * fontScale)
    let source = OmiMarkdownContent.preprocessText(text)
    if let citationMask = ChatCitationMask.mask(source, references: referencesByOrdinal),
      let interactiveMask = ChatCitationMask.maskInlineCode(in: citationMask),
      let attributed = OmiMarkdownContent.styledAttributedString(
        from: interactiveMask.markdown, style: style, fontSize: fontSize, fontScale: fontScale)
    {
      VStack(alignment: .leading, spacing: OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)) {
        ForEach(
          Array(
            ChatCitationMask.units(
              in: attributed,
              citationMarkers: citationMask.markers,
              codePlaceholders: interactiveMask.codePlaceholders
            ).enumerated()),
          id: \.offset
        ) {
          _, line in
          if line.isEmpty {
            Color.clear.frame(height: fontSize * 0.45)
          } else {
            OmiMarkdownInlineFlowLayout(
              spacing: 0, lineSpacing: OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)
            ) {
              ForEach(Array(line.enumerated()), id: \.offset) { _, unit in
                switch unit {
                case .text(let value):
                  Text(value)
                    .lineSpacing(OmiMarkdownContent.chatLineSpacing(fontSize: fontSize))
                    .fixedSize(horizontal: false, vertical: true)
                    .if_available_writingToolsNone()
                case .citation(let reference):
                  ChatCitationToken(
                    reference: reference,
                    fontScale: fontScale,
                    onOpen: { onOpenCitation?($0) })
                case .code(let value):
                  OmiMarkdownInlineCodeCopyButton(
                    code: value,
                    style: style,
                    fontScale: fontScale)
                }
              }
            }
          }
        }
      }
    } else {
      // Type-erased on purpose (#11573). `OmiMarkdownContent.body` reaches this view through
      // `textView` and `OmiMarkdownTableView`, so naming `OmiMarkdownContent` here closes a cycle
      // in the *static* view-type graph. SwiftUI's `View._viewListCount(inputs:)` walks that graph
      // by type, never evaluating a body, so no value-level guard bounds it: on macOS 15 a
      // `ScrollView`/`LazyVStack` host recursed until the main thread wrote past its stack guard
      // page and died with SIGSEGV. `AnyView` is the terminator — it resolves its count
      // dynamically, which cuts both cycles here and leaves the graph acyclic.
      AnyView(OmiMarkdownContent(text: text, style: style, fontScale: fontScale))
    }
  }
}

enum ChatCitationMask {
  struct Marker {
    let placeholder: String
    let reference: ChatCitationReference
  }

  struct Masked {
    let markdown: String
    let markers: [Marker]
  }

  struct InteractiveMask {
    let markdown: String
    let codePlaceholders: [OmiMarkdownInlineCode.Placeholder]
  }

  enum Unit {
    case text(AttributedString)
    case citation(ChatCitationReference)
    case code(String)
  }

  static func mask(_ text: String, references: [Int: ChatCitationReference]) -> Masked? {
    guard !references.isEmpty else { return nil }
    var markdown = ""
    var markers = [Marker]()
    var cursor = text.startIndex

    for match in ChatCitationMarkup.markerMatches(
      in: text, pattern: ChatCitationMarkup.numericMarkerOrMarkdownLinkPattern)
    {
      guard let reference = references[match.ordinal] else { continue }
      markdown += text[cursor..<match.range.lowerBound]
      var placeholder = "omiCitationPlaceholder\(markers.count)"
      while text.contains(placeholder) { placeholder.append("x") }
      markdown += placeholder
      markers.append(Marker(placeholder: placeholder, reference: reference))
      cursor = match.range.upperBound
    }
    guard !markers.isEmpty else { return nil }
    markdown += text[cursor...]
    return Masked(markdown: markdown, markers: markers)
  }

  static func maskInlineCode(in citationMask: Masked) -> InteractiveMask? {
    guard let codeMask = OmiMarkdownInlineCode.maskedMarkdown(citationMask.markdown) else {
      return InteractiveMask(markdown: citationMask.markdown, codePlaceholders: [])
    }
    return InteractiveMask(
      markdown: codeMask.markdown,
      codePlaceholders: codeMask.placeholders)
  }

  static func units(
    in attributed: AttributedString,
    citationMarkers: [Marker],
    codePlaceholders: [OmiMarkdownInlineCode.Placeholder]
  ) -> [[Unit]] {
    enum PlaceholderUnit {
      case citation(ChatCitationReference)
      case code(String)
    }

    var lines: [[Unit]] = [[]]
    let rendered = String(attributed.characters)
    var renderedStart = rendered.startIndex
    var attributedStart = attributed.startIndex

    let placeholders: [(marker: String, unit: PlaceholderUnit)] =
      citationMarkers.map { ($0.placeholder, .citation($0.reference)) }
      + codePlaceholders.map { ($0.marker, .code($0.code)) }

    let orderedPlaceholders = placeholders.compactMap {
      placeholder -> (
        marker: String, unit: PlaceholderUnit, range: Range<String.Index>
      )? in
      guard let range = rendered.range(of: placeholder.marker) else { return nil }
      return (placeholder.marker, placeholder.unit, range)
    }.sorted { $0.range.lowerBound < $1.range.lowerBound }

    func appendText(_ range: Range<AttributedString.Index>) {
      var segmentStart = range.lowerBound
      var cursor = range.lowerBound
      while cursor < range.upperBound {
        let character = attributed.characters[cursor]
        let next = attributed.index(afterCharacter: cursor)
        if character == "\n" {
          if segmentStart < cursor { appendWords(segmentStart..<cursor) }
          lines.append([])
          segmentStart = next
        } else if character.isWhitespace {
          appendWords(segmentStart..<next)
          segmentStart = next
        }
        cursor = next
      }
      if segmentStart < range.upperBound { appendWords(segmentStart..<range.upperBound) }
    }

    func appendWords(_ range: Range<AttributedString.Index>) {
      guard range.lowerBound < range.upperBound else { return }
      lines[lines.count - 1].append(.text(AttributedString(attributed[range])))
    }

    for placeholder in orderedPlaceholders {
      let markerRange = placeholder.range
      guard markerRange.lowerBound >= renderedStart else { continue }
      let lowerOffset = rendered.distance(from: rendered.startIndex, to: markerRange.lowerBound)
      let upperOffset = rendered.distance(from: rendered.startIndex, to: markerRange.upperBound)
      let lower = attributed.index(attributed.startIndex, offsetByCharacters: lowerOffset)
      let upper = attributed.index(attributed.startIndex, offsetByCharacters: upperOffset)
      appendText(attributedStart..<lower)
      switch placeholder.unit {
      case .citation(let reference):
        lines[lines.count - 1].append(.citation(reference))
      case .code(let value):
        lines[lines.count - 1].append(.code(value))
      }
      attributedStart = upper
      renderedStart = markerRange.upperBound
    }
    appendText(attributedStart..<attributed.endIndex)
    return lines
  }
}

private struct ChatCitationToken: View {
  let reference: ChatCitationReference
  let fontScale: CGFloat
  let onOpen: (ChatCitationReference) -> Void

  @State private var isHovering = false
  @State private var isPreviewHovering = false
  @State private var isPreviewPresented = false
  @State private var hoverGeneration = 0
  @FocusState private var isFocused: Bool

  var body: some View {
    Button {
      guard reference.canOpen else { return }
      isPreviewPresented = false
      onOpen(reference)
    } label: {
      Text("[\(reference.ordinal)]")
        .font(.system(size: round(11 * fontScale), weight: .semibold, design: .rounded))
        .foregroundStyle(reference.canOpen ? Ink.accent : Ink.tertiary)
        .padding(.horizontal, 3)
        .padding(.vertical, 2)
        .background(isHovering || isFocused ? Ink.rowFillHover : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .disabled(!reference.canOpen)
    .focused($isFocused)
    .onHover { hovering in
      isHovering = hovering
      hoverGeneration += 1
      let generation = hoverGeneration
      if hovering {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.28) {
          guard isHovering, generation == hoverGeneration else { return }
          isPreviewPresented = true
        }
      } else {
        schedulePreviewDismiss(generation: generation)
      }
    }
    .onChange(of: isFocused) { _, focused in
      if focused { isPreviewPresented = true } else if !isHovering { isPreviewPresented = false }
    }
    .popover(isPresented: $isPreviewPresented, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
      ChatCitationPreview(
        reference: reference,
        fontScale: fontScale,
        onOpen: {
          isPreviewPresented = false
          onOpen(reference)
        }
      )
      .onHover { hovering in
        isPreviewHovering = hovering
        hoverGeneration += 1
        if !hovering {
          schedulePreviewDismiss(generation: hoverGeneration)
        }
      }
    }
    .accessibilityLabel("Source \(reference.ordinal): \(reference.displayTitle)")
    .accessibilityHint(reference.canOpen ? "Open this source" : "This source is unavailable")
    .accessibilityIdentifier("query-shell-citation-\(reference.ordinal)")
    .help("Source \(reference.ordinal): \(reference.displayTitle)")
  }

  private func schedulePreviewDismiss(generation: Int) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
      guard !isHovering, !isPreviewHovering, generation == hoverGeneration, !isFocused else { return }
      isPreviewPresented = false
    }
  }
}

private struct ChatCitationPreview: View {
  let reference: ChatCitationReference
  let fontScale: CGFloat
  let onOpen: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Label(reference.kind.title, systemImage: reference.kind.systemImage)
        .font(.system(size: round(11 * fontScale), weight: .semibold))
        .foregroundStyle(Ink.secondary)
      Text(reference.displayTitle)
        .font(.system(size: round(14 * fontScale), weight: .semibold))
        .foregroundStyle(Ink.primary)
        .lineLimit(2)
      Text(reference.displayPreview)
        .font(.system(size: round(12 * fontScale)))
        .foregroundStyle(Ink.secondary)
        .lineLimit(4)
      if let metadata = [reference.appName, reference.createdAt]
        .compactMap({ $0?.trimmingCharacters(in: .whitespacesAndNewlines) })
        .filter({ !$0.isEmpty }).joined(separator: " · ").nilIfEmpty
      {
        Text(metadata)
          .font(.system(size: round(10 * fontScale)))
          .foregroundStyle(Ink.tertiary)
      }
      if reference.canOpen {
        Button(action: onOpen) {
          Label("Open \(reference.kind.title)", systemImage: "arrow.up.right")
            .font(.system(size: round(11 * fontScale), weight: .semibold))
        }
        .buttonStyle(.plain)
        .foregroundStyle(Ink.accent)
        .accessibilityHint("Open the cited source")
      }
    }
    .padding(OmiSpacing.md)
    .frame(width: 330, alignment: .leading)
    .accessibilityElement(children: .contain)
  }
}

extension String {
  fileprivate var nilIfEmpty: String? { isEmpty ? nil : self }
}

private enum OmiMarkdownClipboard {
  @discardableResult
  static func copy(_ text: String) -> Bool {
    NSPasteboard.general.clearContents()
    return NSPasteboard.general.setString(text, forType: .string)
  }
}

struct OmiMarkdownTable: Equatable {
  enum ColumnAlignment: Equatable {
    case leading
    case center
    case trailing

    var swiftUIAlignment: Alignment {
      switch self {
      case .leading:
        .leading
      case .center:
        .center
      case .trailing:
        .trailing
      }
    }

    var topAlignment: Alignment {
      switch self {
      case .leading:
        .topLeading
      case .center:
        .top
      case .trailing:
        .topTrailing
      }
    }
  }

  let header: [String]
  let alignments: [ColumnAlignment]
  let rows: [[String]]

  fileprivate static func parse(
    lines: [String],
    startingAt startIndex: Int
  ) -> (table: OmiMarkdownTable, nextLineIndex: Int)? {
    guard startIndex + 1 < lines.count else { return nil }

    let header = cells(in: lines[startIndex])
    let separatorCells = cells(in: lines[startIndex + 1])
    guard header.count >= 2, header.count == separatorCells.count else { return nil }

    let parsedAlignments = separatorCells.compactMap(parseAlignment)
    guard parsedAlignments.count == header.count else { return nil }

    var rows = [[String]]()
    var cursor = startIndex + 2

    while cursor < lines.count {
      let line = lines[cursor]
      guard !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { break }
      let rowCells = cells(in: line)
      guard rowCells.count >= 2 else { break }

      rows.append(normalize(rowCells, columnCount: header.count))
      cursor += 1
    }

    return (
      OmiMarkdownTable(
        header: header,
        alignments: parsedAlignments,
        rows: rows
      ),
      cursor
    )
  }

  fileprivate static func cells(in line: String) -> [String] {
    var body = line.trimmingCharacters(in: .whitespaces)
    if body.first == "|" {
      body.removeFirst()
    }
    if body.last == "|", !body.hasSuffix("\\|") {
      body.removeLast()
    }

    var cells = [String]()
    var current = ""
    var inInlineCode = false
    let characters = Array(body)
    var index = 0

    while index < characters.count {
      let character = characters[index]

      if character == "\\", index + 1 < characters.count, characters[index + 1] == "|" {
        current.append("|")
        index += 2
        continue
      }

      if character == "`" {
        inInlineCode.toggle()
        current.append(character)
        index += 1
        continue
      }

      if character == "|", !inInlineCode {
        cells.append(current.trimmingCharacters(in: .whitespaces))
        current = ""
      } else {
        current.append(character)
      }
      index += 1
    }

    cells.append(current.trimmingCharacters(in: .whitespaces))
    return cells
  }

  private static func parseAlignment(_ value: String) -> ColumnAlignment? {
    var marker = value.trimmingCharacters(in: .whitespaces)
    let hasLeadingColon = marker.first == ":"
    let hasTrailingColon = marker.last == ":"

    if hasLeadingColon {
      marker.removeFirst()
    }
    if hasTrailingColon, !marker.isEmpty {
      marker.removeLast()
    }

    guard marker.count >= 3, marker.allSatisfy({ $0 == "-" }) else { return nil }

    switch (hasLeadingColon, hasTrailingColon) {
    case (true, true):
      return .center
    case (false, true):
      return .trailing
    default:
      return .leading
    }
  }

  private static func normalize(_ cells: [String], columnCount: Int) -> [String] {
    if cells.count == columnCount {
      return cells
    }
    if cells.count > columnCount {
      return Array(cells.prefix(columnCount))
    }
    return cells + Array(repeating: "", count: columnCount - cells.count)
  }
}

private struct OmiMarkdownTableView: View {
  let table: OmiMarkdownTable
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  let citations: [ChatCitationReference]
  let onOpenCitation: ((ChatCitationReference) -> Void)?

  private var allRows: [[String]] {
    [table.header] + table.rows
  }

  /// The grid itself. This was a white hairline in *both* branches — legible only because the page
  /// behind it was near-black, and an invisible white-on-white grid the moment the panel went light.
  private var borderColor: Color {
    Ink.separator
  }

  var body: some View {
    ScrollView(.horizontal, showsIndicators: true) {
      tableGrid
    }
    .background(VerticalWheelPassthrough())
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityLabel("Scrollable markdown table")
    .accessibilityHint("Scroll horizontally to view additional columns")
  }

  private var tableGrid: some View {
    Grid(alignment: .topLeading, horizontalSpacing: 1, verticalSpacing: 1) {
      ForEach(Array(allRows.enumerated()), id: \.offset) { rowIndex, row in
        GridRow(alignment: .top) {
          ForEach(Array(row.enumerated()), id: \.offset) { columnIndex, content in
            cell(content, row: rowIndex, column: columnIndex)
          }
        }
      }
    }
    .padding(1)
    .background(borderColor)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .stroke(borderColor, lineWidth: 1)
    )
    .fixedSize(horizontal: false, vertical: true)
    // Tables do not create one AppKit SelectionOverlay per cell inside the
    // live transcript. Copy remains available only on fenced code blocks.
    .textSelection(.disabled)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("omi-markdown-table")
  }

  @ViewBuilder
  private func cell(_ content: String, row: Int, column: Int) -> some View {
    let fontSize = round(14 * fontScale)
    let styled = OmiMarkdownContent.inlineAttributedString(
      from: content,
      style: style,
      fontSize: fontSize,
      fontScale: fontScale
    )
    let columnAlignment = table.alignments[column]
    let metrics = columnMetrics(column, alignment: columnAlignment)

    Group {
      if !citations.isEmpty {
        OmiMarkdownCitationContent(
          text: content,
          style: style,
          fontScale: fontScale,
          citations: citations,
          onOpenCitation: onOpenCitation)
      } else if let inlineCopy = OmiMarkdownContent.inlineCopyContent(
        from: content,
        style: style,
        fontSize: fontSize,
        fontScale: fontScale
      ) {
        OmiMarkdownInlineCopyText(
          attributed: inlineCopy.attributed,
          placeholders: inlineCopy.placeholders,
          style: style,
          fontSize: fontSize,
          fontScale: fontScale
        )
      } else if let styled {
        OmiMarkdownChatText(styled, fontSize: fontSize)
      } else {
        OmiMarkdownChatText(content, fontSize: fontSize, style: style)
      }
    }
    .fontWeight(row == 0 ? .semibold : .regular)
    .frame(
      minWidth: metrics.minWidth,
      idealWidth: metrics.idealWidth,
      maxWidth: metrics.maxWidth,
      alignment: columnAlignment.topAlignment
    )
    .padding(.vertical, row == 0 ? OmiSpacing.sm : OmiSpacing.xs)
    .padding(.horizontal, OmiSpacing.md)
    .frame(maxHeight: .infinity, alignment: columnAlignment.topAlignment)
    .background(rowBackground(row))
    .if_available_writingToolsNone()
  }

  /// Header, then zebra banding, in the glass washes — one ladder for every bubble style, because
  /// they all sit on the same light ground now.
  private func rowBackground(_ row: Int) -> Color {
    if row == 0 {
      return Ink.rowFillHover
    }
    return row.isMultiple(of: 2) ? Ink.rowFill : .clear
  }

  private func columnMetrics(
    _ column: Int,
    alignment: OmiMarkdownTable.ColumnAlignment
  ) -> (minWidth: CGFloat, idealWidth: CGFloat, maxWidth: CGFloat) {
    switch alignment {
    case .trailing:
      return (72, 96, 140)
    case .center:
      return (96, 128, 180)
    case .leading where column == 0:
      return (100, 140, 220)
    case .leading:
      return (120, 180, 280)
    }
  }
}

/// A whole code card is its copy target, avoiding a tiny, easy-to-miss header
/// action and preserving the selection-free live transcript contract.
private struct OmiMarkdownCodeBlockView: View {
  let code: String
  let language: String?
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  @State private var copied = false
  @State private var copyGeneration = 0

  private var backgroundColor: Color {
    Ink.rowFillHover
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      HStack(spacing: OmiSpacing.xs) {
        if let language {
          Text(language)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        Spacer(minLength: 0)
        Image(systemName: copied ? "checkmark" : "doc.on.doc")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(copied ? Ink.listeningGreen : Ink.secondary)
          .frame(width: round(16 * fontScale), height: round(16 * fontScale))
      }

      ScrollView(.horizontal, showsIndicators: false) {
        Text(code)
          .font(.system(size: round(13 * fontScale), design: .monospaced))
          .foregroundColor(OmiMarkdownContent.baseColor(for: style))
          .if_available_writingToolsNone()
          .background(VerticalWheelPassthrough())
      }
    }
    .padding(OmiSpacing.md)
    .background(backgroundColor)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))
    .contentShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))
    .overlay(alignment: .topTrailing) {
      if copied {
        OmiMarkdownCopyToast(fontScale: fontScale)
          .padding(.top, OmiSpacing.md + OmiSpacing.xs)
          .padding(.trailing, OmiSpacing.md)
      }
    }
    .onTapGesture { copyCode() }
    .accessibilityElement(children: .combine)
    .accessibilityAddTraits(.isButton)
    .accessibilityLabel(copied ? "Copied" : "Copy code block")
    .accessibilityHint("Click anywhere in the code block to copy")
    .accessibilityAction { copyCode() }
    .help(copied ? "Copied" : "Click anywhere to copy code")
  }

  private func copyCode() {
    guard OmiMarkdownClipboard.copy(code) else {
      copied = false
      return
    }

    copied = true
    copyGeneration += 1
    let generation = copyGeneration
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
      guard copyGeneration == generation else { return }
      copied = false
    }
  }
}
