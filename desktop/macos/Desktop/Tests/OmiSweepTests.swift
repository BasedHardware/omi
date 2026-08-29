import GRDB
import XCTest

@testable import Omi_Computer

/// The sweep is what stops the lookup from answering out of whichever store it happened
/// to try first. These cover the two halves that decide whether it finds anything: the
/// query it builds from a spoken question, and what the model is told about the result.
final class OmiSweepTests: XCTestCase {

  // MARK: - Query

  /// The regression that matters most. A spoken question is mostly words that appear in
  /// no stored text, so AND — FTS5's default when terms are space-separated — returns
  /// nothing for every real question. Terms must be OR'd.
  func testTermsAreOredNotAnded() {
    XCTAssertEqual(
      OmiSweep.matchExpression(for: "what is my portfolio link"),
      "portfolio OR link")
  }

  func testAskingVerbsAndFillerAreDropped() {
    XCTAssertEqual(
      OmiSweep.matchExpression(for: "where did you put my w9 tax form"), "w9 OR tax OR form")
  }

  /// A short term is usually the most specific word in the question, not the least:
  /// "w9" and "ssn" name exactly one thing each. Only single characters are noise.
  func testShortTermsSurvive() {
    XCTAssertEqual(OmiSweep.matchExpression(for: "my ssn and my ein"), "ssn OR ein")
    XCTAssertNil(OmiSweep.matchExpression(for: "a b c"))
  }

  /// Nothing left to match on is not an empty query against the whole corpus.
  func testAQuestionOfOnlyStopWordsMatchesNothing() {
    XCTAssertNil(OmiSweep.matchExpression(for: "what about that one"))
    XCTAssertNil(OmiSweep.matchExpression(for: "   "))
  }

  /// Punctuation is a syntax error inside an FTS5 MATCH expression, so it never survives
  /// into one.
  func testPunctuationIsStrippedRatherThanQuoted() {
    let expression = OmiSweep.matchExpression(for: "resume.pdf — \"final\" (v2)?")
    XCTAssertEqual(expression, "resume OR pdf OR final OR v2")
  }

  func testRepeatedTermsAppearOnce() {
    XCTAssertEqual(
      OmiSweep.matchExpression(for: "invoice invoice INVOICE number"), "invoice OR number")
  }

  // MARK: - Refs

  func testRefsParseOnlyIntoKnownNamespaces() {
    XCTAssertEqual(OmiSweep.parse("memory:12")?.source, .memory)
    XCTAssertEqual(OmiSweep.parse("transcript:9")?.id, 9)
    XCTAssertNil(OmiSweep.parse("screenshots:1"))
    XCTAssertNil(OmiSweep.parse("memory:not-a-row"))
    XCTAssertNil(OmiSweep.parse("memory"))
  }

  // MARK: - Prompt

  /// An empty sweep must not read as "the user has no such thing". It says the keywords
  /// missed and names the semantic tools, because concluding absence from a keyword miss
  /// is how a lookup tells someone they never wrote something they did.
  func testEmptySweepTellsTheModelToWidenRatherThanConclude() {
    let section = OmiSweep.promptSection(hits: [])
    XCTAssertTrue(section.contains("NOT that the user has no such thing"))
    XCTAssertTrue(section.contains("search_memories"))
    XCTAssertTrue(section.contains("semantic_search"))
  }

  /// Every line carries the ref the model needs to open it and the tool that opens it.
  func testHitsRenderWithRefsAndTheirHydrationTool() {
    let section = OmiSweep.promptSection(hits: [
      SweepHit(
        ref: "memory:7", source: .memory, title: "manual", preview: "Portfolio is example.dev",
        score: -2.1),
      SweepHit(
        ref: "task:3", source: .task, title: "open", preview: "send the deck", score: -1.0),
    ])
    XCTAssertTrue(section.contains("[memory:7]"))
    XCTAssertTrue(section.contains("Portfolio is example.dev"))
    XCTAssertTrue(section.contains("search_memories"))
    XCTAssertTrue(section.contains("[task:3]"))
    XCTAssertTrue(section.contains("get_tasks"))
  }

  /// Lower BM25 is a better match, so the best hit in a source leads.
  func testHitsWithinASourceAreOrderedBestFirst() {
    let section = OmiSweep.promptSection(hits: [
      SweepHit(ref: "memory:2", source: .memory, title: "", preview: "weaker", score: -0.5),
      SweepHit(ref: "memory:1", source: .memory, title: "", preview: "stronger", score: -4.0),
    ])
    let stronger = try? XCTUnwrap(section.range(of: "stronger"))
    let weaker = try? XCTUnwrap(section.range(of: "weaker"))
    XCTAssertNotNil(stronger)
    XCTAssertNotNil(weaker)
    if let stronger, let weaker {
      XCTAssertTrue(stronger.lowerBound < weaker.lowerBound)
    }
  }
}

