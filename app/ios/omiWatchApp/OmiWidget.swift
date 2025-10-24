import SwiftUI
import WidgetKit

/// Omi Smart Stack Widget for watchOS 26
/// Provides quick access to recording status and battery information
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
            // Background with Liquid Glass effect
            Circle()
                .fill(
                    LinearGradient(
                        gradient: Gradient(colors: [
                            Color.white.opacity(0.2),
                            Color.white.opacity(0.1)
                        ]),
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.3), lineWidth: 2)
                )

            VStack(spacing: 4) {
                if entry.isRecording {
                    Image(systemName: "waveform.circle.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [.red, .orange],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                    Text("REC")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundColor(.red)
                } else {
                    Image(systemName: "waveform")
                        .font(.system(size: 24))
                        .foregroundColor(.white)
                    Text("\(entry.batteryLevel)%")
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
    }

    private var rectangularWidget: some View {
        HStack(spacing: 12) {
            // Icon with Liquid Glass styling
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(
                        LinearGradient(
                            gradient: Gradient(colors: [
                                Color.white.opacity(0.2),
                                Color.white.opacity(0.1)
                            ]),
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 40, height: 40)

                Image(systemName: entry.isRecording ? "waveform.circle.fill" : "waveform")
                    .font(.system(size: 20))
                    .foregroundStyle(
                        entry.isRecording ?
                        LinearGradient(colors: [.red, .orange], startPoint: .top, endPoint: .bottom) :
                        LinearGradient(colors: [.white], startPoint: .top, endPoint: .bottom)
                    )
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Omi")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundColor(.white)

                if entry.isRecording {
                    Text("Recording")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundColor(.red)
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "battery.100")
                            .font(.system(size: 10))
                        Text("\(entry.batteryLevel)%")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                    }
                    .foregroundColor(.white.opacity(0.7))
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
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.red, .orange],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            } else {
                Image(systemName: "waveform")
                    .font(.system(size: 24))
                    .foregroundColor(.white)
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
