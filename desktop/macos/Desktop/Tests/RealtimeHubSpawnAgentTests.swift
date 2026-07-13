import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubSpawnAgentTests: XCTestCase {
  func testLocalProfileTurnPlanIsFailClosedOutsideHermeticProfile() {
    XCTAssertNil(
      RealtimeLocalProfileTurnPlan.make(
        transcript: RealtimeLocalProfileTurnPlan.exactMemoryAgentRequest,
        voiceContext: "",
        localProfileEnabled: false))
  }

  func testLocalProfileExactMemoryRequestProducesOneCanonicalSpawnProposal() throws {
    let plan = try XCTUnwrap(
      RealtimeLocalProfileTurnPlan.make(
        transcript: RealtimeLocalProfileTurnPlan.exactMemoryAgentRequest,
        voiceContext: "",
        localProfileEnabled: true))

    XCTAssertEqual(
      plan.spawn,
      RealtimeLocalProfileTurnPlan.Spawn(
        objective: RealtimeLocalProfileTurnPlan.exactMemoryAgentRequest,
        title: "Today's memory insight"))
    XCTAssertFalse(plan.assistantText.isEmpty)
  }

  func testLocalProfileOrdinaryAndRecallTurnsNeverProposeSpawn() throws {
    let marker = "GAUNTLET-20260712-FLOATING-ABC123"
    let ordinary = try XCTUnwrap(
      RealtimeLocalProfileTurnPlan.make(
        transcript: "Remember \(marker) exactly.",
        voiceContext: "",
        localProfileEnabled: true))
    XCTAssertNil(ordinary.spawn)
    XCTAssertTrue(ordinary.assistantText.contains(marker))

    let recall = try XCTUnwrap(
      RealtimeLocalProfileTurnPlan.make(
        transcript: "What was the last thing I asked you for?",
        voiceContext: "Earlier GAUNTLET-OLD. Latest \(marker).",
        localProfileEnabled: true))
    XCTAssertNil(recall.spawn)
    XCTAssertTrue(recall.assistantText.contains(marker))
    XCTAssertFalse(recall.assistantText.contains("GAUNTLET-OLD"))
  }

  func testSpawnJournalReceiptAcceptsOnlyCanonicalTurnIdentity() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
    let payload: [String: Any] = [
      "ok": true,
      "journalReceipt": [
        "accepted": true,
        "continuityKey": continuityKey,
        "userTurnId": KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "user"),
        "assistantTurnId": KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
        "assistantText": "I started a background agent for that.",
      ],
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = try XCTUnwrap(String(data: data, encoding: .utf8))

    XCTAssertEqual(
      RealtimeSpawnJournalReceipt.parse(
        output: output, expectedContinuityKey: continuityKey),
      RealtimeSpawnJournalReceipt(
        continuityKey: continuityKey,
        userTurnID: KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "user"),
        assistantTurnID: KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
        assistantText: "I started a background agent for that."))
    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: output,
        expectedContinuityKey: "voice:00000000-0000-0000-0000-000000000000"))
  }

  func testSpawnJournalReceiptRejectsTamperedStableIdentity() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
    let payload: [String: Any] = [
      "journalReceipt": [
        "accepted": true,
        "continuityKey": continuityKey,
        "userTurnId": "turn_tampered",
        "assistantTurnId": KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
        "assistantText": "I started a background agent for that.",
      ]
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = try XCTUnwrap(String(data: data, encoding: .utf8))

    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: output, expectedContinuityKey: continuityKey))
  }

  func testRealtimeToolRequestHasNoLocalExecutionBranch() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("invokeExternallyAuthorizedTool("))
    XCTAssertTrue(source.contains("AgentRuntimeProcess.shared.invokeExternalSurfaceTool("))
    XCTAssertFalse(source.contains("handleRealtimeDelegationRequest("))
    XCTAssertFalse(source.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation("))
    XCTAssertFalse(source.contains("agentControlService.executeVoiceTool("))
  }

  func testSpawnAgentUsesKernelRuntimeControlAuthority() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("toolName: name"))
    XCTAssertTrue(source.contains("command.surfaceKind == \"realtime_voice\""))
    XCTAssertFalse(source.contains("pendingVoiceAgentHandoff"))
    XCTAssertFalse(source.contains("Starting a background agent."))
  }

  func testRealtimeHubDoesNotPerformPillMutationBeforeKernelPolicy() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("setDesktopAttentionOverride"))
    XCTAssertFalse(source.contains("userExplicitlyRequestedPillManagement"))
    XCTAssertTrue(source.contains("invokeExternalSurfaceTool("))
  }

  func testRealtimeHubUsesCanonicalVoicePlaybackServiceForLocalSpeechFallbacks() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("AVSpeechSynthesizer"))
    XCTAssertFalse(source.contains("AVSpeechUtterance"))
    XCTAssertFalse(source.contains("AVSpeechSynthesisVoice"))
    XCTAssertFalse(source.contains("private func speak(_ text: String)"))
    XCTAssertTrue(
      source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(reply, lease: lease)"))
    XCTAssertTrue(
      source.contains("FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()"))
    XCTAssertTrue(
      source.contains(
        "acquireVoiceOutput(.selectedVoiceFallback, reason: \"text_no_native_audio\")"))
  }

  func testRealtimeHubAudibleOutputIsLeaseGated() throws {
    let coordinator = VoiceTurnCoordinator()
    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))
    coordinator.send(.transcriptionFinal(turnID: turnID, text: "fixture"))
    guard case .acquired(let native) = coordinator.acquireOutput(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native output should acquire the turn")
    }

    XCTAssertEqual(
      coordinator.acquireOutput(.selectedVoiceFallback, turnID: turnID),
      .denied(active: native))
    XCTAssertEqual(
      coordinator.acquireOutput(.deterministicAgentAck, turnID: turnID),
      .denied(active: native))
    XCTAssertFalse(coordinator.outputSnapshot.providerOutputSuppressed)
  }

  func testRealtimeToolTurnsStayOpenUntilToolResultReturns() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var toolEffectIdentityByTransportKey"))
    XCTAssertTrue(source.contains("private var realtimeToolTurnEpoch = 0"))
    XCTAssertTrue(source.contains("expectedTurnEpoch: Int? = nil"))
    XCTAssertTrue(source.contains("toolEffectIdentityByTransportKey[transportKey] = identity"))
    XCTAssertTrue(
      source.contains("toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch)"))
    XCTAssertTrue(source.contains("toolEffectIdentityByTransportKey.removeValue(forKey: key)"))
    XCTAssertTrue(source.contains("turnEpoch == realtimeToolTurnEpoch"))
    XCTAssertTrue(source.contains("waiting for post-tool continuation"))
    XCTAssertTrue(source.contains("authorizedRealtimeInvocations"))
    XCTAssertTrue(source.contains("private func clearRealtimeToolTracking()"))
    XCTAssertTrue(source.contains("realtimeToolTurnEpoch += 1"))
    XCTAssertGreaterThanOrEqual(
      source.components(separatedBy: "clearRealtimeToolTracking()").count - 1, 4)
    XCTAssertFalse(source.contains("session?.sendToolResult("))
  }

  func testRealtimeDelegationCannotExecuteAfterStaleTurn() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("RealtimeAuthorizedToolOwnership.accepts("))
    XCTAssertTrue(source.contains("RealtimeDeferredToolOwnership.accepts("))
    XCTAssertTrue(source.contains("private func isCurrentToolTurn("))
    XCTAssertTrue(
      source.contains(
        "activeToolIdentity: VoiceTurnCoordinator.shared.activeTurn?.toolEffectIdentities[callID]"
      ))
    XCTAssertFalse(source.contains("AgentDelegationExecutor.shared"))
  }

  func testPermissionToolsCannotOpenSettingsBeforeKernelAuthorization() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("ChatToolExecutor.execute("))
    XCTAssertFalse(source.contains("permissionExecutorRoute("))
    XCTAssertTrue(source.contains("invokeExternalSurfaceTool("))
  }

  func testRealtimeToolUsesFinalTranscriptAsExternalRunPrompt() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("RealtimeExternalRunPromptPolicy.finalizedPrompt("))
    XCTAssertTrue(source.contains("deferredRealtimeToolInvocations.enqueue("))
    XCTAssertTrue(source.contains("resumeDeferredRealtimeToolsIfReady()"))
    XCTAssertTrue(source.contains("deferredRealtimeToolInvocations.revokeAll()"))
    XCTAssertTrue(source.contains("prompt: normalizedPrompt"))
    XCTAssertFalse(source.contains("Realtime voice request"))
    XCTAssertFalse(source.contains("I couldn't confirm the spoken request"))
  }

  func testBargeInReplacementCommitIsDeferredInsteadOfRejected() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("case deferredForReplacement"))
    XCTAssertTrue(source.contains("VoiceTurnCoordinator.shared.send(.hubCommitDeferredForReplacement"))
    XCTAssertTrue(source.contains("VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true"))
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

  func testSpawnAgentDelegatesDirectedProviderAvailabilityToKernel() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("LocalAgentProviderDetector.availability"))
    XCTAssertFalse(source.contains("directed_provider_unavailable"))
    XCTAssertTrue(source.contains("invokeExternallyAuthorizedTool("))
    XCTAssertFalse(source.contains("originSurface: .realtime"))
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
