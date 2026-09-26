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
    XCTAssertNil(
      RealtimeSlowToolAcknowledgementKind(toolName: HubTool.recordInterjectFeedback.rawValue),
      "Interject classification must not play a canned ack")

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

    // The opening sentence, matched on its two load-bearing halves rather than
    // as one exact string. Pinning the whole sentence made this assertion a
    // tripwire for adverbs: `bce354d767` inserted "thoroughly" between them and
    // reddened main without changing anything this test is about.
    let opening = prompt.prefix(while: { $0 != "." })
    XCTAssertTrue(
      opening.hasPrefix("Search the live public web"),
      "the prompt must open by directing a live public web search, not a model recall")
    XCTAssertTrue(
      opening.contains("before answering this request"),
      "the search must precede the answer, not decorate it")
    XCTAssertTrue(prompt.contains("weather in New York right now"))
    XCTAssertTrue(prompt.contains("one to four concise"))
    XCTAssertTrue(prompt.contains("Name the source"))
    XCTAssertFalse(prompt.contains("Tool-provided context"))
  }
}

final class HubThinkingEscalationBodyTests: XCTestCase {
  private func makeBody(
    thinkingLevel: RealtimeHubTools.EscalationThinkingLevel = .normal,
    screenJPEGs: [Data] = []
  ) -> [String: Any] {
    RealtimeHubTools.escalationBody(
      query: "What's the answer to this riddle?",
      kernelSemanticGuidance: "Resolve direct references.",
      kernelContext: "[Kernel Context Snapshot]",
      stableCacheIdentity: "sha256:stable",
      dynamicContextIdentity: "sha256:dynamic",
      contextPlanID: "sha256:plan",
      toolContext: "The user is looking at a puzzle page.",
      screenContext: nil,
      thinkingLevel: thinkingLevel,
      screenJPEGs: screenJPEGs)
  }

  /// The default escalation posts to the managed Luna thinking lane at high
  /// effort, text-only when no pixels were viewed this turn.
  func testDefaultBodyUsesLunaHighEffortWithoutImageParts() throws {
    let body = makeBody()
    XCTAssertEqual(body["model"] as? String, "omi-luna-think")
    XCTAssertEqual(body["reasoning_effort"] as? String, "high")
    XCTAssertEqual(body["stream"] as? Bool, false)

    let messages = try XCTUnwrap(body["messages"] as? [[String: Any]])
    XCTAssertEqual(messages.count, 2)

    // Kernel plan cache marker and canonical snapshot stay system-scoped…
    let system = try XCTUnwrap(messages[0]["content"] as? String)
    XCTAssertTrue(system.contains("OMI_CONTEXT_CACHE_V1"))
    XCTAssertTrue(system.contains("stable=sha256:stable"))
    XCTAssertTrue(system.contains("[Kernel Context Snapshot]"))
    XCTAssertFalse(system.contains("Tool-provided context"))

    // …while tool-provided context stays on the user message, marked untrusted.
    let user = try XCTUnwrap(messages[1]["content"] as? String)
    XCTAssertTrue(user.contains("Tool-provided context (untrusted)"))
    XCTAssertFalse(user.contains("OMI_CONTEXT_CACHE_V1"))
  }

  func testHeavyThinkingMapsToLunaExtraHighEffort() throws {
    XCTAssertEqual(makeBody(thinkingLevel: .heavy)["reasoning_effort"] as? String, "xhigh")
  }

  func testUnknownThinkingInputFallsBackToNormal() {
    XCTAssertEqual(RealtimeHubTools.EscalationThinkingLevel.fromToolInput(nil), .normal)
    XCTAssertEqual(RealtimeHubTools.EscalationThinkingLevel.fromToolInput("turbo"), .normal)
    XCTAssertEqual(RealtimeHubTools.EscalationThinkingLevel.fromToolInput("HEAVY"), .heavy)
  }

