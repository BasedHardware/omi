import WidgetKit
import SwiftUI

// MARK: - Timeline Entry

struct BatteryEntry: TimelineEntry {
    let date: Date
    let info: DeviceBatteryInfo
    /// The wearables the Home Screen widget pages through (never the phone), and the one shown.
    var devices: [WidgetDevice] = []
    var selected: Int = 0
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
            ),
            devices: [WidgetDevice(id: "omi", name: "Omi", image: "pendant", connected: true, battery: 85, charging: false)]
        )
    }

    private func current() -> BatteryEntry {
        let devices = SharedWidgetStore.devices()
        return BatteryEntry(date: Date(), info: DeviceBatteryInfo.fromSharedDefaults(), devices: devices,
                            selected: SharedWidgetStore.selectedDevice(in: devices))
    }

    func getSnapshot(in context: Context, completion: @escaping (BatteryEntry) -> Void) {
        completion(current())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BatteryEntry>) -> Void) {
        let entry = current()
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
        .configurationDisplayName("Battery")
        .description("Your devices' charge; tap the dots to switch devices. On the Lock Screen, the mic state.")
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
            SmallBatteryView(devices: entry.devices, selected: entry.selected)
                .widgetURL(omiWidgetURL("/settings/device"))
                .widgetBackground(SmallBatteryView.background)
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

/// Each wearable's charge at a glance (v2 HomeScreen): its picture (the orb for an Omi pendant,
/// its light on while connected), "Battery", the level large, and its state ("Omi · charging").
/// With more than one device, page dots show which it is; tapping them shows the next (iOS 17).
/// The phone is never a device here.
struct SmallBatteryView: View {
    let devices: [WidgetDevice]
    let selected: Int

    /// Liquid Dock card graphite in dark appearance, white in light.
    static let background = Color(UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 20 / 255, green: 23 / 255, blue: 29 / 255, alpha: 1)
            : UIColor.white
    })

    private var device: WidgetDevice? { devices.indices.contains(selected) ? devices[selected] : devices.first }

    private var levelText: String {
        guard let device, device.connected, device.battery >= 0 else { return "--%" }
        return "\(device.battery)%"
    }

    private var stateText: Text {
        guard let device else { return Text("Open Omi to continue") }
        let name = Text(verbatim: device.name.isEmpty ? "Omi" : device.name)
        if !device.connected { return name + Text(" · ") + Text("disconnected") }
        return device.charging ? name + Text(" · ") + Text("charging") : name
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 4) {
                DevicePicture(device: device, size: 44)
                Spacer(minLength: 0)
                VStack(alignment: .trailing, spacing: 8) {
                    Text("Battery")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(OmiWidgetPalette.secondary)
                    if devices.count > 1 { pageDots }
                }
            }
            Spacer(minLength: 0)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(levelText)
                    .font(.system(size: 30, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(device?.connected == true ? OmiWidgetPalette.label : OmiWidgetPalette.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                if device?.connected == true && device?.charging == true {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(OmiWidgetPalette.secondary)
                }
            }
            stateText
                .font(.system(size: 13))
                .foregroundStyle(OmiWidgetPalette.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    /// One dot per device, the shown one lit. A tap shows the next device.
    @ViewBuilder
    private var pageDots: some View {
        let dots = HStack(spacing: 5) {
            ForEach(devices.indices, id: \.self) { index in
                Circle()
                    .fill(index == selected ? OmiWidgetPalette.label : OmiWidgetPalette.tertiary.opacity(0.45))
                    .frame(width: 6, height: 6)
            }
        }
        if #available(iOS 17.0, *) {
            Button(intent: NextDeviceIntent()) {
                dots.padding(.vertical, 8).padding(.leading, 12).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text(verbatim: devices[(selected + 1) % devices.count].name))
        } else {
            dots.accessibilityHidden(true)
        }
    }
}

/// A wearable's own picture: the orb for an Omi pendant (its light on while connected), the
/// product photo for the rest; dimmed while not connected.
struct DevicePicture: View {
    let device: WidgetDevice?
    let size: CGFloat

    var body: some View {
        Group {
            if let device, device.image != "pendant" {
                Image(device.image)
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
                    .opacity(device.connected ? 1 : 0.55)
            } else {
                CapturePendant(active: device?.connected == true, size: size)
            }
        }
        .accessibilityHidden(true)
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
