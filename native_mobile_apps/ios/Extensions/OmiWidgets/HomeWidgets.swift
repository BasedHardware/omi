import OmiExtras
import SwiftUI
import WidgetKit

// MARK: - Up next

struct UpNextEntry: TimelineEntry {
    let date: Date
    /// Nil until the app has published (signed out, or not opened since installing).
    let data: UpNextSnapshot?
}

struct UpNextProvider: TimelineProvider {
    static let sample = UpNextSnapshot(tasks: [
        .init(id: "a", title: String(localized: "Call the dentist"),
              due: Calendar.current.date(bySettingHour: 17, minute: 0, second: 0, of: .now)),
        .init(id: "b", title: String(localized: "Send the pricing draft"), due: .now.addingTimeInterval(-3600)),
        .init(id: "c", title: String(localized: "Book the flights"), due: nil),
    ], open: 5)

    func placeholder(in _: Context) -> UpNextEntry {
        UpNextEntry(date: .now, data: Self.sample)
    }

    func getSnapshot(in context: Context, completion: @escaping (UpNextEntry) -> Void) {
        let data = SharedStore.shared?.read(UpNextSnapshot.self, for: .upNext)
        completion(UpNextEntry(date: .now, data: data ?? (context.isPreview ? Self.sample : nil)))
    }

    func getTimeline(in _: Context, completion: @escaping (Timeline<UpNextEntry>) -> Void) {
        let now = Date.now
        let data = SharedStore.shared?.read(UpNextSnapshot.self, for: .upNext)
        // New entries when a shown task falls due (its time turns into Overdue) and at midnight;
        // the app reloads the timeline when the tasks change.
        var dates: Set<Date> = [now, nextMidnight(after: now)]
        for task in data?.tasks ?? [] {
            if let due = task.due, due > now { dates.insert(due) }
        }
        completion(Timeline(entries: dates.sorted().map { UpNextEntry(date: $0, data: data) }, policy: .atEnd))
    }
}

struct OmiUpNextWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: WidgetKind.upNext.rawValue, provider: UpNextProvider()) { entry in
            UpNextView(entry: entry)
                .widgetURL(WidgetLink.tasks)
                .containerBackground(WidgetPalette.card, for: .widget)
        }
        .configurationDisplayName("Up next")
        .description("Your next tasks from Omi.")
        .supportedFamilies([.systemMedium])
    }
}

/// The Omi mark, Up next and how many are open, then three tasks with when they are due.
struct UpNextView: View {
    let entry: UpNextEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                OmiRingMark(size: 16)
                Text("Up next")
                    .foregroundStyle(WidgetPalette.inkSecondary)
                Spacer(minLength: 4)
                if let open = entry.data?.open, open > 0 {
                    Text("\(open) open")
                        .foregroundStyle(WidgetPalette.inkTertiary)
                }
            }
            .font(.footnote.weight(.semibold))
            .lineLimit(1)
            .padding(.bottom, 4)

            if let data = entry.data, !data.tasks.isEmpty {
                ForEach(data.tasks.prefix(3)) { task in
                    row(task)
                }
                Spacer(minLength: 0)
            } else {
                Spacer(minLength: 0)
                Text(entry.data == nil ? "Open Omi to continue" : "All caught up")
                    .font(.subheadline)
                    .foregroundStyle(WidgetPalette.inkSecondary)
                    .frame(maxWidth: .infinity)
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func row(_ task: UpNextSnapshot.Task) -> some View {
        if let url = WidgetLink.task(task.id) {
            Link(destination: url) { rowContent(task) }
        } else {
            rowContent(task)
        }
    }

    private func rowContent(_ task: UpNextSnapshot.Task) -> some View {
        let overdue = task.due.map { $0 < entry.date } ?? false
        return HStack(spacing: 10) {
            Circle()
                .strokeBorder(WidgetPalette.inkTertiary, lineWidth: 1.5)
                .frame(width: 18, height: 18)
            Text(verbatim: task.title)
                .font(.subheadline)
                .foregroundStyle(WidgetPalette.ink)
                .lineLimit(1)
            Spacer(minLength: 4)
            if let due = dueText(task.due, now: entry.date) {
                due
                    .font(.footnote)
                    .monospacedDigit()
                    .foregroundStyle(overdue ? WidgetPalette.live : WidgetPalette.inkSecondary)
                    .lineLimit(1)
            }
        }
        .frame(maxHeight: 34)
    }
}

// MARK: - Latest conversation

