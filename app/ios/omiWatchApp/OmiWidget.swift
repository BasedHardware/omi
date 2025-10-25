import SwiftUI
import WidgetKit

/// Omi Smart Stack Widget for watchOS 26
/// Provides quick access to recording status and battery information
struct OmiWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> OmiWidgetEntry {
        OmiWidgetEntry(
            date: Date(),
            isRecording: false,
            batteryLevel: 100,
            recordingDuration: 0,
            relevance: TimelineEntryRelevance(score: 0.1)
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (OmiWidgetEntry) -> Void) {
        Task {
            let now = Date()
            let snapshot = await SmartStackRelevanceStore.shared.snapshot()
            let entry = OmiWidgetEntry(snapshot: snapshot, referenceDate: now)
            await MainActor.run {
                completion(entry)
            }
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OmiWidgetEntry>) -> Void) {
        Task {
            let now = Date()
            let snapshot = await SmartStackRelevanceStore.shared.snapshot()
            let entry = OmiWidgetEntry(snapshot: snapshot, referenceDate: now)
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: 5, to: now) ?? now.addingTimeInterval(300)
            let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
            await MainActor.run {
                completion(timeline)
            }
        }
    }

    @available(watchOS 26.0, *)
    func relevance() async -> WidgetRelevance<Void> {
        await SmartStackRelevanceStore.shared.widgetRelevance()
    }
}

struct OmiWidgetEntry: TimelineEntry {
    let date: Date
    let isRecording: Bool
    let batteryLevel: Int
    let recordingDuration: TimeInterval
    let relevance: TimelineEntryRelevance?

    init(
        date: Date,
        isRecording: Bool,
        batteryLevel: Int,
        recordingDuration: TimeInterval,
        relevance: TimelineEntryRelevance? = nil
    ) {
        self.date = date
        self.isRecording = isRecording
        self.batteryLevel = batteryLevel
        self.recordingDuration = recordingDuration
        self.relevance = relevance
    }

    init(snapshot: SmartStackRelevanceStore.Snapshot, referenceDate: Date = Date()) {
        self.date = referenceDate
        self.isRecording = snapshot.isRecording
        self.batteryLevel = snapshot.batteryLevel
        self.recordingDuration = snapshot.recordingDuration(at: referenceDate)
        self.relevance = snapshot.timelineRelevance(currentDate: referenceDate)
    }
}

struct OmiWidgetView: View {
    var entry: OmiWidgetProvider.Entry
    @Environment(\.widgetFamily) var widgetFamily
    @Namespace private var glassNamespace

    private enum GlassID {
        static let circular = "widget.circular.glass.container"
        static let rectangular = "widget.rectangular.glass.container"
        static let rectangularIcon = "widget.rectangular.glass.icon"
    }

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

    @ViewBuilder
    private var circularWidget: some View {
        if #available(watchOS 26.0, *) {
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.12))
                    .glassEffect(.regular)
                    .glassEffectID(GlassID.circular, in: glassNamespace)

                circularContent
            }
        } else {
            legacyCircularWidget
        }
    }

    @ViewBuilder
    private var rectangularWidget: some View {
        if #available(watchOS 26.0, *) {
            HStack(spacing: 12) {
                RoundedRectangle(cornerRadius: 9)
                    .fill(Color.white.opacity(0.15))
                    .frame(width: 42, height: 42)
                    .glassEffect(.regular)
                    .glassEffectID(GlassID.rectangularIcon, in: glassNamespace)
                    .overlay(rectangularIcon)

                rectangularTextStack
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.white.opacity(0.12))
                    .glassEffect(.regular)
                    .glassEffectID(GlassID.rectangular, in: glassNamespace)
            )
        } else {
            legacyRectangularWidget
        }
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

// MARK: - Legacy + Shared Widget Views

private extension OmiWidgetView {
    private var circularContent: some View {
        VStack(spacing: 4) {
            if entry.isRecording {
                Image(systemName: "waveform.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(
                        LinearGradient(colors: [.red, .orange], startPoint: .top, endPoint: .bottom)
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

    private var legacyCircularWidget: some View {
        ZStack {
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

            circularContent
        }
    }

    private var rectangularIcon: some View {
        Image(systemName: entry.isRecording ? "waveform.circle.fill" : "waveform")
            .font(.system(size: 20))
            .foregroundStyle(
                entry.isRecording ?
                LinearGradient(colors: [.red, .orange], startPoint: .top, endPoint: .bottom) :
                LinearGradient(colors: [.white], startPoint: .top, endPoint: .bottom)
            )
    }

    private var rectangularTextStack: some View {
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
    }

    private var legacyRectangularWidget: some View {
        HStack(spacing: 12) {
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

                rectangularIcon
            }

            rectangularTextStack
            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }
}

// NOTE: Widget should be moved to a separate Widget Extension target in production
// Currently in main app target to avoid @main conflict during development
// For now, commented out to allow main watch app to build
/*
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

// Previews also commented out until widget is in separate target
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
*/
