import ContextCore
import Foundation
import XCTest

/// A throwaway `ContextStore` under the system temp directory, plus the deterministic corpus the
/// query tests read.
///
/// Every timestamp in the corpus is derived from one fixed epoch rather than from `Date()`. A test
/// that moves with the wall clock is a test that eventually fails on a Tuesday for no reason, and
/// the whole point of these tests is that a failure means a regression.
final class Fixture {
    /// 2025-10-09T08:53:20Z. Deliberately not the current year: any year that shows up in a rendered
    /// string can then only have come from this corpus.
    static let base: Double = 1_760_000_000

    /// The temp directory holding the database and the fake JPEGs. Removed in `tearDown`.
    let root: URL
    let store: ContextStore

    /// Closed two-sided session: three lines, both speakers, an `appHint`.
    private(set) var sessionA: Int64 = 0
    /// Open one-sided session: the user thinking out loud, nobody else captured.
    private(set) var sessionB: Int64 = 0

    init(seeded: Bool = true) throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        store = try ContextStore(url: root.appendingPathComponent("context.db"))
        if seeded { try seed() }
    }

    var databaseURL: URL { root.appendingPathComponent("context.db") }

    func tearDown() {
        try? FileManager.default.removeItem(at: root)
    }

    // MARK: - Corpus

    /// Two sessions and three frames, arranged so that:
    /// - "pricing" matches two spoken lines and one frame (recall has to merge and rank them),
    /// - "roadmap" matches one spoken line and one frame,
    /// - session B is one-sided and still open,
    /// - no term used by a test matches a row it is not meant to.
    private func seed() throws {
        sessionA = try store.openSession(at: Self.base, appHint: "zoom.us")
        try store.closeSession(sessionA, at: Self.base + 600)
        try addSegment(session: sessionA, at: Self.base + 10, source: .mic,
                       "we decided to ship the pricing change on Friday")
        try addSegment(session: sessionA, at: Self.base + 30, source: .system,
                       "sounds good, I will draft the migration plan")
        try addSegment(session: sessionA, at: Self.base + 60, source: .mic,
                       "remind me about the pricing rollout later")

        // Left open on purpose: `sessions` has to derive a duration from the last line.
        sessionB = try store.openSession(at: Self.base + 7200, appHint: "Slack")
        try addSegment(session: sessionB, at: Self.base + 7210, source: .mic,
                       "thinking out loud about the roadmap")

        try addFrame(at: Self.base + 100, app: "Google Chrome", window: "Pricing — Notion",
                     ocr: "pricing change rollout notes", imagePath: writeImage(named: "frame-1.jpg"))
        try addFrame(at: Self.base + 130, app: "Google Chrome", window: "Roadmap — Notion",
                     ocr: "quarterly roadmap notes")
        try addFrame(at: Self.base + 7300, app: "Xcode", window: "Store.swift", ocr: "func insertSegment")
    }

    // MARK: - Builders

    @discardableResult
    func addSegment(
        session: Int64,
        at startedAt: Double,
        duration: Double = 5,
        source: SegmentSource,
        _ text: String
    ) throws -> Int64 {
        try store.insertSegment(
            Segment(
                sessionId: session,
                startedAt: startedAt,
                endedAt: startedAt + duration,
                source: source,
                text: text))
    }

    @discardableResult
    func addFrame(
        at capturedAt: Double,
        app: String?,
        window: String? = nil,
        ocr: String? = nil,
        imagePath: String? = nil,
        axRootHash: Data? = nil
    ) throws -> Int64 {
        try store.insertFrame(
            Frame(
                capturedAt: capturedAt,
                appName: app,
                windowTitle: window,
                ocrText: ocr,
                imagePath: imagePath,
                axRootHash: axRootHash))
    }

    /// A stand-in for a captured screenshot. Only its existence matters — pruning unlinks by path.
    @discardableResult
    func writeImage(named name: String) throws -> String {
        let directory = root.appendingPathComponent("Frames", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent(name)
        // A minimal JPEG SOI/EOI pair, so anything that sniffs the file sees a plausible image.
        try Data([0xFF, 0xD8, 0xFF, 0xD9]).write(to: url)
        return url.path
    }
}

// MARK: - Assertions

/// Compares by case name rather than `==`: `ContextStoreError` is not declared `Equatable`, and a
/// test should not be the reason a source file has to grow a conformance.
func XCTAssertStoreError(
    _ error: Error,
    _ expected: ContextStoreError,
    file: StaticString = #filePath,
    line: UInt = #line
) {
    guard let actual = error as? ContextStoreError else {
        XCTFail("expected ContextStoreError.\(expected), got \(error)", file: file, line: line)
        return
    }
    XCTAssertEqual(String(describing: actual), String(describing: expected), file: file, line: line)
}
