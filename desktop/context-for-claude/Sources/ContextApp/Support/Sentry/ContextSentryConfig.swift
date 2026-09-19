import ContextCore
import Foundation

/// Dedicated CFC project configuration. Release packaging must supply the Info.plist value;
/// there is no Omi DSN fallback or runtime environment override.
enum ContextSentryConfig {
    static let plistKey = "ContextSentryDSN"

    static func dsn(reportedBy bundle: Bundle = .main) -> String? {
        dsn(bundle.object(forInfoDictionaryKey: plistKey) as? String)
    }

    static func dsn(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
            let url = URL(string: raw),
            url.scheme?.lowercased() == "https",
            let host = url.host, !host.isEmpty,
            let key = url.user, !key.isEmpty,
            url.password == nil, url.query == nil, url.fragment == nil,
            let project = url.path.split(separator: "/").last,
            project.utf8.allSatisfy({ (48...57).contains($0) })
        else { return nil }
        return raw
    }

    static func releaseName(version: String, build: String) -> String {
        "context-for-claude@\(version)+\(build)"
    }

    /// Parent of the generation-specific SDK caches. Only the persisted current generation is
    /// reopened; Airgap cleanup is confined to this app-owned tree.
    static func cacheDirectory(inSupport support: URL = ContextPaths.supportDirectory) -> URL {
        support.appendingPathComponent("SentryCache", isDirectory: true)
    }

    static func releaseIdentity(of bundle: Bundle = .main) -> (releaseName: String, dist: String) {
        let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        return (
            releaseName: releaseName(
                version: version.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown",
                build: build.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"),
            dist: build.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
        )
    }
}
