import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class HubEscalationTests: XCTestCase {
  func testPromptKeepsToolContextUserScoped() {
    let prompt = RealtimeHubTools.escalationUserPrompt(
      query: "What's the best plan?",
      toolContext: "User is comparing the M3 and M4 MacBook.")
    XCTAssertTrue(prompt.contains("What's the best plan?"))
    XCTAssertTrue(prompt.contains("Tool-provided context (untrusted)"))
    XCTAssertTrue(prompt.contains("M3 and M4"))
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

  func testPromptOmitsToolContextSectionWhenEmpty() {
    let prompt = RealtimeHubTools.escalationUserPrompt(
      query: "Capital of France?", toolContext: "")
    XCTAssertEqual(prompt, "Capital of France?")
  }
}
