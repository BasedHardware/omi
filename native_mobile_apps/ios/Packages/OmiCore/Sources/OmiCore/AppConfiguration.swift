import Foundation

/// Build-time configuration, read once from Info.plist (values come from the xcconfig layer).
public struct AppConfiguration: Sendable, Equatable {
    /// Mirrors the Flutter app's `OMI_APP_PROFILE`.
    public enum Profile: String, Sendable {
        case localDev = "local_dev"
        case beta = "mobile_beta"
        case production
    }

    public let profile: Profile
    public let apiBaseURL: URL
    /// `host:port` of the Firebase Auth emulator; nil outside local development.
    public let authEmulator: (host: String, port: Int)?
    public let appVersion: String
    public let appBuild: String

    public init(
        profile: Profile,
        apiBaseURL: URL,
        authEmulator: (host: String, port: Int)?,
        appVersion: String,
        appBuild: String
    ) {
        self.profile = profile
        self.apiBaseURL = apiBaseURL
        self.authEmulator = authEmulator
        self.appVersion = appVersion
        self.appBuild = appBuild
    }

    public static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.profile == rhs.profile && lhs.apiBaseURL == rhs.apiBaseURL
            && lhs.authEmulator?.host == rhs.authEmulator?.host && lhs.authEmulator?.port == rhs.authEmulator?.port
            && lhs.appVersion == rhs.appVersion && lhs.appBuild == rhs.appBuild
    }

    public var isLocalDev: Bool {
        profile == .localDev
    }

    /// Reads the `Omi*` keys the xcconfig layer writes into Info.plist.
    public static func fromInfoDictionary(_ info: [String: Any]) -> AppConfiguration {
        let scheme = (info["OmiAPIScheme"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "https"
        let host = (info["OmiAPIHost"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "api.omi.me"
        let profile = Profile(rawValue: info["OmiAppProfile"] as? String ?? "") ?? .production
        let emulator = (info["OmiAuthEmulatorHost"] as? String).flatMap(parseHostPort)
        return AppConfiguration(
            profile: profile,
            apiBaseURL: URL(string: "\(scheme)://\(host)/")!,
            authEmulator: emulator,
            appVersion: info["CFBundleShortVersionString"] as? String ?? "0",
            appBuild: info["CFBundleVersion"] as? String ?? "0"
        )
    }

    static func parseHostPort(_ value: String) -> (host: String, port: Int)? {
        let parts = value.split(separator: ":")
        guard parts.count == 2, let port = Int(parts[1]), !parts[0].isEmpty else { return nil }
        return (String(parts[0]), port)
    }
}
