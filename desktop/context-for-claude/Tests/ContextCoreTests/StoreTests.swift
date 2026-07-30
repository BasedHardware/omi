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
            ["v1", "v3-segment-confidence", "v4-segment-speaker", "v5-cloud-segment-identity",
             "v6-accessibility-tree", "v7-frame-bundle-id"])

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
             "v6-accessibility-tree", "v7-frame-bundle-id", UploadQueue.migrationIdentifier])
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
            ["v1", "v3-segment-confidence", "v4-segment-speaker", "v5-cloud-segment-identity",
             "v6-accessibility-tree", "v7-frame-bundle-id"])

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
             "v6-accessibility-tree", "v7-frame-bundle-id", UploadQueue.migrationIdentifier])
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
        // The byte cap refuses before it scans, not after: a reader that is under the cap must not
        // report a successful sweep it never performed.
        XCTAssertThrowsError(try reader.pruneFrames(toFitBytes: 0)) { error in
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

    // MARK: - Pruning to a byte cap

    func testByteCapDeletesTheOldestFramesFirstAndStopsAtTheCap() throws {
        let store = fixture.store
        let ocr = ["ancient vorpal", "old brillig", "middling mimsy", "recent slithy", "newest borogove"]
        var ids = [Int64](repeating: 0, count: 5)
        var paths = [String](repeating: "", count: 5)

        // Inserted out of chronological order on purpose: "oldest" has to mean `capturedAt`, never
        // insertion order — a cap that deletes by rowid would pass a same-order corpus and still
        // throw away the wrong week on a real machine.
        for index in [4, 2, 0, 3, 1] {
            paths[index] = try writeImage(named: "frame-\(index).jpg", bytes: 1_000)
            ids[index] = try fixture.addFrame(
                at: Fixture.base + Double(index) * 60, app: "Xcode", window: "frame \(index)",
                ocr: ocr[index], imagePath: paths[index])
        }
        XCTAssertEqual(try store.framesBytesOnDisk(), 5_000)

        // Room for exactly three frames: the two oldest go, and not one frame more.
        let deleted = try store.pruneFrames(toFitBytes: 3_000)

        XCTAssertEqual(deleted, 2, "the cap over- or under-deleted")
        XCTAssertEqual(try store.framesBytesOnDisk(), 3_000)

        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, [ids[2], ids[3], ids[4]], "what survived is not the newest stretch")

        for index in [0, 1] {
            XCTAssertFalse(
                FileManager.default.fileExists(atPath: paths[index]),
                "frame \(index)'s JPEG outlived its row")
        }
        for index in [2, 3, 4] {
            XCTAssertTrue(
                FileManager.default.fileExists(atPath: paths[index]),
                "a surviving frame's JPEG was unlinked")
        }

        // This sweep deletes by id list rather than by cutoff, so it needs its own proof that the FTS
        // `ad` trigger ran: an index still answering with deleted rows is corrupt, not merely stale.
        XCTAssertEqual(try frameMatches("vorpal"), 0)
        XCTAssertEqual(try frameMatches("brillig"), 0)
        XCTAssertEqual(try frameMatches("mimsy"), 1)
        XCTAssertEqual(try frameMatches("borogove"), 1)
    }

    func testByteCapIsANoOpWhenAlreadyUnderTheCap() throws {
        let store = fixture.store
        // Nothing captured yet: the tightest possible cap still has nothing to do.
        XCTAssertEqual(try store.pruneFrames(toFitBytes: 0), 0)

        var paths: [String] = []
        for index in 0..<3 {
            let path = try writeImage(named: "frame-\(index).jpg", bytes: 1_000)
            paths.append(path)
            try fixture.addFrame(
                at: Fixture.base + Double(index) * 60, app: "Xcode", window: "frame \(index)",
                ocr: "note \(index)", imagePath: path)
        }

        XCTAssertEqual(try store.pruneFrames(toFitBytes: 10_000), 0, "deleted while under the cap")
        // "At or under": a total sitting exactly on the cap is not over it.
        XCTAssertEqual(try store.pruneFrames(toFitBytes: 3_000), 0, "deleted while exactly at the cap")

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
        XCTAssertEqual(try store.pruneFrames(toFitBytes: 0), 1)

        XCTAssertEqual(try count(of: "frames"), 0)
        XCTAssertEqual(try count(of: "segments"), 1, "retention ate a transcript line")
        XCTAssertEqual(try count(of: "sessions"), 1, "retention ate a session")
        XCTAssertEqual(try segmentMatches("recaptured"), 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: path))
    }

    func testByteCapSweepsFramesWhoseJPEGWasNeverWritten() throws {
        let store = fixture.store
        // A frame whose OCR was captured but whose JPEG was skipped costs no disk. It is still
        // deleted when it is older than something that has to go, so what survives stays one
        // contiguous recent stretch rather than a corpus with holes in it.
        try fixture.addFrame(at: Fixture.base, app: "Xcode", window: "no image", ocr: "ancient vorpal")
        let olderPath = try writeImage(named: "older.jpg", bytes: 1_000)
        try fixture.addFrame(
            at: Fixture.base + 60, app: "Xcode", window: "older", ocr: "old brillig",
            imagePath: olderPath)
        let newestPath = try writeImage(named: "newest.jpg", bytes: 1_000)
        let newest = try fixture.addFrame(
            at: Fixture.base + 120, app: "Xcode", window: "newest", ocr: "newest slithy",
            imagePath: newestPath)

        XCTAssertEqual(try store.framesBytesOnDisk(), 2_000, "a row with no JPEG must count as zero")

        let deleted = try store.pruneFrames(toFitBytes: 1_000)

        XCTAssertEqual(deleted, 2)
        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, [newest])
        XCTAssertFalse(FileManager.default.fileExists(atPath: olderPath))
        XCTAssertTrue(FileManager.default.fileExists(atPath: newestPath))
    }

    func testEnforceRetentionAppliesWhicheverBoundIsTighter() throws {
        let store = fixture.store
        // The age half reads the wall clock, so this corpus is anchored to it — sampled once, so
        // every row shares one reading.
        let now = ContextTime.now
        let ancientPath = try writeImage(named: "ancient.jpg", bytes: 1_000)
        try fixture.addFrame(
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

        // Age takes the 40-day-old frame; the 2 KiB cap then takes one more that age would have kept.
        let removed = try store.enforceRetention(olderThanDays: 30, toFitBytes: 2_000)

        XCTAssertEqual(removed, 2)
        let remaining: [Int64] = try store.read { db in
            try Int64.fetchAll(db, sql: "SELECT id FROM frames ORDER BY capturedAt")
        }
        XCTAssertEqual(remaining, [recentIds[1], recentIds[2]])
        XCTAssertEqual(try store.framesBytesOnDisk(), 2_000)
        XCTAssertFalse(FileManager.default.fileExists(atPath: ancientPath))
        XCTAssertFalse(FileManager.default.fileExists(atPath: recentPaths[0]))
        XCTAssertTrue(FileManager.default.fileExists(atPath: recentPaths[1]))
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
