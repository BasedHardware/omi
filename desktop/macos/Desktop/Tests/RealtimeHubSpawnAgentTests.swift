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
