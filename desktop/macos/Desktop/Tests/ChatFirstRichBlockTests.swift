import XCTest

@testable import Omi_Computer

final class ChatFirstRichBlockTests: XCTestCase {
  func testBlockWireRejectsTheEntireToolPayloadWhenAnyBlockIsMalformed() {
    let converted = ChatFirstBlockWire.backendBlocks(
      from: [
        "blocks": [
          ["type": "taskCard", "taskId": "task-1"],
          ["type": "taskCard"],
        ]
      ]
    )

    XCTAssertNil(converted, "render_chat_blocks must fail closed instead of rendering a valid subset")
  }

  func testBlockWirePreservesEveryValidatedToolBlock() throws {
    let converted = try XCTUnwrap(
      ChatFirstBlockWire.backendBlocks(
        from: [
          "blocks": [
            ["type": "taskCard", "taskId": "task-1"],
            ["type": "goalLink", "goalId": "goal-1", "summary": "Ship the plan"],
          ]
        ]
      )
    )

    XCTAssertEqual(converted.count, 2)
    XCTAssertEqual(converted[0]["task_id"] as? String, "task-1")
    XCTAssertEqual(converted[1]["goal_id"] as? String, "goal-1")
  }

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

    guard case .questionCard(_, let questionID, let text, let subjectKind, let subjectID, let options, let selectedOptionID) = restored[0]
    else { return XCTFail("question card should survive persisted replay") }
    XCTAssertEqual(questionID, "question-1")
    XCTAssertEqual(text, "Which goal should we focus on?")
    XCTAssertEqual(subjectKind, "goal")
    XCTAssertEqual(subjectID, "goal-1")
    XCTAssertEqual(options.first?["preparedAnswer"] as? String, "Keep goal 1 as my focus")
    XCTAssertNil(selectedOptionID)

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

  func testQuestionSelectionReceiptRoundTripsAndRetiresTheOptions() throws {
    let selected = ChatContentBlock.questionCard(
      id: "question-card",
      questionId: "question-1",
      text: "Which goal should we focus on?",
      subjectKind: "goal",
      subjectId: "goal-1",
      options: [[
        "optionId": "focus-goal-1",
        "label": "Keep this goal",
        "preparedAnswer": "Keep goal 1 as my focus",
      ]],
      selectedOptionId: "focus-goal-1"
    )

    let encoded = try XCTUnwrap(ChatContentBlockCodec.encode([selected]))
    let restoredBlocks = try XCTUnwrap(ChatContentBlockCodec.decode(encoded))
    let restored = try XCTUnwrap(restoredBlocks.first)
    guard case .questionCard(_, _, _, _, _, _, let selectedOptionID) = restored else {
      return XCTFail("question selection receipt should survive replay")
    }
    XCTAssertEqual(selectedOptionID, "focus-goal-1")
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

  func testTaskCaptureLinksFailClosedOutsideTheOmiDeviceArchive() {
    let omiCaptureTask = task(
      id: "omi-task",
      completed: false,
      conversationID: "omi-capture",
      source: "transcription:omi"
    )
    let desktopCaptureTask = task(
      id: "desktop-task",
      completed: false,
      conversationID: "desktop-conversation",
      source: "transcription:desktop"
    )
    let unknownCaptureTask = task(
      id: "unknown-task",
      completed: false,
      conversationID: "unknown-conversation"
    )

    XCTAssertEqual(ChatFirstCaptureLinkPolicy.captureID(for: omiCaptureTask), "omi-capture")
    XCTAssertNil(ChatFirstCaptureLinkPolicy.captureID(for: desktopCaptureTask))
    XCTAssertNil(ChatFirstCaptureLinkPolicy.captureID(for: unknownCaptureTask))
  }

  private func task(
    id: String,
    completed: Bool,
    conversationID: String? = nil,
    source: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "Draft the plan",
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0),
      conversationId: conversationID,
      source: source
    )
  }
}
