import OmiDesign
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// Agent answers as Omi shows them. SwiftUI's `Text` renders inline Markdown only, so the block
/// level is done here: headings, bulleted and numbered items, quotes, code and tables. A quote is how
/// the agent hands over a draft, so it gets its own card with a copy button.
public struct MarkdownBlocks: View {
    enum Block: Hashable {
        case heading(String)
        case bullet(String, level: Int)
        case numbered(String, number: String, level: Int)
        case quote(String)
        case code(String)
        case table([[String]])
        case paragraph(String)
    }

    let blocks: [Block]
    let font: Font
    let selectable: Bool

    /// `font`: the text size (a chat bubble is a little smaller than body). `selectable`: off in a
    /// bubble, whose long press opens its menu (Copy is in it).
    public init(_ text: String, font: Font = DS.Typography.body, selectable: Bool = true) {
        blocks = Self.parse(text)
        self.font = font
        self.selectable = selectable
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case let .heading(text):
                    inline(text).font(font.weight(.semibold)).padding(.top, DS.Spacing.xs)
                case let .bullet(text, level):
                    // A fixed marker column: wrapped lines hang under the first line's text.
                    HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.xs) {
                        Text(verbatim: "•").foregroundStyle(DS.Palette.inkSecondary).frame(width: DS.Spacing.md, alignment: .leading)
                        inline(text)
                    }
                    .padding(.leading, CGFloat(level) * DS.Spacing.lg)
                case let .numbered(text, number, level):
                    HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.xs) {
                        Text(verbatim: number + ".").foregroundStyle(DS.Palette.inkSecondary).monospacedDigit()
                            .frame(minWidth: DS.Spacing.lg + DS.Spacing.xs, alignment: .leading)
                        inline(text)
                    }
                    .padding(.leading, CGFloat(level) * DS.Spacing.lg)
                case let .code(text):
                    ScrollView(.horizontal, showsIndicators: false) {
                        Text(verbatim: text).font(.system(.footnote, design: .monospaced)).foregroundStyle(DS.Palette.ink)
                    }
                    .padding(DS.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DS.Palette.fill, in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                case let .table(rows):
                    TableBlock(rows: rows)
                case let .quote(text):
                    DraftCard(text: text)
                case let .paragraph(text):
                    inline(text)
                }
            }
        }
        .font(font)
        .tint(DS.Palette.agent)
        .modifier(Selectable(enabled: selectable))
    }

    private struct Selectable: ViewModifier {
        let enabled: Bool

        func body(content: Content) -> some View {
            if enabled { content.textSelection(.enabled) } else { content }
        }
    }

    private func inline(_ text: String) -> Text {
        Text(LocalizedStringKey(text))
    }

    static func parse(_ text: String) -> [Block] {
        var parser = Parser()
        for raw in text.components(separatedBy: "\n") {
            parser.feed(raw)
        }
        return parser.finish()
    }

    /// Line by line: fenced code and tables first (they keep their lines as written), then text.
    struct Parser {
        var blocks: [Block] = []
        var quote: [String] = []
        var paragraph: [String] = []
        var code: [String]?
        var table: [[String]] = []

        mutating func feed(_ raw: String) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if let lines = code {
                    blocks.append(.code(lines.joined(separator: "\n")))
                    code = nil
                } else {
                    flush()
                    code = []
                }
            } else if code != nil {
                code?.append(raw)
            } else if line.hasPrefix("|") {
                if table.isEmpty { flush() }
                if let row = Self.tableRow(line) { table.append(row) }
            } else {
                if !table.isEmpty { flush() }
                text(line, indent: raw.prefix { $0 == " " }.count)
            }
        }

        private mutating func text(_ line: String, indent: Int) {
            if line.hasPrefix(">") {
                if !paragraph.isEmpty { blocks.append(.paragraph(paragraph.joined(separator: "\n"))); paragraph = [] }
                quote.append(String(line.dropFirst()).trimmingCharacters(in: .whitespaces))
                return
            }
            if line.isEmpty { return flush() }
            if line.hasPrefix("#") {
                flush()
                blocks.append(.heading(line.drop { $0 == "#" }.trimmingCharacters(in: .whitespaces)))
            } else if let match = line.wholeMatch(of: /[*\-•+–◦]\s+(.+)/) {
                // Any marker and any space after it ("-\t", "•  "), else the line reads as a
                // paragraph whose wrapped lines start under the bullet.
                flush()
                blocks.append(.bullet(String(match.1), level: indent / 2))
            } else if let match = line.wholeMatch(of: /(\d{1,3})[.)]\s+(.+)/) {
                flush()
                blocks.append(.numbered(String(match.2), number: String(match.1), level: indent / 3))
            } else {
                if !quote.isEmpty { flush() }
                paragraph.append(line)
            }
        }

        mutating func flush() {
            if !quote.isEmpty { blocks.append(.quote(quote.joined(separator: "\n"))) }
            if !paragraph.isEmpty { blocks.append(.paragraph(paragraph.joined(separator: "\n"))) }
            if !table.isEmpty { blocks.append(.table(table)) }
            quote = []
            paragraph = []
            table = []
        }

        /// An unclosed fence still shows its code (an answer cut short).
        mutating func finish() -> [Block] {
            if let code { blocks.append(.code(code.joined(separator: "\n"))) }
            code = nil
            flush()
            return blocks
        }

        /// The cells of a `| a | b |` row; nil for the `|---|:--:|` divider under the header.
        static func tableRow(_ line: String) -> [String]? {
            var cells = line.split(separator: "|", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
            if cells.first?.isEmpty == true { cells.removeFirst() }
            if cells.last?.isEmpty == true { cells.removeLast() }
            let divider = cells.allSatisfy { !$0.isEmpty && $0.allSatisfy { ":-".contains($0) } }
            return divider || cells.isEmpty ? nil : cells
        }
    }
}

/// A Markdown table: the first row bold, columns as wide as their content, sideways scrolling.
struct TableBlock: View {
    let rows: [[String]]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            Grid(alignment: .leading, horizontalSpacing: DS.Spacing.md, verticalSpacing: DS.Spacing.xs) {
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    GridRow {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Text(LocalizedStringKey(cell))
                                .font(index == 0 ? DS.Typography.callout.weight(.semibold) : DS.Typography.callout)
                                .fixedSize()
                        }
                    }
                    if index == 0 { Divider().gridCellUnsizedAxes(.horizontal) }
                }
            }
            .padding(DS.Spacing.md)
        }
        .background(DS.Palette.fill.opacity(0.5), in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
    }
}

/// A draft Omi prepared for the user to send themselves.
struct DraftCard: View {
    let text: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text(LocalizedStringKey(text))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                #if canImport(UIKit)
                    UIPasteboard.general.string = text
                #endif
                DSHaptics.success()
                copied = true
            } label: {
                Label(copied ? L("copied") : L("copy"), systemImage: copied ? "checkmark" : "doc.on.doc")
                    .font(DS.Typography.caption.weight(.semibold))
                    .foregroundStyle(DS.Palette.agent)
            }
            .buttonStyle(.plain)
        }
        .padding(DS.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.Palette.agentSoft, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
        .overlay(alignment: .leading) {
            Capsule().fill(DS.Palette.agent).frame(width: 3).padding(.vertical, DS.Spacing.sm)
        }
    }
}
