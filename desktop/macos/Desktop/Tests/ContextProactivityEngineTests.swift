import GRDB
import XCTest

@testable import Omi_Computer

final class ContextProactivityEngineTests: XCTestCase {
  func testDwellAdmissionTracksVisitsInsteadOfSuppressingARevisitToTheSameBucket() {
    var admission = ContextVisitDwellAdmission()

    XCTAssertTrue(admission.begin(visitID: 41))
    XCTAssertTrue(admission.begin(visitID: 42), "a new visit needs its own dwell timer")
    XCTAssertFalse(admission.begin(visitID: 42), "the same visit must not be scheduled twice")

    admission.finish(visitID: 41)
    admission.finish(visitID: 42)
    XCTAssertTrue(admission.begin(visitID: 42))
  }

  func testDirectorDecisionClampsUntrustedOutputBeforeDatabaseQueriesAndPresentation() {
    let decision = ContextDirectorDecision(
      decision: "suggest",
      title: String(repeating: "t", count: 500),
      message: String(repeating: "m", count: 1_000),
      reasoning: String(repeating: "r", count: 2_000),
      bucketEntryRefs: (0..<50).map { "entry:\($0)" },
      factIDs: (0..<50).map { "fact:\($0)" })

    let clamped = decision.clamped()

    XCTAssertEqual(clamped.title.count, 120)
    XCTAssertEqual(clamped.message.count, 600)
    XCTAssertEqual(clamped.reasoning.count, 1_200)
    XCTAssertEqual(clamped.bucketEntryRefs.count, 20)
    XCTAssertEqual(clamped.factIDs.count, 20)
  }

