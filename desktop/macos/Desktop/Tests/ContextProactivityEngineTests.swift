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
  func testPresentationFreeGateRebuildSuppressesMasterChanges() throws {
    let suiteName = "ContextProactivityEngineTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(true, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(3, forKey: NotificationService.frequencyDefaultsKey)

    // Mirror the production rebuild path: capture gate inputs, then re-evaluate
    // after the master toggle flips before presentation.
    let allowed = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      paywalled: false,
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: 3))
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    let rebuilt = ContextDeliveryGateInput(
      masterEnabled: defaults.bool(forKey: NotificationService.masterEnabledDefaultsKey),
      frequencyLevel: defaults.integer(forKey: NotificationService.frequencyDefaultsKey),
      paywalled: false,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: rebuilt), .masterDisabled)
  }

  func testAttemptGateRebuildSuppressesBeforeBudgetReservation() {
    let allowed = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      paywalled: false,
      cooldownSeconds: 0)
    XCTAssertEqual(ContextDeliveryBudget.freeGate(input: allowed), .allowed)

    let paywalled = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 3,
      paywalled: true,
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

  func testHttpLaneErrorRecordsStatusInTerminalProvenanceJSON() throws {
    let classified = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: 12))
    XCTAssertEqual(classified.failure, "http_error")
    XCTAssertEqual(classified.status, 429)
    XCTAssertEqual(classified.logDescription, "http_error status=429")
    let json = try provenanceObject(classified.provenanceJSON)
    XCTAssertEqual(json["failure"] as? String, "http_error")
    XCTAssertEqual((json["status"] as? NSNumber)?.intValue, 429)
    XCTAssertNil(json["error_type"])
  }

  func testQuotaCooldownIsADistinctProvenanceClassFromHttp429() throws {
    let skipped = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.quotaCooldown(retryAfterSeconds: 12))
    XCTAssertEqual(skipped.failure, "quota_cooldown")
    XCTAssertEqual(skipped.status, 429)
    XCTAssertEqual(skipped.logDescription, "quota_cooldown status=429")
    let json = try provenanceObject(skipped.provenanceJSON)
    XCTAssertEqual(json["failure"] as? String, "quota_cooldown")
    XCTAssertEqual((json["status"] as? NSNumber)?.intValue, 429)
    XCTAssertNil(json["error_type"])

    let http = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: 12))
    XCTAssertNotEqual(skipped.failure, http.failure)
    XCTAssertEqual(try provenanceObject(http.provenanceJSON)["failure"] as? String, "http_error")
  }

  func testDecisionDecodeFailureRecordsADistinctClassFromHttpFailure() throws {
    let http = ProactiveLaneFailureClassification.classify(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: nil))
    let decodeError: Error
    do {
      _ = try JSONDecoder().decode(ContextDirectorDecision.self, from: Data(#"{"decision":1}"#.utf8))
      return XCTFail("expected the production decision decoder to reject a malformed payload")
    } catch {
      decodeError = error
    }
    XCTAssertTrue(decodeError is DecodingError)
    let decoded = ProactiveLaneFailureClassification.classify(decodeError)
    XCTAssertEqual(decoded.failure, "decode")
    XCTAssertNotEqual(decoded.failure, http.failure)
    let json = try provenanceObject(decoded.provenanceJSON)
    XCTAssertEqual(json["failure"] as? String, "decode")
    XCTAssertNil(json["status"])
  }

  func testInvalidResponseAndNetworkFailuresUseBoundedClasses() throws {
    let invalid = ProactiveLaneFailureClassification.classify(ProactiveLaneClientError.invalidResponse)
    XCTAssertEqual(invalid.failure, "invalid_response")
    XCTAssertEqual(try provenanceObject(invalid.provenanceJSON)["failure"] as? String, "invalid_response")

    let timedOut = ProactiveLaneFailureClassification.classify(URLError(.timedOut))
    XCTAssertEqual(timedOut.failure, "network")
    XCTAssertEqual(timedOut.errorType, "timed_out")
    let json = try provenanceObject(timedOut.provenanceJSON)
    XCTAssertEqual(json["failure"] as? String, "network")
    XCTAssertEqual(json["error_type"] as? String, "timed_out")
  }

  func testVisitFreshnessRunsToCompletionOnlyWithinTheDeliveryValidityWindow() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: 1, bucketID: "bucket-a", startedAt: now)

    try queue.write { db in
      try db.execute(
        sql: "UPDATE context_visits SET outcome = 'active', endedAt = NULL WHERE id = 1")
      XCTAssertEqual(
        try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now),
        ContextVisitFreshness(fresh: true, endedAt: nil),
        "an active visit is always fresh")

      try db.execute(
        sql: "UPDATE context_visits SET outcome = 'completed', endedAt = ? WHERE id = 1",
        arguments: [now.addingTimeInterval(-5)])
      XCTAssertEqual(
        try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now),
        ContextVisitFreshness(fresh: true, endedAt: now.addingTimeInterval(-5)),
        "a departure five seconds ago must not kill the in-flight evaluation")

      try db.execute(
        sql: "UPDATE context_visits SET endedAt = ? WHERE id = 1",
        arguments: [now.addingTimeInterval(-ContextDeliveryBudget.deliveryValidityWindowSeconds)])
      XCTAssertTrue(
        try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now).fresh,
        "the validity window boundary is inclusive")

      try db.execute(
        sql: "UPDATE context_visits SET endedAt = ? WHERE id = 1",
        arguments: [now.addingTimeInterval(-120)])
      XCTAssertEqual(
        try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now),
        ContextVisitFreshness(fresh: false, endedAt: now.addingTimeInterval(-120)),
        "an evaluation that drags past the window after departure dies at its next guard")

      try db.execute(
        sql: "UPDATE context_visits SET endedAt = NULL WHERE id = 1")
      XCTAssertFalse(
        try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now).fresh,
        "a completed visit with no recorded departure time fails closed")
    }
  }

  func testVisitFreshnessRejectsDiscardedAndInterruptedOutcomesHoweverRecent() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: 1, bucketID: "bucket-a", startedAt: now)

    try queue.write { db in
      for outcome in ["discarded", "interrupted"] {
        try db.execute(
          sql: "UPDATE context_visits SET outcome = ?, endedAt = ? WHERE id = 1",
          arguments: [outcome, now.addingTimeInterval(-1)])
        XCTAssertFalse(
          try ContextBucketStore.visitFreshness(in: db, fence: fence, now: now).fresh,
          "a \(outcome) visit never earned a delivery, however recent")
      }
    }
  }

  func testVisitFreshnessFailsClosedWhenTheFenceIdentityDoesNotMatch() throws {
    let queue = try contextBucketDatabase()
    let now = Date(timeIntervalSince1970: 1_725_000_000)

    try queue.read { db in
      XCTAssertEqual(
        try ContextBucketStore.visitFreshness(
          in: db,
          fence: ContextVisitFence(
            visitID: 1, contextGeneration: 99, poolEpoch: 1, bucketID: "bucket-a", startedAt: now),
          now: now),
        .stale)
      XCTAssertEqual(
        try ContextBucketStore.visitFreshness(
          in: db,
          fence: ContextVisitFence(
            visitID: 999, contextGeneration: 1, poolEpoch: 1, bucketID: "bucket-a", startedAt: now),
          now: now),
        .stale)
    }
  }

  func testSnapshotBucketResolutionSurvivesACompletedVisitButNotADiscardedOne() throws {
    let queue = try contextBucketDatabase()

    try queue.write { db in
      // The fixture seeds visit 1 as completed: the snapshot path must still
      // resolve its bucket so a run-to-completion evaluation can assemble.
      XCTAssertEqual(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db, visitID: 1, contextGeneration: 1, poolEpoch: 1),
        "bucket-a")

      try db.execute(sql: "UPDATE context_visits SET outcome = 'discarded' WHERE id = 1")
      XCTAssertNil(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db, visitID: 1, contextGeneration: 1, poolEpoch: 1))
    }
  }

  func testDirectorFrameBoundRejectsTheNextContextsScreenAfterDeparture() {
    let startedAt = Date(timeIntervalSince1970: 1_725_000_000)
    let endedAt = startedAt.addingTimeInterval(13)

    XCTAssertFalse(
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: startedAt.addingTimeInterval(-1),
        storedAt: startedAt,
        startedAt: startedAt,
        endedAt: nil),
      "a frame captured before the visit began never grounds it")
    XCTAssertTrue(
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: startedAt.addingTimeInterval(30),
        storedAt: startedAt.addingTimeInterval(30),
        startedAt: startedAt,
        endedAt: nil),
      "an active visit keeps today's behavior: any frame at or after startedAt")
    XCTAssertTrue(
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: startedAt.addingTimeInterval(10),
        storedAt: startedAt.addingTimeInterval(10),
        startedAt: startedAt,
        endedAt: endedAt),
      "a frame captured and tracked during the visit grounds its departed evaluation")
    // The switch tick: the next context's frame is CAPTURED milliseconds before
    // the transition writes endedAt, so capture time cannot exclude it — but it
    // is only STORED after the transition persisted the departure.
    XCTAssertFalse(
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: endedAt.addingTimeInterval(-0.005),
        storedAt: endedAt.addingTimeInterval(0.010),
        startedAt: startedAt,
        endedAt: endedAt),
      "the next context's frame on the switch tick must not ground the departed visit")
    XCTAssertFalse(
      AssistantCoordinator.frameMayGroundDirector(
        captureTime: endedAt.addingTimeInterval(
          ContextDeliveryBudget.departedFrameCaptureEpsilonSeconds + 1),
        storedAt: endedAt.addingTimeInterval(
          ContextDeliveryBudget.departedFrameCaptureEpsilonSeconds + 1),
        startedAt: startedAt,
        endedAt: endedAt),
      "a frame captured after departure plus epsilon is the next context's screen")
  }

  private func provenanceObject(_ json: String) throws -> [String: Any] {
    let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
    return try XCTUnwrap(object as? [String: Any])
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

final class ContextProactivityDirectorFailureTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "director-lane-failure")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testEngineRecordsHttp429ProvenanceOnTypedLaneError() async throws {
    let deliveryID = try await seedAttemptedDelivery()
    let engine = ContextProactivityEngine(
      client: ProactiveLaneClient(authorization: { "Bearer test" }),
      store: .shared,
      dwellNanoseconds: 0)

