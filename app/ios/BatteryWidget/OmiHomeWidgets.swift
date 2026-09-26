import AppIntents
import SwiftUI
import WidgetKit

// MARK: - Shared look

/// The app's v2 palette on the Home Screen, light and dark (OmiColors text tokens).
enum OmiWidgetPalette {
    static let label = dynamic(dark: 0xFFFFFF, light: 0x14171D)
    static let secondary = dynamic(dark: 0xA9AEB9, light: 0x5B6270)
    static let tertiary = dynamic(dark: 0x868B96, light: 0x6B7280)
    /// Liquid Dock card graphite in dark appearance, white in light.
    static let background = SmallBatteryView.background

    private static func dynamic(dark: UInt32, light: UInt32) -> Color {
        Color(UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255,
                           green: CGFloat((hex >> 8) & 0xFF) / 255,
                           blue: CGFloat(hex & 0xFF) / 255,
                           alpha: 1)
        })
    }
}

/// The Omi mark: eight dots on a ring, as the app draws it (OmiRingLogo).
struct OmiRingMark: View {
    let size: CGFloat
    var color: Color = OmiWidgetPalette.label

    var body: some View {
        let ring = size * 0.344
        let dot = size * (size < 40 ? 0.079 : 0.066)
        ZStack {
            ForEach(0..<8, id: \.self) { index in
                let angle = -Double.pi / 2 + Double(index) * Double.pi / 4
                Circle()
                    .fill(color)
                    .frame(width: dot * 2, height: dot * 2)
                    .offset(x: ring * CGFloat(cos(angle)), y: ring * CGFloat(sin(angle)))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// An Omi pendant as the app draws it (its orb): a dark sphere with the light near the top, lit
/// blue while connected.
struct WidgetPendantOrb: View {
    let active: Bool
    let size: CGFloat

    private static let led = Color(red: 0x4C / 255, green: 0x9B / 255, blue: 0xFF / 255)
    private static let ledOff = Color(red: 0x33 / 255, green: 0x38 / 255, blue: 0x42 / 255)

    var body: some View {
        let led = max(4, size * 0.13)
        ZStack {
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: Color(red: 0x7A / 255, green: 0x80 / 255, blue: 0x8A / 255), location: 0),
                    .init(color: Color(red: 0x40 / 255, green: 0x45 / 255, blue: 0x4E / 255), location: 0.20),
                    .init(color: Color(red: 0x1B / 255, green: 0x1E / 255, blue: 0x24 / 255), location: 0.52),
                    .init(color: Color(red: 0x0C / 255, green: 0x0D / 255, blue: 0x10 / 255), location: 0.80),
                    .init(color: Color(red: 0x08 / 255, green: 0x09 / 255, blue: 0x0B / 255), location: 1),
                ], center: UnitPoint(x: 0.68, y: 0.24), startRadius: 0, endRadius: size * 0.72))
                .overlay(Circle().strokeBorder(Color.white.opacity(0.25), lineWidth: 0.5))
            Group {
                if active {
                    Circle()
                        .fill(Self.led)
                        .shadow(color: Self.led.opacity(0.7), radius: 5)
                } else {
                    Circle().fill(Self.ledOff)
                }
            }
            .frame(width: led, height: led)
            .offset(y: -size * 0.18)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// A link into Omi: the widget extension's callback scheme, host "app", then the in-app route.
func omiWidgetURL(_ route: String) -> URL? {
    var components = URLComponents()
    components.scheme = Bundle.main.object(forInfoDictionaryKey: "OmiCaptureURLScheme") as? String ?? "omi"
    components.host = "app"
    components.path = route
    return components.url
}

/// When a task is due, as the widget says it at [now]: past due is Overdue, today the time,
/// tomorrow Tomorrow, this week the weekday, later the date. Nil for a task without a date.
func upNextDueText(_ due: Date?, now: Date) -> Text? {
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

// MARK: - Devices: switching between wearables

/// Tapping the page dots on the Devices widget shows the next wearable.
@available(iOS 17.0, *)
struct NextDeviceIntent: AppIntent {
    static var title: LocalizedStringResource = "Next device"
    static var isDiscoverable: Bool = false

    func perform() async throws -> some IntentResult {
        let devices = SharedWidgetStore.devices()
        guard devices.count > 1 else { return .result() }
        let next = devices[(SharedWidgetStore.selectedDevice(in: devices) + 1) % devices.count]
        SharedWidgetStore.defaults?.set(next.id, forKey: HomeWidgetKeys.selectedDevice)
        return .result()
    }
}

// MARK: - Up next (reminders)

struct UpNextEntry: TimelineEntry {
    let date: Date
    /// Nil until the app has published (signed out, or never opened since installing).
    let data: UpNextData?
}

struct UpNextProvider: TimelineProvider {
    static let sample = UpNextData(tasks: [
        UpNextTask(id: "a", title: "Call Chitapa", due: Calendar.current.date(bySettingHour: 17, minute: 0, second: 0, of: Date())?.timeIntervalSince1970),
        UpNextTask(id: "b", title: "Check the battery-drain reports", due: nil),
        UpNextTask(id: "c", title: "Send the pricing draft", due: Date().addingTimeInterval(-3600).timeIntervalSince1970),
    ], open: 3)

    func placeholder(in context: Context) -> UpNextEntry {
        UpNextEntry(date: Date(), data: Self.sample)
    }

    func getSnapshot(in context: Context, completion: @escaping (UpNextEntry) -> Void) {
        let data = SharedWidgetStore.read(UpNextData.self, key: HomeWidgetKeys.upNext)
        completion(UpNextEntry(date: Date(), data: data ?? (context.isPreview ? Self.sample : nil)))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<UpNextEntry>) -> Void) {
        let now = Date()
        let data = SharedWidgetStore.read(UpNextData.self, key: HomeWidgetKeys.upNext)
        // A new entry when a shown task falls due (its time turns into Overdue) and at midnight
        // (today's times and Tomorrow move on); the app reloads the timeline when tasks change.
        var dates: Set<Date> = [now]
        for task in data?.tasks.prefix(3) ?? [] {
            if let due = task.dueDate, due > now { dates.insert(due) }
        }
        if let midnight = Calendar.current.nextDate(after: now, matching: DateComponents(hour: 0, minute: 0),
                                                    matchingPolicy: .nextTime) {
            dates.insert(midnight)
        }
        let entries = dates.sorted().map { UpNextEntry(date: $0, data: data) }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

struct OmiUpNextWidget: Widget {
    let kind: String = "OmiUpNextWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: UpNextProvider()) { entry in
            UpNextEntryView(entry: entry)
        }
        .configurationDisplayName("Up next")
        .description("Your next tasks and reminders from Omi.")
        .supportedFamilies([.systemMedium, .accessoryRectangular, .accessoryInline])
    }
}

struct UpNextEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: UpNextEntry

    var body: some View {
        switch family {
        case .accessoryRectangular:
            UpNextLockScreenView(entry: entry)
                .widgetURL(omiWidgetURL("/action-items"))
                .widgetBackground(.clear, accessory: true)
        case .accessoryInline:
            UpNextInlineView(entry: entry)
                .widgetURL(omiWidgetURL("/action-items"))
                .widgetBackground(.clear, accessory: true)
        default:
            UpNextMediumView(entry: entry)
                .widgetURL(omiWidgetURL("/action-items"))
                .widgetBackground(OmiWidgetPalette.background)
        }
    }
}

/// v2 HomeScreen "Up next": the Omi mark, Up next and how many are open, then three tasks with
/// their due time ("5:00 PM", "Overdue"). Tapping opens To do.
struct UpNextMediumView: View {
    let entry: UpNextEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                OmiRingMark(size: 16)
                Text("Up next")
                    .foregroundStyle(OmiWidgetPalette.secondary)
                Spacer(minLength: 4)
                if let open = entry.data?.open, open > 0 {
                    Text("\(open) open")
                        .foregroundStyle(OmiWidgetPalette.tertiary)
                }
            }
            .font(.system(size: 13, weight: .semibold))
            .lineLimit(1)
            .frame(height: 18)

            if let data = entry.data, !data.tasks.isEmpty {
                ForEach(data.tasks.prefix(3), id: \.id) { task in
                    HStack(spacing: 10) {
                        Circle()
                            .strokeBorder(OmiWidgetPalette.tertiary, lineWidth: 1.5)
                            .frame(width: 20, height: 20)
                        Text(verbatim: task.title)
                            .font(.system(size: 15))
                            .foregroundStyle(OmiWidgetPalette.label)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        if let due = upNextDueText(task.dueDate, now: entry.date) {
                            due
                                .font(.system(size: 13))
                                .monospacedDigit()
                                .foregroundStyle(OmiWidgetPalette.secondary)
                                .lineLimit(1)
                        }
                    }
                    .frame(maxHeight: 36)
                }
                Spacer(minLength: 0)
            } else {
                Spacer(minLength: 0)
                Text(entry.data == nil ? "Open Omi to continue" : "All caught up")
                    .font(.system(size: 15))
                    .foregroundStyle(OmiWidgetPalette.secondary)
                    .frame(maxWidth: .infinity)
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

/// Lock Screen: Up next, then the first task and when it is due.
struct UpNextLockScreenView: View {
    let entry: UpNextEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 4) {
                OmiRingMark(size: 12, color: .primary)
                Text("Up next").font(.system(size: 13, weight: .semibold))
            }
            .widgetAccentable()
            if let first = entry.data?.tasks.first {
                Text(verbatim: first.title)
                    .font(.system(size: 15, weight: .semibold))
                    .lineLimit(1)
                    .privacySensitive()
                if let due = upNextDueText(first.dueDate, now: entry.date) {
                    due.font(.system(size: 13)).foregroundStyle(.secondary).lineLimit(1)
                }
            } else {
                Text(entry.data == nil ? "Open Omi to continue" : "All caught up")
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Lock Screen, above the clock: "Call Chitapa · 5:00 PM".
struct UpNextInlineView: View {
    let entry: UpNextEntry

    var body: some View {
        if let first = entry.data?.tasks.first {
            if let due = upNextDueText(first.dueDate, now: entry.date) {
                Text(verbatim: first.title) + Text(" · ") + due
            } else {
                Text(verbatim: first.title)
            }
        } else {
            Text(entry.data == nil ? "Open Omi to continue" : "All caught up")
        }
    }
}

// MARK: - Latest conversation

struct LatestEntry: TimelineEntry {
    let date: Date
    let conversation: LatestConversation?
    /// The app has published at least once (nil conversation then means there is none yet).
    let known: Bool
}

struct LatestProvider: TimelineProvider {
    static let sample = LatestConversation(id: "", title: "Call Chitapa reminder",
                                           at: Date().addingTimeInterval(-3600).timeIntervalSince1970,
                                           detail: "1 task · 14 s")

    private func current() -> LatestEntry {
        let known = SharedWidgetStore.defaults?.string(forKey: HomeWidgetKeys.latest) != nil
        return LatestEntry(date: Date(), conversation: SharedWidgetStore.read(LatestConversation.self, key: HomeWidgetKeys.latest),
                           known: known)
    }

    func placeholder(in context: Context) -> LatestEntry {
        LatestEntry(date: Date(), conversation: Self.sample, known: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (LatestEntry) -> Void) {
        let entry = current()
        completion(entry.conversation == nil && context.isPreview ? placeholder(in: context) : entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<LatestEntry>) -> Void) {
        let entry = current()
        // At midnight "3:14 PM" becomes "Yesterday"; the app reloads it after each conversation.
        let midnight = Calendar.current.nextDate(after: entry.date, matching: DateComponents(hour: 0, minute: 0),
                                                 matchingPolicy: .nextTime) ?? entry.date.addingTimeInterval(3600)
        completion(Timeline(entries: [entry, LatestEntry(date: midnight, conversation: entry.conversation, known: entry.known)],
                            policy: .atEnd))
    }
}

struct OmiLatestWidget: Widget {
    let kind: String = "OmiLatestWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: LatestProvider()) { entry in
            LatestSmallView(entry: entry)
                .widgetURL(omiWidgetURL(entry.conversation.map { "/conversation/\($0.id)" } ?? "/conversations"))
                .widgetBackground(OmiWidgetPalette.background)
        }
        .configurationDisplayName("Latest")
        .description("Your latest conversation in Omi.")
        .supportedFamilies([.systemSmall])
    }
}

/// v2 HomeScreen "Latest": when it happened, its title in the serif, and its tasks and length.
struct LatestSmallView: View {
    let entry: LatestEntry

    private var when: Text? {
        guard let at = entry.conversation?.date else { return nil }
        let calendar = Calendar.current
        if calendar.isDate(at, inSameDayAs: entry.date) { return Text(at, style: .time) }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: entry.date), calendar.isDate(at, inSameDayAs: yesterday) {
            return Text("Yesterday")
        }
        return Text(at, format: .dateTime.month(.abbreviated).day())
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Group {
                if let when {
                    Text("Latest") + Text(" · ") + when
                } else {
                    Text("Latest")
                }
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(OmiWidgetPalette.secondary)
            .lineLimit(1)
            Spacer(minLength: 6)
            if let conversation = entry.conversation {
                Text(verbatim: conversation.title)
                    .font(.system(size: 19, design: .serif))
                    .foregroundStyle(OmiWidgetPalette.label)
                    .lineLimit(3)
                    .minimumScaleFactor(0.85)
                Spacer(minLength: 6)
                Text(verbatim: conversation.detail)
                    .font(.system(size: 13))
                    .foregroundStyle(OmiWidgetPalette.secondary)
                    .lineLimit(1)
            } else {
                Text(entry.known ? "No conversations yet" : "Open Omi to continue")
                    .font(.system(size: 15))
                    .foregroundStyle(OmiWidgetPalette.secondary)
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}
