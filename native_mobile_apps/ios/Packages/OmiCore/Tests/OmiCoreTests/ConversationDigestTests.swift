import Foundation
@testable import OmiCore
import Testing

/// The detail page's short summary and the "Send to my AI" Markdown.
struct ConversationDigestTests {
    @Test func shortSummaryStaysWhole() {
        let lead = ConversationDigest.lead(of: "Agreed to ship before the holidays. Anna owns the plan.")
        #expect(lead.text == "Agreed to ship before the holidays. Anna owns the plan.")
        #expect(!lead.isShortened)
    }

    @Test func keepsThreeSentences() {
        let lead = ConversationDigest.lead(of: "One. Two is here. Three! Four? Five.")
        #expect(lead.text == "One. Two is here. Three!")
        #expect(lead.isShortened)
    }

    @Test func dropsHeadingsAndBullets() {
        let markdown = """
        ## Overview
        Agreed on the **Q4 plan**.

        ## Decisions
        - Pricing stays until January
        - Anna owns launch
        """
        let lead = ConversationDigest.lead(of: markdown)
        #expect(lead.text == "Agreed on the Q4 plan. Pricing stays until January. Anna owns launch.")
        #expect(lead.isShortened)
    }

    @Test func cutsOneLongSentenceAtAWord() {
        let long = Array(repeating: "word", count: 120).joined(separator: " ")
        let lead = ConversationDigest.lead(of: long, characters: 100)
        #expect(lead.text.hasSuffix("…"))
        #expect(lead.text.count <= 101)
        #expect(lead.isShortened)
    }

    @Test func stopsBeforeTheCharacterBudget() {
        let lead = ConversationDigest.lead(of: "Short one. " + String(repeating: "x", count: 300) + ". Third.", characters: 280)
        #expect(lead.text == "Short one.")
    }

    @Test func emptySummary() {
        #expect(ConversationDigest.lead(of: "  \n").text.isEmpty)
    }

    @Test func mergesOneSpeakersLines() {
        let lines = [
            ConversationDetail.Line(id: 0, speaker: "Speaker 2", isUser: false, text: "Hi.", start: 0, speakerID: 1),
            ConversationDetail.Line(id: 1, speaker: "Speaker 2", isUser: false, text: "How are you?", start: 2, speakerID: 1),
            ConversationDetail.Line(id: 2, speaker: "You", isUser: true, text: "Good.", start: 4),
            ConversationDetail.Line(id: 3, speaker: "You", isUser: true, text: "And you?", start: 5),
            ConversationDetail.Line(id: 4, speaker: "Speaker 3", isUser: false, text: "Fine.", start: 7, speakerID: 2),
        ]
        let paragraphs = ConversationDigest.paragraphs(lines)
        #expect(paragraphs.map(\.id) == [0, 2, 4])
        #expect(paragraphs.map(\.lines.count) == [2, 2, 1])
        #expect(paragraphs[1].contains(3))
    }

    @Test func taskQuoteFromCitedSegmentsElseContext() {
        let conversation = ConversationExtrasTests.conversation("c1")
        var detail = ConversationDetail(conversation: conversation, summaryActionItems: [], transcript: [
            ConversationDetail.Line(id: 0, speaker: "Anna", isUser: false, text: "Can you send the deck?", start: 0, segmentID: "s1"),
            ConversationDetail.Line(id: 1, speaker: "You", isUser: true, text: "Sure, by Friday.", start: 3, segmentID: "s2"),
        ])
        detail.actionItemSources = [
            "send the deck": .init(context: "Anna needs it for the board", segmentIDs: ["s1", "s2"]),
            "book a room": .init(context: "For the offsite", segmentIDs: ["missing"]),
        ]
        #expect(ConversationDigest.quote(forTask: "Send the  deck.", in: detail) == "Can you send the deck? Sure, by Friday.")
        #expect(ConversationDigest.quote(forTask: "Book a room", in: detail) == "For the offsite")
        #expect(ConversationDigest.quote(forTask: "Something else", in: detail) == nil)
    }

