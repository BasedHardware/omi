import Foundation
import OmiNetwork

/// The plain facts behind the top of Settings (the profile header and its four tiles) and the
/// status line on My Omi, kept free of views so they can be tested: who is signed in, what the
/// Omi is doing, how much of the plan is used, how many apps and people there are.
public enum SettingsHub {
    /// What the Omi is doing, for the Settings tile, My Omi's status line and its dot.
    public enum OmiState: Equatable, Sendable {
        /// No Omi was ever paired.
        case none
        case notConnected
        case connecting
        /// Connected and sending audio (`listening`), connected but paused, or connected and idle.
        case connected(battery: Int?, activity: Activity)

        public enum Activity: Equatable, Sendable { case idle, listening, paused }

        /// The dot beside the pendant: red while listening, green while connected, gray otherwise.
        public enum Dot: Equatable, Sendable { case live, connected, off }

        public var dot: Dot {
            switch self {
            case .connected(_, .listening): .live
            case .connected: .connected
            case .none, .notConnected, .connecting: .off
            }
        }

        public var isConnected: Bool {
            if case .connected = self { true } else { false }
        }

        public var battery: Int? {
            if case let .connected(battery, _) = self { battery } else { nil }
        }
    }

    public static func omiState(
        isPaired: Bool, connection: DeviceStore.Connection, battery: Int?, isMuted: Bool, isListening: Bool
    ) -> OmiState {
        guard isPaired else { return .none }
        switch connection {
        case .disconnected: return .notConnected
        case .connecting: return .connecting
        case .connected:
            let activity: OmiState.Activity = isMuted ? .paused : isListening ? .listening : .idle
            return .connected(battery: battery, activity: activity)
        }
    }

    /// One or two letters for the avatar: the name's initials ("Ada Lovelace" → "LS"); without a
    /// name the email's first letter ("ada@…" → "A"); "?" only when neither is known.
    public static func initials(name: String?, email: String?) -> String {
        let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty {
            let words = trimmed.split(whereSeparator: { $0 == " " || $0 == "-" || $0 == "." || $0 == "@" }).prefix(2)
            let letters = words.compactMap(\.first).filter(\.isLetter).map { String($0).uppercased() }.joined()
            if !letters.isEmpty { return letters }
        }
        if let first = email?.trimmingCharacters(in: .whitespaces).first(where: \.isLetter) {
            return String(first).uppercased()
        }
        return "?"
    }

    /// The name shown on top of Settings: the account's name, else the part of the email before
    /// the "@" ("ada@…" → "ada"), never a placeholder word.
    public static func headline(name: String?, email: String?) -> String? {
        if let name = name?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty { return name }
        guard let local = email?.split(separator: "@").first, !local.isEmpty else { return nil }
        return String(local)
    }

    /// The limit closest to running out (the Plan tile's meter); nil when every meter is unlimited.
    public static func busiestMeter(_ meters: [UsageMeter]) -> UsageMeter? {
        meters.filter { $0.fraction != nil }.max { ($0.fraction ?? 0) < ($1.fraction ?? 0) }
    }

    /// Whole percent of a 0…1 share, rounded down below 100 so "100%" means the limit is reached.
    public static func percent(_ fraction: Double) -> Int {
        let value = Int((min(1, max(0, fraction)) * 100).rounded())
        return fraction < 1 ? min(99, value) : 100
    }

    /// The free plan: the header offers Upgrade.
    public static func isFree(_ subscription: Subscription) -> Bool {
        !subscription.isPaid
    }

    /// Connected apps for the Apps tile: calendar, mail and task apps, plus Apple Health and
    /// Reminders when they are on (the "Connected" group of Apps & integrations).
    public static func connectedApps(_ integrations: [Integration], health: Bool, reminders: Bool) -> Int {
        integrations.count(where: \.isConnected) + (health ? 1 : 0) + (reminders ? 1 : 0)
    }
}
