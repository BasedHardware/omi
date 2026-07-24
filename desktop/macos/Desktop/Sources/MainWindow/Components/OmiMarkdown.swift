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
///
/// Chat Markdown deliberately disables SwiftUI text selection. On macOS,
/// `textSelection(.enabled)` installs AppKit-backed `SelectionOverlay` views
/// that can form a non-converging setFont → intrinsic-size → AttributeGraph
/// loop when a long transcript scrolls. Chat bubbles already provide a
/// whole-message copy action; code blocks and tables add focused copy actions.
struct OmiMarkdown: View {
  enum Style: Equatable {
    case assistant
    case user
    case onboardingUser
  }

  let text: String
  let style: Style
  @Environment(\.fontScale) private var fontScale

  init(text: String, sender: ChatSender) {
    self.text = text
    self.style = sender == .user ? .user : .assistant
  }

  init(text: String, style: Style) {
    self.text = text
    self.style = style
  }

  var body: some View {
    OmiMarkdownContent(text: text, style: style, fontScale: fontScale)
      .equatable()
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
/// re-entering AttributeGraph while the transcript scrolls.
struct OmiMarkdownContent: View, Equatable {
  let text: String
  let style: OmiMarkdown.Style
  let fontScale: CGFloat
  let document: OmiMarkdownDocument

  init(text: String, style: OmiMarkdown.Style, fontScale: CGFloat) {
    self.text = text
    self.style = style
    self.fontScale = fontScale
    self.document = OmiMarkdownDocument(markdown: text)
  }

  nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.text == rhs.text && lhs.style == rhs.style && lhs.fontScale == rhs.fontScale
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
              OmiMarkdownTableView(table: table, style: style, fontScale: fontScale)
            }
          }
        }
      }
    }
  }

  @ViewBuilder
  private func textView(_ content: String) -> some View {
    let fontSize = round(14 * fontScale)
    let processed = Self.preprocessText(content)
    let styled = Self.styledAttributedString(
      from: processed, style: style, fontSize: fontSize, fontScale: fontScale
    )

    Group {
      if let s = styled {
        Text(s)
          .if_available_writingToolsNone()
      } else {
        Text(content)
          .font(.system(size: fontSize))
          .foregroundColor(Self.baseColor(for: style))
          .if_available_writingToolsNone()
      }
    }
  }

  // MARK: - Code Block (boxed, monospace)

  @ViewBuilder
  private func codeBlockView(_ code: String, language: String?) -> some View {
    let codeFontSize = round(13 * fontScale)
    let bgColor =
      style == .user
      ? Color.white.opacity(0.15)
      : OmiColors.backgroundTertiary

    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      HStack(spacing: OmiSpacing.xs) {
        if let language {
          Text(language)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(style == .user ? .white.opacity(0.7) : OmiColors.textTertiary)
        }
        Spacer(minLength: 0)
        CodeBlockCopyButton(code: code)
      }

      ScrollView(.horizontal, showsIndicators: false) {
        Text(code)
          .font(.system(size: codeFontSize, design: .monospaced))
          .foregroundColor(Self.baseColor(for: style))
          .if_available_writingToolsNone()
      }
    }
    .padding(OmiSpacing.md)
    .background(bgColor)
    .cornerRadius(OmiChrome.elementRadius)
  }

  // MARK: - Attributed String Styling

  private static func styledAttributedString(
    from processed: String, style: OmiMarkdown.Style, fontSize: CGFloat, fontScale: CGFloat
  ) -> AttributedString? {
    guard
      var attributed = try? AttributedString(
        markdown: processed,
        options: .init(
          allowsExtendedAttributes: true,
          interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
      )
    else { return nil }

    let codeFontSize = round(13 * fontScale)
    let baseColor = baseColor(for: style)
    let linkColor: Color = style == .user ? .white.opacity(0.9) : OmiColors.accent
    let codeBgColor: Color =
      style == .user
      ? .white.opacity(0.15)
      : OmiColors.backgroundTertiary

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

  fileprivate static func inlineAttributedString(
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

  fileprivate static func baseColor(for style: OmiMarkdown.Style) -> Color {
    switch style {
    case .assistant:
      OmiColors.textPrimary
    case .user:
      .white
    case .onboardingUser:
      OmiColors.backgroundPrimary
    }
  }

  // MARK: - Markdown Preprocessing

  /// Converts block-level elements (headers, asterisk lists) into inline-compatible
  /// form for `AttributedString(markdown:)` with `.inlineOnlyPreservingWhitespace`.
  private static func preprocessText(_ text: String) -> String {
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

struct OmiMarkdownDocument: Equatable {
  struct Block: Identifiable, Equatable {
    enum Kind: Equatable {
      case text(String)
      case codeBlock(language: String?, code: String)
      case table(OmiMarkdownTable)
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

      textLines.append(lines[index])
      index += 1
    }

    flushText()
    self.blocks = parsedBlocks
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
  let rawMarkdown: String

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

    var rawLines = [lines[startIndex], lines[startIndex + 1]]
    var rows = [[String]]()
    var cursor = startIndex + 2

    while cursor < lines.count {
      let line = lines[cursor]
      guard !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { break }
      let rowCells = cells(in: line)
      guard rowCells.count >= 2 else { break }

      rows.append(normalize(rowCells, columnCount: header.count))
      rawLines.append(line)
      cursor += 1
    }

    return (
      OmiMarkdownTable(
        header: header,
        alignments: parsedAlignments,
        rows: rows,
        rawMarkdown: rawLines.joined(separator: "\n")
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

  private var allRows: [[String]] {
    [table.header] + table.rows
  }

  private var borderColor: Color {
    style == .user ? .white.opacity(0.18) : .white.opacity(0.14)
  }

  var body: some View {
    VStack(alignment: .trailing, spacing: OmiSpacing.xxs) {
      MarkdownTableCopyButton(markdown: table.rawMarkdown)

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
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    // A table remains copyable through its dedicated action, but does not
    // create one AppKit SelectionOverlay per cell inside the live transcript.
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
      if let styled {
        Text(styled)
      } else {
        Text(content)
          .font(.system(size: fontSize))
          .foregroundColor(OmiMarkdownContent.baseColor(for: style))
      }
    }
    .fontWeight(row == 0 ? .semibold : .regular)
    .frame(
      minWidth: metrics.minWidth,
      idealWidth: metrics.idealWidth,
      maxWidth: metrics.maxWidth,
      minHeight: row == 0 ? 40 : 44,
      alignment: columnAlignment.topAlignment
    )
    .padding(.vertical, OmiSpacing.sm)
    .padding(.horizontal, OmiSpacing.md)
    .frame(maxHeight: .infinity, alignment: columnAlignment.topAlignment)
    .background(rowBackground(row))
    .if_available_writingToolsNone()
  }

  private func rowBackground(_ row: Int) -> Color {
    if style == .user {
      if row == 0 {
        return .white.opacity(0.13)
      }
      return row.isMultiple(of: 2) ? .white.opacity(0.07) : .white.opacity(0.035)
    }
    if row == 0 {
      return OmiColors.backgroundTertiary
    }
    return row.isMultiple(of: 2)
      ? OmiColors.backgroundTertiary.opacity(0.72)
      : OmiColors.backgroundSecondary.opacity(0.92)
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

private struct MarkdownTableCopyButton: View {
  let markdown: String
  @State private var copied = false

  var body: some View {
    Button {
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(markdown, forType: .string)
      copied = true
      DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
        copied = false
      }
    } label: {
      Label(copied ? "Copied" : "Copy table", systemImage: copied ? "checkmark" : "doc.on.doc")
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundColor(copied ? .green : OmiColors.textTertiary)
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("omi-markdown-table-copy")
    .help("Copy table")
  }
}

/// Owns transient copy feedback below the selectable-message render boundary.
/// Updating this leaf must not invalidate the surrounding SelectionOverlay.
private struct CodeBlockCopyButton: View {
  let code: String
  @State private var copied = false

  var body: some View {
    Button {
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(code, forType: .string)
      copied = true
      DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
        copied = false
      }
    } label: {
      Image(systemName: copied ? "checkmark" : "doc.on.doc")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(copied ? .green : OmiColors.textTertiary)
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Copy code")
    .help("Copy code")
  }
}
