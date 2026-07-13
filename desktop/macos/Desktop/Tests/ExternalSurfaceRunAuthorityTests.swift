import XCTest

@testable import Omi_Computer

final class ExternalSurfaceRunAuthorityTests: XCTestCase {
  private let binding = ExternalSurfaceRunBinding(
    ownerID: "owner-1",
    sessionID: "session-1",
    turnID: "voice-turn-7",
    runID: "run-1",
    attemptID: "attempt-1",
    duplicate: false
  )

  func testBeginWireCarriesCorrelationButNoCapabilityToken() {
    let message = AgentRuntimeProcess.externalSurfaceRunBeginWireMessage(
      clientId: "realtime",
      requestId: "request-1",
      ownerId: binding.ownerID,
      sessionId: binding.sessionID,
      turnId: binding.turnID,
      prompt: "What did I do today?",
      mode: .act
    )

    XCTAssertEqual(message["type"] as? String, "external_surface_run_begin")
    XCTAssertEqual(message["protocolVersion"] as? Int, 2)
    XCTAssertEqual(message["turnId"] as? String, binding.turnID)
    XCTAssertEqual(message["mode"] as? String, "act")
    XCTAssertNil(message["capabilityId"])
    XCTAssertNil(message["capabilityToken"])
  }

  func testToolWireIsFencedToPersistedRunAttemptAndInvocation() {
    let message = AgentRuntimeProcess.externalSurfaceToolInvokeWireMessage(
      clientId: "realtime",
      requestId: "request-2",
      binding: binding,
      invocationId: "provider-call-1",
      toolName: "get_memories",
      input: ["limit": 15]
    )

    XCTAssertEqual(message["type"] as? String, "external_surface_tool_invoke")
    XCTAssertEqual(message["ownerId"] as? String, binding.ownerID)
    XCTAssertEqual(message["sessionId"] as? String, binding.sessionID)
    XCTAssertEqual(message["runId"] as? String, binding.runID)
    XCTAssertEqual(message["attemptId"] as? String, binding.attemptID)
    XCTAssertEqual(message["invocationId"] as? String, "provider-call-1")
    XCTAssertEqual((message["input"] as? [String: Any])?["limit"] as? Int, 15)
  }

  func testCompleteWireUsesTerminalStatusAndBoundedFailureCode() {
    let message = AgentRuntimeProcess.externalSurfaceRunCompleteWireMessage(
      clientId: "realtime",
      requestId: "request-3",
      binding: binding,
      terminalStatus: .failed,
      errorCode: "provider_disconnected"
    )

    XCTAssertEqual(message["type"] as? String, "external_surface_run_complete")
    XCTAssertEqual(message["terminalStatus"] as? String, "failed")
    XCTAssertEqual(message["errorCode"] as? String, "provider_disconnected")
  }

  func testStructuredErrorUsesCodeWithoutTrustingDisplayMessage() {
    let error = ExternalSurfaceAuthorityError.from([
      "ok": false,
      "error": ["code": "stale_attempt", "message": "untrusted detail"],
    ], fallback: "fallback")
    XCTAssertEqual(error.code, "stale_attempt")
    XCTAssertFalse(error.localizedDescription.contains("untrusted detail"))
  }
}
