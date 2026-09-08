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
  /// A failed tool call used to emit nothing at all: the call site removed the
  /// start time and then gated the event on `toolStatus == .completed`, so 30
  /// days of `chat_tool_call_completed` carried only successes and tool
  /// reliability could not be measured. Every terminal bridge status must now
  /// map to a bounded outcome.
  func testEveryTerminalBridgeStatusReportsABoundedToolOutcome() {
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome("failed"), "failed")
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome("cancelled"), "cancelled")
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome("interrupted"), "interrupted")
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome("completed"), "completed")

    // Unknown adapter vocabulary must not leak or inflate successful calls.
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome("some_new_status"), "unknown")
    XCTAssertEqual(ChatTelemetryDimension.toolOutcome(""), "unknown")
  }

  /// User Stop is not a tool defect. `ToolCallStatus` deliberately collapses
  /// cancelled/interrupted into `.failed` for the UI, so the telemetry
  /// dimension must stay independent of it or a Stop would count as a failure.
  func testStopIsDistinguishableFromFailureEvenThoughBothMapToFailedStatus() {
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("cancelled"), .failed)
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("interrupted"), .failed)
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("failed"), .failed)

    XCTAssertNotEqual(
      ChatTelemetryDimension.toolOutcome("cancelled"),
      ChatTelemetryDimension.toolOutcome("failed"))
    XCTAssertNotEqual(
      ChatTelemetryDimension.toolOutcome("interrupted"),
      ChatTelemetryDimension.toolOutcome("failed"))
  }

  func testKernelContextTimeoutDoesNotInterruptAnUnstartedAgentQuery() {
    XCTAssertFalse(ChatProvider.shouldInterruptTimedOutAgentQuery(queryStarted: false))
    XCTAssertTrue(ChatProvider.shouldInterruptTimedOutAgentQuery(queryStarted: true))
  }

  func testFailedPayloadCarriesBoundedErrorDetail() {
    let detail = ChatQueryErrorDetail.from(
      BridgeError.agentError("400 Your credit balance is too low to access the Anthropic API."))
    let event = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(attemptId: "attempt-detail", surface: "main_chat", harness: "acp"),
      durationMs: 1200,
      errorClass: .agentError,
      partialResponse: false,
      detail: detail
    )
    let properties = event.analyticsPayload.properties
    XCTAssertEqual(properties["error_code"] as? String, "provider_billing_exhausted")
    XCTAssertEqual(properties["retryable"] as? Bool, false)
    // Bounded dimensions only: the raw provider text must never reach analytics.
    XCTAssertFalse(
      String(describing: properties).contains("credit balance"),
      "raw exception text leaked into analytics properties")
  }

  func testRuntimeFailureDetailCarriesDaemonTaxonomy() {
    let failure = AgentRuntimeFailure(
      code: "adapter_execution_failed",
      failureCode: .authentication,
      userMessage: "Authentication required",
      source: "adapter_execution",
      adapterId: "openclaw",
      provider: "anthropic",
      retryable: false
    )
    let detail = ChatQueryErrorDetail.from(BridgeError.agentRuntimeFailure(failure))
    XCTAssertEqual(detail?.errorCode, "authentication")
    XCTAssertEqual(detail?.failureCode, "adapter_execution_failed")
    XCTAssertEqual(detail?.failureSource, "adapter_execution")
    XCTAssertEqual(detail?.adapterId, "openclaw")
    XCTAssertEqual(detail?.retryable, false)
  }

  func testWorkerRecoveryTelemetryIsBoundedAndExplainsTheNextSendContract() {
    let failure = AgentRuntimeFailure(
      code: "adapter_execution_failed",
      userMessage: "Agent run failed",
      technicalMessage: "private prompt /Users/person/secret.txt",
      source: "adapter_execution",
      adapterId: "pi-mono",
      retryable: true,
      recoveryAction: "worker_recycled",
      recoveryOutcome: "recovered",
      retryDisposition: "next_send"
    )
    let event = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(attemptId: "attempt-recycled", surface: "main_chat", harness: "piMono"),
      durationMs: 400,
      errorClass: .agentError,
      partialResponse: false,
      detail: .from(BridgeError.agentRuntimeFailure(failure))
    )
    let properties = event.analyticsPayload.properties
    XCTAssertEqual(properties["recovery_action"] as? String, "worker_recycled")
    XCTAssertEqual(properties["recovery_outcome"] as? String, "recovered")
    XCTAssertEqual(properties["retry_disposition"] as? String, "next_send")
    XCTAssertFalse(String(describing: properties).contains("/Users/person"))
    XCTAssertFalse(String(describing: properties).contains("private prompt"))
  }

  func testUnknownDaemonAuthFailureReportsClassifierCodeAndIsNotRetryable() {
    let failure = AgentRuntimeFailure(
      code: "adapter_execution_failed",
      failureCode: .unknown,
      userMessage: "Authentication required",
      source: "adapter_execution",
      adapterId: "pi-mono",
      retryable: true
    )
    let error = BridgeError.agentRuntimeFailure(failure)
    let detail = ChatQueryErrorDetail.from(error)

    XCTAssertEqual(detail?.errorCode, "provider_auth_expired")
    XCTAssertEqual(detail?.retryable, false)
    XCTAssertEqual(ChatQueryFailureDisposition.classify(error), .failed(.authentication))
  }

  func testRecycledWorkerHTTP402ReportsBillingNotUnknownRuntime() {
    let failure = AgentRuntimeFailure(
      code: "adapter_execution_failed",
      userMessage: "The local agent reset its session after an error. Send your message again.",
      technicalMessage: "HTTP 402 status code (no body)",
      source: "adapter_execution",
      adapterId: "pi-mono",
      retryable: true,
      recoveryAction: "worker_recycled",
      recoveryOutcome: "recovered",
      retryDisposition: "next_send"
    )
    let error = BridgeError.agentRuntimeFailure(failure)
    let detail = ChatQueryErrorDetail.from(error)

    XCTAssertEqual(detail?.errorCode, "provider_billing_exhausted")
    XCTAssertEqual(detail?.retryable, false)
    XCTAssertEqual(detail?.recoveryAction, "worker_recycled")
    XCTAssertEqual(detail?.adapterId, "pi-mono")
    XCTAssertEqual(ChatQueryFailureDisposition.classify(error), .failed(.quota))
  }

  func testRuntimeDetailedFailureCodeMustBeInTheAnalyticsAllowlist() {
    let failure = AgentRuntimeFailure(
      code: "provider_error_/Users/person/secret.txt",
      userMessage: "Agent run failed"
    )
    let event = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(attemptId: "attempt-private-code", surface: "main_chat", harness: "piMono"),
      durationMs: 100,
      errorClass: .agentRuntime,
      partialResponse: false,
      detail: .from(BridgeError.agentRuntimeFailure(failure))
    )
    let properties = event.analyticsPayload.properties
    XCTAssertNil(properties["failure_code"])
    XCTAssertFalse(String(describing: properties).contains("/Users/person"))
  }

  func testAnalyticsPayloadUsesTypedAllowlist() {
    let event = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(
        attemptId: "attempt-private",
        surface: "main_chat",
        harness: "pimono"
      ),
      durationMs: 900,
      errorClass: .timeout,
      partialResponse: true,
      detail: nil
    )

    let payload = event.analyticsPayload
    XCTAssertEqual(payload.eventName, "chat_agent_error")
    XCTAssertEqual(
      Set(payload.properties.keys),
      Set([
        "attempt_id", "surface", "harness", "duration_ms", "error_class", "error",
        "error_code", "root_cause",
        "partial_response", "watchdog_fired", "telemetry_schema_version", "input_length_bucket",
        "attachment_count", "has_image",
      ])
    )
    XCTAssertEqual(payload.properties["error_class"] as? String, "timeout")
    XCTAssertEqual(payload.properties["error"] as? String, "timeout")
    XCTAssertFalse(payload.properties.keys.contains("text"))
  }

  /// The 2026-08 macOS churn cohort could not explain `chat_agent_error` because
  /// only the bridge catch path supplied a `ChatQueryErrorDetail`; every other
  /// terminal arrived with no `error_code` and no `root_cause`. Every failure
  /// class must now classify itself.
  func testEveryFailureClassCarriesABoundedCodeAndRootCause() {
    let allClasses: [ChatQueryErrorClass] = [
      .agentError, .agentRuntime, .attachmentUpload, .authentication, .bridgeUnavailable,
      .bridgeStartFailed, .browserExtensionMissing, .concurrentRequest, .encoding, .quota,
      .resourceExhausted, .sessionSetup, .timeout, .toolStall, .transientNetwork, .unknown,
    ]
    let allowedRootCauses = Set(
      [
        ChatQueryRootCause.agentRuntime, .attachmentPipeline, .bridgeProcess, .browserExtension,
        .deviceResources, .localSession, .network, .providerClaude, .requestEncoding, .unclassified,
      ].map(\.rawValue))

    for errorClass in allClasses {
      let payload = ChatQueryTelemetryEvent.failed(
        ChatQueryTelemetryContext(attemptId: "a", surface: "main_chat", harness: "pimono"),
        durationMs: 10,
        errorClass: errorClass,
        partialResponse: false,
        detail: nil
      ).analyticsPayload
      let code = payload.properties["error_code"] as? String
      let rootCause = payload.properties["root_cause"] as? String
      XCTAssertNotNil(code, "\(errorClass.rawValue) emitted no error_code")
      XCTAssertFalse(code?.isEmpty ?? true, "\(errorClass.rawValue) emitted an empty error_code")
      XCTAssertNotNil(rootCause, "\(errorClass.rawValue) emitted no root_cause")
      XCTAssertTrue(
        allowedRootCauses.contains(rootCause ?? ""),
        "\(errorClass.rawValue) emitted unbounded root_cause \(rootCause ?? "nil")")
    }
  }

  /// Auth kept the value already published to PostHog so existing breakdowns
  /// stay valid, and the two timeouts stay distinguishable because they have
  /// different owners.
  func testRootCauseAndTimeoutCodesStayActionable() {
    func payload(_ errorClass: ChatQueryErrorClass, watchdogFired: Bool = false) -> [String: Any] {
      ChatQueryTelemetryEvent.failed(
        ChatQueryTelemetryContext(attemptId: "a", surface: "main_chat", harness: "pimono"),
        durationMs: 10,
        errorClass: errorClass,
        partialResponse: false,
        detail: nil,
        watchdogFired: watchdogFired
      ).analyticsPayload.properties
    }

    XCTAssertEqual(payload(.authentication)["root_cause"] as? String, "provider_claude")
    XCTAssertEqual(payload(.authentication)["turn_disposition"] as? String, "auth_blocked")
    XCTAssertEqual(payload(.quota)["root_cause"] as? String, "provider_claude")
    XCTAssertEqual(payload(.bridgeUnavailable)["root_cause"] as? String, "bridge_process")
    XCTAssertEqual(payload(.timeout, watchdogFired: true)["error_code"] as? String, "watchdog_timeout")
    XCTAssertEqual(payload(.timeout)["error_code"] as? String, "bridge_timeout")
  }

  /// A detail is strictly better information than the class fallback, so it
  /// must win rather than be shadowed by it.
  func testErrorDetailCodeOverridesTheClassFallback() {
    let payload = ChatQueryTelemetryEvent.failed(
      ChatQueryTelemetryContext(attemptId: "a", surface: "main_chat", harness: "pimono"),
      durationMs: 10,
      errorClass: .agentRuntime,
      partialResponse: false,
      detail: .from(
        BridgeError.agentRuntimeFailure(
          AgentRuntimeFailure(code: "adapter_not_registered", userMessage: "Agent run failed")))
    ).analyticsPayload

    XCTAssertEqual(payload.properties["failure_code"] as? String, "adapter_not_registered")
    XCTAssertNotEqual(payload.properties["error_code"] as? String, "agent_runtime_failure")
    XCTAssertEqual(payload.properties["root_cause"] as? String, "agent_runtime")
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
    XCTAssertEqual(
      ChatQueryFailureDisposition.classify(BridgeError.failedToStart(.launchFailed)),
      .failed(.bridgeStartFailed)
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
    XCTAssertTrue(
      attempt.complete(
        metrics: ChatQueryCompletionMetrics(
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
      .started(
        ChatQueryTelemetryContext(
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
    XCTAssertFalse(
      ChatQueryResultAuthority.acceptsContinuation(
        currentGeneration: 4,
        turnGeneration: 4,
        turnAcceptsResult: false
      ), "same-generation work must stop as soon as product authority is revoked")
    XCTAssertTrue(
      ChatQueryResultAuthority.accepts(
        currentGeneration: 4,
        resultGeneration: 4,
        turnAcceptsResult: true,
        watchdogFired: false,
        toolStallAbortFired: false
      ))
    XCTAssertFalse(
      ChatQueryResultAuthority.accepts(
        currentGeneration: 5,
        resultGeneration: 4,
        turnAcceptsResult: true,
        watchdogFired: false,
        toolStallAbortFired: false
      ))
    XCTAssertFalse(
      ChatQueryResultAuthority.accepts(
        currentGeneration: 4,
        resultGeneration: 4,
        turnAcceptsResult: false,
        watchdogFired: false,
        toolStallAbortFired: false
      ))
    XCTAssertFalse(
      ChatQueryResultAuthority.accepts(
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

  func testQuestionInteractionContinuityMatchesKernelOwnerConversationScope() {
    let continuityKey = ChatProvider.questionInteractionContinuityKey(
      ownerID: "alice",
      conversationID: "conv_442a0a6004964766830774eb406562e4",
      questionID: "cold-start:0:step:1",
      optionID: "cold-start:0:outcome:progress"
    )

    XCTAssertEqual(continuityKey, "qri_918fa0e3102b91249755bfc291dfb813")
    XCTAssertEqual(
      ChatProvider.messageIds(forAttemptId: continuityKey).user,
      "turn_61f833a2129a50b2"
    )
    XCTAssertEqual(
      ChatProvider.messageIds(forAttemptId: continuityKey).assistant,
      "turn_c7ec848ab1718b5f"
    )
    XCTAssertNotEqual(
      continuityKey,
      ChatProvider.questionInteractionContinuityKey(
        ownerID: "bob",
        conversationID: "conv_442a0a6004964766830774eb406562e4",
        questionID: "cold-start:0:step:1",
        optionID: "cold-start:0:outcome:progress"
      )
    )
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

    XCTAssertTrue(
      coordinator.schedule(messageID: "assistant-1") {
        await Task.yield()
        order.append("streaming_update")
      })

    let beganTerminalization = await coordinator.beginTerminalization(messageID: "assistant-1")
    XCTAssertTrue(beganTerminalization)
    XCTAssertFalse(
      coordinator.schedule(messageID: "assistant-1") {
        postTerminalKernelAttempts += 1
      })
    order.append("terminalize")
    XCTAssertFalse(
      coordinator.schedule(messageID: "assistant-1") {
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
      XCTUnwrap(
        KernelJournalTurn(dictionary: [
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
      XCTUnwrap(
        KernelJournalTurn(dictionary: [
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
    guard case .failed(_, _, let errorClass, _, _, _) = browserEvents.last else {
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

  // T5: auth-blocked turns classify as authentication with session adapter + disposition.
  @MainActor
  func testAuthenticationFailureTelemetryIncludesSessionAdapterAndDisposition() {
    var events: [ChatQueryTelemetryEvent] = []
    let attempt = ChatQueryTelemetryAttempt(
      attemptId: "attempt-auth-blocked",
      surface: "main_chat",
      harness: "piMono",
      bridgeModePreference: "piMono",
      sessionAdapterId: "acp",
      eventSink: { events.append($0) }
    )

    XCTAssertTrue(attempt.fail(errorClass: .authentication))
    guard let terminal = events.last,
      case .failed(_, _, let errorClass, _, _, let watchdogFired) = terminal
    else {
      return XCTFail("expected failed terminal event")
    }
    XCTAssertEqual(errorClass, .authentication)
    XCTAssertFalse(watchdogFired)

    let payload = terminal.analyticsPayload
    XCTAssertEqual(payload.properties["error_class"] as? String, "authentication")
    XCTAssertEqual(payload.properties["session_adapter_id"] as? String, "acp")
    XCTAssertEqual(payload.properties["harness"] as? String, "piMono")
    XCTAssertEqual(payload.properties["bridge_mode_preference"] as? String, "piMono")
    XCTAssertEqual(payload.properties["turn_disposition"] as? String, "auth_blocked")
    XCTAssertEqual(payload.properties["root_cause"] as? String, "provider_claude")
    XCTAssertEqual(payload.properties["adapter_harness_mismatch"] as? Bool, true)
    XCTAssertEqual(payload.properties["watchdog_fired"] as? Bool, false)
  }

  @MainActor
  func testRuntimeAuthenticationFailureClassifiesAsAuthentication() {
    let failure = AgentRuntimeFailure(
      code: "provider_auth_required",
      failureCode: .authentication,
      userMessage: "Claude sign-in is required to continue this chat."
    )
    let disposition = ChatQueryFailureDisposition.classify(
      BridgeError.agentRuntimeFailure(failure)
    )
    guard case .failed(let errorClass) = disposition else {
      return XCTFail("expected failed disposition")
    }
    XCTAssertEqual(errorClass, .authentication)
    XCTAssertTrue(BridgeError.agentRuntimeFailure(failure).isSessionAuthenticationFailure)
  }
}
