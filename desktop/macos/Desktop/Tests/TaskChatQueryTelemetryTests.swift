import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Task chat must join `question_asked` to the terminal chat-query outcome by
/// the same client telemetry attempt ID, matching main chat's #12846 seam.
@MainActor
final class TaskChatQueryTelemetryTests: XCTestCase {
  private var captured: [(String, [String: Any])] = []
  private var previousOwnerID: String?

  override func setUp() async throws {
    captured = []
    AnalyticsManager.shared.questionTelemetryCaptureForTests = { [weak self] name, props in
      self?.captured.append((name, props))
    }
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionOwner(to: "owner-a")
  }

  override func tearDown() async throws {
    AnalyticsManager.shared.questionTelemetryCaptureForTests = nil
    await transitionOwner(to: previousOwnerID)
  }

  func testAcceptedTaskChatSendJoinsTerminalAnswerByTheSameClientAttemptID() async throws {
    let workstreamID = "workstream-taskchat-telemetry-\(UUID().uuidString)"
    let kernelRunID = "kernel-run-1"
    let kernelAttemptID = "kernel-attempt-1"
    var acceptedAttemptID: String?
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, writes in
        try self.exchangeReceipt(writes: writes, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        AgentBridge.QueryResult(
          text: "done",
          costUsd: 0.01,
          omiSessionId: "omi-session",
          runId: kernelRunID,
          attemptId: kernelAttemptID,
          adapterSessionId: nil,
          terminalStatus: "succeeded",
          inputTokens: 1,
          outputTokens: 2,
          cacheReadTokens: 0,
          cacheWriteTokens: 0
        )
      },
      terminalizeJournalMessageOperation: { _, _, _, message, producingRunId, producingAttemptId in
        try self.journalTurn(
          message: message,
          workstreamID: workstreamID,
          seq: 2,
          status: .completed,
          producingRunId: producingRunId,
          producingAttemptId: producingAttemptId
        )
      }
    )

