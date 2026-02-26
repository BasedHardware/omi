// Created by Barrett Jacobsen

import WidgetKit
import SwiftUI

struct QuickRecordEntry: TimelineEntry {
    let date: Date
    let isRecording: Bool
}

struct QuickRecordTimelineProvider: TimelineProvider {
    func placeholder(in context: Context) -> QuickRecordEntry {
        QuickRecordEntry(date: .now, isRecording: false)
    }

    func getSnapshot(in context: Context, completion: @escaping (QuickRecordEntry) -> Void) {
        completion(QuickRecordEntry(date: .now, isRecording: SharedState.isWatchRecording))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<QuickRecordEntry>) -> Void) {
        let entry = QuickRecordEntry(date: .now, isRecording: SharedState.isWatchRecording)
        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: .now)!
        completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
    }
}

struct QuickRecordWidget: Widget {
    let kind = "QuickRecord"

    var body: some WidgetConfiguration {
        StaticConfiguration(
            kind: kind,
            provider: QuickRecordTimelineProvider()
        ) { entry in
            QuickRecordEntryView(entry: entry)
        }
        .configurationDisplayName("Omi Recorder")
        .description("Quickly start recording from your Apple Watch microphone.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryInline,
            .accessoryCorner,
        ])
    }
}

struct QuickRecordEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: QuickRecordEntry

    var body: some View {
        Group {
            switch family {
            case .accessoryCircular:
                QuickRecordCircularView(isRecording: entry.isRecording)
            case .accessoryRectangular:
                QuickRecordRectangularView(isRecording: entry.isRecording)
            case .accessoryInline:
                QuickRecordInlineView(isRecording: entry.isRecording)
            case .accessoryCorner:
                QuickRecordCornerView(isRecording: entry.isRecording)
            default:
                Text("Record")
            }
        }
        .widgetURL(URL(string: "omi-watch://record")!)
    }
}
