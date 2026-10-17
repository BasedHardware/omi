import Foundation
import Observation
import OmiPersistence

/// What capture, transcription and sync did, for Settings › Developer and the transcription log.
/// The last entries stay in memory; with `writesToFile` they also go to a daily JSON-lines file in
/// Documents (`omi_debug_YYYYMMDD.log`, Flutter's `debug_log_manager.dart` format) that can be shared.
@MainActor
@Observable
public final class DebugLog {
    public struct Entry: Identifiable, Hashable, Sendable {
        public enum Level: String, Sendable { case info = "INFO", warning = "WARN", error = "ERROR" }
        public let id: UUID
        public let date: Date
        public let level: Level
        /// `stt` (the transcription socket), `capture`, `sync` …
        public let source: String
        public let message: String
    }

    /// Newest last, at most `capacity`.
    public private(set) var entries: [Entry] = []
    /// Kept in `devLogsToFileEnabled`, which survives sign-out (as in Flutter).
    public var writesToFile: Bool {
        didSet { preferences?.set(writesToFile, for: .devLogsToFileEnabled) }
    }

    private let preferences: Preferences?
    private let capacity: Int
    private let directory: URL

    public init(preferences: Preferences?, directory: URL = URL.documentsDirectory, capacity: Int = 300) {
        self.preferences = preferences
        self.directory = directory
        self.capacity = capacity
        writesToFile = preferences?.bool(.devLogsToFileEnabled, default: false) ?? false
        removeOldFiles()
    }

    /// Files older than three days go (Flutter keeps the same).
    private func removeOldFiles() {
        let cutoff = Date.now.addingTimeInterval(-3 * 86400)
        for file in files {
            let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .now
            if modified < cutoff { try? FileManager.default.removeItem(at: file) }
        }
    }

    public func add(_ level: Entry.Level = .info, _ source: String, _ message: String) {
        let entry = Entry(id: UUID(), date: .now, level: level, source: source, message: message)
        entries.append(entry)
        if entries.count > capacity { entries.removeFirst(entries.count - capacity) }
        if writesToFile { append(entry) }
    }

    public func entries(from source: String) -> [Entry] {
        entries.filter { $0.source == source }
    }

    /// Log files on disk, newest first (only while writing to a file is or was on).
    public var files: [URL] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []
        return names.filter { $0.hasPrefix("omi_debug_") && $0.hasSuffix(".log") }.sorted(by: >).map { directory.appending(path: $0) }
    }

    /// Empties the memory and deletes the files.
    public func clear() {
        entries = []
        for file in files {
            try? FileManager.default.removeItem(at: file)
        }
    }

    /// One line per entry, oldest first: `[LEVEL] HH:mm:ss [source] message` (Flutter's copy format).
    public static func text(_ entries: [Entry]) -> String {
        entries.map { "[\($0.level.rawValue)] \($0.date.formatted(date: .omitted, time: .standard)) [\($0.source)] \($0.message)" }
            .joined(separator: "\n")
    }

    static let maxFileBytes = 5_000_000

    private func append(_ entry: Entry) {
        let day = entry.date.formatted(.iso8601.year().month().day().dateSeparator(.omitted))
        let url = directory.appending(path: "omi_debug_\(day).log")
        let object: [String: String] = [
            "ts": entry.date.formatted(.iso8601), "level": entry.level.rawValue, "message": "[\(entry.source)] \(entry.message)",
        ]
        guard var line = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return }
        line.append(0x0A)
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
        if size > Self.maxFileBytes { try? FileManager.default.removeItem(at: url) }
        if let handle = try? FileHandle(forWritingTo: url) {
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: line)
            try? handle.close()
        } else {
            try? line.write(to: url)
        }
    }
}
