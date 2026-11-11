import XCTest

@testable import Omi_Computer

/// One shell renders one transcript, and every content-block kind in it is a
/// control the reader can act on — on every surface, capability or not.
///
/// The regression these tests exist for was silent by construction: six block
/// kinds were skipped during grouping unless the host passed an optional
/// capability context, so a turn whose only content was a task card rendered as
/// an *empty assistant reply* in the task panel and in the notch, and as a
/// tickable card in the main window. Nothing logged, nothing threw.
@MainActor
final class OneChatShellRichBlockTests: XCTestCase {
  private func defaults() throws -> UserDefaults {
    let suiteName = "OneChatShellRichBlockTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return defaults
  }

  /// A single assistant turn carrying prose plus all six interactable kinds.
  private var everyRichBlockMessage: ChatMessage {
    var message = ChatMessage(id: "assistant-1", text: "", sender: .ai)
    message.contentBlocks = [
      .text(id: "text", text: "Here is what I found."),
      .questionCard(
        id: "question", questionId: "question-1", text: "Which one?",
        subjectKind: "goal", subjectId: "goal-1",
        options: [["optionId": "a", "label": "The first"], ["optionId": "b", "label": "The second"]]
      ),
      .taskCard(id: "task", taskId: "task-1"),
      .goalLink(id: "goal", goalId: "goal-1", summary: "Ship the shell"),
      .captureLink(
        id: "capture", conversationId: "capture-1", momentTimestampMs: 4_000, summary: "Standup"),
      .conversationLink(
        id: "conversation", conversationId: "conversation-1", summary: "Design review",
        recommendedActionItems: []),
      .memoryLink(id: "memory", memoryId: "memory-1", summary: "Prefers mornings"),
    ]
    return message
  }

  func testOneTurnYieldsEveryTypedGroupInTranscriptOrder() {
    let groups = ContentBlockGroup.visibleChatGroups(
      everyRichBlockMessage.contentBlocks, isStreaming: false)

    XCTAssertEqual(
      groups.map(\.id),
      ["text", "question", "task", "goal", "capture", "conversation", "memory"],
      "grouping must preserve the transcript's order and drop nothing")

    var kinds: [String] = []
    for group in groups {
      switch group {
      case .text: kinds.append("text")
      case .questionCard: kinds.append("questionCard")
      case .taskCard: kinds.append("taskCard")
      case .goalLink: kinds.append("goalLink")
      case .captureLink: kinds.append("captureLink")
      case .conversationLink: kinds.append("conversationLink")
      case .memoryLink: kinds.append("memoryLink")
      default: kinds.append("unexpected")
      }
    }
    XCTAssertEqual(
      kinds,
      ["text", "questionCard", "taskCard", "goalLink", "captureLink", "conversationLink", "memoryLink"])
  }

  /// The same turn, grouped through the projection the notch and task panel use.
  /// They call the identical entry point, so "the notch renders fewer kinds" is
  /// no longer expressible.
  func testStreamingAndSettledProjectionsBothKeepEveryRichBlock() {
    let blocks = everyRichBlockMessage.contentBlocks
    XCTAssertEqual(ContentBlockGroup.visibleChatGroups(blocks, isStreaming: true).count, 7)
    XCTAssertEqual(ContentBlockGroup.visibleChatGroups(blocks, isStreaming: false).count, 7)
  }

  /// Each link block's tap lands on the typed focus its card promises, through
  /// the context every host now carries. Recording is the navigation owner's own
  /// published state, not a stubbed closure.
  func testEveryLinkBlockActionReachesItsTypedNavigationTarget() throws {
    let navigation = ChatFirstShellNavigation(defaults: try defaults())

    navigation.open(focus: .task(id: "task-1"))
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertEqual(navigation.pendingFocus, .task(id: "task-1"))

    navigation.open(focus: .goal(id: "goal-1"))
    XCTAssertEqual(navigation.route, .goals)
    XCTAssertEqual(navigation.pendingFocus, .goal(id: "goal-1"))

    navigation.open(focus: .capture(id: "capture-1", momentTs: 4))
    XCTAssertEqual(navigation.route, .memories)
    XCTAssertEqual(navigation.pendingFocus, .capture(id: "capture-1", momentTs: 4))

    navigation.open(focus: .memory(id: "memory-1"))
    XCTAssertEqual(navigation.route, .memories)
    XCTAssertEqual(navigation.pendingFocus, .memory(id: "memory-1"))

    // The conversation link carries the exact fetched record rather than an id,
    // and lands on the hub-owned Conversations destination.
    let record = ChatFirstRichBlockTestConversation.make(id: "conversation-1")
    navigation.open(conversation: record)
    XCTAssertEqual(navigation.route, .memories)
    XCTAssertEqual(navigation.pendingConversation?.id, "conversation-1")
    XCTAssertNil(navigation.pendingFocus)
  }

