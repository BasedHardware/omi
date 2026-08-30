import Foundation

/// A stdio front door for clients that cannot speak to a URL.
///
/// The endpoint itself is Streamable HTTP on the loopback interface, which is
/// what Omi's own runtime and every current desktop client prefer. Some clients
/// still only launch a command and talk to its pipes, so this writes a shim they
/// can launch: `~/.omi/omi-cua`, a few lines of shell that forward each JSON-RPC
/// line to the endpoint and print the reply.
///
/// It is deliberately not a second server. It holds no permission of its own —
/// every accessibility and capture call still happens inside Omi, under the
/// grants the user gave Omi — and it holds no state, so there is nothing in it
/// to get out of step with the app. It is a pipe.
enum CuaStdioShim {
  static var scriptURL: URL {
    LocalSkillsStore.rootURL.appendingPathComponent("omi-cua")
  }

  /// Rewritten whenever control is enabled, because the token can be rotated and
  /// the port can be changed, and a shim carrying either stale value answers 401
  /// to every call — which a client shows as a server with no tools.
  static func install(token: String) throws {
    let script = """
      #!/bin/sh
      # Written by Omi. Bridges an MCP stdio client to Omi's computer-use endpoint.
      # Every line in is one JSON-RPC message; every non-empty reply is one line out.
      # Delete this file, or turn off computer control in Omi, to revoke it.
      while IFS= read -r line; do
        [ -z "$line" ] && continue
        reply=$(printf '%s' "$line" | curl -sS -X POST '\(CuaMcpRegistration.endpointURL)' \\
          -H 'Content-Type: application/json' \\
          -H 'Authorization: Bearer \(token)' \\
          --data-binary @-) || continue
        [ -n "$reply" ] && printf '%s\\n' "$reply"
      done

      """
    let fileManager = FileManager.default
    try fileManager.createDirectory(
      at: LocalSkillsStore.rootURL, withIntermediateDirectories: true)
    try Data(script.utf8).write(to: scriptURL, options: .atomic)
    // The token is in the file, so it is readable only by its owner — the same
    // rule the tokens already in mcp.json live under.
    try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: scriptURL.path)
  }

  static func uninstall() {
    try? FileManager.default.removeItem(at: scriptURL)
  }
}
