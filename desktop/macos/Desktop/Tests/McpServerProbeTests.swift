import XCTest

@testable import Omi_Computer

/// Every configured server used to read "Active in chat", including one whose command is not
/// installed or whose token expired. The user found that out mid-conversation, where the only
/// symptom is the assistant quietly missing the tools it should have.
final class McpServerProbeTests: XCTestCase {
  // MARK: - Target derivation

  func testTargetPrefersACommandAndCarriesItsEnvironment() throws {
    let target = McpServerProbe.Target(entry: [
      "command": " npx ", "args": ["-y", "some-mcp"], "env": ["API_KEY": "k", "n": 3],
    ])
    XCTAssertEqual(target, .stdio(command: "npx", args: ["-y", "some-mcp"], env: ["API_KEY": "k"]))
  }

  func testTargetFoldsStoredCredentialsIntoTheAuthorizationHeader() throws {
    let url = try XCTUnwrap(URL(string: "https://x.example/mcp"))
    XCTAssertEqual(
      McpServerProbe.Target(entry: ["url": url.absoluteString, "token": "abc"]),
      .http(url: url, headers: ["Authorization": "Bearer abc"]))

    XCTAssertEqual(
      McpServerProbe.Target(entry: [
        "url": url.absoluteString, "auth": ["access_token": "refreshed"],
      ]),
      .http(url: url, headers: ["Authorization": "Bearer refreshed"]))

    // An explicit header the user wrote by hand outranks a stored token.
    XCTAssertEqual(
      McpServerProbe.Target(entry: [
        "url": url.absoluteString, "token": "abc", "headers": ["Authorization": "Bearer mine"],
      ]),
      .http(url: url, headers: ["Authorization": "Bearer mine"]))
  }

  func testTargetWithNeitherCommandNorURLIsUnconfigured() throws {
    XCTAssertEqual(McpServerProbe.Target(entry: [:]), .unconfigured)
    XCTAssertEqual(McpServerProbe.Target(entry: ["command": "   "]), .unconfigured)
  }

  // MARK: - Response parsing

  /// Streamable HTTP servers answer as plain JSON or as an SSE stream; a probe that understood
  /// only one would mark half of all healthy servers as broken.
  func testPayloadReadsBothJSONAndServerSentEvents() throws {
    let json = Data(#"{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"a"}]}}"#.utf8)
    XCTAssertEqual((McpServerProbe.payload(from: json)?["tools"] as? [Any])?.count, 1)

    let sse = Data(
      "event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"tools\":[]}}\n\n".utf8)
    XCTAssertNotNil(McpServerProbe.payload(from: sse)?["tools"] as? [Any])

    XCTAssertNil(McpServerProbe.payload(from: Data("not json at all".utf8)))
  }

  // MARK: - Labels

  /// A count the probe could not establish must not render as "-1 tools".
  func testStatusLabelsNeverShowAnUnknownCount() throws {
    XCTAssertEqual(McpServerProbe.Status.running(toolCount: 3).label, "3 tools")
    XCTAssertEqual(McpServerProbe.Status.running(toolCount: 1).label, "1 tool")
    XCTAssertEqual(McpServerProbe.Status.running(toolCount: -1).label, "Responding")
    XCTAssertEqual(McpServerProbe.Status.needsAuth.label, "Needs sign-in")
    XCTAssertEqual(McpServerProbe.Status.unreachable("boom").label, "Not responding")
    XCTAssertEqual(McpServerProbe.Status.unreachable("boom").detail, "boom")
    XCTAssertNil(McpServerProbe.Status.running(toolCount: 2).detail)
    XCTAssertTrue(McpServerProbe.Status.running(toolCount: 0).isHealthy)
    XCTAssertFalse(McpServerProbe.Status.needsAuth.isHealthy)
  }

  /// A bundled app inherits none of a login shell's PATH, and `npx` lives in exactly the places a
  /// version manager or Homebrew put it.
  func testSearchPathAddsToolLocationsWithoutDuplicating() throws {
    let path = McpServerProbe.searchPath(from: ["PATH": "/usr/bin:/opt/homebrew/bin"])
    let entries = path.split(separator: ":").map(String.init)
    XCTAssertEqual(entries.first, "/usr/bin")
    XCTAssertTrue(entries.contains("/opt/homebrew/bin"))
    XCTAssertTrue(entries.contains("/usr/local/bin"))
    XCTAssertEqual(
      entries.count, Set(entries).count, "a duplicated PATH entry slows every command lookup")
  }

  // MARK: - Live handshake

  // MARK: - Local commands

  /// A configured command that resolves is ready; whether it *works* is only knowable by running
  /// it, which a status badge must not do — `npx` installs a package on first run.
  func testResolvesACommandOnThePath() throws {
    XCTAssertEqual(McpServerProbe.resolveCommand("sh"), .configured)
    XCTAssertEqual(McpServerProbe.resolveCommand("/bin/sh"), .configured)
    XCTAssertTrue(McpServerProbe.resolveCommand("sh").isHealthy)
    XCTAssertEqual(McpServerProbe.resolveCommand("sh").label, "Ready")
  }

  /// An `sse` server's URL is an event stream, not a POST target: probing it the Streamable HTTP
  /// way reports every such server as not responding, and the runtime install is equally dead.
  func testSseTransportRoutesToItsOwnTarget() throws {
    let url = try XCTUnwrap(URL(string: "https://mcp.wix.com/sse"))
    XCTAssertEqual(
      McpServerProbe.Target(entry: ["url": url.absoluteString, "transport": "sse"]),
      .sse(url: url, headers: [:]))
    XCTAssertEqual(
      McpServerProbe.Target(entry: ["url": url.absoluteString, "transport": "http"]),
      .http(url: url, headers: [:]))
    // A server written by hand without a transport is Streamable HTTP, today's default.
    XCTAssertEqual(
      McpServerProbe.Target(entry: ["url": url.absoluteString]), .http(url: url, headers: [:]))
  }

  /// The failure that actually happens: a command that was never installed, or was removed after
  /// the server was configured. It used to read "Active in chat".
  func testReportsACommandThatIsNotInstalled() throws {
    let missing = McpServerProbe.resolveCommand("omi-definitely-not-a-real-command")
    XCTAssertFalse(missing.isHealthy)
    XCTAssertEqual(missing.label, "Not responding")
    XCTAssertEqual(missing.detail, "omi-definitely-not-a-real-command is not installed")

    let absent = McpServerProbe.resolveCommand("/nope/not/here")
    XCTAssertFalse(absent.isHealthy)
    XCTAssertEqual(absent.detail, "/nope/not/here is not an executable file")
  }

}
