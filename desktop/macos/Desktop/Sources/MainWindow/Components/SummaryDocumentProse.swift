import AppKit
import Foundation

/// Block semantics for settled documents, rendered in the existing selectable NSTextView.
/// Chat retains its whitespace-preserving streaming parser. Tables and fenced code stay with
/// OmiMarkdown's block renderers; this handles their surrounding prose without SelectionOverlay.
enum SummaryDocumentProse {
  static func attributedString(markdown: String, fontSize: CGFloat, fontScale: CGFloat) -> NSAttributedString? {
    guard let parsed = try? AttributedString(markdown: markdown, options: .init(interpretedSyntax: .full)) else {
      return nil
    }
    let result = NSMutableAttributedString()
    var previousBlock: Int?
    var firstBlock: Int?
    var firstParagraphByItem: [Int: Int] = [:]
    for run in parsed.runs {
      let text = String(parsed[run.range].characters)
      guard !text.isEmpty else { continue }
      let components = run.presentationIntent?.components ?? []
      let block = components.first?.identity
      if result.length == 0 { firstBlock = block }
      var level: Int?
      var listDepth = 0
      var quoteDepth = 0
      var item: (identity: Int, ordinal: Int)?
      var ordered: Bool?
      for component in components {
        switch component.kind {
        case .header(let headingLevel): level = headingLevel
        case .listItem(let ordinal):
          if item == nil { item = (component.identity, ordinal) }
        case .orderedList:
          listDepth += 1
          if ordered == nil { ordered = true }
        case .unorderedList:
          listDepth += 1
          if ordered == nil { ordered = false }
        case .blockQuote: quoteDepth += 1
        default: break
        }
      }
      let newBlock = result.length == 0 || block != previousBlock
      if newBlock && result.length > 0 {
        // The newline belongs to the previous paragraph so its layout and spacing remain stable.
        result.append(
          NSAttributedString(string: "\n", attributes: result.attributes(at: result.length - 1, effectiveRange: nil)))
      }
      let paragraph = NSMutableParagraphStyle()
      paragraph.lineSpacing = 5 * fontScale
      paragraph.paragraphSpacing = (listDepth > 0 ? 3 : 8) * fontScale
      paragraph.paragraphSpacingBefore = level == nil || block == firstBlock ? 0 : 8 * fontScale
      let quoteIndent = CGFloat(quoteDepth) * 12 * fontScale
      paragraph.headIndent = quoteIndent
      paragraph.firstLineHeadIndent = quoteIndent
      var marker: String?
      if let item, listDepth > 0 {
        let label = ordered == true ? "\(item.ordinal)." : "•"
        let labelWidth = (label as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: fontSize)]).width
        let indent = CGFloat(listDepth - 1) * 22 * fontScale + quoteIndent
        paragraph.headIndent = indent + max(22 * fontScale, labelWidth + 7 * fontScale)
        let firstItemParagraph = firstParagraphByItem[item.identity] == nil
        if newBlock && firstItemParagraph { firstParagraphByItem[item.identity] = block ?? -1 }
        paragraph.firstLineHeadIndent =
          firstParagraphByItem[item.identity] == (block ?? -1) ? indent : paragraph.headIndent
        paragraph.tabStops = [NSTextTab(textAlignment: .left, location: paragraph.headIndent)]
        if newBlock && firstItemParagraph { marker = "\(label)\t" }
      }
      let inline = run.inlinePresentationIntent ?? []
      let code = inline.contains(.code)
      let headingExtra: CGFloat = level.map { [10, 6, 3, 1, 0, 0][max(0, min(5, $0 - 1))] } ?? 0
      let size = code ? round(13 * fontScale) : fontSize + headingExtra * fontScale
      var font = code ? NSFont.monospacedSystemFont(ofSize: size, weight: .regular) : NSFont.systemFont(ofSize: size)
      var traits: NSFontTraitMask = []
      if level != nil || inline.contains(.stronglyEmphasized) { traits.insert(.boldFontMask) }
      if inline.contains(.emphasized) { traits.insert(.italicFontMask) }
      if !traits.isEmpty { font = NSFontManager.shared.convert(font, toHaveTrait: traits) }
      var attributes: [NSAttributedString.Key: Any] = [
        .font: font, .foregroundColor: NSColor.labelColor, .paragraphStyle: paragraph,
      ]
      if code { attributes[.backgroundColor] = NSColor.labelColor.withAlphaComponent(0.085) }
      if inline.contains(.strikethrough) { attributes[.strikethroughStyle] = NSUnderlineStyle.single.rawValue }
      if let link = run.link {
        attributes[.link] = link
        attributes[.foregroundColor] = NSColor.systemBlue
      }
      if let marker {
        result.append(
          NSAttributedString(
            string: marker,
            attributes: [
              .font: NSFont.systemFont(ofSize: fontSize), .foregroundColor: NSColor.labelColor,
              .paragraphStyle: paragraph,
            ]))
      }
      result.append(NSAttributedString(string: text, attributes: attributes))
      previousBlock = block
    }
    return result
  }
}