/// The sweep run against a real database with the real migration, because the query
/// builder being right says nothing about whether the SQL matches the schema. Every
/// table here is created exactly as `RewindDatabase` creates it, and the FTS indexes
/// come from the shipping migration rather than a copy of it.
final class OmiSweepDatabaseTests: XCTestCase {
  fileprivate func makeDatabase() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
            category TEXT NOT NULL, isDismissed BOOLEAN NOT NULL DEFAULT 0,
            deleted BOOLEAN NOT NULL DEFAULT 0, createdAt DATETIME NOT NULL DEFAULT ''
          );
          CREATE TABLE transcription_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT,
            startedAt DATETIME, deleted BOOLEAN DEFAULT 0, discarded BOOLEAN DEFAULT 0
          );
          CREATE TABLE transcription_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sessionId INTEGER NOT NULL,
            text TEXT NOT NULL, segmentOrder INTEGER NOT NULL, createdAt DATETIME DEFAULT ''
          );
          """)
      try SweepFTSSchema.installMemoriesFTS(db)
      try SweepFTSSchema.installTranscriptSegmentsFTS(db)
    }
    return queue
  }

  fileprivate func sweep(_ query: String, in queue: DatabaseQueue) throws -> [SweepHit] {
    let match = try XCTUnwrap(OmiSweep.matchExpression(for: query))
    return try queue.read { OmiSweep.hits(matching: match, in: $0) }
  }

  /// The whole point: a value the user stored is found by asking for it the way they
  /// would say it out loud, in a source the old memory search reached only by substring.
  func testASpokenQuestionFindsTheMemoryThatAnswersIt() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO memories (content, category) VALUES (?, 'manual'), (?, 'system')",
        arguments: ["My portfolio lives at example.dev", "I prefer oat milk"])
    }
    let hits = try sweep("what is my portfolio link again", in: queue)
    // The keyword hit leads. The other memory rides along as inventory from the top-up,
    // which must never outrank something the question actually matched.
    XCTAssertEqual(hits.first?.ref, "memory:1")
    XCTAssertEqual(hits.first?.preview, "My portfolio lives at example.dev")
  }

  /// The triggers are the part that silently rots: an index that only reflects rows
  /// present at migration time answers yesterday's questions forever.
  func testRowsWrittenAfterTheMigrationAreIndexed() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO memories (content, category) VALUES ('Passport expires in March', 'manual')")
    }
    XCTAssertEqual(try sweep("when does my passport expire", in: queue).count, 1)
  }

  func testEditedRowsAreReindexedAndDeletedRowsLeaveTheIndex() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO memories (content, category) VALUES ('Home is Elm Street', 'manual')")
      try db.execute(sql: "UPDATE memories SET content = 'Home is Oak Avenue' WHERE id = 1")
    }
    // Disjoint terms on purpose: an OR query shares no word between the two versions,
    // so a stale index cannot pass by matching the part that never changed.
    // The row itself is still topped up as inventory; what must be gone is the index
    // entry that made the stale text findable.
    XCTAssertTrue(try sweep("elm street", in: queue).allSatisfy { !$0.isKeywordMatch })
    XCTAssertEqual(try sweep("oak avenue", in: queue).first?.preview, "Home is Oak Avenue")

    try queue.write { db in try db.execute(sql: "DELETE FROM memories WHERE id = 1") }
    XCTAssertTrue(try sweep("oak avenue", in: queue).isEmpty)
  }

  /// Soft-deleted and dismissed rows stay in the index — the triggers must not try to
  /// track a flag — so the filtering has to happen in the sweep's own SQL.
  func testSoftDeletedAndDismissedMemoriesNeverSurface() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO memories (content, category, deleted, isDismissed) VALUES
            ('Invoice number is 4471', 'manual', 1, 0),
            ('Invoice number is 5582', 'manual', 0, 1),
            ('Invoice number is 6693', 'manual', 0, 0)
          """)
    }
    XCTAssertEqual(try sweep("invoice number", in: queue).map(\.ref), ["memory:3"])
  }

  /// A discarded conversation is one the user threw away; its words must not come back
  /// as an answer.
  func testDiscardedConversationsAreExcluded() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO transcription_sessions (id, title, discarded) VALUES
            (1, 'Standup', 0), (2, 'Scratch', 1)
          """)
      try db.execute(
        sql: """
          INSERT INTO transcription_segments (sessionId, text, segmentOrder) VALUES
            (1, 'we agreed the launch date is October ninth', 0),
            (2, 'the launch date is nonsense', 0)
          """)
    }
    let hits = try sweep("what is the launch date", in: queue)
    XCTAssertEqual(hits.map(\.ref), ["transcript:1"])
    XCTAssertEqual(hits.first?.title, "Standup")
  }

  /// The budget is what keeps the prompt a fixed size no matter how much history exists.
  /// Checked on a source that is not memories, because memories carry a wider budget.
  func testEachSourceIsCappedAtItsBudget() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(sql: "INSERT INTO transcription_sessions (id, title) VALUES (1, 'Review')")
      for index in 0..<20 {
        try db.execute(
          sql: """
            INSERT INTO transcription_segments (sessionId, text, segmentOrder)
            VALUES (1, ?, ?)
            """,
          arguments: ["contract clause number \(index)", index])
      }
    }
    let hits = try sweep("contract clause", in: queue)
    XCTAssertEqual(hits.count, OmiSweep.perSourceLimit)
    XCTAssertTrue(hits.allSatisfy { $0.source == .transcript })
  }

  /// A long value is an address in the sweep, not the thing itself; the model opens it
  /// if it wants the rest.
  func testPreviewsAreClippedToTheirBudget() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO memories (content, category) VALUES (?, 'manual')",
        arguments: ["mortgage " + String(repeating: "detail ", count: 200)])
    }
    let preview = try XCTUnwrap(try sweep("mortgage", in: queue).first?.preview)
    XCTAssertEqual(preview.count, OmiSweep.maxPreviewLength + 1, "clipped plus the ellipsis")
  }
}

/// Near-duplicate collapse, measured against a real profile: a browser tab strip is
/// OCR'd into every screenshot taken in that window, so the top keyword matches were
/// routinely the same strip three times over — three of the model's twenty-one slots
/// spent on one piece of information.
extension OmiSweepTests {
  func testCaseAndWhitespaceDoNotMakeTwoOCRPassesLookDistinct() {
    XCTAssertEqual(
      OmiSweep.duplicateKey("Gems  portfolio   API Job"),
      OmiSweep.duplicateKey("gems portfolio API   job"))
  }

  func testPreviewsThatDivergeLateAreStillTheSameHit() {
    let strip = String(repeating: "tab ", count: 30)
    XCTAssertEqual(OmiSweep.duplicateKey(strip + "one"), OmiSweep.duplicateKey(strip + "two"))
  }

  func testGenuinelyDifferentPreviewsSurviveDeduplication() {
    XCTAssertNotEqual(
      OmiSweep.duplicateKey("My portfolio lives at example.dev"),
      OmiSweep.duplicateKey("My mailing address is Oak Avenue"))
  }
}

extension OmiSweepDatabaseTests {
  /// The real-profile regression: the top matches for a question were three copies of
  /// the same chrome. Only one may reach the model, and the budget then goes to the
  /// next genuinely different thing.
  func testRepeatedChromeCollapsesToOneAndFreesTheBudget() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      for index in 0..<6 {
        try db.execute(
          sql: "INSERT INTO memories (content, category) VALUES (?, 'manual')",
          arguments: ["Gems portfolio API Job Ember Revenue Agentic Okara Schema tab \(index)"])
      }
      try db.execute(
        sql: "INSERT INTO memories (content, category) VALUES (?, 'manual')",
        arguments: ["My portfolio lives at example.dev"])
    }
    let hits = try sweep("portfolio", in: queue)
    XCTAssertEqual(hits.count, 2, "five duplicate strips collapse into one")
    XCTAssertTrue(hits.contains { $0.preview == "My portfolio lives at example.dev" })
  }
}

/// The live regression: "where did I go to graduate school" found nothing, because the
/// memory answering it says "M.S. in Applied Data Intelligence from San Jose State
/// University" — not one word of the question. The backend's semantic search missed the
/// same row, so Omi told the user it did not know something it knew.
extension OmiSweepDatabaseTests {
  private func insertGradSchoolProfile(_ queue: DatabaseQueue) throws {
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO memories (content, category, createdAt) VALUES (?, 'manual', ?)",
        arguments: ["Earned an M.S. in Applied Data Intelligence from San Jose State", "2026-01-01"])
      for index in 0..<4 {
        try db.execute(
          sql: "INSERT INTO memories (content, category, createdAt) VALUES (?, 'system', ?)",
          arguments: ["Unrelated fact \(index)", "2026-02-0\(index + 1)"])
      }
    }
  }

  func testAMemoryTheQuestionSharesNoWordWithStillReachesTheModel() throws {
    let queue = try makeDatabase()
    try insertGradSchoolProfile(queue)
    let hits = try sweep("where did I go to graduate school", in: queue)
    XCTAssertTrue(
      hits.contains { $0.preview.contains("San Jose State") },
      "the top-up must surface a memory no keyword in the question matches")
  }

  /// The top-up is a floor, not a licence: it can never push the source past its budget.
  func testTopUpNeverExceedsTheMemoryBudget() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      for index in 0..<40 {
        try db.execute(
          sql: "INSERT INTO memories (content, category, createdAt) VALUES (?, 'manual', ?)",
          arguments: ["Distinct memory number \(index)", "2026-02-01"])
      }
    }
    XCTAssertEqual(try sweep("nothing matches this", in: queue).count, SweepSource.memory.budget)
  }

  /// A keyword hit is evidence; a topped-up row is only inventory. The hit leads.
  func testKeywordHitsOutrankToppedUpRows() throws {
    let queue = try makeDatabase()
    try insertGradSchoolProfile(queue)
    let hits = try sweep("intelligence", in: queue)
    XCTAssertTrue(hits.first?.preview.contains("Applied Data Intelligence") == true)
    XCTAssertTrue(hits.first?.isKeywordMatch == true)
    XCTAssertTrue(hits.dropFirst().allSatisfy { !$0.isKeywordMatch })
  }

  /// Only memories are topped up. Screen history is large and noisy, and its newest rows
  /// have no claim on the question.
  func testNoisySourcesAreNotToppedUp() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO transcription_sessions (id, title) VALUES (1, 'Standup');
          INSERT INTO transcription_segments (sessionId, text, segmentOrder)
            VALUES (1, 'entirely unrelated chatter', 0);
          """)
    }
    XCTAssertTrue(try sweep("mortgage refinance", in: queue).isEmpty)
  }
}

