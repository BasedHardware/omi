import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// What a capture tick is allowed to leave behind, and in what order.
///
/// Two defects with one shape sit behind this file, and neither is observable from the filesystem
/// after the fact — which is exactly why the write is injected here rather than asserted on disk:
///
/// - **An excluded website's screenshot was written and then unlinked.** The HEIC went to disk, the
///   accessibility tree was read *afterwards*, and only then did the re-judgement notice the frame
///   named a domain the user had excluded and delete the file. `unlink` does not scrub blocks, no
///   `frames` row ever referenced the file so pruning could never have reached it, and an APFS
///   snapshot or a Time Machine pass inside that window keeps it for good. "Deleted a moment later"
///   and "never written" are different promises, and the pipeline made the second one in a comment
///   four lines above the write.
/// - **A stopped watcher went on writing.** Cancelling the loop does not resume a tick already
///   suspended in OCR or in an accessibility walk, so that tick finished after the user switched
///   capture off and handed over a window's full accessibility text — into rows nothing references
///   and pruning never reaches.
///
/// So the assertions are about *whether bytes were ever produced*, not about what survives.
///
/// Isolated per test rather than per class: `setUpWithError` is inherited unisolated, and a class
/// annotation would override it with a main-actor method.
final class CaptureWriteOrderTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("capture-write-order-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    /// The regression. A window whose accessibility text names an excluded site must cost nothing:
    /// no bytes, no row, no subtree.
    @MainActor
    func testAnExcludedWebsiteNeverReachesTheDisk() throws {
        let engine = makeEngine()
        engine.excludeWebsite("mail.proton.me")
        let watcher = ScreenWatcher(exclusions: engine)
        let recorder = Recorder()
        recorder.wire(to: watcher)

        // Admitted with nothing that names the site — the address could not be read this tick,
        // which is the ordinary case and the reason the text is judged at all.
        let ticket = try XCTUnwrap(
            engine.admit(
                CaptureSubject(
                    bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Inbox")
            ).ticket)

        watcher.emit(
            frame(axText: "Inbox\nmail.proton.me\nDrafts\nSent"),
            ticket: ticket,
            axNodes: [AXNodeRecord(hash: Data([0x01]), payload: Data([0x02]))],
            imageData: Data("pretend-heic".utf8))

        XCTAssertEqual(
            recorder.writes, 0,
            "a screenshot of an excluded website was produced — deleting it afterwards is not the "
                + "same as never having written it")
        XCTAssertEqual(recorder.order, [], "nothing at all should have been handed over")
    }

    /// The ordering, stated positively so the test above cannot pass by writing nothing ever.
    ///
    /// Nodes before the frame is the pre-existing rule — a frame carries a root hash into a table
    /// those rows have to be in already — and the write goes in front of both, after the last
    /// judgement, with nothing suspended in between.
    @MainActor
    func testAFrameThatSurvivesTheGateIsWrittenOnceAndItsNodesGoFirst() throws {
        let engine = makeEngine()
        let watcher = ScreenWatcher(exclusions: engine)
        let recorder = Recorder()
        recorder.wire(to: watcher)

        let ticket = try XCTUnwrap(
            engine.admit(
                CaptureSubject(
                    bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Inbox")
            ).ticket)

        watcher.emit(
            frame(axText: "Inbox\nDrafts\nSent"),
            ticket: ticket,
            axNodes: [AXNodeRecord(hash: Data([0x01]), payload: Data([0x02]))],
            imageData: Data("pretend-heic".utf8))

        XCTAssertEqual(recorder.writes, 1)
        XCTAssertEqual(recorder.order, ["write", "nodes", "frame"])
        XCTAssertEqual(
            recorder.frames.first?.imagePath, Recorder.path,
            "the row must point at the file this tick actually wrote")
    }

    /// Stopping capture stops capture, including for the tick that was already in flight.
    ///
    /// `onAXNodes` was the one hand-over `stopScreen` forgot, and forgetting it was invisible: the
    /// accessibility rows it wrote are referenced by no frame, so nothing shows them and pruning —
    /// which walks the `frames` table — never reaches them. They simply stay.
    @MainActor
    func testAStoppedWatcherWritesNothingAndStoresNothing() throws {
        let engine = makeEngine()
        let watcher = ScreenWatcher(exclusions: engine)
        let recorder = Recorder()
        recorder.wire(to: watcher)

        let ticket = try XCTUnwrap(
            engine.admit(
                CaptureSubject(
                    bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Inbox")
            ).ticket)

        watcher.stop()
        watcher.emit(
            frame(axText: "Inbox\nDrafts\nSent"),
            ticket: ticket,
            axNodes: [AXNodeRecord(hash: Data([0x01]), payload: Data([0x02]))],
            imageData: Data("pretend-heic".utf8))

        XCTAssertEqual(recorder.writes, 0, "a stopped recorder wrote a screenshot")
        XCTAssertEqual(
            recorder.order, [],
            "a stopped recorder stored a window's accessibility text, in rows no frame references")
    }

    // MARK: - Helpers

    private func makeEngine() -> ExclusionEngine {
        ExclusionEngine(
            configurationURL: root.appendingPathComponent("exclusions.json"),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
    }

    private func frame(axText: String) -> Frame {
        Frame(
            capturedAt: 1_700_000_000,
            appName: "Arc",
            bundleId: "company.thebrowser.Browser",
            windowTitle: "Inbox",
            ocrText: "Inbox",
            axText: axText)
    }
}

/// Everything one `emit` was allowed to do, in the order it did it.
///
/// At file scope rather than nested, so it carries no actor isolation of its own: the hand-overs it
/// installs are called from the watcher's main actor, and the recorder should add no rules of its
/// own to what is being observed.
private final class Recorder {
    static let path = "/tmp/context-for-claude-test-frame.heic"

    private(set) var writes = 0
    private(set) var order: [String] = []
    private(set) var frames: [Frame] = []

    @MainActor
    func wire(to watcher: ScreenWatcher) {
        watcher.writeImage = { [self] _, _ in
            writes += 1
            order.append("write")
            return Self.path
        }
        watcher.onAXNodes = { [self] _ in order.append("nodes") }
        watcher.onFrame = { [self] frame in
            order.append("frame")
            frames.append(frame)
        }
    }
}
