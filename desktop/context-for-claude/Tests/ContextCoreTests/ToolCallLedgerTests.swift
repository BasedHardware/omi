import ContextCore
import Foundation
import XCTest

/// The MCP-side usage counter, and the promises it has to keep.
///
/// Two things are being defended. The first is **privacy**: this file is plaintext on disk and its
/// contents are destined for an analytics pipeline, so it must be structurally incapable of holding
/// anything the user said. The second is **arithmetic under concurrency**: several MCP servers write
/// it at once with no coordinating parent, and a count that loses increments is worse than no count
/// at all, because it looks like a real number.
final class ToolCallLedgerTests: XCTestCase {

    private var directory: URL!
    private var ledgerURL: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("ledger-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        ledgerURL = directory.appendingPathComponent("tool-calls.json")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    // MARK: - Privacy

    /// The invariant `ToolCallLedger`'s documentation states, pinned so a later field cannot be added
    /// without this failing. A tool name is our own vocabulary and a count is arithmetic; an argument
    /// or a per-call timestamp would be the user's question.
    func testTheLedgerCarriesNothingButToolNamesAndCounts() throws {
        ToolCallLedger.bump(tool: "recall", at: ledgerURL)

        let raw = try XCTUnwrap(try? Data(contentsOf: ledgerURL))
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])

        XCTAssertEqual(Set(object.keys), ["counts"], "the ledger grew a field — see the privacy rule")
        let counts = try XCTUnwrap(object["counts"] as? [String: Int])
        XCTAssertEqual(counts, ["recall": 1])
    }

    /// A tool name is the one string in the whole analytics payload that comes from a dispatch table
    /// rather than a closed Swift enum. If a caller ever passes something else — a name built from
    /// user input, an error string — the sanitiser is what keeps it from reaching PostHog.
    func testAToolNameIsStrippedToOurOwnVocabulary() {
        ToolCallLedger.bump(tool: "Recall Screen/../../etc/passwd", at: ledgerURL)
        let counts = ToolCallLedger.read(from: ledgerURL)?.counts ?? [:]

        XCTAssertEqual(counts, ["recallscreenetcpasswd": 1])
        XCTAssertFalse(counts.keys.contains { $0.contains("/") || $0.contains(".") })
    }

    func testAnEmptyToolNameIsNotCounted() {
        ToolCallLedger.bump(tool: "!!!", at: ledgerURL)
        XCTAssertNil(ToolCallLedger.read(from: ledgerURL))
    }

    // MARK: - Counting

    func testCallsAccumulateAcrossProcessesAndTools() {
        for _ in 0..<3 { ToolCallLedger.bump(tool: "recall", at: ledgerURL) }
        ToolCallLedger.bump(tool: "screen", at: ledgerURL)

        XCTAssertEqual(ToolCallLedger.read(from: ledgerURL)?.counts, ["recall": 3, "screen": 1])
        XCTAssertEqual(ToolCallLedger.read(from: ledgerURL)?.total, 4)
    }

    /// The whole reason the ledger is separate from `QueryStamp`: draining hands the counts to the
    /// caller *and* resets, so two rollups can never report the same call twice.
    func testDrainingReturnsEverythingAndResets() {
        ToolCallLedger.bump(tool: "recall", at: ledgerURL)
        ToolCallLedger.bump(tool: "recall", at: ledgerURL)

        XCTAssertEqual(ToolCallLedger.drain(from: ledgerURL).counts, ["recall": 2])
        XCTAssertTrue(ToolCallLedger.drain(from: ledgerURL).isEmpty, "a second drain must find nothing")
    }

    /// Claude keeps several MCP servers alive at once. Every increment has to survive.
    ///
    /// This is the test that would have caught a plain read-modify-write with no lock: without the
    /// `flock`, concurrent bumps interleave and the total comes out short.
    func testConcurrentWritersLoseNoCounts() {
        let writers = 8
        let bumpsEach = 25
        let group = DispatchGroup()

        for _ in 0..<writers {
            DispatchQueue.global().async(group: group) { [ledgerURL] in
                for _ in 0..<bumpsEach { ToolCallLedger.bump(tool: "recall", at: ledgerURL!) }
            }
        }
        XCTAssertEqual(group.wait(timeout: .now() + 60), .success)

        XCTAssertEqual(ToolCallLedger.read(from: ledgerURL)?.counts["recall"], writers * bumpsEach)
    }

    // MARK: - Damage

    func testADamagedLedgerReadsAsNothingRatherThanAsUsage() throws {
        try Data("not json".utf8).write(to: ledgerURL)
        XCTAssertNil(ToolCallLedger.read(from: ledgerURL))

        try Data(repeating: 0x41, count: ToolCallLedger.maximumFileSize + 1).write(to: ledgerURL)
        XCTAssertNil(ToolCallLedger.read(from: ledgerURL))
    }

    /// A ledger is an accumulation, so one bad key must not throw away the real counts beside it.
    func testAnImplausibleEntryIsDroppedWithoutLosingTheRest() throws {
        let raw = ["counts": ["recall": 4, "": 9, "screen": -2, "Bad Name": 3]]
        try JSONSerialization.data(withJSONObject: raw).write(to: ledgerURL)

        XCTAssertEqual(ToolCallLedger.read(from: ledgerURL)?.counts, ["recall": 4])
    }

    /// An unknown tool cannot displace one already being counted: dropping a new name loses one
    /// series, while evicting an old one silently corrupts every number accumulated under it.
    func testTheDistinctToolCapDropsNewNamesNotEstablishedOnes() {
        for index in 0..<ToolCallLedger.maximumDistinctTools {
            ToolCallLedger.bump(tool: "tool_\(index)", at: ledgerURL)
        }
        ToolCallLedger.bump(tool: "one_too_many", at: ledgerURL)
        // An established name still counts up after the cap is reached.
        ToolCallLedger.bump(tool: "tool_0", at: ledgerURL)

        let counts = ToolCallLedger.read(from: ledgerURL)?.counts ?? [:]
        XCTAssertEqual(counts.count, ToolCallLedger.maximumDistinctTools)
        XCTAssertNil(counts["one_too_many"])
        XCTAssertEqual(counts["tool_0"], 2)
    }

    /// A tool call that succeeded must never be reported to Claude as failed because a counter could
    /// not be written. `bump` returns `Void` and swallows; this proves it swallows a real failure.
    func testAnUnwritableLedgerIsSilent() throws {
        // A *file* where the ledger's parent directory should be. Chmod would not do: `bump` calls
        // `ContextPaths.ensureSupportDirectory`, which chmods the directory back to 0o700 and would
        // quietly repair the very condition the test is trying to create.
        let blocked = directory.appendingPathComponent("not-a-directory")
        try Data("occupied".utf8).write(to: blocked)
        let unreachable = blocked.appendingPathComponent("tool-calls.json")

        // No throw, no crash — the only observable outcome is that nothing was recorded.
        ToolCallLedger.bump(tool: "recall", at: unreachable)
        XCTAssertNil(ToolCallLedger.read(from: unreachable))
        XCTAssertTrue(ToolCallLedger.drain(from: unreachable).isEmpty)
    }
}
