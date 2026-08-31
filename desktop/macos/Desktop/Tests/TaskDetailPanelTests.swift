import XCTest

@testable import Omi_Computer

final class TaskDetailPanelTests: XCTestCase {
  func testOpeningAndClosingTaskDetailPanelTracksOnlyTheRequestedTask() {
    var state = TaskDetailPanelState()
    XCTAssertFalse(state.isPresented)

    state.open(taskID: "task-42")
    XCTAssertTrue(state.isPresented)
    XCTAssertEqual(state.selectedTaskID, "task-42")

    state.open(taskID: "task-99")
    XCTAssertEqual(state.selectedTaskID, "task-99")

    state.close()
    XCTAssertFalse(state.isPresented)
    XCTAssertNil(state.selectedTaskID)
  }

  func testPanelContentIncludesCurrentTaskWhyAndNavigableSource() throws {
    let task = makeTask(
      id: "task-42",
      description: "Send the revised budget",
      completed: false,
      category: "finance",
      source: "transcription:omi",
      conversationID: "capture-42",
      provenance: [
        OmiAPI.EvidenceRef(
          id: "capture-42",
          kind: .conversation,
          scope: .canonical,
          version: "conversation.v1"
        )
      ]
    )

    let content = TaskDetailPanelContent.make(for: task)
    XCTAssertEqual(content.taskID, "task-42")
    XCTAssertEqual(content.description, "Send the revised budget")
    XCTAssertEqual(content.status, "Active")
    XCTAssertEqual(content.whyOmiAddedThis, "It came from a conversation you captured.")
    XCTAssertTrue(content.fields.contains(.init(label: "Category", value: "Finance")))
    XCTAssertTrue(content.fields.contains(.init(label: "Status", value: "Active")))

    let source = try XCTUnwrap(content.linkedSources.first)
    XCTAssertEqual(source.title, "Omi capture")
    XCTAssertEqual(source.route, .capture(id: "capture-42"))
  }

  func testLinkedSourcePolicyUsesRealRouteKindsAndDropsUnroutableEvidence() {
    let task = makeTask(
      id: "task-1",
      description: "Review context",
      source: "screenshot",
      provenance: [
        OmiAPI.EvidenceRef(id: "memory-1", kind: .memory_item, scope: .canonical),
        OmiAPI.EvidenceRef(id: "screen-1", kind: .local_screen, scope: .device_local),
        OmiAPI.EvidenceRef(id: "artifact-1", kind: .artifact, scope: .canonical),
      ]
    )

    let links = TaskDetailSourceLinkPolicy.links(for: task)
    XCTAssertEqual(links.count, 2)
    XCTAssertTrue(links.contains { $0.route == .memory(id: "memory-1") })
    // A screen ref the frame contract cannot resolve still routes to the
    // Rewind page. Only refs with no valid destination at all are dropped.
    XCTAssertTrue(links.contains { $0.route == .rewind })
    XCTAssertFalse(links.contains { $0.id.contains("artifact-1") })
  }

  @MainActor
  func testRewindFrameNavigationRequiresTheValidatedPresentationLease() {
    let focusRequests = NotificationCountRecorder()
    let rewindNavigations = NotificationCountRecorder()
    RewindCitationFocusState.shared.request(777)
    let focusToken = NotificationCenter.default.addObserver(
      forName: .rewindCitationFocusRequested,
      object: nil,
      queue: .main
    ) { _ in focusRequests.record() }
    let navigationToken = NotificationCenter.default.addObserver(
      forName: .navigateToRewind,
      object: nil,
      queue: .main
    ) { _ in rewindNavigations.record() }
    defer {
      NotificationCenter.default.removeObserver(focusToken)
      NotificationCenter.default.removeObserver(navigationToken)
      _ = RewindCitationFocusState.shared.consume()
    }

    TaskDetailSourceNavigator.open(.rewindFrame(id: 42))

    XCTAssertEqual(focusRequests.count, 0)
    XCTAssertEqual(rewindNavigations.count, 0)
    XCTAssertEqual(RewindCitationFocusState.shared.pendingScreenshotID, 777)
  }

