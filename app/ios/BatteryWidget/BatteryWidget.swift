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
            BatteryWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("Omi Battery")
        .description("Shows your Omi device's charge, and on the Lock Screen its mic state.")
        .supportedFamilies([.systemSmall, .accessoryRectangular, .accessoryCircular])
    }
}

// MARK: - Widget Entry View

struct BatteryWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    var entry: BatteryEntry

    var body: some View {
        switch family {
        case .systemSmall:
            SmallBatteryView(info: entry.info).widgetBackground(SmallBatteryView.background)
        case .accessoryCircular:
            AccessoryCircularView(info: entry.info).widgetBackground(.clear, accessory: true)
        default:
            AccessoryRectangularView(info: entry.info).widgetBackground(.clear, accessory: true)
        }
    }
}

extension View {
    /// The widget's container background on iOS 17+ (the system fill for Lock Screen accessories);
    /// earlier systems draw [color] behind the view.
    @ViewBuilder
    func widgetBackground(_ color: Color, accessory: Bool = false) -> some View {
        if #available(iOS 17.0, *) {
            if accessory {
                containerBackground(.fill.tertiary, for: .widget)
            } else {
                containerBackground(color, for: .widget)
            }
        } else if accessory {
            self
        } else {
            padding(16).frame(maxWidth: .infinity, maxHeight: .infinity).background(color)
        }
    }
}

// MARK: - Home Screen: Small (v2 HomeScreen "Battery")

/// The Omi's charge at a glance (v2 HomeScreen): the orb, "Battery", the level large, and the
/// device's state ("Omi · charging"). The orb's light is on while the device is connected.
struct SmallBatteryView: View {
    let info: DeviceBatteryInfo

    /// Liquid Dock card graphite in dark appearance, white in light.
    static let background = Color(UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 20 / 255, green: 23 / 255, blue: 29 / 255, alpha: 1)
            : UIColor.white
    })

    private var levelText: String {
        info.isConnected && info.batteryLevel >= 0 ? "\(info.batteryLevel)%" : "--%"
    }

    private var stateText: String {
        let name = info.deviceName.isEmpty ? "Omi" : info.deviceName
        if !info.isConnected { return "\(name) · not connected" }
        return info.isCharging ? "\(name) · charging" : name
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 4) {
                CapturePendant(active: info.isConnected, size: 40)
                Spacer(minLength: 0)
                Text("Battery")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(levelText)
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .foregroundStyle(info.isConnected ? .primary : .secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                if info.isConnected && info.isCharging {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }
            Text(stateText)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Omi battery \(levelText), \(stateText)"))
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

        let charging = BatteryEntry(
            date: Date(),
            info: DeviceBatteryInfo(
                deviceName: "Omi",
                batteryLevel: 42,
                deviceType: "omi",
                isConnected: true,
                lastUpdated: Date(),
                isMuted: false,
                isCharging: true
            )
        )

        Group {
            BatteryWidgetEntryView(entry: charging)
                .previewContext(WidgetPreviewContext(family: .systemSmall))
                .previewDisplayName("Small – Charging")
            BatteryWidgetEntryView(entry: disconnected)
                .previewContext(WidgetPreviewContext(family: .systemSmall))
                .previewDisplayName("Small – Disconnected")
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
