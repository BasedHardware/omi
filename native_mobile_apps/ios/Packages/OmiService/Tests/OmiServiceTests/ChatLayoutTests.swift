import Foundation
import OmiCore
@testable import OmiService
import Testing

/// The thread's layout rules: split answers, grouped bubbles, extras, stacks, the bottom, the header.
struct ChatBubbleSplitTests {
    @Test func shortAnswersStayOneBubble() {
        #expect(ChatBubbleSplit.split("Lunch with Anna at 1.") == ["Lunch with Anna at 1."])
        #expect(ChatBubbleSplit.split("  \n ").isEmpty)
    }

    @Test func paragraphsBecomeBubbles() {
        let text = "First **thing**.\n\nSecond, with a [link](https://omi.me).\n\n\nThird."
        #expect(ChatBubbleSplit.split(text) == ["First **thing**.", "Second, with a [link](https://omi.me).", "Third."])
    }

    @Test func listsTablesAndQuotesStayTogether() {
        let list = "- one\n\n- two\n\n- three"
        #expect(ChatBubbleSplit.split(list) == ["- one\n\n- two\n\n- three"])
        let table = "| a | b |\n|---|---|\n\n| 1 | 2 |"
        #expect(ChatBubbleSplit.split(table).count == 1)
        let quote = "> Hi Anna,\n\n> see you Thursday."
        #expect(ChatBubbleSplit.split(quote).count == 1)
    }

    @Test func headingsAndIntrosStayWithWhatFollows() {
        let text = "## Plan\n\nWe start Monday.\n\nHere is what I found:\n\n1. The deck\n2. The notes"
        #expect(ChatBubbleSplit.split(text) == ["## Plan\n\nWe start Monday.", "Here is what I found:\n\n1. The deck\n2. The notes"])
    }

    @Test func codeIsNeverCut() {
        let text = "Run this:\n\n```\nmake build\n\nmake test\n```\n\nDone."
        #expect(ChatBubbleSplit.split(text) == ["Run this:\n\n```\nmake build\n\nmake test\n```", "Done."])
    }

    @Test func atMostFourBubbles() {
        let text = (1 ... 6).map { "Part \($0)." }.joined(separator: "\n\n")
        let parts = ChatBubbleSplit.split(text)
        #expect(parts.count == ChatBubbleSplit.maxBubbles)
        #expect(parts.last == "Part 4.\n\nPart 5.\n\nPart 6.")
    }

    /// While an answer streams, finished paragraphs keep their bubbles; only the end changes.
    @Test func streamingOnlyChangesTheEnd() {
        let full = "One.\n\nTwo.\n\nThree is longer."
        let final = ChatBubbleSplit.split(full)
        #expect(final == ["One.", "Two.", "Three is longer."])
        for end in full.indices {
            let parts = ChatBubbleSplit.split(String(full[...end]))
            #expect(Array(parts.dropLast()) == Array(final.prefix(max(0, parts.count - 1))))
        }
        // A loose list joins its items as they arrive (the bubble before the end grows).
        #expect(ChatBubbleSplit.split("One.\n\n- a\n\n- b") == ["One.", "- a\n\n- b"])
    }
}

struct ChatGroupingTests {
    let now = Date(timeIntervalSince1970: 1_000_000)

    @Test func sameSenderInARowIsOneGroup() {
        let positions = ChatGrouping.positions([
            .init(id: "day", sender: nil),
            .init(id: "q1", sender: .user, date: now),
            .init(id: "q2", sender: .user, date: now.addingTimeInterval(30)),
            .init(id: "a1", sender: .omi, date: now.addingTimeInterval(40)),
            .init(id: "a2", sender: .omi, date: now.addingTimeInterval(50)),
            .init(id: "a3", sender: .omi, date: now.addingTimeInterval(60)),
        ])
        #expect(positions["day"] == nil)
        #expect(positions["q1"] == .init(isFirst: true, isLast: false))
        #expect(positions["q2"] == .init(isFirst: false, isLast: true))
        #expect(positions["a1"] == .init(isFirst: true, isLast: false))
        #expect(positions["a2"] == .init(isFirst: false, isLast: false))
        #expect(positions["a3"] == .init(isFirst: false, isLast: true))
    }

    @Test func dayLinesRunsGapsAndExtrasEndAGroup() {
        let positions = ChatGrouping.positions([
            .init(id: "q1", sender: .user, date: now),
            .init(id: "run", sender: nil),
            .init(id: "q2", sender: .user, date: now.addingTimeInterval(10)),
            .init(id: "q3", sender: .user, date: now.addingTimeInterval(ChatGrouping.maxGap + 60)),
            .init(id: "a1", sender: .omi, date: now.addingTimeInterval(ChatGrouping.maxGap + 70), endsWithExtras: true),
            .init(id: "a2", sender: .omi, date: now.addingTimeInterval(ChatGrouping.maxGap + 80)),
            .init(id: "a3", sender: .omi, date: now.addingTimeInterval(ChatGrouping.maxGap + 90), leadsWithExtras: true),
        ])
        for id in ["q1", "q2", "q3", "a1", "a2", "a3"] {
            #expect(positions[id] == .alone, "\(id)")
        }
    }
}

struct ChatAnswerExtrasTests {
    @Test func theLatestAnswerKeepsItsChipsAndFollowUp() {
        let shown = ChatAnswerExtras.shown(.init(isLatest: true, citations: 2, hasFollowUp: true), draftIsEmpty: true, isSpeaking: false)
        #expect(shown == .init(sources: .chips, followUp: true, stopReading: false))
    }

