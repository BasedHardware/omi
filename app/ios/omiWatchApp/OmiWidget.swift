import SwiftUI
import WidgetKit

/// Omi Smart Stack Widget for watchOS 26
/// Uses native materials and framework-provided Liquid Glass effects
struct OmiWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> OmiWidgetEntry {
        OmiWidgetEntry(date: Date(), isRecording: false, batteryLevel: 100, recordingDuration: 0)
    }

    func getSnapshot(in context: Context, completion: @escaping (OmiWidgetEntry) -> Void) {
        let entry = OmiWidgetEntry(date: Date(), isRecording: false, batteryLevel: 85, recordingDuration: 0)
        completion(entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OmiWidgetEntry>) -> Void) {
        // Get current status
        let batteryInfo = BatteryManager.shared.getBatteryInfo()
        let batteryLevel = batteryInfo["level"] as? Float ?? 0

        let entry = OmiWidgetEntry(
            date: Date(),
            isRecording: false, // This would be updated from shared state
            batteryLevel: Int(batteryLevel),
            recordingDuration: 0
        )

        // Update every 15 minutes or when recording state changes
        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: Date())!
        let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
        completion(timeline)
    }
}

struct OmiWidgetEntry: TimelineEntry {
    let date: Date
    let isRecording: Bool
    let batteryLevel: Int
    let recordingDuration: TimeInterval
}

struct OmiWidgetView: View {
    var entry: OmiWidgetProvider.Entry
    @Environment(\.widgetFamily) var widgetFamily

    var body: some View {
        switch widgetFamily {
        case .accessoryCircular:
            circularWidget
        case .accessoryRectangular:
            rectangularWidget
        case .accessoryCorner:
            cornerWidget
        default:
            circularWidget
        }
    }

    private var circularWidget: some View {
        ZStack {
            // Native Liquid Glass material background
            Circle()
                .fill(.ultraThinMaterial)

            VStack(spacing: 4) {
                if entry.isRecording {
                    Image(systemName: "waveform.circle.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(.red)
                    Text("REC")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundStyle(.red)
                } else {
                    Image(systemName: "waveform")
                        .font(.system(size: 24))
                        .foregroundStyle(.white)
                    Text("\(entry.batteryLevel)%")
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var rectangularWidget: some View {
        HStack(spacing: 12) {
            // Icon with native material background
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(.thinMaterial)
                    .frame(width: 40, height: 40)

                Image(systemName: entry.isRecording ? "waveform.circle.fill" : "waveform")
                    .font(.system(size: 20))
                    .foregroundStyle(entry.isRecording ? .red : .white)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Omi")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)

                if entry.isRecording {
                    Text("Recording")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.red)
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "battery.100")
                            .font(.system(size: 10))
                        Text("\(entry.batteryLevel)%")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                    }
                    .foregroundStyle(.secondary)
                }
            }

            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    private var cornerWidget: some View {
        ZStack {
            if entry.isRecording {
                Image(systemName: "waveform.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(.red)
            } else {
                Image(systemName: "waveform")
                    .font(.system(size: 24))
                    .foregroundStyle(.white)
            }
        }
    }
}

@main
struct OmiWidget: Widget {
    let kind: String = "OmiWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: OmiWidgetProvider()) { entry in
            OmiWidgetView(entry: entry)
        }
        .configurationDisplayName("Omi")
        .description("Quick access to Omi recording and status")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryCorner
        ])
    }
}

#Preview("Circular - Not Recording", as: .accessoryCircular) {
    OmiWidget()
} timeline: {
    OmiWidgetEntry(date: Date(), isRecording: false, batteryLevel: 85, recordingDuration: 0)
}

#Preview("Circular - Recording", as: .accessoryCircular) {
    OmiWidget()
} timeline: {
    OmiWidgetEntry(date: Date(), isRecording: true, batteryLevel: 85, recordingDuration: 120)
}

#Preview("Rectangular - Not Recording", as: .accessoryRectangular) {
    OmiWidget()
} timeline: {
    OmiWidgetEntry(date: Date(), isRecording: false, batteryLevel: 85, recordingDuration: 0)
}

#Preview("Rectangular - Recording", as: .accessoryRectangular) {
    OmiWidget()
} timeline: {
    OmiWidgetEntry(date: Date(), isRecording: true, batteryLevel: 85, recordingDuration: 120)
}
