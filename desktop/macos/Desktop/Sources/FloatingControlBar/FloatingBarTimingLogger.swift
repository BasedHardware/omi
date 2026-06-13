import Foundation

/// Side-effect layer for `FloatingBarQueryTiming`.
///
/// - Writes one JSON line per completed query to a dedicated timings log so
///   the data is easy to tail during a hackathon demo (`tail -f`).
/// - Emits a single PostHog event per query with the aggregate timings.
///
/// Both side effects are best-effort. A logger failure must never break the
/// user's query — we log the error to the standard logger and move on.
///
/// Production builds write to `/tmp/omi.log` only (PostHog path). Dev/test
/// bundles write to the timings file in addition.
@MainActor
public final class FloatingBarTimingLogger {
    public static let shared = FloatingBarTimingLogger()

    /// Path of the per-query timings log file. One JSON object per line.
    public nonisolated(unsafe) static let defaultLogFile = "/tmp/omi-floating-bar-timings.log"

    private let timingsLogFile: String
    private let logQueue: DispatchQueue
    private let postHog: PostHogEmit
    private let standardLog: StandardLog

    /// Public init for tests — production uses `.shared`.
    public init(
        timingsLogFile: String = FloatingBarTimingLogger.defaultLogFile,
        logQueue: DispatchQueue = DispatchQueue(
            label: "me.omi.floating-bar.timings", qos: .utility),
        postHog: PostHogEmit = PostHogEmitLive(),
        standardLog: StandardLog = StandardLogLive()
    ) {
        self.timingsLogFile = timingsLogFile
        self.logQueue = logQueue
        self.postHog = postHog
        self.standardLog = standardLog
    }

    /// Persist the final timing to the log file and emit a PostHog event.
    /// Safe to call multiple times; only the first call writes (idempotent).
    public func record(_ timing: FloatingBarQueryTiming) {
        guard timing.final != nil else {
            standardLog.log(
                "FloatingBarTimingLogger: skipping record — query not ended (\(timing.queryId))"
            )
            return
        }

        // Serialize once, share the JSON string between file + PostHog paths.
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]

        let data: Data
        do {
            data = try encoder.encode(timing)
        } catch {
            standardLog.log(
                "FloatingBarTimingLogger: encode failed: \(error.localizedDescription)"
            )
            return
        }
        guard let jsonString = String(data: data, encoding: .utf8) else {
            standardLog.log("FloatingBarTimingLogger: json string conversion failed")
            return
        }

        // File write — non-blocking, async, on logQueue.
        logQueue.async { [timingsLogFile] in
            Self.appendLine(jsonString, to: timingsLogFile)
        }

        // PostHog — single event with aggregate timings.
        let props = Self.postHogProperties(for: timing)
        postHog.track("floating_bar_query_timing", properties: props)
    }

    // MARK: - PostHog property bag

    /// Flatten the timing struct into PostHog's [String: Any]. Stage timings
    /// are flattened to `stage_<stage>_ms` (e.g. `stage_first_delta_ms`)
    /// so dashboards can graph each stage independently.
    static func postHogProperties(for timing: FloatingBarQueryTiming) -> [String: Any] {
        var props: [String: Any] = [
            "query_id": timing.queryId,
            "source": timing.source.rawValue,
            "query_length": timing.queryLength,
        ]
        if let model = timing.model { props["model"] = model }
        for mark in timing.stages {
            props["stage_\(mark.stage.rawValue)_ms"] = mark.msSinceStart
            if let note = mark.note { props["stage_\(mark.stage.rawValue)_note"] = note }
        }
        if let final = timing.final {
            props["total_ms"] = final.totalMs
            props["had_screenshot"] = final.hadScreenshot
            props["tool_call_count"] = final.toolCallCount
            props["cancelled"] = final.cancelled
            props["end_reason"] = final.reason.rawValue
            if let prompt = final.promptTokens { props["prompt_tokens"] = prompt }
            if let completion = final.completionTokens {
                props["completion_tokens"] = completion
            }
            if let cost = final.costUsd { props["cost_usd"] = cost }
            if let err = final.error { props["error"] = err }
        }
        return props
    }

    // MARK: - File IO (testable)

    /// Append a line + newline to a file, creating it if missing. Exposed
    /// (internal access via `internal`) so tests can call it on a temp file
    /// without going through the async queue.
    static func appendLine(_ line: String, to path: String) {
        guard let data = (line + "\n").data(using: .utf8) else { return }
        let fm = FileManager.default
        if fm.fileExists(atPath: path) {
            if let handle = try? FileHandle(forWritingTo: URL(fileURLWithPath: path)) {
                defer { try? handle.close() }
                do {
                    try handle.seekToEnd()
                    try handle.write(contentsOf: data)
                } catch {
                    // Best effort — never break the caller.
                }
            }
        } else {
            fm.createFile(atPath: path, contents: data)
        }
    }
}

// MARK: - Injectable dependencies

/// Thin wrapper around `PostHogManager.shared.track` so tests can swap in a
/// capture-only implementation without spinning up the PostHog SDK.
public protocol PostHogEmit: Sendable {
    @MainActor func track(_ eventName: String, properties: [String: Any])
}

public struct PostHogEmitLive: PostHogEmit {
    public init() {}
    @MainActor public func track(_ eventName: String, properties: [String: Any]) {
        PostHogManager.shared.track(eventName, properties: properties)
    }
}

public final class PostHogEmitCapture: PostHogEmit, @unchecked Sendable {
    public private(set) var events: [(String, [String: Any])] = []
    private let lock = NSLock()
    public init() {}
    @MainActor public func track(_ eventName: String, properties: [String: Any]) {
        lock.lock(); defer { lock.unlock() }
        events.append((eventName, properties))
    }
}

/// Thin wrapper around the file logger so tests can capture the error log
/// without polluting the real /tmp/omi.log.
public protocol StandardLog: Sendable {
    @MainActor func log(_ message: String)
}

public struct StandardLogLive: StandardLog {
    public init() {}
    @MainActor public func log(_ message: String) {
        log(message)
    }
}

public final class StandardLogCapture: StandardLog, @unchecked Sendable {
    public private(set) var messages: [String] = []
    private let lock = NSLock()
    public init() {}
    @MainActor public func log(_ message: String) {
        lock.lock(); defer { lock.unlock() }
        messages.append(message)
    }
}