    await state.sendMessage(
      "Keep working on this",
      onAcceptedWithAttemptID: { attemptID in
        acceptedAttemptID = attemptID
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 20, source: "task_chat", attemptID: attemptID)
      }
    )

    let asked = captured.filter { $0.0 == "question_asked" }
    let answered = captured.filter { $0.0 == "question_answered" }
    let clientAttemptID = try XCTUnwrap(acceptedAttemptID)
    XCTAssertFalse(clientAttemptID.isEmpty)
    XCTAssertNotEqual(clientAttemptID, kernelAttemptID)
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(answered.count, 1)
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(answered.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(asked.first?.1["source"] as? String, "task_chat")
    XCTAssertEqual(answered.first?.1["outcome"] as? String, "grounded")
    XCTAssertEqual(answered.first?.1["surface"] as? String, "chat_window")
    XCTAssertFalse(state.isSending)
    XCTAssertNil(state.errorMessage)
  }

  func testFailedJournalAdmissionDoesNotCountAsAsked() async {
    var acceptedAttemptID: String?
    var journalUpdateStatuses: [KernelJournalTurnStatus?] = []
    let state = makeState(
      workstreamID: "workstream-taskchat-journal-fail-\(UUID().uuidString)",
      recordJournalExchangeOperation: { _, _, _, _ in
        throw BridgeError.agentError("second exchange turn identity collision")
      },
      queryOperation: { _, _, _, _ in
        XCTFail("query must not run when journal admission fails")
        throw BridgeError.agentError("query must not run")
      },
      onJournalUpdate: { status in
        journalUpdateStatuses.append(status)
      }
    )

    await state.sendMessage(
      "Keep both halves atomic",
      onAccepted: {
        XCTFail("journal admission failure must not count as accepted")
      },
      onAcceptedWithAttemptID: { attemptID in
        acceptedAttemptID = attemptID
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 24, source: "task_chat", attemptID: attemptID)
      }
    )

    XCTAssertNil(acceptedAttemptID)
    XCTAssertTrue(captured.filter { $0.0 == "question_asked" }.isEmpty)
    XCTAssertTrue(captured.filter { $0.0 == "question_answered" }.isEmpty)
    XCTAssertTrue(journalUpdateStatuses.isEmpty)
    XCTAssertTrue(state.messages.isEmpty)
    XCTAssertFalse(state.isSending)
    XCTAssertEqual(state.errorMessage, "Could not save this message. Try again.")
  }

  func testQueryFailureAfterAdmissionJoinsAskedAndAnsweredByTheSameAttemptID() async throws {
    let workstreamID = "workstream-taskchat-query-fail-\(UUID().uuidString)"
    var acceptedAttemptID: String?
    var journalUpdateStatuses: [KernelJournalTurnStatus?] = []
    var terminalized = false
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, writes in
        try self.exchangeReceipt(writes: writes, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        throw BridgeError.timeout
      },
      onJournalUpdate: { status in
        journalUpdateStatuses.append(status)
      },
      onTerminalize: {
        terminalized = true
      }
    )

    await state.sendMessage(
      "Continue this work",
      onAcceptedWithAttemptID: { attemptID in
        acceptedAttemptID = attemptID
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 18, source: "task_chat", attemptID: attemptID)
      }
    )

    let asked = captured.filter { $0.0 == "question_asked" }
    let answered = captured.filter { $0.0 == "question_answered" }
    let clientAttemptID = try XCTUnwrap(acceptedAttemptID)
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(answered.count, 1)
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(answered.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(answered.first?.1["outcome"] as? String, "error")
    XCTAssertEqual(journalUpdateStatuses.last ?? nil, .failed)
    XCTAssertFalse(terminalized, "unbound query failure must not exact-terminalize the producing turn")
    XCTAssertFalse(state.isSending)
  }

  func testUserStopAfterAdmissionJoinsAskedAndCancelledByTheSameAttemptID() async throws {
    let workstreamID = "workstream-taskchat-cancel-\(UUID().uuidString)"
    var acceptedAttemptID: String?
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, writes in
        try self.exchangeReceipt(writes: writes, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        throw BridgeError.stopped
      }
    )

    await state.sendMessage(
      "Stop after admission",
      onAcceptedWithAttemptID: { attemptID in
        acceptedAttemptID = attemptID
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 20, source: "task_chat", attemptID: attemptID)
      }
    )

    let asked = captured.filter { $0.0 == "question_asked" }
    let answered = captured.filter { $0.0 == "question_answered" }
    let clientAttemptID = try XCTUnwrap(acceptedAttemptID)
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(answered.count, 1)
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(answered.first?.1["attempt_id"] as? String, clientAttemptID)
    XCTAssertEqual(answered.first?.1["outcome"] as? String, "cancelled")
    XCTAssertFalse(state.isSending)
    XCTAssertNil(state.errorMessage)
  }

  func testClaudeBillingFailureExplainsTheProviderAndRequiresExplicitRecovery() async throws {
    let workstreamID = "task-credit-report"
    var queryCount = 0
    var migrationCount = 0
    let failure = AgentRuntimeFailure(
      code: "adapter_execution_failed",
      failureCode: .quotaExceeded,
      userMessage: "Internal error: Credit balance is too low",
      adapterId: "acp",
      retryable: false
    )
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, writes in
        try self.exchangeReceipt(writes: writes, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        queryCount += 1
        return AgentBridge.QueryResult(
          text: "", costUsd: 0, omiSessionId: "session-1", runId: "run-1", attemptId: "attempt-1",
          adapterSessionId: nil, terminalStatus: "failed", failure: failure,
          inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0
        )
      },
      useOmiAIOperation: { requestedWorkstream, workspace, authorization in
        XCTAssertEqual(requestedWorkstream, workstreamID)
        XCTAssertEqual(workspace, "/tmp")
        XCTAssertTrue(RuntimeOwnerIdentity.isAuthorizationCurrent(authorization))
        migrationCount += 1
      }
    )
    await state.sendMessage("Can you help me find a topic for this?")
    XCTAssertTrue(state.errorMessage?.contains("This thread uses Claude") == true)
    XCTAssertFalse(state.errorMessage?.contains("Internal error") == true)
    XCTAssertTrue(state.messages.last?.text.contains("This thread uses Claude") == true)
    XCTAssertTrue(state.canUseOmiAI)
    XCTAssertEqual(migrationCount, 0, "billing failure must not switch a provider automatically")
    let messageIDs = state.messages.map(\.id)
    try captureErrorPanelIfRequested(state)

    state.isSending = true
    await state.useOmiAI()
    XCTAssertEqual(migrationCount, 0, "an active turn cannot change its provider")
    state.isSending = false
    await state.useOmiAI()
    XCTAssertEqual(migrationCount, 1)
    XCTAssertEqual(queryCount, 1, "provider recovery must not resend the request")
    XCTAssertEqual(state.messages.map(\.id), messageIDs, "provider recovery must retain the thread")
    XCTAssertNil(state.errorMessage)
    XCTAssertFalse(state.canUseOmiAI)
    XCTAssertFalse(state.isSwitchingProvider)
  }

  func testReopenedClaudeFailureRestoresRecoveryWithoutSendingOrRewritingHistory() async throws {
    let workstreamID = "reopened-claude-credit-thread"
    let session = try recoverySession(adapterID: "acp", generation: 1)
    let recovery = try XCTUnwrap(
      TaskChatState.providerRecovery(
        from: recoveryListing(workstreamID: workstreamID),
        session: session,
        workstreamID: workstreamID,
        ownerID: "owner-a"
      ))
    let user = ChatMessage(
      id: "saved-user", text: "Find a topic", createdAt: Date(timeIntervalSince1970: 1), sender: .user)
    let assistant = ChatMessage(
      id: "saved-assistant", text: "Failed: Internal error: Credit balance is too low",
      createdAt: Date(timeIntervalSince1970: 2), sender: .ai)
    let savedTurns = [
      try journalTurn(message: user, workstreamID: workstreamID, seq: 1, status: .completed),
      try journalTurn(
        message: assistant, workstreamID: workstreamID, seq: 2, status: .failed,
        producingRunId: "saved-run", producingAttemptId: "saved-attempt"),
    ]
    var writes = 0
    var queries = 0
    var migrations = 0
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, turns in
        writes += 1
        return try self.exchangeReceipt(writes: turns, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        queries += 1
        throw BridgeError.agentError("Reopening must not submit a query")
      },
      onJournalUpdate: { _ in writes += 1 },
      onTerminalize: { writes += 1 },
      useOmiAIOperation: { _, _, snapshot in
        XCTAssertTrue(RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot))
        migrations += 1
      },
      loadProviderRecoveryOperation: { requestedWorkstream, _, snapshot in
        XCTAssertEqual(requestedWorkstream, workstreamID)
        XCTAssertEqual(snapshot.ownerID, "owner-a")
        XCTAssertTrue(RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot))
        return recovery
      },
      listJournalTurnsOperation: { _, _, _, _, _ in
        AgentRuntimeProcess.JournalOperationResult(
          operation: "list", conversationId: session.conversationId, turn: nil, turns: savedTurns,
          clearedCount: 0, highWaterTurnSeq: 2, conversationGeneration: 1, generationBaseTurnSeq: 0)
      }
    )

    await state.loadPersistedMessages()

    XCTAssertTrue(state.canUseOmiAI)
    XCTAssertTrue(state.errorMessage?.contains("This thread uses Claude") == true)
    XCTAssertEqual(state.messages.map(\.id), [user.id, assistant.id])
    XCTAssertEqual(
      state.messages.last?.text, assistant.text, "recovery hydration must not rewrite historical failure text")
    XCTAssertEqual(writes, 0)
    XCTAssertEqual(queries, 0)
    XCTAssertEqual(migrations, 0)

    await state.useOmiAI()

    XCTAssertEqual(migrations, 1)
    XCTAssertEqual(writes, 0)
    XCTAssertEqual(queries, 0)
    XCTAssertEqual(state.messages.map(\.id), [user.id, assistant.id])
    XCTAssertNil(state.errorMessage)
    XCTAssertFalse(state.canUseOmiAI)
  }

  func testHistoricalRecoveryRequiresExactOwnerSessionAndCurrentProfileGeneration() throws {
    let workstreamID = "recovery-correlation"
    let current = try recoverySession(adapterID: "acp", generation: 1)
    XCTAssertNotNil(
      TaskChatState.providerRecovery(
        from: try recoveryListing(workstreamID: workstreamID), session: current,
        workstreamID: workstreamID, ownerID: "owner-a"))

    let rejectedListings = [
      try recoveryListing(workstreamID: workstreamID, ownerID: "owner-b"),
      try recoveryListing(workstreamID: workstreamID, sessionID: "another-session"),
      try recoveryListing(workstreamID: "another-workstream"),
      try recoveryListing(workstreamID: workstreamID, sessionGeneration: 2),
      try recoveryListing(workstreamID: workstreamID, runGeneration: 2),
      try recoveryListing(workstreamID: workstreamID, runGeneration: nil),
      try recoveryListing(workstreamID: workstreamID, runStatus: "succeeded"),
      try recoveryListing(workstreamID: workstreamID, hasActiveRun: true),
    ]
    for listing in rejectedListings {
      XCTAssertNil(
        TaskChatState.providerRecovery(
          from: listing, session: current, workstreamID: workstreamID, ownerID: "owner-a"))
    }
    let migrated = try recoverySession(adapterID: "pi-mono", generation: 2)
    XCTAssertNil(
      TaskChatState.providerRecovery(
        from: try recoveryListing(workstreamID: workstreamID), session: migrated,
        workstreamID: workstreamID, ownerID: "owner-a"),
      "an old Claude failure must not reappear after the pinned provider migrated")
  }

  func testSuspendedRecoveryReadCannotPublishAfterOwnerRevocation() async throws {
    let workstreamID = "revoked-recovery-read"
    var readStarted = false
    var capturedSnapshot: RuntimeOwnerAuthorizationSnapshot?
    var release: CheckedContinuation<TaskChatProviderRecovery?, Never>?
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, _ in
        XCTFail("Recovery hydration must never write a journal exchange")
        throw BridgeError.agentError("Unexpected journal write")
      },
      loadProviderRecoveryOperation: { _, _, snapshot in
        XCTAssertEqual(snapshot.ownerID, "owner-a")
        capturedSnapshot = snapshot
        return await withCheckedContinuation { continuation in
          release = continuation
          readStarted = true
        }
      }
    )
    let load = Task { @MainActor in await state.loadPersistedMessages() }
    while !readStarted { await Task.yield() }
    await transitionOwner(to: nil)
    await transitionOwner(to: "owner-a")
    XCTAssertFalse(RuntimeOwnerIdentity.isAuthorizationCurrent(try XCTUnwrap(capturedSnapshot)))
    release?.resume(
      returning: TaskChatProviderRecovery(
        adapterID: "acp",
        failure: AgentRuntimeFailure(
          code: "adapter_execution_failed", userMessage: "Credit balance is too low", adapterId: "acp")))
    await load.value

    XCTAssertTrue(state.ownerProjectionIsEmpty)
    XCTAssertNil(state.failedAdapterID)
    XCTAssertFalse(state.canUseOmiAI)
  }

  func testSuspendedHistoricalRecoveryCannotReplaceANewerSendOutcome() async throws {
    let workstreamID = "recovery-racing-new-send"
    var readStarted = false
    var release: CheckedContinuation<TaskChatProviderRecovery?, Never>?
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, writes in
        try self.exchangeReceipt(writes: writes, workstreamID: workstreamID)
      },
      queryOperation: { _, _, _, _ in
        AgentBridge.QueryResult(
          text: "Recovered answer", costUsd: 0, omiSessionId: "saved-session", runId: "new-run",
          attemptId: "new-attempt",
          adapterSessionId: nil, terminalStatus: "succeeded",
          inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0)
      },
      terminalizeJournalMessageOperation: { _, _, _, message, runID, attemptID in
        try self.journalTurn(
          message: message, workstreamID: workstreamID, seq: 2, status: .completed,
          producingRunId: runID, producingAttemptId: attemptID)
      },
      loadProviderRecoveryOperation: { _, _, _ in
        await withCheckedContinuation { continuation in
          release = continuation
          readStarted = true
        }
      }
    )
    let load = Task { @MainActor in await state.loadPersistedMessages() }
    while !readStarted { await Task.yield() }
    await state.sendMessage("Try a new topic")
    release?.resume(
      returning: TaskChatProviderRecovery(
        adapterID: "acp",
        failure: AgentRuntimeFailure(
          code: "adapter_execution_failed", userMessage: "Credit balance is too low", adapterId: "acp")))
    await load.value

    XCTAssertEqual(state.messages.last?.text, "Recovered answer")
    XCTAssertNil(state.errorMessage)
    XCTAssertNil(state.failedAdapterID)
    XCTAssertFalse(state.canUseOmiAI)
  }

  func testSuspendedHistoricalRecoveryCannotReplaceANewerAdmissionFailure() async {
    let workstreamID = "recovery-racing-admission-failure"
    var readStarted = false
    var release: CheckedContinuation<TaskChatProviderRecovery?, Never>?
    let state = makeState(
      workstreamID: workstreamID,
      recordJournalExchangeOperation: { _, _, _, _ in
        throw BridgeError.agentError("Journal admission rejected")
      },
      queryOperation: { _, _, _, _ in
        XCTFail("A failed journal admission must not submit a query")
        throw BridgeError.agentError("Unexpected query")
      },
      loadProviderRecoveryOperation: { _, _, _ in
        await withCheckedContinuation { continuation in
          release = continuation
          readStarted = true
        }
      }
    )
    let load = Task { @MainActor in await state.loadPersistedMessages() }
    while !readStarted { await Task.yield() }
    await state.sendMessage("Try a new topic")
    XCTAssertEqual(state.localSendToken.generation, 0)
    XCTAssertFalse(state.isSending)
    release?.resume(
      returning: TaskChatProviderRecovery(
        adapterID: "acp",
        failure: AgentRuntimeFailure(
          code: "adapter_execution_failed", userMessage: "Credit balance is too low", adapterId: "acp")))
    await load.value

    XCTAssertEqual(state.errorMessage, "Could not save this message. Try again.")
    XCTAssertTrue(state.messages.isEmpty)
    XCTAssertNil(state.failedAdapterID)
    XCTAssertFalse(state.canUseOmiAI)
  }

  private func recoverySession(adapterID: String, generation: Int) throws -> AgentSurfaceSession {
    let profile = try XCTUnwrap(
      AgentExecutionProfile(dictionary: [
        "profileGeneration": generation, "adapterId": adapterID,
        "credentialScope": adapterID == "acp" ? "local_user" : "managed_cloud",
        "workingDirectory": "/tmp", "executionRole": "coordinator",
      ]))
    return AgentSurfaceSession(
      created: false, conversationId: "conversation-task-chat-telemetry", sessionId: "saved-session", profile: profile)
  }

  private func recoveryListing(
    workstreamID: String,
    ownerID: String = "owner-a",
    sessionID: String = "saved-session",
    sessionGeneration: Int = 1,
    runGeneration: Int? = 1,
    runStatus: String = "failed",
    hasActiveRun: Bool = false
  ) throws -> String {
    var latestRun: [String: Any] = [
      "runId": "saved-run", "sessionId": sessionID, "status": runStatus,
      "errorCode": "adapter_execution_failed", "errorMessage": "Internal error: Credit balance is too low",
    ]
    if let runGeneration { latestRun["profileGeneration"] = runGeneration }
    var summary: [String: Any] = [
      "session": [
        "sessionId": sessionID, "ownerId": ownerID, "surfaceKind": "workstream", "externalRefKind": "workstream",
        "externalRefId": workstreamID, "defaultAdapterId": "acp", "executionProfileGeneration": sessionGeneration,
      ],
      "latestRun": latestRun,
      "activeRun": NSNull(),
    ]
    if hasActiveRun { summary["activeRun"] = ["runId": "active-run", "status": "running"] }
    return try XCTUnwrap(
      String(data: JSONSerialization.data(withJSONObject: ["ok": true, "sessions": [summary]]), encoding: .utf8))
  }

  /// Optional local rendering proof; CI exercises the behavioral assertions only.
  private func captureErrorPanelIfRequested(_ state: TaskChatState) throws {
    guard let directory = ProcessInfo.processInfo.environment["OMI_TASK_CREDIT_SCREENSHOT_DIR"] else { return }
    let provider = ChatProvider.mainInstance ?? ChatProvider()
    let coordinator = TaskChatCoordinator(chatProvider: provider, ownerIDProvider: { "owner-a" })
    coordinator.activeTaskId = state.activeTaskId
    coordinator.workspacePath = "/tmp/task-provider-fixture"
    let task = TaskActionItem(
      id: state.activeTaskId, description: "Research project: topic selection", completed: false, createdAt: Date()
    )
    let view = TaskChatPanel(
      taskState: state, coordinator: coordinator, task: task, onClose: {}, onOpenRewindEvidence: nil
    )
    .frame(width: 640, height: 800)
    .background(Color.white)
    .environment(\.colorScheme, .light)
    let host = NSHostingView(rootView: view)
    host.frame = NSRect(x: 0, y: 0, width: 640, height: 800)
    host.layoutSubtreeIfNeeded()
    let bitmap = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
    host.cacheDisplay(in: host.bounds, to: bitmap)
    let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
    try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
    try data.write(to: URL(fileURLWithPath: directory).appendingPathComponent("task-credit-recovery-fixture.png"))
  }

  private func makeState(
    workstreamID: String,
    recordJournalExchangeOperation: @escaping TaskChatState.RecordJournalExchangeOperation,
    queryOperation: TaskChatState.QueryOperation? = nil,
    terminalizeJournalMessageOperation: TaskChatState.TerminalizeJournalMessageOperation? = nil,
    onJournalUpdate: ((KernelJournalTurnStatus?) -> Void)? = nil,
    onTerminalize: (() -> Void)? = nil,
    useOmiAIOperation: TaskChatState.UseOmiAIOperation? = nil,
    loadProviderRecoveryOperation: TaskChatState.LoadProviderRecoveryOperation? = nil,
    listJournalTurnsOperation: TaskChatState.ListJournalTurnsOperation? = nil
  ) -> TaskChatState {
    TaskChatState(
      taskId: "task-telemetry",
      workstreamId: workstreamID,
      workspacePath: "/tmp",
      ownerIDProvider: { "owner-a" },
      attachJournalEventsOperation: { _, _, _ in UUID() },
      listJournalTurnsOperation: listJournalTurnsOperation ?? { _, _, _, _, _ in
        AgentRuntimeProcess.JournalOperationResult(
          operation: "list",
          conversationId: "conversation-task-chat-telemetry",
          turn: nil,
          turns: [],
          clearedCount: 0,
          highWaterTurnSeq: 0,
          conversationGeneration: 1,
          generationBaseTurnSeq: 0
        )
      },
      recordJournalExchangeOperation: recordJournalExchangeOperation,
      queryOperation: queryOperation,
      updateJournalMessageOperation: { _, _, _, message, status in
        onJournalUpdate?(status)
        return try self.journalTurn(
          message: message,
          workstreamID: workstreamID,
          seq: 2,
          status: status ?? .streaming
        )
      },
      terminalizeJournalMessageOperation: {
        workstreamId, ownerID, snapshot, message, producingRunId, producingAttemptId in
        onTerminalize?()
        if let terminalizeJournalMessageOperation {
          return try await terminalizeJournalMessageOperation(
            workstreamId,
            ownerID,
            snapshot,
            message,
            producingRunId,
            producingAttemptId)
        }
        return try self.journalTurn(
          message: message,
          workstreamID: workstreamID,
          seq: 2,
          status: .failed,
          producingRunId: producingRunId,
          producingAttemptId: producingAttemptId
        )
      },
      providerPreference: { "piMono" },
      useOmiAIOperation: useOmiAIOperation,
      loadProviderRecoveryOperation: loadProviderRecoveryOperation ?? { _, _, _ in nil }
    )
  }

  private func exchangeReceipt(
    writes: [KernelJournalTurnWrite],
    workstreamID: String
  ) throws -> AgentRuntimeProcess.JournalOperationResult {
    let turns = try writes.enumerated().map { index, write in
      try journalTurn(write: write, workstreamID: workstreamID, seq: index + 1)
    }
    return AgentRuntimeProcess.JournalOperationResult(
      operation: "record_exchange",
      conversationId: "conversation-task-chat-telemetry",
      turn: nil,
      turns: turns,
      clearedCount: 0,
      highWaterTurnSeq: turns.count,
      conversationGeneration: 1,
      generationBaseTurnSeq: 0
    )
  }

  private func journalTurn(
    write: KernelJournalTurnWrite,
    workstreamID: String,
    seq: Int,
    status: KernelJournalTurnStatus? = nil,
    producingRunId: String? = nil,
    producingAttemptId: String? = nil
  ) throws -> KernelJournalTurn {
    var dictionary: [String: Any] = [
      "conversationId": "conversation-task-chat-telemetry",
      "turnId": write.turnId,
      "turnSeq": seq,
      "conversationGeneration": 1,
      "generationBaseTurnSeq": 0,
      "producerId": "producer-test",
      "payloadHash": "sha256:test-\(write.turnId)",
      "role": write.role,
      "surfaceKind": "workstream",
      "externalRefKind": "workstream",
      "externalRefId": workstreamID,
      "content": write.content,
      "origin": write.origin,
      "status": (status ?? write.status).rawValue,
      "contentBlocks": [],
      "resources": [],
      "metadataJson": write.metadataJSON,
      "createdAtMs": write.createdAtMs,
      "updatedAtMs": write.createdAtMs,
    ]
    if let producingRunId {
      dictionary["producingRunId"] = producingRunId
    }
    if let producingAttemptId {
      dictionary["producingAttemptId"] = producingAttemptId
    }
    return try XCTUnwrap(KernelJournalTurn(dictionary: dictionary))
  }

  private func journalTurn(
    message: ChatMessage,
    workstreamID: String,
    seq: Int,
    status: KernelJournalTurnStatus,
    producingRunId: String? = nil,
    producingAttemptId: String? = nil
  ) throws -> KernelJournalTurn {
    try journalTurn(
      write: message.journalWrite(
        origin: "workstream",
        status: status,
        continuityKey: message.clientTurnId,
        messageSource: "workstream"
      ),
      workstreamID: workstreamID,
      seq: seq,
      status: status,
      producingRunId: producingRunId,
      producingAttemptId: producingAttemptId
    )
  }

  private func transitionOwner(to ownerID: String?) async {
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {
          await MainActor.run {
            NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
          }
        },
        { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        }
      )
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }
}