    @Test func longTurnsBreakIntoParagraphs() {
        let sentence = String(repeating: "word ", count: 30) // 150 characters
        let lines = (0 ..< 5).map {
            ConversationDetail.Line(id: $0, speaker: "You", isUser: true, text: sentence, start: Double($0) * 10)
        }
        let paragraphs = ConversationDigest.paragraphs(lines, maxCharacters: 320)
        #expect(paragraphs.map(\.lines.count) == [2, 2, 1])
        #expect(paragraphs.map(\.continuesTurn) == [false, true, true])
    }

    @Test func chaptersFollowTheNotesSections() {
        let lines = (0 ..< 6).map { index in
            ConversationDetail.Line(
                id: index, speaker: index.isMultiple(of: 2) ? "You" : "Anna", isUser: index.isMultiple(of: 2),
                text: "Line \(index).", start: Double(index) * 30, segmentID: "s\(index)", speakerID: index.isMultiple(of: 2) ? nil : 1
            )
        }
        let sections = [
            ConversationDetail.Chapter(heading: "Pricing", segmentIDs: ["s0", "s1"]),
            ConversationDetail.Chapter(heading: "Launch", segmentIDs: ["s3", "s4"]),
        ]
        let chapters = ConversationDigest.chapters(lines, sections: sections)
        #expect(chapters.map(\.title) == ["Pricing", "Launch"])
        // s2 is not cited: it stays with the chapter before it.
        #expect(chapters.map { $0.paragraphs.map(\.id) } == [[0, 1, 2], [3, 4, 5]])
        #expect(chapters[1].start == 90)
    }

    @Test func chaptersFallBackToBlocks() {
        let lines = (0 ..< 8).map { index in
            ConversationDetail.Line(id: index, speaker: index.isMultiple(of: 2) ? "You" : "Anna", isUser: index.isMultiple(of: 2),
                                    text: "Line.", start: Double(index), speakerID: index.isMultiple(of: 2) ? nil : 1)
        }
        let chapters = ConversationDigest.chapters(lines, sections: [], blockSize: 3)
        #expect(chapters.map(\.paragraphs.count) == [3, 3, 2])
        #expect(chapters.allSatisfy { $0.title == nil })
    }

    @Test func timestamps() {
        #expect(ConversationDigest.timestamp(65) == "1:05")
        #expect(ConversationDigest.timestamp(3729) == "1:02:09")
    }

    @Test func markdownExport() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "UTC"))
        let lines = [
            ConversationDetail.Line(id: 0, speaker: "You", isUser: true, text: "Ship it.", start: 4),
            ConversationDetail.Line(id: 1, speaker: "Anna", isUser: false, text: "Agreed.", start: 65),
        ]
        let export = ConversationDigest.Export(
            title: "Q4 roadmap", date: Date(timeIntervalSince1970: 0), duration: 38 * 60,
            summary: "## Plan\nShip before the holidays.",
            actionItems: [.init("Send the deck"), .init("Book a room", isDone: true)],
            transcript: lines, link: URL(string: "https://h.omi.me/conversations/c1")
        )
        let text = ConversationDigest.markdown(
            export,
            labels: .init(summary: "Summary", actionItems: "Action items", transcript: "Transcript", link: "Link"),
            calendar: calendar, locale: Locale(identifier: "en_US")
        )
        #expect(text.hasPrefix("# Q4 roadmap\n\n"))
        #expect(text.contains("· 38 min"))
        #expect(text.contains("## Summary\n\n### Plan\nShip before the holidays."))
        #expect(text.contains("- [ ] Send the deck\n- [x] Book a room"))
        #expect(text.contains("[0:04] **You:** Ship it.\n[1:05] **Anna:** Agreed."))
        #expect(text.hasSuffix("Link: https://h.omi.me/conversations/c1\n"))
    }
}
