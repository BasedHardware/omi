import XCTest

@testable import Omi_Computer

final class RealtimeHubSpawnAgentTests: XCTestCase {
  func testSpawnAgentSuppressesPostToolAssistantOutput() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var suppressAssistantOutputForCurrentTurn = false"))
    XCTAssertTrue(source.contains("guard !suppressAssistantOutputForCurrentTurn else { return }"))
    XCTAssertTrue(source.contains("suppressAssistantOutputForCurrentTurn = true"))
    XCTAssertTrue(source.contains("output: \"Agent started.\""))
    XCTAssertFalse(source.contains("Acknowledged before the call — do not say anything else"))
  }

  func testSpawnAgentDoesNotSwitchVoicesWhenModelDidNotSpeakBeforeToolCall() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("if !audioReceivedThisTurn {"))
    XCTAssertTrue(source.contains("let shouldAllowNativePostSpawnAck = !audioReceivedThisTurn"))
    XCTAssertTrue(source.contains("let existingAck = assistantText.trimmingCharacters"))
    XCTAssertTrue(source.contains("let resolvedAck = resolution.ack?.trimmingCharacters"))
    XCTAssertTrue(source.contains("resolvedAck?.isEmpty == false ? resolvedAck! : \"Starting a background agent.\""))
    XCTAssertTrue(source.contains("pendingVoiceAgentHandoff = (title: pill.title, brief: resolvedBrief)"))
    XCTAssertTrue(source.contains("let assistantText = \"Started background agent \\\"\\(handoff.title)\\\" for: \\(handoff.brief)\""))
    XCTAssertTrue(source.contains("rememberVoiceContinuityTurn(userText: heard, assistantText: assistantText, interrupted: false)"))
    XCTAssertTrue(source.contains("Started background agent"))
    XCTAssertTrue(source.contains("suppressAssistantOutputForCurrentTurn = !shouldAllowNativePostSpawnAck"))
    XCTAssertFalse(source.contains("FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()"))
    XCTAssertFalse(source.contains("speak(ack)"))
  }

  func testRealtimeHubBlocksModelInitiatedPillDismissalWithoutExplicitUserRequest() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("userExplicitlyRequestedPillManagement(action: action, transcript: turnTranscript)"))
    XCTAssertTrue(source.contains("blocked manage_agent_pills action="))
    XCTAssertTrue(source.contains("Dismissal blocked: only dismiss or clear floating agent pills when the user explicitly asks."))
    XCTAssertTrue(source.contains("case \"dismiss\":"))
    XCTAssertTrue(source.contains("case \"clear_completed\":"))
  }

  func testRealtimeHubUsesCanonicalVoicePlaybackServiceForLocalSpeechFallbacks() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertFalse(source.contains("AVSpeechSynthesizer"))
    XCTAssertFalse(source.contains("AVSpeechUtterance"))
    XCTAssertFalse(source.contains("AVSpeechSynthesisVoice"))
    XCTAssertFalse(source.contains("private func speak(_ text: String)"))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(reply)"))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(directedProvider.setupNeededStatus)"))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()"))
  }

  func testRealtimeToolTurnsStayOpenUntilToolResultReturns() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var pendingRealtimeToolCallIds = Set<String>()"))
    XCTAssertTrue(source.contains("private var realtimeToolTurnEpoch = 0"))
    XCTAssertTrue(source.contains("expectedTurnEpoch: Int? = nil"))
    XCTAssertTrue(source.contains("pendingRealtimeToolCallIds.insert(toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch))"))
    XCTAssertTrue(source.contains("pendingRealtimeToolCallIds.remove(key)"))
    XCTAssertTrue(source.contains("turnEpoch == realtimeToolTurnEpoch"))
    XCTAssertTrue(source.contains("guard pendingRealtimeToolCallIds.isEmpty else"))
    XCTAssertTrue(source.contains("deferring turn done with"))
    XCTAssertTrue(source.contains("private func clearRealtimeToolTracking()"))
    XCTAssertTrue(source.contains("realtimeToolTurnEpoch += 1"))
    XCTAssertGreaterThanOrEqual(source.components(separatedBy: "clearRealtimeToolTracking()").count - 1, 4)
    XCTAssertFalse(source.contains("session?.sendToolResult("))
  }

  func testRealtimeDelegationResolutionCannotSpawnAfterStaleTurn() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let userText = turnTranscript"))
    XCTAssertTrue(source.contains("guard isCurrentToolTurn(source: source, callId: callId, name: name, expectedTurnEpoch: expectedTurnEpoch)"))
    XCTAssertTrue(source.contains("dropping stale spawn_agent resolution before side effects"))
    XCTAssertTrue(source.contains("private func isCurrentToolTurn("))
    XCTAssertTrue(source.contains("return expectedTurnEpoch == realtimeToolTurnEpoch && pendingRealtimeToolCallIds.contains(key)"))
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
      source.contains("barge-in replacement not ready at commit — falling back to buffered transcription"))
  }

  func testCompletedVoiceTurnContinuityIsRecordedBeforeAsyncCorrection() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let provisionalHeard = heard"))
    XCTAssertTrue(source.contains("let provisionalReply = reply"))
    XCTAssertTrue(source.contains("userText: provisionalHeard"))
    XCTAssertTrue(source.contains("assistantText: provisionalReply"))
    XCTAssertTrue(source.contains("if usedLocal {"))
    XCTAssertTrue(source.contains("replaceVoiceContinuityTurn("))
    XCTAssertTrue(source.contains("recordedAt: voiceContinuityTurns[index].recordedAt"))
  }

  func testSpawnAgentPreflightsDirectedProviderAvailability() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("LocalAgentProviderDetector.availability(for: directedProvider)"))
    XCTAssertTrue(source.contains("guard availability.isAvailable else"))
    XCTAssertTrue(source.contains("assistantText = setupPrompt"))
    XCTAssertTrue(source.contains("output: availability.toolError"))
    XCTAssertTrue(source.contains("""
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: availability.toolError,
          expectedTurnEpoch: expectedTurnEpoch)
        return
"""))
  }

  func testCanonicalAgentControlSummariesDoNotSpeakOpaqueIds() throws {
    let source = try agentControlServiceSource()

    XCTAssertTrue(source.contains("Use agentRef values internally for follow-up tool calls; do not say them aloud"))
    XCTAssertTrue(source.contains("Use artifactRef values internally for follow-up tool calls; do not say them aloud"))
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