  @MainActor
  func testRewindFrameNavigationRejectsLeaseAfterCompletedOwnerTransition() throws {
    let owner = try XCTUnwrap(RewindCaptureOwnerSnapshot.capture())
    RewindCaptureOwnerGeneration.beginTransition()
    RewindCaptureOwnerGeneration.endTransition()
    let focusRequests = NotificationCountRecorder()
    let rewindNavigations = NotificationCountRecorder()
    let focusToken = NotificationCenter.default.addObserver(
      forName: .rewindCitationFocusRequested,
      object: nil,
      queue: .main
    ) { _ in focusRequests.record() }
    let navigationToken = NotificationCenter.default.addObserver(
      forName: .navigateToRewind,
      object: nil,
      queue: .main
    ) { _ in rewindNavigations.record() }
    defer {
      NotificationCenter.default.removeObserver(focusToken)
      NotificationCenter.default.removeObserver(navigationToken)
    }

    TaskDetailSourceNavigator.open(
      .rewindFrame(id: 42),
      rewindLease: RewindEvidenceCardLease(screenshotID: 42, owner: owner)
    )

    XCTAssertEqual(focusRequests.count, 0)
    XCTAssertEqual(rewindNavigations.count, 0)
  }

  @MainActor
  func testRewindFrameNavigationPostsOneFocusAndOneDestinationNotification() throws {
    let owner = try XCTUnwrap(RewindCaptureOwnerSnapshot.capture())
    let focusRequests = NotificationCountRecorder()
    let rewindNavigations = NotificationCountRecorder()
    let focusToken = NotificationCenter.default.addObserver(
      forName: .rewindCitationFocusRequested,
      object: nil,
      queue: .main
    ) { _ in focusRequests.record() }
    let navigationToken = NotificationCenter.default.addObserver(
      forName: .navigateToRewind,
      object: nil,
      queue: .main
    ) { _ in rewindNavigations.record() }
    defer {
      NotificationCenter.default.removeObserver(focusToken)
      NotificationCenter.default.removeObserver(navigationToken)
      _ = RewindCitationFocusState.shared.consume()
    }

    TaskDetailSourceNavigator.open(
      .rewindFrame(id: 42),
      rewindLease: RewindEvidenceCardLease(screenshotID: 42, owner: owner)
    )

    XCTAssertEqual(focusRequests.count, 1)
    XCTAssertEqual(rewindNavigations.count, 1)
  }

  func testPanelDetailsRetainUnmodeledTaskMetadata() {
    let task = makeTask(
      id: "task-metadata",
      description: "Investigate the report",
      metadata: "{\"creation_reason\":\"User feedback\",\"relevant_files\":[\"Report.swift\"]}"
    )

    let fields = TaskDetailPanelContent.make(for: task).fields
    XCTAssertTrue(fields.contains(.init(label: "Creation Reason", value: "User feedback")))
    XCTAssertTrue(fields.contains(.init(label: "Relevant Files", value: "Report.swift")))
  }

  func testPanelDetailsExcludeNarrativeContextMetadata() {
    let task = makeTask(
      id: "task-context",
      description: "Review the budget",
      metadata: """
        {
          "context_summary": "Spreadsheet open with Q4 numbers",
          "current_activity": "Editing cells in Excel",
          "reasoning": "User mentioned sending the budget",
          "agent_plan": "Draft email with attached figures",
          "creation_reason": "Screen capture"
        }
        """
    )

    let fields = TaskDetailPanelContent.make(for: task).fields
    XCTAssertTrue(fields.contains(.init(label: "Creation Reason", value: "Screen capture")))
    XCTAssertFalse(fields.contains { $0.label == "Context Summary" })
    XCTAssertFalse(fields.contains { $0.label == "Current Activity" })
    XCTAssertFalse(fields.contains { $0.label == "Reasoning" })
    XCTAssertFalse(fields.contains { $0.label == "Agent Plan" })
  }

