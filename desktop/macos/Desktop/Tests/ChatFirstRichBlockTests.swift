import XCTest

@testable import Omi_Computer

final class ChatFirstRichBlockTests: XCTestCase {
  private func conversation(
    id: String,
    source: ConversationSource = .desktop,
    status: ConversationStatus = .completed,
    discarded: Bool = false
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 1_000),
      updatedAt: Date(timeIntervalSince1970: 1_001),
      startedAt: Date(timeIntervalSince1970: 1_000),
      finishedAt: Date(timeIntervalSince1970: 1_060),
      structured: Structured(
        title: "Meeting notes",
        overview: "Overview",
        emoji: "",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: source,
      language: "en",
      status: status,
      discarded: discarded,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil,
      deferred: false
    )
  }

  func testConversationLinkCarriesExactFetchedRecordAndRejectsUnavailableResponses() {
    let fetched = conversation(id: "meeting-42")
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.validatedConversation(fetched, requestedID: "meeting-42"),
      fetched
    )
    XCTAssertNil(
      ChatFirstConversationLinkPolicy.validatedConversation(nil, requestedID: "meeting-42"),
      "A failed detail fetch must render the unavailable state rather than fall back to the list"
    )
    XCTAssertNil(
      ChatFirstConversationLinkPolicy.validatedConversation(
        conversation(id: "different-meeting"),
        requestedID: "meeting-42"
      ),
      "A mismatched detail response must render the unavailable state"
    )
  }

  /// The reported failure: an agent's conversation search returns desktop
  /// recordings, and a citation naming one used to route the capture focus,
  /// whose source-scoped archive fetch rejected it — landing the reader on the
  /// Conversations list with nothing opened.
  func testCitationRouteOpensNonCaptureConversationsAsExactRecords() {
    let desktop = conversation(id: "desktop-1", source: .desktop)
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: desktop,
        requestedID: "desktop-1",
        momentTimestampMs: nil),
      .exactRecord,
      "A desktop recording must open as the exact fetched record, not the capture focus"
    )

    let phone = conversation(id: "phone-1", source: .phone)
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: phone,
        requestedID: "phone-1",
        momentTimestampMs: nil),
      .exactRecord
    )

    let discardedCapture = conversation(id: "omi-d", source: .omi, discarded: true)
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: discardedCapture,
        requestedID: "omi-d",
        momentTimestampMs: nil),
      .exactRecord,
      "A discarded capture is outside the archive contract but still an openable record"
    )
  }

  func testCitationRouteKeepsCaptureFocusAndMomentForOmiCaptures() {
    let capture = conversation(id: "omi-1", source: .omi)
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: capture,
        requestedID: "omi-1",
        momentTimestampMs: 16_000),
      .captureFocus(momentTs: 16.0),
      "An Omi-device capture keeps the capture focus so its moment still plays"
    )
    XCTAssertEqual(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: capture,
        requestedID: "omi-1",
        momentTimestampMs: nil),
      .captureFocus(momentTs: nil)
    )
  }

  func testCitationRouteRefusesToNavigateWhenTheRecordCannotBeTrusted() {
    XCTAssertNil(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: nil,
        requestedID: "gone-1",
        momentTimestampMs: nil),
      "A failed fetch must not navigate anywhere instead of stranding the reader on a list"
    )
    XCTAssertNil(
      ChatFirstConversationLinkPolicy.citationRoute(
        forFetched: conversation(id: "other-1"),
        requestedID: "gone-1",
        momentTimestampMs: nil),
      "A mismatched fetch must not open a nearby row"
    )
  }

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
            ["type": "memoryLink", "memoryId": "memory-1", "summary": "Remember the launch constraint"],
            [
              "type": "conversationLink",
              "conversationId": "conversation-1",
              "summary": "Meeting notes",
              "recommendedActionItems": [
                ["description": "Send the deck", "taskId": "task-2"],
                ["description": "Book the follow-up"],
              ],
            ],
          ]
        ]
      )
    )

    XCTAssertEqual(converted.count, 4)
    XCTAssertEqual(converted[0]["task_id"] as? String, "task-1")
    XCTAssertEqual(converted[1]["goal_id"] as? String, "goal-1")
    XCTAssertEqual(converted[2]["memory_id"] as? String, "memory-1")
    let actionItems = try XCTUnwrap(converted[3]["recommended_action_items"] as? [[String: Any]])
    XCTAssertEqual(actionItems.map { $0["description"] as? String }, ["Send the deck", "Book the follow-up"])
    XCTAssertEqual(actionItems.first?["task_id"] as? String, "task-2")
  }

  func testCodecRoundTripsEveryChatFirstBlock() throws {
    let blocks: [ChatContentBlock] = [
      .questionCard(
        id: "question-card",
        questionId: "question-1",
        text: "Which goal should we focus on?",
        subjectKind: "goal",
        subjectId: "goal-1",
        options: [
          [
            "optionId": "focus-goal-1",
            "label": "Keep this goal",
            "preparedAnswer": "Keep goal 1 as my focus",
            "defer": false,
          ]
        ]
      ),
      .taskCard(id: "task-card", taskId: "task-1"),
      .goalLink(id: "goal-link", goalId: "goal-1", summary: "Finish the launch plan"),
      .captureLink(
        id: "capture-link",
        conversationId: "capture-1",
        momentTimestampMs: 42_000,
        summary: "Planning conversation"
      ),
      .conversationLink(
        id: "conversation-link",
        conversationId: "conversation-1",
        summary: "Meeting notes",
        recommendedActionItems: [
          ConversationLinkActionItem(description: "Send the deck", taskID: "task-2"),
          ConversationLinkActionItem(description: "Book the follow-up", taskID: nil),
        ]
      ),
      .memoryLink(id: "memory-link", memoryId: "memory-1", summary: "Launch constraint"),
    ]

    let encoded = try XCTUnwrap(ChatContentBlockCodec.encode(blocks))
    let restored = try XCTUnwrap(ChatContentBlockCodec.decode(encoded))
    XCTAssertEqual(restored.count, blocks.count)

    guard
      case .questionCard(
        _, let questionID, let text, let subjectKind, let subjectID, let options, let selectedOptionID) = restored[0]
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

    guard
      case .conversationLink(
        _, let conversationID, let conversationSummary, let recommendedActionItems) = restored[4]
    else {
      return XCTFail("conversation link should survive persisted replay")
    }
    XCTAssertEqual(conversationID, "conversation-1")
    XCTAssertEqual(conversationSummary, "Meeting notes")
    XCTAssertEqual(
      recommendedActionItems,
      [
        ConversationLinkActionItem(description: "Send the deck", taskID: "task-2"),
        ConversationLinkActionItem(description: "Book the follow-up", taskID: nil),
      ])

    guard case .memoryLink(_, let memoryID, let memorySummary) = restored[5] else {
      return XCTFail("memory link should survive persisted replay")
    }
    XCTAssertEqual(memoryID, "memory-1")
    XCTAssertEqual(memorySummary, "Launch constraint")
  }

  func testLegacyConversationLinkWithoutRecommendedItemsDegradesToTheExistingCard() {
    let restored = ChatContentBlockCodec.decode([
      [
        "type": "conversationLink",
        "id": "conversation-link",
        "conversationId": "conversation-1",
        "summary": "Meeting notes",
      ]
    ])

    guard let first = restored.first,
      case .conversationLink(_, _, _, let recommendedActionItems) = first
    else {
      return XCTFail("legacy conversation link should still decode")
    }
    XCTAssertTrue(recommendedActionItems.isEmpty)
  }

  func testQuestionSelectionReceiptRoundTripsAndRetiresTheOptions() throws {
    let selected = ChatContentBlock.questionCard(
      id: "question-card",
      questionId: "question-1",
      text: "Which goal should we focus on?",
      subjectKind: "goal",
      subjectId: "goal-1",
      options: [
        [
          "optionId": "focus-goal-1",
          "label": "Keep this goal",
          "preparedAnswer": "Keep goal 1 as my focus",
        ]
      ],
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

  /// Every Chat surface renders every rich block. This used to assert the
  /// opposite — that a caller without an explicit context got nothing — which is
  /// how a turn whose only content was a task card read as an empty assistant
  /// reply in the task panel and in the notch.
  func testEveryRichBlockSurvivesGroupingOnEveryChatSurface() {
    let blocks: [ChatContentBlock] = [
      .questionCard(
        id: "question", questionId: "question-1", text: "Question", subjectKind: "goal", subjectId: "goal-1",
        options: []
      ),
      .taskCard(id: "task", taskId: "task-1"),
      .goalLink(id: "goal", goalId: "goal-1", summary: "Goal"),
      .captureLink(id: "capture", conversationId: "capture-1", momentTimestampMs: nil, summary: "Capture"),
      .conversationLink(
        id: "conversation", conversationId: "conversation-1", summary: "Conversation",
        recommendedActionItems: []),
      .memoryLink(id: "memory", memoryId: "memory-1", summary: "Memory"),
    ]

    let groups = ContentBlockGroup.visibleChatGroups(blocks, isStreaming: false)
    XCTAssertEqual(groups.count, 6)
    XCTAssertEqual(groups.map(\.id), blocks.map(\.id), "order is the transcript's, not the renderer's")
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

  func testTaskCardRetainsCompletedPresentationWhileCanonicalTaskRehydrates() {
    let completed = task(id: "task-1", completed: true)

    XCTAssertEqual(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: nil,
        retainedCompletedTask: completed
      ),
      completed
    )
    XCTAssertNil(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: nil,
        retainedCompletedTask: task(id: "task-1", completed: false)
      )
    )
    XCTAssertNil(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: task(id: "task-1", completed: true, taskStatus: "superseded"),
        retainedCompletedTask: completed
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
    source: String? = nil,
    taskStatus: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "Draft the plan",
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0),
      conversationId: conversationID,
      source: source,
      taskStatus: taskStatus
    )
  }
}
