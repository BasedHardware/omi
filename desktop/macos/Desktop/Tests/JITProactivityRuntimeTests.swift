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

  func testOffAndKillSwitchPreserveLegacyOuterFallbackBeforeSnapshotRead() async throws {
    for (flags, expected) in [
      (JITProactivityFlags(rollout: .disabled, killSwitch: .disabled), "rollout_disabled"),
      (JITProactivityFlags(rollout: .enabled, killSwitch: .enabled), "kill_switch"),
    ] {
      let runtime = JITProactivityRuntime(
        flags: { _ in flags },
        snapshots: { _ in
          XCTFail("disabled authority must not read a new-runtime snapshot")
          throw ProactiveLaneClientError.invalidResponse
        })

      let decision = await runtime.admission(
        authorizationSnapshot: try snapshot(), observation: .init(text: "release"))

      XCTAssertEqual(decision, .legacyContextBucketFallback(reason: expected))
    }
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

  func testAuthorityMismatchAndStaleLeaseSuppressWithoutAmbientFallback() async throws {
    let trigger = try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])
    for (receiptOwner, receiptRevision, authorizationCurrent) in [
      ("other-owner", "revision", true),
      ("owner", "stale-revision", true),
      ("owner", "revision", false),
    ] {
      let runtime = wiredRuntime(
        triggers: [trigger],
        receiptOwner: receiptOwner,
        receiptRevision: receiptRevision,
        authorizationCurrent: authorizationCurrent)

      let decision = await runtime.admission(
        authorizationSnapshot: try snapshot(),
        observation: .init(text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)),
        ambient: validAmbient())

      XCTAssertEqual(decision, .suppressed(reason: "planned_runtime_rejected"))
    }
  }

  func testNoPlannedMatchReachesExistingAmbientAdmissionOnlyAfterAuthoritativeEvaluation() async throws {
    let runtime = wiredRuntime(
      triggers: [try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)))

    XCTAssertEqual(decision, .suppressed(reason: "ambient_local_gate"))
  }

  func testConfirmedMatchWinsAlongsideAmbiguousAndMapsExactAction() async throws {
    let ambiguous = try compiledTrigger(id: "a-ambiguous", condition: ["apps": ["Slack"]])
    let confirmed = try compiledTrigger(
      id: "z-confirmed",
      condition: ["keywords": ["release"]],
      prompt: "Use this exact standing action")
    let runtime = wiredRuntime(triggers: [ambiguous, confirmed])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        text: "release", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)))
    guard case .deliver(.planned, "z-confirmed", let continuityKey) = decision else {
      return XCTFail("confirmed planned trigger must win: \(decision)")
    }
    let execution = await runtime.takeExecution(continuityKey: continuityKey)

    XCTAssertEqual(execution?.triggerID, "z-confirmed")
    XCTAssertEqual(execution?.prompt, "Use this exact standing action")
    XCTAssertEqual(execution?.claim.triggerID, "z-confirmed")
  }

  func testAmbiguousOnlySuppressesWithoutAmbientOrNewModelAuthority() async throws {
    let runtime = wiredRuntime(
      triggers: [try compiledTrigger(id: "ambiguous", condition: ["apps": ["Slack"]])])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(occurredAt: Date(timeIntervalSince1970: 1_777_248_000)),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "planned_match_ambiguous"))
  }

  func testEmbeddingScoreCannotActivateWithoutAnActualLocalEmbeddingContract() async throws {
    let runtime = wiredRuntime(
      triggers: [
        try compiledTrigger(
          id: "embedding",
          condition: ["embedding": ["prototype_id": "intent", "min_similarity": 0.8]])
      ])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        occurredAt: Date(timeIntervalSince1970: 1_777_248_000),
        embeddingScores: ["intent": 0.99]))

    XCTAssertEqual(decision, .suppressed(reason: "planned_runtime_rejected"))
  }

  func testAtomicClaimRemainsFinalRaceFence() async throws {
    let runtime = wiredRuntime(
      triggers: [try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])],
      claim: { _, _, _, _, _, _, _, _ in nil })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        text: "release", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)))

    XCTAssertEqual(decision, .suppressed(reason: "planned_duplicate_or_budget"))
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

  private func wiredRuntime(
    triggers: [KnowledgeLedgerCompiledTrigger],
    receiptOwner: String = "owner",
    receiptRevision: String = "revision",
    authorizationCurrent: Bool = true,
    claim: JITProactivityRuntime.ClaimWakeup? = nil
  ) -> JITProactivityRuntime {
    let serverSnapshot = JITTriggerSnapshot(
      ownerID: "owner",
      accountGeneration: 3,
      headCommitID: "head",
      commitSequence: 4,
      snapshotRevision: "revision",
      complete: true,
      rows: [],
      failureReason: nil)
    let receipt = JITTriggerMirrorReceipt(
      ownerID: receiptOwner,
      accountGeneration: 3,
      commitSequence: 4,
      snapshotRevision: receiptRevision,
      rowCount: 0)
    return JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in serverSnapshot },
      reconcileSnapshot: { _, _ in receipt },
      compileSnapshot: { _, _ in triggers },
      readWakeupCounts: { _, _, _ in [:] },
      claimPlannedWakeup: claim ?? { continuityKey, triggerID, _, _, _, _, _, _ in
        JITTriggerWakeupClaim(
          continuityKey: continuityKey, triggerID: triggerID, leaseToken: "lease")
      },
      authorizationCurrent: { _ in authorizationCurrent })
  }

  private func compiledTrigger(
    id: String,
    condition: [String: Any],
    prompt: String = "Run the standing action"
  ) throws -> KnowledgeLedgerCompiledTrigger {
    var triggerCondition = condition
    triggerCondition["schema_version"] = "jit_trigger.v1"
    triggerCondition["action"] = ["type": "agent_prompt", "prompt": prompt]
    let row = try KnowledgeLedgerTriggerRow(
      id: id, triggerCondition: triggerCondition, wakeupBudgetPerDay: 2)
    guard case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compile(row) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("test trigger did not compile")
    }
    return trigger
  }

  private func validAmbient() -> JITAmbientRuntimeContext {
    JITAmbientRuntimeContext(
      id: "bucket",
      semanticFingerprint: String(repeating: "a", count: 64),
      locallyRelevant: true,
      boundedEvidence: "validated local change")
  }
}
