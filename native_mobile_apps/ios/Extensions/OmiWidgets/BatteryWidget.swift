import OmiExtras
import SwiftUI
import WidgetKit

struct BatteryEntry: TimelineEntry {
    let date: Date
    /// Nil when no Omi is paired (or the app has not published yet).
    let device: DeviceSnapshot?
}

struct BatteryProvider: TimelineProvider {
    static let sample = DeviceSnapshot(name: "Omi", connected: true, battery: 82)

    func placeholder(in _: Context) -> BatteryEntry {
        BatteryEntry(date: .now, device: Self.sample)
    }

    func getSnapshot(in context: Context, completion: @escaping (BatteryEntry) -> Void) {
        let device = SharedStore.shared?.read(DeviceSnapshot.self, for: .device)
        completion(BatteryEntry(date: .now, device: device ?? (context.isPreview ? Self.sample : nil)))
    }

    func getTimeline(in _: Context, completion: @escaping (Timeline<BatteryEntry>) -> Void) {
        let entry = BatteryEntry(date: .now, device: SharedStore.shared?.read(DeviceSnapshot.self, for: .device))
        // The app writes every level and reloads on what matters; this picks up the small steps.
        completion(Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(15 * 60))))
    }
}

struct OmiBatteryWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: WidgetKind.battery.rawValue, provider: BatteryProvider()) { entry in
            BatteryWidgetView(entry: entry)
                .widgetURL(WidgetLink.device)
        }
        .configurationDisplayName("Battery")
        .description("Your Omi's charge at a glance.")
        .supportedFamilies([.systemSmall, .accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}

struct BatteryWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: BatteryEntry

    private var level: Int? {
        entry.device.flatMap { $0.connected ? $0.battery : nil }
    }

    /// "82%", "82 %" in German.
    private func percent(_ level: Int) -> Text {
        Text(Double(level) / 100, format: .percent.precision(.fractionLength(0)))
    }

    private var name: String {
        entry.device?.name ?? "Omi"
    }

    var body: some View {
        switch family {
        case .accessoryCircular:
            circular.containerBackground(.fill.tertiary, for: .widget)
        case .accessoryRectangular:
            rectangular.containerBackground(.fill.tertiary, for: .widget)
        case .accessoryInline:
            inline.containerBackground(.clear, for: .widget)
        default:
            small.containerBackground(WidgetPalette.card, for: .widget)
        }
    }

    // MARK: Home Screen

    private var small: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top) {
                Image(entry.device?.connected == true ? "device-omi" : "device-omi-off")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 46, height: 46)
                    .accessibilityHidden(true)
                Spacer(minLength: 0)
                Text("Battery")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(WidgetPalette.inkSecondary)
            }
            Spacer(minLength: 0)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                (level.map(percent) ?? Text(verbatim: "—"))
                    .font(.system(size: 34, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(level == nil ? WidgetPalette.inkTertiary : WidgetPalette.ink)
                    .contentTransition(.numericText())
                if let level, level <= DeviceSnapshot.lowMark {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(WidgetPalette.live)
                        .accessibilityLabel(Text("Low battery"))
                }
            }
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            status
                .font(.footnote)
                .foregroundStyle(WidgetPalette.inkSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var status: Text {
        guard let device = entry.device else { return Text("No Omi paired") }
        return device.connected ? Text(verbatim: device.name) : Text(verbatim: device.name) + Text(verbatim: " · ") + Text("Not connected")
    }

    // MARK: Lock Screen

    private var circular: some View {
        Gauge(value: Double(level ?? 0), in: 0 ... 100) {
            OmiRingMark(size: 14, color: .primary)
        } currentValueLabel: {
            Text(verbatim: level.map(String.init) ?? "—")
                .monospacedDigit()
        }
        .gaugeStyle(.accessoryCircular)
        .widgetAccentable()
        .accessibilityLabel(Text(verbatim: name))
        .accessibilityValue(level.map(percent) ?? Text("Not connected"))
    }

    private var rectangular: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                OmiRingMark(size: 14, color: .primary)
                Text(verbatim: name)
                    .font(.headline)
                    .widgetAccentable()
                    .lineLimit(1)
            }
            if let level {
                percent(level)
                    .font(.system(.title2, design: .rounded).weight(.semibold))
                    .monospacedDigit()
                Gauge(value: Double(level), in: 0 ... 100) { EmptyView() }
                    .gaugeStyle(.accessoryLinearCapacity)
            } else {
                Text(entry.device == nil ? "No Omi paired" : "Not connected")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var inline: some View {
        Label {
            if let level {
                Text(verbatim: name + " ") + percent(level)
            } else {
                Text(verbatim: name) + Text(verbatim: " · ") + Text("Not connected")
            }
        } icon: {
            Image(systemName: batterySymbol(level))
        }
    }
}

#Preview("Small", as: .systemSmall) {
    OmiBatteryWidget()
} timeline: {
    BatteryEntry(date: .now, device: BatteryProvider.sample)
    BatteryEntry(date: .now, device: DeviceSnapshot(name: "Omi", connected: true, battery: 14))
    BatteryEntry(date: .now, device: DeviceSnapshot(name: "Omi", connected: false, battery: nil))
}

#Preview("Circular", as: .accessoryCircular) {
    OmiBatteryWidget()
} timeline: {
    BatteryEntry(date: .now, device: BatteryProvider.sample)
}
