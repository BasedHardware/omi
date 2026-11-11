import ContextCore
import ContextMCPKit
import Foundation

/// stdout is the JSON-RPC channel. Nothing in this process may print to it — every diagnostic here
/// goes to stderr, where Claude logs it instead of trying to parse it as a frame.
private func note(_ message: String) {
    guard let data = "context-for-claude: \(message)\n".data(using: .utf8) else { return }
    try? FileHandle.standardError.write(contentsOf: data)
}

/// A missing database is the normal first-run state, not a failure: the server still starts, and
/// every tool explains that Context for Claude has not captured anything yet.
///
/// A database that exists but will not open is a different thing entirely, and the two used to be
/// nilled into one. The heartbeat is the tiebreaker — the app rewrites it every 30s, so a live beat
/// against an unopenable store proves the fault is in this process, not in the user's history. It is
/// logged loudly here because the operator reading stderr is the one who can fix it.
private func openStore() -> (store: ContextStore?, error: Error?) {
    do {
        return (try ContextStore(readOnly: true), nil)
    } catch ContextStoreError.notInitialized {
        switch CaptureState.diagnoseMissingDatabase() {
        case let .readerIsStale(_, age):
            note("""
            no database at \(ContextPaths.databaseURL.path), but the app's heartbeat is \(Int(age))s \
            old — capture is running somewhere this binary cannot see. This is almost certainly a \
            stale MCP server from an earlier install; restart Claude to reconnect it.
            """)
        case .appNotRunning:
            note("no database yet — Context for Claude has not captured anything")
        case .databaseAwaitingUpgrade:
            note("database predates this binary — launch the Context for Claude app once to upgrade it")
        }
        return (nil, nil)
    } catch ContextStoreError.awaitingAppUpgrade {
        note("""
        the capture database predates this binary and the app owns migrations, so every query would \
        fail. Launch the Context for Claude app once — it upgrades on launch. No captured data is lost.
        """)
        return (nil, nil)
    } catch {
        note("could not open the database read-only: \(error)")
        return (nil, error)
    }
}

// A client that goes away mid-write must surface as an EPIPE error on the write, not kill us.
_ = signal(SIGPIPE, SIG_IGN)

let opened = openStore()
MCPServer(store: opened.store, openError: opened.error).run()
