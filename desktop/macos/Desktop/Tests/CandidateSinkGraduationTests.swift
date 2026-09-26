import GRDB
import XCTest

@testable import Omi_Computer

final class CandidateSinkGraduationTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var previousOwnerID: String?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "candidate-graduation")
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionOwner(to: fixture?.testUserId)
  }

  override func tearDown() async throws {
    await transitionOwner(to: previousOwnerID)
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testGraduationReasonsDistinguishEmptyFactsFromStaleFacts() async throws {
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let empty = await CandidateSink.shared.graduateValidatedFacts(
      deliveryID: "unused",
      factIDs: [],
      authorizationSnapshot: snapshot,
      now: now)
    XCTAssertEqual(empty, .noFactIDs)

    let seeded = try await seedDelivery(factDisposition: "candidate_pending", now: now)
    let stale = await CandidateSink.shared.graduateValidatedFacts(
      deliveryID: seeded.deliveryID,
      factIDs: ["current", "missing"],
      authorizationSnapshot: snapshot,
      now: now)
    XCTAssertEqual(stale, .stale)
    XCTAssertNotEqual(empty.rawValue, stale.rawValue)

    let emptyProvenance = CandidateGraduationProvenance.mergingFailure(
      into: #"{"bucket_id":"bucket"}"#, reason: empty)
    let staleProvenance = CandidateGraduationProvenance.mergingFailure(
      into: #"{"bucket_id":"bucket"}"#, reason: stale)
    XCTAssertEqual(
      try provenanceObject(emptyProvenance)["graduation_reason"] as? String, "no_fact_ids")
    XCTAssertEqual(try provenanceObject(staleProvenance)["graduation_reason"] as? String, "stale")
  }

  func testAlreadyPendingFactsGraduateWithoutChangingDisposition() async throws {
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let seeded = try await seedDelivery(factDisposition: "candidate_pending", now: now)

    let reason = await CandidateSink.shared.graduateValidatedFacts(
      deliveryID: seeded.deliveryID,
      factIDs: ["current"],
      authorizationSnapshot: snapshot,
      now: now)

    XCTAssertEqual(reason, .graduated)
    XCTAssertTrue(
      CandidateSinkDeliveryGate.mayPresentInteractively(
        decisionType: "task_candidate", graduation: reason))
    let (database, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let disposition = try await pool.read { db in
      try String.fetchOne(
        db, sql: "SELECT dispositionState FROM bucket_facts WHERE id = 'current'")
    }
    XCTAssertEqual(disposition, "candidate_pending")
  }

  private struct SeededDelivery {
    let deliveryID: String
  }

  private func seedDelivery(factDisposition: String, now: Date) async throws -> SeededDelivery {
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await pool.write { db -> Int64 in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'graduation-test', ?, ?)
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
          VALUES (1, 1, ?, 'bucket', 'Graduation', 'raw', 'normalized', 'reference', ?, 'active', ?, ?)
          """,
        arguments: [poolEpoch, now, now, now])
      let versionID =
        try Int64.fetchOne(
          db,
          sql: "SELECT id FROM bucket_versions WHERE bucketID = 'bucket' AND version = 1")
        ?? 0
      try db.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, bucketVersionID, appName, rawContextKey,
             normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
          VALUES ('entry-current', 'bucket', 1, ?, 'Graduation', 'raw', 'normalized', 'narrative', '[]', 1, ?)
          """,
        arguments: [versionID, now])
      try db.execute(
        sql: """
          INSERT INTO bucket_facts
            (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
             evidenceRefsJson, validityState, dispositionState, confidence,
             notifyWorthiness, createdAt, updatedAt)
          VALUES ('current', 'bucket', 'entry-current', 'Graduation', 'statement', '[]', 'evidence',
                  '[]', 'validated', ?, 1, 1, ?, ?)
          """,
        arguments: [factDisposition, now, now])
      return versionID
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
        tail: ["entry:current"],
        validatedFacts: ["fact:current statement"],
        notifyWorthiness: 1),
      gate: ContextDeliveryGateInput(
        masterEnabled: true,
        frequencyLevel: 5,
        paywalled: false,
        cooldownSeconds: 0),
      now: now)
    return SeededDelivery(deliveryID: try XCTUnwrap(attempt.id))
  }

  private func provenanceObject(_ json: String) throws -> [String: Any] {
    let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
    return try XCTUnwrap(object as? [String: Any])
  }

  private func transitionOwner(to ownerID: String?) async {
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        })
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }
}
