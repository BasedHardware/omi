import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubSpawnAgentTests: XCTestCase {
  func testSpawnAgentSuppressesPostToolAssistantOutput() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var suppressAssistantOutputForCurrentTurn = false"))
    XCTAssertTrue(source.contains("guard !suppressAssistantOutputForCurrentTurn,"))
    XCTAssertTrue(source.contains("!voiceOutputCoordinator.snapshot().providerOutputSuppressed"))
    XCTAssertTrue(source.contains("suppressAssistantOutputForCurrentTurn = true"))
    XCTAssertTrue(source.contains("output: \"Agent started.\""))
    XCTAssertFalse(source.contains("Acknowledged before the call — do not say anything else"))
  }

  func testSpawnAgentUsesCanonicalDelegationPath() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let shouldAllowNativePostSpawnAck = !audioReceivedThisTurn"))
    XCTAssertTrue(source.contains("let existingAck = assistantText.trimmingCharacters"))
    XCTAssertTrue(source.contains("let resolvedAck = resolution.ack?.trimmingCharacters"))
    XCTAssertTrue(
      source.contains(
        "resolvedAck?.isEmpty == false ? resolvedAck! : \"Starting a background agent.\""))
    XCTAssertTrue(
      source.contains("pendingVoiceAgentHandoff = (title: pill.title, brief: resolvedBrief)"))
    XCTAssertTrue(source.contains("idempotencyKey: completedTurnIdempotencyKey"))
    XCTAssertTrue(source.contains("Started background agent"))
    XCTAssertTrue(
      source.contains("suppressAssistantOutputForCurrentTurn = !shouldAllowNativePostSpawnAck"))
    XCTAssertTrue(source.contains("await self.handleRealtimeDelegationRequest("))
    XCTAssertTrue(source.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation("))
    XCTAssertFalse(source.contains("name: \"spawn_agent\", arguments: toolArgs"))
    XCTAssertFalse(source.contains("speak(ack)"))
  }

  func testDelayedDelegationResolutionCannotCrossBargeInBoundary() async {
    var current = true
    let resolution = await RealtimeDelegationExecutionGate.resolveIfCurrent(
      resolve: {
        await Task.yield()
        current = false
        return "resolved"
      },
      isCurrent: { current })

    XCTAssertNil(resolution)
  }

  func testStaleDelegationCannotExecuteSpawnSideEffect() {
    var spawnCount = 0

    let result: String? = RealtimeDelegationExecutionGate.performIfCurrent(
      isCurrent: { false },
      operation: {
        spawnCount += 1
        return "Agent started."
      })

    XCTAssertNil(result)
    XCTAssertEqual(spawnCount, 0)
  }

  func testFailedDelegationProducesNoSuccessAcknowledgement() {
    let result: String? = RealtimeDelegationExecutionGate.performIfCurrent(
      isCurrent: { true },
      operation: { nil })

    XCTAssertNil(result)
  }

  func testRealtimeHubBlocksModelInitiatedPillDismissalWithoutExplicitUserRequest() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(
      source.contains(
        "userExplicitlyRequestedPillManagement(action: action, transcript: turnTranscript)"))
    XCTAssertTrue(source.contains("blocked set_desktop_attention_override"))
    XCTAssertTrue(
      source.contains(
        "Dismissal blocked: only dismiss or clear floating agent pills when the user explicitly asks."
      ))
    XCTAssertTrue(source.contains("case \"dismiss\":"))
    XCTAssertTrue(source.contains("case \"clear_completed\":"))
  }

  func testRealtimeHubUsesCanonicalVoicePlaybackServiceForLocalSpeechFallbacks() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("AVSpeechSynthesizer"))
    XCTAssertFalse(source.contains("AVSpeechUtterance"))
    XCTAssertFalse(source.contains("AVSpeechSynthesisVoice"))
    XCTAssertFalse(source.contains("private func speak(_ text: String)"))
    XCTAssertTrue(
      source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(reply, lease: lease)"))
    XCTAssertTrue(source.contains("directedProvider.setupNeededStatus,"))
    XCTAssertTrue(
      source.contains("FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()"))
    XCTAssertTrue(
      source.contains(
        "acquireVoiceOutput(.selectedVoiceFallback, reason: \"text_no_native_audio\")"))
    XCTAssertTrue(
      source.contains(".deterministicAgentAck, reason: \"directed_provider_unavailable\""))
  }

  func testRealtimeHubAudibleOutputIsLeaseGated() throws {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    guard case .acquired(let native) = coordinator.acquire(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native output should acquire the turn")
    }

    XCTAssertEqual(
      coordinator.acquire(.selectedVoiceFallback, turnID: turnID),
      .denied(active: native))
    XCTAssertEqual(
      coordinator.acquire(.deterministicAgentAck, turnID: turnID),
      .denied(active: native))
    XCTAssertFalse(coordinator.snapshot().providerOutputSuppressed)
  }

  func testRealtimeToolTurnsStayOpenUntilToolResultReturns() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var pendingRealtimeToolCallIds = Set<String>()"))
    XCTAssertTrue(source.contains("private var realtimeToolTurnEpoch = 0"))
    XCTAssertTrue(source.contains("expectedTurnEpoch: Int? = nil"))
    XCTAssertTrue(source.contains("pendingRealtimeToolCallIds.insert("))
    XCTAssertTrue(
      source.contains("toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch)"))
    XCTAssertTrue(source.contains("pendingRealtimeToolCallIds.remove(key)"))
    XCTAssertTrue(source.contains("turnEpoch == realtimeToolTurnEpoch"))
    XCTAssertTrue(source.contains("guard pendingRealtimeToolCallIds.isEmpty else"))
    XCTAssertTrue(source.contains("deferring turn done with"))
    XCTAssertTrue(source.contains("private func clearRealtimeToolTracking()"))
    XCTAssertTrue(source.contains("realtimeToolTurnEpoch += 1"))
    XCTAssertGreaterThanOrEqual(
      source.components(separatedBy: "clearRealtimeToolTracking()").count - 1, 4)
    XCTAssertFalse(source.contains("session?.sendToolResult("))
  }

  func testRealtimeDelegationResolutionCannotSpawnAfterStaleTurn() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let userText = turnTranscript"))
    XCTAssertTrue(source.contains("RealtimeDelegationExecutionGate.resolveIfCurrent("))
    XCTAssertTrue(
      source.contains(
        "source: source, callId: callId, name: name, expectedTurnEpoch: expectedTurnEpoch"))
    XCTAssertTrue(source.contains("dropping stale spawn_agent resolution before side effects"))
    XCTAssertTrue(source.contains("RealtimeDelegationExecutionGate.performIfCurrent("))
    XCTAssertTrue(source.contains("private func isCurrentToolTurn("))
    XCTAssertTrue(
      source.contains(
        "return expectedTurnEpoch == realtimeToolTurnEpoch && pendingRealtimeToolCallIds.contains(key)"
      ))
  }

  func testBargeInReplacementCommitIsDeferredInsteadOfRejected() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("case deferredForReplacement"))
    XCTAssertTrue(source.contains("if var pending = pendingBargeInReplacement"))
    XCTAssertTrue(source.contains("pending.pendingCommit = true"))
    XCTAssertTrue(source.contains("pendingBargeInReplacement = pending"))
    XCTAssertTrue(source.contains("barge-in replacement not ready at commit"))
    XCTAssertTrue(source.contains("return .deferredForReplacement"))
    XCTAssertFalse(
      source.contains(
        "barge-in replacement not ready at commit — falling back to buffered transcription"))
  }

  func testCompletedVoiceTurnUsesKernelPersistenceAfterAsyncCorrection() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let completedTurnIdempotencyKey = turnIdempotencyKey"))
    XCTAssertFalse(source.contains("self?.turnIdempotencyKey ="))
    XCTAssertTrue(source.contains("let resolution = await Self.resolveTranscript("))
    XCTAssertTrue(source.contains("resolution.usedLocalTranscript"))
    XCTAssertTrue(source.contains("idempotencyKey: completedTurnIdempotencyKey"))
    XCTAssertFalse(source.contains("rememberVoiceContinuityTurn("))
    XCTAssertFalse(source.contains("replaceVoiceContinuityTurn("))
  }

  func testSpawnAgentPreflightsDirectedProviderAvailability() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("LocalAgentProviderDetector.availability(for: directedProvider)"))
    XCTAssertTrue(source.contains("guard availability.isAvailable else"))
    XCTAssertTrue(source.contains("assistantText = setupPrompt"))
    XCTAssertTrue(source.contains("output: availability.toolError"))
    XCTAssertTrue(
      source.contains(
        """
                sendToolResultIfCurrent(
                  source: source, callId: callId, name: name,
                  output: availability.toolError,
                  expectedTurnEpoch: expectedTurnEpoch)
                return
        """))
  }

  func testCanonicalAgentControlSummariesDoNotSpeakOpaqueIds() throws {
    let source = try agentControlServiceSource()

    XCTAssertTrue(
      source.contains(
        "Use agentRef values internally for follow-up tool calls; do not say them aloud"))
    XCTAssertTrue(
      source.contains(
        "Use artifactRef values internally for follow-up tool calls; do not say them aloud"))
    XCTAssertTrue(source.contains("agent_\\(index + 1)"))
    XCTAssertTrue(source.contains("artifact_\\(index + 1)"))
    XCTAssertFalse(source.contains("sessionId=\\($0)"))
    XCTAssertFalse(source.contains("runId=\\($0)"))
    XCTAssertFalse(source.contains("artifactId=\\(artifactId)"))
    XCTAssertTrue(source.contains("The selected canonical run is \\(status)"))
    XCTAssertTrue(source.contains("Agent control failed. Try listing the agents again"))
    XCTAssertTrue(source.contains("Artifact lifecycle is now \\(state)"))
  }

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func agentControlServiceSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentControlService.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
