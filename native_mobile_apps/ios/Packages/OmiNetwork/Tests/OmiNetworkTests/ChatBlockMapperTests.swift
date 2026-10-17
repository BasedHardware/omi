import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// `content_blocks` as they arrive: two dialects, a JSON string on a push, and every kind of
/// damage a single block can carry (a missing field, an unknown type, a whole block absent).
struct ChatBlockMapperTests {
    @Test func aTaskCardReadsInBothDialects() throws {
        let json = #"[{"id":"b1","type":"taskCard","taskId":"t1"}]"#
        let camel = try #require(try ChatBlockMapper.blocks(from: array(json)).first)
        #expect(camel.id == "b1")
        #expect(camel.kind == .task(taskID: "t1"))

        let snake = try #require(try ChatBlockMapper.blocks(from: array(#"[{"id":"b2","type":"task_card","task_id":"t2"}]"#)).first)
        #expect(snake.kind == .task(taskID: "t2"))
    }

    @Test func aBlockWithoutATaskIdIsOnlyItsLine() {
        let blocks = ChatBlockMapper.blocks(from: [["id": "b1", "type": "taskCard"]])
        #expect(blocks.map(\.kind) == [.other(type: "taskCard")])
        #expect(blocks.first?.fallbackText == "Task")
    }

    @Test func aGoalAndAMemoryLinkNeedTheirIdAndSummary() {
        let goal = ChatBlockMapper.blocks(from: [["id": "g", "type": "goalLink", "goalId": "g1", "summary": "Run 10k"]])
        #expect(goal.first?.kind == .goal(goalID: "g1", summary: "Run 10k"))
        // No summary: not a link, only the line.
        let bare = ChatBlockMapper.blocks(from: [["id": "g", "type": "goal_link", "goal_id": "g1"]])
        #expect(bare.first?.kind == .other(type: "goal_link"))
        #expect(bare.first?.fallbackText == "Goal")

        let memory = ChatBlockMapper.blocks(from: [["id": "m", "type": "memoryLink", "memoryId": "m1", "summary": "Lives in Berlin"]])
        #expect(memory.first?.kind == .memory(memoryID: "m1", summary: "Lives in Berlin"))
        let bareMemory = ChatBlockMapper.blocks(from: [["id": "m", "type": "memoryLink", "memory_id": "m1"]])
        #expect(bareMemory.first?.kind == .other(type: "memoryLink"))
    }

