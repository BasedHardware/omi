import Foundation

/// Every on-disk location the app and the MCP server agree on.
///
/// Deliberately independent of the Omi desktop app's own support directory — Earshot never reads or
/// writes Omi's data, and Omi never sees Earshot's.
public enum EarshotPaths {
    public static let bundleIdentifier = "com.omi.earshot"

    /// `~/Library/Application Support/Earshot`
    public static var supportDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("Earshot", isDirectory: true)
    }

    /// `~/Library/Application Support/Earshot/earshot.db`
    public static var databaseURL: URL {
        supportDirectory.appendingPathComponent("earshot.db")
    }

    /// Where screen JPEGs live, one directory per day.
    public static var framesDirectory: URL {
        supportDirectory.appendingPathComponent("Frames", isDirectory: true)
    }

    public static func framesDirectory(for epoch: Double) -> URL {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return framesDirectory.appendingPathComponent(f.string(from: Date(timeIntervalSince1970: epoch)), isDirectory: true)
    }

    /// Written by the app so the MCP server can report live capture state without an IPC channel.
    public static var heartbeatURL: URL {
        supportDirectory.appendingPathComponent("capture-state.json")
    }

    @discardableResult
    public static func ensureSupportDirectory() throws -> URL {
        let dir = supportDirectory
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
}

/// The app writes this; `earshot-mcp` reads it. A file rather than a socket because the MCP server
/// is spawned per Claude session and must work whether or not the app happens to be running.
public struct CaptureState: Codable, Sendable, Equatable {
    public var capturing: Bool
    public var pausedReason: String?
    public var capabilities: [CapabilityReport]
    public var updatedAt: Double

    public init(
        capturing: Bool,
        pausedReason: String? = nil,
        capabilities: [CapabilityReport] = [],
        updatedAt: Double = EarshotTime.now
    ) {
        self.capturing = capturing
        self.pausedReason = pausedReason
        self.capabilities = capabilities
        self.updatedAt = updatedAt
    }

    /// Considered live only if the app touched it recently; otherwise the app is not running.
    public static let stalenessSeconds: Double = 90

    public var isStale: Bool { EarshotTime.now - updatedAt > Self.stalenessSeconds }

    public func write(to url: URL = EarshotPaths.heartbeatURL) throws {
        try EarshotPaths.ensureSupportDirectory()
        let data = try JSONEncoder().encode(self)
        try data.write(to: url, options: .atomic)
    }

    public static func read(from url: URL = EarshotPaths.heartbeatURL) -> CaptureState? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(CaptureState.self, from: data)
    }
}
