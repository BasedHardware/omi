import Foundation
import GRDB
import XCTest

@testable import ContextCore

/// The two things retention leaves behind, and the one mistake neither sweep may ever make.
///
/// Retention expires a frame's *picture* and keeps its row, so everything the row stopped naming has
/// to go with it: the image on disk and the accessibility subtrees its tree was built from. Neither
/// followed, so both grew forever — the images invisibly, because `framesBytesOnDisk` counts rows
/// and an orphan has none, and `ax_nodes` measurably, at ~370 MB a year on the shape this machine
/// actually captures.
///
/// Every test here is written twice over, because a sweep has two failure modes and they are not
/// equally bad. Failing to collect garbage costs disk. Collecting something live costs the user a
/// screenshot they still have a row for, or an accessibility tree with a hole in it — so each sweep
/// is asserted to remove what it must *and* to leave alone the thing that looks identical to it
/// from a distance: the artefact written seconds ago whose row has not landed yet.
final class RetentionSweepTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        fixture = try Fixture(seeded: false)
    }

    override func tearDownWithError() throws {
        fixture?.tearDown()
        fixture = nil
    }

    private var store: ContextStore { fixture.store }

    /// Long enough ago that anything stamped with it is stale under any grace this suite uses.
    private let longAgo: Double = 0

    // MARK: - Orphaned images

    /// The whole reason the file sweep exists: both prune paths commit the row deletes and then
    /// unlink, so anything that interrupts them leaves an image nothing will ever name again.
    /// Rehearsed here the way it actually happens — the rows go, the process does not come back to
    /// finish — and the next sweep has to be what reclaims it.
    func testAnImageOrphanedByAnInterruptedPruneIsReclaimedByTheNextSweep() throws {
        let kept = try writeImage(named: "kept.heic", ageSeconds: 8 * 86_400)
        let orphan = try writeImage(named: "orphaned.heic", ageSeconds: 40 * 86_400)

        try fixture.addFrame(at: ContextTime.now - 8 * 86_400, app: "Cursor", imagePath: kept.path)
        try fixture.addFrame(
            at: ContextTime.now - 40 * 86_400, app: "Cursor", imagePath: orphan.path)

        // The interruption: the row delete committed, the unlink never ran.
        try store.write { db in
            try db.execute(
                sql: "DELETE FROM frames WHERE imagePath = ?", arguments: [orphan.path])
        }
        XCTAssertTrue(exists(orphan), "the fixture failed to orphan the file")

        XCTAssertEqual(try store.sweepOrphanedFrameImages(), 1)

        XCTAssertFalse(exists(orphan), "the orphan survived the sweep")
        XCTAssertTrue(exists(kept), "a file a row still names was deleted")
        // And the sweep is idempotent: a second pass finds nothing left to do.
        XCTAssertEqual(try store.sweepOrphanedFrameImages(), 0)
    }

    /// **The inverse error, and the reason the sweep is not a plain set difference.**
    ///
    /// `ScreenWatcher` writes the image and only then hands the frame over to be inserted, so at any
    /// instant the newest screenshot on disk legitimately has no row. A sweep running in that gap
    /// sees exactly what an orphan looks like. It must not act on it — and then the row lands and
    /// the file has to still be there.
    func testAnImageWrittenMomentsAgoSurvivesASweepThatRunsBeforeItsRowLands() throws {
        let inFlight = try writeImage(named: "in-flight.heic", ageSeconds: 2)
        let settled = try writeImage(named: "settled.heic", ageSeconds: 40 * 86_400)

        XCTAssertEqual(
            try store.sweepOrphanedFrameImages(), 1,
            "the sweep did not collect the one file that was genuinely stale")
        XCTAssertTrue(exists(inFlight), "a screenshot was deleted out from under live capture")
        XCTAssertFalse(exists(settled))

        // The write the sweep raced: the row arrives afterwards and finds its image intact.
        try fixture.addFrame(at: ContextTime.now, app: "Cursor", imagePath: inFlight.path)
        XCTAssertEqual(try store.framesBytesOnDisk(), Int64(Self.imageBytes.count))
        XCTAssertEqual(try store.sweepOrphanedFrameImages(), 0)
        XCTAssertTrue(exists(inFlight))
    }

    /// `Frames/` is this app's directory but it is not only ever this app's files: `Data.write` with
    /// `.atomic` stages a partial file beside its destination, and a user can drop anything into a
    /// folder. The sweep deletes the shapes capture writes and nothing else.
    func testTheSweepLeavesFilesCaptureDidNotWrite() throws {
        let note = try writeFile(named: "notes.txt", ageSeconds: 40 * 86_400)
        let partial = try writeFile(named: ".dat.nosync0e1f.9Kd3lX", ageSeconds: 40 * 86_400)
        let orphan = try writeImage(named: "orphaned.jpg", ageSeconds: 40 * 86_400)

        XCTAssertEqual(try store.sweepOrphanedFrameImages(), 1)

        XCTAssertFalse(exists(orphan))
        XCTAssertTrue(exists(note), "the sweep deleted a file this app never wrote")
        XCTAssertTrue(exists(partial), "the sweep deleted a partially written capture")
    }

    /// A sweep is a delete, and the MCP reader may not perform one. It has to refuse before it walks
    /// the directory, not after: a reader that found nothing to collect would report a successful
    /// sweep it was never entitled to run.
    func testSweepsThroughAReadOnlyStoreRefuse() throws {
        _ = try writeImage(named: "orphaned.heic", ageSeconds: 40 * 86_400)
        let reader = try ContextStore(url: fixture.databaseURL, readOnly: true)

        XCTAssertThrowsError(try reader.sweepOrphanedFrameImages()) { error in
            XCTAssertStoreError(error, .readOnly)
        }
        XCTAssertThrowsError(try reader.sweepAXNodes()) { error in
            XCTAssertStoreError(error, .readOnly)
        }
    }

    /// Retention is one call, and it has to finish the job it starts: the pictures it expires are
    /// exactly what orphans the files and the subtrees. The count it returns stays images, because
    /// its caller reports it as images.
    ///
    /// **This is also the test that keeps `sweepAXNodes` alive.** Frame rows are no longer deleted
    /// by retention, so if expiry left `axRootHash` in place every node would stay reachable from a
    /// row that lives forever, and the sweep this file exists for would collect nothing ever again —
    /// the table would go back to growing without bound. The subtree count going to zero here is
    /// what proves the root was cleared with the picture; the frame's `ocrText` and `axText`, which
    /// `StoreTests` asserts separately, are what proves the text was not.
    func testEnforceRetentionCollectsWhatItsOwnExpiriesOrphaned() throws {
        let old = try writeImage(named: "old.heic", ageSeconds: 40 * 86_400)
        let tree = try seedTree(node("AXWindow", text: "Mail", children: [node("AXStaticText", text: "Inbox")]), seenAt: longAgo)
        let frame = try fixture.addFrame(
            at: ContextTime.now - 40 * 86_400, app: "Mail", imagePath: old.path,
            axRootHash: tree.root)

        let expired = try store.enforceRetention(olderThanDays: 30)

        XCTAssertEqual(expired, 1, "the return value must count images, not everything collected")
        XCTAssertFalse(exists(old), "the frame's image outlived the row that stopped naming it")
        XCTAssertEqual(try nodeCount(), 0, "the frame's subtrees outlived the tree root")
        // And the row itself is untouched, which is the whole tier.
        let rows: Int = try store.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM frames WHERE id = ?", arguments: [frame]) ?? 0
        }
        XCTAssertEqual(rows, 1, "retention deleted a frame row")
    }

    // MARK: - Unreachable accessibility subtrees

    /// The bound the table never had. A subtree lives exactly as long as some frame still needs it,
    /// and "needs" is reachability through the payload rather than a foreign key — which is what
    /// makes a shared node survive the frame that first paid for it.
    func testTheSweepCollectsSubtreesNoFrameReachesAndKeepsEverySharedOne() throws {
        // Two windows sharing a toolbar, which is the sharing the whole table is built on.
        let toolbar = node("AXToolbar", text: "Send", children: [node("AXButton", text: "Reply")])
        let mail = node("AXWindow", text: "Mail", children: [toolbar, node("AXStaticText", text: "Inbox")])
        let draft = node("AXWindow", text: "Draft", children: [toolbar, node("AXStaticText", text: "To:")])

        let mailTree = try seedTree(mail, seenAt: longAgo)
        let draftTree = try seedTree(draft, seenAt: longAgo)
        let mailFrame = try fixture.addFrame(
            at: Fixture.base, app: "Mail", axRootHash: mailTree.root)
        try fixture.addFrame(at: Fixture.base + 10, app: "Mail", axRootHash: draftTree.root)

        let before = try nodeCount()
        XCTAssertEqual(try store.sweepAXNodes(), 0, "a live tree was collected")
        XCTAssertEqual(try nodeCount(), before)

        // Retention takes the first frame. Everything only *it* reached is now unreachable; the
        // shared toolbar is not.
        try store.write { db in
            try db.execute(sql: "DELETE FROM frames WHERE id = ?", arguments: [mailFrame])
        }

        let collected = try store.sweepAXNodes()

        XCTAssertEqual(collected, 2, "expected the window and its own label, and nothing else")
        try assertTreeIsWhole(draftTree, "the surviving frame's tree lost a node")
        XCTAssertEqual(try nodeCount(), draftTree.hashes.count)
    }

    /// A tree is only whole if *every* node of it survives, so the sweep is asserted against the
    /// deepest thing it could get wrong: a leaf reachable only through several payloads.
    func testReachabilityFollowsThePayloadAllTheWayDown() throws {
        let deep = node(
            "AXWindow", text: "Xcode",
            children: [
                node(
                    "AXGroup", text: nil,
                    children: [
                        node(
                            "AXScrollArea", text: nil,
                            children: [node("AXStaticText", text: "func insertSegment")])
                    ])
            ])
        let tree = try seedTree(deep, seenAt: longAgo)
        // Garbage from a frame that is long gone, sharing nothing with the live tree.
        let dead = try seedTree(node("AXWindow", text: "Terminal"), seenAt: longAgo)
        try fixture.addFrame(at: Fixture.base, app: "Xcode", axRootHash: tree.root)

        XCTAssertEqual(try store.sweepAXNodes(), dead.hashes.count)

        try assertTreeIsWhole(tree, "a nested node was collected while its frame still needed it")
    }

    /// **The interleaving that can orphan a live tree, run in the order that causes it.**
    ///
    /// A subtree that already exists is *re-used* rather than re-inserted: `INSERT OR IGNORE`
    /// writes no row, so a node whose every frame aged out weeks ago can be picked up again by the
    /// capture happening right now without anything about it changing. If the sweep scanned before
    /// that capture and deleted after it, the frame that lands next references a row that is gone.
    ///
    /// The three phases are driven here in exactly that order. The delete re-tests staleness inside
    /// its own statement, so the re-used node no longer matches it and survives.
    func testANodeReUsedBetweenTheScanAndTheDeleteIsNotCollected() throws {
        let shared = node("AXToolbar", text: "Send")
        let stale = try seedTree(node("AXWindow", text: "Mail", children: [shared]), seenAt: longAgo)
        let sharedHash = AccessibilityTree.rootHash(of: shared)

        // No frame references any of it: every row is a candidate.
        let now = ContextTime.now
        let cutoff = now - ContextStore.unreferencedGraceSeconds
        let reachable = try store.reachableAXNodeHashes()
        let doomed = try store.collectableAXNodeHashes(
            reachable: reachable, cutoff: cutoff, limit: ContextStore.axNodeSweepLimit)
        XCTAssertEqual(Set(doomed), Set(stale.hashes), "the scan did not see the whole tree")

        // The capture that arrives in the gap. Its tree re-uses the toolbar, so the store is
        // *offered* the node without a row being written for it.
        let revived = try seedTree(
            node("AXWindow", text: "Draft", children: [shared]), seenAt: now)

        XCTAssertEqual(try store.deleteAXNodes(doomed, stalerThan: cutoff), 1)

        XCTAssertTrue(
            try nodeExists(sharedHash),
            "a subtree re-used by a capture in flight was collected before its frame landed")
        // And the frame the capture was about to write finds its whole tree intact.
        try fixture.addFrame(at: now, app: "Mail", axRootHash: revived.root)
        try assertTreeIsWhole(revived, "the revived frame's tree has a hole in it")
    }

    /// The same protection stated as a rule rather than as a race: a node the store has been offered
    /// inside the grace window is never collected, however unreachable it looks. That is what covers
    /// the ordinary case — nodes are written *before* the frame that names them — without any
    /// interleaving at all.
    func testARecentlyOfferedNodeIsKeptEvenWithNoFrameNamingIt() throws {
        let now = ContextTime.now
        let fresh = try seedTree(node("AXWindow", text: "Mail"), seenAt: now - 5)
        let old = try seedTree(node("AXWindow", text: "Terminal"), seenAt: longAgo)

        XCTAssertEqual(try store.sweepAXNodes(now: now), old.hashes.count)

        XCTAssertTrue(try nodeExists(fresh.root), "a tree captured five seconds ago was collected")
        XCTAssertFalse(try nodeExists(old.root))

        // Once the grace has passed and nothing has claimed it, the same node is collectable — the
        // window is a delay, not an exemption.
        XCTAssertEqual(
            try store.sweepAXNodes(now: now + ContextStore.unreferencedGraceSeconds + 1), 1)
        XCTAssertFalse(try nodeExists(fresh.root))
    }

    /// Re-seeing a subtree has to move its clock forward, or the grace window protects only nodes
    /// that happened to be new — and re-use is the common case, not the rare one.
    func testReOfferingAStoredNodeRefreshesWhenItWasLastSeen() throws {
        let tree = node("AXWindow", text: "Mail")
        let records = AccessibilityTree.records(of: tree)

        XCTAssertEqual(try store.insertAXNodes(records, firstSeenFrameId: nil, seenAt: longAgo), 1)
        // Second offer: nothing new to write, which is exactly why the timestamp has to move.
        XCTAssertEqual(
            try store.insertAXNodes(records, firstSeenFrameId: nil, seenAt: 5_000), 0,
            "a content address that already exists must not be counted as a new row")

        XCTAssertEqual(try lastSeen(AccessibilityTree.rootHash(of: tree)), 5_000)
        // And it never moves backwards: an out-of-order write must not make a live node collectable.
        XCTAssertEqual(try store.insertAXNodes(records, firstSeenFrameId: nil, seenAt: 1_000), 0)
        XCTAssertEqual(try lastSeen(AccessibilityTree.rootHash(of: tree)), 5_000)
    }

    /// A backlog is reclaimed over several passes rather than in one transaction that holds the
    /// writer while capture is running. Progress per pass is what matters — a bound that could stall
    /// would leave the table growing exactly as it did before.
    func testTheSweepIsBoundedPerPassAndStillFinishesTheBacklog() throws {
        for index in 0..<12 {
            _ = try seedTree(node("AXWindow", text: "window \(index)"), seenAt: longAgo)
        }
        XCTAssertEqual(try nodeCount(), 12)

        XCTAssertEqual(try store.sweepAXNodes(limit: 5), 5)
        XCTAssertEqual(try store.sweepAXNodes(limit: 5), 5)
        XCTAssertEqual(try store.sweepAXNodes(limit: 5), 2)
        XCTAssertEqual(try nodeCount(), 0)
        XCTAssertEqual(try store.sweepAXNodes(limit: 5), 0)
    }

    /// The migration has to make the *existing* population collectable. A nullable column, or one
    /// defaulted into the future, would leave every row captured before today permanently exempt —
    /// which is the one population this whole change exists for.
    func testNodesStoredBeforeTheMigrationAreCollectable() throws {
        let url = fixture.root.appendingPathComponent("pre-sweep.db")
        let hash: Data
        do {
            let legacy = try ContextStore(url: url)
            let records = AccessibilityTree.records(of: node("AXWindow", text: "Mail"))
            hash = records[0].hash
            _ = try legacy.insertAXNodes(records, firstSeenFrameId: nil, seenAt: ContextTime.now)
            try legacy.write { db in
                try db.execute(sql: "ALTER TABLE ax_nodes DROP COLUMN lastSeenAt")
                try db.execute(
                    sql: "DELETE FROM grdb_migrations WHERE identifier = ?",
                    arguments: ["v10-ax-node-last-seen"])
            }
        }

        let upgraded = try ContextStore(url: url)

        let stamp: Double = try upgraded.read { db in
            try Double.fetchOne(
                db, sql: "SELECT lastSeenAt FROM ax_nodes WHERE hash = ?", arguments: [hash]) ?? -1
        }
        XCTAssertEqual(stamp, 0, "an existing row was backfilled with a time it was never seen at")
        XCTAssertEqual(try upgraded.sweepAXNodes(), 1, "the pre-migration backlog is uncollectable")
    }

    // MARK: - Fixtures

    /// A minimal HEIC stand-in. Only its length and its existence matter.
    private static let imageBytes = Data([0xFF, 0xD8, 0xFF, 0xD9])

    private func node(_ role: String, text: String?, children: [AXNode] = []) -> AXNode {
        AXNode(role: role, subrole: nil, text: text, children: children)
    }

    private struct SeededTree {
        let root: Data
        let hashes: [Data]
    }

    /// Stores a whole tree the way capture does, stamped with a time the test controls.
    @discardableResult
    private func seedTree(_ tree: AXNode, seenAt: Double) throws -> SeededTree {
        let records = AccessibilityTree.records(of: tree)
        _ = try store.insertAXNodes(records, firstSeenFrameId: nil, seenAt: seenAt)
        return SeededTree(root: AccessibilityTree.rootHash(of: tree), hashes: records.map(\.hash))
    }

    private func assertTreeIsWhole(
        _ tree: SeededTree, _ message: String, file: StaticString = #filePath, line: UInt = #line
    ) throws {
        for hash in tree.hashes {
            XCTAssertTrue(try nodeExists(hash), message, file: file, line: line)
        }
    }

    private func nodeExists(_ hash: Data) throws -> Bool {
        try store.read { db in
            try Int.fetchOne(
                db, sql: "SELECT COUNT(*) FROM ax_nodes WHERE hash = ?", arguments: [hash]) == 1
        }
    }

    private func nodeCount() throws -> Int {
        try store.read { db in try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM ax_nodes") ?? -1 }
    }

    private func lastSeen(_ hash: Data) throws -> Double {
        try store.read { db in
            try Double.fetchOne(
                db, sql: "SELECT lastSeenAt FROM ax_nodes WHERE hash = ?", arguments: [hash]) ?? -1
        }
    }

    /// Writes a file into a day directory under this store's own frames root, aged by touching its
    /// modification time — which is what capture time means for a file written once and never again.
    @discardableResult
    private func writeImage(named name: String, ageSeconds: Double) throws -> URL {
        try writeFile(named: name, ageSeconds: ageSeconds)
    }

    @discardableResult
    private func writeFile(named name: String, ageSeconds: Double) throws -> URL {
        let day = store.framesRoot.appendingPathComponent("2025-10-09", isDirectory: true)
        try FileManager.default.createDirectory(at: day, withIntermediateDirectories: true)
        let url = day.appendingPathComponent(name)
        try Self.imageBytes.write(to: url)
        try FileManager.default.setAttributes(
            [.modificationDate: Date(timeIntervalSince1970: ContextTime.now - ageSeconds)],
            ofItemAtPath: url.path)
        return url
    }

    private func exists(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.path)
    }
}
