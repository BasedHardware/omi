// Created by Barrett Jacobsen

import WidgetKit
import SwiftUI

struct DeviceMonitorEntry: TimelineEntry {
    let date: Date
    let batteryLevel: Float
    let isRecording: Bool
    let isConnected: Bool
    let tapAction: ComplicationTapAction
}

struct DeviceMonitorTimelineProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> DeviceMonitorEntry {
        DeviceMonitorEntry(date: .now, batteryLevel: 85, isRecording: false, isConnected: true, tapAction: .startDeviceRecording)
    }

    func snapshot(for configuration: DeviceMonitorConfigIntent, in context: Context) async -> DeviceMonitorEntry {
        DeviceMonitorEntry(
            date: .now,
            batteryLevel: SharedState.deviceBatteryLevel,
            isRecording: SharedState.isDeviceRecording,
            isConnected: SharedState.isDeviceConnected,
            tapAction: configuration.tapAction
        )
    }

    func timeline(for configuration: DeviceMonitorConfigIntent, in context: Context) async -> Timeline<DeviceMonitorEntry> {
        let entry = DeviceMonitorEntry(
            date: .now,
            batteryLevel: SharedState.deviceBatteryLevel,
            isRecording: SharedState.isDeviceRecording,
            isConnected: SharedState.isDeviceConnected,
            tapAction: configuration.tapAction
        )
        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: .now)!
        return Timeline(entries: [entry], policy: .after(nextUpdate))
    }
}

struct OmiDeviceMonitorWidget: Widget {
    let kind = "OmiDeviceMonitor"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: DeviceMonitorConfigIntent.self,
            provider: DeviceMonitorTimelineProvider()
        ) { entry in
            DeviceMonitorEntryView(entry: entry)
        }
        .configurationDisplayName("Omi Device")
        .description("Monitor your Omi device battery and recording status.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryInline,
            .accessoryCorner,
        ])
    }
}

struct DeviceMonitorEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: DeviceMonitorEntry

    private var widgetURL: URL {
        switch entry.tapAction {
        case .startDeviceRecording:
            return URL(string: "omi-watch://device-record")!
        case .startWatchRecording:
            return URL(string: "omi-watch://record")!
        case .askQuestion:
            return URL(string: "omi-watch://ask")!
        case .openApp:
            return URL(string: "omi-watch://open")!
        }
    }

    var body: some View {
        Group {
            switch family {
            case .accessoryCircular:
                DeviceMonitorCircularView(batteryLevel: entry.batteryLevel, isRecording: entry.isRecording, isConnected: entry.isConnected)
            case .accessoryRectangular:
                DeviceMonitorRectangularView(batteryLevel: entry.batteryLevel, isRecording: entry.isRecording, isConnected: entry.isConnected)
            case .accessoryInline:
                DeviceMonitorInlineView(batteryLevel: entry.batteryLevel, isRecording: entry.isRecording, isConnected: entry.isConnected)
            case .accessoryCorner:
                DeviceMonitorCornerView(batteryLevel: entry.batteryLevel, isRecording: entry.isRecording)
            default:
                Text("Omi")
            }
        }
        .widgetURL(widgetURL)
    }
}
