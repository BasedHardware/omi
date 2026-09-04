import AppKit
import OmiTheme
import SwiftUI

/// **Selection where the words already are.**
///
/// The transcript used to answer "let me copy that date out of your answer"
/// with a popover: `ChatSelectableTextPopover` re-printed the message, in raw
/// Markdown, in a floating box beside the row the reader was already looking
/// at. It was the only remedy available, because SwiftUI's own selection is
/// permanently barred here — PR #10834 put SwiftUI's own native selection back
/// on settled rows and reopened FC-selection-overlay-layout-loop in Omi Beta
/// 0.12.146, with every sampled main-thread stack in `SelectionOverlay`,
/// `setFont` and AttributeGraph while memory climbed without bound.
///
/// That boundary is about `SelectionOverlay`, not about selection. An
/// `NSTextView` *is* its own selection: one view owns one selection, a parent
/// rebuild replaces a string instead of installing a second overlay, and
/// nothing per-`Text` is mounted at all. `ChatSelectableTextPopover` already
/// said so in its own header — it just kept that view outside the transcript.
/// This brings it inside, so a reader drags across the answer in place, on
/// their own turns as much as Omi's, and `⌘C` copies exactly what they
/// highlighted.
///
/// `.github/scripts/check_chat_selection_boundary.py` still forbids SwiftUI
/// selection in the live transcript, and now also forbids it here.
enum ChatSelectableProse {
  /// The scheme the transcript's own citation markers travel under. It is not
  /// openable by the system: the click is handled in-process and the URL never
  /// reaches `NSWorkspace`.
  static let citationScheme = "omi-citation"

  static func citationOrdinal(from url: URL) -> Int? {
    guard url.scheme == citationScheme else { return nil }
    return Int(url.host ?? url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
  }

  /// The one place chat prose becomes AppKit text.
  ///
  /// It parses exactly what `OmiMarkdownContent.styledAttributedString` parses —
  /// same preprocessing, same tilde rule, same inline-only syntax — and then
  /// maps the parsed *intents* rather than SwiftUI's own attributes, which do
  /// not bridge. Anything this cannot represent (a table, a fenced block) never
  /// reaches here; those keep their SwiftUI renderers and their copy controls.
  static func attributedString(
    markdown source: String,
    style: OmiMarkdown.Style,
    fontSize: CGFloat,
    fontScale: CGFloat,
    citationOrdinals: Set<Int> = []
  ) -> NSAttributedString? {
    let processed = OmiMarkdownContent.preprocessText(source)
    let escaped = OmiMarkdownTilde.escapingNonPairDelimiters(processed)
    guard
      let parsed = try? AttributedString(
        markdown: escaped,
        options: .init(
          allowsExtendedAttributes: true,
          interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
      )
    else { return nil }

    let codeFontSize = round(13 * fontScale)
    let paragraph = NSMutableParagraphStyle()
    paragraph.lineSpacing = OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)
    let result = NSMutableAttributedString()

    for run in parsed.runs {
      let text = String(parsed[run.range].characters)
      guard !text.isEmpty else { continue }
      let intent = run.inlinePresentationIntent ?? []
      let isCode = intent.contains(.code)
      var attributes: [NSAttributedString.Key: Any] = [
        .font: font(
          size: isCode ? codeFontSize : fontSize,
          bold: intent.contains(.stronglyEmphasized),
          italic: intent.contains(.emphasized),
          code: isCode
        ),
        .foregroundColor: NSColor.labelColor,
        .paragraphStyle: paragraph,
      ]
      if isCode {
        // The same chip wash the SwiftUI renderer paints, flattened: a run
        // background cannot round its corners, and a rounded corner is not
        // worth an attachment that would drop out of the copied text.
        attributes[.backgroundColor] = NSColor.labelColor.withAlphaComponent(0.085)
      }
      if let link = run.link {
        attributes[.link] = link
        attributes[.foregroundColor] = NSColor.systemBlue
        if style == .user { attributes[.underlineStyle] = NSUnderlineStyle.single.rawValue }
      }
      result.append(NSAttributedString(string: text, attributes: attributes))
    }

    applyCitationLinks(to: result, ordinals: citationOrdinals)
    return result
  }

  /// `[7]` is a marker the transcript owns, not Markdown. Markdown leaves it as
  /// literal text (there is no link destination after it), so it is still here
  /// to find, and turning it into a link keeps it clickable *and* selectable —
  /// the chip button it replaces was neither.
  ///
  /// The pattern is the transcript's own, not a second copy of it: ordinals run
  /// to four digits and the model also writes kind-prefixed markers like
  /// `[memory 5023]`, both of which a hand-rolled `\[\d{1,3}\]` quietly left
  /// as dead text.
  static func applyCitationLinks(to text: NSMutableAttributedString, ordinals: Set<Int>) {
    guard !ordinals.isEmpty else { return }
    guard
      let pattern = try? NSRegularExpression(pattern: ChatCitationMarkup.numericMarkerPattern)
    else { return }
    let full = NSRange(location: 0, length: text.length)
    for match in pattern.matches(in: text.string, range: full).reversed() {
      guard match.numberOfRanges == 2,
        let digits = Range(match.range(at: 1), in: text.string),
        let ordinal = Int(text.string[digits]),
        ordinals.contains(ordinal),
        let url = URL(string: "\(citationScheme)://\(ordinal)")
      else { continue }
      text.addAttributes(
        [.link: url, .foregroundColor: NSColor.systemBlue], range: match.range)
    }
  }

  private static func font(size: CGFloat, bold: Bool, italic: Bool, code: Bool) -> NSFont {
    if code { return .monospacedSystemFont(ofSize: size, weight: bold ? .semibold : .regular) }
    let base = bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size)
    guard italic else { return base }
    let italicized = NSFontManager.shared.convert(base, toHaveTrait: .italicFontMask)
    return italicized
  }
}

