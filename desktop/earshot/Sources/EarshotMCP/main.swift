import EarshotCore
import EarshotMCPKit
import Foundation

/// stdout is the JSON-RPC channel. Nothing in this process may print to it — every diagnostic here
/// goes to stderr, where Claude logs it instead of trying to parse it as a frame.
private func note(_ message: String) {
    guard let data = "earshot: \(message)\n".data(using: .utf8) else { return }
    try? FileHandle.standardError.write(contentsOf: data)
}

/// A missing or unreadable database is the normal first-run state, not a failure: the server still
/// starts, and every tool explains that Earshot has not captured anything yet.
private func openStore() -> EarshotStore? {
    do {
        return try EarshotStore(readOnly: true)
    } catch EarshotStoreError.notInitialized {
        note("no database yet — Earshot has not captured anything")
        return nil
    } catch {
        note("could not open the database read-only: \(error)")
        return nil
    }
}

// A client that goes away mid-write must surface as an EPIPE error on the write, not kill us.
_ = signal(SIGPIPE, SIG_IGN)

MCPServer(store: openStore()).run()
