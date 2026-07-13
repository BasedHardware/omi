import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
private final class ChatTestGenerationBox {
  var value: Int

  init(_ value: Int) {
    self.value = value
  }
}

final class ChatQueryTelemetryTests: XCTestCase {
  func testAnalyticsPayloadUsesTypedAllowlist() {
    let event = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(
        attemptId: "attempt-private",
        surface: "main_chat",
        harness: "pimono"
      ),
      durationMs: 900,
      errorClass: .timeout,
      partialResponse: true
    )

    let payload = event.analyticsPayload
    XCTAssertEqual(payload.eventName, "chat_agent_error")
    XCTAssertEqual(
      Set(payload.properties.keys),
      Set([
        "attempt_id", "surface", "harness", "duration_ms", "error_class", "error",
        "partial_response", "telemetry_schema_version", "input_length_bucket",
        "attachment_count", "has_image",
      ])
    )
    XCTAssertEqual(payload.properties["error_class"] as? String, "timeout")
    XCTAssertEqual(payload.properties["error"] as? String, "timeout")
    XCTAssertFalse(payload.properties.keys.contains("text"))
  }

  func testDecoratedToolAndFailureDimensionsCannotLeakContentOrExplodeCardinality() {
    let metrics = ChatQueryCompletionMetrics(
      toolCallCount: 4,
      toolNames: [
        "WebSearch: \"private medical query\"",
        "Read: /Users/person/secret.txt",
        "mcp__omi-tools__search_memories",
        "customer_secret_tool",
      ],
      costUsd: 0,
      responseLength: 0,
      screenToolRequested: true,
      screenToolSucceeded: false,
      screenToolApprovalRequired: false,
      screenToolFailureCodes: ["permission_denied", "person@example.com"]
    )

    XCTAssertEqual(metrics.toolNames, ["other", "read", "search_memories", "websearch"])
    XCTAssertEqual(metrics.screenToolFailureCodes, ["permission_denied", "unknown"])
    let payload = ChatQueryTelemetryEvent.completed(
      ChatQueryTelemetryContext(attemptId: "attempt-safe", surface: "main_chat", harness: "pimono"),
      durationMs: 1,
      metrics: metrics
    ).analyticsPayload
    let serializedDimensions = [
      payload.properties["tool_names"] as? String,
      payload.properties["screen_tool_failure_codes"] as? String,
    ].compactMap { $0 }.joined(separator: " ")
    XCTAssertFalse(serializedDimensions.contains("medical"))
    XCTAssertFalse(serializedDimensions.contains("/Users"))
    XCTAssertFalse(serializedDimensions.contains("@"))
  }

  func testDiagnosticErrorClassesAreBounded() {
    XCTAssertEqual(PostHogManager.diagnosticErrorClass("HTTP 401 invalid token"), "authentication")
    XCTAssertEqual(PostHogManager.diagnosticErrorClass("provider returned 429"), "rate_limit")
    XCTAssertEqual(PostHogManager.diagnosticErrorClass("auth provider returned HTTP 403"), "permission")
    XCTAssertEqual(PostHogManager.diagnosticErrorClass("auth provider rate limit 429"), "rate_limit")
    XCTAssertEqual(PostHogManager.diagnosticErrorClass("person@example.com said something"), "unknown")
  }

  func testUserStopIsCancellationButWatchdogStopIsFailure() {
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(BridgeError.stopped),
      .cancelled(.userStop)
    )
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(BridgeError.stopped, watchdogFired: true),
      .failed(.timeout)
    )
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(BridgeError.stopped, toolStallAbortFired: true),
      .failed(.toolStall)
    )
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(
        BridgeError.stopped,
        watchdogFired: true,
        toolStallAbortFired: true
      ),
      .failed(.toolStall)
    )
    XCTAssertFalse(ChatQueryFailureDisposition.classify(CancellationError()).presentsUserError)
    XCTAssertTrue(
      ChatQueryFailureDisposition.classify(BridgeError.timeout).presentsUserError
    )
  }

  @MainActor
  func testAttemptEmitsExactlyOneTerminalEvent() {
    var elapsedMs = 0
    var events: [ChatQueryTelemetryEvent] = []
    let attempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-1",
      surface: "main_chat",
      harness: "pimono",
      elapsedMilliseconds: { elapsedMs },
      eventSink: { events.append($0) }
    )

    elapsedMs = 2_000
    XCTAssertTrue(attempt.complete(metrics: ChatQueryCompletionMetrics(
      toolCallCount: 1,
      toolNames: ["get_memories"],
      costUsd: 0.01,
      responseLength: 42,
      screenToolRequested: false,
      screenToolSucceeded: false,
      screenToolApprovalRequired: false,
      screenToolFailureCodes: []
    )))
    XCTAssertFalse(attempt.fail(errorClass: .timeout))

    XCTAssertEqual(events.count, 2)
    XCTAssertEqual(
      events[0],
      .started(ChatQueryTelemetryContext(
        attemptId: "attempt-1",
        surface: "main_chat",
        harness: "pimono",
        inputLengthBucket: "0_99"
      ))
    )
    guard case .completed(let context, let durationMs, _) = events[1] else {
      return XCTFail("expected completed terminal event")
    }
    XCTAssertEqual(context.attemptId, "attempt-1")
    XCTAssertEqual(durationMs, 2_000)
  }

  func testLateOrRevokedResultsAreNeverAuthoritative() {
    XCTAssertFalse(ChatQueryResultAuthority.acceptsContinuation(
      currentGeneration: 4,
      turnGeneration: 4,
      turnAcceptsResult: false
    ), "same-generation work must stop as soon as product authority is revoked")
    XCTAssertTrue(ChatQueryResultAuthority.accepts(
      currentGeneration: 4,
      resultGeneration: 4,
      turnAcceptsResult: true,
      watchdogFired: false,
      toolStallAbortFired: false
    ))
    XCTAssertFalse(ChatQueryResultAuthority.accepts(
      currentGeneration: 5,
      resultGeneration: 4,
      turnAcceptsResult: true,
      watchdogFired: false,
      toolStallAbortFired: false
    ))
    XCTAssertFalse(ChatQueryResultAuthority.accepts(
      currentGeneration: 4,
      resultGeneration: 4,
      turnAcceptsResult: false,
      watchdogFired: false,
      toolStallAbortFired: false
    ))
    XCTAssertFalse(ChatQueryResultAuthority.accepts(
      currentGeneration: 4,
      resultGeneration: 4,
      turnAcceptsResult: true,
      watchdogFired: true,
      toolStallAbortFired: false
    ))
  }

  func testFloatingOriginWinsOverCanonicalMainRuntimeSurface() {
    XCTAssertEqual(
      ChatProvider.chatTelemetrySurface(
        turnOwner: .floatingDefault,
        isOnboarding: false,
        systemPromptStyle: .floating
      ),
      "floating_text"
    )
    XCTAssertEqual(
      ChatProvider.chatTelemetrySurface(
        turnOwner: .floatingVoice,
        isOnboarding: false,
        systemPromptStyle: .floating
      ),
      "floating_voice"
    )
  }

  func testAttemptIdJoinsTelemetryAndJournalMessages() {
    let ids = ChatProvider.messageIds(forAttemptId: "attempt-123")
    XCTAssertEqual(ids.user, "attempt-123")
    XCTAssertEqual(ids.assistant, "attempt-123-assistant")
  }

  func testStagedImageAttachmentIsReportedAsImageInput() {
    XCTAssertTrue(
      ChatProvider.chatTelemetryHasImage(
        explicitImagePresent: false,
        stagedImageAttachmentPresent: true
      )
    )
    XCTAssertFalse(
      ChatProvider.chatTelemetryHasImage(
        explicitImagePresent: false,
        stagedImageAttachmentPresent: false
      )
    )
  }

  func testStaleStoppedTurnCannotReleaseNewerSendLock() {
    var lock = ChatSendLockOwnership()

    XCTAssertTrue(lock.acquire(generation: 1))
    XCTAssertTrue(lock.release(generation: 1), "stop grace force-releases the stopped turn")
    XCTAssertTrue(lock.acquire(generation: 3), "the next user turn acquires the released bridge")

    XCTAssertFalse(lock.release(generation: 1), "late cleanup from the stopped turn is no longer authoritative")
    XCTAssertEqual(lock.generation, 3)
    XCTAssertTrue(lock.isHeld)
  }

  func testTerminalJournalTargetIsClaimedOnceWithoutConsumingNewerGeneration() {
    var targets = ChatTerminalTargetRegistry<String>()
    targets.register("old-journal-row", generation: 4)
    targets.register("new-journal-row", generation: 6)

    XCTAssertEqual(targets.claim(generation: 4), "old-journal-row")
    XCTAssertNil(targets.claim(generation: 4), "late cleanup must not finalize twice")
    XCTAssertEqual(
      targets.claim(generation: 6),
      "new-journal-row",
      "claiming the old turn must leave the newer target intact"
    )
  }

  @MainActor
  func testQueuedJournalUpdateDrainsBeforeTerminalizationAndLaterWritesAreRejectedLocally() async {
    let coordinator = ChatJournalWriteCoordinator()
    var order: [String] = []
    var postTerminalKernelAttempts = 0

    XCTAssertTrue(coordinator.schedule(messageID: "assistant-1") {
      await Task.yield()
      order.append("streaming_update")
    })

    let beganTerminalization = await coordinator.beginTerminalization(messageID: "assistant-1")
    XCTAssertTrue(beganTerminalization)
    XCTAssertFalse(coordinator.schedule(messageID: "assistant-1") {
      postTerminalKernelAttempts += 1
    })
    order.append("terminalize")
    XCTAssertFalse(coordinator.schedule(messageID: "assistant-1") {
      postTerminalKernelAttempts += 1
    })
    await Task.yield()

    XCTAssertEqual(order, ["streaming_update", "terminalize"])
    XCTAssertEqual(postTerminalKernelAttempts, 0)
  }

  @MainActor
  func testOwnerIsolationControlProbeCreatesSurfaceBeforeCanonicalExchange() async throws {
    var events: [String] = []
    var capturedWrites: [KernelJournalTurnWrite] = []
    let surface = AgentSurfaceReference.mainChat(chatId: nil)
    let recordedTurns = try [
      XCTUnwrap(KernelJournalTurn(dictionary: [
        "conversationId": "conversation-b",
        "turnId": "user-b",
        "turnSeq": 1,
        "role": "user",
        "content": "PROBE request",
        "origin": "typed_chat",
        "status": "completed",
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
      ])),
      XCTUnwrap(KernelJournalTurn(dictionary: [
        "conversationId": "conversation-b",
        "turnId": "assistant-b",
        "turnSeq": 2,
        "role": "assistant",
        "content": "PROBE",
        "origin": "typed_chat",
        "status": "completed",
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
      ])),
    ]

    let receipt = try await OwnerIsolationKernelProbe.run(
      ownerID: "owner-b",
      query: "PROBE request",
      response: "PROBE",
      registerControlOnlyRuntime: { events.append("register") },
      synchronizeOwner: {
        events.append("synchronize")
        return true
      },
      resolveSurface: {
        events.append("resolve_surface")
        return ("conversation-b", "session-b")
      },
      recordExchange: { writes in
        events.append("record_exchange")
        capturedWrites = writes
        return recordedTurns
      }
    )

    XCTAssertEqual(events, ["register", "synchronize", "resolve_surface", "record_exchange"])
    XCTAssertEqual(capturedWrites.map(\.role), ["user", "assistant"])
    XCTAssertEqual(capturedWrites.map(\.status), [.completed, .completed])
    XCTAssertEqual(capturedWrites.map(\.content), ["PROBE request", "PROBE"])
    XCTAssertEqual(receipt.ownerID, "owner-b")
    XCTAssertEqual(receipt.conversationID, "conversation-b")
    XCTAssertEqual(receipt.sessionID, "session-b")
    XCTAssertEqual(receipt.turns, recordedTurns)
  }

  @MainActor
  func testBridgeCallbackEmittedBeforeReturnDrainsBeforeTurnCompletes() async {
    let lifecycle = ChatTurnLifecycle()
    let generation = ChatTestGenerationBox(7)
    let callbacks = ChatTurnCallbackQueue(
      generation: 7,
      lifecycle: lifecycle,
      currentGeneration: { generation.value }
    )
    var visibleText = ""

    callbacks.submit {
      visibleText += "final delta"
    }

    await callbacks.drain()
    XCTAssertTrue(lifecycle.complete())
    XCTAssertEqual(visibleText, "final delta")
  }

  @MainActor
  func testCallbackQueueRejectsEveryCallbackAfterGenerationChanges() async {
    let lifecycle = ChatTurnLifecycle()
    let generation = ChatTestGenerationBox(11)
    let callbacks = ChatTurnCallbackQueue(
      generation: 11,
      lifecycle: lifecycle,
      currentGeneration: { generation.value }
    )
    var callbackEffects: [String] = []

    callbacks.submit { callbackEffects.append("text") }
    callbacks.submit { callbackEffects.append("tool") }
    callbacks.submit { callbackEffects.append("auth") }
    generation.value = 12

    await callbacks.drain()
    XCTAssertEqual(callbackEffects, [])
  }

  @MainActor
  func testCallbackQueueRejectsEveryCallbackAfterLifecycleRevocation() async {
    let lifecycle = ChatTurnLifecycle()
    let generation = ChatTestGenerationBox(3)
    let callbacks = ChatTurnCallbackQueue(
      generation: 3,
      lifecycle: lifecycle,
      currentGeneration: { generation.value }
    )
    var callbackEffects: [String] = []

    callbacks.submit { callbackEffects.append("delta") }
    XCTAssertTrue(lifecycle.revoke(.stop(.superseded)))

    await callbacks.drain()
    XCTAssertEqual(callbackEffects, [])
  }

  func testStatusOnlyJournalTerminalizationCarriesNoLateResultPayload() {
    let update = KernelJournalTurnUpdate.statusOnly(
      turnId: "attempt-7-assistant",
      status: .failed
    )

    XCTAssertEqual(
      Set(update.dictionary.keys),
      Set(["turnId", "status"])
    )
    XCTAssertEqual(update.dictionary["turnId"] as? String, "attempt-7-assistant")
    XCTAssertEqual(update.dictionary["status"] as? String, "failed")
  }

  @MainActor
  func testVisibleCompletionEmitsOneTerminalEventBeforeJournalCommit() async {
    let lifecycle = ChatTurnLifecycle()
    var order: [String] = []
    let attempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-visible",
      surface: "main_chat",
      harness: "pimono",
      eventSink: { event in
        switch event {
        case .started: order.append("started")
        case .completed, .failed, .cancelled: order.append("terminal")
        }
      }
    )
    let metrics = ChatQueryCompletionMetrics(
      toolCallCount: 0,
      toolNames: [],
      costUsd: 0,
      responseLength: 12,
      screenToolRequested: false,
      screenToolSucceeded: false,
      screenToolApprovalRequired: false,
      screenToolFailureCodes: []
    )

    let journalAccepted = await ChatVisibleTurnCompletion.finish(
      lifecycle: lifecycle,
      telemetryAttempt: attempt,
      metrics: metrics,
      afterTerminal: { order.append("cleanup") },
      journalCommit: {
        order.append("journal")
        return true
      }
    )

    XCTAssertTrue(journalAccepted)
    XCTAssertEqual(order, ["started", "terminal", "cleanup", "journal"])
    XCTAssertFalse(attempt.fail(errorClass: .unknown))
    XCTAssertEqual(order.filter { $0 == "terminal" }.count, 1)
  }

  @MainActor
  func testTurnLifecycleRevocationIsIndependentFromTelemetry() {
    let lifecycle = ChatTurnLifecycle()
    XCTAssertTrue(lifecycle.acceptsResult)
    XCTAssertTrue(lifecycle.revoke(.stop(.userStop)))
    XCTAssertFalse(lifecycle.acceptsResult)
    XCTAssertEqual(lifecycle.state, .revoked(.stop(.userStop)))
    XCTAssertFalse(lifecycle.complete())
  }

  @MainActor
  func testEarlierToolStallRevocationCannotBeRelabeledByWatchdog() {
    let lifecycle = ChatTurnLifecycle()

    XCTAssertTrue(lifecycle.revoke(.toolStall))
    XCTAssertFalse(lifecycle.revoke(.watchdogTimeout))
    XCTAssertEqual(lifecycle.revocationReason, .toolStall)
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(
        BridgeError.stopped,
        watchdogFired: lifecycle.revocationReason == .watchdogTimeout,
        toolStallAbortFired: lifecycle.revocationReason == .toolStall
      ),
      .failed(.toolStall)
    )
  }

  @MainActor
  func testAttemptClassifiesStoppedTurnWithoutEmittingAnError() {
    var events: [ChatQueryTelemetryEvent] = []
    let attempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-stop",
      surface: "floating_chat",
      harness: "hermes",
      eventSink: { events.append($0) }
    )

    XCTAssertTrue(attempt.finish(error: BridgeError.stopped, partialResponse: true))
    XCTAssertEqual(events.count, 2)
    guard case .cancelled(_, _, let reason, let partialResponse) = events[1] else {
      return XCTFail("expected cancelled terminal event")
    }
    XCTAssertEqual(reason, .userStop)
    XCTAssertTrue(partialResponse)
  }

  @MainActor
  func testExplicitStopProvenanceDistinguishesFailureFromSupersession() {
    var browserEvents: [ChatQueryTelemetryEvent] = []
    let browserAttempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-browser",
      surface: "main_chat",
      harness: "pimono",
      eventSink: { browserEvents.append($0) }
    )
    XCTAssertTrue(browserAttempt.finish(stopReason: .browserExtensionMissing))
    guard case .failed(_, _, let errorClass, _) = browserEvents.last else {
      return XCTFail("expected browser precondition failure")
    }
    XCTAssertEqual(errorClass, .browserExtensionMissing)

    var supersededEvents: [ChatQueryTelemetryEvent] = []
    let supersededAttempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-superseded",
      surface: "floating_chat",
      harness: "hermes",
      eventSink: { supersededEvents.append($0) }
    )
    XCTAssertTrue(supersededAttempt.finish(stopReason: .superseded))
    guard case .cancelled(_, _, let reason, _) = supersededEvents.last else {
      return XCTFail("expected superseded cancellation")
    }
    XCTAssertEqual(reason, .superseded)
  }
}
