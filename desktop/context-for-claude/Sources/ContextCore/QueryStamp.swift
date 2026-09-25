import Foundation

/// Proof that Claude actually called one of this app's MCP tools.
///
/// `context-for-claude-mcp` writes this; the app reads it. It exists for one reason: the first-run
/// tutorial ends by telling the user to restart Claude and ask it a question, and the "found it"
/// beat that follows has to be *earned*. A timer, a fixed delay, or an optimistic assumption would
/// all be theatre — this app's whole claim is that it never reports coverage it does not have, and a
/// staged payoff in the tutorial would be the first lie it tells.
///
/// A file rather than IPC because the two processes cannot talk: Claude spawns the MCP server over
/// stdio, per session, and it opens the database **read-only** (`Store.makeConfiguration(readOnly:)`).
/// The database is therefore not available as the channel — the writer here is a reader there.
///
/// ## What is recorded, and what must never be
///
/// A tool name and a timestamp. Nothing else, ever.
///
/// **Never add the query, the tool arguments, or the result.** Those are the user's questions, and
/// through them their private context; this file is plaintext on disk and exists purely so a UI
/// animation can be honest. Trading the confidentiality of what the user asks for the ability to
/// animate a checkmark is not a trade worth making — if the choice ever comes up, drop the
/// animation. `QueryStamp` deliberately has no field that could hold them, and
/// `QueryStampTests.testTheStampCarriesNothingButAToolNameAndATime` fails if one is added.
public struct QueryStamp: Codable, Sendable, Equatable {
    /// Which tool was served, e.g. `recall`. Safe to show the user — it is our own vocabulary, not
    /// theirs.
    public let tool: String
    /// When it was served, as a UNIX epoch in seconds.
    public let at: Double

    public init(tool: String, at: Double = ContextTime.now) {
        self.tool = tool
        self.at = at
    }

    /// Nothing legitimate is anywhere near this large; a bigger file has been appended to or
    /// scribbled on, and is not a stamp.
    static let maximumFileSize = 4096

    /// How far ahead of now an existing stamp may sit and still be believed. Wide enough that two
    /// MCP servers on one machine always agree, narrow enough that a mis-set clock heals in minutes.
    static let futureTolerance: Double = 300

    /// Rejects a file that parses but cannot have come from `record`. A default-decoded or
    /// zero-filled stamp claiming a 1970 tool call would read as a real one.
    var isPlausible: Bool {
        !tool.isEmpty && tool.count <= 64 && at.isFinite && at > 0
    }

    // MARK: - Writing (the MCP server side)

    /// Records this stamp, replacing whatever was there — unless what was there is newer.
    ///
    /// ## Concurrency
    ///
    /// Claude routinely keeps **several MCP server processes alive at once** (two is normal on a
    /// working machine), so this is a multi-writer file with no coordinating parent, and the reader
    /// is a third process. Two properties matter, and both are handled here rather than left to the
    /// caller:
    ///
    /// 1. **A reader never sees a partial file.** `ContextFileLock.replace` writes to a uniquely
    ///    named temp file and `rename(2)`s it onto the destination, so a reader opening the path gets
    ///    either the whole previous file or the whole new one. Readers therefore take no lock at all
    ///    and can never block a server.
    /// 2. **The newest call wins.** Renames alone are last-writer-wins by wall-clock arrival, so a
    ///    server that was slightly slow could bury a newer stamp under its older one. The
    ///    read-compare-rename is therefore done under an exclusive `flock` on a *separate* lock file
    ///    — `ContextFileLock`, which documents why separate is the only workable choice and why a
    ///    crashed MCP server cannot wedge the file.
    public func record(to url: URL = ContextPaths.queryStampURL) throws {
        let directory = url.deletingLastPathComponent()
        // The MCP server can be spawned before the app has ever run, so the directory may not exist
        // yet. Recording the very first call still has to work.
        _ = try ContextPaths.ensureSupportDirectory(at: directory)

        let lock = try ContextFileLock(at: ContextPaths.queryStampLockURL(for: url))
        defer { lock.release() }
        try lock.acquire()

        // Monotonic: a stamp never moves backwards, so a slow writer cannot hide a newer call.
        //
        // Except from the future, which is not a newer call — it is a wrong clock. Deferring to it
        // unconditionally would wedge this file until wall-clock caught up, and a tutorial waiting
        // forever for a call Claude already made is a worse failure than losing one stamp.
        if let existing = Self.read(from: url), existing.at >= at,
           existing.at <= ContextTime.now + Self.futureTolerance {
            return
        }

        try ContextFileLock.replace(url, with: JSONEncoder().encode(self))
    }

    /// Convenience for the one call site that matters: the MCP server's tool dispatch.
    public static func record(
        tool: String,
        at: Double = ContextTime.now,
        to url: URL = ContextPaths.queryStampURL
    ) throws {
        try QueryStamp(tool: tool, at: at).record(to: url)
    }

    // MARK: - Reading (the app side)

    /// The last recorded call, or nil if there is none.
    ///
    /// Missing, empty, truncated, over-sized, non-JSON and implausible files all answer nil. "I
    /// cannot read a stamp" and "no tool has been called" lead to the same honest UI — waiting —
    /// whereas treating a damaged file as a call would fire the payoff beat for nothing.
    public static func read(from url: URL = ContextPaths.queryStampURL) -> QueryStamp? {
        guard let data = try? Data(contentsOf: url), !data.isEmpty, data.count <= maximumFileSize,
              let stamp = try? JSONDecoder().decode(QueryStamp.self, from: data),
              stamp.isPlausible
        else { return nil }
        return stamp
    }

    /// A call served *strictly after* `moment`, or nil.
    ///
    /// This is what the tutorial asks: it snapshots `ContextTime.now` before telling the user to
    /// restart Claude, then watches. Strictly after, because a stamp already on disk when the watch
    /// began was left by an earlier session and proves nothing about the question the user is about
    /// to ask.
    public static func newCall(since moment: Double, from url: URL = ContextPaths.queryStampURL) -> QueryStamp? {
        guard let stamp = read(from: url), stamp.at > moment else { return nil }
        return stamp
    }

    /// Waits for a call served after `moment`, giving up after `timeout` seconds. Returns nil on
    /// timeout or cancellation.
    ///
    /// Polling, not a file-system watch: the stamp is *replaced* by rename, so a vnode source on the
    /// file would be watching an inode that has been unlinked, and a directory watch is more
    /// machinery than a 50-byte file checked twice a second deserves.
    public static func waitForCall(
        since moment: Double,
        timeout: Double,
        pollInterval: Double = 0.5,
        from url: URL = ContextPaths.queryStampURL
    ) async -> QueryStamp? {
        let deadline = ContextTime.now + max(0, timeout)
        while true {
            if let stamp = newCall(since: moment, from: url) { return stamp }
            let remaining = deadline - ContextTime.now
            if remaining <= 0 { return nil }
            let nap = min(max(0.01, pollInterval), remaining)
            do {
                try await Task.sleep(nanoseconds: UInt64(nap * 1_000_000_000))
            } catch {
                return nil // Cancelled: the tutorial moved on or the window closed.
            }
        }
    }
}

// The lock and the atomic replace live in `ContextFileLock`, shared with `ToolCallLedger`. Both files
// are written by concurrent `context-for-claude-mcp` processes and read by the app, so they need the
// identical discipline; two hand-written flock dances in one package is one more than can be kept
// correct.
