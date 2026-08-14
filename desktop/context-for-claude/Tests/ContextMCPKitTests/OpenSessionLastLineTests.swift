import ContextCore
import Foundation
import XCTest

@testable import ContextMCPKit

/// What a session summary already knows about a conversation nothing ever closed.
///
/// A crash or a force-quit leaves `endedAt` null forever, and the app closes those at their last
/// line on the next launch. It used to find that line by reading each candidate's transcript back —
/// every segment of every session in the scan, on every launch, to close what is usually one. It
/// does not need to: the summary is measured to `MAX(segments.endedAt)` in the query that produced
/// it, and to the session's own start when it holds no lines at all. That is the property the
/// recovery reads instead, so it is the property worth pinning — the summary is also what the
/// `conversations` tool renders an open session's span from.
final class OpenSessionLastLineTests: XCTestCase {
    /// 2025-10-09T08:53:20Z, fixed — a test that reads the wall clock fails on a Tuesday.
    private let base: Double = 1_760_000_000
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("open-session-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { [root] in try? FileManager.default.removeItem(at: root!) }
    }

    private func makeStore() throws -> ContextStore {
        try ContextStore(url: root.appendingPathComponent("context.db"))
    }

    func testAnUnclosedSessionIsAlreadyMeasuredToTheEndOfItsLastLine() throws {
        let store = try makeStore()
        let sessionId = try store.openSession(at: base, appHint: "zoom.us")
        for start in [base + 10, base + 300] {
            _ = try store.insertSegment(
                Segment(
                    sessionId: sessionId, startedAt: start, endedAt: start + 30, source: .mic,
                    text: "a line inside this conversation"))
        }

        let summary = try XCTUnwrap(Queries.sessions(store, limit: 10).first)

        XCTAssertNil(summary.endedAt, "the fixture closed the session; there is nothing to recover")
        // The *end* of the last line, not its start: a conversation does not stop at the moment its
        // final sentence began, and a recovery that closed it there would lose that sentence from
        // every crashed session's duration.
        XCTAssertEqual(
            summary.startedAt + summary.durationSeconds, base + 330, accuracy: 0.001,
            "an open session's summary does not reach its last line")
    }

    /// The other half of what the old loop spelled out with `?? session.startedAt`: a session that
    /// crashed before anything was said has no last line to be closed at.
    func testAnUnclosedSessionThatRecordedNothingIsMeasuredToItsOwnStart() throws {
        let store = try makeStore()
        _ = try store.openSession(at: base, appHint: "zoom.us")

        let summary = try XCTUnwrap(Queries.sessions(store, limit: 10).first)

        XCTAssertNil(summary.endedAt)
        XCTAssertEqual(summary.durationSeconds, 0, accuracy: 0.001)
    }
}
