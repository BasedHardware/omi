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

  func testNonSilenceGroundingIsPerDecisionType() {
    // insight/suggest/task_candidate make new claims about bucket content and
    // keep the full anti-hallucination invariant: one entry ref AND one fact ref.
    for decision in ["insight", "suggest", "task_candidate"] {
      XCTAssertTrue(
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision, entryRefs: ["entry:one"], factIDs: ["fact:one"]))
      XCTAssertFalse(
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision, entryRefs: ["entry:one"], factIDs: []))
      XCTAssertFalse(
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision, entryRefs: [], factIDs: ["fact:one"]))
    }
    // A resurface grounds on an open task connected to current context; its
    // citable half is the validated fact evidencing the connection. Nine of
    // these were vetoed in one dogfood window by the old unconditional AND.
    XCTAssertTrue(
      ContextDirectorGrounding.permitsNonSilence(
        decision: "resurface", entryRefs: [], factIDs: ["fact:one"]))
    XCTAssertTrue(
      ContextDirectorGrounding.permitsNonSilence(
        decision: "resurface", entryRefs: ["entry:one"], factIDs: []))
    XCTAssertFalse(
      ContextDirectorGrounding.permitsNonSilence(
        decision: "resurface", entryRefs: [], factIDs: []),
      "a resurface with no citation of either kind stays vetoed")
  }

  func testRetrievedRefsGroundInsightAndSuggestOnly() {
    // The answer to a question the user is writing lives in retrieved history,
    // not in this screen's bucket — an insight/suggest citing a hop-validated
    // retrieved ref must survive the veto even with no bucket grounding.
    for decision in ["insight", "suggest"] {
      XCTAssertTrue(
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision, entryRefs: [], factIDs: [],
          retrievedRefs: ["memory:abc"]))
    }
    // task_candidate keeps the strict bucket invariant regardless of retrieval.
    XCTAssertFalse(
      ContextDirectorGrounding.permitsNonSilence(
        decision: "task_candidate", entryRefs: [], factIDs: [],
        retrievedRefs: ["memory:abc"]))
    // No retrieved refs -> unchanged behavior for every type.
    for decision in ["insight", "suggest", "task_candidate"] {
      XCTAssertFalse(
        ContextDirectorGrounding.permitsNonSilence(
          decision: decision, entryRefs: [], factIDs: [], retrievedRefs: []))
    }
    // resurface keeps its bucket/fact-only rule: retrieval never grounds it.
    XCTAssertFalse(
      ContextDirectorGrounding.permitsNonSilence(
        decision: "resurface", entryRefs: [], factIDs: [],
        retrievedRefs: ["conversation:xyz"]))
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

  func testDepartureEvaluationTriggersOnlyAtTheWorthinessThresholdWithTheFlagOn() {
    XCTAssertFalse(
      ContextDepartureEvaluationPolicy.triggers(
        maximumValidatedWorthiness: 0.59, flagEnabled: true))
    XCTAssertTrue(
      ContextDepartureEvaluationPolicy.triggers(
        maximumValidatedWorthiness: 0.6, flagEnabled: true))
    XCTAssertFalse(
      ContextDepartureEvaluationPolicy.triggers(
        maximumValidatedWorthiness: 1.0, flagEnabled: false),
      "the feature flag gates the departure path entirely")
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
    XCTAssertEqual(
      row["decisionType"] as String?, ContextDeliveryLifecycle.unresolvedDecisionType,
      "a transport failure never produced a director decision")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "http_error")
    XCTAssertEqual((provenance["status"] as? NSNumber)?.intValue, 429)
  }

  func testEngineRecordsHttp502AsUnresolvedRatherThanSilence() async throws {
    let deliveryID = try await seedAttemptedDelivery()
    let engine = ContextProactivityEngine(
      client: ProactiveLaneClient(authorization: { "Bearer test" }),
      store: .shared,
      dwellNanoseconds: 0)

    await engine.recordDirectorFailure(
      deliveryID: deliveryID,
      error: ProactiveLaneClientError.http(status: 502, retryAfterSeconds: nil))

    let row = try await fetchDelivery(id: deliveryID)
    XCTAssertEqual(row["lifecycleState"] as String?, "failed")
    XCTAssertEqual(row["decisionType"] as String?, ContextDeliveryLifecycle.unresolvedDecisionType)
    XCTAssertNotEqual(row["decisionType"] as String?, "silence")
    let provenance = try provenanceObject(try XCTUnwrap(row["provenanceJson"] as String?))
    XCTAssertEqual(provenance["failure"] as? String, "http_error")
    XCTAssertEqual((provenance["status"] as? NSNumber)?.intValue, 502)
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
    XCTAssertEqual(
      row["decisionType"] as String?, ContextDeliveryLifecycle.unresolvedDecisionType,
      "quota cooldown is a lane skip, not a silence decision")
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
    XCTAssertEqual(row["decisionType"] as String?, ContextDeliveryLifecycle.unresolvedDecisionType)
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

final class ContextDepartureEvaluationStoreTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "departure-evaluation-store")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testWorkstreamTagsPersistPoolAcrossBucketsAndResolveTheLiveTag() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    try await seedBucket(in: pool, now: now)
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket-b', 'task', 'workstream-sibling', ?, ?)
          """,
        arguments: [now, now])
      try Self.insertVisit(
        db, id: 1, poolEpoch: poolEpoch, outcome: "completed",
        startedAt: now.addingTimeInterval(-13), endedAt: now)
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
          VALUES (2, 1, ?, 'bucket-b', 'Sibling App', 'raw', 'normalized', 'reference-b', ?, ?,
                  'completed', ?, ?)
          """,
        arguments: [poolEpoch, now.addingTimeInterval(-60), now.addingTimeInterval(-40), now, now])
    }
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
      startedAt: now.addingTimeInterval(-13))
    let siblingFence = ContextVisitFence(
      visitID: 2, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket-b",
      startedAt: now.addingTimeInterval(-60))

    func fact(_ statement: String, worthiness: Double, visit: Int64) -> BucketExtraction.Fact {
      BucketExtraction.Fact(
        statement: statement,
        identifiers: ["identity"],
        evidenceText: "identity",
        evidenceRefs: ["visit:\(visit)"],
        confidence: 1,
        notifyWorthiness: worthiness)
    }
    // Extraction no longer writes workstream tags. Stamp historically tagged
    // rows so pooling — still wired, now dormant for new facts — stays covered.
    _ = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "own narrative",
        facts: [fact("own visit fact", worthiness: 0.7, visit: 1)]),
      for: fence, appName: "Test App", rawContextKey: "raw", normalizedContextKey: "normalized",
      now: now)
    _ = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "sibling narrative",
        facts: [
          fact("sibling poolable fact", worthiness: 0.8, visit: 2),
          fact("sibling weak fact", worthiness: 0.1, visit: 2),
          fact("Identifier proposal: visit:2", worthiness: 0.9, visit: 2),
        ]),
      for: siblingFence, appName: "Sibling App", rawContextKey: "raw",
      normalizedContextKey: "normalized", now: now.addingTimeInterval(-30))

    let storedStatements = try await pool.read { db in
      try String.fetchAll(db, sql: "SELECT statement FROM bucket_facts ORDER BY statement")
    }
    XCTAssertEqual(
      storedStatements,
      ["own visit fact", "sibling poolable fact", "sibling weak fact"])
    let tagsBeforeStamp = try await pool.read { db in
      try String.fetchAll(
        db, sql: "SELECT workstreamTag FROM bucket_facts WHERE workstreamTag IS NOT NULL")
    }
    XCTAssertEqual(tagsBeforeStamp, [])

    try await pool.write { db in
      try db.execute(sql: "UPDATE bucket_facts SET workstreamTag = 'omi-app'")
    }

    let liveTag = await ContextBucketStore.shared.liveWorkstreamTag(for: fence, now: now)
    XCTAssertEqual(liveTag, "omi-app")

    let candidates = await ContextBucketStore.shared.workstreamPool(
      tag: "omi-app", excludingBucketID: "bucket", now: now)
    let selected = ContextWorkstreamPooling.select(candidates, now: now)
    XCTAssertEqual(selected.map(\.statement), ["sibling poolable fact"])
    XCTAssertEqual(selected.map(\.bucketID), ["bucket-b"])
    let section = try XCTUnwrap(
      ContextWorkstreamPooling.promptSection(tag: "omi-app", items: selected, now: now))
    XCTAssertTrue(section.contains("RELATED WORKSTREAM CONTEXT (omi-app)"))
    XCTAssertTrue(section.contains("sibling poolable fact"))
    XCTAssertFalse(section.contains("fact:"), "pooled facts must never expose citable refs")
  }

  func testWriteExtractionReportsTheMaximumWorthinessOfNewlyValidatedFactsOnly() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    try await seedBucket(in: pool, now: now)
    try await pool.write { db in
      try Self.insertVisit(
        db, id: 1, poolEpoch: poolEpoch, outcome: "completed",
        startedAt: now.addingTimeInterval(-13), endedAt: now)
    }
    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now.addingTimeInterval(-13))

    let result = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "narrative",
        facts: [
          BucketExtraction.Fact(
            statement: "validated commitment",
            identifiers: ["deadline"],
            evidenceText: "deadline evidence",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.6),
          // No identifier, but resolvable evidence: validates under
          // evidence-only validity, so its 0.9 IS the admission signal. (The
          // old identifier gate demoted this shape to needs_review and zeroed
          // it — measured at zero discriminative value on live data.)
          BucketExtraction.Fact(
            statement: "unidentified claim",
            identifiers: [],
            evidenceText: "evidence",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.9),
          // Unresolvable evidence still demotes and must not count.
          BucketExtraction.Fact(
            statement: "evidence-free claim",
            identifiers: ["handle"],
            evidenceText: " ",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 1.0),
        ]),
      for: fence,
      appName: "Test App",
      rawContextKey: "raw",
      normalizedContextKey: "normalized",
      now: now)

    let writeResult = try XCTUnwrap(result)
    XCTAssertEqual(writeResult.maximumValidatedWorthiness, 0.9, accuracy: 0.000_001)
    XCTAssertTrue(
      ContextDepartureEvaluationPolicy.triggers(
        maximumValidatedWorthiness: writeResult.maximumValidatedWorthiness, flagEnabled: true))

    let below = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "narrative two",
        facts: [
          BucketExtraction.Fact(
            statement: "mild update",
            identifiers: ["status"],
            evidenceText: "status evidence",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.59)
        ]),
      for: fence,
      appName: "Test App",
      rawContextKey: "raw",
      normalizedContextKey: "normalized",
      now: now.addingTimeInterval(1))
    let belowResult = try XCTUnwrap(below)
    XCTAssertFalse(
      ContextDepartureEvaluationPolicy.triggers(
        maximumValidatedWorthiness: belowResult.maximumValidatedWorthiness, flagEnabled: true))
  }

  func testWriteExtractionDropsScaffoldingGatesIdentifiersAndLeavesWorkstreamNull() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    try await seedBucket(in: pool, now: now)
    try await pool.write { db in
      try Self.insertVisit(
        db, id: 1, poolEpoch: poolEpoch, outcome: "completed",
        startedAt: now.addingTimeInterval(-13), endedAt: now)
    }
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
      startedAt: now.addingTimeInterval(-13))

    _ = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "narrative",
        facts: [
          BucketExtraction.Fact(
            statement: "Ambient narrative: A Finder window labeled Downloads sits in the foreground",
            identifiers: ["Downloads"],
            evidenceText: "A Finder window labeled Downloads sits in the foreground",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.9),
          BucketExtraction.Fact(
            statement: "Proposed fact 1 — The board was lying",
            identifiers: ["board"],
            evidenceText: "The board was lying",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.8),
          BucketExtraction.Fact(
            statement: "Nik asked for the demo recording before tomorrow's launch video.",
            identifiers: ["fact-001", "f-002", "ftn-003", "visit:9", "screenshot:42", "Nik"],
            evidenceText: "Nik asked for the demo recording before tomorrow's launch video.",
            evidenceRefs: ["visit:1"],
            confidence: 1,
            notifyWorthiness: 0.7),
        ]),
      for: fence, appName: "Test App", rawContextKey: "raw", normalizedContextKey: "normalized",
      now: now)

    let rows = try await pool.read { db in
      try Row.fetchAll(
        db,
        sql: """
          SELECT statement, identifiersJson, workstreamTag FROM bucket_facts
          ORDER BY statement
          """)
    }
    XCTAssertEqual(rows.count, 1)
    XCTAssertEqual(
      rows.first?["statement"] as String?,
      "Nik asked for the demo recording before tomorrow's launch video.")
    XCTAssertNil(rows.first?["workstreamTag"] as String?)
    let encoded = try XCTUnwrap(rows.first?["identifiersJson"] as String?)
    let identifiers = try JSONDecoder().decode([String].self, from: Data(encoded.utf8))
    XCTAssertEqual(identifiers, ["Nik"])
  }

  func testWriteExtractionAppliesWritePolicyOnlyWhenEnabled() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    try await seedBucket(in: pool, now: now)
    try await pool.write { db in
      try Self.insertVisit(
        db, id: 1, poolEpoch: poolEpoch, outcome: "completed",
        startedAt: now.addingTimeInterval(-13), endedAt: now)
    }
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
      startedAt: now.addingTimeInterval(-13))
    let extraction = BucketExtraction(
      narrative: "narrative",
      facts: [
        // Machinery echo: must not be stored at all when the policy applies.
        BucketExtraction.Fact(
          statement: "The destination is unknown/.",
          identifiers: ["unknown"],
          evidenceText: "The destination is unknown/.",
          evidenceRefs: ["visit:1"],
          confidence: 1,
          notifyWorthiness: 0.6),
        // Scenery: stored, worthiness capped to 0 so it can never arm.
        BucketExtraction.Fact(
          statement: "A Google Sheets document named Combined_Cap_Table is open in a tab.",
          identifiers: ["Combined_Cap_Table"],
          evidenceText: "Combined_Cap_Table is open in a tab.",
          evidenceRefs: ["visit:1"],
          confidence: 1,
          notifyWorthiness: 0.8),
        // Named-person speech act: floored to arming eligibility from nano's 0.0.
        BucketExtraction.Fact(
          statement: "Mihir Malde thanked flagging the issue and said the team is fixing it.",
          identifiers: ["Mihir Malde"],
          evidenceText: "Mihir Malde thanked flagging the issue and said the team is fixing it.",
          evidenceRefs: ["visit:1"],
          confidence: 1,
          notifyWorthiness: 0.0),
      ])

    let result = try await ContextBucketStore.shared.writeExtraction(
      extraction, for: fence, appName: "Test App", rawContextKey: "raw",
      normalizedContextKey: "normalized", applyWritePolicy: true, now: now)
    let rows = try await pool.read { db in
      try Row.fetchAll(
        db, sql: "SELECT statement, notifyWorthiness FROM bucket_facts ORDER BY statement")
    }
    XCTAssertEqual(rows.count, 2, "the machinery echo must not be stored")
    XCTAssertEqual(
      rows.first?["statement"] as String?,
      "A Google Sheets document named Combined_Cap_Table is open in a tab.")
    XCTAssertEqual(rows.first?["notifyWorthiness"] as Double? ?? -1, 0, "scenery must not arm")
    XCTAssertEqual(
      rows.last?["notifyWorthiness"] as Double? ?? -1,
      ContextFactWritePolicy.humanEventWorthinessFloor,
      "a named-person speech act must reach arming eligibility")
    // The floored human event is what departure evaluation should key on.
    XCTAssertEqual(
      try XCTUnwrap(result).maximumValidatedWorthiness,
      ContextFactWritePolicy.humanEventWorthinessFloor, accuracy: 0.000_001)

    // Policy off: the same extraction stores all three facts with nano's raw
    // scores — byte-identical to the pre-policy write path.
    try await pool.write { db in
      try db.execute(sql: "DELETE FROM bucket_facts")
      try db.execute(sql: "DELETE FROM bucket_entries")
    }
    _ = try await ContextBucketStore.shared.writeExtraction(
      extraction, for: fence, appName: "Test App", rawContextKey: "raw",
      normalizedContextKey: "normalized", now: now.addingTimeInterval(1))
    let unfiltered = try await pool.read { db in
      try Row.fetchAll(
        db, sql: "SELECT statement, notifyWorthiness FROM bucket_facts ORDER BY statement")
    }
    XCTAssertEqual(unfiltered.count, 3)
    XCTAssertEqual(unfiltered.map { $0["notifyWorthiness"] as Double? ?? -1 }, [0.8, 0.0, 0.6])
  }

  private func seedBucket(in pool: DatabasePool, now: Date) async throws {
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'departure-evaluation', ?, ?)
          """,
        arguments: [now, now])
    }
  }

  private static func insertVisit(
    _ db: Database, id: Int64, poolEpoch: Int, outcome: String, startedAt: Date, endedAt: Date?
  ) throws {
    try db.execute(
      sql: """
        INSERT INTO context_visits
          (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
           normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
        VALUES (?, 1, ?, 'bucket', 'Test App', 'raw', 'normalized', ?, ?, ?, ?, ?, ?)
        """,
      arguments: [id, poolEpoch, "reference-\(id)", startedAt, endedAt, outcome, startedAt, startedAt])
  }

  func testClampedStripsInlineRefTokensFromVisibleText() {
    let decision = ContextDirectorDecision(
      decision: "insight",
      title: "Download link [memory:abc-123]",
      message: "The link is omi.me/desktop. [memory:3fe5b70f-f445-4580-b353-7b0d2560de3f]",
      reasoning: "r",
      bucketEntryRefs: ["memory:abc-123"],
      factIDs: []
    ).clamped()
    XCTAssertEqual(decision.title, "Download link")
    XCTAssertEqual(decision.message, "The link is omi.me/desktop.")
    XCTAssertEqual(decision.bucketEntryRefs, ["memory:abc-123"], "citations stay citations")
  }

  @MainActor
  func testDwellCaptureGuardRejectsSameAppTitleSwitch() async {
    // Prime the tracker (buckets disabled so no store writes), then a same-app
    // title switch must invalidate the old context for the dwell capture guard.
    _ = await AssistantCoordinator.shared.checkContextSwitch(
      newApp: "GuardTestApp", newWindowTitle: "Original Title", bucketsEnabled: false)
    XCTAssertTrue(
      AssistantCoordinator.shared.isTracking(app: "GuardTestApp", windowTitle: "Original Title"))
    _ = await AssistantCoordinator.shared.checkContextSwitch(
      newApp: "GuardTestApp", newWindowTitle: "Different Document", bucketsEnabled: false)
    XCTAssertFalse(
      AssistantCoordinator.shared.isTracking(app: "GuardTestApp", windowTitle: "Original Title"),
      "a same-app title switch during the async capture must drop the stale frame")
    XCTAssertFalse(
      AssistantCoordinator.shared.isTracking(app: "OtherApp", windowTitle: "Different Document"))
    XCTAssertTrue(
      AssistantCoordinator.shared.isTracking(
        app: "GuardTestApp", windowTitle: "Different Document"))
  }
}
