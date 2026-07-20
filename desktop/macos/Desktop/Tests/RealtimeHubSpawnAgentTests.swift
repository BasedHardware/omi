import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

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

    func testCanonicalSpawnReceiptKeepsProviderContinuationInNativeVoiceLane() {
      XCTAssertEqual(
        RealtimeProviderOutputPresentationPolicy.decide(
          screenGroundingState: .inactive,
          reducerOutputSuppressed: false),
        .present)
      XCTAssertEqual(
        RealtimeProviderTurnDoneDisposition.decide(
          pendingToolCount: 0,
          postToolContinuationRequired: true),
        .requestPostToolContinuation)
    }

    func testCanonicalSpawnReceiptNeverRedrivesAfterExpectedSessionRefresh() {
      XCTAssertFalse(
        RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
          sessionChanged: true,
          hasCanonicalSpawnReceipt: true))
      XCTAssertTrue(
        RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
          sessionChanged: true,
          hasCanonicalSpawnReceipt: false))
      XCTAssertFalse(
        RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
          sessionChanged: false,
          hasCanonicalSpawnReceipt: false))
    }

    func testSpawnJournalReceiptAcceptsOnlyCanonicalTurnIdentity() throws {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
      let payload = canonicalSpawnPayload(continuityKey: continuityKey)
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
          assistantText: "I started a background agent for that.",
          pillProjection: nil))
      XCTAssertNil(
        RealtimeSpawnJournalReceipt.parse(
          output: output,
          expectedContinuityKey: "voice:00000000-0000-0000-0000-000000000000"))
    }

    func testSpawnJournalReceiptProjectsTheKernelAcceptedChildRun() throws {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009516"
      let pillID = UUID(uuidString: "00000000-0000-0000-0000-000000000123")!
      let payload = canonicalSpawnPayload(
        continuityKey: continuityKey,
        pillID: pillID,
        title: "Research models",
        objective: "Research the latest models")
      let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
      let output = try XCTUnwrap(String(data: data, encoding: .utf8))

      let receipt = try XCTUnwrap(
        RealtimeSpawnJournalReceipt.parse(output: output, expectedContinuityKey: continuityKey))
      XCTAssertEqual(
        receipt.pillProjection,
        RealtimeSpawnJournalReceipt.PillProjection(
          pillID: pillID,
          sessionID: "session-child",
          runID: "run-child",
          attemptID: "attempt-child",
          provider: "hermes",
          title: "Research models",
          objective: "Research the latest models"))
    }

    func testSpawnJournalReceiptRejectsTamperedStableIdentity() throws {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
      var payload = canonicalSpawnPayload(continuityKey: continuityKey)
      var receipt = try XCTUnwrap(payload["journalReceipt"] as? [String: Any])
      receipt["userTurnId"] = "turn_tampered"
      payload["journalReceipt"] = receipt
      let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
      let output = try XCTUnwrap(String(data: data, encoding: .utf8))

      XCTAssertNil(
        RealtimeSpawnJournalReceipt.parse(
          output: output, expectedContinuityKey: continuityKey))
    }

    func testSpawnJournalReceiptRejectsMissingOrMismatchedChildLifecycle() throws {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009518"
      var missingChild = canonicalSpawnPayload(continuityKey: continuityKey)
      missingChild.removeValue(forKey: "child")
      let missingData = try JSONSerialization.data(withJSONObject: missingChild, options: [.sortedKeys])
      XCTAssertNil(
        RealtimeSpawnJournalReceipt.parse(
          output: try XCTUnwrap(String(data: missingData, encoding: .utf8)),
          expectedContinuityKey: continuityKey))

      var mismatched = canonicalSpawnPayload(continuityKey: continuityKey)
      var providerResult = try XCTUnwrap(mismatched["providerResult"] as? [String: Any])
      providerResult["semanticDigest"] = "different-semantic-child"
      mismatched["providerResult"] = providerResult
      let mismatchData = try JSONSerialization.data(withJSONObject: mismatched, options: [.sortedKeys])
      XCTAssertNil(
        RealtimeSpawnJournalReceipt.parse(
          output: try XCTUnwrap(String(data: mismatchData, encoding: .utf8)),
          expectedContinuityKey: continuityKey))
    }

    func testRejectedSpawnResultCannotBeTreatedAsAnAcceptedVoiceTurn() {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009517"
      let rejected = #"{"ok":false,"error":{"code":"provider_boundary_rejected","message":"not allowed"}}"#

      XCTAssertEqual(
        RealtimeSpawnAgentToolOutcome.classify(
          output: rejected,
          expectedContinuityKey: continuityKey),
        .rejected)
    }

    func testDirectedProviderSetupNeededIsTypedAndCannotCreateAPill() {
      let continuityKey = "voice:00000000-0000-0000-0000-000000009519"
      let setupNeeded =
        #"{"ok":false,"error":{"code":"provider_setup_needed","provider":"openclaw","message":"OpenClaw needs setup"}}"#

      XCTAssertEqual(
        RealtimeSpawnAgentToolOutcome.classify(
          output: setupNeeded,
          expectedContinuityKey: continuityKey),
        .setupNeeded(.openclaw))
    }

    func testSharedSpawnReceiptFixturesAcceptValidAndRejectMalformed() throws {
      let fixtureDir = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("agent/fixtures/spawn-receipt/v1")
      let names = try FileManager.default.contentsOfDirectory(atPath: fixtureDir.path)
        .filter { $0.hasSuffix(".json") }
        .sorted()
      XCTAssertTrue(names.contains("valid-running.json"))
      XCTAssertTrue(names.contains { $0.hasPrefix("malformed-") })

      for name in names {
        let data = try Data(contentsOf: fixtureDir.appendingPathComponent(name))
        let output = try XCTUnwrap(String(data: data, encoding: .utf8))
        let payload = try XCTUnwrap(
          JSONSerialization.jsonObject(with: data) as? [String: Any])
        let continuityKey =
          (payload["journalReceipt"] as? [String: Any])?["continuityKey"] as? String
          ?? "voice:00000000-0000-0000-0000-00000000f001"
        let parsed = RealtimeSpawnJournalReceipt.parse(
          output: output,
          expectedContinuityKey: continuityKey)
        if name.hasPrefix("valid-") {
          let receipt = try XCTUnwrap(parsed, "valid fixture \(name) must parse")
          XCTAssertEqual(receipt.continuityKey, continuityKey)
          XCTAssertEqual(
            receipt.userTurnID,
            KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user"))
          XCTAssertEqual(
            receipt.assistantTurnID,
            KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "assistant"))
          XCTAssertFalse(receipt.assistantText.isEmpty)
        } else {
          XCTAssertNil(parsed, "malformed fixture \(name) must be rejected")
        }
      }
    }

    private func canonicalSpawnPayload(
      continuityKey: String,
      pillID: UUID? = nil,
      title: String = "Background agent",
      objective: String = "Research the latest models"
    ) -> [String: Any] {
      let childLifecycle: [String: Any] = [
        "state": "running",
        "attemptState": "running",
        "revision": 2,
        "adapterId": "hermes",
        "updatedAtMs": 1_720_000_000_000 as NSNumber,
      ]
      var child: [String: Any] = [
        "sessionId": "session-child",
        "runId": "run-child",
        "attemptId": "attempt-child",
        "title": title,
        "objective": objective,
        "provider": "hermes",
        "lifecycle": childLifecycle,
      ]
      if let pillID { child["pillId"] = pillID.uuidString }
      let semanticDigest = "semantic-child-digest"
      return [
        "schemaVersion": 1,
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
        "child": child,
        "semanticDigest": semanticDigest,
        "providerResult": [
          "schemaVersion": 1,
          "ok": true,
          "code": "spawn_started",
          "message": "Background agent started.",
          "child": [
            "sessionId": "session-child",
            "runId": "run-child",
            "attemptId": "attempt-child",
            "state": "running",
            "attemptState": "running",
            "revision": 2,
            "adapterId": "hermes",
            "updatedAtMs": 1_720_000_000_000 as NSNumber,
          ],
          "semanticDigest": semanticDigest,
        ],
      ]
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
      let toolAuthoritySource = try realtimeToolAuthoritySource()

      XCTAssertTrue(source.contains("toolName: name"))
      XCTAssertTrue(toolAuthoritySource.contains("command.surfaceKind == \"realtime_voice\""))
      XCTAssertFalse(source.contains("pendingVoiceAgentHandoff"))
      XCTAssertFalse(source.contains("Starting a background agent."))
    }

    func testRealtimeHubDoesNotPerformPillMutationBeforeKernelPolicy() throws {
      let source = try realtimeHubControllerSource()

      XCTAssertFalse(source.contains("setDesktopAttentionOverride"))
      XCTAssertFalse(source.contains("userExplicitlyRequestedPillManagement"))
      XCTAssertTrue(source.contains("invokeExternalSurfaceTool("))
    }

    func testRealtimeAcceptedSpawnProjectsPillOnlyAfterTheCurrentTurnFence() throws {
      // omi-test-quality: source-inspection -- static contract: an accepted PTT spawn can project only after the same current-turn fence used for its tool result.
      let source = try realtimeHubControllerSource()

      let outputCall = try XCTUnwrap(
        source.range(of: "let output = try await AgentRuntimeProcess.shared.invokeExternalSurfaceTool("))
      let currentFence = try XCTUnwrap(
        source.range(
          of: #"guard\s+self\.isCurrentToolTurn\("#,
          options: .regularExpression,
          range: outputCall.upperBound..<source.endIndex))
      let pillProjection = try XCTUnwrap(
        source.range(
          of: "AgentPillsManager.shared.upsertSpawnedPill(", range: currentFence.upperBound..<source.endIndex))
      XCTAssertLessThan(outputCall.lowerBound, currentFence.lowerBound)
      XCTAssertLessThan(currentFence.lowerBound, pillProjection.lowerBound)
      XCTAssertTrue(
        source.contains("producingJournalSurface: FloatingControlBarManager.shared.realtimeVoiceSurfaceReference()"))
    }

    func testRealtimeHubUsesCanonicalVoicePlaybackServiceForLocalSpeechFallbacks() throws {
      // omi-test-quality: source-inspection -- static contract: the realtime controller must not
      // reintroduce a local TTS takeover for an accepted background-agent receipt.
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
      // The spawn receipt persists the canonical lifecycle fact, but only the
      // native provider continuation may answer the same PTT turn aloud.
      XCTAssertTrue(source.contains("preserving native provider continuation"))
      XCTAssertFalse(source.contains("playCanonicalSpawnAcknowledgement"))
      XCTAssertFalse(source.contains("kind: .spawnReceipt"))
      XCTAssertTrue(source.contains("RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive("))
      XCTAssertTrue(source.contains("postToolContinuationRequired"))
    }

    func testRealtimeHubAudibleOutputIsLeaseGated() throws {
      let coordinator = VoiceTurnCoordinator()
      let turnID = coordinator.begin(intent: .hold)
      coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
      coordinator.publish(.finalize(turnID: turnID))
      coordinator.publish(.transcriptionStarted(turnID: turnID))
      coordinator.publish(.transcriptionFinal(turnID: turnID, text: "fixture"))
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

      XCTAssertTrue(source.contains("var toolEffectIdentityByTransportKey"))
      // The screen-receipt extension shares this epoch fence after the visual receipt refactor.
      XCTAssertTrue(source.contains("var realtimeToolTurnEpoch = 0"))
      XCTAssertTrue(source.contains("expectedTurnEpoch: Int? = nil"))
      XCTAssertTrue(source.contains("toolEffectIdentityByTransportKey[transportKey] = toolIdentity"))
      XCTAssertTrue(
        source.contains("toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch)"))
      XCTAssertTrue(source.contains("toolEffectIdentityByTransportKey.removeValue(forKey: key)"))
      XCTAssertTrue(source.contains("turnEpoch == realtimeToolTurnEpoch"))
      XCTAssertTrue(source.contains("waiting for provider tool delivery"))
      XCTAssertTrue(source.contains("authorizedRealtimeInvocations"))
      XCTAssertTrue(source.contains("func clearRealtimeToolTracking()"))
      XCTAssertTrue(source.contains("realtimeToolTurnEpoch += 1"))
      XCTAssertGreaterThanOrEqual(
        source.components(separatedBy: "clearRealtimeToolTracking()").count - 1, 4)
      XCTAssertFalse(source.contains("session?.sendToolResult("))
    }

    func testRealtimeDelegationCannotExecuteAfterStaleTurn() throws {
      // omi-test-quality: source-inspection -- static contract: all realtime tool paths must retain the shared turn fence.
      let source = try realtimeHubControllerSource()

      XCTAssertTrue(source.contains("RealtimeAuthorizedToolOwnership.accepts("))
      XCTAssertTrue(source.contains("RealtimeToolTurnOwnership.accepts("))
      XCTAssertTrue(source.contains("func isCurrentToolTurn("))
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

    func testRealtimeToolUsesAuthorizedFallbackWhenProviderTranscriptIsUnavailable() throws {
      // omi-test-quality: source-inspection -- static contract: the realtime tool path must not reintroduce a transcript/tool circular wait.
      let source = try realtimeHubControllerSource()
      let toolAuthoritySource = try realtimeToolAuthoritySource()

      XCTAssertTrue(source.contains("RealtimeExternalRunPromptPolicy.promptForAuthorizedTool("))
      XCTAssertTrue(source.contains("authorizedToolFallback"))
      XCTAssertFalse(source.contains("deferredRealtimeToolInvocations.enqueue("))
      XCTAssertFalse(source.contains("resumeDeferredRealtimeToolsIfReady()"))
      XCTAssertTrue(source.contains("prompt: normalizedPrompt"))
      XCTAssertTrue(toolAuthoritySource.contains("Execute only that separately authorized invocation"))
      XCTAssertFalse(source.contains("I couldn't confirm the spoken request"))
    }

    func testBargeInReplacementCommitIsDeferredInsteadOfRejected() throws {
      let source = try realtimeHubControllerSource()
      let sessionPoliciesSource = try realtimeHubSessionPoliciesSource()

      XCTAssertTrue(sessionPoliciesSource.contains("case deferredForReplacement"))
      XCTAssertTrue(source.contains("VoiceTurnCoordinator.shared.publish(.hubCommitDeferredForReplacement"))
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
      try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
    }

    private func realtimeToolAuthoritySource() throws -> String {
      let sourceURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/RealtimeToolAuthority.swift")
      // omi-test-quality: source-inspection -- static contract: extracted policy ownership helper
      return try String(contentsOf: sourceURL, encoding: .utf8)
    }

    private func realtimeHubSessionPoliciesSource() throws -> String {
      let sourceURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubSessionPolicies.swift")
      // omi-test-quality: source-inspection -- static contract: extracted policy ownership helper
      return try String(contentsOf: sourceURL, encoding: .utf8)
    }

    private func agentControlServiceSource() throws -> String {
      let sourceURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/Chat/AgentControlService.swift")
      // omi-test-quality: source-inspection -- static contract: forbidden-path ratchet helper
      return try String(contentsOf: sourceURL, encoding: .utf8)
    }
  }
#endif
