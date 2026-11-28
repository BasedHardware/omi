import Foundation

/// A reply to an earlier message travels as a short quote line in front of the question
/// ("> Omi: …", a blank line, then the question), so the agent reads what it refers to and any
/// device shows it. The chat draws the quote above the question instead of as text.
public struct ChatQuote: Hashable, Sendable {
    /// "Omi" or "Me": who wrote the quoted message.
    public let speaker: String
    public let snippet: String

    public static let omiSpeaker = "Omi"
    public static let userSpeaker = "Me"
    /// Longer messages are cut to about this many characters in the quote.
    public static let maxLength = 200

    public init(speaker: String, snippet: String) {
        self.speaker = speaker
        self.snippet = snippet
    }

    /// The quote for replying to `message`: one line, cut at a word near `maxLength`.
    public init(replyingTo message: ChatMessage) {
        let body = Self.split(message.text).body
        let words = body.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        var snippet = words
        if words.count > Self.maxLength {
            let cut = words.prefix(Self.maxLength)
            let trimmed = cut.lastIndex(of: " ").map { cut[..<$0] } ?? cut
            snippet = trimmed.trimmingCharacters(in: .punctuationCharacters.union(.whitespaces)) + "…"
        }
        self.init(speaker: message.sender == .omi ? Self.omiSpeaker : Self.userSpeaker, snippet: snippet)
    }

    /// Whether the quoted message is one of Omi's.
    public var quotesOmi: Bool {
        speaker == Self.omiSpeaker
    }

    /// `text` with this quote in front, as it is sent.
    public func prefixing(_ text: String) -> String {
        "> \(speaker): \(snippet)\n\n\(text)"
    }

    /// The quote a message starts with (if any) and the rest of its text.
    public static func split(_ text: String) -> (quote: ChatQuote?, body: String) {
        guard text.hasPrefix("> "), let end = text.range(of: "\n\n") else { return (nil, text) }
        let line = text[text.index(text.startIndex, offsetBy: 2) ..< end.lowerBound]
        guard !line.contains("\n"), let colon = line.range(of: ": ") else { return (nil, text) }
        let speaker = String(line[..<colon.lowerBound])
        guard speaker == omiSpeaker || speaker == userSpeaker else { return (nil, text) }
        let body = String(text[end.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { return (nil, text) }
        return (ChatQuote(speaker: speaker, snippet: String(line[colon.upperBound...])), body)
    }
}