  /// A goal link resolves asynchronously; a newer link must win. This is the one
  /// action with a fence, so it is asserted through the fence's own API.
  func testGoalLinkResolutionFenceKeepsTheNewestRequest() throws {
    let navigation = ChatFirstShellNavigation(defaults: try defaults())
    let stale = navigation.beginGoalLinkResolution()
    let fresh = navigation.beginGoalLinkResolution()

    XCTAssertFalse(navigation.completeGoalLinkResolution(goalID: "goal-stale", generation: stale))
    XCTAssertNil(navigation.pendingFocus)
    XCTAssertTrue(navigation.completeGoalLinkResolution(goalID: "goal-fresh", generation: fresh))
    XCTAssertEqual(navigation.pendingFocus, .goal(id: "goal-fresh"))
  }

  // MARK: - Capability-off

  /// Capability-off must degrade, not disappear. The question card is the only
  /// block whose *action* needs the server projection, so it is the only one that
  /// changes — and it changes to "visible but unpressable", never to "hidden".
  func testCapabilityOffDisablesQuestionOptionsWithoutHidingThem() {
    let off = ChatFirstQuestionCardOptionsPolicy.presentation(
      isActionable: false, isCapabilityAvailable: false, hasSelection: false, hasOptions: true)
    XCTAssertEqual(off, .disabled)
    XCTAssertTrue(off.isVisible, "a question with no visible answers explains nothing")
    XCTAssertFalse(off.isPressable)

    let on = ChatFirstQuestionCardOptionsPolicy.presentation(
      isActionable: true, isCapabilityAvailable: true, hasSelection: false, hasOptions: true)
    XCTAssertEqual(on, .enabled)
    XCTAssertTrue(on.isPressable)
  }

  /// The two ways a live capability retires a question keep hiding its options:
  /// it has been answered, or its turn is no longer the transcript's tail.
  func testAnsweredOrRetiredQuestionStillHidesItsOptions() {
    XCTAssertEqual(
      ChatFirstQuestionCardOptionsPolicy.presentation(
        isActionable: false, isCapabilityAvailable: true, hasSelection: true, hasOptions: true),
      .hidden)
    XCTAssertEqual(
      ChatFirstQuestionCardOptionsPolicy.presentation(
        isActionable: false, isCapabilityAvailable: true, hasSelection: false, hasOptions: true),
      .hidden,
      "a question that has lost the tail is history, not an offer")
    XCTAssertEqual(
      ChatFirstQuestionCardOptionsPolicy.presentation(
        isActionable: true, isCapabilityAvailable: false, hasSelection: false, hasOptions: false),
      .hidden)
  }

  /// The task card is bound to `TasksStore`, so checking one off never consulted
  /// the projection and must keep working with it absent.
  func testTaskCardStaysActionableWithNoCapabilityProjection() {
    var gate = ChatFirstMainChatProjectionGate()
    XCTAssertTrue(gate.configure(sample: nil, ownerID: "owner-a"))
    XCTAssertNil(gate.capability(for: .mainChat(chatId: nil), ownerID: "owner-a"))

    // Nothing in the task card's own presentation consults the gate: its display
    // is derived from the store's record alone.
    let task = TaskActionItem(
      id: "task-1", description: "Ship it", completed: false, createdAt: Date(),
      dueAt: nil, completedAt: nil, deleted: false)
    XCTAssertEqual(
      ChatFirstTaskCardPresentation.displayTask(liveTask: task, retainedCompletedTask: nil)?.id,
      "task-1")
    XCTAssertTrue(
      ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
        intendedCompletion: true,
        reconciledTask: TaskActionItem(
          id: "task-1", description: "Ship it", completed: true, createdAt: Date(),
          dueAt: nil, completedAt: Date(), deleted: false)))
  }
}

/// A minimal server record for the conversation-link assertions above.
enum ChatFirstRichBlockTestConversation {
  static func make(id: String) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 1_000),
      updatedAt: Date(timeIntervalSince1970: 1_001),
      startedAt: Date(timeIntervalSince1970: 1_000),
      finishedAt: Date(timeIntervalSince1970: 1_060),
      structured: Structured(
        title: "Design review",
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
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil,
      deferred: false
    )
  }
}
