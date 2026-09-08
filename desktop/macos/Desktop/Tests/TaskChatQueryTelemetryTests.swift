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

  private func makeState(
    workstreamID: String,
    recordJournalExchangeOperation: @escaping TaskChatState.RecordJournalExchangeOperation,
    queryOperation: TaskChatState.QueryOperation? = nil,
    terminalizeJournalMessageOperation: TaskChatState.TerminalizeJournalMessageOperation? = nil,
    onJournalUpdate: ((KernelJournalTurnStatus?) -> Void)? = nil,
    onTerminalize: (() -> Void)? = nil
  ) -> TaskChatState {
    TaskChatState(
      taskId: "task-telemetry",
      workstreamId: workstreamID,
      workspacePath: "/tmp",
      ownerIDProvider: { "owner-a" },
      listJournalTurnsOperation: { _, _, _, _, _ in
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
      }
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
        }
      ) { defaults in
        defaults.removeObject(forKey: .automationOwnerOverride)
        if let ownerID {
          defaults.set(ownerID, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
      }
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }
}