/// The second live regression: the model answered "I couldn't find the exact dates"
/// while the memory holding them sat one row outside the budget. It never called
/// get_memories because eight lines with no remainder read as the whole store.
extension OmiSweepTests {
  private var oneMemoryHit: [SweepHit] {
    [SweepHit(ref: "memory:1", source: .memory, title: "", preview: "worked at Datasaur", score: -1)]
  }

  func testTheModelIsToldHowMuchOfItsMemoriesItIsNotSeeing() {
    let section = OmiSweep.promptSection(hits: oneMemoryHit, memoryTotal: 14)
    XCTAssertTrue(section.contains("showing 1 of 14"))
    // The remainder must point at the local store the sweep itself read. Pointing it at
    // the backend's get_memories was measured live: the model took the hint and burned
    // four turns on a tool that never returned the row.
    XCTAssertTrue(section.contains("list_memories reads the other 13 in one call"))
  }

  /// No remainder means no remainder. A count that matches what is shown must not
  /// produce a "there is more" line the model would waste a turn chasing.
  func testNoRemainderIsClaimedWhenEverythingIsShown() {
    XCTAssertFalse(
      OmiSweep.promptSection(hits: oneMemoryHit, memoryTotal: 1).contains("showing"))
  }

  /// Only memories carry a total. The other sources are large by nature and "showing 3
  /// of 2,576" invites paging through screen history one page at a time.
  func testOtherSourcesDoNotAdvertiseARemainder() {
    let hits = [
      SweepHit(ref: "screen:1", source: .screen, title: "Safari", preview: "a page", score: -1)
    ]
    XCTAssertFalse(OmiSweep.promptSection(hits: hits, memoryTotal: 99).contains("showing"))
  }
}

extension OmiSweepDatabaseTests {
  func testMemoryTotalCountsOnlyWhatTheUserStillHas() throws {
    let queue = try makeDatabase()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO memories (content, category, deleted, isDismissed) VALUES
            ('kept one', 'manual', 0, 0), ('kept two', 'manual', 0, 0),
            ('gone', 'manual', 1, 0), ('hidden', 'manual', 0, 1)
          """)
    }
    XCTAssertEqual(try queue.read { OmiSweep.memoryTotal(in: $0) }, 2)
  }
}
