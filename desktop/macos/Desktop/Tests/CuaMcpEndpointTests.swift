import CoreGraphics
import XCTest

@testable import Omi_Computer

/// The wire contract. A client that cannot negotiate a version or read the tool
/// list sees a server with no tools, which looks exactly like a server that is
/// not running.
final class CuaMcpEndpointTests: XCTestCase {
  private func send(_ message: [String: Any]) async -> [String: Any]? {
    await CuaMcpEndpoint.handle(message)
  }

  func testInitializeAnswersInTheVersionTheClientAsked() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": ["protocolVersion": "2025-06-18"],
    ])
    let result = response?["result"] as? [String: Any]
    XCTAssertEqual(result?["protocolVersion"] as? String, "2025-06-18")
    XCTAssertNotNil((result?["capabilities"] as? [String: Any])?["tools"])
    XCTAssertEqual(
      (result?["serverInfo"] as? [String: Any])?["name"] as? String, "omi-computer-use")
  }

  /// A version we do not speak still gets an answer, in the newest legacy
  /// revision. A legacy client has no fall-forward path, so silence would leave
  /// it with nothing to show the user.
  func testInitializeFallsBackToTheNewestLegacyVersion() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": ["protocolVersion": "1900-01-01"],
    ])
    XCTAssertEqual(
      (response?["result"] as? [String: Any])?["protocolVersion"] as? String, "2025-11-25")
  }

  /// The 2026-07-28 shape: no handshake, the version rides on every request.
  func testDiscoverNamesEveryVersionAndTheServer() async {
    let response = await send(["jsonrpc": "2.0", "id": "d1", "method": "server/discover"])
    let result = response?["result"] as? [String: Any]
    XCTAssertEqual(result?["resultType"] as? String, "complete")
    let versions = result?["supportedVersions"] as? [String]
    XCTAssertEqual(versions?.first, "2026-07-28")
    XCTAssertTrue(versions?.contains("2025-06-18") ?? false)
    let meta = result?["_meta"] as? [String: Any]
    let serverInfo = meta?["io.modelcontextprotocol/serverInfo"] as? [String: Any]
    XCTAssertEqual(serverInfo?["name"] as? String, "omi-computer-use")
  }

  /// A modern client naming a version we cannot speak gets the renumbered
  /// `UnsupportedProtocolVersionError`, with the list it should retry from.
  func testAnUnknownPerRequestVersionIsRejectedWithTheSupportedList() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 7, "method": "tools/list",
      "params": ["_meta": ["io.modelcontextprotocol/protocolVersion": "2030-01-01"]],
    ])
    let error = response?["error"] as? [String: Any]
    XCTAssertEqual(error?["code"] as? Int, -32022)
    let data = error?["data"] as? [String: Any]
    XCTAssertEqual(data?["requested"] as? String, "2030-01-01")
    XCTAssertEqual((data?["supported"] as? [String])?.first, "2026-07-28")
  }

  func testAKnownPerRequestVersionIsServed() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 8, "method": "tools/list",
      "params": ["_meta": ["io.modelcontextprotocol/protocolVersion": "2026-07-28"]],
    ])
    XCTAssertNotNil((response?["result"] as? [String: Any])?["tools"])
  }

  func testToolsListCarriesNamesSchemasAndCacheHints() async {
    let response = await send(["jsonrpc": "2.0", "id": 2, "method": "tools/list"])
    let result = response?["result"] as? [String: Any]
    let tools = result?["tools"] as? [[String: Any]] ?? []
    XCTAssertEqual(tools.count, CuaToolCatalog.tools.count)
    XCTAssertTrue(tools.allSatisfy { ($0["description"] as? String)?.isEmpty == false })
    XCTAssertTrue(tools.allSatisfy { ($0["inputSchema"] as? [String: Any])?["type"] != nil })
    // Required on a modern result, ignored by a legacy client.
    XCTAssertEqual(result?["cacheScope"] as? String, "private")
    XCTAssertNotNil(result?["ttlMs"])
  }

  /// The whole surface is JSON-serialisable or the transport cannot answer at
  /// all — a schema built with a stray Swift value fails only at send time.
  func testTheToolListSerialises() async {
    let response = await send(["jsonrpc": "2.0", "id": 3, "method": "tools/list"])
    XCTAssertTrue(JSONSerialization.isValidJSONObject(response ?? [:]))
  }

  func testANotificationGetsNoResponse() async {
    let response = await send(["jsonrpc": "2.0", "method": "notifications/initialized"])
    XCTAssertNil(response)
  }

  func testAnUnknownMethodIsAJsonRpcError() async {
    let response = await send(["jsonrpc": "2.0", "id": 4, "method": "resources/list"])
    XCTAssertEqual((response?["error"] as? [String: Any])?["code"] as? Int, -32601)
  }

  /// An unknown tool is a result the model can read and recover from, not a
  /// transport error that ends the turn.
  func testAnUnknownToolIsAToolError() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 5, "method": "tools/call",
      "params": ["name": "make_coffee", "arguments": [:]],
    ])
    let result = response?["result"] as? [String: Any]
    XCTAssertEqual(result?["isError"] as? Bool, true)
    XCTAssertNil(response?["error"])
  }

  /// A client's health probe opens with `initialize` and reads `tools/list`.
  /// Refusing those while the switch is off made the probe report the server as
  /// broken — "Needs sign-in", from a 403 it cannot tell from an expired token —
  /// in the state the switch spends most of its life in.
  func testTheHandshakeAnswersWhileTheSwitchIsOff() async {
    let initialize = await send([
      "jsonrpc": "2.0", "id": 20, "method": "initialize", "params": [:],
    ])
    XCTAssertNotNil((initialize?["result"] as? [String: Any])?["serverInfo"])
    let tools = await send(["jsonrpc": "2.0", "id": 21, "method": "tools/list"])
    XCTAssertFalse(((tools?["result"] as? [String: Any])?["tools"] as? [Any] ?? []).isEmpty)
  }

  /// And nothing that touches the Mac answers while it is off.
  func testEveryToolCallIsRefusedWhileTheSwitchIsOff() async {
    let response = await send([
      "jsonrpc": "2.0", "id": 22, "method": "tools/call",
      "params": ["name": "list_windows", "arguments": [:]],
    ])
    let result = response?["result"] as? [String: Any]
    XCTAssertEqual(result?["isError"] as? Bool, true)
    let text = (result?["content"] as? [[String: Any]])?.first?["text"] as? String
    XCTAssertTrue(text?.contains("Computer control is off") ?? false)
  }

  /// HIToolbox's input-source APIs assert they are on the main queue and *trap*
  /// when they are not, so resolving a chord from the server's own queue took the
  /// whole app down — `TSMGetInputSourceProperty` → `_dispatch_assert_queue_fail`
  /// → SIGTRAP — the first time a model pressed a key. This drives `key` from a
  /// background context the way the endpoint does; if the main-actor hop is
  /// removed, this test does not fail, it kills the test runner.
  func testResolvingAChordFromABackgroundContextDoesNotTrap() async {
    let result = await Task.detached {
      await CuaToolCatalog.call("key", arguments: ["combo": "hyper+q"])
    }.value
    XCTAssertTrue(result.isError)
  }

  /// Every listed tool must be dispatched, and nothing else. The list and the
  /// switch are written in two places, and a tool that lists but does not
  /// dispatch is one the model will call exactly once and never get an answer
  /// from. Empty arguments are used on purpose: every acting tool validates its
  /// arguments before it touches the gate, so this drives no input.
  func testEveryListedToolIsDispatched() async {
    for tool in CuaToolCatalog.tools {
      let result = await CuaToolCatalog.call(tool.name, arguments: [:])
      let text = result.content.compactMap { block -> String? in
        if case .text(let text) = block { return text }
        return nil
      }.joined()
      XCTAssertFalse(
        text.contains("Unknown tool"), "\(tool.name) is listed but has no dispatch case")
    }
    let unknown = await CuaToolCatalog.call("not_a_tool", arguments: [:])
    XCTAssertTrue(unknown.isError)
  }
}
