import ContextCore
import Foundation
import OSLog

/// Diagnostics for Context for Claude.
///
/// `os.Logger` is the real destination: it survives a crash, costs nothing when nobody is reading,
/// and never leaves the machine. The `/tmp/context-for-claude.log` mirror exists only so the
/// build-and-verify loop can read what happened without Console.app, which is why it is opt-in
/// behind `CONTEXT_DEBUG=1`.
///
/// Callers own what they pass: never put captured audio, transcript text, or OCR into a message.
///
/// # Reading it back
///
/// ```sh
/// /usr/bin/log show --info --last 30m --predicate 'subsystem == "com.omi.context-for-claude"'
/// ```
///
/// Two things in that line are the difference between a diagnosis and "the app produces no log
/// output at all", which is how a real investigation on 2026-08-15 spent its first hour:
///
/// - **`/usr/bin/log`, not `log`.** `log` is a **zsh builtin** (it prints the `watch` list), and it
///   is the one that wins in an interactive zsh. `log show --predicate …` there does not reach the
///   unified log at all — it fails with `log: too many arguments` and writes nothing to stdout,
///   which reads as an app that logs nothing. Every invocation in this file is absolute for that
///   reason, and so should every one anybody pastes into a bug report.
/// - **`--info`, or two thirds of this file is invisible.** `info` is `OS_LOG_TYPE_INFO`, which
///   `log show` does not print unless asked; see the level table below. Without the flag the query
///   is not empty — it is correctly showing you the `milestone` and `error` lines only, and a quiet
///   app can genuinely have none of those in a five-minute window.
///
/// **Not `process == "Context for Claude"`.** That matches, but it also drags in every framework
/// this process links — CoreAudio, CFNetwork, boringssl — and buries the app's own lines in
/// thousands of them. The subsystem is the app's, and only the app's.
///
/// **The subsystem is the running bundle id**, so a locally built app logs under
/// `com.omi.context-for-claude.dev` and the installed release under `com.omi.context-for-claude`.
/// That is the point — two builds writing one subsystem produce an interleaved transcript nobody
/// can attribute. Query the one you are debugging, or `subsystem BEGINSWITH
/// "com.omi.context-for-claude"` for both.
///
/// To hand a whole run to somebody, the same query over a window that contains it:
///
/// ```sh
/// /usr/bin/log show --info --predicate 'subsystem == "com.omi.context-for-claude"' \
///   --start "2026-08-15 11:39:00" --end "2026-08-15 11:45:00" --style compact
/// ```
///
/// # Which level survives long enough to debug with
///
/// This is not a style question, it is the difference between a diagnosable failure and a guess.
/// Unified logging treats the levels differently and only some of them reach the disk:
///
/// | Level              | `os_log` type      | Where it goes                                 |
/// |--------------------|--------------------|-----------------------------------------------|
/// | `.debug`           | `DEBUG`            | dropped unless the subsystem is opted in       |
/// | `info`             | `INFO`             | **memory ring buffer only** — evicted in minutes |
/// | `milestone`        | `DEFAULT`          | persisted                                      |
/// | `error`            | `ERROR`            | persisted                                      |
///
/// Measured on this Mac on 2026-08-02: a query run at 14:14 could still read `DEFAULT` lines from
/// 13:40, and the *oldest* `INFO` line it could see anywhere was from 14:10 — four minutes back.
/// The app wrote every lifecycle decision it makes through `info`, so by the time anyone asked what
/// had happened, the answer had already been thrown away. That is why `milestone` exists: it is for
/// the handful of lines whose absence turns a bug report into an archaeology exercise — process
/// lifecycle, and any decision the app makes *on the user's behalf* that it cannot ask about later.
///
/// It is deliberately not `error`. A quit the user pressed is not a failure, and a log that shouts
/// about ordinary events is a log people stop reading.
enum ContextLog {
    static func info(_ message: String, _ category: String = "app") {
        logger(for: category).info("\(message, privacy: .public)")
        mirror(level: "info", category: category, message: message)
    }

    /// An event that has to still be there tomorrow. See the level table above — `info` will not be.
    ///
    /// Use it sparingly and for facts rather than progress: who ended this process, what the app
    /// decided to do about it, and on which inputs. Everything else stays `info`.
    static func milestone(_ message: String, _ category: String = "app") {
        // `.notice` is Swift's spelling of `OS_LOG_TYPE_DEFAULT`, which is the persisted level.
        logger(for: category).notice("\(message, privacy: .public)")
        mirror(level: "milestone", category: category, message: message)
    }