    @Test func aConversationLinkCarriesItsStepsAndWhetherItIsACapture() throws {
        let json = #"""
        [{"id":"c","type":"conversationLink","conversationId":"c1","summary":"Standup","recommended_action_items":[
        {"description":"Book the room","taskId":"t9"},{"description":"Book the room"},{"taskId":"t8"}]}]
        """#
        let block = try #require(try ChatBlockMapper.blocks(from: array(json)).first)
        // A hint without a description is dropped; the same line twice is kept (the mapper does not dedupe).
        #expect(block.kind == .conversation(
            conversationID: "c1", summary: "Standup",
            actionItems: [
                .init(description: "Book the room", taskID: "t9"),
                .init(description: "Book the room", taskID: nil),
            ],
            isCapture: false
        ))
        #expect(block.fallbackText == "Meeting notes ready - Standup")

        let capture = ChatBlockMapper.blocks(from: [["id": "c", "type": "capture_link", "conversation_id": "c2", "summary": "Walk"]])
        #expect(capture.first?.kind == .conversation(
            conversationID: "c2", summary: "Walk", actionItems: [], isCapture: true
        ))
    }

    /// A conversation link with no summary has nothing to draw, so only its line stays.
    @Test func aLinkWithoutItsSummaryFallsBackToItsLine() {
        let blocks = ChatBlockMapper.blocks(from: [["id": "c", "type": "conversationLink", "conversationId": "c1"]])
        #expect(blocks.map(\.kind) == [.other(type: "conversationLink")])
        #expect(blocks.first?.fallbackText == "Meeting notes ready")
    }

    @Test func aQuestionKeepsItsPreparedAnswers() throws {
        let json = #"""
        [{"id":"q","type":"questionCard","questionId":"q1","text":"Which one?","subject":{"kind":"task","id":"t1"},
        "options":[{"optionId":"o1","label":"The roof","preparedAnswer":"Go with the roof"},{"optionId":"o2","label":"The cellar"}]}]
        """#
        let block = try #require(try ChatBlockMapper.blocks(from: array(json)).first)
        guard case let .question(question) = block.kind else {
            Issue.record("not a question: \(block.kind)")
            return
        }
        #expect(question.questionID == "q1")
        #expect(question.text == "Which one?")
        #expect(question.options.map(\.id) == ["o1", "o2"])
        // An option with no prepared answer sends its own label.
        #expect(question.options.map(\.preparedAnswer) == ["Go with the roof", "The cellar"])
        #expect(question.visibleOptions.count == 2)
        #expect(!question.isAnswered)
    }

    @Test func anAnsweredQuestionShowsOnlyTheChosenOption() throws {
        let json = #"""
        [{"id":"q","type":"questionCard","questionId":"q1","text":"Which one?","subject":{"kind":"task","id":"t1"},
        "selectedOptionId":"o2","options":[{"optionId":"o1","label":"The roof"},{"optionId":"o2","label":"The cellar"}]}]
        """#
        let block = try #require(try ChatBlockMapper.blocks(from: array(json)).first)
        guard case let .question(question) = block.kind else {
            Issue.record("not a question: \(block.kind)")
            return
        }
        #expect(question.isAnswered)
        #expect(question.visibleOptions.map(\.label) == ["The cellar"])
    }

    /// A question is a question only with its subject and at least one usable option; anything
    /// less keeps the question's line (the word "Question" when it carries no text of its own).
    @Test func aBrokenQuestionIsOnlyItsLine() {
        let partials: [([String: Any], String?)] = [
            (["id": "q", "type": "question_card", "questionId": "q1", "options": [["optionId": "o1", "label": "A"]]], "Question"),
            (["id": "q", "type": "question_card", "questionId": "q1", "text": "Which?", "subject": ["kind": "task"]], "Which?"),
            (["id": "q", "type": "question_card", "questionId": "q1", "text": "Which?",
              "subject": ["kind": "task", "id": "t1"], "options": []], "Which?"),
            (["id": "q", "type": "question_card", "questionId": "q1", "text": "Which?", "subject": ["kind": "task", "id": "t1"],
              "options": [["label": "No id"]]], "Which?"),
            (["id": "q", "type": "question_card", "question_id": "q1", "text": "Which?", "subject": ["kind": "task", "id": "t1"],
              "options": [["option_id": "o1", "label": "The roof"]]], nil),
        ]
        for (partial, line) in partials {
            let block = ChatBlockMapper.blocks(from: [partial]).first
            guard let line else {
                // The snake_case spelling of an option is read like the camelCase one.
                #expect(block?.kind == .question(ChatQuestion(
                    questionID: "q1", text: "Which?", options: [.init(id: "o1", label: "The roof", preparedAnswer: "The roof")],
                    selectedOptionID: nil
                )), "\(partial)")
                continue
            }
            #expect(block?.kind == .other(type: "question_card"), "\(partial)")
            #expect(block?.fallbackText == line, "\(partial)")
        }
    }

    @Test func anAgentSpawnIsRunningAndACompletionCarriesItsStatus() {
        let spawn = ChatBlockMapper.blocks(from: [
            ["id": "a1", "type": "agentSpawn", "sessionId": "s", "runId": "r", "title": "Check flights", "objective": "Find one"],
        ]).first
        #expect(spawn?.kind == .agentRun(title: "Check flights", detail: "Find one", status: .running))

        func completion(_ status: String?) -> ChatBlock.Kind? {
            var object: [String: Any] = ["id": "a2", "type": "agent_completion", "title": "Did it", "output": "Booked"]
            object["status"] = status
            return ChatBlockMapper.blocks(from: [object]).first?.kind
        }
        #expect(completion("completed") == .agentRun(title: "Did it", detail: "Booked", status: .completed))
        #expect(completion("succeeded") == .agentRun(title: "Did it", detail: "Booked", status: .completed))
        #expect(completion("cancelled") == .agentRun(title: "Did it", detail: "Booked", status: .cancelled))
        #expect(completion("timed_out") == .agentRun(title: "Did it", detail: "Booked", status: .timedOut))
        #expect(completion("failed") == .agentRun(title: "Did it", detail: "Booked", status: .failed))
        // An unknown word is not read as success.
        #expect(completion("banana") == .agentRun(title: "Did it", detail: "Booked", status: .failed))
        // Older stored completions carry no status at all: they completed.
        #expect(completion(nil) == .agentRun(title: "Did it", detail: "Booked", status: .completed))
    }

    @Test func aSpawnWithoutARunIsOnlyItsLine() {
        let blocks = ChatBlockMapper.blocks(from: [["id": "a1", "type": "agent_spawn", "session_id": "s", "title": "Check flights"]])
        #expect(blocks.map(\.kind) == [.other(type: "agent_spawn")])
    }

    @Test func aDiscoveryCarriesItsLongTextAndItsLine() {
        let blocks = ChatBlockMapper.blocks(from: [
            ["id": "d", "type": "discoveryCard", "title": "A cafe", "summary": "Nearby", "fullText": "Two doors down, open late."],
        ])
        #expect(blocks.first?.kind == .discovery(title: "A cafe", summary: "Nearby", fullText: "Two doors down, open late."))
        #expect(blocks.first?.fallbackText == "Discovery - A cafe - Nearby")
    }

    @Test func aMemoryReviewKeepsThreeItemsAtMost() throws {
        let items = (1 ... 5).map { #"{"memoryId":"m\#($0)","content":"Fact \#($0)","category":"system"}"# }.joined(separator: ",")
        let json = #"[{"id":"r","type":"memory_review_card","summaryId":"s1","date":"2026-10-12","items":[\#(items)]}]"#
        let block = try #require(try ChatBlockMapper.blocks(from: array(json)).first)
        guard case let .memoryReview(review) = block.kind else {
            Issue.record("not a review: \(block.kind)")
            return
        }
        #expect(review.summaryID == "s1")
        #expect(review.date == "2026-10-12")
        #expect(review.items.map(\.memoryID) == ["m1", "m2", "m3"])
        #expect(review.items.first?.content == "Fact 1")
        // The review card draws its own heading: it says nothing as a line.
        #expect(block.fallbackText.isEmpty)
    }

    @Test func aReviewWithNothingUsableIsNoCard() {
        // Items without an id or without text are dropped, and a card with none left is nothing.
        let blocks = ChatBlockMapper.blocks(from: [
            ["id": "r", "type": "memoryReviewCard", "items": [["content": "No id"], ["memoryId": "m1"]]],
        ])
        #expect(blocks.isEmpty)
    }

    /// The follow-up chip and the evidence envelope are read elsewhere; they must not double as cards.
    @Test func theFollowUpAndEvidenceBlocksAreLeftOut() {
        let blocks = ChatBlockMapper.blocks(from: [
            ["id": "f", "type": "followUp", "text": "Want Tuesday too?"],
            ["id": "e", "type": "evidence", "references": []],
            ["id": "e2", "type": "evidence_envelope"],
            ["id": "t", "type": "taskCard", "taskId": "t1"],
        ])
        #expect(blocks.map(\.id) == ["t"])
    }

    @Test func anUnknownTypeKeepsItsLine() {
        let blocks = ChatBlockMapper.blocks(from: [["id": "x", "type": "quantumLeap", "title": "Leap", "summary": "Up"]])
        #expect(blocks.map(\.kind) == [.other(type: "quantumLeap")])
        #expect(blocks.first?.fallbackText == "Chat item - Leap - Up")
    }

    /// A block with no id still renders, under an id of its own; a drawing type without one is
    /// not drawn (there would be nothing to address it by).
    @Test func aBlockWithoutAnIdGetsOneOfItsOwn() {
        let blocks = ChatBlockMapper.blocks(from: [
            ["type": "taskCard", "taskId": "t1"],
            ["type": "thinking", "text": "Looking at the calendar"],
        ])
        #expect(blocks.map(\.id) == ["block-0", "block-1"])
        #expect(blocks[0].kind == .other(type: "taskCard"))
        #expect(blocks[1].kind == .other(type: "thinking"))
        #expect(blocks[1].fallbackText == "Thinking - Looking at the calendar")
    }

    /// A block with neither a card nor a line of its own leaves no empty row behind.
    @Test func aBlockWithNeitherKindNorLineIsDropped() {
        #expect(ChatBlockMapper.blocks(from: [["id": "r", "type": "memoryReviewCard"]]).isEmpty)
        // The review card is the only type whose line is empty by design: a broken one is nothing.
        #expect(ChatBlockMapper.fallbackText(["type": "memoryReviewCard"]).isEmpty)
    }

    @Test func theBlockArrayAlsoArrivesAsAJSONString() {
        // A push sends the same array as a string.
        let text = #"[{"id":"b1","type":"taskCard","taskId":"t1"},"# +
            #"{"id":"b2","type":"questionCard","questionId":"q1","text":"Which?","# +
            #""subject":{"kind":"task","id":"t1"},"options":[{"optionId":"o1","label":"A"}]}]"#
        let blocks = ChatBlockMapper.blocks(from: text)
        #expect(blocks.map(\.id) == ["b1", "b2"])
        #expect(blocks.first?.kind == .task(taskID: "t1"))
        // Garbage in a string is no blocks at all, never a crash.
        #expect(ChatBlockMapper.blocks(from: "not json").isEmpty)
        #expect(ChatBlockMapper.blocks(from: #"{"type":"taskCard"}"#).isEmpty)
        #expect(ChatBlockMapper.blocks(from: nil).isEmpty)
        #expect(ChatBlockMapper.blocks(from: 42).isEmpty)
    }

    @Test func aMessageReadsItsBlocksAndItsKindOffTheWire() throws {
        let json = #"""
        {"id":"m1","text":"Buy milk","sender":"ai","created_at":"2026-10-12T09:00:00Z","type":"day_summary",
        "content_blocks":[{"id":"b1","type":"taskCard","taskId":"t1"}]}
        """#
        let message = try #require(ChatMessageMapper.message(fromJSON: Data(json.utf8)))
        #expect(message.kind == .daySummary)
        #expect(message.blocks.map(\.kind) == [.task(taskID: "t1")])
        #expect(message.blocks.first?.fallbackText == "Task")
    }

    /// A message with no `type`, and one with a type this client does not know, are both plain text.
    @Test func anUnknownMessageKindReadsAsText() throws {
        let plain = try #require(ChatMessageMapper.message(fromJSON: Data(#"{"id":"m2","text":"Hi","sender":"ai"}"#.utf8)))
        #expect(plain.kind == .text)
        #expect(plain.blocks.isEmpty)
        let odd = try #require(ChatMessageMapper.message(
            fromJSON: Data(#"{"id":"m3","text":"Hi","sender":"ai","type":"recap_v9"}"#.utf8)
        ))
        #expect(odd.kind == .text)
    }

    private func array(_ json: String) throws -> [[String: Any]] {
        try #require(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [[String: Any]])
    }
}
