import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class HubEscalationTests: XCTestCase {
  func testSlowToolAcknowledgementsUseNaturalUserFacingLanguage() throws {
    XCTAssertEqual(
      RealtimeSlowToolAcknowledgementKind(toolName: HubTool.thinkDeeper.rawValue),
      .deeperThinking)
    XCTAssertEqual(
      RealtimeSlowToolAcknowledgementKind(toolName: HubTool.webSearch.rawValue),
      .publicWebSearch)
    XCTAssertNil(RealtimeSlowToolAcknowledgementKind(toolName: HubTool.getTasks.rawValue))

    let phrases = RealtimeSlowToolAcknowledgementKind.allCases.flatMap(\.phrases)
    XCTAssertGreaterThanOrEqual(phrases.count, 8)
    for phrase in phrases {
      let normalized = phrase.lowercased()
      XCTAssertFalse(normalized.contains("higher model"))
      XCTAssertFalse(normalized.contains("another model"))
      XCTAssertFalse(normalized.contains("send that over"))
      XCTAssertFalse(normalized.contains("delegate"))
    }
  }

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

  func testPublicWebPromptIsSpeakableAndExcludesPrivateToolContext() {
    let prompt = RealtimeHubTools.publicWebSearchPrompt(
      query: "What is the weather in New York right now?")

    XCTAssertTrue(prompt.hasPrefix("Search the live public web before answering this request."))
    XCTAssertTrue(prompt.contains("weather in New York right now"))
    XCTAssertTrue(prompt.contains("one to four concise"))
    XCTAssertTrue(prompt.contains("Name the source"))
    XCTAssertFalse(prompt.contains("Tool-provided context"))
  }
}