    static func error(_ message: String, _ category: String = "app") {
        logger(for: category).error("\(message, privacy: .public)")
        mirror(level: "error", category: category, message: message)
    }

    // MARK: - os.Logger

    /// The running bundle, not the shipping constant, so a dev build's lines and the installed
    /// app's are separable in one `log show` rather than interleaved under one name.
    ///
    /// Internal rather than private only so the wiring can be asserted — `os.Logger` never gives its
    /// subsystem back, so reading this constant is the whole of what is observable about it.
    static let subsystem = ContextPaths.bundleIdentifier
    private static let loggersLock = NSLock()
    private static nonisolated(unsafe) var loggers: [String: Logger] = [:]

    /// One `Logger` per category, cached. `Logger(subsystem:category:)` allocates an `os_log_t`, and
    /// the capture paths call this often enough for that allocation to be worth avoiding.
    private static func logger(for category: String) -> Logger {
        loggersLock.lock()
        defer { loggersLock.unlock() }
        if let existing = loggers[category] { return existing }
        let created = Logger(subsystem: subsystem, category: category)
        loggers[category] = created
        return created
    }

    // MARK: - Debug mirror

    private static let mirrorPath = "/tmp/context-for-claude.log"
    private static let isMirroring = ProcessInfo.processInfo.environment["CONTEXT_DEBUG"] == "1"
    /// Serial: the mirror is a transcript, so lines must land in the order they were emitted, and
    /// nothing below is safe to touch from two threads at once.
    private static let mirrorQueue = DispatchQueue(label: "com.omi.context-for-claude.log", qos: .utility)
    private static let mirrorTimestamps: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss.SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    // Both are read and written only inside `mirrorQueue`.
    private static nonisolated(unsafe) var isMirrorFileUsable = false
    private static nonisolated(unsafe) var didReportMirrorFailure = false

    private static func mirror(level: String, category: String, message: String) {
        guard isMirroring else { return }
        // Stamp at the call, format on the queue: `DateFormatter` is not thread-safe, and a queued
        // line should still carry the time it actually happened.
        let occurredAt = Date()
        mirrorQueue.async {
            let stamp = mirrorTimestamps.string(from: occurredAt)
            guard let data = "[\(stamp)] [\(category)] [\(level)] \(message)\n".data(using: .utf8) else { return }
            if !isMirrorFileUsable { isMirrorFileUsable = prepareMirrorFile() }
            guard isMirrorFileUsable else { return }
            append(data)
        }
    }

    /// Appends. `FileHandle(forWritingTo:)` opens without truncating, and seeking to the end before
    /// every write is what keeps a long run's earlier lines intact — unlike `Data.write(to:)`, which
    /// would replace the whole file on each call.
    private static func append(_ data: Data) {
        do {
            let handle = try FileHandle(forWritingTo: URL(fileURLWithPath: mirrorPath))
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: data)
        } catch {
            // The file was removed underneath us, or the disk is full. Re-prepare on the next line
            // rather than silently dropping every line for the rest of the run.
            isMirrorFileUsable = false
            reportMirrorFailureOnce(error)
        }
    }

    /// `/tmp` is world-writable and sticky, so any local user can pre-create this path. Never adopt
    /// something we do not own: `lstat` judges a symlink on its own rather than on its target, and
    /// anything that is not our own regular file is removed and recreated owner-only.
    private static func prepareMirrorFile() -> Bool {
        let fileManager = FileManager.default
        var info = stat()
        if lstat(mirrorPath, &info) == 0 {
            let isRegularFile = (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
            if isRegularFile, info.st_uid == getuid() {
                // Keep what a previous run wrote; only tighten the permissions.
                return (try? fileManager.setAttributes(
                    [.posixPermissions: 0o600], ofItemAtPath: mirrorPath)) != nil
            }
            guard (try? fileManager.removeItem(atPath: mirrorPath)) != nil else { return false }
        }
        return fileManager.createFile(
            atPath: mirrorPath, contents: nil, attributes: [.posixPermissions: 0o600])
    }

    /// Bounded: a full disk fails on every line, and the mirror must never become the loudest thing
    /// in the log it is mirroring.
    private static func reportMirrorFailureOnce(_ error: Error) {
        guard !didReportMirrorFailure else { return }
        didReportMirrorFailure = true
        let nsError = error as NSError
        logger(for: "log").error(
            "Debug log mirror unavailable (domain=\(nsError.domain, privacy: .public) code=\(nsError.code, privacy: .public))"
        )
    }
}
