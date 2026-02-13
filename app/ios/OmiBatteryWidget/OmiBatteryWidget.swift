import WidgetKit
import SwiftUI
import os

private let logger = Logger(subsystem: "com.omi.battery-widget", category: "widget")

// MARK: - Data Model

struct BatteryEntry: TimelineEntry {
    let date: Date
    let batteryLevel: Int // 0-100, -1 = unknown
    let isConnected: Bool
}

// MARK: - Timeline Provider

struct BatteryTimelineProvider: TimelineProvider {
    private let groupId = "group.omi.shared.data"

    func placeholder(in context: Context) -> BatteryEntry {
        BatteryEntry(date: Date(), batteryLevel: 75, isConnected: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (BatteryEntry) -> Void) {
        completion(readEntry())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BatteryEntry>) -> Void) {
        let entry = readEntry()
        let timeline = Timeline(entries: [entry], policy: .never)
        completion(timeline)
    }

    private func readEntry() -> BatteryEntry {
        logger.warning("readEntry called")

        if let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: groupId) {
            logger.warning("Widget container URL: \(containerURL.path)")
        } else {
            logger.error("Widget container URL is nil!")
        }

        guard let defaults = UserDefaults(suiteName: groupId) else {
            logger.error("Cannot open shared UserDefaults for group: \(self.groupId)")
            return BatteryEntry(date: Date(), batteryLevel: -1, isConnected: false)
        }

        let batteryLevel = defaults.integer(forKey: "omi_battery_level")
        let isConnected = defaults.bool(forKey: "omi_is_connected")
        logger.warning("readEntry: battery=\(batteryLevel), connected=\(isConnected)")

        return BatteryEntry(
            date: Date(),
            batteryLevel: batteryLevel,
            isConnected: isConnected
        )
    }
}

// MARK: - Widget View

struct BatteryWidgetView: View {
    let entry: BatteryEntry

    var body: some View {
        Gauge(value: Double(max(entry.batteryLevel, 0)), in: 0...100) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 12))
        } currentValueLabel: {
            Text(entry.isConnected ? "\(entry.batteryLevel)" : "--")
                .font(.system(size: 12, weight: .medium, design: .rounded))
        }
        .gaugeStyle(.accessoryCircular)
    }
}

// MARK: - Widget Configuration

@main
struct OmiBatteryWidget: Widget {
    let kind: String = "OmiBatteryWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BatteryTimelineProvider()) { entry in
            BatteryWidgetView(entry: entry)
        }
        .configurationDisplayName("Omi Battery")
        .description("Shows your Omi device battery level")
        .supportedFamilies([.accessoryCircular])
    }
}
