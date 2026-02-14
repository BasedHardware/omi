// Created by Barrett Jacobsen

import WidgetKit
import SwiftUI

struct AskOmiEntry: TimelineEntry {
    let date: Date
}

struct AskOmiTimelineProvider: TimelineProvider {
    func placeholder(in context: Context) -> AskOmiEntry {
        AskOmiEntry(date: .now)
    }

    func getSnapshot(in context: Context, completion: @escaping (AskOmiEntry) -> Void) {
        completion(AskOmiEntry(date: .now))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AskOmiEntry>) -> Void) {
        let entry = AskOmiEntry(date: .now)
        let nextUpdate = Calendar.current.date(byAdding: .hour, value: 1, to: .now)!
        completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
    }
}

struct AskOmiWidget: Widget {
    let kind = "AskOmi"

    var body: some WidgetConfiguration {
        StaticConfiguration(
            kind: kind,
            provider: AskOmiTimelineProvider()
        ) { entry in
            AskOmiEntryView(entry: entry)
        }
        .configurationDisplayName("Ask Omi")
        .description("Ask Omi a question using your Apple Watch microphone.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryInline,
            .accessoryCorner,
        ])
    }
}

struct AskOmiEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: AskOmiEntry

    var body: some View {
        Group {
            switch family {
            case .accessoryCircular:
                AskOmiCircularView()
            case .accessoryRectangular:
                AskOmiRectangularView()
            case .accessoryInline:
                AskOmiInlineView()
            case .accessoryCorner:
                AskOmiCornerView()
            default:
                Text("Ask")
            }
        }
        .widgetURL(URL(string: "omi-watch://ask")!)
    }
}
