import Foundation

/// Putting Omi's own computer-use server into the MCP config Omi reads.
///
/// The agent runtime discovers servers from `~/.omi/mcp.json` and nowhere else,
/// so the way to give Omi's chat these tools is to write an entry there, exactly
/// as a user adding any other remote server would. Nothing is special-cased in
/// the runtime, which means the tools reach the pi lane, the ACP lane, and any
/// other client the user points at the same file, all through one path.
enum CuaMcpRegistration {
  static let serverName = "omi-computer-use"

  static var endpointURL: String {
    "\(LocalAgentAPISettings.serverURL)/mcp"
  }

  /// The entry as written. The token is the local API's, because that is the
  /// credential this endpoint authenticates against; it lands in the same
  /// user-owned file every other MCP token already lives in.
  static func entry(token: String) -> [String: Any] {
    ["url": endpointURL, "token": token]
  }

  static func register(token: String) throws {
    try LocalMcpStore.upsertServer(serverName, entry: entry(token: token))
    try CuaStdioShim.install(token: token)
  }

  static func unregister() {
    LocalMcpStore.removeServer(name: serverName)
    CuaStdioShim.uninstall()
  }

  /// Whether the entry present on disk points at this build's endpoint. A port
  /// change or a reinstalled token leaves a stale entry that answers 401 on
  /// every call, which reads to the model as a server that has no tools.
  static func isRegistered(token: String?) -> Bool {
    guard let raw = LocalMcpStore.readAllServers()[serverName] as? [String: Any] else {
      return false
    }
    guard raw["url"] as? String == endpointURL else { return false }
    guard let token else { return true }
    return raw["token"] as? String == token
  }
}
