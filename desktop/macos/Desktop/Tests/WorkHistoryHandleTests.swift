import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class WorkHistoryHandleTests: XCTestCase {
  func testCanonicalizesHttpURLAndDropsFragmentUserinfoAndDefaultPort() {
    let handle = WorkHistoryHandle.url(
      "HTTPS://User:secret@Docs.Google.COM:443/document/d/abc/?usp=sharing#heading")
    XCTAssertEqual(handle?.kind, .url)
    XCTAssertEqual(handle?.value, "https://docs.google.com/document/d/abc")
  }

  func testTrackingQueryDoesNotSplitIdentity() {
    let shared = WorkHistoryHandle.url("https://docs.google.com/document/d/abc?usp=sharing")
    let clean = WorkHistoryHandle.url("https://docs.google.com/document/d/abc")
    XCTAssertEqual(shared, clean)
  }

  func testCredentialQueryIsDroppedFromIdentityAndOutboundJSON() {
    let handle = WorkHistoryHandle.url(
      "https://docs.google.com/document/d/abc?access_token=secret&q=proposal")
    XCTAssertEqual(handle?.value, "https://docs.google.com/document/d/abc?q=proposal")
    XCTAssertEqual(handle?.jsonObject()["value"], "https://docs.google.com/document/d/abc?q=proposal")
  }

  func testPreservesPercentEncodedPathIdentity() {
    let handle = WorkHistoryHandle.url("https://example.com/a%2Fb/?utm_source=x")
    XCTAssertEqual(handle?.value, "https://example.com/a%2Fb")
  }

  func testBrowserPrefersDocumentURLOverChildAXURL() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Safari",
      windowTitle: "Proposal",
      bundleID: "com.apple.Safari",
      documentURL: URL(string: "https://docs.google.com/document/d/abc"),
      browserURL: URL(string: "https://example.com/favicon.ico")
    )
    XCTAssertEqual(
      WorkHistoryHandleExtractor.handles(from: snapshot).first?.value,
      "https://docs.google.com/document/d/abc")
  }

  func testRejectsNonHttpSchemesAndAboutBlank() {
    XCTAssertNil(WorkHistoryHandle.url("about:blank"))
    XCTAssertNil(WorkHistoryHandle.url("javascript:alert(1)"))
    XCTAssertNil(WorkHistoryHandle.url("file:///tmp/notes.md"))
  }

  func testCanonicalizesFilePaths() {
    XCTAssertEqual(WorkHistoryHandle.file("file:///Users/ada/Notes.md")?.value, "/Users/ada/Notes.md")
    XCTAssertEqual(WorkHistoryHandle.file("/Users/ada/./Notes.md")?.value, "/Users/ada/Notes.md")
    XCTAssertNil(WorkHistoryHandle.file("/"))
  }

  func testExtractorPrefersBrowserURLOverWindowTitle() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Google Chrome",
      windowTitle: "Proposal - Google Docs",
      bundleID: "com.google.Chrome",
      documentURL: nil,
      browserURL: URL(string: "https://docs.google.com/document/d/abc")
    )
    let handles = WorkHistoryHandleExtractor.handles(from: snapshot)
    XCTAssertEqual(handles.first?.kind, .url)
    XCTAssertEqual(handles.first?.value, "https://docs.google.com/document/d/abc")
    XCTAssertTrue(handles.contains(where: { $0.kind == .appWindow }))
  }

  func testExtractorUsesAXDocumentAsFileHandleForEditors() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Cursor",
      windowTitle: "WorkHistoryHandle.swift — omi",
      bundleID: "com.todesktop.230313mzl4w4u92",
      documentURL: URL(fileURLWithPath: "/Users/ada/omi/WorkHistoryHandle.swift"),
      browserURL: nil
    )
    let handles = WorkHistoryHandleExtractor.handles(from: snapshot)
    XCTAssertEqual(handles.first?.kind, .file)
    XCTAssertEqual(handles.first?.value, "/Users/ada/omi/WorkHistoryHandle.swift")
  }

  func testSameCanonicalURLIsPrimaryAcrossApps() {
    let chrome = WorkHistoryHandleExtractor.handles(
      from: WorkHistoryFrontmostSnapshot(
        appName: "Google Chrome",
        windowTitle: "PR 12",
        browserURL: URL(string: "https://github.com/BasedHardware/omi/pull/12/")
      ))
    let arc = WorkHistoryHandleExtractor.handles(
      from: WorkHistoryFrontmostSnapshot(
        appName: "Arc",
        windowTitle: "Different title",
        browserURL: URL(string: "https://github.com/BasedHardware/omi/pull/12")
      ))
    XCTAssertEqual(WorkHistoryHandle.primary(in: chrome), WorkHistoryHandle.primary(in: arc))
  }
}

