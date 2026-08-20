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
            "idx_frames_showable", "idx_frames_bundle_by_app",
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

    /// **An index nothing plans against is a write cost with no reader**, so the two partial indexes
    /// are pinned by the plans that justify them rather than by their existence alone.
    ///
    /// Both were added because the reads below planned a full table scan without them — measured at
    /// 581 ms (`coverage`), 575 ms (the search panel's total for a query the FTS index cannot
    /// represent) and 779 ms (`bundleIdsByApp`) against a synthetic year of capture, all three on
    /// reads the app makes on the main actor. This is a static tripwire on the *planner*, not a
    /// timing assertion: it fails if a migration is dropped, if a predicate drifts out of the
    /// partial index's condition, or if a query is reworded so that the index no longer applies —
    /// which are the three ways the cost silently comes back.
    func testShowableAndBundleReadsPlanAgainstTheirPartialIndexes() throws {
        func plan(_ sql: String) throws -> String {
            try fixture.store.read { db in
                try Row.fetchAll(db, sql: "EXPLAIN QUERY PLAN " + sql)
                    .map { ($0["detail"] as String?) ?? "" }
                    .joined(separator: " | ")
            }
        }

        for (label, sql) in [
            ("coverage oldest", "SELECT MIN(capturedAt) FROM frames WHERE imagePath IS NOT NULL"),
            ("coverage newest", "SELECT MAX(capturedAt) FROM frames WHERE imagePath IS NOT NULL"),
            ("search total", "SELECT COUNT(*) FROM frames f WHERE f.imagePath IS NOT NULL"),
            (
                "day window",
                """
                SELECT COUNT(*) FROM frames
                WHERE capturedAt >= 0 AND capturedAt <= 1 AND imagePath IS NOT NULL
                """
            ),
        ] {
            let detail = try plan(sql)
            XCTAssertTrue(
                detail.contains("idx_frames_showable"),
                "\(label) no longer uses idx_frames_showable: \(detail)")
        }

        let bundles = try plan(
            """
            SELECT appName, bundleId FROM frames
            WHERE bundleId IS NOT NULL AND TRIM(bundleId) <> ''
              AND appName IS NOT NULL AND TRIM(appName) <> ''
              AND id IN (SELECT MAX(id) FROM frames
                         WHERE bundleId IS NOT NULL AND TRIM(bundleId) <> ''
                         GROUP BY appName)
            """)
        XCTAssertTrue(
            bundles.contains("idx_frames_bundle_by_app"),
            "bundleIdsByApp no longer uses idx_frames_bundle_by_app: \(bundles)")
    }

    /// The partial indexes must not change *which* rows a showable read returns — only how it finds
    /// them. A condition written the other way round (`imagePath IS NULL`) would still be a legal
    /// index and would still be planned against, and every one of these reads would quietly invert.
    func testPartialIndexesDoNotChangeWhichRowsAShowableReadReturns() throws {
        try fixture.addFrame(at: Fixture.base, app: "Cursor", imagePath: "/tmp/a.heic")
        try fixture.addFrame(at: Fixture.base + 10, app: "Cursor", imagePath: nil)
        try fixture.addFrame(at: Fixture.base + 20, app: "Cursor", imagePath: "/tmp/b.heic")

        XCTAssertEqual(
            try RewindQueries.coverage(fixture.store),
            Fixture.base...(Fixture.base + 20))
        XCTAssertEqual(
            try RewindQueries.frameCount(
                fixture.store, since: Fixture.base - 1, until: Fixture.base + 100),
            2)
    }

    func testConfidenceMigrationAddsTheColumnWithoutDisturbingExistingRows() throws {
        // Rewinds a populated database to the shape it had before per-line confidence existed —
        // column gone, ledger entry forgotten — and reopens it. That is the upgrade a user with
        // months of transcript actually performs, and the only way to prove the migration adds the
        // column *to rows that are already there* rather than only to a database it created itself.
        let url = fixture.root.appendingPathComponent("legacy.db")
        let legacySessionId: Int64
        let legacySegmentId: Int64
        do {
            let legacy = try ContextStore(url: url)
            legacySessionId = try legacy.openSession(at: Fixture.base, appHint: "zoom.us")
            legacySegmentId = try legacy.insertSegment(
                Segment(
                    sessionId: legacySessionId,
                    startedAt: Fixture.base + 10,
                    endedAt: Fixture.base + 14,
                    source: .mic,
                    text: "twas brillig and the slithy toves"))
            try legacy.write { db in
                try db.execute(sql: "ALTER TABLE segments DROP COLUMN confidence")
                try db.execute(
                    sql: "DELETE FROM grdb_migrations WHERE identifier = ?",
                    arguments: ["v3-segment-confidence"])
            }
            XCTAssertFalse(
                try columns(of: "segments", in: legacy).contains("confidence"),
                "the fixture failed to rewind: this test would prove nothing")
        }

        let upgraded = try ContextStore(url: url)

        XCTAssertTrue(try columns(of: "segments", in: upgraded).contains("confidence"))
        let applied: [String] = try upgraded.read { db in
            try String.fetchAll(db, sql: "SELECT identifier FROM grdb_migrations ORDER BY identifier")
        }
        // Exactly the ones the store's own migrator registers. A missing entry would mean the
        // migration re-runs on every launch and fails on the second one.
        XCTAssertEqual(
            applied,
            ["v1", "v10-ax-node-last-seen", "v11-account-cache", "v3-segment-confidence",
             "v4-segment-speaker", "v5-cloud-segment-identity", "v6-accessibility-tree",
             "v7-frame-bundle-id", "v8-frame-showable-index", "v9-frame-bundle-by-app-index"])

        // The ledger is shared with `UploadQueue`, which registers `v2-uploads` outside this
        // migrator and skips itself when its identifier is already recorded. Proving the two live
        // together is the only way to know the new identifier did not quietly claim its slot.
        try UploadQueue.prepare(upgraded)
        let coexisting: Set<String> = try upgraded.read { db in
            Set(try String.fetchAll(db, sql: "SELECT identifier FROM grdb_migrations"))
        }
        XCTAssertEqual(
            coexisting,
            ["v1", "v3-segment-confidence", "v4-segment-speaker", "v5-cloud-segment-identity",
             "v6-accessibility-tree", "v7-frame-bundle-id", "v8-frame-showable-index",
             "v9-frame-bundle-by-app-index", "v10-ax-node-last-seen", "v11-account-cache",
             UploadQueue.migrationIdentifier])
        XCTAssertTrue(try tableExists("uploads", in: upgraded), "the uploads migration was skipped")

        let segments: [Segment] = try upgraded.read { try Segment.fetchAll($0) }
        let segment = try XCTUnwrap(segments.first)
        XCTAssertEqual(segments.count, 1, "the migration lost or duplicated a row")
        XCTAssertEqual(segment.id, legacySegmentId)
        XCTAssertEqual(segment.sessionId, legacySessionId)
        XCTAssertEqual(segment.startedAt, Fixture.base + 10)
        XCTAssertEqual(segment.endedAt, Fixture.base + 14)
        XCTAssertEqual(segment.source, SegmentSource.mic.rawValue)
        XCTAssertEqual(segment.text, "twas brillig and the slithy toves")
        // The whole point of the column being nullable: a line captured before scores existed is
        // unknown, not doubtful.
        XCTAssertNil(segment.confidence)
        XCTAssertEqual(
            try nullConfidenceCount(in: upgraded), 1,
            "an existing row was backfilled with a number the model never produced")

        // Search has to survive the alter: the FTS index is external-content over `segments`, so a
        // column added under it must leave the sync triggers and the index intact.
        let matches: Int = try upgraded.read { db in
            try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM segments_fts WHERE segments_fts MATCH ?",
                arguments: ["brillig"]) ?? 0
        }
        XCTAssertEqual(matches, 1, "the migration broke the segments FTS index")

        // And the upgraded database has to accept a scored line, which is what the column is for.
        let scoredId = try upgraded.insertSegment(
            Segment(
                sessionId: legacySessionId,
                startedAt: Fixture.base + 20,
                endedAt: Fixture.base + 24,
                source: .mic,
                text: "mimsy were the borogoves",
                confidence: 0.91))
        let scored: Segment? = try upgraded.read { db in
            try Segment.fetchOne(db, sql: "SELECT * FROM segments WHERE id = ?", arguments: [scoredId])
        }
        XCTAssertEqual(try XCTUnwrap(scored).confidence, 0.91)
    }

    func testSpeakerMigrationAddsBothColumnsWithoutDisturbingExistingRows() throws {
        // Same rewind as the confidence test, and for the same reason: the upgrade that matters is
        // the one a user with months of transcript performs, not the schema a fresh database is
        // born with.
        let url = fixture.root.appendingPathComponent("pre-speaker.db")
        let legacySessionId: Int64
        let legacySegmentId: Int64
        do {
            let legacy = try ContextStore(url: url)
            legacySessionId = try legacy.openSession(at: Fixture.base, appHint: "zoom.us")
            legacySegmentId = try legacy.insertSegment(
                Segment(
                    sessionId: legacySessionId,
                    startedAt: Fixture.base + 10,
                    endedAt: Fixture.base + 14,
                    source: .system,
                    text: "twas brillig and the slithy toves",
                    confidence: 0.88))
            try legacy.write { db in
                try db.execute(sql: "ALTER TABLE segments DROP COLUMN speakerLabel")
                try db.execute(sql: "ALTER TABLE segments DROP COLUMN personId")
                try db.execute(
                    sql: "DELETE FROM grdb_migrations WHERE identifier = ?",
                    arguments: ["v4-segment-speaker"])
            }
            let before = try columns(of: "segments", in: legacy)
            XCTAssertFalse(
                before.contains("speakerLabel"),
                "the fixture failed to rewind: this test would prove nothing")
            XCTAssertFalse(before.contains("personId"), "the fixture failed to rewind")
        }

        let upgraded = try ContextStore(url: url)

        let after = try columns(of: "segments", in: upgraded)
        XCTAssertTrue(after.contains("speakerLabel"))
        XCTAssertTrue(after.contains("personId"))

        let applied: [String] = try upgraded.read { db in
            try String.fetchAll(db, sql: "SELECT identifier FROM grdb_migrations ORDER BY identifier")
        }
        // Exactly what this migrator registers, in order. A fresh identifier rather than a reused
        // one is the whole point: a duplicate would be skipped forever and the columns would simply
        // never appear.
        XCTAssertEqual(
            applied,
            ["v1", "v10-ax-node-last-seen", "v11-account-cache", "v3-segment-confidence",
             "v4-segment-speaker", "v5-cloud-segment-identity", "v6-accessibility-tree",
             "v7-frame-bundle-id", "v8-frame-showable-index", "v9-frame-bundle-by-app-index"])

        // The ledger is shared with `UploadQueue`, which registers `v2-uploads` outside this
        // migrator. Proving they still coexist is the only way to know `v4-` did not claim a slot
        // that was already spoken for.
        try UploadQueue.prepare(upgraded)
        let coexisting: Set<String> = try upgraded.read { db in
            Set(try String.fetchAll(db, sql: "SELECT identifier FROM grdb_migrations"))
        }
        XCTAssertEqual(
            coexisting,
            ["v1", "v3-segment-confidence", "v4-segment-speaker", "v5-cloud-segment-identity",
             "v6-accessibility-tree", "v7-frame-bundle-id", "v8-frame-showable-index",
             "v9-frame-bundle-by-app-index", "v10-ax-node-last-seen", "v11-account-cache",
             UploadQueue.migrationIdentifier])
        XCTAssertTrue(try tableExists("uploads", in: upgraded), "the uploads migration was skipped")

        let segments: [Segment] = try upgraded.read { try Segment.fetchAll($0) }
        let segment = try XCTUnwrap(segments.first)
        XCTAssertEqual(segments.count, 1, "the migration lost or duplicated a row")
        XCTAssertEqual(segment.id, legacySegmentId)
        XCTAssertEqual(segment.sessionId, legacySessionId)
        XCTAssertEqual(segment.startedAt, Fixture.base + 10)
        XCTAssertEqual(segment.endedAt, Fixture.base + 14)
        XCTAssertEqual(segment.source, SegmentSource.system.rawValue)
        XCTAssertEqual(segment.speaker, "them")
        XCTAssertEqual(segment.text, "twas brillig and the slithy toves")
        // The column added beside them must not disturb the one added before it.
        XCTAssertEqual(segment.confidence, 0.88)
        // A line captured before the backend diarized anything was never attributed to a person,
        // and the upgrade must not invent one for it.
        XCTAssertNil(segment.speakerLabel)
        XCTAssertNil(segment.personId)
        XCTAssertEqual(
            try unattributedCount(in: upgraded), 1,
            "an existing row was backfilled with attribution nobody produced")

        // Search has to survive the alter: `segments_fts` is external-content over `segments`, so
        // two columns added under it must leave the sync triggers and the index intact.
        let matches: Int = try upgraded.read { db in
            try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM segments_fts WHERE segments_fts MATCH ?",
                arguments: ["brillig"]) ?? 0
        }
        XCTAssertEqual(matches, 1, "the migration broke the segments FTS index")

        // And the upgraded database has to accept an attributed line, which is what the columns are
        // for.
        let attributedId = try upgraded.insertSegment(
            Segment(
                sessionId: legacySessionId,
                startedAt: Fixture.base + 20,
                endedAt: Fixture.base + 24,
                source: .system,
                text: "mimsy were the borogoves",
                speakerLabel: "SPEAKER_01",
                personId: "person-sarah"))
        let attributed: Segment? = try upgraded.read { db in
            try Segment.fetchOne(db, sql: "SELECT * FROM segments WHERE id = ?", arguments: [attributedId])
        }
        let stored = try XCTUnwrap(attributed)
        XCTAssertEqual(stored.speakerLabel, "SPEAKER_01")
        XCTAssertEqual(stored.personId, "person-sarah")
    }

    func testCloudIdentityMigrationLeavesOldSegmentsUnidentifiedAndAddsTheUniqueKey() throws {
        let url = fixture.root.appendingPathComponent("pre-cloud-identity.db")
        let legacySessionId: Int64
        let legacySegmentId: Int64
        do {
            let legacy = try ContextStore(url: url)
            legacySessionId = try legacy.openSession(at: Fixture.base, appHint: "zoom.us")
            legacySegmentId = try legacy.insertSegment(
                Segment(
                    sessionId: legacySessionId,
                    startedAt: Fixture.base + 10,
                    endedAt: Fixture.base + 14,
                    source: .system,
                    text: "a local line from before cloud identities"))
            try legacy.write { db in
                try db.execute(sql: "DROP INDEX idx_segments_backend_identity")
                try db.execute(sql: "ALTER TABLE segments DROP COLUMN backendConversationId")
                try db.execute(sql: "ALTER TABLE segments DROP COLUMN backendSegmentId")
                try db.execute(
                    sql: "DELETE FROM grdb_migrations WHERE identifier = ?",
                    arguments: ["v5-cloud-segment-identity"])
            }
        }

        let upgraded = try ContextStore(url: url)
        let columnsAfter = try columns(of: "segments", in: upgraded)
        XCTAssertTrue(columnsAfter.contains("backendConversationId"))
        XCTAssertTrue(columnsAfter.contains("backendSegmentId"))
        let indexes = try upgraded.read { db in
            try String.fetchAll(db, sql: "SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        XCTAssertTrue(indexes.contains("idx_segments_backend_identity"))

        let legacy: Segment? = try upgraded.read { db in
            try Segment.fetchOne(db, sql: "SELECT * FROM segments WHERE id = ?", arguments: [legacySegmentId])
        }
        XCTAssertNil(try XCTUnwrap(legacy).backendConversationId)
        XCTAssertNil(try XCTUnwrap(legacy).backendSegmentId)

        let cloud = Segment(
            sessionId: legacySessionId,
            startedAt: Fixture.base + 20,
            endedAt: Fixture.base + 25,
            source: .system,
            text: "the backend can now revise this",
            backendConversationId: "conversation-8",
            backendSegmentId: "segment-1")
        _ = try upgraded.upsertCloudSegment(cloud)
        let count = try upgraded.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM segments") ?? 0
        }
        XCTAssertEqual(count, 2)
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

    func testSegmentConfidenceRoundTripsAndAnAbsentScoreStaysNull() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: nil)
        // 0.57 is the real number from the dogfooding session: background music transcribed through
        // the microphone as the user's own first-person speech.
        let uncertainId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 10, endedAt: Fixture.base + 14,
                source: .mic, text: "and I will always love you", confidence: 0.57))
        let certainId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 30, endedAt: Fixture.base + 34,
                source: .mic, text: "let us ship the pricing change on Friday", confidence: 0.98))
        // A caller that has no score — every writer before this column existed, and any future one
        // whose engine cannot produce one.
        let unscoredId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 50, endedAt: Fixture.base + 54,
                source: .system, text: "sounds good, I will draft the plan"))

        let byID: [Int64: Segment] = try store.read { db in
            try Segment.fetchAll(db).reduce(into: [:]) { $0[$1.id ?? -1] = $1 }
        }

        XCTAssertEqual(byID[uncertainId]?.confidence, 0.57)
        XCTAssertEqual(byID[certainId]?.confidence, 0.98)
        // The assertion the whole design turns on: an unscored line reads as unknown, and never as
        // a zero that would libel a line the model transcribed perfectly well.
        XCTAssertNil(try XCTUnwrap(byID[unscoredId]).confidence)
        XCTAssertNotEqual(byID[unscoredId]?.confidence, 0)

        // Through the column itself, not only through the decoder: a NULL that arrived as 0.0 would
        // still decode to `Optional(0.0)` and pass a nil-check written any less carefully.
        XCTAssertEqual(try nullConfidenceCount(in: store), 1)
        let stored: [Double] = try store.read { db in
            try Double.fetchAll(
                db, sql: "SELECT confidence FROM segments WHERE confidence IS NOT NULL ORDER BY startedAt")
        }
        XCTAssertEqual(stored, [0.57, 0.98])
    }

    func testSegmentSpeakerAttributionRoundTripsAndAnAbsentPersonStaysNull() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: "zoom.us")
        // What the backend actually sends: a diarization label per voice, and a person id only for
        // the voices an enrolled speech profile matched.
        let namedId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 10, endedAt: Fixture.base + 14,
                source: .system, text: "I will send the contract tonight",
                speakerLabel: "SPEAKER_00", personId: "person-sarah"))
        // A second voice on the same call: diarized apart, but nobody the account knows. The whole
        // reason the label is stored separately from the person.
        let anonymousId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 30, endedAt: Fixture.base + 34,
                source: .system, text: "can we push it to Monday",
                speakerLabel: "SPEAKER_01"))
        // A locally transcribed line: no diarizer ran, so neither field has an answer.
        let localId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 50, endedAt: Fixture.base + 54,
                source: .mic, text: "let me check the calendar"))
        // Blank is the same absence as missing — the wire is full of empty strings, and two
        // readings of "unattributed" in one column is how a `personId IS NOT NULL` query and a
        // `!= nil` check come to disagree.
        let blankId = try store.insertSegment(
            Segment(
                sessionId: sessionId, startedAt: Fixture.base + 70, endedAt: Fixture.base + 74,
                source: .system, text: "sounds good", speakerLabel: "  ", personId: ""))

        let byID: [Int64: Segment] = try store.read { db in
            try Segment.fetchAll(db).reduce(into: [:]) { $0[$1.id ?? -1] = $1 }
        }

        XCTAssertEqual(byID[namedId]?.speakerLabel, "SPEAKER_00")
        XCTAssertEqual(byID[namedId]?.personId, "person-sarah")
        // Source-derived attribution is untouched by any of this: it is what the app observed
        // itself, and it stays true whatever the backend knows about the voice.
        XCTAssertEqual(byID[namedId]?.speaker, "them")

        XCTAssertEqual(byID[anonymousId]?.speakerLabel, "SPEAKER_01")
        XCTAssertNil(try XCTUnwrap(byID[anonymousId]).personId)

        XCTAssertNil(try XCTUnwrap(byID[localId]).speakerLabel)
        XCTAssertNil(try XCTUnwrap(byID[localId]).personId)

        XCTAssertNil(try XCTUnwrap(byID[blankId]).speakerLabel)
        XCTAssertNil(try XCTUnwrap(byID[blankId]).personId)

        // Through the columns themselves, not only through the decoder: an empty string stored as a
        // value would still decode to `Optional("")` and pass a nil-check written any less
        // carefully, and would make this row look like an identified person to SQL.
        XCTAssertEqual(try unattributedCount(in: store), 3)
        let people: [String] = try store.read { db in
            try String.fetchAll(
                db, sql: "SELECT personId FROM segments WHERE personId IS NOT NULL ORDER BY startedAt")
        }
        XCTAssertEqual(people, ["person-sarah"])
    }

    func testClosingAnUnknownSessionIsANoOp() throws {
        // The engine closes sessions it may never have opened when a source dies mid-write.
        XCTAssertNoThrow(try fixture.store.closeSession(9_999, at: Fixture.base))
    }

    // MARK: - Cloud transcript identity

    func testCloudSegmentUpsertReplacesTheStoredRevisionAndFTSContent() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: "Zoom")
        let original = Segment(
            sessionId: sessionId,
            startedAt: Fixture.base + 10,
            endedAt: Fixture.base + 14,
            source: .system,
            text: "we should ship on Thursday",
            speakerLabel: "SPEAKER_00",
            personId: "person-alex",
            backendConversationId: "conversation-7",
            backendSegmentId: "segment-42")
        let originalID = try store.upsertCloudSegment(original)

        let revision = Segment(
            sessionId: sessionId,
            startedAt: Fixture.base + 10,
            endedAt: Fixture.base + 15,
            source: .system,
            text: "we should ship on Friday",
            speakerLabel: "SPEAKER_01",
            personId: "person-sam",
            backendConversationId: "conversation-7",
            backendSegmentId: "segment-42")
        let revisionID = try store.upsertCloudSegment(revision)

        XCTAssertEqual(revisionID, originalID, "a backend revision must update its canonical row")
        let rows: [(id: Int64, text: String, speaker: String?, person: String?)] = try store.read { db in
            try Row.fetchAll(
                db,
                sql: "SELECT id, text, speakerLabel, personId FROM segments "
                    + "WHERE backendConversationId = ? AND backendSegmentId = ?",
                arguments: ["conversation-7", "segment-42"]
            ).map { row in
                (row["id"], row["text"], row["speakerLabel"], row["personId"])
            }
        }
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows.first?.id, originalID)
        XCTAssertEqual(rows.first?.text, "we should ship on Friday")
        XCTAssertEqual(rows.first?.speaker, "SPEAKER_01")
        XCTAssertEqual(rows.first?.person, "person-sam")
        XCTAssertEqual(try segmentMatches("Thursday"), 0, "FTS retained the superseded revision")
        XCTAssertEqual(try segmentMatches("Friday"), 1, "FTS did not receive the replacement text")
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

    /// **The one delete that does not come from a `DELETE` statement.**
    ///
    /// `segments.sessionId` is `ON DELETE CASCADE`, so a session going takes its lines with it —
    /// and the `ad` trigger that keeps `segments_fts` honest has to fire for those too. It does,
    /// because SQLite runs delete triggers for foreign-key actions, but that is a property of the
    /// engine rather than of anything written here: an index left holding rows whose content is gone
    /// answers searches with text nobody can open, and nothing else in this suite would notice.
    ///
    /// `integrity-check` is FTS5's own audit of an external-content index against its content table,
    /// and it is also the answer to "what if it drifts anyway": the same table accepts a `rebuild`
    /// command that rereads the content table from scratch.
    func testCascadingSessionDeleteLeavesNoOrphanInTheSearchIndex() throws {
        let sessionId = try fixture.store.openSession(at: Fixture.base, appHint: nil)
        try fixture.addSegment(session: sessionId, at: Fixture.base, source: .mic, "borogoves outgrabe")
        try fixture.addFrame(at: Fixture.base, app: "Cursor", window: "Jabberwock", ocr: "beamish boy")
        XCTAssertEqual(try segmentMatches("borogoves"), 1)

        try fixture.store.write { db in
            try db.execute(sql: "DELETE FROM sessions WHERE id = ?", arguments: [sessionId])
        }

        let remaining = try fixture.store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM segments") ?? -1
        }
        XCTAssertEqual(remaining, 0, "the cascade did not reach segments")
        XCTAssertEqual(
            try segmentMatches("borogoves"), 0,
            "a cascaded delete left an orphaned row in segments_fts")

        // All three external-content indexes, audited against the tables they mirror.
        for index in ["segments_fts", "frames_fts", "frames_ax_fts"] {
            XCTAssertNoThrow(
                try fixture.store.write { db in
                    try db.execute(sql: "INSERT INTO \(index)(\(index)) VALUES('integrity-check')")
                },
                "\(index) has drifted from its content table")
        }
    }

    /// Whatever state an index reached, rereading the content table has to be able to restore it.
    /// Without that, the only remedy for a drifted index is deleting the user's history.
    func testRebuildingASearchIndexRestoresItFromTheContentTable() throws {
        try fixture.addFrame(at: Fixture.base, app: "Cursor", window: "Jabberwock", ocr: "beamish boy")
        XCTAssertEqual(try frameMatches("beamish"), 1)

        try fixture.store.write { db in
            // The shape drift takes: the index is emptied while the rows it describes stay.
            try db.execute(sql: "INSERT INTO frames_fts(frames_fts) VALUES('delete-all')")
        }
        XCTAssertEqual(try frameMatches("beamish"), 0, "the index was not actually disturbed")

        try fixture.store.write { db in
            try db.execute(sql: "INSERT INTO frames_fts(frames_fts) VALUES('rebuild')")
        }

        XCTAssertEqual(try frameMatches("beamish"), 1, "rebuild did not restore the index")
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
        // Both refuse before they scan, not after: a reader with nothing to expire must not report
        // a successful sweep it never performed.
        XCTAssertThrowsError(try reader.expireFrameImages(olderThanDays: 30)) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        XCTAssertThrowsError(try reader.expireFrameImages(toFitBytes: 0)) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        XCTAssertThrowsError(try reader.enforceRetention()) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        // Reading is exactly what this connection exists for.
        XCTAssertNoThrow(try Queries.status(reader))
        XCTAssertNoThrow(try reader.framesBytesOnDisk())
    }

    func testReadOnlyOpenOfAMissingDatabaseThrowsNotInitialized() throws {
        let missing = fixture.root.appendingPathComponent("never-captured.db")

        XCTAssertThrowsError(try ContextStore(url: missing, readOnly: true)) { error in
            XCTAssertStoreError(error, .notInitialized)
        }
        // And it must not have created the file on its way out; the app owns migration.
        XCTAssertFalse(FileManager.default.fileExists(atPath: missing.path))
    }

    // MARK: - Expiring images by age
    //
    // Tiered retention: past the horizon a frame loses its **picture** and keeps everything that can
    // be read. Every test in this section is written twice over, because the two failure modes are
    // not equally bad — leaving a picture behind costs disk, and taking a row's text costs the user
    // history that cannot be recaptured. So each asserts what went *and* what stayed.

    func testExpiringOldImagesRemovesThePictureAndKeepsTheRowAndAllOfItsText() throws {
        let store = fixture.store
        // The cutoff is measured from the wall clock, so the corpus has to be anchored to it too.
        // Sampled once, so every row in this test shares one clock reading.
        let now = ContextTime.now
        let day: Double = 86_400

        let ancientImage = try fixture.writeImage(named: "ancient.jpg")
        let staleImage = try fixture.writeImage(named: "stale.jpg")
        let keptImage = try fixture.writeImage(named: "kept.jpg")

        let ancient = try fixture.addFrame(at: now - 400 * day, app: "Xcode", window: "ancient",
                                           ocr: "ancient vorpal text", imagePath: ancientImage)
        let stale = try fixture.addFrame(at: now - 31 * day, app: "Xcode", window: "stale",
                                         ocr: "stale brillig text", imagePath: staleImage)
        // No image at all: a frame whose OCR was captured but whose JPEG was skipped is already
        // exactly what an expired frame becomes, and must neither be counted nor disturbed.
        let never = try fixture.addFrame(at: now - 90 * day, app: "Xcode", window: "no image",
                                         ocr: "mimsy")
        let kept = try fixture.addFrame(at: now - 2 * day, app: "Xcode", window: "kept",
                                        ocr: "kept slithy text", imagePath: keptImage)

        let expired = try store.expireFrameImages(olderThanDays: 30)

        // What went: two pictures, and only pictures.
        XCTAssertEqual(expired, 2, "the row with no image was counted as an expiry")
        XCTAssertFalse(FileManager.default.fileExists(atPath: ancientImage), "an expired JPEG leaked")
        XCTAssertFalse(FileManager.default.fileExists(atPath: staleImage), "an expired JPEG leaked")
        XCTAssertNil(try imagePath(of: ancient), "the row still points at a file that is gone")
        XCTAssertNil(try imagePath(of: stale), "the row still points at a file that is gone")

        // What stayed: every row, every word, and the picture inside the horizon.
        XCTAssertTrue(FileManager.default.fileExists(atPath: keptImage), "a recent JPEG was unlinked")
        XCTAssertEqual(try imagePath(of: kept), keptImage)
        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY id")
        }
        XCTAssertEqual(remaining, [ancient, stale, never, kept], "expiry deleted a frame row")
        // The whole point of the tier. Search still finds the moment whose picture is gone.
        XCTAssertEqual(try frameMatches("vorpal"), 1, "an expired frame fell out of the search index")
        XCTAssertEqual(try frameMatches("brillig"), 1)
        XCTAssertEqual(try frameMatches("mimsy"), 1)
        XCTAssertEqual(try frameMatches("slithy"), 1)
    }

    func testExpiringOldImagesNeverTouchesTranscripts() throws {
        let store = fixture.store
        let now = ContextTime.now
        let sessionId = try store.openSession(at: now - 400 * 86_400, appHint: nil)
        try fixture.addSegment(session: sessionId, at: now - 400 * 86_400, source: .mic,
                               "a year old and still the reason this app exists")

        _ = try store.expireFrameImages(olderThanDays: 30)

        XCTAssertEqual(try count(of: "segments"), 1)
        XCTAssertEqual(try count(of: "sessions"), 1)
    }

    /// The tree root goes with the picture, and `axText` does not.
    ///
    /// Both directions matter here for a reason that is easy to miss: rows now live forever, so a
    /// root kept forever would keep every `ax_nodes` row permanently reachable and silently disable
    /// `sweepAXNodes` — the table would grow without bound again. Clearing the *text* instead would
    /// be the opposite mistake, and would take the searchable half this whole feature exists to keep.
    func testExpiringAnImageClearsItsTreeRootAndKeepsItsAccessibilityText() throws {
        let store = fixture.store
        let now = ContextTime.now
        let root = Data(repeating: 0xAB, count: 32)
        let image = try fixture.writeImage(named: "old.jpg")
        let old = try store.insertFrame(
            Frame(capturedAt: now - 40 * 86_400, appName: "Xcode", windowTitle: "old",
                  ocrText: "ocr text", imagePath: image, axRootHash: root))
        try store.write { db in
            try db.execute(sql: "UPDATE frames SET axText = ? WHERE id = ?",
                           arguments: ["borogove in the accessibility tree", old])
        }

        XCTAssertEqual(try store.expireFrameImages(olderThanDays: 30), 1)

        let (hash, text): (Data?, String?) = try store.read { db in
            let row = try Row.fetchOne(db, sql: "SELECT axRootHash, axText FROM frames WHERE id = ?",
                                       arguments: [old])!
            return (row["axRootHash"], row["axText"])
        }
        XCTAssertNil(hash, "the tree root outlived the picture, so ax_nodes can never be collected")
        XCTAssertEqual(text, "borogove in the accessibility tree", "the accessibility text was taken")
    }

    // MARK: - Expiring images to a byte cap

    func testByteCapExpiresTheOldestPicturesFirstAndStopsAtTheCap() throws {
        let store = fixture.store
        let ocr = ["ancient vorpal", "old brillig", "middling mimsy", "recent slithy", "newest borogove"]
        var ids = [Int64](repeating: 0, count: 5)
        var paths = [String](repeating: "", count: 5)

        // Inserted out of chronological order on purpose: "oldest" has to mean `capturedAt`, never
        // insertion order — a cap that expired by rowid would pass a same-order corpus and still
        // throw away the wrong week on a real machine.
        for index in [4, 2, 0, 3, 1] {
            paths[index] = try writeImage(named: "frame-\(index).jpg", bytes: 1_000)
            ids[index] = try fixture.addFrame(
                at: Fixture.base + Double(index) * 60, app: "Xcode", window: "frame \(index)",
                ocr: ocr[index], imagePath: paths[index])
        }
        XCTAssertEqual(try store.framesBytesOnDisk(), 5_000)

        // Room for exactly three pictures: the two oldest go, and not one more.
        let expired = try store.expireFrameImages(toFitBytes: 3_000)

        XCTAssertEqual(expired, 2, "the cap over- or under-expired")
        XCTAssertEqual(try store.framesBytesOnDisk(), 3_000)

        for index in [0, 1] {
            XCTAssertFalse(FileManager.default.fileExists(atPath: paths[index]),
                           "frame \(index)'s JPEG survived the cap")
            XCTAssertNil(try imagePath(of: ids[index]), "the row still names a file that is gone")
        }
        for index in [2, 3, 4] {
            XCTAssertTrue(FileManager.default.fileExists(atPath: paths[index]),
                          "a surviving frame's JPEG was unlinked")
            XCTAssertEqual(try imagePath(of: ids[index]), paths[index])
        }

        // Every row and every word survives a bound that is about bytes on disk.
        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, ids)
        for term in ["vorpal", "brillig", "mimsy", "borogove"] {
            XCTAssertEqual(try frameMatches(term), 1, "\(term) fell out of the index")
        }
    }

    func testByteCapIsANoOpWhenAlreadyUnderTheCap() throws {
        let store = fixture.store
        // Nothing captured yet: the tightest possible cap still has nothing to do.
        XCTAssertEqual(try store.expireFrameImages(toFitBytes: 0), 0)

        var paths: [String] = []
        for index in 0..<3 {
            let path = try writeImage(named: "frame-\(index).jpg", bytes: 1_000)
            paths.append(path)
            try fixture.addFrame(
                at: Fixture.base + Double(index) * 60, app: "Xcode", window: "frame \(index)",
                ocr: "note \(index)", imagePath: path)
        }

        XCTAssertEqual(try store.expireFrameImages(toFitBytes: 10_000), 0, "expired while under the cap")
        // "At or under": a total sitting exactly on the cap is not over it.
        XCTAssertEqual(try store.expireFrameImages(toFitBytes: 3_000), 0, "expired while exactly at the cap")

        XCTAssertEqual(try count(of: "frames"), 3)
        for path in paths {
            XCTAssertTrue(FileManager.default.fileExists(atPath: path), "a JPEG was unlinked for nothing")
        }
        XCTAssertEqual(try store.framesBytesOnDisk(), 3_000)
    }

    func testByteCapNeverTouchesTranscripts() throws {
        let store = fixture.store
        let sessionId = try store.openSession(at: Fixture.base, appHint: "zoom.us")
        try fixture.addSegment(
            session: sessionId, at: Fixture.base + 10, source: .mic,
            "the words are the half that cannot be recaptured")
        let path = try writeImage(named: "frame.jpg", bytes: 4_096)
        try fixture.addFrame(
            at: Fixture.base + 20, app: "Xcode", window: "frame", ocr: "vorpal", imagePath: path)

        // A cap of zero is the harshest sweep there is; the transcript still has to survive it.
        XCTAssertEqual(try store.expireFrameImages(toFitBytes: 0), 1)

        XCTAssertEqual(try count(of: "frames"), 1, "retention ate a frame row")
        XCTAssertEqual(try count(of: "segments"), 1, "retention ate a transcript line")
        XCTAssertEqual(try count(of: "sessions"), 1, "retention ate a session")
        XCTAssertEqual(try segmentMatches("recaptured"), 1)
        XCTAssertEqual(try frameMatches("vorpal"), 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: path))
    }

    /// The bound that makes the two tiers composable, and the bug that made them not.
    ///
    /// The row-deleting predecessor of this method walked frames oldest-first and appended every one
    /// of them to its doomed list, image or no image. A frame with no picture frees nothing, so once
    /// the age tier began leaving image-less rows behind — which is now the *normal* state of
    /// everything past the horizon — the byte pass would have deleted thousands of those rows, and
    /// all of their text, before it freed a single byte. It has to skip them and keep walking.
    func testByteCapSkipsFramesThatHaveNoImageInsteadOfSpendingThemOnTheCap() throws {
        let store = fixture.store
        // Oldest, and already expired: no picture to reclaim, all of its text still worth keeping.
        let expiredAlready = try fixture.addFrame(
            at: Fixture.base, app: "Xcode", window: "no image", ocr: "ancient vorpal")
        let olderPath = try writeImage(named: "older.jpg", bytes: 1_000)
        let older = try fixture.addFrame(
            at: Fixture.base + 60, app: "Xcode", window: "older", ocr: "old brillig",
            imagePath: olderPath)
        let newestPath = try writeImage(named: "newest.jpg", bytes: 1_000)
        let newest = try fixture.addFrame(
            at: Fixture.base + 120, app: "Xcode", window: "newest", ocr: "newest slithy",
            imagePath: newestPath)

        XCTAssertEqual(try store.framesBytesOnDisk(), 2_000, "a row with no JPEG must count as zero")

        let expired = try store.expireFrameImages(toFitBytes: 1_000)

        // One picture went — the oldest one that *had* a picture — and the image-less row was not
        // spent getting there.
        XCTAssertEqual(expired, 1)
        XCTAssertEqual(try store.framesBytesOnDisk(), 1_000)
        XCTAssertFalse(FileManager.default.fileExists(atPath: olderPath))
        XCTAssertTrue(FileManager.default.fileExists(atPath: newestPath))

        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, [expiredAlready, older, newest], "an image-less row was deleted")
        XCTAssertEqual(try frameMatches("vorpal"), 1, "the text of an already-expired frame was taken")
    }

    func testEnforceRetentionAppliesWhicheverBoundIsTighterAndKeepsEveryRow() throws {
        let store = fixture.store
        // The age half reads the wall clock, so this corpus is anchored to it — sampled once, so
        // every row shares one reading.
        let now = ContextTime.now
        let ancientPath = try writeImage(named: "ancient.jpg", bytes: 1_000)
        let ancient = try fixture.addFrame(
            at: now - 40 * 86_400, app: "Xcode", window: "ancient", ocr: "ancient vorpal",
            imagePath: ancientPath)

        var recentIds: [Int64] = []
        var recentPaths: [String] = []
        for index in 0..<3 {
            let path = try writeImage(named: "recent-\(index).jpg", bytes: 1_000)
            recentPaths.append(path)
            let id = try fixture.addFrame(
                at: now - Double(3 - index) * 60, app: "Xcode", window: "recent \(index)",
                ocr: "recent note \(index)", imagePath: path)
            recentIds.append(id)
        }

        // Age takes the 40-day-old picture; the 2 KiB cap then takes one more that age would keep.
        let expired = try store.enforceRetention(olderThanDays: 30, toFitBytes: 2_000)

        XCTAssertEqual(expired, 2)
        XCTAssertEqual(try store.framesBytesOnDisk(), 2_000)
        XCTAssertFalse(FileManager.default.fileExists(atPath: ancientPath))
        XCTAssertFalse(FileManager.default.fileExists(atPath: recentPaths[0]))
        XCTAssertTrue(FileManager.default.fileExists(atPath: recentPaths[1]))

        // And the sentence the whole feature rests on: nothing was deleted from the database.
        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, [ancient] + recentIds)
        XCTAssertEqual(try frameMatches("vorpal"), 1)
    }

    /// The `imagePath` a row currently names, or nil once its picture has expired.
    private func imagePath(of id: Int64) throws -> String? {
        try fixture.store.read { db in
            try String.fetchOne(db, sql: "SELECT imagePath FROM frames WHERE id = ?", arguments: [id])
        }
    }

    // MARK: - Helpers

    /// A stand-in screenshot of an exact size, so a byte cap can be expressed in whole frames.
    /// `Fixture.writeImage` writes a fixed four bytes, which cannot express "over the cap".
    private func writeImage(named name: String, bytes: Int) throws -> String {
        let directory = fixture.root.appendingPathComponent("Frames", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent(name)
        // A minimal JPEG SOI/EOI pair padded out, so anything that sniffs the file still sees an image.
        var data = Data([0xFF, 0xD8, 0xFF, 0xD9])
        data.append(Data(repeating: 0, count: max(0, bytes - data.count)))
        try data.write(to: url)
        return url.path
    }

    /// Column names as SQLite itself reports them, so a schema assertion cannot be satisfied by a
    /// record type that merely claims to have the property.
    private func columns(of table: String, in store: ContextStore) throws -> Set<String> {
        try store.read { db in
            let rows = try Row.fetchAll(db, sql: "PRAGMA table_info(\(table))")
            return Set(rows.compactMap { row -> String? in row["name"] })
        }
    }

    private func tableExists(_ name: String, in store: ContextStore) throws -> Bool {
        try store.read { db in try db.tableExists(name) }
    }

    /// Rows with no matched person, counted in SQL so an empty string cannot pass for absence.
    private func unattributedCount(in store: ContextStore) throws -> Int {
        try store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM segments WHERE personId IS NULL") ?? -1
        }
    }

    private func nullConfidenceCount(in store: ContextStore) throws -> Int {
        try store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM segments WHERE confidence IS NULL") ?? -1
        }
    }

    private func count(of table: String) throws -> Int {
        try fixture.store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM \(table)") ?? -1
        }
    }

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

    // MARK: - A database older than the binary reading it

    /// The app owns migrations and the MCP reader opens read-only, so between an update and the
    /// app's next launch the reader meets a schema older than its own queries. That window used to
    /// surface as `SQLite error 1: no such column: speakerLabel` — returned not to a log but to the
    /// model, as the *answer* to the user's question.
    ///
    /// Detected at open, as a named condition, so the one thing that fixes it can be said plainly.
    func testAReaderRefusesADatabaseOlderThanItsOwnQueries() throws {
        XCTAssertFalse(
            ContextStore.needsAppUpgrade(at: fixture.databaseURL),
            "a freshly migrated database was reported as needing an upgrade")

        // Roll the ledger back to exactly what an older app would have left behind: those rows are
        // what GRDB consults, and what `hasCompletedMigrations` reads.
        try fixture.store.write { db in
            try db.execute(
                sql: "DELETE FROM grdb_migrations WHERE identifier IN (?, ?)",
                arguments: ["v4-segment-speaker", "v5-cloud-segment-identity"])
        }

        XCTAssertTrue(
            ContextStore.needsAppUpgrade(at: fixture.databaseURL),
            "a database behind this binary was not recognised as needing the app to upgrade it")

        XCTAssertThrowsError(try ContextStore(url: fixture.databaseURL, readOnly: true)) { error in
            guard case ContextStoreError.awaitingAppUpgrade = error else {
                return XCTFail("opened an unqueryable database instead of naming the reason: \(error)")
            }
        }
    }

    /// Absence and staleness are different faults with different remedies — only one of them is
    /// fixed by launching the app — so the check must not answer "upgrade me" for a database that
    /// is simply not there.
    func testAMissingDatabaseIsNotReportedAsNeedingAnUpgrade() {
        XCTAssertFalse(
            ContextStore.needsAppUpgrade(at: fixture.root.appendingPathComponent("nothing-here.db")))
    }
}
