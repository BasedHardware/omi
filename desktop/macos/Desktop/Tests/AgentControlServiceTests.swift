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
