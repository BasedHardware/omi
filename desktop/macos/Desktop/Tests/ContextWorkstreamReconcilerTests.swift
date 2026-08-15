import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextWorkstreamReconcilerTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  func testBatchSelectionRanksUntaggedThenFactCountThenRecencyAndCapsExploration() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      // 16 eligible buckets: first 14 untagged with decreasing fact counts,
      // then 2 tagged with high fact counts that must sort after untagged.
      for index in 1...14 {
        try seedBucket(
          "u-\(index)", factCount: 17 - index,
          newestOffset: TimeInterval(index), tagged: false, in: db)
      }
      try seedBucket("t-high", factCount: 40, newestOffset: 0, tagged: true, in: db)
      try seedBucket("t-mid", factCount: 20, newestOffset: 0, tagged: true, in: db)
      try seedBucket("too-few", factCount: 2, newestOffset: 0, tagged: false, in: db)
    }

    let eligible = try queue.read { db in
      try ContextWorkstreamBatchSelection.fetchEligible(in: db, now: now)
    }
    XCTAssertFalse(eligible.contains { $0.bucketID == "too-few" })
    XCTAssertEqual(eligible.first?.bucketID, "u-1", "untagged + most facts ranks first")
    XCTAssertEqual(Array(eligible.map(\.bucketID).prefix(14)), (1...14).map { "u-\($0)" })
    XCTAssertEqual(
      eligible.suffix(2).map(\.bucketID), ["t-high", "t-mid"],
      "tagged buckets sort after every untagged eligible bucket")

    let ranked = eligible.map(\.bucketID)
    let swapped = ContextWorkstreamBatchSelection.applyExploration(rankedIDs: ranked) { pool, count in
      Array(pool.suffix(count))
    }
    XCTAssertEqual(swapped.count, 12)
    XCTAssertEqual(Array(swapped.prefix(10)), (1...10).map { "u-\($0)" })
    XCTAssertEqual(Array(swapped.suffix(2)), ["t-high", "t-mid"])
    XCTAssertFalse(swapped.contains("u-11"))
    XCTAssertFalse(swapped.contains("u-12"))

    let capped = ContextWorkstreamBatchSelection.applyExploration(rankedIDs: ranked) { pool, _ in
      pool
    }
    XCTAssertEqual(capped.count, ContextWorkstreamBatchSelection.batchCap)
    XCTAssertEqual(Array(capped.prefix(10)), (1...10).map { "u-\($0)" })
  }

  func testBatchSelectionKeepsAShortRankingIntact() {
    XCTAssertEqual(
      ContextWorkstreamBatchSelection.applyExploration(rankedIDs: ["a", "b", "c"]),
      ["a", "b", "c"])
  }

  func testSelectFactsDropsScaffoldingAndKeepsHighestWorthiness() {
    let facts = [
      fact("scaffold", statement: "Identifier proposal: visit:1", worthiness: 0.99),
      fact("weak", worthiness: 0.4),
      fact("strong", worthiness: 0.9),
      fact("mid", worthiness: 0.7),
      fact("also-strong", worthiness: 0.85),
      fact("fifth", worthiness: 0.6),
      fact("sixth", worthiness: 0.55),
    ]
    XCTAssertEqual(
      ContextWorkstreamBatchSelection.selectFacts(facts).map(\.id),
      ["strong", "also-strong", "mid", "fifth", "sixth"])
  }

  func testLabelSanitisationAndInsertOrIgnoreNeverDeletesAnExistingAssignment() throws {
    XCTAssertEqual(ContextWorkstreamTag.sanitize("Hermes"), "hermes")
    XCTAssertNil(ContextWorkstreamTag.sanitize("unknown"))
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("bucket-a", factCount: 3, newestOffset: 0, tagged: false, in: db)
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: "bucket-a", tag: "hermes", now: now, in: db)
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: "bucket-a", tag: "hermes", now: now.addingTimeInterval(60), in: db)
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: "bucket-a", tag: "car", now: now, in: db)
    }
    let rows = try queue.read { db in
      try Row.fetchAll(
        db, sql: "SELECT tag FROM bucket_workstreams WHERE bucketID = 'bucket-a' ORDER BY tag")
    }
    XCTAssertEqual(rows.map { $0["tag"] as String }, ["car", "hermes"])
  }

  func testAcceptedAssignmentsRequireTwoGroupsForANewLabelAndKeepExistingOnes() {
    let response = ContextWorkstreamTagging.Response(
      workstreams: [
        .init(label: "Hermes", evidence: "two groups"),
        .init(label: "solo", evidence: "one group"),
      ],
      assignments: [
        .init(group: "G1", label: "Hermes"),
        .init(group: "G2", label: "Hermes"),
        .init(group: "G3", label: "solo"),
        .init(group: "G4", label: "car"),
        .init(group: "G5", label: nil),
      ])
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: response,
      batchIDs: ["b1", "b2", "b3", "b4", "b5"],
      existingTags: ["car"],
      observations: "Hermes PR blocked. CAR contract review. solo note.")
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["b1:hermes", "b2:hermes", "b4:car"])
    XCTAssertFalse(accepted.contains { $0.tag == "solo" })
    XCTAssertFalse(accepted.contains { $0.bucketID == "b5" })
  }

  func testCandidateLookupPrefersABucketMatchOverANewerWorkstreamMatch() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 3, newestOffset: 0, tagged: true, in: db)
      try seedBucket("other", factCount: 3, newestOffset: 0, tagged: true, in: db)
      try insertCandidate(
        id: "bucket-hit", bucketID: "here", tag: nil,
        message: "the Hermes PR still needs review", createdAt: now.addingTimeInterval(-120),
        in: db)
      try insertCandidate(
        id: "workstream-hit", bucketID: "other", tag: "hermes",
        message: "CAR signature is due Friday", createdAt: now.addingTimeInterval(-10),
        in: db)
    }
    let found = try queue.read { db in
      try ContextProactiveCandidateLookup.lookupArmed(
        bucketID: "here", tags: ["hermes"], now: now, in: db)
    }
    XCTAssertEqual(found.map(\.id), ["bucket-hit", "workstream-hit"])
  }

  func testDuplicateSuppressionSkipsACandidateThatRepeatsARecentDelivery() {
    let bucketHit = ContextProactiveCandidate(
      id: "dup", bucketID: "here", workstreamTag: nil,
      message: "the Hermes PR still needs review",
      groundingFactIDsJson: "[\"f1\"]", triggerNote: "when the PR is open",
      state: "armed", createdAt: now, expiresAt: now.addingTimeInterval(60), consumedAt: nil)
    let other = ContextProactiveCandidate(
      id: "fresh", bucketID: "here", workstreamTag: nil,
      message: "CAR signature is due Friday",
      groundingFactIDsJson: "[\"f2\"]", triggerNote: "when the contract is open",
      state: "armed", createdAt: now, expiresAt: now.addingTimeInterval(60), consumedAt: nil)
    XCTAssertNil(
      ContextProactiveCandidateLookup.firstDeliverable(
        candidates: [bucketHit],
        recentMessages: ["The Hermes PR still needs review"]))
    XCTAssertEqual(
      ContextProactiveCandidateLookup.firstDeliverable(
        candidates: [bucketHit, other],
        recentMessages: ["The Hermes PR still needs review"])?.id,
      "fresh")
  }

  func testGateResponseParsingAcceptsBooleansAndFailsClosedOnMalformedPayloads() {
    XCTAssertEqual(
      ContextProactiveCandidateGate.parse(#"{"show":true,"reason":"adds a deadline"}"#),
      ContextProactiveCandidateGate.Decision(show: true, reason: "adds a deadline"))
    XCTAssertEqual(
      ContextProactiveCandidateGate.parse(#"{"show":false,"reason":"already on screen"}"#)?.show,
      false)
    XCTAssertNil(ContextProactiveCandidateGate.parse("{"))
    XCTAssertNil(ContextProactiveCandidateGate.parse(#"{"show":"yes","reason":"nope"}"#))
    XCTAssertNil(ContextProactiveCandidateGate.parse(#"{"reason":"missing show"}"#))
  }

  func testCandidateWriterDropsGroundingThatIsNotPresentAndValidated() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 3, newestOffset: 0, tagged: false, in: db)
      let valid = try ContextProactiveCandidateWriter.validatedFactIDs(
        ["here-0", "missing"], bucketID: "here", now: now, in: db)
      XCTAssertEqual(valid, ["here-0"])
      try db.execute(sql: "UPDATE bucket_facts SET validityState = 'rejected' WHERE id = 'here-1'")
      XCTAssertEqual(
        try ContextProactiveCandidateWriter.validatedFactIDs(
          ["here-1"], bucketID: "here", now: now, in: db),
        [])
    }
  }

  private func fact(
    _ id: String, statement: String = "a concrete fact", worthiness: Double
  ) -> ContextWorkstreamBatchFact {
    ContextWorkstreamBatchFact(
      id: id, bucketID: "b", appName: "App", statement: statement,
      notifyWorthiness: worthiness, createdAt: now)
  }

  private func seedBucket(
    _ id: String, factCount: Int, newestOffset: TimeInterval, tagged: Bool, in db: Database
  ) throws {
    try db.execute(
      sql: """
        INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
        VALUES (?, 'task', ?, ?, ?)
        """,
      arguments: [id, id, now, now])
    let visitID =
      (try Int64.fetchOne(db, sql: "SELECT COALESCE(MAX(id), 0) FROM context_visits") ?? 0) + 1
    try db.execute(
      sql: """
        INSERT INTO context_visits
          (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
           normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
        VALUES (?, 1, 1, ?, 'App', 'raw', 'normalized', ?, ?, 'completed', ?, ?)
        """,
      arguments: [visitID, id, "ref-\(id)", now, now, now])
    try db.execute(
      sql: """
        INSERT INTO bucket_entries
          (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
           narrative, evidenceRefsJson, tokenCount, createdAt)
        VALUES (?, ?, ?, 'App', 'raw', 'normalized', 'narrative', '[]', 1, ?)
        """,
      arguments: ["entry-\(id)", id, visitID, now])
    for index in 0..<factCount {
      try db.execute(
        sql: """
          INSERT INTO bucket_facts
            (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
             evidenceRefsJson, validityState, dispositionState, confidence,
             notifyWorthiness, createdAt, updatedAt)
          VALUES (?, ?, ?, 'App', ?, '[]', 'evidence', '[]', 'validated', 'none', 1, 0.7, ?, ?)
          """,
        arguments: [
          "\(id)-\(index)", id, "entry-\(id)", "fact \(index) about \(id)",
          now.addingTimeInterval(-newestOffset - TimeInterval(index)), now,
        ])
    }
    if tagged {
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: id, tag: "hermes", now: now, in: db)
    }
  }

  private func insertCandidate(
    id: String, bucketID: String, tag: String?, message: String, createdAt: Date, in db: Database
  ) throws {
    try db.execute(
      sql: """
        INSERT INTO proactive_candidates
          (id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote,
           state, createdAt, expiresAt)
        VALUES (?, ?, ?, ?, '["f1"]', 'when relevant', 'armed', ?, ?)
        """,
      arguments: [id, bucketID, tag, message, createdAt, now.addingTimeInterval(12 * 60 * 60)])
  }

  private func migratedQueue() throws -> DatabaseQueue {
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
      UserDefaults(suiteName: "ContextWorkstreamReconcilerTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }
}
