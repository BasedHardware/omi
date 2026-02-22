import SwiftUI

/// A markdown text view that supports text selection across paragraph breaks.
///
/// Splits content into text segments and code blocks:
/// - Text segments render as a single `Text(AttributedString)` so selection
///   works across paragraphs, bold, italic, etc.
/// - Code blocks render with proper monospace font and background box.
///
/// This replaces MarkdownUI's `Markdown` which creates separate views per
/// block element and breaks cross-paragraph selection.
struct SelectableMarkdown: View {
    let text: String
    let sender: ChatSender
    @Environment(\.fontScale) private var fontScale

    var body: some View {
        let segments = Self.splitSegments(text)

        if segments.count == 1, case .text = segments[0].kind {
            // Single text segment — no VStack overhead
            textView(segments[0].content)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(segments) { segment in
                    switch segment.kind {
                    case .text:
                        textView(segment.content)
                    case .codeBlock:
                        codeBlockView(segment.content)
                    }
                }
            }
        }
    }

    // MARK: - Text Segment (selectable across paragraphs)

    @ViewBuilder
    private func textView(_ content: String) -> some View {
        let fontSize = round(14 * fontScale)
        let processed = Self.preprocessText(content)

        if let styled = Self.styledAttributedString(
            from: processed, sender: sender, fontSize: fontSize, fontScale: fontScale
        ) {
            Text(styled)
                .if_available_writingToolsNone()
        } else {
            Text(content)
                .font(.system(size: fontSize))
                .foregroundColor(sender == .user ? .white : OmiColors.textPrimary)
                .if_available_writingToolsNone()
        }
    }

    // MARK: - Code Block (boxed, monospace)

    @ViewBuilder
    private func codeBlockView(_ code: String) -> some View {
        let codeFontSize = round(13 * fontScale)
        let bgColor = sender == .user
            ? Color.white.opacity(0.15)
            : OmiColors.backgroundTertiary

        ScrollView(.horizontal, showsIndicators: false) {
            Text(code)
                .font(.system(size: codeFontSize, design: .monospaced))
                .foregroundColor(sender == .user ? .white : OmiColors.textPrimary)
                .if_available_writingToolsNone()
        }
        .padding(12)
        .background(bgColor)
        .cornerRadius(8)
    }

    // MARK: - Attributed String Styling

    private static func styledAttributedString(
        from processed: String, sender: ChatSender, fontSize: CGFloat, fontScale: CGFloat
    ) -> AttributedString? {
        guard var attributed = try? AttributedString(
            markdown: processed,
            options: .init(
                allowsExtendedAttributes: true,
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            )
        ) else { return nil }

        let codeFontSize = round(13 * fontScale)
        let baseColor: Color = sender == .user ? .white : OmiColors.textPrimary
        let linkColor: Color = sender == .user ? .white.opacity(0.9) : OmiColors.purplePrimary
        let codeBgColor: Color = sender == .user
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
            if sender == .user {
                attributed[range].underlineStyle = .single
            }
        }

        return attributed
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

    // MARK: - Segment Splitting

    enum SegmentKind: Equatable {
        case text
        case codeBlock(language: String?)
    }

    struct Segment: Identifiable {
        let id: Int
        let kind: SegmentKind
        let content: String
    }

    /// Splits markdown into alternating text and code block segments.
    static func splitSegments(_ text: String) -> [Segment] {
        var segments = [Segment]()
        var currentText = ""
        var inCodeBlock = false
        var codeBlockLines = [String]()
        var codeLanguage: String?
        var nextId = 0

        for line in text.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            if trimmed.hasPrefix("```") {
                if inCodeBlock {
                    // End of code block — flush accumulated text first, then add code block
                    let textContent = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !textContent.isEmpty {
                        segments.append(Segment(id: nextId, kind: .text, content: textContent))
                        nextId += 1
                        currentText = ""
                    }

                    let code = codeBlockLines.joined(separator: "\n")
                    segments.append(Segment(id: nextId, kind: .codeBlock(language: codeLanguage), content: code))
                    nextId += 1
                    codeBlockLines = []
                    codeLanguage = nil
                } else {
                    // Start of code block — flush accumulated text
                    let textContent = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !textContent.isEmpty {
                        segments.append(Segment(id: nextId, kind: .text, content: textContent))
                        nextId += 1
                        currentText = ""
                    }

                    let lang = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                    codeLanguage = lang.isEmpty ? nil : lang
                }
                inCodeBlock.toggle()
                continue
            }

            if inCodeBlock {
                codeBlockLines.append(line)
            } else {
                if !currentText.isEmpty {
                    currentText += "\n"
                }
                currentText += line
            }
        }

        // Flush remaining content
        if inCodeBlock {
            // Unclosed code block — treat accumulated code as text
            currentText += "\n```" + (codeLanguage ?? "")
            for line in codeBlockLines {
                currentText += "\n" + line
            }
        }

        let remaining = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !remaining.isEmpty {
            segments.append(Segment(id: nextId, kind: .text, content: remaining))
        }

        return segments
    }
}
