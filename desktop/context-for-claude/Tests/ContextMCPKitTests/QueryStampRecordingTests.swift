import ContextCore
import ContextMCPKit
import Foundation
import XCTest

/// The server half of the proof-of-query mechanism: serving a tool call leaves a trace the app can
/// see, and that trace never carries what the user asked.
///
/// Lives beside the other MCP protocol tests because the behaviour under test is the *dispatch* — the
/// stamp has to be written by whatever path a real `tools/call` frame takes, not by a helper a future
/// refactor could route around.
final class QueryStampRecordingTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("stamp-recording-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: root)
    }

    private var stampURL: URL { root.appendingPathComponent("last-query.json") }

    private func server() -> MCPServer {
        // No store: the tools answer in prose when nothing has been captured, which is exactly the
        // state the tutorial's "ask Claude a question" step runs in on a fresh install.
        MCPServer(store: nil, queryStampURL: stampURL)
    }

    private func callFrame(_ name: String, arguments: String = "{}") -> String {
        #"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"#
            + "\"\(name)\"" + #","arguments":"# + arguments + "}}"
    }

    // MARK: - The trace exists

    func testServingAToolCallLeavesAStampTheAppCanObserve() throws {
        let watchStarted = ContextTime.now
        XCTAssertNil(QueryStamp.newCall(since: watchStarted, from: stampURL), "nothing called yet")

        _ = server().handle(line: callFrame("status"))

        let stamp = try XCTUnwrap(QueryStamp.newCall(since: watchStarted, from: stampURL),
                                  "a served tool call left no proof the app could see")
        XCTAssertEqual(stamp.tool, "status")
    }

    func testAFailingToolCallStillProvesClaudeReachedUs() throws {
        // `recall` without its required `query` fails — but the connection is what the tutorial is
        // proving, and Claude retrying with better arguments is normal. A trace only on success would
        // make the payoff beat depend on the answer instead of on the connection.
        let watchStarted = ContextTime.now

        let response = try XCTUnwrap(server().handle(line: callFrame("recall")))

        XCTAssertTrue(response.contains("\"isError\":true"), "expected the call to fail: \(response)")
        XCTAssertEqual(QueryStamp.newCall(since: watchStarted, from: stampURL)?.tool, "recall")
    }

    func testAToolThisServerDoesNotAdvertiseIsNotProof() {
        let watchStarted = ContextTime.now

        _ = server().handle(line: callFrame("no_such_tool"))
        // A nameless call never reaches a tool at all.
        _ = server().handle(line: #"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"arguments":{}}}"#)
        // Neither does anything that is not a tool call.
        _ = server().handle(line: #"{"jsonrpc":"2.0","id":3,"method":"tools/list"}"#)
        _ = server().handle(line: #"{"jsonrpc":"2.0","id":4,"method":"initialize"}"#)

        XCTAssertNil(QueryStamp.newCall(since: watchStarted, from: stampURL),
                     "only a tool this server advertises is proof that Claude reached us")
    }

    // MARK: - Privacy

    func testTheStampNeverContainsTheQueryText() throws {
        // This is the test that stops a future change from quietly putting the user's questions on
        // disk. The string below is distinctive enough that it cannot arrive by coincidence.
        let secret = "Zarquon-Severance-Package-Negotiation-8813"

        _ = server().handle(line: callFrame("recall", arguments: #"{"query":"# + "\"\(secret)\"" + "}"))
        _ = server().handle(line: callFrame("screen", arguments: #"{"query":"# + "\"\(secret)\"" + "}"))

        let raw = try XCTUnwrap(try? Data(contentsOf: stampURL), "the calls should still have been recorded")
        let text = try XCTUnwrap(String(data: raw, encoding: .utf8))

        XCTAssertFalse(text.localizedCaseInsensitiveContains(secret),
                       "the query text reached the stamp file: \(text)")
        XCTAssertFalse(text.localizedCaseInsensitiveContains("query"),
                       "an argument name reached the stamp file: \(text)")
        let decoded = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
        XCTAssertEqual(Set(decoded.keys), ["tool", "at"], "the stamp grew a field: \(text)")

        // And the whole directory, in case a stamp write ever spills a second file next to it.
        for file in try FileManager.default.contentsOfDirectory(atPath: root.path) {
            let contents = (try? String(contentsOf: root.appendingPathComponent(file), encoding: .utf8)) ?? ""
            XCTAssertFalse(contents.localizedCaseInsensitiveContains(secret),
                           "the query text reached \(file)")
        }
    }

    // MARK: - Concurrent servers

    func testTwoServersSharingADataDirectoryDoNotCorruptEachOthersStamps() throws {
        // Claude routinely keeps more than one MCP server process alive. Here they are two objects
        // over one path, which is the same contention.
        let a = server()
        let b = server()

        DispatchQueue.concurrentPerform(iterations: 24) { index in
            let server = index.isMultiple(of: 2) ? a : b
            _ = server.handle(line: self.callFrame("status"))
        }

        XCTAssertEqual(QueryStamp.read(from: stampURL)?.tool, "status",
                       "concurrent servers left an unreadable stamp file")
    }
}
