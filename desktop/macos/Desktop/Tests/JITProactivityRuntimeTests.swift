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

  /// The live gap: the server's `effective` verdict said enabled, but the client
  /// re-derived admission from the raw flags and never read the snapshot. An
  /// `effective`-enabled authority must reach the snapshot read even when the
  /// raw pair is unknown, and a complete empty watchlist must still persist the
  /// local trigger-snapshot receipt.
  func testEffectiveEnabledAuthorityReadsSnapshotAndPersistsEmptyWatchlistReceipt() async throws {
    let queue = try migratedQueue()
    let emptyWatchlist = serverSnapshot(sequence: 4, revision: "revision-4", rows: [])
    let sequence = SnapshotSequence([emptyWatchlist])
    let runtime = JITProactivityRuntime(
      flags: { _ in
        JITProactivityFlags(rollout: .unknown, killSwitch: .unknown, effective: .enabled)
      },
      snapshots: { _ in try await sequence.next() },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      },
      compileSnapshot: { _, _ in [] },
      readWakeupCounts: { _, _, _ in [:] },
      authorizationCurrent: { _ in true })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(), observation: KnowledgeLedgerTriggerObservation())

    // No ambient context was supplied, so the empty watchlist reaches the
    // ambient local gate rather than a silent suppression.
    XCTAssertEqual(decision, .suppressed(reason: "ambient_local_gate"))

    let remaining = await sequence.remaining
    XCTAssertEqual(remaining, 0, "effective-enabled authority must read the trigger snapshot")
    let receipts = try await queue.read { db in
      try String.fetchAll(
        db, sql: "SELECT ownerID FROM jit_trigger_snapshot_receipts")
    }
    XCTAssertEqual(receipts, ["owner"])
  }

  func testEmptyCompleteWatchlistReachesAmbientAdmission() async throws {
    let usageReads = UsageReadProbe()
    let runtime = try wiredRuntime(
      triggers: [],
      ambientNanoUsage: { day, _ in
        await usageReads.record(day)
        return JITAmbientNanoUsage(used: 0, lastSpentAt: nil)
      })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)),
      ambient: validAmbient())

    // Pacing admitted the spend; the only thing missing in a hermetic test is
    // the local receipt database, which is the next step after pacing.
    XCTAssertEqual(decision, .suppressed(reason: "ambient_nano_receipt_unavailable"))
    let days = await usageReads.days
    XCTAssertEqual(days.count, 1, "pacing must read today's usage exactly once before spending")
  }

  func testAmbientPacingUsesAuthoritativeProfileTimezoneForBudgetDay() async throws {
    let usageReads = UsageReadProbe()
    // 05:30 UTC is Aug 24 in New York but still Aug 23 in Los Angeles. The
    // server reservation uses the profile timezone, so the local mirror must
    // make the same day choice before it paces or claims nano work.
    let runtime = try wiredRuntime(
      triggers: [],
      budgetTimezone: "America/Los_Angeles",
      evaluationTime: Date(timeIntervalSince1970: 1_787_549_400),
      ambientNanoUsage: { day, _ in
        await usageReads.record(day)
        return JITAmbientNanoUsage(used: 8, lastSpentAt: nil)
      })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_787_549_400)),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "ambient_nano_budget"))
    let days = await usageReads.days
    XCTAssertEqual(days, ["2026-08-23"])
  }

  func testAmbientAdmissionUsesOneEvaluationInstantAcrossMidnight() async throws {
    let beforeMidnight = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-09-06T03:59:59Z"))
    let clock = AdvancingEvaluationClock(beforeMidnight)
    let usageReads = UsageReadProbe()
    let runtime = try wiredRuntime(
      triggers: [],
      budgetTimezone: "America/New_York",
      ambientNanoUsage: { day, _ in
        await usageReads.record(day)
        return JITAmbientNanoUsage(used: 8, lastSpentAt: nil)
      },
      evaluationNow: { clock.next() })
    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "deadline", occurredAt: beforeMidnight),
      ambient: validAmbient())
    XCTAssertEqual(decision, .suppressed(reason: "ambient_nano_budget"))
    let days = await usageReads.days
    XCTAssertEqual(days, ["2026-09-05"])
    XCTAssertEqual(clock.count, 1)
  }

  func testMalformedAuthoritativeTimezoneFailsClosedBeforeAmbientSpend() async throws {
    let usageReads = UsageReadProbe()
    let runtime = try wiredRuntime(
      triggers: [],
      budgetTimezone: "Mars/Olympus_Mons",
      ambientNanoUsage: { day, _ in
        await usageReads.record(day)
        return JITAmbientNanoUsage(used: 0, lastSpentAt: nil)
      })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_787_549_400)),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "budget_authority_unavailable"))
    let days = await usageReads.days
    XCTAssertTrue(days.isEmpty)
  }

  func testAmbientPacingDefersUnmatchedContextInsideSpacingWithoutSpend() async throws {
    let now = Date(timeIntervalSince1970: 1_777_248_000)
    let runtime = try wiredRuntime(
      triggers: [],
      evaluationTime: now,
      ambientNanoUsage: { _, _ in
        JITAmbientNanoUsage(used: 2, lastSpentAt: now.addingTimeInterval(-600))
      })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: now),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "ambient_paced"))
  }

  func testDerivedIntentMatchBypassesSpacingButNotTheDailyCap() async throws {
    let now = Date(timeIntervalSince1970: 1_777_248_000)
    let match = JITDerivedIntentMatch(entries: [
      JITDerivedIntentEntry(id: "derived:task", source: .task, label: "ship release", keywords: ["ship", "release"])
    ])
    let insideSpacing = try wiredRuntime(
      triggers: [],
      evaluationTime: now,
      ambientNanoUsage: { _, _ in JITAmbientNanoUsage(used: 2, lastSpentAt: now.addingTimeInterval(-600)) },
      derivedIntent: { _, _ in match })
    let paced = await insideSpacing.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "ship the release", occurredAt: now),
      ambient: validAmbient())
    XCTAssertEqual(paced, .suppressed(reason: "ambient_nano_receipt_unavailable"))

    let exhausted = try wiredRuntime(
      triggers: [],
      evaluationTime: now,
      ambientNanoUsage: { _, _ in JITAmbientNanoUsage(used: 8, lastSpentAt: now.addingTimeInterval(-600)) },
      derivedIntent: { _, _ in match })
    let capped = await exhausted.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "ship the release", occurredAt: now),
      ambient: validAmbient())
    XCTAssertEqual(capped, .suppressed(reason: "ambient_nano_budget"))
  }

  func testServerNanoDenialBacksOffInsteadOfRetryingEveryVisit() async throws {
    let reserves = ReservationRecorder()
    let now = Date(timeIntervalSince1970: 1_777_248_000)
    let clock = MutableDateBox(now)
    let runtime = try wiredRuntime(
      triggers: [],
      reserve: { reservation, _ in
        await reserves.record(reservation)
        return false
      },
      ambientNanoUsage: { _, _ in JITAmbientNanoUsage(used: 0, lastSpentAt: nil) },
      claimAmbientNano: { request in
        JITTriggerWakeupClaim(
          continuityKey: "jit-nano:\(request.contextID):\(request.semanticFingerprint)",
          triggerID: "ambient-nano", leaseToken: "lease")
      },
      evaluationNow: { clock.value })

    let first = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: now),
      ambient: validAmbient())
    XCTAssertEqual(first, .suppressed(reason: "ambient_nano_budget"))

    let second = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "dinner", occurredAt: now.addingTimeInterval(60)),
      ambient: validAmbient(fingerprint: String(repeating: "b", count: 64)))
    XCTAssertEqual(second, .suppressed(reason: "ambient_server_denied"))
    let recorded = await reserves.values
    XCTAssertEqual(recorded.count, 1, "a denied day must not re-reserve on the next visit")

    clock.value = now.addingTimeInterval(JITProactivityRuntime.ambientServerDenialBackoff + 1)
    let later = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(
        text: "dinner", occurredAt: now.addingTimeInterval(JITProactivityRuntime.ambientServerDenialBackoff + 1)),
      ambient: validAmbient(fingerprint: String(repeating: "c", count: 64)))
    XCTAssertEqual(later, .suppressed(reason: "ambient_nano_budget"))
  }

  func testAmbientUsageReadFailureFailsClosedBeforeAnySpend() async throws {
    let runtime = try wiredRuntime(
      triggers: [],
      ambientNanoUsage: { _, _ in throw JITTriggerMirrorError.databaseUnavailable })

    let decision = await runtime.admission(
      authorizationSnapshot: try snapshot(),
      observation: .init(text: "lunch", occurredAt: Date(timeIntervalSince1970: 1_777_248_000)),
      ambient: validAmbient())

    XCTAssertEqual(decision, .suppressed(reason: "ambient_nano_receipt_unavailable"))
  }

  func testJITAdmissionSourceDoesNotStartMemoryAssistant() throws {
    let runtimeSource = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/ProactiveAssistants/Core/JITProactivityRuntime.swift")
    // omi-test-quality: source-inspection -- static contract: JIT admission must not construct or start MemoryAssistant; empty watchlists suppress rather than buying another extraction lane
    let source = try String(contentsOf: runtimeSource, encoding: .utf8)
    XCTAssertFalse(source.contains("MemoryAssistant"))
  }

  // MARK: - Signed-in startup snapshot sync

  /// Snapshot sync on signed-in startup must not wait for a context visit: an
  /// effective-enabled owner fetches the authoritative snapshot and persists
  /// the receipt even when the watchlist is empty and no visit ever settles.
  func testStartupSyncFetchesSnapshotAndPersistsEmptyWatchlistReceiptWithoutAContextVisit() async throws {
    let queue = try migratedQueue()
    let emptyWatchlist = serverSnapshot(sequence: 4, revision: "revision-4", rows: [])
    let sequence = SnapshotSequence([emptyWatchlist])
    let runtime = JITProactivityRuntime(
      flags: { _ in
        JITProactivityFlags(rollout: .unknown, killSwitch: .unknown, effective: .enabled)
      },
      snapshots: { _ in try await sequence.next() },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      },
      authorizationCurrent: { _ in true })

    await runtime.syncTriggerSnapshot(authorizationSnapshot: try snapshot())

    let remaining = await sequence.remaining
    XCTAssertEqual(remaining, 0, "startup sync must read the trigger snapshot with zero context visits")
    let receipts = try await queue.read { db in
      try Row.fetchAll(
        db, sql: "SELECT ownerID, rowCount FROM jit_trigger_snapshot_receipts")
    }
    XCTAssertEqual(receipts.count, 1)
    let receipt = try XCTUnwrap(receipts.first)
    let ownerID: String = receipt["ownerID"]
    let rowCount: Int = receipt["rowCount"]
    XCTAssertEqual(ownerID, "owner")
    XCTAssertEqual(rowCount, 0, "an empty watchlist still persists its receipt")
  }

  /// Fail-closed startup: every non-permitting authority — unknown, rollout
  /// disabled, kill switch, and an explicit `effective=disabled` — skips the
  /// snapshot read and writes no receipt.
  func testStartupSyncFailsClosedWhenAuthorityDoesNotPermitNewLane() async throws {
    let nonPermitting: [JITProactivityFlags] = [
      JITProactivityFlags(rollout: .unknown, killSwitch: .unknown),
      JITProactivityFlags(rollout: .disabled, killSwitch: .disabled),
      JITProactivityFlags(rollout: .enabled, killSwitch: .enabled),
      JITProactivityFlags(rollout: .enabled, killSwitch: .disabled, effective: .disabled),
    ]
    for flags in nonPermitting {
      let queue = try migratedQueue()
      let runtime = JITProactivityRuntime(
        flags: { _ in flags },
        snapshots: { _ in
          XCTFail("a non-permitting authority must not fetch the trigger snapshot")
          throw ProactiveLaneClientError.invalidResponse
        },
        reconcileSnapshot: { snapshot, _ in
          try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
        })

      await runtime.syncTriggerSnapshot(authorizationSnapshot: try snapshot())

      let receipts = try await queue.read { db in
        try String.fetchAll(db, sql: "SELECT ownerID FROM jit_trigger_snapshot_receipts")
      }
      XCTAssertTrue(receipts.isEmpty, "flags \(flags) must leave no receipt")
    }
  }

  /// One shot, no loop: an unavailable snapshot at startup must swallow the
  /// failure without crashing and leave the mirror untouched — the next
  /// context visit's admission still owns recovery.
  func testStartupSyncSwallowsSnapshotFailureWithoutPersistingAReceipt() async throws {
    let queue = try migratedQueue()
    let runtime = JITProactivityRuntime(
      flags: { _ in
        JITProactivityFlags(rollout: .unknown, killSwitch: .unknown, effective: .enabled)
      },
      snapshots: { _ in throw ProactiveLaneClientError.invalidResponse },
      reconcileSnapshot: { snapshot, _ in
        try queue.write { db in try JITTriggerMirror.reconcile(snapshot, in: db, now: Date()) }
      })

    await runtime.syncTriggerSnapshot(authorizationSnapshot: try snapshot())

    let receipts = try await queue.read { db in
      try String.fetchAll(db, sql: "SELECT ownerID FROM jit_trigger_snapshot_receipts")
    }
    XCTAssertTrue(receipts.isEmpty)
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
    // The deleting snapshot leaves an empty watchlist, which now reaches the
    // ambient lane; no ambient context is supplied here, so its local gate stops it.
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
    budgetTimezone: String? = nil,
    evaluationTime: Date? = nil,
    authorizationCurrent: Bool = true,
    claim: JITProactivityRuntime.ClaimWakeup? = nil,
    begin: JITProactivityRuntime.BeginPlannedExecution? = nil,
    nano: @escaping JITProactivityRuntime.NanoTriage = { _, _ in .unknown },
    reserve: @escaping JITProactivityRuntime.Reserve = { _, _ in true },
    ambientNanoUsage: JITProactivityRuntime.AmbientNanoUsageReader? = { _, _ in
      JITAmbientNanoUsage(used: 0, lastSpentAt: nil)
    },
    derivedIntent: @escaping JITProactivityRuntime.DerivedIntentResolver = { _, _ in .none },
    claimAmbientNano: JITProactivityRuntime.ClaimAmbientNano? = nil,
    evaluationNow: @escaping @Sendable () -> Date = Date.init
  ) throws -> JITProactivityRuntime {
    let rows = try triggers.map { try snapshotRow(for: $0) }
    let serverSnapshot = serverSnapshot(
      sequence: 4, revision: "revision", rows: rows, budgetTimezone: budgetTimezone)
    let receipt = JITTriggerMirrorReceipt(
      ownerID: receiptOwner,
      accountGeneration: 3,
      commitSequence: 4,
      snapshotRevision: receiptRevision,
      rowCount: rows.count)
    let resolvedEvaluationNow: @Sendable () -> Date
    if let evaluationTime {
      resolvedEvaluationNow = { evaluationTime }
    } else {
      resolvedEvaluationNow = evaluationNow
    }
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
      authorizationCurrent: { _ in authorizationCurrent },
      derivedIntent: derivedIntent,
      ambientNanoUsage: ambientNanoUsage,
      claimAmbientNano: claimAmbientNano,
      evaluationNow: resolvedEvaluationNow)
  }

  private final class AdvancingEvaluationClock: @unchecked Sendable {
    private let lock = NSLock()
    private let initial: Date
    private var reads = 0
    init(_ initial: Date) { self.initial = initial }
    func next() -> Date {
      lock.lock()
      defer { lock.unlock() }
      defer { reads += 1 }
      return initial.addingTimeInterval(TimeInterval(reads * 2))
    }
    var count: Int {
      lock.lock()
      defer { lock.unlock() }
      return reads
    }
  }

  private final class MutableDateBox: @unchecked Sendable {
    var value: Date
    init(_ value: Date) { self.value = value }
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

  private func validAmbient(fingerprint: String = String(repeating: "a", count: 64)) -> JITAmbientRuntimeContext {
    JITAmbientRuntimeContext(
      id: "bucket",
      semanticFingerprint: fingerprint,
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
    sequence: Int, revision: String, rows: [JITTriggerSnapshotRow], budgetTimezone: String? = nil
  ) -> JITTriggerSnapshot {
    JITTriggerSnapshot(
      ownerID: "owner", accountGeneration: 3, headCommitID: "head-\(sequence)",
      commitSequence: sequence, snapshotRevision: revision, complete: true, rows: rows,
      failureReason: nil, budgetTimezone: budgetTimezone)
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

  var remaining: Int {
    snapshots.count
  }
}

private actor UsageReadProbe {
  private(set) var days: [String] = []
  func record(_ day: String) { days.append(day) }
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