final class WorkHistoryIndexTests: XCTestCase {
  func testSecondURLVisitCreatesHandleBucketNotTitleHash() throws {
    let queue = try migratedQueue()
    let url = try XCTUnwrap(WorkHistoryHandle.url("https://docs.google.com/document/d/abc"))
    let firstStart = Date(timeIntervalSince1970: 1_725_000_000)

    try queue.write { db in
      XCTAssertNil(
        try ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: "sha256:chrome-title",
          normalizedTitle: "Proposal",
          startedAt: firstStart,
          primaryHandle: url))
      _ = try insertVisit(
        in: db,
        appName: "Google Chrome",
        windowTitle: "Proposal",
        handle: url,
        referenceHash: "sha256:chrome-title",
        startedAt: firstStart,
        endedAt: firstStart.addingTimeInterval(4),
        outcome: "completed")

      let second = try XCTUnwrap(
        ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: "sha256:arc-title",
          normalizedTitle: "Other tab title",
          startedAt: firstStart.addingTimeInterval(60),
          primaryHandle: url))
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT subjectKind FROM context_buckets WHERE id = ?", arguments: [second]),
        "url")
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT subjectID FROM context_buckets WHERE id = ?", arguments: [second]),
        url.value)
    }
  }

  func testTitleOnlyFirstVisitStaysUnbucketed() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      XCTAssertNil(
        try ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: "sha256:only-title",
          normalizedTitle: "Notes",
          startedAt: Date(timeIntervalSince1970: 1_725_000_000),
          primaryHandle: nil))
    }
  }

  func testWorkContextVisitsAndBriefsComeFromHandleIndex() throws {
    let queue = try migratedQueue()
    let url = try XCTUnwrap(WorkHistoryHandle.url("https://docs.google.com/document/d/abc"))
    let start = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, displayLabel, visitCount, lastVisitedAt, createdAt, updatedAt)
          VALUES ('bucket-1', 'url', ?, 'Pricing proposal', 2, ?, ?, ?)
          """,
        arguments: [url.value, start, start, start])
      _ = try insertVisit(
        in: db,
        appName: "Arc",
        windowTitle: "Pricing proposal",
        handle: url,
        referenceHash: url.identityKey,
        bucketID: "bucket-1",
        startedAt: start,
        endedAt: start.addingTimeInterval(30),
        outcome: "completed")
      try db.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
             narrative, evidenceRefsJson, tokenCount, createdAt)
          VALUES ('entry-1', 'bucket-1', 1, 'Arc', 'Arc\nPricing', 'arc::pricing',
                  'Working the pricing doc', '[]', 10, ?)
          """,
        arguments: [start])
      try db.execute(
        sql: """
          INSERT INTO bucket_facts
            (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
             evidenceRefsJson, validityState, dispositionState, confidence,
             notifyWorthiness, createdAt, updatedAt)
          VALUES ('fact-1', 'bucket-1', 'entry-1', 'Arc', 'Pricing doc is the source of truth',
                  ?, 'Pricing doc', '["visit:1"]', 'validated', 'none', 0.9, 0.2, ?, ?)
          """,
        arguments: [WorkHistoryHandle.encodeList([url]), start, start])

      let visits = try WorkHistoryIndex.fetchRecentVisits(
        in: db, from: start.addingTimeInterval(-60), to: start.addingTimeInterval(60), limit: 10)
      XCTAssertEqual(visits.count, 1)
      XCTAssertEqual(visits.first?.handles.first?.value, url.value)

      let briefs = try WorkHistoryIndex.fetchBriefs(in: db, limit: 5)
      XCTAssertEqual(briefs.first?.bucketID, "bucket-1")
      XCTAssertEqual(briefs.first?.handles.first?.kind, .url)
      XCTAssertTrue(WorkHistoryIndex.recapSection(from: briefs).contains("Pricing proposal"))
    }
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
      UserDefaults(suiteName: "WorkHistoryIndexTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }

  @discardableResult
  private func insertVisit(
    in db: Database,
    appName: String,
    windowTitle: String,
    handle: WorkHistoryHandle?,
    referenceHash: String,
    bucketID: String? = nil,
    startedAt: Date,
    endedAt: Date? = nil,
    outcome: String
  ) throws -> Int64 {
    let handles = handle.map { [$0] } ?? []
    try db.execute(
      sql: """
        INSERT INTO context_visits
          (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
           normalizedContextKey, referenceHash, startedAt, outcome, endedAt, createdAt, updatedAt,
           primaryHandleType, primaryHandleValue, handlesJson)
        VALUES (1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
      arguments: [
        bucketID, appName, "\(appName)\n\(windowTitle)", "\(appName.lowercased())::\(windowTitle.lowercased())",
        referenceHash, startedAt, outcome, endedAt, startedAt, endedAt ?? startedAt,
        handle?.kind.rawValue, handle?.value, WorkHistoryHandle.encodeList(handles),
      ])
    return db.lastInsertedRowID
  }
}
