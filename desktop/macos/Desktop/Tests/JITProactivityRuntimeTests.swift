import CryptoKit
@preconcurrency import GRDB
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

  /// The coordinator's observation carries a calendar query that reaches EventKit on every
  /// context visit. A non-admitted owner must not pay for it to reach a decision that never
  /// reads the observation.
  func testNonAdmittedOwnerNeverBuildsTheObservationInputs() async throws {
    for flags in [
      JITProactivityFlags(rollout: .unknown, killSwitch: .unknown),
      JITProactivityFlags(rollout: .disabled, killSwitch: .disabled),
      JITProactivityFlags(rollout: .enabled, killSwitch: .enabled),
    ] {
      let probe = ObservationBuildProbe()
      let runtime = JITProactivityRuntime(
        flags: { _ in flags },
        snapshots: { _ in
          XCTFail("non-admitted authority must not read a new-runtime snapshot")
          throw ProactiveLaneClientError.invalidResponse
        })

      let decision = await runtime.admission(
        authorizationSnapshot: try snapshot(),
        observationProvider: { await probe.build() })

      let builds = await probe.builds
      XCTAssertEqual(builds, 0)
      guard case .legacyContextBucketFallback = decision else {
        return XCTFail("non-admitted authority must keep the legacy lane, got \(decision)")
      }
    }
  }

  func testAdmittedOwnerStillBuildsTheObservationExactlyOnce() async throws {
    let probe = ObservationBuildProbe()
    let runtime = JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in throw ProactiveLaneClientError.invalidResponse })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observationProvider: { await probe.build() })

    let builds = await probe.builds
    XCTAssertEqual(builds, 1)
    XCTAssertEqual(decision, .suppressed(reason: "authoritative_snapshot_unavailable"))
  }

  func testRolloutWireStatesFailClosed() {
    XCTAssertEqual(ProactiveLaneClient.jitState("enabled"), .enabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("disabled"), .disabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("unknown"), .unknown)
    XCTAssertEqual(ProactiveLaneClient.jitState("future"), .unknown)
    XCTAssertEqual(ProactiveLaneClient.jitState(nil), .unknown)
    // Retired spellings must fail closed, not re-enable the lane.
    XCTAssertEqual(ProactiveLaneClient.jitState("on"), .unknown)
    XCTAssertEqual(ProactiveLaneClient.jitState("off"), .unknown)
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
      let runtime = try wiredRuntime(
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
    let runtime = try wiredRuntime(
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
    let runtime = try wiredRuntime(triggers: [ambiguous, confirmed])

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
    let runtime = try wiredRuntime(
      triggers: [try compiledTrigger(id: "ambiguous", condition: ["apps": ["Slack"]])])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(occurredAt: Date(timeIntervalSince1970: 1_777_248_000)),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "planned_match_ambiguous"))
  }

  func testAmbiguousPlannedMatchUsesOneServerReservedNanoBeforeDelivery() async throws {
    let reservations = ReservationRecorder()
    let runtime = try wiredRuntime(
      triggers: [try compiledTrigger(id: "ambiguous", condition: ["apps": ["Slack"]])],
      nano: { _, _ in .approved },
      reserve: { reservation, _ in
        await reservations.record(reservation)
        return true
      })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "bounded evidence", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)))

    guard case .deliver(.planned, "ambiguous", _) = decision else {
      return XCTFail("approved bounded nano should admit the planned trigger: \(decision)")
    }
    let recorded = await reservations.values
    XCTAssertEqual(recorded.map(\.operation), [.nanoTriage])
    XCTAssertTrue(recorded.allSatisfy { $0.eventID.count == 64 && $0.candidateID.count == 64 })
  }

  func testDisabledEmbeddingPolicyIsDeterministicNoMatchDespiteLocalScore() async throws {
    let runtime = try wiredRuntime(
      triggers: [
        try compiledTrigger(
          id: "embedding",
          condition: ["embedding": embeddingCondition(prototypeID: "intent")])
      ])

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        occurredAt: Date(timeIntervalSince1970: 1_777_248_000),
        embeddingScores: ["intent": 0.99]))

    XCTAssertEqual(decision, .suppressed(reason: "ambient_local_gate"))
  }

  func testAtomicClaimRemainsFinalRaceFence() async throws {
    let runtime = try wiredRuntime(
      triggers: [try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])],
      claim: { _ in nil })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        text: "release", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)))

    XCTAssertEqual(decision, .suppressed(reason: "planned_duplicate_or_budget"))
  }

  func testSnoozedPlannedTriggerSuppressesBeforeExpiryAndAdmitsAtExactExpiry() async throws {
    let expiry = Date(timeIntervalSince1970: 500)
    let trigger = try compiledTrigger(
      id: "snoozed", condition: ["keywords": ["release"]], snoozedUntil: expiry)
    let runtime = try wiredRuntime(triggers: [trigger])
    let authorization = try snapshot()

    let before = await runtime.admission(
      authorizationSnapshot: authorization,
      observation: .init(text: "release", occurredAt: expiry.addingTimeInterval(-0.001)))
    XCTAssertEqual(before, .suppressed(reason: "ambient_local_gate"))

    let atExpiry = await runtime.admission(
      authorizationSnapshot: authorization,
      observation: .init(text: "release", occurredAt: expiry))
    guard case .deliver(.planned, "snoozed", _) = atExpiry else {
      return XCTFail("trigger must become eligible at its exact snooze expiry: (atExpiry)")
    }
  }

  func testRunningExecutionSuppressesSameProcessReclaimBeyondDatabaseLease() async throws {
    let runtime = try wiredRuntime(
      triggers: [try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])],
      begin: { _, _ in true })
    let observation = KnowledgeLedgerTriggerObservation(text: "release", occurredAt: Date())
    let authorization = try snapshot()
    let first = await runtime.admission(
      authorizationSnapshot: authorization, observation: observation)
    guard case .deliver(.planned, "planned", let continuityKey) = first,
      let execution = await runtime.takeExecution(continuityKey: continuityKey)
    else { return XCTFail("expected a planned execution: \(first)") }
    let began = await runtime.beginExecution(execution)
    XCTAssertTrue(began)

    let duplicate = await runtime.admission(
      authorizationSnapshot: authorization, observation: observation)

    XCTAssertEqual(duplicate, .suppressed(reason: "planned_duplicate_or_budget"))
    await runtime.finish(execution, delivered: false)
  }

  func testNewerAdmissionDeletingTriggerRejectsStaleClaimAfterActorReentrancy() async throws {
    let queue = try migratedQueue()
    let gate = AdmissionRaceGate()
    let trigger = try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])
    let oldRow = try snapshotRow(for: trigger, revision: 1)
    let oldSnapshot = serverSnapshot(sequence: 4, revision: "revision-4", rows: [oldRow])
    let newSnapshot = serverSnapshot(sequence: 5, revision: "revision-5", rows: [])
    let sequence = SnapshotSequence([oldSnapshot, newSnapshot])
    let runtime = JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in try await sequence.next() },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      },
      compileSnapshot: { receipt, _ in
        if receipt.snapshotRevision == "revision-4" {
          await gate.suspendFirstAdmission()
          return [trigger]
        }
        return []
      },
      readWakeupCounts: { _, _, _ in [:] },
      claimPlannedWakeup: { request in
        try queue.write { db in try JITTriggerMirror.claimPlannedWakeup(request, in: db) }
      },
      authorizationCurrent: { _ in true })
    let observation = KnowledgeLedgerTriggerObservation(
      text: "release", occurredAt: Date(timeIntervalSince1970: 1_777_248_000))
    let firstAuthorization = try snapshot()

    let first = Task {
      await runtime.admission(authorizationSnapshot: firstAuthorization, observation: observation)
    }
    await gate.waitUntilSuspended()
    let second = await runtime.admission(
      authorizationSnapshot: try snapshot(), observation: .init(text: "anything"))
    XCTAssertEqual(second, .suppressed(reason: "ambient_local_gate"))
    await gate.resumeFirstAdmission()
    let firstDecision = await first.value

    XCTAssertEqual(firstDecision, .suppressed(reason: "planned_duplicate_or_budget"))
    let claimCount = try await queue.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM jit_trigger_wakeup_receipts") ?? -1
    }
    XCTAssertEqual(claimCount, 0)
    let fingerprint = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger, observation: observation, day: "2026-04-26"
    ).observationFingerprint
    let staleKey = JITProactivityRuntime.plannedContinuityKey(
      triggerID: trigger.id, snapshotRevision: "revision-4", budgetDay: "2026-04-26",
      observationFingerprint: fingerprint)
    let pending = await runtime.takeExecution(continuityKey: staleKey)
    XCTAssertNil(pending)
  }

  func testReconciliationAfterClaimRejectsExecutionBeforeAgentTurnStarts() async throws {
    let queue = try migratedQueue()
    let trigger = try compiledTrigger(id: "planned", condition: ["keywords": ["release"]])
    let row = try snapshotRow(for: trigger)
    let admittedSnapshot = serverSnapshot(sequence: 4, revision: "revision-4", rows: [row])
    let deletedSnapshot = serverSnapshot(sequence: 5, revision: "revision-5", rows: [])
    let now = Date()
    let runtime = JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in admittedSnapshot },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: now) }
      },
      compileSnapshot: { _, _ in [trigger] },
      readWakeupCounts: { _, _, _ in [:] },
      claimPlannedWakeup: { request in
        try queue.write { db in try JITTriggerMirror.claimPlannedWakeup(request, in: db) }
      },
      beginPlannedExecution: { authority, claim in
        try queue.write { db in
          try JITTriggerMirror.beginPlannedExecution(
            authority, claim: claim, now: now.addingTimeInterval(1), in: db)
        }
      },
      authorizationCurrent: { _ in true })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "release", occurredAt: now))
    guard case .deliver(.planned, "planned", let continuityKey) = decision,
      let execution = await runtime.takeExecution(continuityKey: continuityKey)
    else { return XCTFail("expected a claimed planned execution: \(decision)") }

    try await queue.write { db in
      _ = try JITTriggerMirror.reconcile(deletedSnapshot, in: db, now: now.addingTimeInterval(1))
    }

    let mayBegin = await runtime.beginExecution(execution)
    XCTAssertFalse(mayBegin)
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

  func testRetainedJITIdentifiersAreHMACOpaqueToKnownContentAndInstallationKeys() {
    let knownInstallation = "known-installation-secret"
    let components = ["semantic", "bucket-1", "release owner changed"]
    let opaque = JITProactivityReservation.opaqueIdentifier(
      components, installationIdentity: knownInstallation)
    let plainDigest = SHA256.hash(data: Data(components.joined(separator: "\u{1f}").utf8))
      .map { String(format: "%02x", $0) }.joined()

    XCTAssertEqual(opaque.count, 64)
    XCTAssertNotEqual(
      opaque, plainDigest,
      "a known context must not derive the retained identifier without the installation key")
    XCTAssertEqual(
      opaque,
      JITProactivityReservation.opaqueIdentifier(
        components, installationIdentity: knownInstallation),
      "local dedupe remains stable for one installation")
    XCTAssertNotEqual(
      opaque,
      JITProactivityReservation.opaqueIdentifier(
        components, installationIdentity: "different-installation-secret"),
      "the same context on another installation must not share a predictable identifier")
  }

  func testInstallationIdentityIsPersistedRandomMaterialNotMachineDerived() {
    let suiteName = "JITProactivityRuntimeTests.identity.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      return XCTFail("test suite defaults unavailable")
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let service = ClientDeviceService(
      bundleIdentifier: AppBuild.desktopDevBundleIdentifier,
      userDefaults: defaults)

    let first = service.installationIdentity
    let second = ClientDeviceService(
      bundleIdentifier: AppBuild.desktopDevBundleIdentifier,
      userDefaults: defaults
    ).installationIdentity

    XCTAssertFalse(first.isEmpty)
    XCTAssertEqual(first, second)
    XCTAssertNotEqual(first.lowercased(), "macbook-pro")
    XCTAssertNotEqual(first.lowercased(), "localhost")
  }

  private func wiredRuntime(
    triggers: [KnowledgeLedgerCompiledTrigger],
    receiptOwner: String = "owner",
    receiptRevision: String = "revision",
    authorizationCurrent: Bool = true,
    claim: JITProactivityRuntime.ClaimWakeup? = nil,
    begin: JITProactivityRuntime.BeginPlannedExecution? = nil,
    nano: @escaping JITProactivityRuntime.NanoTriage = { _, _ in .unknown },
    reserve: @escaping JITProactivityRuntime.Reserve = { _, _ in true }
  ) throws -> JITProactivityRuntime {
    let rows = try triggers.map { try snapshotRow(for: $0) }
    let serverSnapshot = serverSnapshot(sequence: 4, revision: "revision", rows: rows)
    let receipt = JITTriggerMirrorReceipt(
      ownerID: receiptOwner,
      accountGeneration: 3,
      commitSequence: 4,
      snapshotRevision: receiptRevision,
      rowCount: rows.count)
    return JITProactivityRuntime(
      flags: { _ in JITProactivityFlags(rollout: .enabled, killSwitch: .disabled) },
      snapshots: { _ in serverSnapshot },
      nanoTriage: nano,
      reconcileSnapshot: { _, _ in receipt },
      compileSnapshot: { _, _ in triggers },
      readWakeupCounts: { _, _, _ in [:] },
      claimPlannedWakeup: claim ?? { request in
        JITTriggerWakeupClaim(
          continuityKey: request.continuityKey, triggerID: request.triggerID, leaseToken: "lease")
      },
      beginPlannedExecution: begin,
      reserve: reserve,
      authorizationCurrent: { _ in authorizationCurrent })
  }

  private func compiledTrigger(
    id: String,
    condition: [String: Any],
    prompt: String = "Run the standing action",
    snoozedUntil: Date? = nil
  ) throws -> KnowledgeLedgerCompiledTrigger {
    var triggerCondition = condition
    triggerCondition["schema_version"] = "jit_trigger.v1"
    triggerCondition["action"] = ["type": "agent_prompt", "prompt": prompt]
    let row = try KnowledgeLedgerTriggerRow(
      id: id, triggerCondition: triggerCondition, wakeupBudgetPerDay: 1)
    if let snoozedUntil {
      let data = try JSONSerialization.data(withJSONObject: triggerCondition, options: [.sortedKeys])
      guard
        case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compileAuthoritativeSnapshotRow(
          id: id, triggerConditionJSON: data, wakeupBudgetPerDay: 1, snoozedUntil: snoozedUntil)
      else { throw KnowledgeLedgerTriggerCompileFailure.malformed("test trigger did not compile") }
      return trigger
    }
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

  private func embeddingCondition(prototypeID: String) -> [String: Any] {
    [
      "prototype_id": prototypeID,
      "prototype_revision": "prototype-v1",
      "model_id": "local-jit-embedding",
      "model_version": "1",
      "language": "en",
      "min_similarity": 0.82,
    ]
  }

  private func migratedQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    var migrator = DatabaseMigrator()
    JITTriggerMirrorSchema.registerMigration(on: &migrator)
    try migrator.migrate(queue)
    return queue
  }

  private func serverSnapshot(
    sequence: Int, revision: String, rows: [JITTriggerSnapshotRow]
  ) -> JITTriggerSnapshot {
    JITTriggerSnapshot(
      ownerID: "owner", accountGeneration: 3, headCommitID: "head-\(sequence)",
      commitSequence: sequence, snapshotRevision: revision, complete: true, rows: rows,
      failureReason: nil)
  }

  private func snapshotRow(
    for trigger: KnowledgeLedgerCompiledTrigger, revision: Int = 1
  ) throws -> JITTriggerSnapshotRow {
    let action = try XCTUnwrap(trigger.action)
    var condition: [String: Any] = [
      "schema_version": "jit_trigger.v1",
      "match_mode": trigger.matchMode.rawValue,
      "action": ["type": action.type, "prompt": action.prompt],
    ]
    if !trigger.keywords.isEmpty { condition["keywords"] = trigger.keywords }
    if !trigger.apps.isEmpty { condition["apps"] = trigger.apps }
    if let embedding = trigger.embedding {
      condition["embedding"] = [
        "prototype_id": embedding.prototypeID,
        "prototype_revision": embedding.prototypeRevision,
        "model_id": embedding.modelID,
        "model_version": embedding.modelVersion,
        "language": embedding.language,
        "min_similarity": embedding.minSimilarity,
      ]
    }
    if let modelID = trigger.metadata.modelID { condition["model_id"] = modelID }
    if let modelVersion = trigger.metadata.modelVersion { condition["model_version"] = modelVersion }
    if let threshold = trigger.metadata.threshold { condition["threshold"] = threshold }
    let data = try JSONSerialization.data(withJSONObject: condition, options: [.sortedKeys])
    return JITTriggerSnapshotRow(
      memoryID: trigger.id, itemRevision: revision, updatedAt: Date(timeIntervalSince1970: 10),
      triggerConditionJSON: String(decoding: data, as: UTF8.self),
      action: JITTriggerSnapshotAction(type: action.type, prompt: action.prompt),
      wakeupBudgetPerDay: trigger.metadata.wakeupBudgetPerDay ?? 1,
      snoozedUntil: trigger.snoozedUntil)
  }
}

