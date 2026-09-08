import ContextCore
import Foundation
import XCTest

/// The proof-of-query trace the first-run tutorial's payoff beat rests on.
///
/// Two things are being defended here. The first is honesty: "found it" may only appear when Claude
/// really called a tool, so a missing, damaged or stale stamp has to read as *no call* rather than as
/// a call. The second is that this is a genuinely multi-process file — Claude keeps several MCP
/// servers alive at once and the app reads while they write — so the corruption and lost-update cases
/// are the interesting ones, not an afterthought.
final class QueryStampTests: XCTestCase {

    /// 2025-10-09T08:53:20Z. A fixed epoch, so nothing here moves with the wall clock.
    private static let base: Double = 1_760_000_000

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("query-stamp-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: root)
    }

    /// Deliberately rebuilt from the directory path rather than shared, so a writer and a reader in
    /// this file agree on the file the way two *processes* do: by path, not by object identity.
    private func stampURL() -> URL {
        URL(fileURLWithPath: root.path, isDirectory: true).appendingPathComponent("last-query.json")
    }

    // MARK: - Across processes

    func testAStampWrittenByOneProcessIsObservedByAnother() throws {
        // The writer is the MCP server; the reader is the app. They share nothing but the path.
        let writerView = stampURL()
        let readerView = stampURL()

        try QueryStamp(tool: "recall", at: Self.base).record(to: writerView)

        let observed = try XCTUnwrap(QueryStamp.read(from: readerView))
        XCTAssertEqual(observed, QueryStamp(tool: "recall", at: Self.base))
        XCTAssertEqual(observed.tool, "recall", "the app names the tool in the payoff beat")
    }

    func testRecordingCreatesTheDataDirectoryWhenTheAppHasNeverRun() throws {
        // Claude can spawn the MCP server before the app has ever launched; the first call still has
        // to leave a trace.
        let fresh = root.appendingPathComponent("never-launched", isDirectory: true)
            .appendingPathComponent("last-query.json")

        try QueryStamp(tool: "status", at: Self.base).record(to: fresh)

        XCTAssertEqual(QueryStamp.read(from: fresh)?.tool, "status")
    }

    // MARK: - Privacy

