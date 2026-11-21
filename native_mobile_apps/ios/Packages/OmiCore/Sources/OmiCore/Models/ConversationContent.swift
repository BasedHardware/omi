import Foundation

/// A calendar meeting Omi did not capture (`GET v1/calendar/capture-gaps`): accepted, timed, and
/// no kept conversation overlaps it.
public struct CaptureGap: Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let start: Date
    public let end: Date

    public init(id: String, title: String, start: Date, end: Date) {
        self.id = id
        self.title = title
        self.start = start
        self.end = end
    }

    /// The gaps by local day (start of day), each day's in time order.
    public static func byDay(_ gaps: [CaptureGap], calendar: Calendar = .current) -> [Date: [CaptureGap]] {
        Dictionary(grouping: gaps) { calendar.startOfDay(for: $0.start) }.mapValues { $0.sorted { $0.start < $1.start } }
    }
}

/// A folder as the editor fills it in: name, emoji, color (`#RRGGBB`), description.
public struct FolderDraft: Hashable, Sendable {
    public var name: String
    public var icon: String
    public var color: String
    public var description: String

    public init(name: String = "", icon: String = "📁", color: String = FolderDraft.colors[0], description: String = "") {
        self.name = name
        self.icon = icon
        self.color = color
        self.description = description
    }

    /// The name and description without surrounding spaces; `nil` when the name is empty.
    public var trimmed: FolderDraft? {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        return FolderDraft(name: name, icon: icon, color: color, description: description.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// The Flutter app's folder colors (`folderColors`), in its order.
    public static let colors = [
        "#3B82F6", "#EF4444", "#10B981", "#8B5CF6", "#F59E0B", "#06B6D4", "#EC4899", "#6366F1", "#F97316", "#6B7280",
    ]

    /// The Flutter app's folder emoji (`folderIconStrings`), in its order.
    public static let icons = [
        "📁", "💼", "🏠", "📚", "👨‍👩‍👧‍👦", "❤️", "🎮", "✈️", "🏥", "🛒", "💰", "🎵", "🎨", "📝", "💬", "🌎", "🛠️", "🍔", "🏆", "🔒",
    ]
}
