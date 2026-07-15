import XCTest

@testable import Omi_Computer

final class ChatFirstRichBlockTests: XCTestCase {
  func testCodecRoundTripsEveryChatFirstBlock() throws {
    let blocks: [ChatContentBlock] = [
      .questionCard(
        id: "question-card",
        questionId: "question-1",
        text: "Which goal should we focus on?",
        subjectKind: "goal",
        subjectId: "goal-1",
        options: [[
          "optionId": "focus-goal-1",
          "label": "Keep this goal",
          "preparedAnswer": "Keep goal 1 as my focus",
          "defer": false,
        ]]
      ),
      .taskCard(id: "task-card", taskId: "task-1"),
      .goalLink(id: "goal-link", goalId: "goal-1", summary: "Finish the launch plan"),
      .captureLink(
        id: "capture-link",
        conversationId: "capture-1",
        momentTimestampMs: 42_000,
        summary: "Planning conversation"
      ),
    ]

    let encoded = try XCTUnwrap(ChatContentBlockCodec.encode(blocks))
    let restored = try XCTUnwrap(ChatContentBlockCodec.decode(encoded))
    XCTAssertEqual(restored.count, blocks.count)

    guard case .questionCard(_, let questionID, let text, let subjectKind, let subjectID, let options) = restored[0]
    else { return XCTFail("question card should survive persisted replay") }
    XCTAssertEqual(questionID, "question-1")
    XCTAssertEqual(text, "Which goal should we focus on?")
    XCTAssertEqual(subjectKind, "goal")
    XCTAssertEqual(subjectID, "goal-1")
    XCTAssertEqual(options.first?["preparedAnswer"] as? String, "Keep goal 1 as my focus")

    guard case .taskCard(_, let taskID) = restored[1] else {
      return XCTFail("task card should survive persisted replay")
    }
    XCTAssertEqual(taskID, "task-1")

    guard case .goalLink(_, let goalID, let goalSummary) = restored[2] else {
      return XCTFail("goal link should survive persisted replay")
    }
    XCTAssertEqual(goalID, "goal-1")
    XCTAssertEqual(goalSummary, "Finish the launch plan")

    guard case .captureLink(_, let captureID, let timestamp, let captureSummary) = restored[3] else {
      return XCTFail("capture link should survive persisted replay")
    }
    XCTAssertEqual(captureID, "capture-1")
    XCTAssertEqual(timestamp, 42_000)
    XCTAssertEqual(captureSummary, "Planning conversation")
  }

  func testUnknownPersistedBlockDoesNotDropRecognizedNeighbors() throws {
    let restored = ChatContentBlockCodec.decode([
      ["type": "text", "id": "before", "text": "Before"],
      ["type": "futureCard", "id": "future", "payload": "new server version"],
      ["type": "goalLink", "id": "after", "goalId": "goal-1", "summary": "After"],
    ])

    XCTAssertEqual(restored.count, 2)
    guard case .text(let textID, let text) = restored[0] else {
      return XCTFail("known text before an unknown block must remain")
    }
    XCTAssertEqual(textID, "before")
    XCTAssertEqual(text, "Before")
    guard case .goalLink(_, let goalID, let summary) = restored[1] else {
      return XCTFail("known block after an unknown block must remain")
    }
    XCTAssertEqual(goalID, "goal-1")
    XCTAssertEqual(summary, "After")
  }

  func testRichRendererSelectionRequiresExplicitChatFirstContext() {
    let blocks: [ChatContentBlock] = [
      .questionCard(
        id: "question", questionId: "question-1", text: "Question", subjectKind: "goal", subjectId: "goal-1",
        options: []
      ),
      .taskCard(id: "task", taskId: "task-1"),
      .goalLink(id: "goal", goalId: "goal-1", summary: "Goal"),
      .captureLink(id: "capture", conversationId: "capture-1", momentTimestampMs: nil, summary: "Capture"),
    ]

    XCTAssertTrue(
      ContentBlockGroup.visibleChatGroups(blocks, isStreaming: false).isEmpty,
      "legacy, floating, task, and onboarding call sites must keep rich blocks inert"
    )

    let enabled = ContentBlockGroup.visibleChatGroups(
      blocks,
      isStreaming: false,
      richBlockRenderingEnabled: true
    )
    XCTAssertEqual(enabled.count, 4)
    XCTAssertTrue(enabled.contains { if case .questionCard = $0 { return true }; return false })
    XCTAssertTrue(enabled.contains { if case .taskCard = $0 { return true }; return false })
    XCTAssertTrue(enabled.contains { if case .goalLink = $0 { return true }; return false })
    XCTAssertTrue(enabled.contains { if case .captureLink = $0 { return true }; return false })
  }

  func testTaskAcknowledgementRequiresReconciledCompletedRecord() {
    let incomplete = task(id: "task-1", completed: false)
    let completed = task(id: "task-1", completed: true)

    XCTAssertTrue(
      ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
        intendedCompletion: true,
        reconciledTask: completed
      )
    )
    XCTAssertFalse(
      ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
        intendedCompletion: true,
        reconciledTask: incomplete
      ),
      "a store rollback must not produce a chat-card success acknowledgement"
    )
    XCTAssertFalse(
      ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
        intendedCompletion: false,
        reconciledTask: incomplete
      )
    )
    XCTAssertFalse(
      ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
        intendedCompletion: true,
        reconciledTask: nil
      )
    )
  }

  private func task(id: String, completed: Bool) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "Draft the plan",
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0)
    )
  }
}