/// One `NSTextView`, laid out by SwiftUI, drawing one run of chat prose.
///
/// Deliberately *not* `NSTextView.scrollableTextView()`: an inner scroller
/// would swallow the transcript's own trackpad gestures the way a fenced code
/// block does. This view has no scroller, reports the height its text needs at
/// the proposed width, and lets the transcript do the scrolling.
struct ChatSelectableProseText: NSViewRepresentable {
  let attributed: NSAttributedString
  /// The shared-cache entry this block's parse lives in, when it came from
  /// `ChatSelectableProseBlock`. Lets the measured height ride the same entry
  /// instead of a throwaway TextKit stack per `sizeThatFits` query — SwiftUI
  /// issues about nine of those per block across the mount layout passes.
  /// Standalone constructions leave it nil and measure every time.
  var heightEntry: ChatProseRenderCache.Entry?
  var onOpenCitation: ((Int) -> Void)?
  /// Reports the citation under the pointer and the rectangle its marker
  /// occupies, so the transcript can anchor the same source preview the chip
  /// used to open. `nil` means the pointer left every marker.
  var onHoverCitation: ((CitationHover?) -> Void)?

  struct CitationHover: Equatable {
    let ordinal: Int
    let rect: CGRect
  }

  func makeCoordinator() -> Coordinator {
    Coordinator(onOpenCitation: onOpenCitation, onHoverCitation: onHoverCitation)
  }

  func makeNSView(context: Context) -> NSTextView {
    let textView = ChatProseTextView()
    textView.isEditable = false
    textView.isSelectable = true
    textView.drawsBackground = false
    textView.backgroundColor = .clear
    textView.isRichText = false
    textView.textContainerInset = .zero
    textView.textContainer?.lineFragmentPadding = 0
    textView.textContainer?.widthTracksTextView = true
    textView.isVerticallyResizable = false
    textView.isHorizontallyResizable = false
    textView.linkTextAttributes = [
      .foregroundColor: NSColor.systemBlue,
      .cursor: NSCursor.pointingHand,
    ]
    textView.delegate = context.coordinator
    textView.onHoverCitation = { [weak coordinator = context.coordinator] hover in
      coordinator?.onHoverCitation?(hover)
    }
    textView.textStorage?.setAttributedString(attributed)
    return textView
  }

  func updateNSView(_ textView: NSTextView, context: Context) {
    context.coordinator.onOpenCitation = onOpenCitation
    context.coordinator.onHoverCitation = onHoverCitation
    guard textView.textStorage?.isEqual(to: attributed) != true else { return }
    // Replacing the storage of the one view that owns this selection. There is
    // no second overlay to install, which is why this is AppKit.
    textView.textStorage?.setAttributedString(attributed)
  }

