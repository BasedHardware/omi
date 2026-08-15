import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextDestinationKeyTests: XCTestCase {

  // MARK: - Scope

  func testOnlyBrowsersAreEligible() {
    XCTAssertTrue(ContextDestinationKey.isBrowser(appName: "Google Chrome"))
    XCTAssertTrue(ContextDestinationKey.isBrowser(appName: "Safari"))
    XCTAssertTrue(ContextDestinationKey.isBrowser(appName: "Arc"))
    // Native apps keep per-title identity. Unscoped destination labelling collapsed
    // every distinct Telegram thread into one bucket, so this boundary is the
    // primary defense against merging unrelated private conversations.
    XCTAssertFalse(ContextDestinationKey.isBrowser(appName: "Telegram"))
    XCTAssertFalse(ContextDestinationKey.isBrowser(appName: "Slack"))
    XCTAssertFalse(ContextDestinationKey.isBrowser(appName: "ChatGPT"))
  }

  func testNonBrowserPromptAsksForAbstention() {
    let prompt = ContextProactivityPromptBuilder.extractionPrompt(
      appName: "Telegram", windowTitle: "deploy", evidenceRef: "visit:1")
    XCTAssertTrue(prompt.contains(ContextDestinationKey.abstention))
    XCTAssertFalse(prompt.contains("page-group"))
  }

  func testBrowserPromptCarriesRulesBelowTheUntrustedPreamble() {
    let prompt = ContextProactivityPromptBuilder.extractionPrompt(
      appName: "Google Chrome", windowTitle: "Home / X", evidenceRef: "visit:1")
    XCTAssertTrue(prompt.contains("page-group"))
    // The window title is attacker-controlled (any page sets document.title), so the
    // routing rules must sit below the untrusted framing, never above it.
    let preambleIndex = try? XCTUnwrap(prompt.range(of: ScreenDerivedContent.untrustedPreamble))
    let rulesIndex = try? XCTUnwrap(prompt.range(of: "page-group"))
    if let preambleIndex, let rulesIndex {
      XCTAssertLessThan(preambleIndex.lowerBound, rulesIndex.lowerBound)
    }
  }

  // MARK: - Site hint

  func testSiteHintTakesTheTrailingSegment() {
    // Chrome truncates titles mid-string with an ellipsis, so only the tail survives.
    XCTAssertEqual(
      ContextDestinationKey.siteHint(title: "fix(desktop): split rewindpage…est #11537 · acme/omi"),
      "acme/omi")
    XCTAssertEqual(ContextDestinationKey.siteHint(title: "Inbox - user@example.com - Gmail"), "gmail")
    XCTAssertNil(ContextDestinationKey.siteHint(title: "bookmarks"))
  }

  // MARK: - Sanitization

  func testBrowserNamedDomainsAreRejected() {
    // Accepting these would merge every open tab into one bucket.
    for forbidden in ["chrome/newtab", "google-chrome/tabs", "safari/start", "browser/home"] {
      XCTAssertNil(
        ContextDestinationKey.sanitize(forbidden, title: "anything"),
        "\(forbidden) must never become an identity")
    }
  }

  func testAbstentionIsNotAKey() {
    XCTAssertNil(ContextDestinationKey.sanitize("unknown/spud pay", title: "spud pay"))
    XCTAssertNil(ContextDestinationKey.sanitize("", title: "spud pay"))
    XCTAssertNil(ContextDestinationKey.sanitize(nil, title: "spud pay"))
  }

  func testUngroundedDomainIsRejected() {
    // Observed hallucination: this title was labelled with a domain that appears
    // nowhere in it. The guard costs no model call and removed a third of the
    // remaining false merges.
    XCTAssertNil(
      ContextDestinationKey.sanitize(
        "scalingforever.com/inbox", title: "re: modulate transcription - da…ever.com"))
  }

  func testGroundedKeyIsAccepted() {
    XCTAssertEqual(
      ContextDestinationKey.sanitize("x.com/feed", title: "Home / X"),
      "dest:x.com/feed")
    XCTAssertEqual(
      ContextDestinationKey.sanitize("github.com/acme/omi", title: "fix: thing #11 · acme/omi"),
      "dest:github.com/acme/omi")
    // Trailing slashes must not fork one destination into two identities.
    XCTAssertEqual(
      ContextDestinationKey.sanitize("x.com/feed/", title: "Home / X"),
      ContextDestinationKey.sanitize("x.com/feed", title: "Home / X"))
  }

  func testCaseAndWhitespaceDoNotForkIdentity() {
    XCTAssertEqual(
      ContextDestinationKey.sanitize("  X.com/Feed  ", title: "Home / X"),
      ContextDestinationKey.sanitize("x.com/feed", title: "Home / X"))
  }

  // MARK: - Binding

  func testDestinationClaimsItsOwnBucketWhenUnused() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let bucket = try seedBucket(in: db, hash: "sha256:a", subjectID: "sha256:a")
      let resolved = try ContextDestinationBinder.apply(
        in: db, referenceHash: "sha256:a", currentBucketID: bucket, subjectID: "dest:x.com/feed")
      XCTAssertEqual(resolved, bucket)
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT subjectID FROM context_buckets WHERE id = ?", arguments: [bucket]),
        "dest:x.com/feed")
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT source FROM subject_bindings WHERE referenceHash = 'sha256:a'"),
        ContextDestinationKey.derivationSource)
    }
  }

  func testSecondTitleJoinsTheExistingDestinationBucket() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let first = try seedBucket(in: db, hash: "sha256:a", subjectID: "sha256:a")
      try ContextDestinationBinder.apply(
        in: db, referenceHash: "sha256:a", currentBucketID: first, subjectID: "dest:x.com/feed")

      let second = try seedBucket(in: db, hash: "sha256:b", subjectID: "sha256:b")
      let resolved = try ContextDestinationBinder.apply(
        in: db, referenceHash: "sha256:b", currentBucketID: second, subjectID: "dest:x.com/feed")

      // This is the whole point: two reference hashes, one bucket.
      XCTAssertEqual(resolved, first)
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT bucketID FROM subject_bindings WHERE referenceHash = 'sha256:b'"),
        first)
      // The uniqueness tuple must still hold exactly one row for the destination.
      XCTAssertEqual(
        try Int.fetchOne(
          db, sql: "SELECT COUNT(*) FROM context_buckets WHERE subjectID = 'dest:x.com/feed'"),
        1)
    }
  }

  func testExplicitBindingIsNeverOverwritten() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let bucket = try seedBucket(
        in: db, hash: "sha256:a", subjectID: "workstream-subject", source: "explicit_open")
      XCTAssertNil(
        try ContextDestinationBinder.apply(
          in: db, referenceHash: "sha256:a", currentBucketID: bucket,
          subjectID: "dest:x.com/feed"))
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT subjectID FROM subject_bindings WHERE referenceHash = 'sha256:a'"),
        "workstream-subject")
    }
  }

  func testAlreadyDerivedBindingIsNotReadjudicated() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let bucket = try seedBucket(in: db, hash: "sha256:a", subjectID: "sha256:a")
      try ContextDestinationBinder.apply(
        in: db, referenceHash: "sha256:a", currentBucketID: bucket, subjectID: "dest:x.com/feed")
      // A later visit proposing a different key must not move an established
      // identity; stability is what makes the cached decision trustworthy.
      XCTAssertNil(
        try ContextDestinationBinder.apply(
          in: db, referenceHash: "sha256:a", currentBucketID: bucket,
          subjectID: "dest:example.com/other"))
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT subjectID FROM subject_bindings WHERE referenceHash = 'sha256:a'"),
        "dest:x.com/feed")
    }
  }

  func testEphemeralHashesNeverBind() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let bucket = try seedBucket(in: db, hash: "ephemeral:abc", subjectID: "ephemeral:abc")
      XCTAssertNil(
        try ContextDestinationBinder.apply(
          in: db, referenceHash: "ephemeral:abc", currentBucketID: bucket,
          subjectID: "dest:x.com/feed"))
    }
  }

  func testUnprefixedSubjectIsRejected() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      let bucket = try seedBucket(in: db, hash: "sha256:a", subjectID: "sha256:a")
      XCTAssertNil(
        try ContextDestinationBinder.apply(
          in: db, referenceHash: "sha256:a", currentBucketID: bucket, subjectID: "x.com/feed"))
    }
  }

  // MARK: - Helpers

  @discardableResult
  private func seedBucket(
    in db: Database, hash: String, subjectID: String, source: String = "repeat_cooccurrence"
  ) throws -> String {
    let id = UUID().uuidString.lowercased()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try db.execute(
      sql: """
        INSERT INTO context_buckets
          (id, subjectKind, subjectID, workstreamID, displayLabel, visitCount, lastVisitedAt,
           createdAt, updatedAt)
        VALUES (?, 'context', ?, NULL, NULL, 0, ?, ?, ?)
        """,
      arguments: [id, subjectID, now, now, now])
    try db.execute(
      sql: """
        INSERT INTO subject_bindings
          (referenceHash, bucketID, subjectKind, subjectID, confidence, source, occurrenceCount,
           createdAt, updatedAt)
        VALUES (?, ?, 'context', ?, 0.5, ?, 1, ?, ?)
        """,
      arguments: [hash, id, subjectID, source, now, now])
    return id
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
      UserDefaults(suiteName: "ContextDestinationKeyTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }
}