    await engine.recordDirectorFailure(
      deliveryID: deliveryID,
      error: ProactiveLaneClientError.http(status: 429, retryAfterSeconds: 30))

    let row = try await fetchDelivery(id: deliveryID)
    XCTAssertEqual(row["lifecycleState"] as String?, "failed")
    XCTAssertEqual(row["decisionType"] as String?, "silence")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "http_error")
    XCTAssertEqual((provenance["status"] as? NSNumber)?.intValue, 429)
  }

  func testEngineRecordsQuotaCooldownProvenanceOnSelfSuppressedLaneError() async throws {
    let deliveryID = try await seedAttemptedDelivery()
    let engine = ContextProactivityEngine(
      client: ProactiveLaneClient(authorization: { "Bearer test" }),
      store: .shared,
      dwellNanoseconds: 0)

    await engine.recordDirectorFailure(
      deliveryID: deliveryID,
      error: ProactiveLaneClientError.quotaCooldown(retryAfterSeconds: 30))

    let row = try await fetchDelivery(id: deliveryID)
    XCTAssertEqual(row["lifecycleState"] as String?, "failed")
    XCTAssertEqual(row["decisionType"] as String?, "silence")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "quota_cooldown")
    XCTAssertEqual((provenance["status"] as? NSNumber)?.intValue, 429)
    XCTAssertNil(provenance["error_type"])
  }

  func testEngineRecordsDecodeProvenanceDistinctFromHttpError() async throws {
    let deliveryID = try await seedAttemptedDelivery()
    let engine = ContextProactivityEngine(
      client: ProactiveLaneClient(authorization: { "Bearer test" }),
      store: .shared,
      dwellNanoseconds: 0)
    let decodeError: Error
    do {
      _ = try JSONDecoder().decode(ContextDirectorDecision.self, from: Data(#"{"decision":1}"#.utf8))
      return XCTFail("expected the production decision decoder to reject a malformed payload")
    } catch {
      decodeError = error
    }

    await engine.recordDirectorFailure(deliveryID: deliveryID, error: decodeError)

    let row = try await fetchDelivery(id: deliveryID)
    XCTAssertEqual(row["lifecycleState"] as String?, "failed")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "decode")
    XCTAssertNil(provenance["status"])
  }

  func testGraduationFailureKeepsDirectorDecisionAndBucketProvenance() async throws {
    let deliveryID = try await seedAttemptedDelivery()
    let versionID = try await fetchDelivery(id: deliveryID)["bucketVersionID"] as Int64
    let provenanceJSON =
      String(
        data: try JSONSerialization.data(
          withJSONObject: [
            "bucket_entry_refs": ["entry:one"],
            "bucket_id": "bucket",
            "bucket_version_id": versionID,
            "fact_ids": ["fact:one"],
          ],
          options: [.sortedKeys]),
        encoding: .utf8) ?? "{}"
    let store = ContextBucketStore.shared
    let advanced = try await store.completeDelivery(
      id: deliveryID,
      decisionType: "task_candidate",
      provenanceJSON: provenanceJSON,
      message: "commitment",
      state: "policy_approved")
    XCTAssertTrue(advanced)
    let engine = ContextProactivityEngine(
      client: ProactiveLaneClient(authorization: { "Bearer test" }),
      store: store,
      dwellNanoseconds: 0)

    await engine.recordGraduationFailure(
      deliveryID: deliveryID,
      decisionType: "task_candidate",
      provenanceJSON: provenanceJSON,
      message: "commitment",
      reason: .stale)

    let row = try await fetchDelivery(id: deliveryID)
    XCTAssertEqual(row["decisionType"] as String?, "task_candidate")
    XCTAssertEqual(row["lifecycleState"] as String?, "failed")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "candidate_graduation_failed")
    XCTAssertEqual(provenance["graduation_reason"] as? String, "stale")
    XCTAssertEqual(provenance["bucket_id"] as? String, "bucket")
    XCTAssertEqual((provenance["bucket_version_id"] as? NSNumber)?.int64Value, versionID)
    XCTAssertEqual(provenance["bucket_entry_refs"] as? [String], ["entry:one"])
    XCTAssertEqual(provenance["fact_ids"] as? [String], ["fact:one"])
  }

  private func seedAttemptedDelivery() async throws -> String {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await pool.write { db -> Int64 in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'director-failure', ?, ?)
          """,
        arguments: [now, now])
      try db.execute(
        sql: """
          INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, createdAt)
          VALUES ('bucket', 1, 'header', ?, ?)
          """,
        arguments: [Data(), now])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, ?, 'bucket', 'Director Failure', 'raw', 'normalized', 'reference', ?, 'active', ?, ?)
          """,
        arguments: [poolEpoch, now, now, now])
      return try Int64.fetchOne(
        db,
        sql: "SELECT id FROM bucket_versions WHERE bucketID = 'bucket' AND version = 1")
        ?? 0
    }
    let attempt = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: ContextVisitFence(
        visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket", startedAt: now),
      snapshot: ContextBucketSnapshot(
        bucketID: "bucket",
        versionID: versionID,
        version: 1,
        header: "header",
        frozenRankedSegment: Data(),
        tail: ["entry:one"],
        validatedFacts: ["fact:one statement"],
        notifyWorthiness: 1),
      gate: ContextDeliveryGateInput(
        masterEnabled: true,
        frequencyLevel: 5,
        paywalled: false,
        cooldownSeconds: 0),
      now: now)
    return try XCTUnwrap(attempt.id)
  }

  private func fetchDelivery(id: String) async throws -> Row {
    let (database, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    return try await pool.read { db in
      try XCTUnwrap(
        Row.fetchOne(db, sql: "SELECT * FROM proactive_deliveries WHERE id = ?", arguments: [id]))
    }
  }

  private func provenanceObject(_ json: String) throws -> [String: Any] {
    let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
    return try XCTUnwrap(object as? [String: Any])
  }
}
