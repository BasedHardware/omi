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

  func testSpawnAgentProvidesLocalAckWhenModelDidNotSpeakBeforeToolCall() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("if !audioReceivedThisTurn {"))
    XCTAssertTrue(source.contains("let existingAck = assistantText.trimmingCharacters"))
    XCTAssertTrue(source.contains("let ack = existingAck.isEmpty ? \"Starting a background agent.\" : existingAck"))
    XCTAssertTrue(source.contains("speak(ack)"))
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
            output: availability.toolError)
          return
"""))
  }

  func testSetupAgentProviderUsesDeterministicInstallerNotAnAgentPill() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("case .setupAgentProvider:"))
    // Idempotent already-installed path — no dialog, no reinstall.
    XCTAssertTrue(source.contains("is already installed and ready — no setup needed."))
    // The deterministic installer (native confirm dialog + Process) is the
    // code-level consent gate; the hub never spawns an installer agent pill.
    XCTAssertTrue(source.contains("LocalAgentProviderInstaller.shared.beginInstall(for: provider)"))
    XCTAssertFalse(source.contains("spawnInstallAssistPill"))
    // The tool result returns immediately — the voice turn never blocks on
    // the dialog; the ack points the user at it.
    XCTAssertTrue(source.contains("Please confirm the \\(provider.displayName) install in the dialog on screen."))
    XCTAssertTrue(source.contains("output: installMessage)"))
  }

  func testForceRewarmIsIdleGatedIncludingBargeInReplacement() throws {
    let source = try realtimeHubControllerSource()

    // Shared idle-only re-warm used by system wake and provider-change
    // refresh; the guard also skips an in-flight barge-in replacement.
    XCTAssertTrue(source.contains("private func forceRewarm(reason: String) {"))
    XCTAssertTrue(
      source.contains("guard session != nil, !responding, !minting, !bargeInReplacementInFlight else { return }"))
    XCTAssertTrue(source.contains("forceRewarm(reason: \"system woke (dropping possibly-stale socket)\")"))
    XCTAssertTrue(source.contains("forceRewarm(reason: \"local agent provider availability changed\")"))
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
