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
      observationsByBucket: [
        "b1": "Hermes PR blocked.",
        "b2": "Hermes PR blocked.",
        "b3": "solo note.",
        "b4": "CAR contract review.",
        "b5": "",
      ])
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["b1:hermes", "b2:hermes", "b4:car"])
    XCTAssertFalse(accepted.contains { $0.tag == "solo" })
    XCTAssertFalse(accepted.contains { $0.bucketID == "b5" })
  }

  func testLabelAppearsInObservationsRequiresAWholeWordNotAnIncidentalSubstring() {
    XCTAssertTrue(
      ContextWorkstreamTagging.labelAppearsInObservations(
        "car-project", observations: "The CAR contract review is due Friday."))
    XCTAssertFalse(
      ContextWorkstreamTagging.labelAppearsInObservations(
        "car-project", observations: "Please concatenate the two reports."),
      "\"car\" inside \"concatenate\" must not count as the word appearing")
  }

  func testAcceptedAssignmentsRejectALabelAbsentFromTheAssignedBucketsFacts() {
    let response = ContextWorkstreamTagging.Response(
      workstreams: [.init(label: "stably", evidence: "two groups")],
      assignments: [
        .init(group: "G1", label: "stably"),
        .init(group: "G2", label: "stably"),
      ])
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: response,
      batchIDs: ["cursor-agents", "github-pr"],
      existingTags: [],
      observationsByBucket: [
        "cursor-agents": "Screen content is from the Cursor app window labeled Cursor Agents.",
        "github-pr": "The stably deploy is green and the rate-card PR remains parked.",
      ])
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["github-pr:stably"],
      "a label earned by one bucket must not attach to another bucket in the same batch")
    XCTAssertFalse(
      accepted.contains { $0.bucketID == "cursor-agents" },
      "attestation must use the assigned bucket's own facts, not the rest of the batch")
  }

  func testGenericLabelsAreRejectedWhileRealProjectNamesAreAccepted() {
    let requiredNouns = [
      "api", "dashboard", "config", "meetings", "downloads", "standup", "docs",
      "chat", "email", "browser", "terminal", "settings", "notifications", "tasks",
      "calendar", "search", "updates", "release", "testing", "review", "research",
      "planning", "admin", "ops",
    ]
    for noun in requiredNouns {
      XCTAssertTrue(
        ContextWorkstreamTagging.genericLabels.contains(noun),
        "stop-list must include the measured generic noun \(noun)")
    }
    for label in ContextWorkstreamTagging.genericLabels {
      XCTAssertTrue(
        ContextWorkstreamTagging.isGenericLabel(label),
        "stop-list entry \(label) must be rejected")
    }
    for compound in [
      "cloud-meetings", "downloads-collection", "team-standups",
      "telecom-coordination", "config-management",
    ] {
      XCTAssertTrue(
        ContextWorkstreamTagging.isGenericLabel(compound),
        "every-token-generic compound \(compound) must be rejected")
    }
    XCTAssertFalse(ContextWorkstreamTagging.isGenericLabel("omi"))
    XCTAssertFalse(ContextWorkstreamTagging.isGenericLabel("hermes"))
    XCTAssertFalse(
      ContextWorkstreamTagging.isGenericLabel("omi-api"),
      "a real project name that happens to include a surface noun is not generic")

    let response = ContextWorkstreamTagging.Response(
      workstreams: [
        .init(label: "omi", evidence: "the product"),
        .init(label: "api", evidence: "four groups mentioned the API"),
        .init(label: "Hermes", evidence: "two groups"),
      ],
      assignments: [
        .init(group: "G1", label: "omi"),
        .init(group: "G2", label: "omi"),
        .init(group: "G3", label: "api"),
        .init(group: "G4", label: "api"),
        .init(group: "G5", label: "Hermes"),
        .init(group: "G6", label: "Hermes"),
        .init(group: "G7", label: "unknown"),
      ])
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: response,
      batchIDs: ["b1", "b2", "b3", "b4", "b5", "b6", "b7"],
      existingTags: ["api"],
      observationsByBucket: [
        "b1": "Omi release blocked on the Hermes PR.",
        "b2": "Omi release blocked on the Hermes PR.",
        "b3": "API rate limit on /v1/chat.",
        "b4": "API rate limit on /v1/chat.",
        "b5": "Omi release blocked on the Hermes PR.",
        "b6": "Omi release blocked on the Hermes PR.",
        "b7": "",
      ])
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["b1:omi", "b2:omi", "b5:hermes", "b6:hermes"])
    XCTAssertFalse(accepted.contains { $0.tag == "api" })
    XCTAssertFalse(
      accepted.contains { $0.bucketID == "b7" },
      "unknown abstention must still drop the assignment")
    XCTAssertNil(ContextWorkstreamTag.sanitize("unknown"))
  }

  func testAcceptedAssignmentsLetALaterValidAssignmentWinAfterAnEarlierInvalidOneForTheSameBucket() {
    let response = ContextWorkstreamTagging.Response(
      workstreams: [.init(label: "Hermes", evidence: "two groups")],
      assignments: [
        // b1's first assignment is null (a legitimate "no label" response)
        // and must not block b1's later valid assignment for the same group.
        .init(group: "G1", label: nil),
        .init(group: "G1", label: "Hermes"),
        .init(group: "G2", label: "Hermes"),
      ])
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: response,
      batchIDs: ["b1", "b2"],
      existingTags: [],
      observationsByBucket: [
        "b1": "Hermes PR blocked.",
        "b2": "Hermes PR blocked.",
      ])
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["b1:hermes", "b2:hermes"],
      "the invalid first assignment for b1 must not claim the bucket and drop the valid one")
  }

  func testAcceptedAssignmentsLetALaterValidProposalWinAfterAnUnattestableFirstOneForTheSameBucket() {
    let response = ContextWorkstreamTagging.Response(
      workstreams: [.init(label: "Hermes", evidence: "two groups")],
      assignments: [
        // b1's first proposal sanitizes but is absent from b1's own facts;
        // it must not claim the bucket and drop b1's later attestable one.
        .init(group: "G1", label: "Hermes"),
        .init(group: "G1", label: "Car"),
        .init(group: "G2", label: "Hermes"),
      ])
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: response,
      batchIDs: ["b1", "b2"],
      existingTags: ["car"],
      observationsByBucket: [
        "b1": "The CAR contract review is due.",
        "b2": "Hermes PR blocked.",
      ])
    XCTAssertEqual(
      Set(accepted.map { "\($0.bucketID):\($0.tag)" }),
      ["b1:car", "b2:hermes"],
      "an unattestable first proposal must not claim the bucket and drop the later valid one")
  }

  func testInsertArmedCandidatesLetsALaterValidCandidateWinAfterAnEarlierInvalidOneForTheSameBucket() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 3, newestOffset: 0, tagged: false, in: db)
    }
    let groups = [
      ContextWorkstreamReconcileGroup(
        bucketID: "here", facts: [], needsCandidate: true, workstreamTag: nil)
    ]
    let proposed: [ContextProactiveCandidateWriter.Response.Candidate] = [
      // First candidate for "here" is invalid (empty message) and must not
      // claim the bucket ahead of the later valid candidate.
      .init(bucket: "here", message: "   ", factIDs: ["fact:here-0"], triggerNote: "when relevant"),
      .init(
        bucket: "here", message: "the Hermes PR still needs review", factIDs: ["fact:here-0"],
        triggerNote: "when relevant"),
    ]
    try queue.write { db in
      try ContextProactiveCandidateWriter.insertValidatedCandidates(
        proposed, groups: groups, now: now, in: db)
    }
    let messages = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT message FROM proactive_candidates WHERE bucketID = 'here'")
    }
    XCTAssertEqual(
      messages, ["the Hermes PR still needs review"],
      "the invalid first candidate for the bucket must not claim it and drop the valid one")
  }

  /// The reconciler's instruction blocks are what the constant cache keys name,
  /// so they must not vary with the batch, and splitting them out must leave the
  /// prompt the model receives byte-identical to the unsplit one.
  func testReconcilerInstructionBlocksAreBatchIndependentAndComposeToTheWholePrompt() {
    func batch(_ bucketID: String, tags: Set<String>) -> ContextWorkstreamReconcileBatch {
      ContextWorkstreamReconcileBatch(
        groups: [
          ContextWorkstreamReconcileGroup(
            bucketID: bucketID,
            facts: [
              ContextWorkstreamBatchFact(
                id: "\(bucketID)-0", bucketID: bucketID, appName: "Notes",
                statement: "PR-123 is blocked", notifyWorthiness: 0.9, createdAt: now)
            ],
            needsCandidate: true,
            workstreamTag: nil)
        ],
        existingTags: tags)
    }
    let first = batch("alpha", tags: ["hermes"])
    let second = batch("beta", tags: [])

    XCTAssertNotEqual(
      ContextWorkstreamReconciler.taggingData(batch: first),
      ContextWorkstreamReconciler.taggingData(batch: second))
    XCTAssertEqual(
      ContextWorkstreamReconciler.taggingPrompt(batch: first),
      ContextWorkstreamReconciler.taggingInstructions + "\n\n"
        + ContextWorkstreamReconciler.taggingData(batch: first))
    XCTAssertEqual(
      ContextWorkstreamReconciler.candidatePrompt(groups: first.groups),
      ContextWorkstreamReconciler.candidateInstructions + "\n\n"
        + ContextWorkstreamReconciler.candidateData(groups: first.groups))
    // The safety preamble must stay above every quoted statement, which means
    // it belongs to the instruction half, not the per-pass data half.
    XCTAssertTrue(
      ContextWorkstreamReconciler.taggingInstructions.hasPrefix(
        ScreenDerivedContent.untrustedPreamble))
    XCTAssertTrue(
      ContextWorkstreamReconciler.candidateInstructions.hasPrefix(
        ScreenDerivedContent.untrustedPreamble))
    XCTAssertFalse(
      ContextWorkstreamReconciler.taggingData(batch: first).contains(
        ScreenDerivedContent.untrustedPreamble))
    XCTAssertNotEqual(
      ContextPromptCacheKey.reconcilerTagging, ContextPromptCacheKey.reconcilerCandidates,
      "two different instruction blocks under one key would only evict each other")
  }

  /// Arming selects for a discrete transition, not a standing condition. The
  /// durability test is actionability at delivery, not mere truth; the
  /// minute-volatile-count guard stays beside it.
  func testCandidateInstructionsRequireADiscreteTransitionAndStayActionable() {
    let instructions = ContextWorkstreamReconciler.candidateInstructions
    // Clause assertions run against a whitespace-flattened copy: these sentences
    // wrap across source lines, and rewrapping one must not silently pass or
    // fail an assertion about whether the clause is still there.
    let flattened = instructions.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    XCTAssertTrue(
      instructions.hasPrefix(ScreenDerivedContent.untrustedPreamble),
      "the safety preamble must stay above every quoted statement")
    XCTAssertTrue(
      flattened.contains("discrete transition"),
      "arming must require a discrete transition, not a standing commitment or blocker")
    XCTAssertTrue(
      flattened.contains("merely persists is not enough"),
      "a condition that merely persists must be an explicit omit")
    XCTAssertTrue(
      flattened.contains("still be actionable"),
      "the delivery-time test is actionability, not whether the statement stays true")
    XCTAssertFalse(
      flattened.contains("still be true and useful"),
      "the old truth-durability line selected for standing state")
    XCTAssertTrue(
      flattened.contains(
        "Do not build the message around counts or figures that change minute to minute."),
      "the minute-volatile-count staleness guard is load-bearing")
  }

  func testInsertsSkipAGarbageCollectedBucketWithoutAbortingTheRestOfTheBatch() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("kept", factCount: 3, newestOffset: 0, tagged: false, in: db)
      try seedBucket("gone", factCount: 3, newestOffset: 0, tagged: false, in: db)
      try db.execute(sql: "DELETE FROM context_buckets WHERE id = 'gone'")
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: "gone", tag: "hermes", now: now, in: db)
      try ContextWorkstreamTagging.insertAssignment(
        bucketID: "kept", tag: "hermes", now: now, in: db)
      try ContextProactiveCandidateWriter.insertArmed(
        bucketID: "gone", workstreamTag: "hermes",
        message: "should not land", factIDs: ["gone-0"], triggerNote: "when relevant",
        now: now, in: db)
      try ContextProactiveCandidateWriter.insertArmed(
        bucketID: "kept", workstreamTag: "hermes",
        message: "the Hermes PR still needs review", factIDs: ["kept-0"],
        triggerNote: "when relevant", now: now, in: db)
    }
    let tags = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT tag FROM bucket_workstreams ORDER BY bucketID")
    }
    XCTAssertEqual(tags, ["hermes"])
    let messages = try queue.read { db in
      try String.fetchAll(db, sql: "SELECT message FROM proactive_candidates ORDER BY message")
    }
    XCTAssertEqual(messages, ["the Hermes PR still needs review"])
  }

  func testDeletingABucketCascadesWorkstreamAndCandidateRows() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: true, in: db)
      try insertCandidate(
        id: "live", bucketID: "here", tag: "hermes", message: "message", createdAt: now, in: db)
      try db.execute(sql: "DELETE FROM context_buckets WHERE id = 'here'")
    }
    let leftover = try queue.read { db in
      (
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM bucket_workstreams") ?? -1,
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM proactive_candidates") ?? -1
      )
    }
    XCTAssertEqual(leftover.0, 0, "workstream rows must cascade with the bucket")
    XCTAssertEqual(leftover.1, 0, "candidate rows must cascade with the bucket")
  }

  func testHasArmedCandidateIgnoresACandidateWhoseGroundingIsNoLongerValid() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: false, in: db)
      try insertCandidate(
        id: "stale", bucketID: "here", tag: nil, message: "message", createdAt: now, in: db)
      try db.execute(
        sql: "UPDATE proactive_candidates SET groundingFactIDsJson = '[\"here-0\"]' WHERE id = 'stale'")
      XCTAssertTrue(
        try ContextProactiveCandidateWriter.hasArmedCandidate(bucketID: "here", now: now, in: db))
      try db.execute(sql: "UPDATE bucket_facts SET validityState = 'rejected' WHERE id = 'here-0'")
      XCTAssertFalse(
        try ContextProactiveCandidateWriter.hasArmedCandidate(bucketID: "here", now: now, in: db),
        "an ungrounded armed row must not block the reconciler from writing a replacement")
    }
  }

  func testRestoreReArmsAConsumedCandidateAndRefusesAnExpiredOne() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: false, in: db)
      try insertCandidate(
        id: "live", bucketID: "here", tag: nil, message: "message", createdAt: now, in: db)
      XCTAssertTrue(try ContextProactiveCandidateLookup.consume(id: "live", now: now, in: db))
      XCTAssertTrue(try ContextProactiveCandidateLookup.restore(id: "live", now: now, in: db))
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT state FROM proactive_candidates WHERE id = 'live'"),
        "armed")
      XCTAssertTrue(try ContextProactiveCandidateLookup.consume(id: "live", now: now, in: db))

      try insertCandidate(
        id: "stale", bucketID: "here", tag: nil, message: "message",
        createdAt: now.addingTimeInterval(-13 * 60 * 60), in: db)
      try db.execute(
        sql: "UPDATE proactive_candidates SET state = 'consumed', consumedAt = ?, expiresAt = ? WHERE id = 'stale'",
        arguments: [now.addingTimeInterval(-60), now.addingTimeInterval(-60)])
      XCTAssertFalse(try ContextProactiveCandidateLookup.restore(id: "stale", now: now, in: db))
    }
  }

  func testAssignedTagDeliveryMemorySeesASiblingBucketsDeliveredMessage() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: true, in: db)
      try seedBucket("other", factCount: 1, newestOffset: 0, tagged: true, in: db)
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, bucketID, decisionType, lifecycleState, provenanceJson, message,
             attemptedAt, deliveredAt, expiresAt, createdAt)
          VALUES ('d1', 'other', 'insight', 'delivered', '{}', 'the Hermes PR still needs review',
                  ?, ?, ?, ?)
          """,
        arguments: [now, now, now.addingTimeInterval(30 * 24 * 60 * 60), now])
    }
    let sibling = try queue.read { db in
      try ContextProactiveCandidateLookup.recentDeliveredForAssignedTags(
        tags: ["hermes"], excludingBucketID: "here", now: now, limit: 15, in: db)
    }
    XCTAssertEqual(sibling.map(\.message), ["the Hermes PR still needs review"])
    let bucketHit = ContextProactiveCandidate(
      id: "dup", bucketID: "other", workstreamTag: "hermes",
      message: "the Hermes PR still needs review",
      groundingFactIDsJson: "[\"f1\"]", triggerNote: "when the PR is open",
      state: "armed", createdAt: now, expiresAt: now.addingTimeInterval(60), consumedAt: nil)
    XCTAssertNil(
      ContextProactiveCandidateLookup.firstDeliverable(
        candidates: [bucketHit], recentMessages: sibling.compactMap(\.message)),
      "a workstream-matched candidate must not re-send a sibling bucket's delivered point")
  }

  func testConsumeAndDeclineRejectACandidateThatHasAlreadyExpired() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: false, in: db)
      try insertCandidate(
        id: "stale", bucketID: "here", tag: nil, message: "message",
        createdAt: now.addingTimeInterval(-13 * 60 * 60), in: db)
      try db.execute(
        sql: "UPDATE proactive_candidates SET expiresAt = ? WHERE id = 'stale'",
        arguments: [now.addingTimeInterval(-60)])
      XCTAssertFalse(
        try ContextProactiveCandidateLookup.consume(id: "stale", now: now, in: db),
        "a candidate that expired while the gate call was in flight must not be consumable")
      XCTAssertFalse(
        try ContextProactiveCandidateLookup.decline(id: "stale", now: now, in: db))

      try insertCandidate(
        id: "live", bucketID: "here", tag: nil, message: "message", createdAt: now, in: db)
      XCTAssertTrue(try ContextProactiveCandidateLookup.consume(id: "live", now: now, in: db))
    }
  }

  func testExpiredCandidateNeverReportsAsArmed() throws {
    let queue = try migratedQueue()
    let overdue = ContextProactiveCandidate(
      id: "stale", bucketID: "here", workstreamTag: nil, message: "message",
      groundingFactIDsJson: "[\"f1\"]", triggerNote: "when relevant",
      state: "armed", createdAt: now.addingTimeInterval(-13 * 60 * 60),
      expiresAt: now.addingTimeInterval(-60), consumedAt: nil)
    XCTAssertEqual(
      overdue.effectiveState(at: now), "expired",
      "callers that report state must not still call an overdue row armed")
    XCTAssertEqual(overdue.state, "armed", "the stored column stays armed until the sweep")

    try queue.write { db in
      try seedBucket("here", factCount: 1, newestOffset: 0, tagged: false, in: db)
      try insertCandidate(
        id: "stale", bucketID: "here", tag: nil, message: "message",
        createdAt: now.addingTimeInterval(-13 * 60 * 60), in: db)
      try db.execute(
        sql: "UPDATE proactive_candidates SET expiresAt = ? WHERE id = 'stale'",
        arguments: [now.addingTimeInterval(-60)])
      XCTAssertEqual(
        try ContextProactiveCandidateLookup.lookupArmed(
          bucketID: "here", tags: [], now: now, in: db
        ).map(\.id),
        [],
        "lookup must not return an overdue row as armed")
      try ContextProactiveCandidateLookup.expireStale(now: now, in: db)
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT state FROM proactive_candidates WHERE id = 'stale'"),
        "expired")
      XCTAssertEqual(
        try ContextProactiveCandidateLookup.lookupArmed(
          bucketID: "here", tags: [], now: now, in: db
        ).map(\.id),
        [])
    }
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
    // Empty content is what a completion-token budget exhausted by reasoning
    // returns. It must parse to nil — *not* to a decision — so the delivery
    // path can tell "the model did not answer" apart from "the model said no".
    XCTAssertNil(ContextProactiveCandidateGate.parse(""))
  }

  /// Strict-equality golden, to the same standard as the extraction and
  /// director prompts. The gate's previous contract shipped with mutually
  /// exclusive clauses and rejected 66 of 69 live candidates; a substring
  /// assertion would not have caught a clause drifting back in.
  func testGatePromptIsExact() {
    let prompt = ContextProactiveCandidateGate.prompt(
      message: "Nik is waiting on the demo recording.",
      groundingFacts: ["Nik asked for the recording before the launch video."],
      validatedFacts: ["The release checklist is on screen."],
      recentDeliveries: [])
    let expected = """
      \(ScreenDerivedContent.untrustedPreamble)
      You are a yes/no delivery gate for one pre-written notification. Do not rewrite it.
      The notification was written earlier, from the stored evidence below, not from the
      current screen. The current screen is not expected to mention it.
      Answer show=false only for one of these three reasons:
      1. The current screen clearly shows that the very matter this notification is about
         is already resolved, completed, or changed, so the notification is now wrong or
         moot. A different task, pull request, or topic being resolved on screen is not
         this reason.
      2. The notification repeats a point in the recently-delivered list, even reworded.
      3. The notification only tells the user what they are already looking at right now.
      Otherwise answer show=true.
      The current screen not mentioning or confirming the notification is normal and is
      never a reason to answer false.
      Keep reason to one short sentence.

      == CANDIDATE NOTIFICATION ==
      Nik is waiting on the demo recording.

      == STORED EVIDENCE THE NOTIFICATION WAS WRITTEN FROM ==
      - Nik asked for the recording before the launch video.

      == VALIDATED FACTS ON THIS VISIT (current screen) ==
      The release checklist is on screen.

      == RECENTLY DELIVERED FOR THIS BUCKET ==
      (none)
      """
    XCTAssertEqual(prompt, expected)
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