  /// Height for the width the transcript proposed, measured **beside** the
  /// live view rather than inside it.
  ///
  /// Measuring in the view's own text container is what broke the column: the
  /// container was left holding a measurement width, the frame later arrived at
  /// a different one, and the answer wrapped to neither. A throwaway layout
  /// manager answers the question without touching what is on screen, and the
  /// live container simply tracks the frame it is finally given.
  func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextView, context: Context) -> CGSize? {
    guard let width = proposal.width, width > 0, width < .greatestFiniteMagnitude else { return nil }
    let height: CGFloat
    if let heightEntry {
      height = ChatProseRenderCache.height(for: heightEntry, width: width) {
        Self.height(of: attributed, fittingWidth: width)
      }
    } else {
      height = Self.height(of: attributed, fittingWidth: width)
    }
    return CGSize(width: width, height: height)
  }

  /// Exposed so a test can assert the row's height without mounting a window.
  static func height(of attributed: NSAttributedString, fittingWidth width: CGFloat) -> CGFloat {
    let storage = NSTextStorage(attributedString: attributed)
    let container = NSTextContainer(size: NSSize(width: width, height: .greatestFiniteMagnitude))
    container.lineFragmentPadding = 0
    let layoutManager = NSLayoutManager()
    layoutManager.addTextContainer(container)
    storage.addLayoutManager(layoutManager)
    layoutManager.ensureLayout(for: container)
    return ceil(layoutManager.usedRect(for: container).height)
  }

  final class Coordinator: NSObject, NSTextViewDelegate {
    var onOpenCitation: ((Int) -> Void)?
    var onHoverCitation: ((CitationHover?) -> Void)?

    init(
      onOpenCitation: ((Int) -> Void)?,
      onHoverCitation: ((CitationHover?) -> Void)?
    ) {
      self.onOpenCitation = onOpenCitation
      self.onHoverCitation = onHoverCitation
    }

    func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
      guard let url = link as? URL ?? (link as? String).flatMap(URL.init(string:)) else { return false }
      if let ordinal = ChatSelectableProse.citationOrdinal(from: url) {
        onOpenCitation?(ordinal)
        return true
      }
      // Everything else is an ordinary Markdown link and belongs to the browser.
      return false
    }
  }
}

/// A text view that reads as prose rather than as a control.
///
/// Two AppKit defaults are wrong for a transcript: the field editor's I-beam
/// tracking rectangle is fine, but the view would otherwise accept first
/// responder from a `Tab` walk and steal the composer's focus ring, and a
/// right-click would open AppKit's editing menu instead of the row's own
/// "Copy Message" menu.
final class ChatProseTextView: NSTextView {
  var onHoverCitation: ((ChatSelectableProseText.CitationHover?) -> Void)?
  private var hoveredOrdinal: Int?

  override var acceptsFirstResponder: Bool { true }

  /// The column belongs to the transcript. Claiming an intrinsic width here is
  /// what let a short line pull the whole row in from the container edge.
  override var intrinsicContentSize: NSSize {
    NSSize(width: NSView.noIntrinsicMetric, height: NSView.noIntrinsicMetric)
  }

  override func updateTrackingAreas() {
    super.updateTrackingAreas()
    trackingAreas.filter { $0.owner === self }.forEach(removeTrackingArea)
    addTrackingArea(
      NSTrackingArea(
        rect: bounds,
        options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
        owner: self))
  }

  override func mouseMoved(with event: NSEvent) {
    super.mouseMoved(with: event)
    publishHover(at: convert(event.locationInWindow, from: nil))
  }

  override func mouseExited(with event: NSEvent) {
    super.mouseExited(with: event)
    publishHover(at: nil)
  }

  /// Point to marker. A miss is as meaningful as a hit — it is what dismisses
  /// a preview the reader has moved away from.
  private func publishHover(at point: CGPoint?) {
    guard let point, let layoutManager, let textContainer else {
      publish(nil)
      return
    }
    let glyph = layoutManager.glyphIndex(for: point, in: textContainer)
    let bounds = layoutManager.boundingRect(
      forGlyphRange: NSRange(location: glyph, length: 1), in: textContainer)
    guard bounds.contains(point) else {
      publish(nil)
      return
    }
    let index = layoutManager.characterIndexForGlyph(at: glyph)
    guard index < (textStorage?.length ?? 0) else {
      publish(nil)
      return
    }
    var range = NSRange(location: 0, length: 0)
    guard let url = textStorage?.attribute(.link, at: index, effectiveRange: &range) as? URL,
      let ordinal = ChatSelectableProse.citationOrdinal(from: url)
    else {
      publish(nil)
      return
    }
    let rect = layoutManager.boundingRect(forGlyphRange: range, in: textContainer)
    guard hoveredOrdinal != ordinal else { return }
    hoveredOrdinal = ordinal
    onHoverCitation?(.init(ordinal: ordinal, rect: rect))
  }

  private func publish(_ hover: ChatSelectableProseText.CitationHover?) {
    guard hoveredOrdinal != nil else { return }
    hoveredOrdinal = nil
    onHoverCitation?(hover)
  }

