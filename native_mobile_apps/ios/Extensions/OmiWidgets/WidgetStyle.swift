import SwiftUI
import WidgetKit

/// The app's palette (OmiDesign `DS.Palette`), repeated here so the extension stays small.
enum WidgetPalette {
    static let ink = Color(light: 0x000000, dark: 0xFFFFFF)
    static let inkSecondary = Color(light: 0x6C6C70, dark: 0xAEAEB2)
    static let inkTertiary = Color(light: 0x636366, dark: 0x8E8E93)
    static let card = Color(light: 0xFFFFFF, dark: 0x1C1C1E)
    static let agent = Color(light: 0x6B4EFF, dark: 0x9C8AFF)
    static let live = Color(light: 0xFF3B30, dark: 0xFF453A)
    static let success = Color(light: 0x34C759, dark: 0x30D158)
    static let warning = Color(light: 0xFF9500, dark: 0xFF9F0A)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: 1)
    }

    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            UIColor(Color(hex: traits.userInterfaceStyle == .dark ? dark : light))
        })
    }
}

/// The Omi mark: eight dots on a ring, as the app draws it.
struct OmiRingMark: View {
    let size: CGFloat
    var color: Color = WidgetPalette.ink

    var body: some View {
        let ring = size * 0.344
        let dot = size * (size < 40 ? 0.079 : 0.066)
        ZStack {
            ForEach(0 ..< 8, id: \.self) { index in
                let angle = -Double.pi / 2 + Double(index) * Double.pi / 4
                Circle()
                    .fill(color)
                    .frame(width: dot * 2, height: dot * 2)
                    .offset(x: ring * cos(angle), y: ring * sin(angle))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// Links into the app; `DeepLink(url:)` in the app reads them (`omi://task/<id>`, `omi://device`).
enum WidgetLink {
    static let device = URL(string: "omi://device")
    static let tasks = URL(string: "omi://tasks")
    static let home = URL(string: "omi://home")

    static func conversation(_ id: String) -> URL? {
        path("conversation", id)
    }

    static func task(_ id: String) -> URL? {
        path("task", id)
    }

    private static func path(_ kind: String, _ id: String) -> URL? {
        var components = URLComponents()
        components.scheme = "omi"
        components.host = kind
        components.path = "/" + id
        return components.url
    }
}

/// The battery symbol for a level, in quarters.
func batterySymbol(_ level: Int?) -> String {
    guard let level else { return "battery.0percent" }
    switch level {
    case ..<13: return "battery.0percent"
    case ..<38: return "battery.25percent"
    case ..<63: return "battery.50percent"
    case ..<88: return "battery.75percent"
    default: return "battery.100percent"
    }
}

/// When a task is due, as the widget says it at `now`: Overdue, today's time, Tomorrow, the
/// weekday this week, else the date. Nil for a task without a date.
func dueText(_ due: Date?, now: Date) -> Text? {
    guard let due else { return nil }
    let calendar = Calendar.current
    if due < now { return Text("Overdue") }
    if calendar.isDate(due, inSameDayAs: now) { return Text(due, style: .time) }
    if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(due, inSameDayAs: tomorrow) {
        return Text("Tomorrow")
    }
    if let week = calendar.date(byAdding: .day, value: 6, to: calendar.startOfDay(for: now)), due < week {
        return Text(due, format: .dateTime.weekday(.abbreviated))
    }
    return Text(due, format: .dateTime.month(.abbreviated).day())
}

/// The next midnight, when "today" and "tomorrow" move on.
func nextMidnight(after date: Date) -> Date {
    Calendar.current.nextDate(after: date, matching: DateComponents(hour: 0, minute: 0), matchingPolicy: .nextTime)
        ?? date.addingTimeInterval(3600)
}