private actor SnapshotSequence {
  private var snapshots: [JITTriggerSnapshot]

  init(_ snapshots: [JITTriggerSnapshot]) { self.snapshots = snapshots }

  func next() throws -> JITTriggerSnapshot {
    guard !snapshots.isEmpty else { throw ProactiveLaneClientError.invalidResponse }
    return snapshots.removeFirst()
  }
}

private actor ReservationRecorder {
  private(set) var values: [JITProactivityReservation] = []
  func record(_ value: JITProactivityReservation) { values.append(value) }
}

private actor AdmissionRaceGate {
  private var suspended = false
  private var release: CheckedContinuation<Void, Never>?
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func suspendFirstAdmission() async {
    suspended = true
    for waiter in waiters { waiter.resume() }
    waiters.removeAll()
    await withCheckedContinuation { release = $0 }
  }

  func waitUntilSuspended() async {
    if suspended { return }
    await withCheckedContinuation { waiters.append($0) }
  }

  func resumeFirstAdmission() {
    release?.resume()
    release = nil
  }
}

/// Counts how many times the deferred observation inputs were actually built.
private actor ObservationBuildProbe {
  private(set) var builds = 0

  func build() -> KnowledgeLedgerTriggerObservation {
    builds += 1
    return KnowledgeLedgerTriggerObservation(text: "release")
  }
}