  /// Focus arrives by clicking into the words, never by tabbing through them.
  override func becomeFirstResponder() -> Bool {
    guard NSApp.currentEvent?.type != .keyDown else { return false }
    return super.becomeFirstResponder()
  }

  override func menu(for event: NSEvent) -> NSMenu? {
    // Nothing selected — let the row's context menu answer, so "Copy Message"
    // stays one right-click away from anywhere in the bubble.
    guard selectedRange().length > 0 else { return nil }
    return super.menu(for: event)
  }
}

/// One run of chat prose, selectable, with the citation preview the chip used
/// to own.
///
/// The chip was a `Button` inside a flow layout, which is precisely what made
/// the surrounding words unselectable: a line of prose had to be chopped into
/// per-segment `Text` views to make room for it. Here the marker is a link
/// range inside the one text view, so the same `[7]` is draggable, copyable,
/// clickable *and* still opens its source on hover.
struct ChatSelectableProseBlock: View {
  let text: String
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  let citations: [ChatCitationReference]
  let onOpenCitation: ((ChatCitationReference) -> Void)?

  @State private var hover: ChatSelectableProseText.CitationHover?
  @State private var isPreviewHovering = false
  @State private var hoverGeneration = 0

  private var referencesByOrdinal: [Int: ChatCitationReference] {
    Dictionary(citations.map { ($0.ordinal, $0) }, uniquingKeysWith: { first, _ in first })
  }

  private var hoveredReference: ChatCitationReference? {
    hover.flatMap { referencesByOrdinal[$0.ordinal] }
  }

  var body: some View {
    let fontSize = round(14 * fontScale)
    // The parse and the measured height are keyed on the exact render inputs,
    // so a hit is identical to a recompute — and a route return, which rebuilds
    // this block from the same transcript text, hits instead of paying the
    // Foundation Markdown parse and the throwaway TextKit layout again. See
    // `ChatProseRenderCache` for the measured cost this retires.
    let cacheKey = ChatProseRenderCache.Key(
      markdown: text,
      style: style,
      fontSize: Int(fontSize),
      fontScaleMilli: Int((fontScale * 1_000).rounded()),
      citationOrdinals: citations.map(\.ordinal).sorted())
    if let entry = ChatProseRenderCache.entry(
      for: cacheKey,
      produce: {
        ChatSelectableProse.attributedString(
          markdown: text,
          style: style,
          fontSize: fontSize,
          fontScale: fontScale,
          citationOrdinals: Set(citations.map(\.ordinal)))
      })
    {
      ChatSelectableProseText(
        attributed: entry.attributed,
        heightEntry: entry,
        onOpenCitation: { ordinal in
          guard let reference = referencesByOrdinal[ordinal], reference.canOpen else { return }
          hover = nil
          onOpenCitation?(reference)
        },
        onHoverCitation: { value in
          hoverGeneration += 1
          let generation = hoverGeneration
          if value == nil {
            schedulePreviewDismiss(generation: generation)
          } else {
            hover = value
          }
        }
      )
      // Without this the row asks the text for its ideal width and gets the
      // text's own, not the column's: assistant prose stopped 200pt short of
      // the container edge and re-wrapped inside a gutter nobody reserved.
      .frame(maxWidth: .infinity, alignment: .leading)
      .popover(
        // A real binding, not a constant: SwiftUI writes `false` back when the
        // reader dismisses the preview, and a constant would swallow that and
        // leave a popover that cannot be closed.
        isPresented: Binding(
          get: { hoveredReference != nil },
          set: { if !$0 { hover = nil } }
        ),
        attachmentAnchor: .rect(.rect(hover?.rect ?? .zero)),
        arrowEdge: .bottom
      ) {
        if let reference = hoveredReference {
          ChatCitationPreview(
            reference: reference,
            fontScale: fontScale,
            onOpen: {
              hover = nil
              onOpenCitation?(reference)
            }
          )
          .onHover { hovering in
            isPreviewHovering = hovering
            hoverGeneration += 1
            if !hovering { schedulePreviewDismiss(generation: hoverGeneration) }
          }
        }
      }
    } else {
      // The parse failed, which is not a reason to withhold the words.
      OmiMarkdownChatText(text, fontSize: fontSize, style: style)
    }
  }

  /// The pointer crosses the gap between marker and popover; dismissing on the
  /// first miss would make the preview unreachable.
  private func schedulePreviewDismiss(generation: Int) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
      guard !isPreviewHovering, generation == hoverGeneration else { return }
      hover = nil
    }
  }
}
