import Foundation

/// How many times Claude called each of this app's MCP tools, since the app last reported.
///
/// This is the product's central usage question. Everything else the analytics measure — launches,
/// permissions, captures — is setup; *this* is the thing the app exists to do, and it happens in a
/// process the app does not own. `context-for-claude-mcp` is spawned by Claude over stdio, once per
/// session, several at a time, and killed without warning. It cannot hold a socket open long enough
/// to report anything itself, and it must not try: a short-lived process that POSTs on exit either
/// blocks Claude's shutdown or loses the event.
///
/// So the MCP process counts and the app reports. The ledger is the seam.
///
/// ## Why not `QueryStamp`
///
/// `QueryStamp` already records that a tool was called, and deliberately records only the *latest*
/// one — it exists so the first-run tutorial can honestly say "found it", and a monotonic
/// last-writer-wins stamp is exactly right for that. It cannot answer "how many times this week",
/// and widening it to try would break the property its tests pin. Two files, two questions.
///
/// ## What is recorded, and what must never be
///
/// A tool name and a count. Nothing else, ever.
///
/// **Never add the query, the tool arguments, the result, or a per-call timestamp.** Those are the
/// user's questions and, through them, their private context. This file is plaintext on disk and its
/// contents are destined for an analytics pipeline, which raises the stakes over `QueryStamp` rather
/// than lowering them: a tool name is our own vocabulary, a count is arithmetic, and neither can be
/// turned back into anything the user said. An argument or a timestamp can.
/// `ToolCallLedgerTests.testTheLedgerCarriesNothingButToolNamesAndCounts` fails if a field is added.
public struct ToolCallLedger: Codable, Sendable, Equatable {
    /// Tool name → calls served since the last drain.
    public let counts: [String: Int]

    public init(counts: [String: Int] = [:]) {
        self.counts = counts
    }

    public var isEmpty: Bool { counts.isEmpty }

    public var total: Int { counts.values.reduce(0, +) }

    /// Nothing legitimate is anywhere near this large; a bigger file has been appended to or
    /// scribbled on, and is not a ledger.
    public static let maximumFileSize = 8192

    /// The app exposes ten tools. The cap is generous enough to survive a release that adds more and
    /// tight enough that a runaway writer cannot grow the file without bound — a ledger that has to
    /// be deleted to recover would lose real usage on every machine it happened to.
    public static let maximumDistinctTools = 64

    /// A single tool name longer than this is not one of ours.
    public static let maximumToolNameLength = 64

    // MARK: - Writing (the MCP server side)

    /// Adds one call for `tool`.
    ///
    /// Read-modify-write under the shared lock, then an atomic rename — the same discipline
    /// `QueryStamp.record` documents at length, and for the same reason: several MCP servers run at
    /// once with no coordinating parent, and the app reads this file as a third process.
    ///
    /// **Failure is silent by design.** A tool call that succeeded must not be reported to Claude as
    /// failed because a counter could not be written. The caller gets `Void` and no error; a lost
    /// count is a rounding error in a metric, while a failed `recall` is a broken product.
    public static func bump(tool: String, at url: URL = ContextPaths.toolCallLedgerURL) {
        let name = normalized(tool)
        guard !name.isEmpty else { return }

        do {
            let directory = url.deletingLastPathComponent()
            // The MCP server can be spawned before the app has ever run, so the directory may not
            // exist yet. Counting the very first call still has to work.
            _ = try ContextPaths.ensureSupportDirectory(at: directory)

            let lock = try ContextFileLock(at: ContextPaths.toolCallLedgerLockURL(for: url))
            defer { lock.release() }
            try lock.acquire()

            var counts = read(from: url)?.counts ?? [:]
            // A tool we have never seen cannot displace one we are already counting once the cap is
            // reached. Dropping the new name loses one series; evicting an old one silently corrupts
            // every number already accumulated under it.
            guard counts[name] != nil || counts.count < maximumDistinctTools else { return }
            counts[name, default: 0] += 1

            try ContextFileLock.replace(url, with: JSONEncoder().encode(ToolCallLedger(counts: counts)))
        } catch {
            return
        }
    }

    // MARK: - Reading (the app side)

    /// Returns everything counted since the last drain and resets the ledger to empty, atomically.
    ///
    /// Drain-on-read rather than read-and-remember: the app must not have to persist a high-water
    /// mark, and two app launches racing the same file would otherwise double-count. The reset is
    /// inside the same lock as the read, so a call arriving mid-drain lands in the next window
    /// instead of vanishing.
    ///
    /// **The caller now owns these counts.** If the report they were drained for fails to send, they
    /// are gone — the ledger has already forgotten them. `AnalyticsSpool` therefore takes them
    /// straight to durable storage before anything network-shaped is attempted.
    public static func drain(from url: URL = ContextPaths.toolCallLedgerURL) -> ToolCallLedger {
        do {
            let lock = try ContextFileLock(at: ContextPaths.toolCallLedgerLockURL(for: url))
            defer { lock.release() }
            try lock.acquire()

            guard let ledger = read(from: url), !ledger.isEmpty else { return ToolCallLedger() }
            try ContextFileLock.replace(url, with: JSONEncoder().encode(ToolCallLedger()))
            return ledger
        } catch {
            return ToolCallLedger()
        }
    }

    /// The current counts without draining them, or nil if there is no readable ledger.
    ///
    /// Missing, empty, truncated, over-sized, non-JSON and implausible files all answer nil, exactly
    /// as `QueryStamp.read` does: "I cannot read a ledger" and "nothing has been called" lead to the
    /// same honest outcome — reporting nothing — whereas treating a damaged file as data would
    /// invent usage that never happened.
    public static func read(from url: URL = ContextPaths.toolCallLedgerURL) -> ToolCallLedger? {
        guard let data = try? Data(contentsOf: url), !data.isEmpty, data.count <= maximumFileSize,
              let ledger = try? JSONDecoder().decode(ToolCallLedger.self, from: data)
        else { return nil }
        return ledger.plausible
    }

    /// Drops anything that cannot have come from `bump`, rather than rejecting the whole file.
    ///
    /// A ledger is an accumulation: discarding every count because one key is malformed would throw
    /// away real usage to punish a line nobody wrote on purpose.
    var plausible: ToolCallLedger? {
        let kept = counts.filter { name, count in
            !name.isEmpty && name.count <= Self.maximumToolNameLength && count > 0
                && name == Self.normalized(name)
        }
        guard !kept.isEmpty else { return nil }
        // Sorted before the cap so an over-long ledger truncates to the same set every time it is
        // read. Dictionary iteration order is not stable across processes, and a cap applied to an
        // unstable order would make two readers of one file disagree about what it says.
        let capped = kept.sorted { $0.key < $1.key }.prefix(Self.maximumDistinctTools)
        return ToolCallLedger(counts: Dictionary(uniqueKeysWithValues: capped.map { ($0.key, $0.value) }))
    }

    /// Our own vocabulary, spelled one way.
    ///
    /// Lowercased and stripped to `[a-z0-9_]` so a tool name can never carry anything but a tool
    /// name — this is the one string in the analytics payload that originates in a dispatch table
    /// rather than in a closed Swift enum, and the sanitiser is what keeps that difference from
    /// mattering.
    static func normalized(_ tool: String) -> String {
        String(tool.lowercased().unicodeScalars.filter {
            ("a"..."z").contains(String($0)) || ("0"..."9").contains(String($0)) || $0 == "_"
        }.map(Character.init).prefix(maximumToolNameLength))
    }
}
