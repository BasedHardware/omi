import XCTest

@testable import Omi_Computer

final class JITProactivityRuntimeTests: XCTestCase {
  private func snapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    return try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
  }

  func testUnknownAuthorityPreservesLegacyLane() async throws {
    let runtime = JITProactivityRuntime { _ in
      JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
    }

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(), observation: KnowledgeLedgerTriggerObservation())

    XCTAssertEqual(decision, .legacyContextBucketFallback(reason: "rollout_unknown"))
  }

  func testRolloutWireStatesFailClosed() {
    XCTAssertEqual(ProactiveLaneClient.jitState("on"), .enabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("off"), .disabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("future"), .unknown)
    XCTAssertEqual(ProactiveLaneClient.jitState(nil), .unknown)
  }

  func testEnabledAuthorityFailsClosedWhenSnapshotIsUnavailable() async throws {
    let runtime = JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in throw ProactiveLaneClientError.invalidResponse })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(), observation: KnowledgeLedgerTriggerObservation())

    XCTAssertEqual(
      decision,
      .suppressed(reason: "authoritative_snapshot_unavailable"))
  }

  func testAmbientLocalGateDoesNotUseHistoricalIntentWords() {
    let historicalWords = JITAmbientRuntimeContext(
      id: "bucket:1", semanticFingerprint: String(repeating: "a", count: 64), locallyRelevant: true,
      boundedEvidence: "remember what happened before in history")
    let ordinaryWords = JITAmbientRuntimeContext(
      id: "bucket:1", semanticFingerprint: String(repeating: "b", count: 64), locallyRelevant: true,
      boundedEvidence: "the release owner changed")

    XCTAssertTrue(historicalWords.permitsNanoTriage)
    XCTAssertEqual(historicalWords.permitsNanoTriage, ordinaryWords.permitsNanoTriage)
  }

  func testAmbientCheapGateRejectsBeforeAnyModelWhenSemanticIdentityOrRelevanceIsMissing() {
    for context in [
      JITAmbientRuntimeContext(
        id: "bucket", semanticFingerprint: "", locallyRelevant: true,
        boundedEvidence: "fact"),
      JITAmbientRuntimeContext(
        id: "bucket", semanticFingerprint: String(repeating: "a", count: 64), locallyRelevant: false,
        boundedEvidence: "fact"),
    ] {
      XCTAssertFalse(context.permitsNanoTriage)
    }
  }

  func testAmbientSemanticFingerprintIgnoresFactOrderWhitespaceAndCaptureVolatility() {
    let first = JITAmbientRuntimeContext.semanticFingerprint(
      contextID: "bucket-1", validatedFacts: ["Release   OWNER changed", "Build is green"])
    let revisit = JITAmbientRuntimeContext.semanticFingerprint(
      contextID: "bucket-1", validatedFacts: ["build is green", "Release OWNER changed"])
    let changed = JITAmbientRuntimeContext.semanticFingerprint(
      contextID: "bucket-1", validatedFacts: ["build is red", "Release OWNER changed"])

    XCTAssertEqual(first, revisit)
    XCTAssertNotEqual(first, changed)
  }
}