    @Test func olderAnswersFoldTheirSources() {
        let answer = ChatAnswerExtras.Answer(isLatest: false, citations: 2, hasFollowUp: true)
        let older = ChatAnswerExtras.shown(answer, draftIsEmpty: true, isSpeaking: false)
        #expect(older == .init(sources: .collapsed(2), followUp: false, stopReading: false))
        let opened = ChatAnswerExtras.shown(answer, draftIsEmpty: true, isSpeaking: false, sourcesExpanded: true)
        #expect(opened.sources == .chips)
    }

    @Test func theFollowUpWaitsForTheAnswerAndAnEmptyComposer() {
        func followUp(streaming: Bool = false, failed: Bool = false, draftIsEmpty: Bool = true) -> Bool {
            let answer = ChatAnswerExtras.Answer(isLatest: true, isStreaming: streaming, failed: failed, hasFollowUp: true)
            return ChatAnswerExtras.shown(answer, draftIsEmpty: draftIsEmpty, isSpeaking: false).followUp
        }
        #expect(followUp())
        #expect(!followUp(streaming: true))
        #expect(!followUp(failed: true))
        #expect(!followUp(draftIsEmpty: false))
    }

    @Test func stopReadingOnlyWhileSpeaking() {
        let older = ChatAnswerExtras.Answer(isLatest: false)
        #expect(ChatAnswerExtras.shown(older, draftIsEmpty: true, isSpeaking: false).isEmpty)
        #expect(ChatAnswerExtras.shown(older, draftIsEmpty: true, isSpeaking: true).stopReading)
        let failed = ChatAnswerExtras.Answer(isLatest: true, failed: true, citations: 3, hasFollowUp: true)
        #expect(ChatAnswerExtras.shown(failed, draftIsEmpty: true, isSpeaking: false).sources == .none)
    }
}

struct ChatStackingTests {
    @Test func cardsOfAKindInARowStack() {
        let cards: [ChatCard] = [
            .connect("gmail"), .connect("google_calendar"),
            .taskAdded(id: "1", title: "A"), .taskAdded(id: "2", title: "B"), .taskAdded(id: "3", title: "C"),
            .taskCompleted(id: "4", title: "D"), .taskAdded(id: "5", title: "E"),
        ]
        let stacks = ChatStacking.stacks(cards, kind: \.kind)
        #expect(stacks.map(\.count) == [2, 3, 1, 1])
        #expect(ChatStacking.stacks([Int](), kind: String.init).isEmpty)
    }
}

struct ChatBottomTrackerTests {
    @Test func atTheBottomWithinTheThreshold() {
        // 1000 pt of content in a 600 pt list with a 100 pt composer: the end is at offset 500.
        #expect(ChatBottomTracker.isAtBottom(offsetY: 500, containerHeight: 600, bottomInset: 100, contentHeight: 1000))
        #expect(ChatBottomTracker.isAtBottom(offsetY: 421, containerHeight: 600, bottomInset: 100, contentHeight: 1000))
        #expect(!ChatBottomTracker.isAtBottom(offsetY: 419, containerHeight: 600, bottomInset: 100, contentHeight: 1000))
        // A fling that bounces past the end still counts.
        #expect(ChatBottomTracker.isAtBottom(offsetY: 540, containerHeight: 600, bottomInset: 100, contentHeight: 1000))
    }

    @Test func onlyTheUsersScrollLeavesTheBottom() {
        var tracker = ChatBottomTracker()
        // A growing answer (no scrolling) pushes the end away: still following.
        tracker.geometryChanged(atBottom: false)
        #expect(tracker.isAtBottom)
        // The user drags up: no longer at the bottom.
        tracker.phaseChanged(isIdle: false)
        tracker.geometryChanged(atBottom: false)
        tracker.phaseChanged(isIdle: true)
        #expect(!tracker.isAtBottom)
    }

    /// The bug the arrow had: scrolled back down by hand, it stayed. Coming to rest at the end clears it.
    @Test func scrollingBackDownClearsTheArrow() {
        var tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle: false)
        tracker.geometryChanged(atBottom: false)
        tracker.phaseChanged(isIdle: true)
        #expect(!tracker.isAtBottom)
        // Back down: the last geometry update during the drag may still say "not yet"; it ends at the bottom.
        tracker.phaseChanged(isIdle: false)
        tracker.geometryChanged(atBottom: false)
        tracker.geometryChanged(atBottom: true)
        #expect(tracker.isAtBottom)
        tracker.phaseChanged(isIdle: true)
        #expect(tracker.isAtBottom)
    }

    /// A fling that ends at the end while the geometry settles after the phase: resting there counts.
    @Test func reachingTheEndWhileIdleCounts() {
        var tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle: false)
        tracker.geometryChanged(atBottom: false)
        tracker.phaseChanged(isIdle: true)
        tracker.geometryChanged(atBottom: true)
        #expect(tracker.isAtBottom)
    }

    @Test func jumpingGoesBackToFollowing() {
        var tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle: false)
        tracker.geometryChanged(atBottom: false)
        tracker.phaseChanged(isIdle: true)
        tracker.jumpedToBottom()
        #expect(tracker.isAtBottom)
        // The answer growing right after the jump does not bring the arrow back.
        tracker.geometryChanged(atBottom: false)
        #expect(tracker.isAtBottom)
    }
}