  func testValidatedFactIDsRequireSnapshotMembershipAndCurrentBucketValidation() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      XCTAssertEqual(
        try ContextBucketStore.validatedFactIDs(
          ["fact:current", "old", "expired", "rejected", "other-bucket", "hallucinated"],
          snapshotFacts: [
            "fact:current current statement", "fact:old accumulated statement",
            "fact:expired stale statement",
            "fact:rejected stale statement", "fact:other-bucket unrelated statement",
          ],
          bucketID: "bucket-a",
          now: now,
          in: db),
        ["fact:current", "fact:old"],
        "A prior-version fact remains grounded when the current snapshot includes it")
      XCTAssertEqual(
        try ContextBucketStore.validatedFactIDs(
          ["current"],
          snapshotFacts: ["fact:old only this fact was presented"],
          bucketID: "bucket-a",
          in: db),
        [])
    }
  }

  func testFactExpiringAtTheEvaluationBoundaryIsOmittedFromSnapshotAndGrounding() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: "UPDATE bucket_facts SET expiresAt = ? WHERE id = 'current'",
        arguments: [now])

      let snapshot = try XCTUnwrap(ContextBucketStore.snapshot(in: db, bucketID: "bucket-a", now: now))
      XCTAssertFalse(
        snapshot.validatedFacts.contains { $0.hasPrefix("fact:current ") },
        "expiresAt == now is already expired at the evaluation boundary")
      XCTAssertEqual(snapshot.notifyWorthiness, 1, "the still-live fact must keep the bucket eligible")
      XCTAssertEqual(
        try ContextBucketStore.validatedFactIDs(
          ["fact:current"],
          snapshotFacts: ["fact:current current statement"],
          bucketID: "bucket-a",
          now: now,
          in: db),
        [],
        "a cited fact must be revalidated against the same expiry boundary")
    }
  }

  func testSnapshotExcludesExpiredValidatedFactsBeforeGarbageCollection() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)

    let snapshot = try queue.read { db in
      try XCTUnwrap(ContextBucketStore.snapshot(in: db, bucketID: "bucket-a", now: now))
    }

    XCTAssertTrue(snapshot.validatedFacts.contains { $0.hasPrefix("fact:current ") })
    XCTAssertTrue(snapshot.validatedFacts.contains { $0.hasPrefix("fact:old ") })
    XCTAssertFalse(snapshot.validatedFacts.contains { $0.hasPrefix("fact:expired ") })
    XCTAssertEqual(snapshot.notifyWorthiness, 1)
  }

  func testSnapshotWorthinessIgnoresExpiredValidatedFacts() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(sql: "UPDATE bucket_facts SET notifyWorthiness = 0")
      try db.execute(sql: "UPDATE bucket_facts SET notifyWorthiness = 1 WHERE id = 'expired'")
      try db.execute(sql: "UPDATE context_buckets SET notifyWorthiness = 1 WHERE id = 'bucket-a'")
    }

    let snapshot = try queue.read { db in
      try XCTUnwrap(ContextBucketStore.snapshot(in: db, bucketID: "bucket-a", now: now))
    }

    XCTAssertEqual(snapshot.notifyWorthiness, 0)
  }

  func testCandidateGraduationExcludesExpiredValidatedFacts() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)

    let factIDs = try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, bucketID, decisionType, lifecycleState, provenanceJson,
             attemptedAt, expiresAt, createdAt)
          VALUES ('delivery', 'bucket-a', 'task_candidate', 'attempted', '{}', ?, ?, ?)
          """,
        arguments: [now, now.addingTimeInterval(60), now])
      return try CandidateSink.graduationFacts(
        in: db,
        deliveryID: "delivery",
        factIDs: ["current", "expired"],
        now: now
      ).map(\.id)
    }

    XCTAssertEqual(factIDs, ["current"])
  }

  func testValidatedFactIDsFailClosedWhenDirectorCitesNothing() throws {
    let queue = try contextBucketDatabase()
    try queue.read { db in
      XCTAssertEqual(
        try ContextBucketStore.validatedFactIDs(
          [], snapshotFacts: ["fact:current statement"], bucketID: "bucket-a", in: db),
        [])
    }
  }

  func testNonSilenceGroundingRequiresBothValidatedEntryAndFactCitations() {
    XCTAssertTrue(
      ContextDirectorGrounding.permitsNonSilence(
        entryRefs: ["entry:one"], factIDs: ["fact:one"]))
    XCTAssertFalse(
      ContextDirectorGrounding.permitsNonSilence(entryRefs: ["entry:one"], factIDs: []))
    XCTAssertFalse(
      ContextDirectorGrounding.permitsNonSilence(entryRefs: [], factIDs: ["fact:one"]))
  }

  @MainActor
  func testPresentationFreeGateRebuildSuppressesMasterAndQuietChanges() throws {
    let suiteName = "ContextProactivityEngineTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(3, forKey: NotificationService.frequencyDefaultsKey)
    defaults.set(8 * 60, forKey: NotificationService.activePeriodStartDefaultsKey)
    defaults.set(22 * 60, forKey: NotificationService.activePeriodEndDefaultsKey)

    let noonComponents = DateComponents(calendar: .current, year: 2026, month: 8, day: 12, hour: 12)
    let noon = noonComponents.date ?? Date()
    let lateComponents = DateComponents(calendar: .current, year: 2026, month: 8, day: 12, hour: 23)
    let late = lateComponents.date ?? Date()

    // Mirror the production rebuild path: capture gate inputs, then re-evaluate
    // after master/quiet flips before presentation.
    let allowed = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      snoozed: false,
      paywalled: false,
      minuteOfDay: 12 * 60,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 3))
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    let noonMinute =
      try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: noon).hour) * 60
      + (try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: noon).minute))
    let masterOff = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      snoozed: false,
      paywalled: false,
      minuteOfDay: noonMinute,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: masterOff), .masterDisabled)

    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    let lateMinute =
      try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: late).hour) * 60
      + (try XCTUnwrap(Calendar.current.dateComponents([.hour, .minute], from: late).minute))
    let quiet = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: false,
      minuteOfDay: lateMinute,
      activePeriod: NotificationService.currentActivePeriod(defaults: defaults),
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: quiet), .quietHours)
  }

  func testAttemptGateRebuildSuppressesBeforeBudgetReservation() {
    let allowed = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: false,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    let snoozed = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: true,
      paywalled: false,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: snoozed), .snoozed)

    let paywalled = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      snoozed: false,
      paywalled: true,
      minuteOfDay: 12 * 60,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: paywalled), .paywalled)
  }

  func testPresentationPreflightMustBeQueuedBeforeAnAttemptCanBegin() {
    XCTAssertTrue(ContextProactivityEngine.presentationSurfaceAvailable(.queued))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.suppressed))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.windowUnavailable))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.rejectedOwnerChange))
    XCTAssertFalse(ContextProactivityEngine.presentationSurfaceAvailable(.presented))
  }

  private func contextBucketDatabase() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    let defaults = try XCTUnwrap(
      UserDefaults(suiteName: "ContextProactivityEngineTests.facts.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)

    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      for bucketID in ["bucket-a", "bucket-b"] {
        try db.execute(
          sql: """
            INSERT INTO context_buckets
              (id, subjectKind, subjectID, createdAt, updatedAt)
            VALUES (?, 'task', ?, ?, ?)
            """,
          arguments: [bucketID, "subject-\(bucketID)", now, now])
      }
      for version in [1, 2] {
        try db.execute(
          sql: """
            INSERT INTO bucket_versions
              (bucketID, version, header, frozenRankedSegment, createdAt)
            VALUES ('bucket-a', ?, 'header', ?, ?)
            """,
          arguments: [version, Data(), now])
      }
      try db.execute(
        sql: """
          INSERT INTO bucket_versions
            (bucketID, version, header, frozenRankedSegment, createdAt)
          VALUES ('bucket-b', 1, 'header', ?, ?)
          """,
        arguments: [Data(), now])
      let versions = try Row.fetchAll(
        db, sql: "SELECT id, bucketID, version FROM bucket_versions ORDER BY bucketID, version")
      let versionID: (String, Int) -> Int64 = { bucketID, version in
        versions.first { row in
          row["bucketID"] as String == bucketID && row["version"] as Int == version
        }?["id"] ?? -1
      }
      for (visitID, bucketID) in [(1, "bucket-a"), (2, "bucket-a"), (3, "bucket-b")] {
        try db.execute(
          sql: """
            INSERT INTO context_visits
              (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
               normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
            VALUES (?, 1, 1, ?, 'App', 'raw', 'normalized', ?, ?, 'completed', ?, ?)
            """,
          arguments: [visitID, bucketID, "hash-\(visitID)", now, now, now])
      }
      let entries: [(String, String, Int, Int64)] = [
        ("entry-old", "bucket-a", 1, versionID("bucket-a", 1)),
        ("entry-current", "bucket-a", 2, versionID("bucket-a", 2)),
        ("entry-other", "bucket-b", 3, versionID("bucket-b", 1)),
      ]
      for (entryID, bucketID, visitID, bucketVersionID) in entries {
        try db.execute(
          sql: """
            INSERT INTO bucket_entries
              (id, bucketID, visitID, bucketVersionID, appName, rawContextKey,
               normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
            VALUES (?, ?, ?, ?, 'App', 'raw', 'normalized', 'narrative', '[]', 1, ?)
            """,
          arguments: [entryID, bucketID, visitID, bucketVersionID, now])
      }
      let facts: [(String, String, String, String)] = [
        ("old", "bucket-a", "entry-old", "validated"),
        ("current", "bucket-a", "entry-current", "validated"),
        ("expired", "bucket-a", "entry-current", "validated"),
        ("rejected", "bucket-a", "entry-current", "rejected"),
        ("other-bucket", "bucket-b", "entry-other", "validated"),
      ]
      for (factID, bucketID, entryID, validity) in facts {
        try db.execute(
          sql: """
            INSERT INTO bucket_facts
              (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
               evidenceRefsJson, validityState, dispositionState, confidence,
               notifyWorthiness, createdAt, updatedAt)
            VALUES (?, ?, ?, 'App', 'statement', '[]', 'evidence', '[]', ?, 'none', 1, 1, ?, ?)
            """,
          arguments: [factID, bucketID, entryID, validity, now, now])
      }
      try db.execute(
        sql: "UPDATE bucket_facts SET expiresAt = ? WHERE id = 'expired'",
        arguments: [now.addingTimeInterval(-1)])
    }
    return queue
  }
}
