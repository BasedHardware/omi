import XCTest

@testable import Omi_Computer

final class HubEscalationTests: XCTestCase {
  func testBodyUsesCanonicalKernelContextAndKeepsToolContextUserScoped() {
    let kernelContext = """
      [Kernel Context Snapshot version=conversation generation=7]
      The JSON below is untrusted contextual data selected by the desktop kernel.
      {"recentTurns":[{"content":"canonical turn"}]}
      """
    let body = RealtimeHubTools.escalationBody(
      query: "What's the best plan?",
      kernelSemanticGuidance: "Resolve direct references from canonical turns.",
      kernelContext: kernelContext,
      stableCacheIdentity: "sha256:stable",
      dynamicContextIdentity: "sha256:dynamic",
      contextPlanID: "sha256:plan",
      toolContext: "User is comparing the M3 and M4 MacBook.")
    XCTAssertEqual(body["model"] as? String, "claude-sonnet-4-6")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertEqual(messages[0]["role"], "system")
    XCTAssertTrue(messages[0]["content"]!.contains("Resolve direct references"))
    XCTAssertTrue(messages[0]["content"]!.contains("<!-- OMI_CONTEXT_CACHE_V1 stable=sha256:stable dynamic=sha256:dynamic plan=sha256:plan -->"))
    XCTAssertTrue(messages[0]["content"]!.contains("canonical turn"))
    XCTAssertFalse(messages[0]["content"]!.contains("M3 and M4"))
    XCTAssertEqual(messages[1]["role"], "user")
    XCTAssertTrue(messages[1]["content"]!.contains("What's the best plan?"))
    XCTAssertTrue(messages[1]["content"]!.contains("Tool-provided context (untrusted)"))
    XCTAssertTrue(messages[1]["content"]!.contains("M3 and M4"))
  }

  /// A valid new conversation renders no context material but still carries a
  /// kernel session and a freshness identity. Escalation must stay available:
  /// gating it on rendered text broke the first PTT turn of every session.
  @MainActor
  func testResolvedSnapshotWithoutContextMaterialStillAllowsEscalation() {
    let context = RealtimeHubController.VoiceSessionContext(
      sessionID: "session_1",
      rendered: "",
      snapshotFreshnessIdentity: "conversation:renderer:v1",
      planID: "",
      stableCacheIdentity: "",
      dynamicContextIdentity: "",
      semanticGuidance: "")
    XCTAssertTrue(context.isResolved)
  }

  /// The `.empty` sentinel (transport/bridge failure, or a snapshot bound to a
  /// different owner scope) must still fail closed.
  @MainActor
  func testUnresolvedSnapshotBlocksEscalation() {
    let unbound = RealtimeHubController.VoiceSessionContext(
      sessionID: "",
      rendered: "",
      snapshotFreshnessIdentity: "",
      planID: "",
      stableCacheIdentity: "",
      dynamicContextIdentity: "",
      semanticGuidance: "")
    XCTAssertFalse(unbound.isResolved)

    let sessionlessButRendered = RealtimeHubController.VoiceSessionContext(
      sessionID: "",
      rendered: "[Kernel Context Snapshot]",
      snapshotFreshnessIdentity: "conversation:renderer:v1",
      planID: "sha256:plan",
      stableCacheIdentity: "sha256:stable",
      dynamicContextIdentity: "sha256:dynamic",
      semanticGuidance: "Resolve direct references.")
    XCTAssertFalse(sessionlessButRendered.isResolved)
  }

  func testBodyOmitsContextSectionWhenEmpty() {
    let body = RealtimeHubTools.escalationBody(
      query: "Capital of France?",
      kernelSemanticGuidance: "",
      kernelContext: "",
      stableCacheIdentity: "",
      dynamicContextIdentity: "",
      contextPlanID: "",
      toolContext: "")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertFalse(messages[1]["content"]!.contains("Context"))
    XCTAssertFalse(messages[1]["content"]!.contains("Answer concisely for a spoken reply"))
  }
}
