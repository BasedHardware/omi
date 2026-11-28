import Foundation

/// The short form of a conversation: the summary's first sentences (the detail page leads with
/// them, "More" shows the rest) and a clean Markdown export for the user's own AI.
public enum ConversationDigest {
    /// The opening of a summary as plain text: headings, bullets and emphasis dropped, at most
    /// `sentences` sentences and about `characters` characters. `isShortened` says whether the
    /// summary has more than that (the page then offers "More").
    public static func lead(of markdown: String, sentences: Int = 3, characters: Int = 280) -> (text: String, isShortened: Bool) {
        let paragraphs = plainParagraphs(markdown)
        let all = paragraphs.joined(separator: " ")
        guard !all.isEmpty else { return ("", false) }
        var kept: [String] = []
        var length = 0
        for sentence in split(all) {
            if kept.count == sentences { break }
            // Always keep the first sentence; later ones only while they fit.
            if !kept.isEmpty, length + sentence.count + 1 > characters { break }
            kept.append(sentence)
            length += sentence.count + 1
        }
        var text = kept.joined(separator: " ")
        if text.count > characters + 40 {
            // One very long first sentence: cut at a word.
            let cut = text.prefix(characters)
            text = (cut.range(of: " ", options: .backwards).map { String(cut[..<$0.lowerBound]) } ?? String(cut)) + "…"
        }
        let rest = all.count - text.count
        // A summary that is a heading list ("## Decisions") is shortened even when its prose fits.
        return (text, rest > 1 || markdown.contains("\n#") || markdown.hasPrefix("#"))
    }

    /// The conversation as Markdown for another AI: title, date, summary, action items,
    /// the transcript with timestamps, and the link.
    public static func markdown(
        _ export: Export, labels: Labels, calendar: Calendar = .current, locale: Locale = .current
    ) -> String {
        var parts = ["# \(export.title)"]
        var when = export.date.formatted(Date.FormatStyle(
            date: .complete,
            time: .shortened,
            locale: locale,
            calendar: calendar,
            timeZone: calendar.timeZone
        ))
        if let duration = export.duration { when += " · \(max(1, Int((duration / 60).rounded()))) min" }
        parts.append(when)
        let summary = export.summary.trimmingCharacters(in: .whitespacesAndNewlines)
        if !summary.isEmpty { parts.append("## \(labels.summary)\n\n\(demoteHeadings(summary))") }
        if !export.actionItems.isEmpty {
            let items = export.actionItems.map { "- [\($0.isDone ? "x" : " ")] \($0.text)" }.joined(separator: "\n")
            parts.append("## \(labels.actionItems)\n\n\(items)")
        }
        if !export.transcript.isEmpty {
            let lines = export.transcript.map { "[\(timestamp($0.start))] **\($0.speaker):** \($0.text)" }.joined(separator: "\n")
            parts.append("## \(labels.transcript)\n\n\(lines)")
        }
        if let link = export.link { parts.append("\(labels.link): \(link.absoluteString)") }
        return parts.joined(separator: "\n\n") + "\n"
    }

    /// What goes into the export.
    public struct Export: Sendable {
        public let title: String
        public let date: Date
        public let duration: TimeInterval?
        public let summary: String
        public let actionItems: [ActionItemLine]
        public let transcript: [ConversationDetail.Line]
        public let link: URL?

        public init(
            title: String, date: Date, duration: TimeInterval?, summary: String,
            actionItems: [ActionItemLine], transcript: [ConversationDetail.Line], link: URL?
        ) {
            self.title = title
            self.date = date
            self.duration = duration
            self.summary = summary
            self.actionItems = actionItems
            self.transcript = transcript
            self.link = link
        }
    }

    public struct ActionItemLine: Sendable {
        public let text: String
        public let isDone: Bool

        public init(_ text: String, isDone: Bool = false) {
            self.text = text
            self.isDone = isDone
        }
    }

    public struct Labels: Sendable {
        public let summary: String
        public let actionItems: String
        public let transcript: String
        public let link: String

        public init(summary: String, actionItems: String, transcript: String, link: String) {
            self.summary = summary
            self.actionItems = actionItems
            self.transcript = transcript
            self.link = link
        }
    }

    /// Where a task came from in this conversation, in one line: the transcript words its
    /// extraction cited, else the extraction's context ("Anna asked for it before Friday"), else nil.
    public static func quote(forTask description: String, in detail: ConversationDetail) -> String? {
        guard let source = detail.actionItemSources[normalized(description)] else { return nil }
        let cited = Set(source.segmentIDs)
        let words = detail.transcript.filter { $0.segmentID.map(cited.contains) ?? false }.map(\.text)
        if !words.isEmpty { return words.joined(separator: " ") }
        let context = source.context.trimmingCharacters(in: .whitespacesAndNewlines)
        return context.isEmpty ? nil : context
    }

    /// Task descriptions as keys: case, spacing and a final period do not matter.
    public static func normalized(_ description: String) -> String {
        var text = description.lowercased().split(whereSeparator: \.isWhitespace).joined(separator: " ")
        if text.hasSuffix(".") { text.removeLast() }
        return text
    }

    /// Consecutive lines of one speaker as one paragraph (a transcript reads like a document,
    /// not a chat), but never a wall: a long turn breaks into paragraphs of about
    /// `maxCharacters`. A paragraph's id is its first line's.
    public static func paragraphs(_ lines: [ConversationDetail.Line], maxCharacters: Int = 420) -> [Paragraph] {
        var result: [Paragraph] = []
        for line in lines {
            if let current = result.last, let last = current.lines.last, sameSpeaker(last, line),
               current.characterCount + line.text.count <= maxCharacters
            {
                result[result.count - 1].lines.append(line)
            } else {
                let continues = result.last?.lines.last.map { sameSpeaker($0, line) } ?? false
                result.append(Paragraph(lines: [line], continuesTurn: continues))
            }
        }
        return result
    }