struct LatestEntry: TimelineEntry {
    let date: Date
    let conversation: LatestSnapshot?
    /// The app has published (a nil conversation then means there is none yet).
    let known: Bool
}

struct LatestProvider: TimelineProvider {
    static let sample = LatestSnapshot(id: "", title: String(localized: "Planning the product launch"),
                                       at: .now.addingTimeInterval(-3600), taskCount: 2, duration: 840)

    private func current() -> LatestEntry {
        let store = SharedStore.shared
        return LatestEntry(
            date: .now,
            conversation: store?.read(LatestSnapshot.self, for: .latest),
            known: store?.isKnown(.latest) ?? false
        )
    }

    func placeholder(in _: Context) -> LatestEntry {
        LatestEntry(date: .now, conversation: Self.sample, known: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (LatestEntry) -> Void) {
        let entry = current()
        completion(entry.conversation == nil && context.isPreview ? placeholder(in: context) : entry)
    }

    func getTimeline(in _: Context, completion: @escaping (Timeline<LatestEntry>) -> Void) {
        let entry = current()
        // At midnight today's time becomes Yesterday; the app reloads after each conversation.
        let midnight = LatestEntry(date: nextMidnight(after: entry.date), conversation: entry.conversation, known: entry.known)
        completion(Timeline(entries: [entry, midnight], policy: .atEnd))
    }
}

struct OmiLatestWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: WidgetKind.latest.rawValue, provider: LatestProvider()) { entry in
            LatestView(entry: entry)
                .widgetURL(entry.conversation.flatMap { WidgetLink.conversation($0.id) } ?? WidgetLink.home)
                .containerBackground(WidgetPalette.card, for: .widget)
        }
        .configurationDisplayName("Latest")
        .description("Your latest conversation in Omi.")
        .supportedFamilies([.systemSmall])
    }
}

/// When it happened, its title in the serif, and its tasks and length.
struct LatestView: View {
    let entry: LatestEntry

    private var when: Text? {
        guard let at = entry.conversation?.at else { return nil }
        let calendar = Calendar.current
        if calendar.isDate(at, inSameDayAs: entry.date) { return Text(at, style: .time) }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: entry.date), calendar.isDate(at, inSameDayAs: yesterday) {
            return Text("Yesterday")
        }
        return Text(at, format: .dateTime.month(.abbreviated).day())
    }

    private var detail: Text? {
        guard let conversation = entry.conversation else { return nil }
        var parts: [Text] = []
        if conversation.taskCount > 0 { parts.append(Text("\(conversation.taskCount) tasks")) }
        if let duration = conversation.duration, duration >= 1 {
            let units: Set<Duration.UnitsFormatStyle.Unit> = duration >= 3600 ? [.hours, .minutes] : duration >= 60 ? [.minutes] :
                [.seconds]
            parts.append(Text(Duration.seconds(duration), format: .units(allowed: units, width: .abbreviated)))
        }
        guard let first = parts.first else { return nil }
        return parts.dropFirst().reduce(first) { $0 + Text(verbatim: " · ") + $1 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Group {
                if let when {
                    Text("Latest") + Text(verbatim: " · ") + when
                } else {
                    Text("Latest")
                }
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(WidgetPalette.inkSecondary)
            .lineLimit(1)
            Spacer(minLength: 6)
            if let conversation = entry.conversation {
                Group {
                    if conversation.title.isEmpty {
                        Text("Untitled conversation")
                    } else {
                        Text(verbatim: conversation.title)
                    }
                }
                .font(.system(size: 19, design: .serif))
                .foregroundStyle(WidgetPalette.ink)
                .lineLimit(3)
                .minimumScaleFactor(0.85)
                Spacer(minLength: 6)
                detail?
                    .font(.footnote)
                    .foregroundStyle(WidgetPalette.inkSecondary)
                    .lineLimit(1)
            } else {
                Text(entry.known ? "No conversations yet" : "Open Omi to continue")
                    .font(.subheadline)
                    .foregroundStyle(WidgetPalette.inkSecondary)
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

#Preview("Up next", as: .systemMedium) {
    OmiUpNextWidget()
} timeline: {
    UpNextEntry(date: .now, data: UpNextProvider.sample)
    UpNextEntry(date: .now, data: UpNextSnapshot(tasks: [], open: 0))
}

#Preview("Latest", as: .systemSmall) {
    OmiLatestWidget()
} timeline: {
    LatestEntry(date: .now, conversation: LatestProvider.sample, known: true)
}
