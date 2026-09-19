import ContextCore
import Foundation

/// The dedicated Sentry project's configuration, read from explicit release inputs.
///
/// **This is the Context for Claude project's configuration, and never the Omi desktop app's.**
/// Crash diagnostics get their own Sentry project (`omi-nk3/context-for-claude`); sharing the Omi
/// app's project would mix two products' issue streams and, worse, would let this app's events be
/// mistaken for the other app's crashes in triage. The DSN is the only piece of configuration this
/// integration needs, and like the PostHog token in `AnalyticsSink` it is public by design: a DSN
/// can only write events into its own project, it reads nothing, and it is not an API key.
///
/// ## Where the DSN comes from
///
/// `Bundle.main`'s Info.plist, under the `ContextSentryDSN` key. That is a *release input*, not a
/// code constant on purpose: the provisioning state of the Sentry project is deployment
/// information, and baking it into a source file would mean a Swift edit per environment and a
/// placeholder DSN in every dev machine's binary. `scripts/build.sh` already injects the bundle
/// identifier and version into the copied plist with PlistBuddy; the release pipeline injects this
/// key the same way, from a CI secret. The template plist in this package carries no value at all.
///
/// There is deliberately **no runtime environment override**. A variable that could arm reporting
/// at runtime would be a second key that bypasses the shipping and Airgap gates, and `swift test`
/// proved with analytics that a process nobody considers production can look exactly like the
/// release (`ContextPaths.isShippingBundle` exists because the suite POSTed to PostHog for months).
/// Tests arm the integration through the same injected seam every other part of it uses; verifying
/// delivery end to end needs the shipping app, which is the one process allowed to report.
///
/// ## What "invalid" means, and why it must never throw
///
/// Anything missing, placeholder, or malformed resolves to `nil`, and `nil` means the SDK is never
/// started: no crash handler, no threads, no cache directory, no startup cost. The SDK's own DSN
/// parser would also refuse a malformed value, but it does so by logging and continuing with
/// reporting half-alive; refusing here first keeps "no valid config" and "reporting disabled" the
/// same state rather than two moods of it.
enum ContextSentryConfig {

    /// The Info.plist key the release pipeline sets. Absent in dev builds by design.
    static let plistKey = "ContextSentryDSN"

    /// The validated DSN for the dedicated project, or nil when reporting must stay disabled.
    static func dsn(reportedBy bundle: Bundle = .main) -> String? {
        let raw = bundle.object(forInfoDictionaryKey: plistKey) as? String
        return Self.dsn(raw)
    }

    /// The rule, over a stated string, so the whole refusal path is testable without a bundle.
    ///
    /// A DSN is `https://<publicKey>@<host>/<projectId>`. Every component is checked: an `http`
    /// DSN would ship crash payloads in cleartext, and a missing project id would send the SDK
    /// into its own fatal-path logging at start. Placeholders — the empty string the template
    /// could plausibly carry after a round-trip through tooling — are just invalid.
    static func dsn(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty,
              let url = URL(string: raw),
              url.scheme?.lowercased() == "https",
              let host = url.host, !host.isEmpty,
              url.user != nil, !url.user!.isEmpty,
              let projectId = url.path.split(separator: "/").last,
              projectId.allSatisfy(\.isNumber)
        else { return nil }
        return raw
    }

    /// What every event reports itself as: `context-for-claude@1.2.3+1002003`.
    ///
    /// Sentry's `project@release` convention. The version mirrors the GitHub release tag this
    /// pipeline publishes (`context-for-claude-v<version>`), and `+{build}` carries the numeric
    /// Sparkle build number `release-micro-app.sh` derives, so every release is a distinct
    /// Sentry release and `dist` alone can slice further. The same identity is what the dSYM
    /// upload is associated with — see `docs/sentry.md`.
    static func releaseName(version: String, build: String) -> String {
        "context-for-claude@\(version)+\(build)"
    }

    /// Where the SDK keeps its state — and the directory an Airgap transition deletes.
    ///
    /// **Every byte the SDK writes, including the native crash envelopes it stores for the next
    /// launch, lands under this one root** (`<root>/io.sentry/<dsn-hash>/…`). Pointing it into the
    /// app's own `0o700` support directory is what makes strict Airgap drop semantics possible
    /// through supported API: the SDK has no public purge, but deleting a directory we configured
    /// is not SDK surgery. The default — somewhere in `~/Library/Caches` nobody audits — is
    /// exactly the property this integration must not have.
    static func cacheDirectory(inSupport support: URL = ContextPaths.supportDirectory) -> URL {
        support.appendingPathComponent("SentryCache", isDirectory: true)
    }

    /// Build identity, read once. `nil` components fall back to `"unknown"` so a release field is
    /// always present — an event without a release is an event release filters cannot find.
    static func releaseIdentity(of bundle: Bundle = .main) -> (releaseName: String, dist: String) {
        let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        return (
            releaseName: Self.releaseName(
                version: version.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown",
                build: build.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"),
            dist: build.flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
        )
    }
}