    public struct Paragraph: Identifiable, Hashable, Sendable {
        public var lines: [ConversationDetail.Line]
        /// The same speaker went on from the paragraph before (the page shows just the time).
        public var continuesTurn = false

        public var id: Int {
            lines[0].id
        }

        public var first: ConversationDetail.Line {
            lines[0]
        }

        var characterCount: Int {
            lines.reduce(0) { $0 + $1.text.count + 1 }
        }

        public func contains(_ lineID: Int) -> Bool {
            lines.contains { $0.id == lineID }
        }
    }

    /// The transcript in chapters, so it can be scanned: the notes' sections (each cites its
    /// segments) when they cover enough of it, else blocks of `blockSize` paragraphs. A chapter's
    /// id is its first paragraph's.
    public static func chapters(
        _ lines: [ConversationDetail.Line], sections: [ConversationDetail.Chapter], blockSize: Int = 6
    ) -> [Chapter] {
        let paragraphs = paragraphs(lines)
        guard !paragraphs.isEmpty else { return [] }
        var sectionOf: [String: Int] = [:]
        for (index, section) in sections.enumerated() {
            for id in section.segmentIDs where sectionOf[id] == nil {
                sectionOf[id] = index
            }
        }
        let cited = lines.count { $0.segmentID.map { sectionOf[$0] != nil } ?? false }
        // Notes that cite little of the transcript would leave most of it under the wrong heading.
        guard sections.count > 1, Double(cited) >= Double(lines.count) * 0.3 else {
            return stride(from: 0, to: paragraphs.count, by: blockSize).map { start in
                Chapter(title: nil, paragraphs: Array(paragraphs[start ..< min(start + blockSize, paragraphs.count)]))
            }
        }
        var result: [Chapter] = []
        var currentSection: Int?
        for paragraph in paragraphs {
            let own = paragraph.lines.lazy.compactMap { $0.segmentID.flatMap { sectionOf[$0] } }.first
            let section = own ?? currentSection
            if let last = result.last, section == currentSection, !last.paragraphs.isEmpty {
                result[result.count - 1].paragraphs.append(paragraph)
            } else {
                result.append(Chapter(title: section.map { sections[$0].heading }, paragraphs: [paragraph]))
            }
            currentSection = section
        }
        return result
    }

    public struct Chapter: Identifiable, Hashable, Sendable {
        /// The notes' heading; `nil` for a plain block (the page shows its time).
        public let title: String?
        public var paragraphs: [Paragraph]

        public var id: Int {
            paragraphs[0].id
        }

        public var start: TimeInterval {
            paragraphs[0].first.start
        }

        public func contains(_ lineID: Int) -> Bool {
            paragraphs.contains { $0.contains(lineID) }
        }
    }

    static func sameSpeaker(_ lhs: ConversationDetail.Line, _ rhs: ConversationDetail.Line) -> Bool {
        if lhs.isUser || rhs.isUser { return lhs.isUser == rhs.isUser }
        if let left = lhs.personID ?? lhs.speakerID.map(String.init), let right = rhs.personID ?? rhs.speakerID.map(String.init) {
            return left == right
        }
        return lhs.speaker == rhs.speaker
    }

    /// "4:05", "1:02:09".
    public static func timestamp(_ seconds: TimeInterval) -> String {
        let total = max(0, Int(seconds.rounded(.down)))
        let (hours, minutes, rest) = (total / 3600, total / 60 % 60, total % 60)
        return hours > 0 ? String(format: "%d:%02d:%02d", hours, minutes, rest) : String(format: "%d:%02d", minutes, rest)
    }

    // MARK: Helpers

    /// Paragraph text without Markdown: headings are dropped (they are labels, not prose).
    static func plainParagraphs(_ markdown: String) -> [String] {
        markdown
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && !$0.hasPrefix("#") && $0 != "---" }
            .map { line in
                var line = line
                for marker in ["- ", "* ", "• ", "> "] where line.hasPrefix(marker) {
                    line = String(line.dropFirst(marker.count))
                }
                if let match = line.range(of: #"^\d+\.\s"#, options: .regularExpression) { line.removeSubrange(match) }
                line = line.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "__", with: "")
                // A bullet without a period still ends a thought.
                if let last = line.last, !".!?…:".contains(last) { line += "." }
                return line
            }
    }

    /// Sentences, split after ". ", "! ", "? " (abbreviations like "e.g." are rare in summaries).
    static func split(_ text: String) -> [String] {
        var sentences: [String] = []
        var current = ""
        let characters = Array(text)
        for (index, character) in characters.enumerated() {
            current.append(character)
            let next = index + 1 < characters.count ? characters[index + 1] : " "
            if ".!?…".contains(character), next == " " {
                let sentence = current.trimmingCharacters(in: .whitespaces)
                if !sentence.isEmpty { sentences.append(sentence) }
                current = ""
            }
        }
        let tail = current.trimmingCharacters(in: .whitespaces)
        if !tail.isEmpty { sentences.append(tail) }
        return sentences
    }

    /// Summary headings one level under the export's "## Summary".
    static func demoteHeadings(_ markdown: String) -> String {
        markdown.components(separatedBy: "\n").map { line in
            line.hasPrefix("#") ? "#" + line : line
        }.joined(separator: "\n")
    }
}
