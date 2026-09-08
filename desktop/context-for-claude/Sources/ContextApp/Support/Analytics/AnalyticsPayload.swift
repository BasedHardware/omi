import ContextCore
import CryptoKit
import Foundation

/// Who this install is, for analytics only.
///
/// ## Not the backend's install id
///
/// `ClientDevice` already mints a per-install UUID and hashes it into `X-Device-Id-Hash`. This one is
/// derived from the same UUID under a **different salt**, and that separation is the point: the
/// backend id keys the user's own captured rows and is joinable to their account, so reusing it here
/// would make every anonymous analytics event trivially re-identifiable by anyone holding both
/// datasets. Salted separately, the two ids cannot be linked without the original UUID, which never
/// leaves the Mac.
///
/// Deriving rather than minting a second UUID is deliberate too: a second stored id is a second thing
/// that can be lost, and an id that resets makes every returning user look new — the exact failure
/// that makes a retention curve meaningless.
enum AnalyticsIdentity {

    /// The salt. Changing this string re-anonymises every install on the next launch and severs
    /// history — every existing user becomes a new user, and every retention curve restarts. Do not
    /// change it to "clean up" identity.
    private static let salt = "context-for-claude/analytics/v1"

    /// `cfc_` + 16 hex characters of salted SHA-256.
    ///
    /// The prefix keeps these ids from ever colliding with, or being mistaken for, the Firebase uids
    /// the Omi app sends as `distinct_id` into the same PostHog project — a shared project means a
    /// shared id space, and two products silently sharing a person record would corrupt both.
    static let distinctID: String = derive(from: ClientDevice.installId(in: .standard))

    static func derive(from installID: String) -> String {
        let digest = SHA256.hash(data: Data((salt + installID).utf8))
        return "cfc_" + digest.map { String(format: "%02x", $0) }.joined().prefix(16)
    }
}

/// One PostHog `capture` payload, built from an `AnalyticsEvent`.
///
/// Pure and synchronous so the entire wire format is testable without a network, a clock, or an app.
struct AnalyticsPayload: Sendable, Equatable {
    let name: String
    let distinctID: String
    let timestamp: Date
    let properties: [String: AnalyticsValue]

    /// Properties attached to every event, so a call site cannot forget them and no event is left
    /// unattributable to a build.
    ///
    /// **`$os_name` is deliberately absent, and must stay absent.** Omi's macOS retention,
    /// activation and weekly-actives queries — in `web/admin/app/api/omi/stats/` and in the
    /// analytics runbook — all scope on `properties.$os_name = 'macOS'`. Setting it here would
    /// enrol every Context for Claude install into the Omi macOS numbers, which is both wrong and
    /// almost undetectable after the fact. `macos_version` carries the same information under a name
    /// nothing else queries. `AnalyticsPayloadTests.testPayloadNeverSetsDollarOSName` pins this.
    static func superProperties(
        version: String,
        build: String,
        macOSVersion: String
    ) -> [String: AnalyticsValue] {
        [
            // The discriminator every query on this project should filter by. Belt and braces with
            // the `cfc_` event-name prefix: either one alone would keep the two products apart, and
            // whichever a future query author reaches for first, it works.
            "app": .string("context-for-claude"),
            "app_version": .string(version),
            "app_build": .string(build),
            "macos_version": .string(macOSVersion),
        ]
    }

    init(
        event: AnalyticsEvent,
        distinctID: String,
        timestamp: Date,
        superProperties: [String: AnalyticsValue]
    ) {
        self.name = event.name
        self.distinctID = distinctID
        self.timestamp = timestamp
        // Super-properties first so an event can never overwrite its own build identity.
        self.properties = superProperties.merging(event.properties) { _, eventValue in eventValue }
    }

    /// The JSON body PostHog's `/batch` endpoint expects for one event.
    var json: [String: Any] {
        var properties = self.properties.mapValues(\.json)
        properties["distinct_id"] = distinctID
        return [
            "event": name,
            "properties": properties,
            "timestamp": ISO8601DateFormatter.analytics.string(from: timestamp),
        ]
    }
}

extension ISO8601DateFormatter {
    /// PostHog accepts ISO-8601; fixing the formatter here keeps every event's timestamp in one
    /// format regardless of the machine's locale or calendar settings.
    static let analytics: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()
}
