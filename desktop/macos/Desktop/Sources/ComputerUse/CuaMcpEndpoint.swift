import Foundation

/// The computer-use tools, spoken as MCP.
///
/// A pure message-in, message-out handler: the loopback server owns the socket,
/// the token and the origin checks, and everything here is JSON-RPC. That split
/// is what makes the protocol testable without a network.
///
/// **Dual-era, on purpose.** MCP `2026-07-28` removed the `initialize`
/// handshake and made every request carry its own version, but the clients that
/// exist today — Omi's own runtime, Claude Desktop, Cursor — still open with
/// `initialize`. A server that speaks only one era is unreachable from half the
/// ecosystem, so this one answers both: `initialize` selects legacy semantics,
/// and `server/discover` plus per-request `_meta` selects modern. The spec's own
/// compatibility matrix calls this shape dual-era and expects it to work with
/// every client on either side.
enum CuaMcpEndpoint {
  static let serverName = "omi-computer-use"
  static let serverVersion = "1.0.0"

  /// Newest first, which is also the order a client should prefer them in.
  static let supportedVersions = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"]

  /// Sent to the model with the tool list. Says which lane to reach for, because
  /// the difference between the two is a thousand tokens and a missed click.
  static let instructions = """
    Drives this Mac. Prefer the accessibility lane: ui_snapshot lists an app's \
    controls with refs, and ui_action presses one by ref — cheap, and it cannot \
    miss. Fall back to screenshot plus click for apps that publish no tree. \
    Coordinates are always in the pixels of the screenshot you were last shown. \
    Look again after acting: this is a real desk, and windows move.
    """

  private enum ErrorCode {
    static let invalidRequest = -32600
    static let methodNotFound = -32601
    /// `2026-07-28` renumbered this out of the implementation-defined range.
    static let unsupportedProtocolVersion = -32022
  }

  /// One JSON-RPC message in, one response out. `nil` means the message was a
  /// notification and the transport should answer with no body.
  static func handle(_ message: [String: Any]) async -> [String: Any]? {
    let id = message["id"]
    guard let method = message["method"] as? String else {
      return failure(id: id, code: ErrorCode.invalidRequest, message: "Missing method")
    }
    let params = message["params"] as? [String: Any] ?? [:]

    // A modern client names its version on every request. A legacy client names
    // it once, in `initialize`, and is checked there instead.
    if let meta = params["_meta"] as? [String: Any],
      let requested = meta["io.modelcontextprotocol/protocolVersion"] as? String,
      !supportedVersions.contains(requested)
    {
      guard id != nil else { return nil }
      return [
        "jsonrpc": "2.0",
        "id": id!,
        "error": [
          "code": ErrorCode.unsupportedProtocolVersion,
          "message": "Unsupported protocol version",
          "data": ["supported": supportedVersions, "requested": requested],
        ],
      ]
    }

    switch method {
    case "initialize":
      return success(id: id, result: initializeResult(params: params))
    case "server/discover":
      return success(id: id, result: discoverResult())
    case "notifications/initialized", "notifications/cancelled":
      return nil
    case "ping":
      return success(id: id, result: [:])
    case "tools/list":
      return success(id: id, result: toolsListResult())
    case "tools/call":
      return await success(id: id, result: toolsCallResult(params: params))
    default:
      return failure(id: id, code: ErrorCode.methodNotFound, message: "Unknown method \(method)")
    }
  }

  // MARK: - Results

  private static func initializeResult(params: [String: Any]) -> [String: Any] {
    // Echo the client's version when we speak it, so a client pinned to an older
    // revision keeps talking in that revision; otherwise name our newest legacy
    // one, which is the answer the spec expects a client to either accept or
    // disconnect on.
    let requested = params["protocolVersion"] as? String
    let agreed = requested.flatMap { supportedVersions.contains($0) ? $0 : nil } ?? "2025-11-25"
    return [
      "protocolVersion": agreed,
      "capabilities": ["tools": ["listChanged": false]],
      "serverInfo": ["name": serverName, "version": serverVersion],
      "instructions": instructions,
    ]
  }

  private static func discoverResult() -> [String: Any] {
    [
      "resultType": "complete",
      "supportedVersions": supportedVersions,
      "capabilities": ["tools": [:]],
      "instructions": instructions,
      "_meta": [
        "io.modelcontextprotocol/serverInfo": ["name": serverName, "version": serverVersion]
      ],
      // The tool list is fixed for the life of the process, but the answers it
      // gives are not, so nothing here invites a shared cache.
      "ttlMs": 3_600_000,
      "cacheScope": "private",
    ]
  }

  private static func toolsListResult() -> [String: Any] {
    [
      "resultType": "complete",
      "tools": CuaToolCatalog.tools.map { tool in
        [
          "name": tool.name,
          "description": tool.description,
          "inputSchema": tool.inputSchema,
        ] as [String: Any]
      },
      "ttlMs": 3_600_000,
      "cacheScope": "private",
    ]
  }

  private static func toolsCallResult(params: [String: Any]) async -> [String: Any] {
    guard let name = params["name"] as? String else {
      return errorContent("tools/call needs a tool name.")
    }
    guard CuaToolCatalog.tool(named: name) != nil else {
      return errorContent("Unknown tool \(name).")
    }
    let arguments = params["arguments"] as? [String: Any] ?? [:]
    let result = await CuaToolCatalog.call(name, arguments: arguments)
    return [
      "resultType": "complete",
      "content": result.content.map(\.json),
      "isError": result.isError,
    ]
  }

  /// A tool-level failure is a result, not a JSON-RPC error: the model is meant
  /// to read it and try something else, which it cannot do with a transport
  /// error.
  private static func errorContent(_ text: String) -> [String: Any] {
    [
      "resultType": "complete",
      "content": [["type": "text", "text": text]],
      "isError": true,
    ]
  }

  private static func success(id: Any?, result: [String: Any]) -> [String: Any]? {
    guard let id else { return nil }
    return ["jsonrpc": "2.0", "id": id, "result": result]
  }

  private static func failure(id: Any?, code: Int, message: String) -> [String: Any]? {
    guard let id else { return nil }
    return ["jsonrpc": "2.0", "id": id, "error": ["code": code, "message": message]]
  }
}
