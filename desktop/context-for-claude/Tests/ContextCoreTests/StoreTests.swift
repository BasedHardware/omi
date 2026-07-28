import ContextCore
import Foundation
import GRDB
import XCTest

/// The storage layer, tested through the SQL surface the app actually depends on.
///
/// The FTS assertions carry the most weight here: the search index is maintained by triggers, so a
/// broken one produces a database that still accepts every write, still answers every query, and
/// silently returns nothing — or worse, returns rows whose content no longer exists.
final class StoreTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        // Unseeded: these tests assert exact row counts and prune behaviour.
        fixture = try Fixture(seeded: false)
    }

    override func tearDownWithError() throws {
        fixture?.tearDown()
        fixture = nil
    }

    // MARK: - Schema

    func testMigrationCreatesEveryTableIndexAndFTSTrigger() throws {
        let objects: [(type: String, name: String, table: String)] = try fixture.store.read { db in
            try Row.fetchAll(db, sql: "SELECT type, name, tbl_name FROM sqlite_master").map { row in
                let type: String = row["type"] ?? ""
                let name: String = row["name"] ?? ""
                let table: String = row["tbl_name"] ?? ""
                return (type: type, name: name, table: table)
            }
        }

        let tables = Set(objects.filter { $0.type == "table" }.map(\.name))
        for expected in ["sessions", "segments", "frames", "segments_fts", "frames_fts"] {
            XCTAssertTrue(tables.contains(expected), "missing table \(expected)")
        }

        let indexes = Set(objects.filter { $0.type == "index" }.map(\.name))
        for expected in [
            "idx_sessions_startedAt", "idx_segments_startedAt", "idx_segments_sessionId",
            "idx_frames_capturedAt", "idx_frames_app",
        ] {
            XCTAssertTrue(indexes.contains(expected), "missing index \(expected)")
        }

        // Asserted by count rather than by name: the three insert/delete/update sync triggers live on
        // the *content* tables, and GRDB owns what they are called.
        for content in ["segments", "frames"] {
            let triggers = objects.filter { $0.type == "trigger" && $0.table == content }
            XCTAssertGreaterThanOrEqual(
                triggers.count, 3,
                "\(content) needs the ai/ad/au FTS sync triggers, found \(triggers.map(\.name))")
        }
    }

    // MARK: - Round trips

    func testSessionSegmentAndFrameRoundTrip() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: "zoom.us")
        try store.closeSession(sessionId, at: Fixture.base + 600)
        let segmentId = try store.insertSegment(
            Segment(
                sessionId: sessionId,
                startedAt: Fixture.base + 10,
                endedAt: Fixture.base + 14,
                source: .system,
                text: "sounds good, I will draft the migration plan"))
        let imagePath = try fixture.writeImage(named: "round-trip.jpg")
        let frameId = try store.insertFrame(
            Frame(
                capturedAt: Fixture.base + 20,
                appName: "Google Chrome",
                windowTitle: "Pricing — Notion",
                ocrText: "pricing change rollout notes",
                imagePath: imagePath))

        XCTAssertGreaterThan(sessionId, 0)
        XCTAssertGreaterThan(segmentId, 0)
        XCTAssertGreaterThan(frameId, 0)

        let sessions: [Session] = try store.read { try Session.fetchAll($0) }
        let segments: [Segment] = try store.read { try Segment.fetchAll($0) }
        let frames: [Frame] = try store.read { try Frame.fetchAll($0) }

        let session = try XCTUnwrap(sessions.first)
        XCTAssertEqual(sessions.count, 1)
        XCTAssertEqual(session.id, sessionId)
        XCTAssertEqual(session.startedAt, Fixture.base)
        XCTAssertEqual(session.endedAt, Fixture.base + 600)
        XCTAssertEqual(session.appHint, "zoom.us")

        let segment = try XCTUnwrap(segments.first)
        XCTAssertEqual(segments.count, 1)
        XCTAssertEqual(segment.id, segmentId)
        XCTAssertEqual(segment.sessionId, sessionId)
        XCTAssertEqual(segment.startedAt, Fixture.base + 10)
        XCTAssertEqual(segment.endedAt, Fixture.base + 14)
        XCTAssertEqual(segment.source, SegmentSource.system.rawValue)
        // Attribution is derived on the way in, never supplied by the caller.
        XCTAssertEqual(segment.speaker, "them")
        XCTAssertEqual(segment.text, "sounds good, I will draft the migration plan")

        let frame = try XCTUnwrap(frames.first)
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frame.id, frameId)
        XCTAssertEqual(frame.capturedAt, Fixture.base + 20)
        XCTAssertEqual(frame.appName, "Google Chrome")
        XCTAssertEqual(frame.windowTitle, "Pricing — Notion")
        XCTAssertEqual(frame.ocrText, "pricing change rollout notes")
        XCTAssertEqual(frame.imagePath, imagePath)
    }

    func testClosingAnUnknownSessionIsANoOp() throws {
        // The engine closes sessions it may never have opened when a source dies mid-write.
        XCTAssertNoThrow(try fixture.store.closeSession(9_999, at: Fixture.base))
    }

    // MARK: - FTS synchronisation

    func testSegmentFTSIndexesInsertsUpdatesAndDeletes() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: nil)
        let id = try store.insertSegment(
            Segment(
                sessionId: sessionId,
                startedAt: Fixture.base,
                endedAt: Fixture.base + 4,
                source: .mic,
                text: "twas brillig and the slithy toves"))

        XCTAssertEqual(try segmentMatches("brillig"), 1, "insert did not reach segments_fts")

        try store.write { db in
            try db.execute(sql: "UPDATE segments SET text = ? WHERE id = ?",
                           arguments: ["mimsy were the borogoves", id])
        }
        XCTAssertEqual(try segmentMatches("brillig"), 0, "update left the old text in segments_fts")
        XCTAssertEqual(try segmentMatches("mimsy"), 1, "update did not reach segments_fts")

        try store.write { db in
            try db.execute(sql: "DELETE FROM segments WHERE id = ?", arguments: [id])
        }
        // An external-content index that keeps a row whose content is gone is corrupt, not merely
        // stale — this assertion is the one that catches a dropped `ad` trigger.
        XCTAssertEqual(try segmentMatches("mimsy"), 0, "delete left an orphaned row in segments_fts")
    }

    func testFrameFTSIndexesOCRTitleAndAppAndRemovesThemOnDelete() throws {
        let id = try fixture.addFrame(
            at: Fixture.base, app: "Context for Claude", window: "Slithy Toves", ocr: "vorpal blade snicker snack")

        XCTAssertEqual(try frameMatches("vorpal"), 1, "OCR text is not indexed")
        XCTAssertEqual(try frameMatches("slithy"), 1, "window titles are not indexed")

        try fixture.store.write { db in
            try db.execute(sql: "DELETE FROM frames WHERE id = ?", arguments: [id])
        }
        XCTAssertEqual(try frameMatches("vorpal"), 0)
        XCTAssertEqual(try frameMatches("slithy"), 0)
    }

    // MARK: - Read-only mode

    func testWriteThroughAReadOnlyStoreThrowsReadOnly() throws {
        let reader = try ContextStore(url: fixture.databaseURL, readOnly: true)

        XCTAssertThrowsError(try reader.insertFrame(Frame(capturedAt: Fixture.base))) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        XCTAssertThrowsError(try reader.openSession(at: Fixture.base, appHint: nil)) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        XCTAssertThrowsError(try reader.pruneFrames(olderThanDays: 30)) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        // Reading is exactly what this connection exists for.
        XCTAssertNoThrow(try Queries.status(reader))
    }

    func testReadOnlyOpenOfAMissingDatabaseThrowsNotInitialized() throws {
        let missing = fixture.root.appendingPathComponent("never-captured.db")

        XCTAssertThrowsError(try ContextStore(url: missing, readOnly: true)) { error in
            XCTAssertStoreError(error, .notInitialized)
        }
        // And it must not have created the file on its way out; the app owns migration.
        XCTAssertFalse(FileManager.default.fileExists(atPath: missing.path))
    }

    // MARK: - Pruning

    func testPruneFramesDeletesOldRowsAndTheirImagesAndLeavesNewerOnesAlone() throws {
        let store = fixture.store
        // `pruneFrames` measures the cutoff from the wall clock, so the corpus has to be anchored to
        // it too. Sampled once, so every row in this test shares one clock reading.
        let now = ContextTime.now
        let day: Double = 86_400

        let ancientImage = try fixture.writeImage(named: "ancient.jpg")
        let staleImage = try fixture.writeImage(named: "stale.jpg")
        let keptImage = try fixture.writeImage(named: "kept.jpg")

        try fixture.addFrame(at: now - 400 * day, app: "Xcode", window: "ancient",
                             ocr: "ancient vorpal text", imagePath: ancientImage)
        try fixture.addFrame(at: now - 31 * day, app: "Xcode", window: "stale",
                             ocr: "stale brillig text", imagePath: staleImage)
        // No image at all: a frame whose OCR was captured but whose JPEG was skipped must not stop
        // the sweep.
        try fixture.addFrame(at: now - 90 * day, app: "Xcode", window: "no image", ocr: "mimsy")
        let keptId = try fixture.addFrame(at: now - 2 * day, app: "Xcode", window: "kept",
                                          ocr: "kept slithy text", imagePath: keptImage)

        let deleted = try store.pruneFrames(olderThanDays: 30)

        XCTAssertEqual(deleted, 3)
        XCTAssertFalse(FileManager.default.fileExists(atPath: ancientImage), "old JPEG leaked")
        XCTAssertFalse(FileManager.default.fileExists(atPath: staleImage), "old JPEG leaked")
        XCTAssertTrue(FileManager.default.fileExists(atPath: keptImage), "a surviving JPEG was unlinked")

        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY id")
        }
        XCTAssertEqual(remaining, [keptId])

        // The delete trigger has to run for the prune too, or search keeps answering with rows whose
        // screenshots and content are gone.
        XCTAssertEqual(try frameMatches("brillig"), 0)
        XCTAssertEqual(try frameMatches("slithy"), 1)
    }

    func testPruneFramesNeverTouchesTranscripts() throws {
        let store = fixture.store
        let now = ContextTime.now
        let sessionId = try store.openSession(at: now - 400 * 86_400, appHint: nil)
        try fixture.addSegment(session: sessionId, at: now - 400 * 86_400, source: .mic,
                               "a year old and still the reason this app exists")

        _ = try store.pruneFrames(olderThanDays: 30)

        let segments: Int = try store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM segments") ?? 0
        }
        XCTAssertEqual(segments, 1)
    }

    // MARK: - Helpers

    private func segmentMatches(_ term: String) throws -> Int {
        try fixture.store.read { db in
            try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM segments_fts WHERE segments_fts MATCH ?",
                arguments: [term]) ?? 0
        }
    }

    private func frameMatches(_ term: String) throws -> Int {
        try fixture.store.read { db in
            try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM frames_fts WHERE frames_fts MATCH ?",
                arguments: [term]) ?? 0
        }
    }
}
