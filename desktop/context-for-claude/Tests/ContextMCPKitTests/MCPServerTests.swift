import ContextCore
import ContextMCPKit
import Foundation
import XCTest

/// The wire protocol Claude Code and Claude Desktop speak to this binary.
///
/// The framing rules are the whole contract: one JSON object per line, a notification is never
/// answered, and a failing tool comes back as a *result* the model can read rather than an error the
/// client swallows. Getting any of these wrong looks like "Omi is not connected" and nothing else.
final class MCPServerTests: XCTestCase {

    // MARK: - Handshake

    func testInitializeAnnouncesTheProtocolAndServerIdentity() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 7, method: "initialize")))
        let frame = try parse(response)

        XCTAssertEqual(frame["jsonrpc"]?.stringValue, "2.0")
        // The id must come back as the client sent it — a `7.0` here desynchronizes the client.
        XCTAssertEqual(frame["id"]?.intValue, 7)
        let result = try XCTUnwrap(frame["result"])
        XCTAssertEqual(result["protocolVersion"]?.stringValue, "2024-11-05")
        XCTAssertEqual(result["serverInfo"]?["name"]?.stringValue, "context-for-claude")
        XCTAssertNotNil(result["serverInfo"]?["version"]?.stringValue)
        XCTAssertNotNil(result["capabilities"]?["tools"], "a server with no tools capability is ignored")
    }

    func testNotificationsAreNeverAnswered() {
        let server = MCPServer(store: nil)

        // Answering a notification desynchronizes the client for the rest of the session.
        XCTAssertNil(server.handle(line: #"{"jsonrpc":"2.0","method":"notifications/initialized"}"#))
        XCTAssertNil(server.handle(line: #"{"jsonrpc":"2.0","method":"notifications/cancelled","params":{}}"#))
        XCTAssertNil(server.handle(line: "   "), "a blank line is not a request")
    }

    func testPingIsAnswered() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 1, method: "ping")))

        XCTAssertNotNil(try parse(response)["result"])
    }

    // MARK: - Tools

    func testToolsListAdvertisesExactlyTheSevenTools() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 2, method: "tools/list")))
        let tools = try XCTUnwrap(try parse(response)["result"]?["tools"]?.arrayValue)

        XCTAssertEqual(tools.count, 7)
        XCTAssertEqual(
            Set(tools.compactMap { $0["name"]?.stringValue }),
            ["recall", "recent", "conversations", "transcript", "screen", "activity", "status"])
        for tool in tools {
            XCTAssertNotNil(tool["description"]?.stringValue)
            XCTAssertEqual(tool["inputSchema"]?["type"]?.stringValue, "object")
        }
        XCTAssertEqual(tools.count, Tools.all.count)
    }

    func testAFailingToolIsAResultWithIsErrorNotAJSONRPCError() throws {
        // MCP models a tool failure as a result so the model can read the reason and recover; a
        // JSON-RPC error is swallowed by the client and the model never learns why.
        let server = MCPServer(store: try makeStore())

        let response = try XCTUnwrap(server.handle(line: """
            {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"no_such_tool","arguments":{}}}
            """))
        let frame = try parse(response)

        XCTAssertNil(frame["error"], "a tool failure must not surface as a protocol error")
        let result = try XCTUnwrap(frame["result"])
        XCTAssertEqual(result["isError"]?.boolValue, true)
        let text = try XCTUnwrap(result["content"]?[0]?["text"]?.stringValue)
        XCTAssertFalse(text.isEmpty, "the model needs a reason it can act on")
    }

    func testASucceedingToolCallCarriesTextContent() throws {
        let server = MCPServer(store: try makeStore())

        let response = try XCTUnwrap(server.handle(line: """
            {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"status","arguments":{}}}
            """))
        let result = try XCTUnwrap(try parse(response)["result"])

        XCTAssertEqual(result["isError"]?.boolValue, false)
        XCTAssertEqual(result["content"]?[0]?["type"]?.stringValue, "text")
        XCTAssertFalse(try XCTUnwrap(result["content"]?[0]?["text"]?.stringValue).isEmpty)
    }

    // MARK: - Errors

    func testUnknownMethodIsMethodNotFound() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 5, method: "resources/list")))
        let frame = try parse(response)

        XCTAssertNil(frame["result"])
        XCTAssertEqual(frame["error"]?["code"]?.intValue, -32601)
        XCTAssertEqual(frame["id"]?.intValue, 5)
    }

    func testMalformedLineIsAParseError() throws {
        let server = MCPServer(store: nil)

        for garbage in ["{not json", "]]]", "\"a string\", trailing"] {
            let response = try XCTUnwrap(server.handle(line: garbage), garbage)
            XCTAssertEqual(try parse(response)["error"]?["code"]?.intValue, -32700, garbage)
        }
    }

    // MARK: - Framing

    func testEveryResponseIsExactlyOneLine() throws {
        // The tools answer in Markdown, which is full of newlines. If one of them reaches the wire
        // unescaped the client reads half a frame and drops the connection.
        let server = MCPServer(store: try seededStore())
        let lines = [
            request(id: 1, method: "initialize"),
            request(id: 2, method: "tools/list"),
            request(id: 3, method: "nope"),
            "{not json",
            #"{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"status","arguments":{}}}"#,
            #"{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"recent","arguments":{"minutes":60}}}"#,
            #"{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"no_such_tool"}}"#,
        ]

        for line in lines {
            let response = try XCTUnwrap(server.handle(line: line), line)
            XCTAssertFalse(response.contains("\n"), "embedded newline in the response to \(line)")
            XCTAssertFalse(response.contains("\r"), "embedded carriage return in the response to \(line)")
            XCTAssertNotNil(RPC.json(line: response), "response to \(line) is not JSON: \(response)")
        }
    }

    // MARK: - Helpers

    private func request(id: Int, method: String) -> String {
        #"{"jsonrpc":"2.0","id":\#(id),"method":"\#(method)"}"#
    }

    private func parse(_ line: String, file: StaticString = #filePath, line sourceLine: UInt = #line) throws -> JSONValue {
        try XCTUnwrap(RPC.json(line: line), "not JSON: \(line)", file: file, line: sourceLine)
    }

    /// An empty store in a fresh temp directory, removed when the test finishes.
    private func makeStore() throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("context-for-claude-mcp-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        return try ContextStore(url: root.appendingPathComponent("context.db"))
    }

    /// A store with one line and one frame in it, so a tool has something to render.
    private func seededStore() throws -> ContextStore {
        let store = try makeStore()
        let now = ContextTime.now
        let sessionId = try store.openSession(at: now - 600, appHint: "zoom.us")
        _ = try store.insertSegment(
            Segment(
                sessionId: sessionId,
                startedAt: now - 300,
                endedAt: now - 295,
                source: .mic,
                text: "we decided to ship the pricing change on Friday"))
        _ = try store.insertFrame(
            Frame(
                capturedAt: now - 120,
                appName: "Google Chrome",
                windowTitle: "Pricing — Notion",
                ocrText: "pricing change rollout notes"))
        return store
    }
}
