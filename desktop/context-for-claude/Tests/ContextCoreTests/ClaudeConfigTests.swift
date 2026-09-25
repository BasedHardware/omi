import ContextCore
import Foundation
import XCTest

/// Registration into the user's Claude config.
///
/// `~/.claude.json` is the user's account, their project history, and their other MCP servers.
/// Context for Claude adds one key to one dictionary inside it, so the tests that matter are the ones proving
/// everything else came back byte-for-byte. **Nothing here touches a real config file** — every
/// path is a temp directory, and the pure functions take dictionaries.
final class ClaudeConfigTests: XCTestCase {
    private let binary = "/Applications/Context for Claude.app/Contents/MacOS/context-for-claude-mcp"
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-config-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let root { try? FileManager.default.removeItem(at: root) }
        root = nil
    }

    // MARK: - Locations

    func testConfigLocationsAreTheOnesClaudeReads() {
        XCTAssertEqual(ClaudeConfig.serverName, "context-for-claude")
        XCTAssertEqual(ClaudeConfig.claudeCodeConfigURL.lastPathComponent, ".claude.json")
        XCTAssertTrue(
            ClaudeConfig.claudeDesktopConfigURL.path
                .hasSuffix("Library/Application Support/Claude/claude_desktop_config.json"),
            ClaudeConfig.claudeDesktopConfigURL.path)
    }

    // MARK: - Merging

    func testMergePreservesASiblingServerAndEveryUnrelatedKey() throws {
        let existing = populatedDocument()

        let merged = ClaudeConfig.merged(into: existing, mcpBinaryPath: binary)

        // The sibling server survives exactly, headers and all — this is the user's live connection
        // to their own memory, and a merge that flattens it is a silent outage.
        let servers = try object(merged["mcpServers"])
        let originalServers = try object(existing["mcpServers"])
        XCTAssertEqual(
            NSDictionary(dictionary: try object(servers["omi-memory"])),
            NSDictionary(dictionary: try object(originalServers["omi-memory"])))

        // Keys we have never heard of are nearly all of the document.
        XCTAssertEqual(merged["numStartups"] as? Int, 42)
        XCTAssertEqual(
            NSDictionary(dictionary: try object(merged["oauthAccount"])),
            NSDictionary(dictionary: try object(existing["oauthAccount"])))
        XCTAssertEqual(
            NSDictionary(dictionary: try object(merged["projects"])),
            NSDictionary(dictionary: try object(existing["projects"])))
        XCTAssertEqual(merged["hasCompletedOnboarding"] as? Bool, true)
        XCTAssertEqual(Set(merged.keys), Set(existing.keys))

        // And the input is not mutated on the way through.
        XCTAssertEqual(try object(existing["mcpServers"]).keys.count, 1)
    }

    func testMergeWritesExactlyTheStdioEntry() throws {
        let merged = ClaudeConfig.merged(into: [:], mcpBinaryPath: binary)

        let entry = try object(try object(merged["mcpServers"])["context-for-claude"])
        XCTAssertEqual(Set(entry.keys), ["type", "command", "args", "env"])
        XCTAssertEqual(entry["type"] as? String, "stdio")
        XCTAssertEqual(entry["command"] as? String, binary)
        XCTAssertEqual((entry["args"] as? [Any])?.count, 0)
        XCTAssertEqual((entry["env"] as? [String: Any])?.count, 0)
    }

    func testMergeRepointsAStaleEntry() throws {
        let stale = ClaudeConfig.merged(into: [:], mcpBinaryPath: "/old/path/context-for-claude-mcp")

        let merged = ClaudeConfig.merged(into: stale, mcpBinaryPath: binary)

        let entry = try object(try object(merged["mcpServers"])["context-for-claude"])
        XCTAssertEqual(entry["command"] as? String, binary)
    }

    func testMergeLeavesADocumentAloneWhenMCPServersIsNotAnObject() throws {
        // Not a shape we wrote and not one we understand. Failing to register is recoverable;
        // deleting whatever the user put there is not.
        for hostile: Any in ["oops", [1, 2, 3] as [Any], 7, NSNull()] {
            let existing: [String: Any] = ["mcpServers": hostile, "numStartups": 42]

            let merged = ClaudeConfig.merged(into: existing, mcpBinaryPath: binary)

            XCTAssertNil(merged["mcpServers"] as? [String: Any], "\(hostile) was replaced")
            XCTAssertEqual(
                NSDictionary(dictionary: merged),
                NSDictionary(dictionary: existing),
                "the document changed for \(hostile)")
            XCTAssertFalse(ClaudeConfig.isRegistered(in: merged, mcpBinaryPath: binary))
        }
    }

    // MARK: - Registration state

    func testIsRegisteredIsAnExactPathMatch() throws {
        let registered = ClaudeConfig.merged(into: populatedDocument(), mcpBinaryPath: binary)

        XCTAssertTrue(ClaudeConfig.isRegistered(in: registered, mcpBinaryPath: binary))
        // A leftover entry from an older install has our name and a command that no longer resolves;
        // reporting it as registered would leave Claude with a server that never spawns.
        XCTAssertFalse(ClaudeConfig.isRegistered(in: registered, mcpBinaryPath: "/old/path/context-for-claude-mcp"))
        XCTAssertFalse(ClaudeConfig.isRegistered(in: [:], mcpBinaryPath: binary))
        XCTAssertFalse(ClaudeConfig.isRegistered(in: populatedDocument(), mcpBinaryPath: binary))
        XCTAssertFalse(ClaudeConfig.isRegistered(
            in: ["mcpServers": ["context-for-claude": ["type": "stdio"]]], mcpBinaryPath: binary))
        XCTAssertFalse(ClaudeConfig.isRegistered(in: ["mcpServers": "oops"], mcpBinaryPath: binary))
    }

    // MARK: - Removal

    func testRemovedTakesOutOnlyOurKey() throws {
        let registered = ClaudeConfig.merged(into: populatedDocument(), mcpBinaryPath: binary)

        let removed = ClaudeConfig.removed(from: registered)

        let servers = try object(removed["mcpServers"])
        XCTAssertEqual(Set(servers.keys), ["omi-memory"])
        XCTAssertFalse(ClaudeConfig.isRegistered(in: removed, mcpBinaryPath: binary))
        XCTAssertEqual(removed["numStartups"] as? Int, 42)
        XCTAssertEqual(
            NSDictionary(dictionary: try object(removed["projects"])),
            NSDictionary(dictionary: try object(populatedDocument()["projects"])))
    }

    func testRemovedFromADocumentWithoutServersAddsNothing() {
        let removed = ClaudeConfig.removed(from: ["numStartups": 42])

        XCTAssertNil(removed["mcpServers"])
        XCTAssertEqual(removed["numStartups"] as? Int, 42)
    }

    // MARK: - File I/O

    func testWriteThenReadRoundTripsTheWholeDocument() throws {
        let url = root.appendingPathComponent("claude.json")
        let document = ClaudeConfig.merged(into: populatedDocument(), mcpBinaryPath: binary)

        try ClaudeConfig.writeDocument(document, to: url)
        let read = try ClaudeConfig.readDocument(at: url)

        XCTAssertEqual(NSDictionary(dictionary: read), NSDictionary(dictionary: document))
        XCTAssertTrue(ClaudeConfig.isRegistered(in: read, mcpBinaryPath: binary))

        // Rewriting an unchanged document must not churn the file: a diff the user sees should mean
        // a change we actually made.
        let first = try Data(contentsOf: url)
        try ClaudeConfig.writeDocument(read, to: url)
        XCTAssertEqual(try Data(contentsOf: url), first)
    }

    func testWriteCreatesAMissingDirectory() throws {
        // Claude Desktop's config directory does not exist until Claude Desktop has run once.
        let url = root
            .appendingPathComponent("Library/Application Support/Claude", isDirectory: true)
            .appendingPathComponent("claude_desktop_config.json")

        try ClaudeConfig.writeDocument(ClaudeConfig.merged(into: [:], mcpBinaryPath: binary), to: url)

        XCTAssertTrue(ClaudeConfig.isRegistered(
            in: try ClaudeConfig.readDocument(at: url), mcpBinaryPath: binary))
    }

    func testReadTreatsAMissingFileAsEmptyAndACorruptOneAsAnError() throws {
        XCTAssertEqual(
            try ClaudeConfig.readDocument(at: root.appendingPathComponent("absent.json")).count, 0)

        let corrupt = root.appendingPathComponent("corrupt.json")
        try Data("{ not json".utf8).write(to: corrupt)
        // Silently starting from scratch here would overwrite the user's whole config.
        XCTAssertThrowsError(try ClaudeConfig.readDocument(at: corrupt))
    }

    // MARK: - Helpers

    /// A miniature `~/.claude.json`: an account, project history, and the user's other MCP server.
    private func populatedDocument() -> [String: Any] {
        [
            "numStartups": 42,
            "hasCompletedOnboarding": true,
            "oauthAccount": [
                "accountUuid": "0000-1111",
                "emailAddress": "user@example.com",
            ] as [String: Any],
            "projects": [
                "/Users/example/omi": [
                    "allowedTools": ["Bash", "Read"],
                    "history": [["display": "fix the tap"]],
                ] as [String: Any],
            ] as [String: Any],
            "mcpServers": [
                "omi-memory": [
                    "type": "http",
                    "url": "https://api.omi.me/mcp",
                    "headers": ["Authorization": "Bearer redacted"] as [String: Any],
                ] as [String: Any],
            ] as [String: Any],
        ]
    }

    private func object(
        _ value: Any?,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> [String: Any] {
        try XCTUnwrap(value as? [String: Any], "expected a JSON object", file: file, line: line)
    }
}