    func testTheStampCarriesNothingButAToolNameAndATime() throws {
        // The guard against a future "improvement" that records the query. If a field is added to
        // `QueryStamp`, this fails — and the failure is the conversation.
        let url = stampURL()
        try QueryStamp(tool: "recall", at: Self.base).record(to: url)

        let raw = try XCTUnwrap(try? Data(contentsOf: url))
        let decoded = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])

        XCTAssertEqual(Set(decoded.keys), ["tool", "at"],
                       "the stamp must hold only when a call happened and which tool — never the query")
    }

    // MARK: - Concurrency

    func testConcurrentWritersNeitherCorruptTheFileNorLoseTheNewestStamp() throws {
        let url = stampURL()
        let writers = 64
        // Shuffled so the newest stamp is not simply the last one scheduled.
        let times = (0..<writers).map { Self.base + Double($0) }.shuffled()
        let newest = Self.base + Double(writers - 1)

        // A reader hammering the file throughout: every read must see a whole stamp or nothing. A
        // half-written file would show up here as a nil in the middle of the run.
        let readerFailures = Atomic(0)
        let keepReading = Atomic(1)
        let reader = Thread {
            while keepReading.value == 1 {
                if let data = try? Data(contentsOf: url) {
                    if (try? JSONDecoder().decode(QueryStamp.self, from: data)) == nil {
                        readerFailures.add(1)
                    }
                }
            }
        }
        reader.start()

        let writeFailures = Atomic(0)
        DispatchQueue.concurrentPerform(iterations: writers) { index in
            do {
                try QueryStamp(tool: "recall", at: times[index]).record(to: url)
            } catch {
                writeFailures.add(1)
            }
        }
        keepReading.set(0)
        while !reader.isFinished { usleep(1000) }

        XCTAssertEqual(writeFailures.value, 0, "a concurrent write failed")
        XCTAssertEqual(readerFailures.value, 0, "a reader observed a partially written stamp file")
        let final = try XCTUnwrap(QueryStamp.read(from: url), "the file did not survive \(writers) writers")
        XCTAssertEqual(final.at, newest, "the newest call must win, whatever order the writers landed in")
    }

    func testAStampNeverMovesBackwards() throws {
        // A slow MCP server finishing after a faster one must not bury the newer call.
        let url = stampURL()
        try QueryStamp(tool: "recent", at: Self.base + 100).record(to: url)

        try QueryStamp(tool: "recall", at: Self.base).record(to: url)

        XCTAssertEqual(QueryStamp.read(from: url), QueryStamp(tool: "recent", at: Self.base + 100))
    }

    func testAStampFromTheFutureIsNotAllowedToWedgeTheFile() throws {
        // A clock that jumped backwards leaves a stamp nothing can beat. Honouring it forever would
        // strand the tutorial waiting for a call Claude had already made, so a far-future stamp is
        // treated as the wrong clock it is and replaced.
        let url = stampURL()
        try QueryStamp(tool: "recall", at: ContextTime.now + 86_400).record(to: url)

        let real = QueryStamp(tool: "status", at: ContextTime.now)
        try real.record(to: url)

        XCTAssertEqual(QueryStamp.read(from: url), real)
        XCTAssertNotNil(QueryStamp.newCall(since: ContextTime.now - 1, from: url))
    }

    // MARK: - Damaged files

    func testADamagedStampFileReadsAsNoCallRatherThanAsACall() throws {
        let url = stampURL()
        let damaged: [(String, String)] = [
            ("empty", ""),
            ("truncated mid-object", #"{"tool":"recall","at":176000"#),
            ("truncated mid-key", #"{"to"#),
            ("not JSON at all", "recall 1760000000\n"),
            ("a JSON array", #"["recall",1760000000]"#),
            ("missing the timestamp", #"{"tool":"recall"}"#),
            ("missing the tool", #"{"at":1760000000}"#),
            ("a zero-filled stamp", #"{"tool":"","at":0}"#),
            ("an epoch of zero", #"{"tool":"recall","at":0}"#),
            ("a non-finite timestamp", #"{"tool":"recall","at":1e999}"#),
            ("interleaved writes", #"{"tool":"recall","at":1}{"tool":"recent","at":2}"#),
        ]

        for (label, contents) in damaged {
            try contents.data(using: .utf8)!.write(to: url)
            XCTAssertNil(QueryStamp.read(from: url), "\(label) was accepted as a real stamp")
            XCTAssertNil(QueryStamp.newCall(since: 0, from: url), "\(label) was reported as a new call")
        }

        // An absurdly large file is not a stamp either, however well-formed its first bytes are.
        let padded = #"{"tool":"recall","at":1760000000,"pad":"# + "\"" + String(repeating: "x", count: 8192) + "\"}"
        try padded.data(using: .utf8)!.write(to: url)
        XCTAssertNil(QueryStamp.read(from: url), "an over-sized file was accepted as a stamp")
    }

    func testAMissingFileIsNoCall() {
        XCTAssertNil(QueryStamp.read(from: stampURL()))
        XCTAssertNil(QueryStamp.newCall(since: 0, from: stampURL()))
    }

    // MARK: - "Since" boundary

    func testOnlyACallStrictlyAfterTheWatchStartedCounts() throws {
        let url = stampURL()
        try QueryStamp(tool: "recall", at: Self.base).record(to: url)

        // Older than the moment the tutorial started watching: left by an earlier Claude session,
        // proves nothing about the question the user was just told to ask.
        XCTAssertNil(QueryStamp.newCall(since: Self.base + 1, from: url))
        // Exactly at the moment: not *after* it.
        XCTAssertNil(QueryStamp.newCall(since: Self.base, from: url))
        // Newer: this is the payoff.
        XCTAssertEqual(QueryStamp.newCall(since: Self.base - 1, from: url)?.tool, "recall")
        XCTAssertEqual(QueryStamp.newCall(since: 0, from: url)?.at, Self.base)
    }

    func testAStaleStampDoesNotSatisfyANewWatch() throws {
        // The realistic sequence: a previous session left a stamp, the tutorial starts watching now,
        // and nothing new arrives.
        let url = stampURL()
        try QueryStamp(tool: "status", at: Self.base).record(to: url)
        let watchStarted = Self.base + 3600

        XCTAssertNil(QueryStamp.newCall(since: watchStarted, from: url))

        try QueryStamp(tool: "recall", at: watchStarted + 5).record(to: url)

        XCTAssertEqual(QueryStamp.newCall(since: watchStarted, from: url)?.tool, "recall")
    }

    // MARK: - Waiting

    func testWaitingReturnsTheCallThatIsAlreadyThere() async throws {
        let url = stampURL()
        try QueryStamp(tool: "recall", at: Self.base).record(to: url)

        let stamp = await QueryStamp.waitForCall(since: Self.base - 1, timeout: 0, from: url)

        XCTAssertEqual(stamp?.tool, "recall")
    }

    func testWaitingGivesUpRatherThanClaimingACall() async {
        // Zero timeout, so this checks once and returns — no sleep, nothing to flake.
        let stamp = await QueryStamp.waitForCall(since: Self.base, timeout: 0, from: stampURL())

        XCTAssertNil(stamp)
    }
}

/// A counter usable from several threads. `XCTest` has no equivalent and the alternative is a
/// data race in the test that is supposed to prove there is no data race in the code.
private final class Atomic: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: Int

    init(_ value: Int) { storage = value }

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func add(_ delta: Int) {
        lock.lock()
        storage += delta
        lock.unlock()
    }

    func set(_ newValue: Int) {
        lock.lock()
        storage = newValue
        lock.unlock()
    }
}
