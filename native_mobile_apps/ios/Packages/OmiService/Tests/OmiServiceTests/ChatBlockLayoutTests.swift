import Foundation
import OmiCore
@testable import OmiService
import Testing

/// How a turn's blocks sit against its body. Fixtures only: the cards themselves are proved on
/// screen, these are the rules underneath them.
struct ChatBlockLayoutTests {
    private func message(_ text: String, _ blocks: [ChatBlock], kind: ChatMessage.Kind = .text) -> ChatMessage {
        var message = ChatMessage(id: "m1", text: text, sender: .omi, createdAt: .now)
        message.blocks = blocks
        message.kind = kind
        return message
    }

    @Test func aCardPerActableKind() {
        #expect(ChatBlockLayout.isRenderable(.task(taskID: "t")))
        #expect(ChatBlockLayout.isRenderable(.goal(goalID: "g", summary: "s")))
        #expect(ChatBlockLayout.isRenderable(.memory(memoryID: "m", summary: "s")))
        #expect(ChatBlockLayout.isRenderable(.conversation(conversationID: "c", summary: "s", actionItems: [], isCapture: false)))
        #expect(ChatBlockLayout.isRenderable(.discovery(title: "t", summary: "s", fullText: "f")))
        #expect(ChatBlockLayout.isRenderable(.question(ChatQuestion(questionID: "q", text: "?", options: [], selectedOptionID: nil))))
        #expect(ChatBlockLayout.isRenderable(.agentRun(title: "t", detail: "d", status: .running)))
        #expect(ChatBlockLayout.isRenderable(.memoryReview(ChatMemoryReview(summaryID: "s", date: "2026-10-12", items: []))))
        // A type this client does not draw is not a card, and neither is a plain text block.
        #expect(!ChatBlockLayout.isRenderable(.text("hello")))
        #expect(!ChatBlockLayout.isRenderable(.other(type: "quantumLeap")))
    }

    @Test func cardsReplaceABodyThatWasOnlyTheirFallback() {
        let block = ChatBlock(id: "b1", kind: .task(taskID: "t1"), fallbackText: "Buy milk")
        #expect(ChatBlockLayout.blocksReplaceBody(message("Buy milk", [block])))
        // Whitespace differences are the same body.
        #expect(ChatBlockLayout.blocksReplaceBody(message("  Buy\n milk ", [block])))
        // An empty body has nothing of its own to keep.
        #expect(ChatBlockLayout.blocksReplaceBody(message("", [block])))
    }

    @Test func aBodyOfItsOwnStays() {
        let block = ChatBlock(id: "b1", kind: .task(taskID: "t1"), fallbackText: "Buy milk")
        #expect(!ChatBlockLayout.blocksReplaceBody(message("I added that to your list.", [block])))
        #expect(!ChatBlockLayout.blocksReplaceBody(message("Buy milk and eggs", [block])))
    }

    @Test func aTextOnlyTurnIsUntouched() {
        let text = ChatBlock(id: "b1", kind: .text("Hello there"), fallbackText: "Hello there")
        #expect(!ChatBlockLayout.blocksReplaceBody(message("Hello there", [text])))
        #expect(!ChatBlockLayout.blocksReplaceBody(message("Nothing at all", [])))
    }

    @Test func aDaySummaryKeepsItsBody() {
        let block = ChatBlock(id: "b1", kind: .task(taskID: "t1"), fallbackText: "Buy milk")
        #expect(!ChatBlockLayout.blocksReplaceBody(message("Buy milk", [block], kind: .daySummary)))
    }

    /// The review card is chrome: a turn that is only a review card is no body to replace.
    @Test func aReviewCardNeverReplacesTheBody() {
        let review = ChatBlock(
            id: "b1",
            kind: .memoryReview(ChatMemoryReview(summaryID: "s", date: "2026-10-12", items: [])),
            fallbackText: "Things I learned today"
        )
        #expect(!ChatBlockLayout.blocksReplaceBody(message("Things I learned today", [review])))
        #expect(!ChatBlockLayout.blocksReplaceBody(message("", [review])))
        // Beside a card that does carry the turn, the review card no longer blocks the replacement.
        let task = ChatBlock(id: "b2", kind: .task(taskID: "t1"), fallbackText: "Buy milk")
        #expect(ChatBlockLayout.blocksReplaceBody(message("Buy milk\nThings I learned today", [task, review])))
    }

    /// The lines a card cannot draw stay readable when the cards took the body away.
    @Test func linesWithoutACardSurviveABodyReplacement() {
        let thinking = ChatBlock(id: "b1", kind: .other(type: "thinking"), fallbackText: "Thinking about it")
        let task = ChatBlock(id: "b2", kind: .task(taskID: "t1"), fallbackText: "Buy milk")
        let blocks = [thinking, task, ChatBlock(id: "b3", kind: .text("  "), fallbackText: "   ")]
        #expect(ChatBlockLayout.fallbackLines(blocks) == ["Thinking about it"])
        #expect(ChatBlockLayout.structuredFallback(blocks) == "Thinking about it\nBuy milk")
    }
}

/// The day summary's list, as Flutter `DaySummaryWidget.splitMessage` reads it.
struct ChatDaySummaryTests {
    @Test func aNumberedListLosesItsNumbers() {
        let text = "1. Walked with Anna\n2. Finished the deck\n3. Booked the flight"
        #expect(ChatDaySummary.items(text) == ["Walked with Anna", "Finished the deck", "Booked the flight"])
    }

    @Test func proseSplitsAtSentenceEnds() {
        #expect(ChatDaySummary.items("Swam at the lake. Finished the deck.") == ["Swam at the lake", "Finished the deck"])
        #expect(ChatDaySummary.items("One thing happened") == ["One thing happened"])
        #expect(ChatDaySummary.items("Done.") == ["Done"])
    }

    @Test func nothingInNothingOut() {
        #expect(ChatDaySummary.items("") .isEmpty)
        #expect(ChatDaySummary.items("  \n ") .isEmpty)
    }
}
