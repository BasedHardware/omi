import ContextCore
import ContextMCPKit
import CoreGraphics
import Foundation
import ImageIO
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

    /// The revision a session runs under is the client's to ask for and ours to confirm, and for a
    /// long time we ignored the ask and answered `2024-11-05` to everyone. Both shipping Claudes
    /// tolerate that — `2024-11-05` is on their supported list — but it pinned every session to the
    /// oldest revision we know, which is the one with no `icons` field in it. Asserted for every
    /// version we claim rather than for the newest alone, so dropping one from the list is a failure
    /// here and not a silent downgrade in the field.
    func testInitializeAgreesToTheRevisionTheClientAskedFor() throws {
        let server = MCPServer(store: nil)

        for version in MCPServer.supportedProtocolVersions {
            let response = try XCTUnwrap(server.handle(line: initialize(id: 1, protocolVersion: version)))

            XCTAssertEqual(try parse(response)["result"]?["protocolVersion"]?.stringValue, version)
        }
    }

    /// A revision we do not know is answered with our floor, not with our newest: a client asking
    /// for something unfamiliar is either older than everything here — in which case the newest is
    /// further from it — or newer, in which case the floor is a version it certainly still reads.
    /// This is also the value every client got before negotiation existed, which is what makes the
    /// change unable to break one that works today.
    func testAnUnknownRevisionFallsBackToTheOneWeAlwaysAnswered() throws {
        let server = MCPServer(store: nil)

        for version in ["2099-01-01", "2024-10-07", "", "not-a-date"] {
            let response = try XCTUnwrap(server.handle(line: initialize(id: 2, protocolVersion: version)), version)

            XCTAssertEqual(try parse(response)["result"]?["protocolVersion"]?.stringValue,
                           MCPServer.protocolVersion, version)
        }
        // A client that sends no version at all still gets a session rather than an error: an
        // `initialize` we cannot read the ask from is still an `initialize`.
        let bare = try XCTUnwrap(server.handle(line: request(id: 3, method: "initialize")))
        XCTAssertEqual(try parse(bare)["result"]?["protocolVersion"]?.stringValue, MCPServer.protocolVersion)
    }

    /// The instructions ride on `initialize` and nowhere else, so a client that never reads them is
    /// a client the tool descriptions have to carry alone. Asserted as *present and non-trivial* on
    /// the wire rather than word for word: pinning the prose would make every future edit to it a
    /// test failure, and the thing worth protecting is that it is sent at all.
    func testInitializeCarriesTheServerInstructions() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 8, method: "initialize")))
        let instructions = try XCTUnwrap(try parse(response)["result"]?["instructions"]?.stringValue)

        XCTAssertGreaterThan(instructions.count, 200, "an empty or stub instruction block steers nothing")
        XCTAssertEqual(instructions, MCPServer.instructions)
    }

    /// **The regression.** Asked the tutorial's own suggested question, Claude replied "I don't have
    /// access to what you were reading before this conversation started. I can only see messages
    /// within our current chat" — and offered pasting the text, the browser history, and
    /// `conversation_search` as the alternatives. The root cause was that no server was running, but
    /// the instructions were also silent on the one thing worth forbidding outright, so a model with
    /// the tools in hand had nothing telling it that answer is wrong.
    ///
    /// A keyword check, and named as such: it proves the guidance is still addressed to this failure,
    /// not that any model obeys it. Nothing here can make a model call a tool.
    func testTheInstructionsForbidClaimingNoAccessToTheUsersOwnHistory() {
        let instructions = MCPServer.instructions.lowercased()

        XCTAssertTrue(
            instructions.contains("never tell this user you have no access"),
            "the exact answer that broke the product has to be named as wrong")
        for alternative in ["paste", "browser history", "past conversations"] {
            XCTAssertTrue(
                instructions.contains(alternative),
                "the deflection Claude offered instead of a tool call is unaddressed: \(alternative)")
        }
        XCTAssertTrue(
            instructions.contains("a few minutes ago"),
            "the tutorial's own suggested question has to be one the instructions claim")
        XCTAssertTrue(
            instructions.contains("create_memory"),
            "durable memory requests must point Claude at the write tool")
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

    func testToolsListAdvertisesExactlyTheContractedTools() throws {
        let server = MCPServer(store: nil)

        let response = try XCTUnwrap(server.handle(line: request(id: 2, method: "tools/list")))
        let tools = try XCTUnwrap(try parse(response)["result"]?["tools"]?.arrayValue)

        XCTAssertEqual(tools.count, 12)
        XCTAssertEqual(
            Set(tools.compactMap { $0["name"]?.stringValue }),
            [
                "recall", "recent", "conversations", "transcript", "screen", "look", "activity",
                "status", "get_memories", "create_memory", "edit_memory", "delete_memory",
            ])
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

    // MARK: - Pictures on the wire

    /// `look` is the one tool that returns pixels, and the content array is where that either works
    /// or silently degrades into a text-only answer the model reads as "there was no screenshot".
    ///
    /// The order is asserted along with the blocks. MCP's `image` block carries no timestamp and no
    /// caption, so everything that stops a screenshot being misread — when it was taken, whether
    /// the screen has changed since — is in the text block, and only works if the model meets it
    /// first.
    func testALookResultCarriesTheProseFirstAndThenTheImage() throws {
        let store = try makeStore()
        let framePath = try heicFixture()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 2, appName: "Xcode", windowTitle: "MCPServer.swift",
                imagePath: framePath))

        let response = try XCTUnwrap(server(store).handle(line: toolCall(id: 21, name: "look")))
        let blocks = try XCTUnwrap(try parse(response)["result"]?["content"]?.arrayValue)

        XCTAssertEqual(blocks.count, 2, "expected prose plus one picture: \(response)")
        XCTAssertEqual(blocks.first?["type"]?.stringValue, "text")
        XCTAssertEqual(blocks.last?["type"]?.stringValue, "image")
        XCTAssertEqual(blocks.last?["mimeType"]?.stringValue, "image/jpeg")

        let encoded = try XCTUnwrap(blocks.last?["data"]?.stringValue)
        XCTAssertFalse(encoded.hasPrefix("data:"), "a data URI here is silently rejected by the client")
        XCTAssertNotNil(Data(base64Encoded: encoded), "the image block is not base64")
    }

    /// Every other tool must keep returning exactly one text block. An empty `image` block, or a
    /// second block carrying nothing, is the kind of change that passes every tool test and breaks
    /// rendering in the client.
    func testATextToolStillReturnsOneTextBlockAndNothingElse() throws {
        let response = try XCTUnwrap(server(try makeStore()).handle(line: toolCall(id: 22, name: "status")))
        let blocks = try XCTUnwrap(try parse(response)["result"]?["content"]?.arrayValue)

        XCTAssertEqual(blocks.count, 1)
        XCTAssertEqual(blocks.first?["type"]?.stringValue, "text")
    }

    private func server(_ store: ContextStore) -> MCPServer {
        MCPServer(
            store: store,
            // Kept out of the real support directory: the stamp exists to drive an animation in the
            // installed app, and a test run must not light it up.
            queryStampURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("stamp-\(UUID().uuidString).json"))
    }

    private func toolCall(id: Int, name: String) -> String {
        #"{"jsonrpc":"2.0","id":\#(id),"method":"tools/call","params":{"name":"\#(name)","arguments":{}}}"#
    }

    /// A frame image in the format capture actually writes.
    private func heicFixture() throws -> String {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("wire-frame-\(UUID().uuidString).heic")
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }

        let context = try XCTUnwrap(
            CGContext(
                data: nil, width: 48, height: 48, bitsPerComponent: 8, bytesPerRow: 0,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(red: 0.1, green: 0.6, blue: 0.3, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 48, height: 48))
        let image = try XCTUnwrap(context.makeImage())

        let data = NSMutableData()
        let destination = try XCTUnwrap(
            CGImageDestinationCreateWithData(data as CFMutableData, "public.heic" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        try (data as Data).write(to: url)
        return url.path
    }

    private func request(id: Int, method: String) -> String {
        #"{"jsonrpc":"2.0","id":\#(id),"method":"\#(method)"}"#
    }

    /// The real first frame: a client naming the revision it wants. `clientInfo` is included because
    /// every shipping client sends it and a server that only works without it works nowhere.
    private func initialize(id: Int, protocolVersion: String) -> String {
        #"""
        {"jsonrpc":"2.0","id":\#(id),"method":"initialize","params":{"protocolVersion":"\#(protocolVersion)",\#
        "capabilities":{},"clientInfo":{"name":"test-client","version":"0"}}}
        """#
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
