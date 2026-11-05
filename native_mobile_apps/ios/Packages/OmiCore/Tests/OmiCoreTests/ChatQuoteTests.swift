import Foundation
@testable import OmiCore
import Testing

struct ChatQuoteTests {
    @Test func aReplyRoundTrips() {
        let answer = ChatMessage(id: "a", text: "Lunch with Anna\nat 1 pm.", sender: .omi, createdAt: .now)
        let sent = ChatQuote(replyingTo: answer).prefixing("Move it to 2?")
        #expect(sent == "> Omi: Lunch with Anna at 1 pm.\n\nMove it to 2?")
        let (quote, body) = ChatQuote.split(sent)
        #expect(quote == ChatQuote(speaker: "Omi", snippet: "Lunch with Anna at 1 pm."))
        #expect(quote?.quotesOmi == true)
        #expect(body == "Move it to 2?")
    }

    @Test func longMessagesAreCutAtAWord() {
        let text = Array(repeating: "word", count: 80).joined(separator: " ")
        let quote = ChatQuote(replyingTo: ChatMessage(id: "q", text: text, sender: .user, createdAt: .now))
        #expect(quote.speaker == "Me")
        #expect(quote.snippet.hasSuffix("word…"))
        #expect(quote.snippet.count <= ChatQuote.maxLength + 1)
    }

    /// Quoting a reply quotes its question, not the quote in front of it.
    @Test func aQuotedReplyIsQuotedWithoutItsQuote() {
        let reply = ChatMessage(id: "r", text: "> Omi: Earlier.\n\nAnd now?", sender: .user, createdAt: .now)
        #expect(ChatQuote(replyingTo: reply).snippet == "And now?")
    }

    @Test func ordinaryMarkdownQuotesStayText() {
        for text in ["> A quote from a book\n\nMy thoughts", "> Omi: no body\n\n", "Hello", "> Someone: hi\n\nyes"] {
            #expect(ChatQuote.split(text).quote == nil)
            #expect(ChatQuote.split(text).body == text)
        }
    }
}
