import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubSpawnAgentTests: XCTestCase {
  func testSpawnAgentSuppressesPostToolAssistantOutput() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var suppressAssistantOutputForCurrentTurn = false"))
    XCTAssertTrue(source.contains("guard !suppressAssistantOutputForCurrentTurn else { return }"))
    XCTAssertTrue(source.contains("suppressAssistantOutputForCurrentTurn = true"))
    XCTAssertFalse(source.contains("Acknowledged before the call — do not say anything else"))
  }

  func testSpawnAgentToolResultReportsStartupTruth() throws {
    // The spawn tool result must not blindly claim the agent started: it waits
    // out the startup window and reports failure (with relay instructions) or
    // success (with a no-guessing status rule).
    let source = try chatToolExecutorSource()

    XCTAssertTrue(source.contains("agent FAILED to start:"))
    XCTAssertTrue(source.contains("check get_task_agent_status first"))
    XCTAssertTrue(source.contains("case .failed(let errorText) = pill.status"))
  }

  func testSpawnAgentDoesNotSwitchVoicesWhenModelDidNotSpeakBeforeToolCall() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("if !self.audioReceivedThisTurn {"))
    XCTAssertTrue(source.contains("let existingAck = self.assistantText.trimmingCharacters"))
    XCTAssertTrue(source.contains("let ack = existingAck.isEmpty ? plan.ack : existingAck"))
    XCTAssertTrue(source.contains("self.speak(ack)"))
  }

  func testLocalProfileOrdinaryAndRecallTurnsNeverProposeSpawn() throws {
    let marker = "GAUNTLET-20260712-FLOATING-ABC123"
    let ordinary = try XCTUnwrap(
      RealtimeLocalProfileTurnPlan.make(
        transcript: "Remember \(marker) exactly.",
        voiceContext: "",
        localProfileEnabled: true))
    XCTAssertNil(ordinary.spawn)
    XCTAssertTrue(ordinary.assistantText.contains(marker))

    let recall = try XCTUnwrap(
      RealtimeLocalProfileTurnPlan.make(
        transcript: "What was the last thing I asked you for?",
        voiceContext: "Earlier GAUNTLET-OLD. Latest \(marker).",
        localProfileEnabled: true))
    XCTAssertNil(recall.spawn)
    XCTAssertTrue(recall.assistantText.contains(marker))
    XCTAssertFalse(recall.assistantText.contains("GAUNTLET-OLD"))
  }

  func testCanonicalSpawnReceiptKeepsProviderContinuationInNativeVoiceLane() {
    XCTAssertEqual(
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: .inactive,
        reducerOutputSuppressed: false),
      .present)
    XCTAssertEqual(
      RealtimeProviderTurnDoneDisposition.decide(
        pendingToolCount: 0,
        postToolContinuationRequired: true),
      .requestPostToolContinuation)
  }

  func testCanonicalSpawnReceiptNeverRedrivesAfterExpectedSessionRefresh() {
    XCTAssertFalse(
      RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
        sessionChanged: true,
        hasCanonicalSpawnReceipt: true))
    XCTAssertTrue(
      RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
        sessionChanged: true,
        hasCanonicalSpawnReceipt: false))
    XCTAssertFalse(
      RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
        sessionChanged: false,
        hasCanonicalSpawnReceipt: false))
  }

  func testSpawnJournalReceiptAcceptsOnlyCanonicalTurnIdentity() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
    let payload = canonicalSpawnPayload(continuityKey: continuityKey)
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = try XCTUnwrap(String(data: data, encoding: .utf8))

    XCTAssertEqual(
      RealtimeSpawnJournalReceipt.parse(
        output: output, expectedContinuityKey: continuityKey),
      RealtimeSpawnJournalReceipt(
        continuityKey: continuityKey,
        userTurnID: KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "user"),
        assistantTurnID: KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
        assistantText: "I started a background agent for that.",
        pillProjection: nil))
    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: output,
        expectedContinuityKey: "voice:00000000-0000-0000-0000-000000000000"))
  }

  func testSpawnJournalReceiptProjectsTheKernelAcceptedChildRun() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009516"
    let pillID = UUID(uuidString: "00000000-0000-0000-0000-000000000123")!
    let payload = canonicalSpawnPayload(
      continuityKey: continuityKey,
      pillID: pillID,
      title: "Research models",
      objective: "Research the latest models")
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = try XCTUnwrap(String(data: data, encoding: .utf8))

    let receipt = try XCTUnwrap(
      RealtimeSpawnJournalReceipt.parse(output: output, expectedContinuityKey: continuityKey))
    XCTAssertEqual(
      receipt.pillProjection,
      RealtimeSpawnJournalReceipt.PillProjection(
        pillID: pillID,
        sessionID: "session-child",
        runID: "run-child",
        attemptID: "attempt-child",
        provider: "hermes",
        title: "Research models",
        objective: "Research the latest models"))
  }

  func testSpawnJournalReceiptRejectsTamperedStableIdentity() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009515"
    var payload = canonicalSpawnPayload(continuityKey: continuityKey)
    var receipt = try XCTUnwrap(payload["journalReceipt"] as? [String: Any])
    receipt["userTurnId"] = "turn_tampered"
    payload["journalReceipt"] = receipt
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let output = try XCTUnwrap(String(data: data, encoding: .utf8))

    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: output, expectedContinuityKey: continuityKey))
  }

  func testSpawnJournalReceiptRejectsMissingOrMismatchedChildLifecycle() throws {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009518"
    var missingChild = canonicalSpawnPayload(continuityKey: continuityKey)
    missingChild.removeValue(forKey: "child")
    let missingData = try JSONSerialization.data(withJSONObject: missingChild, options: [.sortedKeys])
    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: try XCTUnwrap(String(data: missingData, encoding: .utf8)),
        expectedContinuityKey: continuityKey))

    var mismatched = canonicalSpawnPayload(continuityKey: continuityKey)
    var providerResult = try XCTUnwrap(mismatched["providerResult"] as? [String: Any])
    providerResult["semanticDigest"] = "different-semantic-child"
    mismatched["providerResult"] = providerResult
    let mismatchData = try JSONSerialization.data(withJSONObject: mismatched, options: [.sortedKeys])
    XCTAssertNil(
      RealtimeSpawnJournalReceipt.parse(
        output: try XCTUnwrap(String(data: mismatchData, encoding: .utf8)),
        expectedContinuityKey: continuityKey))
  }

  func testRejectedSpawnResultCannotBeTreatedAsAnAcceptedVoiceTurn() {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009517"
    let rejected = #"{"ok":false,"error":{"code":"provider_boundary_rejected","message":"not allowed"}}"#

    XCTAssertEqual(
      RealtimeSpawnAgentToolOutcome.classify(
        output: rejected,
        expectedContinuityKey: continuityKey),
      .rejected)
  }

  func testDirectedProviderSetupNeededIsTypedAndCannotCreateAPill() {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009519"
    let setupNeeded =
      #"{"ok":false,"error":{"code":"provider_setup_needed","provider":"openclaw","message":"OpenClaw needs setup"}}"#

    XCTAssertEqual(
      RealtimeSpawnAgentToolOutcome.classify(
        output: setupNeeded,
        expectedContinuityKey: continuityKey),
      .setupNeeded(.openclaw))
  }

  func testDirectedCodexSetupNeededIsTypedAndCannotCreateAPill() {
    let continuityKey = "voice:00000000-0000-0000-0000-000000009520"
    let setupNeeded =
      #"{"ok":false,"error":{"code":"provider_setup_needed","provider":"codex","message":"Codex needs setup"}}"#

    XCTAssertEqual(
      RealtimeSpawnAgentToolOutcome.classify(
        output: setupNeeded,
        expectedContinuityKey: continuityKey),
      .setupNeeded(.codex))
  }

  func testSharedSpawnReceiptFixturesAcceptValidAndRejectMalformed() throws {
    let fixtureDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("agent/fixtures/spawn-receipt/v1")
    let names = try FileManager.default.contentsOfDirectory(atPath: fixtureDir.path)
      .filter { $0.hasSuffix(".json") }
      .sorted()
    XCTAssertTrue(names.contains("valid-running.json"))
    XCTAssertTrue(names.contains { $0.hasPrefix("malformed-") })

    for name in names {
      let data = try Data(contentsOf: fixtureDir.appendingPathComponent(name))
      let output = try XCTUnwrap(String(data: data, encoding: .utf8))
      let payload = try XCTUnwrap(
        JSONSerialization.jsonObject(with: data) as? [String: Any])
      let continuityKey =
        (payload["journalReceipt"] as? [String: Any])?["continuityKey"] as? String
        ?? "voice:00000000-0000-0000-0000-00000000f001"
      let parsed = RealtimeSpawnJournalReceipt.parse(
        output: output,
        expectedContinuityKey: continuityKey)
      if name.hasPrefix("valid-") {
        let receipt = try XCTUnwrap(parsed, "valid fixture \(name) must parse")
        XCTAssertEqual(receipt.continuityKey, continuityKey)
        XCTAssertEqual(
          receipt.userTurnID,
          KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user"))
        XCTAssertEqual(
          receipt.assistantTurnID,
          KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "assistant"))
        XCTAssertFalse(receipt.assistantText.isEmpty)
      } else {
        XCTAssertNil(parsed, "malformed fixture \(name) must be rejected")
      }
    }
  }

  private func canonicalSpawnPayload(
    continuityKey: String,
    pillID: UUID? = nil,
    title: String = "Background agent",
    objective: String = "Research the latest models"
  ) -> [String: Any] {
    let childLifecycle: [String: Any] = [
      "state": "running",
      "attemptState": "running",
      "revision": 2,
      "adapterId": "hermes",
      "updatedAtMs": 1_720_000_000_000 as NSNumber,
    ]
    var child: [String: Any] = [
      "sessionId": "session-child",
      "runId": "run-child",
      "attemptId": "attempt-child",
      "title": title,
      "objective": objective,
      "provider": "hermes",
      "lifecycle": childLifecycle,
    ]
    if let pillID { child["pillId"] = pillID.uuidString }
    let semanticDigest = "semantic-child-digest"
    return [
      "schemaVersion": 1,
      "ok": true,
      "journalReceipt": [
        "accepted": true,
        "continuityKey": continuityKey,
        "userTurnId": KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "user"),
        "assistantTurnId": KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
        "assistantText": "I started a background agent for that.",
      ],
      "child": child,
      "semanticDigest": semanticDigest,
      "providerResult": [
        "schemaVersion": 1,
        "ok": true,
        "code": "spawn_started",
        "message": "Background agent started.",
        "child": [
          "sessionId": "session-child",
          "runId": "run-child",
          "attemptId": "attempt-child",
          "state": "running",
          "attemptState": "running",
          "revision": 2,
          "adapterId": "hermes",
          "updatedAtMs": 1_720_000_000_000 as NSNumber,
        ],
        "semanticDigest": semanticDigest,
      ],
    ]
  }

  func testRealtimeToolRequestHasNoLocalExecutionBranch() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("LocalAgentProviderRouting.resolveSpawnWithAutoInstall("))
    XCTAssertTrue(source.contains("case .setupRequired(let provider, let setupPrompt, let spokenStatus):"))
    XCTAssertTrue(source.contains("self.assistantText = setupPrompt"))
    XCTAssertTrue(source.contains("self.speak(spokenStatus)"))
    XCTAssertTrue(source.contains("output: \"Error: \\(setupPrompt)\""))
  }

  func testCanonicalAgentControlSummariesDoNotSpeakOpaqueIds() throws {
    let source = try agentControlServiceSource()

    XCTAssertTrue(
      source.contains(
        "Use agentRef values internally for follow-up tool calls; do not say them aloud"))
    XCTAssertTrue(
      source.contains(
        "Use artifactRef values internally for follow-up tool calls; do not say them aloud"))
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
    try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
  }

  private func realtimeToolAuthoritySource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeToolAuthority.swift")
    // omi-test-quality: source-inspection -- static contract: extracted policy ownership helper
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubSessionPoliciesSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubSessionPolicies.swift")
    // omi-test-quality: source-inspection -- static contract: extracted policy ownership helper
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func chatToolExecutorSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatToolExecutor.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func agentControlServiceSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentControlService.swift")
    // omi-test-quality: source-inspection -- static contract: forbidden-path ratchet helper
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
