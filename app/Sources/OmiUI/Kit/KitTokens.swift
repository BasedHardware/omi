import Foundation
import Foundation
import OmiKit
import SwiftUI

// Shared kit tokens and formatting, ported from `react-native/src/mobile/mobileTokens.ts`
// and the projection formatting helpers of `react-native/src/ui/`. The desktop
// tokens already live in `../Tokens.swift`; these are the mobile-plane values
// plus the pure date/duration formatters both surfaces consume.

public enum MobilePalette {
    public nonisolated(unsafe) static let background = OmiColor.hex(0x0F0F0F)
    public nonisolated(unsafe) static let surface = OmiColor.hex(0x1A1A1A)
    public nonisolated(unsafe) static let surfaceRaised = OmiColor.hex(0x252622)
    public nonisolated(unsafe) static let surfaceQuiet = OmiColor.hex(0x151613)
    public nonisolated(unsafe) static let border = OmiColor.hex(0x343630)
    public nonisolated(unsafe) static let text = Color.white
    public nonisolated(unsafe) static let textMuted = OmiColor.hex(0xB5B8AF)
    public nonisolated(unsafe) static let textSubtle = OmiColor.hex(0x92968B)
    public nonisolated(unsafe) static let accent = Color.white
    public nonisolated(unsafe) static let recording = OmiColor.hex(0xFF5A62)
    public nonisolated(unsafe) static let connected = OmiColor.hex(0x10B981)
    public nonisolated(unsafe) static let warning = OmiColor.hex(0xF0B56D)
    /// The translucent omnibar field: `rgba(26, 26, 26, 0.88)`.
    public nonisolated(unsafe) static let omnibarField = Color(
        red: 26.0 / 255.0, green: 26.0 / 255.0, blue: 26.0 / 255.0, opacity: 0.88
    )
}

public enum MobileSpace {
    public nonisolated(unsafe) static let xs: CGFloat = 6
    public nonisolated(unsafe) static let sm: CGFloat = 10
    public nonisolated(unsafe) static let md: CGFloat = 16
    public nonisolated(unsafe) static let lg: CGFloat = 20
    public nonisolated(unsafe) static let xl: CGFloat = 28
    public nonisolated(unsafe) static let xxl: CGFloat = 36
}

public enum MobileRadius {
    public nonisolated(unsafe) static let sm: CGFloat = 12
    public nonisolated(unsafe) static let md: CGFloat = 16
    public nonisolated(unsafe) static let lg: CGFloat = 22
    public nonisolated(unsafe) static let chip: CGFloat = 16
    public nonisolated(unsafe) static let round: CGFloat = 18
}

public enum MobileType {
    public nonisolated(unsafe) static let caption = TypeStyle(
        size: 13, lineHeight: 18, weight: .medium
    )
    public nonisolated(unsafe) static let body = TypeStyle(
        size: 17, lineHeight: 24, weight: .regular
    )
    public nonisolated(unsafe) static let title = TypeStyle(
        size: 22, lineHeight: 28, weight: .semibold
    )
}

/// Motion feel ported from the RN springs: quick press feedback and a soft
/// slide for route/selection changes. Reduce-motion callers pass `nil`.
public enum KitMotion {
    public nonisolated(unsafe) static let press = Animation.easeOut(duration: 0.15)
    public nonisolated(unsafe) static let slide = Animation.spring(
        response: 0.4, dampingFraction: 0.85
    )
    public nonisolated(unsafe) static let breathe = Animation.easeInOut(duration: 4.0)
}

// MARK: - Formatting (ports of the ui/ date + duration helpers)

public enum KitFormat {
    /// `formatConversationDate` — "Sep 28, 9:41 AM"; "Time unavailable" when
    /// the value is absent or undateable.
    public static func conversationDate(_ value: String?) -> String {
        guard let value, let seconds = ISO8601Reader.epochSeconds(value) else {
            return "Time unavailable"
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "MMM d, h:mm a"
        return formatter.string(from: Date(timeIntervalSince1970: seconds))
    }

    /// `formatConversationDuration` — "3 min" / "2 hr 5 min";
    /// "Duration unavailable" otherwise.
    public static func conversationDuration(startedAt: String?, finishedAt: String?) -> String {
        guard let startedAt, let finishedAt,
            let start = ISO8601Reader.epochSeconds(startedAt),
            let finish = ISO8601Reader.epochSeconds(finishedAt)
        else { return "Duration unavailable" }
        let duration = finish - start
        if duration < 0 { return "Duration unavailable" }
        let minutes = Int((duration / 60.0).rounded())
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        return remaining == 0 ? "\(hours) hr" : "\(hours) hr \(remaining) min"
    }

    /// Mobile task due date — "Sep 28" in UTC (mobileTokens TaskRow).
    public static func mobileTaskDue(_ milliseconds: Int64?) -> String? {
        guard let milliseconds else { return nil }
        return utcDateFormat("MMM d").string(
            from: Date(timeIntervalSince1970: Double(milliseconds) / 1000.0)
        )
    }

    /// Tasks page due copy — "No due date" / "28 Sep" (UTC day+month).
    public static func taskDue(_ milliseconds: Int64?) -> String {
        guard let milliseconds else { return "No due date" }
        return utcDateFormat("d MMM").string(
            from: Date(timeIntervalSince1970: Double(milliseconds) / 1000.0)
        )
    }

    /// Memory card date — "28 Sep 2026"; "Date unavailable" when nil.
    public static func memoryDate(_ seconds: Int64?) -> String {
        guard let seconds else { return "Date unavailable" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "d MMM yyyy"
        return formatter.string(from: Date(timeIntervalSince1970: Double(seconds)))
    }

    /// Chat transcript time — "9:41 AM".
    public static func chatTime(createdAt milliseconds: Int64) -> String {
        let normalized =
            milliseconds > 100_000_000_000 ? milliseconds : milliseconds * 1000
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "h:mm a"
        return formatter.string(
            from: Date(timeIntervalSince1970: Double(normalized) / 1000.0)
        )
    }

    /// Device captured time — the local `toLocaleString()` of a projection.
    public static func localDateTime(milliseconds: Int64) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy, h:mm a"
        return formatter.string(
            from: Date(timeIntervalSince1970: Double(milliseconds) / 1000.0)
        )
    }

    private static func utcDateFormat(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = format
        return formatter
    }
}

// MARK: - Shared state panel copy

/// `StatePanel` copy in `MobileAppSurface.tsx` — shared with the pages so the
/// loading/empty/offline/error vocabulary stays identical across surfaces.
public enum KitStateCopy {
    public static func panel(status: String, noun: String) -> String {
        if status == "loading" { return "Loading \(noun)…" }
        if status == "empty" {
            return noun == "tasks" ? "Nothing's waiting on you." : "No \(noun) yet"
        }
        if status == "offline" { return "Couldn’t refresh \(noun)" }
        return "Couldn’t load \(noun)"
    }
}
