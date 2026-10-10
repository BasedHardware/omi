import XCTest

@testable import Omi_Computer

/// ~/.omi/mcp.json is the standard client format and may be hand-edited;
/// UI writes must round-trip cleanly and never clobber entries they don't own.
final class LocalMcpStoreTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-mcp-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  func testAddListRemoveCommandServer() throws {
    try LocalMcpStore.addCommandServer(name: "Playwright", commandLine: "npx @playwright/mcp@latest")

    let servers = LocalMcpStore.listServers()
    XCTAssertEqual(servers.map(\.name), ["playwright"])
    XCTAssertEqual(servers[0].summary, "npx @playwright/mcp@latest")
    XCTAssertTrue(servers[0].isCommand)

    let raw =
      try JSONSerialization.jsonObject(
        with: Data(contentsOf: LocalMcpStore.fileURL)) as? [String: Any]
    let entry = (raw?["mcpServers"] as? [String: Any])?["playwright"] as? [String: Any]
    XCTAssertEqual(entry?["command"] as? String, "npx")
    XCTAssertEqual(entry?["args"] as? [String], ["@playwright/mcp@latest"])

    LocalMcpStore.removeServer(name: "playwright")
    XCTAssertTrue(LocalMcpStore.listServers().isEmpty)
  }

  func testHandEditedEntriesSurviveWritesAndListWithUrls() throws {
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    let handWritten = """
      {"mcpServers": {"deepwiki": {"url": "https://mcp.deepwiki.com/mcp"}},
       "somethingElse": {"keep": true}}
      """
    try Data(handWritten.utf8).write(to: LocalMcpStore.fileURL)

    try LocalMcpStore.addCommandServer(name: "calc", commandLine: "node calc.js")

    let servers = LocalMcpStore.listServers()
    XCTAssertEqual(servers.map(\.name), ["calc", "deepwiki"])
    XCTAssertFalse(servers[1].isCommand)
    XCTAssertEqual(servers[1].summary, "https://mcp.deepwiki.com/mcp")

    let raw =
      try JSONSerialization.jsonObject(
        with: Data(contentsOf: LocalMcpStore.fileURL)) as? [String: Any]
    XCTAssertNotNil(raw?["somethingElse"], "unknown top-level keys must survive")
  }

  func testRejectsEmptyNameOrCommand() {
    XCTAssertThrowsError(try LocalMcpStore.addCommandServer(name: "!!!", commandLine: "npx x"))
    XCTAssertThrowsError(try LocalMcpStore.addCommandServer(name: "ok", commandLine: "   "))
  }

  // MARK: - Explicit credential replacement

  func testSavingKeyRemovesEveryAuthorizationHeaderAndPreservesServerConfiguration() throws {
    try LocalMcpStore.upsertServer(
      "example",
      entry: [
        "url": "https://example.test/sse", "transport": "sse",
        "token": "old-key", "auth": ["access_token": "old-oauth"],
        "headers": [
          "Authorization": "Bearer old-header", "authorization": "Bearer lower-header",
          "aUtHoRiZaTiOn": "Bearer mixed-header", "X-Workspace": "fixture-workspace",
          "X-Api-Key": "unrelated-header",
        ],
        "custom": ["retain": true],
      ])

    try LocalMcpStore.setAPIKey(name: "example", apiKey: "  replacement-key  ")

    let saved = try XCTUnwrap(LocalMcpStore.readAllServers()["example"] as? [String: Any])
    XCTAssertEqual(saved["token"] as? String, "replacement-key")
    XCTAssertNil(saved["auth"], "The previous OAuth credential must not remain an alternative key")
    XCTAssertEqual(
      saved["headers"] as? [String: String],
      [
        "X-Workspace": "fixture-workspace", "X-Api-Key": "unrelated-header",
      ])
    XCTAssertEqual(saved["url"] as? String, "https://example.test/sse")
    XCTAssertEqual(saved["transport"] as? String, "sse")
    XCTAssertEqual(saved["custom"] as? [String: Bool], ["retain": true])
    XCTAssertEqual(
      McpServerProbe.headers(from: saved),
      [
        "Authorization": "Bearer replacement-key", "X-Workspace": "fixture-workspace",
        "X-Api-Key": "unrelated-header",
      ])
  }

  func testClearingKeyRemovesStaleAuthorizationWithoutDiscardingExistingOAuth() throws {
    try LocalMcpStore.upsertServer(
      "example",
      entry: [
        "url": "https://example.test/mcp", "token": "old-key",
        "auth": ["access_token": "retained-oauth"],
        "headers": ["authorization": "Bearer stale-header"],
      ])

    try LocalMcpStore.setAPIKey(name: "example", apiKey: " \n ")

    let saved = try XCTUnwrap(LocalMcpStore.readAllServers()["example"] as? [String: Any])
    XCTAssertNil(saved["token"])
    XCTAssertNil(saved["headers"], "No empty or stale Authorization header should survive")
    XCTAssertEqual((saved["auth"] as? [String: String])?["access_token"], "retained-oauth")
    XCTAssertEqual(McpServerProbe.headers(from: saved), ["Authorization": "Bearer retained-oauth"])
  }

  func testSuccessfulOAuthReplacementRemovesHeaderAndTokenPrecedenceWithoutChangingServer() throws {
    let original: [String: Any] = [
      "url": "https://example.test/sse", "transport": "sse", "token": "stale-key",
      "auth": ["access_token": "stale-oauth"],
      "headers": ["authorization": "Bearer stale-header", "X-Workspace": "retained-workspace"],
      "custom": ["enabled": true],
    ]
    let authorized = LocalMcpStore.replacingOAuthCredentials(
      in: original, with: ["access_token": "authorized-oauth", "refresh_token": "authorized-refresh"])
    try LocalMcpStore.upsertServer("example", entry: authorized)

    let saved = try XCTUnwrap(LocalMcpStore.readAllServers()["example"] as? [String: Any])
    XCTAssertNil(saved["token"])
    XCTAssertEqual(saved["headers"] as? [String: String], ["X-Workspace": "retained-workspace"])
    XCTAssertEqual(
      saved["auth"] as? [String: String],
      [
        "access_token": "authorized-oauth", "refresh_token": "authorized-refresh",
      ])
    XCTAssertEqual(saved["custom"] as? [String: Bool], ["enabled": true])
    XCTAssertEqual(
      McpServerProbe.Target(entry: saved),
      .sse(
        url: try XCTUnwrap(URL(string: "https://example.test/sse")),
        headers: ["Authorization": "Bearer authorized-oauth", "X-Workspace": "retained-workspace"]))
    XCTAssertEqual(
      original["headers"] as? [String: String],
      [
        "authorization": "Bearer stale-header", "X-Workspace": "retained-workspace",
      ], "Preparing replacement must not mutate the original configuration")
  }

  // MARK: - File permissions

  private func posixPermissions(of url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return (attributes[.posixPermissions] as? NSNumber)?.intValue ?? -1
  }

  /// mcp.json carries OAuth access/refresh tokens and client secrets, and the
  /// directory also holds auth data — both must be user-only.
  func testFreshStoreWritesUserOnlyFileInPrivateDirectory() throws {
    try LocalMcpStore.addCommandServer(name: "calc", commandLine: "node calc.js")

    XCTAssertEqual(try posixPermissions(of: LocalMcpStore.fileURL), 0o600)
    XCTAssertEqual(try posixPermissions(of: tempRoot), 0o700)
  }

  /// A store written by an older build is world-readable; the next write must
  /// tighten both the file and the directory rather than preserve the leak.
  func testPreExistingWorldReadableFileAndDirectoryAreTightened() throws {
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    try Data("{\"mcpServers\": {}}".utf8).write(to: LocalMcpStore.fileURL)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o644], ofItemAtPath: LocalMcpStore.fileURL.path)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: tempRoot.path)

    try LocalMcpStore.addCommandServer(name: "calc", commandLine: "node calc.js")

    XCTAssertEqual(try posixPermissions(of: LocalMcpStore.fileURL), 0o600)
    XCTAssertEqual(try posixPermissions(of: tempRoot), 0o700)
  }

  // MARK: - Command-line splitting

  /// Quoted paths and arguments must survive as one argv entry; the spawn
  /// would otherwise run a mangled command (or a different one entirely).
  func testQuotedArgumentsSurviveSplitting() throws {
    try LocalMcpStore.addCommandServer(
      name: "Files Server",
      commandLine: #"python3 "/Users/me/My Tool/server.py" --mode 'read only'"#)

    let raw =
      try JSONSerialization.jsonObject(
        with: Data(contentsOf: LocalMcpStore.fileURL)) as? [String: Any]
    let entry = (raw?["mcpServers"] as? [String: Any])?["files-server"] as? [String: Any]
    XCTAssertEqual(entry?["command"] as? String, "python3")
    XCTAssertEqual(
      entry?["args"] as? [String],
      ["/Users/me/My Tool/server.py", "--mode", "read only"])

    // A quote toggles quoting from anywhere in a word.
    XCTAssertEqual(
      try LocalMcpStore.splitCommandLine(#"npx --filter="App Store" serve"#),
      ["npx", "--filter=App Store", "serve"])
    // Runs of spaces separate words outside quotes, never inside.
    XCTAssertEqual(
      try LocalMcpStore.splitCommandLine("node  'my tool.js'"),
      ["node", "my tool.js"])
    // An unterminated quote would mangle the command at spawn.
    XCTAssertThrowsError(try LocalMcpStore.splitCommandLine(#"python3 "/Users/me/tool.py"#))
  }

  /// The PKCE verifier proves the party redeeming the code is the one that began the flow, and
  /// `state` is the CSRF binding; both must come from the system CSPRNG, not `Int.random`.
  func testOAuthTokensAreUrlSafeUniqueAndFullLength() throws {
    // RFC 7636 §4.1: 32 octets base64url-encode to 43 characters, 16 to 22.
    XCTAssertEqual(try LocalMcpStore.randomURLSafeToken(byteCount: 32).count, 43)
    XCTAssertEqual(try LocalMcpStore.randomURLSafeToken(byteCount: 16).count, 22)

    let allowed = CharacterSet(
      charactersIn:
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    var seen = Set<String>()
    for _ in 0..<200 {
      let token = try LocalMcpStore.randomURLSafeToken(byteCount: 32)
      XCTAssertNil(
        token.rangeOfCharacter(from: allowed.inverted),
        "a verifier must survive a query string unescaped: \(token)")
      seen.insert(token)
    }
    XCTAssertEqual(seen.count, 200, "every draw must be distinct")
  }
}
