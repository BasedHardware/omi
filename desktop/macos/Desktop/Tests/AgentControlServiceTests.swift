import XCTest

@testable import Omi_Computer

@MainActor
final class AgentControlServiceTests: XCTestCase {
  func testSessionSummaryUsesVoiceHandlesInsteadOfCanonicalIds() {
    let service = AgentControlService()
    let raw = """
      {"ok":true,"sessions":[{"session":{"omiSessionId":"session_123","title":"Draft launch note","status":"open","surfaceKind":"main_chat"},"latestRun":{"runId":"run_123","status":"running","mode":"act"},"latestAttempt":{"attemptId":"attempt_123"}}]}
      """

    let summary = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: raw)

    XCTAssertTrue(summary.contains("agent_1"))
    XCTAssertFalse(summary.contains("session_123"))
    XCTAssertFalse(summary.contains("run_123"))
    XCTAssertFalse(summary.contains("attempt_123"))
  }

  func testSessionSummaryPrefersActiveRunForVoiceHandles() {
    let service = AgentControlService()
    let raw = """
      {"ok":true,"sessions":[{"session":{"omiSessionId":"session_123","title":"Draft launch note","status":"open"},"latestRun":{"runId":"run_terminal","status":"completed","mode":"ask"},"activeRun":{"runId":"run_active","status":"running","mode":"act"},"latestAttempt":{"attemptId":"attempt_terminal"},"activeAttempt":{"attemptId":"attempt_active"}}]}
      """

    let summary = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: raw)
    let resolved = service.resolveVoiceHandles(in: ["agentRef": "agent_1"])

    XCTAssertTrue(summary.contains("running"))
    XCTAssertTrue(summary.contains("mode act"))
    XCTAssertFalse(summary.contains("completed"))
    XCTAssertEqual(resolved["runId"] as? String, "run_active")
    XCTAssertEqual(resolved["attemptId"] as? String, "attempt_active")
  }

  func testCancellationSummaryDoesNotExposeRunId() {
    let service = AgentControlService()
    let raw = """
      {"ok":true,"cancellation":{"accepted":true,"dispatchAttempted":true,"adapterAcknowledged":false},"run":{"runId":"run_123","status":"cancelling"}}
      """

    let summary = service.summarizeVoiceResult(name: HubTool.cancelAgentRun.rawValue, raw: raw)

    XCTAssertTrue(summary.contains("accepted=true"))
    XCTAssertTrue(summary.contains("dispatched=true"))
    XCTAssertTrue(summary.contains("acknowledged=false"))
    XCTAssertTrue(summary.contains("cancelling"))
    XCTAssertFalse(summary.contains("run_123"))
  }

  func testArtifactSummaryUsesVoiceHandlesInsteadOfCanonicalIds() {
    let service = AgentControlService()
    let raw = """
      {"ok":true,"artifacts":[{"artifactId":"artifact_123","role":"result","lifecycleState":"retained"}]}
      """

    let summary = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: raw)

    XCTAssertTrue(summary.contains("artifact_1"))
    XCTAssertFalse(summary.contains("artifact_123"))
  }

  func testEmptySessionSummaryClearsStaleVoiceHandles() {
    let service = AgentControlService()
    let withSession = """
      {"ok":true,"sessions":[{"session":{"omiSessionId":"session_123","title":"Draft launch note"},"latestRun":{"runId":"run_123"},"latestAttempt":{"attemptId":"attempt_123"}}]}
      """

    _ = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: withSession)
    XCTAssertEqual(service.resolveVoiceHandles(in: ["agentRef": "agent_1"])["sessionId"] as? String, "session_123")

    _ = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: "{\"ok\":true,\"sessions\":[]}")
    let resolved = service.resolveVoiceHandles(in: ["agentRef": "agent_1"])

    XCTAssertNil(resolved["sessionId"])
    XCTAssertNil(resolved["runId"])
    XCTAssertNil(resolved["attemptId"])
  }

  func testListSessionFailureClearsStaleVoiceHandles() {
    let service = AgentControlService()
    let withSession = """
      {"ok":true,"sessions":[{"session":{"omiSessionId":"session_123","title":"Draft launch note"},"latestRun":{"runId":"run_123"},"latestAttempt":{"attemptId":"attempt_123"}}]}
      """

    _ = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: withSession)
    _ = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: "{\"ok\":false,\"error\":{\"message\":\"boom\"}}")
    let resolved = service.resolveVoiceHandles(in: ["agentRef": "agent_1"])

    XCTAssertNil(resolved["sessionId"])
    XCTAssertNil(resolved["runId"])
    XCTAssertNil(resolved["attemptId"])
  }

  func testEmptyArtifactSummaryClearsStaleVoiceHandles() {
    let service = AgentControlService()
    let withArtifact = """
      {"ok":true,"artifacts":[{"artifactId":"artifact_123","role":"result","lifecycleState":"retained"}]}
      """

    _ = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: withArtifact)
    XCTAssertEqual(service.resolveVoiceHandles(in: ["artifactRef": "artifact_1"])["artifactId"] as? String, "artifact_123")

    _ = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: "{\"ok\":true,\"artifacts\":[]}")
    let resolved = service.resolveVoiceHandles(in: ["artifactRef": "artifact_1"])

    XCTAssertNil(resolved["artifactId"])
  }

  func testArtifactInspectionFailureClearsStaleVoiceHandles() {
    let service = AgentControlService()
    let withArtifact = """
      {"ok":true,"artifacts":[{"artifactId":"artifact_123","role":"result","lifecycleState":"retained"}]}
      """

    _ = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: withArtifact)
    _ = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: "{\"ok\":false,\"error\":{\"message\":\"boom\"}}")
    let resolved = service.resolveVoiceHandles(in: ["artifactRef": "artifact_1"])

    XCTAssertNil(resolved["artifactId"])
  }

  func testFailureResponsesClearAllStaleVoiceHandles() {
    let service = AgentControlService()
    let withSession = """
      {"ok":true,"sessions":[{"session":{"omiSessionId":"session_123","title":"Draft launch note"},"latestRun":{"runId":"run_123"},"latestAttempt":{"attemptId":"attempt_123"}}]}
      """
    let withArtifact = """
      {"ok":true,"artifacts":[{"artifactId":"artifact_123","role":"result","lifecycleState":"retained"}]}
      """
    let failingToolNames = [
      HubTool.getAgentRun.rawValue,
      HubTool.cancelAgentRun.rawValue,
      HubTool.updateAgentArtifactLifecycle.rawValue,
    ]

    for toolName in failingToolNames {
      _ = service.summarizeVoiceResult(name: HubTool.listAgentSessions.rawValue, raw: withSession)
      _ = service.summarizeVoiceResult(name: HubTool.inspectAgentArtifacts.rawValue, raw: withArtifact)
      _ = service.summarizeVoiceResult(name: toolName, raw: "{\"ok\":false,\"error\":{\"message\":\"boom\"}}")

      XCTAssertNil(service.resolveVoiceHandles(in: ["agentRef": "agent_1"])["sessionId"], toolName)
      XCTAssertNil(service.resolveVoiceHandles(in: ["artifactRef": "artifact_1"])["artifactId"], toolName)
    }
  }

  func testErrorSummaryDoesNotExposeRawCanonicalIds() {
    let service = AgentControlService()
    let raw = """
      {"ok":false,"error":{"code":"control_tool_failed","message":"Run run_123 does not belong to session session_123"}}
      """

    let summary = service.summarizeVoiceResult(name: "get_agent_run", raw: raw)

    XCTAssertTrue(summary.contains("Agent control failed"))
    XCTAssertFalse(summary.contains("run_123"))
    XCTAssertFalse(summary.contains("session_123"))
  }
}
