import WidgetKit
import SwiftUI

// MARK: - Timeline Entry

struct BatteryEntry: TimelineEntry {
    let date: Date
    let info: DeviceBatteryInfo
}

// MARK: - Timeline Provider

struct BatteryTimelineProvider: TimelineProvider {
    func placeholder(in context: Context) -> BatteryEntry {
        BatteryEntry(
            date: Date(),
            info: DeviceBatteryInfo(
                deviceName: "Omi",
                batteryLevel: 85,
                deviceType: "omi",
                isConnected: true,
                lastUpdated: Date(),
                isMuted: false
            )
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (BatteryEntry) -> Void) {
        completion(BatteryEntry(date: Date(), info: DeviceBatteryInfo.fromSharedDefaults()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BatteryEntry>) -> Void) {
        let info = DeviceBatteryInfo.fromSharedDefaults()
        let entry = BatteryEntry(date: Date(), info: info)
        // 5-minute fallback refresh; the app pushes instant updates via
        // WidgetCenter.shared.reloadAllTimelines on battery or mute state changes.
        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 5, to: Date())!
        completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
    }
}

// MARK: - Widget Definition

struct OmiBatteryWidget: Widget {
    let kind: String = "OmiBatteryWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BatteryTimelineProvider()) { entry in
            if #available(iOS 17.0, *) {
                BatteryWidgetEntryView(entry: entry)
                    .containerBackground(.fill.tertiary, for: .widget)
            } else {
                BatteryWidgetEntryView(entry: entry)
            }
        }
        .configurationDisplayName("Omi Battery")
        .description("Shows your Omi device battery level and mic state.")
        .supportedFamilies([.accessoryRectangular, .accessoryCircular])
    }
}

// MARK: - Widget Entry View

struct BatteryWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    var entry: BatteryEntry

    var body: some View {
        switch family {
        case .accessoryCircular:
            AccessoryCircularView(info: entry.info)
        default:
            AccessoryRectangularView(info: entry.info)
        }
    }
}

// MARK: - Lock Screen: Rectangular

struct AccessoryRectangularView: View {
    let info: DeviceBatteryInfo

    var body: some View {
        HStack(spacing: 0) {
            // Left — Omi logo
            Image("omi-logo")
                .resizable()
                .renderingMode(.template)
                .scaledToFit()
                .frame(width: 36, height: 36)
                .foregroundColor(.primary)

            Spacer(minLength: 4)

            if info.isConnected {
                // Center — battery %
                Group {
                    if info.batteryLevel >= 0 {
                        Text("\(info.batteryLevel)%")
                    } else {
                        Text("--%")
                            .foregroundColor(.secondary)
                    }
                }
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.6)

                Spacer(minLength: 4)

                // Right — mute state
                Image(systemName: info.isMuted ? "mic.slash.fill" : "mic.fill")
                    .font(.system(size: 22, weight: .medium))
                    .foregroundColor(info.isMuted ? Color(red: 1.0, green: 0.23, blue: 0.19) : .primary)
                    .frame(width: 36)
            } else {
                // Disconnected
                Text("Connect\ndevice")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(.white.opacity(0.25))
        )
    }
}

// MARK: - Lock Screen: Circular (compact 1×1)

struct AccessoryCircularView: View {
    let info: DeviceBatteryInfo

    var body: some View {
        let text = (info.isConnected && info.batteryLevel >= 0)
            ? "\(info.batteryLevel)%"
            : "--"
        Text(text)
            .font(.system(size: 20, weight: .bold, design: .rounded))
            .minimumScaleFactor(0.5)
            .lineLimit(1)
            .widgetAccentable()
    }
}

// MARK: - Previews

#if DEBUG
struct OmiBatteryWidget_Previews: PreviewProvider {
    static var previews: some View {
        let connected = BatteryEntry(
            date: Date(),
            info: DeviceBatteryInfo(
                deviceName: "Omi DevKit",
                batteryLevel: 98,
                deviceType: "omi",
                isConnected: true,
                lastUpdated: Date(),
                isMuted: false
            )
        )
        let muted = BatteryEntry(
            date: Date(),
            info: DeviceBatteryInfo(
                deviceName: "Omi",
                batteryLevel: 72,
                deviceType: "omi",
                isConnected: true,
                lastUpdated: Date(),
                isMuted: true
            )
        )
        let disconnected = BatteryEntry(
            date: Date(),
            info: DeviceBatteryInfo(
                deviceName: "Omi",
                batteryLevel: -1,
                deviceType: "omi",
                isConnected: false,
                lastUpdated: Date.distantPast,
                isMuted: false
            )
        )

        Group {
            BatteryWidgetEntryView(entry: connected)
                .previewContext(WidgetPreviewContext(family: .accessoryRectangular))
                .previewDisplayName("Rectangular – Connected")
            BatteryWidgetEntryView(entry: muted)
                .previewContext(WidgetPreviewContext(family: .accessoryRectangular))
                .previewDisplayName("Rectangular – Muted")
            BatteryWidgetEntryView(entry: disconnected)
                .previewContext(WidgetPreviewContext(family: .accessoryRectangular))
                .previewDisplayName("Rectangular – Disconnected")
            BatteryWidgetEntryView(entry: connected)
                .previewContext(WidgetPreviewContext(family: .accessoryInline))
                .previewDisplayName("Inline")
        }
    }
}
#endif