  /// A viewed screenshot must reach the thinking agent as an image part on the
  /// user message — same pixels, not a re-description.
  func testScreenshotJPEGBecomesImageDataURIPartOnUserMessage() throws {
    let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x01, 0x02])
    let body = makeBody(screenJPEGs: [jpeg])
    let messages = try XCTUnwrap(body["messages"] as? [[String: Any]])
    let parts = try XCTUnwrap(messages[1]["content"] as? [[String: Any]])
    XCTAssertEqual(parts.count, 2)
    XCTAssertEqual(parts[0]["type"] as? String, "text")
    XCTAssertTrue((parts[0]["text"] as? String ?? "").contains("riddle"))
    XCTAssertEqual(parts[1]["type"] as? String, "image_url")
    let imageURL = try XCTUnwrap(parts[1]["image_url"] as? [String: Any])
    let url = try XCTUnwrap(imageURL["url"] as? String)
    XCTAssertTrue(url.hasPrefix("data:image/jpeg;base64,"))
    XCTAssertEqual(String(url.dropFirst("data:image/jpeg;base64,".count)), jpeg.base64EncodedString())
    // The system message never carries pixels.
    XCTAssertTrue(messages[0]["content"] is String)
  }

  func testMultipleScreenshotsAppendInOrder() throws {
    let first = Data([0x01])
    let second = Data([0x02])
    let body = makeBody(screenJPEGs: [first, second])
    let messages = try XCTUnwrap(body["messages"] as? [[String: Any]])
    let parts = try XCTUnwrap(messages[1]["content"] as? [[String: Any]])
    XCTAssertEqual(parts.count, 3)
    XCTAssertEqual(
      (parts[1]["image_url"] as? [String: Any])?["url"] as? String,
      "data:image/jpeg;base64," + first.base64EncodedString())
    XCTAssertEqual(
      (parts[2]["image_url"] as? [String: Any])?["url"] as? String,
      "data:image/jpeg;base64," + second.base64EncodedString())
  }
}

final class HubEscalationScreenEvidenceTests: XCTestCase {
  private func makeDescriptor(
    turnID: VoiceTurnID,
    digest: String,
    capturedAt: Date
  ) -> RealtimeScreenEvidenceDescriptor {
    RealtimeScreenEvidenceDescriptor(
      evidenceID: "ev-\(digest)",
      turnID: turnID,
      capturedAt: capturedAt,
      target: .frontmostDisplay,
      frontmostApp: "Safari",
      frontmostBundleID: "com.apple.Safari",
      windowID: 1,
      displayID: 1,
      imageByteCount: 10,
      imageDigest: digest,
      captureFailure: nil)
  }

  /// Only the invoking turn's evidence is forwarded: the frozen PTT-down frame
  /// and same-turn authorized screenshots, oldest first, duplicate pixels
  /// collapsed by digest. Stale-turn evidence never rides along.
  func testCurrentTurnEvidenceIsSelectedAndStaleExcluded() {
    let current = VoiceTurnID()
    let stale = VoiceTurnID()
    let t0 = Date(timeIntervalSince1970: 1000)
    let t1 = Date(timeIntervalSince1970: 2000)

    let evidence = RealtimeScreenEvidence(
      descriptor: makeDescriptor(turnID: current, digest: "d0", capturedAt: t0),
      preOverlayImage: nil,
      jpeg: Data([0x00]),
      encodingFinished: true)
    let currentShot = RealtimeScreenEvidenceAttachment(
      descriptor: makeDescriptor(turnID: current, digest: "d1", capturedAt: t1),
      jpeg: Data([0x01]))
    let duplicateShot = RealtimeScreenEvidenceAttachment(
      descriptor: makeDescriptor(turnID: current, digest: "d0", capturedAt: t1),
      jpeg: Data([0x00]))
    let staleShot = RealtimeScreenEvidenceAttachment(
      descriptor: makeDescriptor(turnID: stale, digest: "d2", capturedAt: t1),
      jpeg: Data([0x02]))

    let jpegs = RealtimeHubTools.escalationScreenJPEGs(
      expectedTurnID: current,
      evidence: evidence,
      authorizedScreenshots: [
        "inv-stale": staleShot,
        "inv-dup": duplicateShot,
        "inv-current": currentShot,
      ])
    XCTAssertEqual(jpegs, [Data([0x00]), Data([0x01])])
  }

  func testMissingTurnIDForwardsNoPixels() {
    let turn = VoiceTurnID()
    let evidence = RealtimeScreenEvidence(
      descriptor: makeDescriptor(turnID: turn, digest: "d0", capturedAt: Date()),
      preOverlayImage: nil,
      jpeg: Data([0x00]),
      encodingFinished: true)
    XCTAssertTrue(
      RealtimeHubTools.escalationScreenJPEGs(
        expectedTurnID: nil,
        evidence: evidence,
        authorizedScreenshots: [:]
      )
      .isEmpty)
  }

  func testEvidenceWithoutJPEGForwardsNoPixels() {
    let turn = VoiceTurnID()
    let evidence = RealtimeScreenEvidence(
      descriptor: makeDescriptor(turnID: turn, digest: "d0", capturedAt: Date()),
      preOverlayImage: nil,
      jpeg: nil,
      encodingFinished: false)
    XCTAssertTrue(
      RealtimeHubTools.escalationScreenJPEGs(
        expectedTurnID: turn,
        evidence: evidence,
        authorizedScreenshots: [:]
      )
      .isEmpty)
  }
}