  func testTaskDetailActionPolicyPreservesCompletionAndCRUDActions() {
    let active = makeTask(id: "active", description: "Do it", completed: false)
    let completed = makeTask(id: "done", description: "Did it", completed: true)

    let activeActions = TaskDetailPanelActionPolicy.availableActions(for: active, indentLevel: 1, hasChat: true)
    XCTAssertTrue(activeActions.contains(.toggleCompletion))
    XCTAssertTrue(activeActions.contains(.edit))
    XCTAssertTrue(activeActions.contains(.openThread))
    XCTAssertTrue(activeActions.contains(.decreaseIndent))
    XCTAssertTrue(activeActions.contains(.increaseIndent))
    XCTAssertTrue(activeActions.contains(.copyLink))
    XCTAssertTrue(activeActions.contains(.delete))

    let completedActions = TaskDetailPanelActionPolicy.availableActions(for: completed, indentLevel: 3, hasChat: false)
    XCTAssertFalse(completedActions.contains(.openThread))
    XCTAssertFalse(completedActions.contains(.increaseIndent))
    XCTAssertTrue(completedActions.contains(.toggleCompletion))
    XCTAssertTrue(completedActions.contains(.delete))
  }

  func testHoverActionsAreSuppressedForEveryRowWhileDetailPanelIsPresented() {
    XCTAssertFalse(
      TaskDetailPanelPresentationPolicy.showsHoverActions(
        isRowHovering: true,
        isMultiSelectMode: false,
        isDeletedTask: false,
        isTextFieldFocused: false,
        isDetailPanelPresented: true
      )
    )
    XCTAssertTrue(
      TaskDetailPanelPresentationPolicy.showsHoverActions(
        isRowHovering: true,
        isMultiSelectMode: false,
        isDeletedTask: false,
        isTextFieldFocused: false,
        isDetailPanelPresented: false
      )
    )
    XCTAssertTrue(
      TaskDetailPanelPresentationPolicy.showsHoverActions(
        isRowHovering: false,
        isKeyboardSelected: true,
        isMultiSelectMode: false,
        isDeletedTask: false,
        isTextFieldFocused: false,
        isDetailPanelPresented: false
      ),
      "keyboard-selected rows need the same accessible action menu as hovered rows"
    )
    XCTAssertFalse(
      TaskDetailPanelPresentationPolicy.showsHoverActions(
        isRowHovering: true,
        isMultiSelectMode: true,
        isDeletedTask: false,
        isTextFieldFocused: false,
        isDetailPanelPresented: false
      )
    )
  }

  /// Priority moved off the task row's hover strip into the detail panel, where
  /// it is an editable control rather than a duplicated read-only field.
  func testPriorityIsNotDuplicatedAsAReadOnlyDetailField() {
    let task = TaskActionItem(
      id: "task-priority",
      description: "Ship the build",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 1_700_000_000),
      priority: "high"
    )

    let fields = TaskDetailPanelContent.make(for: task).fields

    XCTAssertFalse(
      fields.contains { $0.label == "Priority" },
      "the panel edits priority directly, so it must not also list it as a read-only field")
  }

  private func makeTask(
    id: String,
    description: String,
    completed: Bool = false,
    category: String? = nil,
    source: String? = nil,
    conversationID: String? = nil,
    provenance: [OmiAPI.EvidenceRef]? = nil,
    metadata: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: description,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 1_700_000_000),
      completedAt: completed ? Date(timeIntervalSince1970: 1_700_000_100) : nil,
      conversationId: conversationID,
      source: source,
      metadata: metadata,
      category: category,
      provenance: provenance
    )
  }
}

private final class NotificationCountRecorder: @unchecked Sendable {
  private(set) var count = 0

  func record() {
    count += 1
  }
}
