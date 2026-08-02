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
enum ContextLog {
    static func info(_ message: String, _ category: String = "app") {
        logger(for: category).info("\(message, privacy: .public)")
        mirror(level: "info", category: category, message: message)
    }

    static func error(_ message: String, _ category: String = "app") {
        logger(for: category).error("\(message, privacy: .public)")
        mirror(level: "error", category: category, message: message)
    }

    // MARK: - os.Logger

    private static let subsystem = "com.omi.context-for-claude"
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
