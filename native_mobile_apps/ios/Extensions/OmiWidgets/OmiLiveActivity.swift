import ActivityKit
import OmiExtras
import SwiftUI
import WidgetKit

/// The recording and Omi's work on a task, on the Lock Screen and in the Dynamic Island. The views
/// (Extensions/LiveActivityUI) are the Flutter app's capture card; this places them.
struct OmiLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: OmiActivityAttributes.self) { context in
            Group {
                switch context.attributes.kind {
                case .capture: CaptureLockScreenView(snapshot: context.captureSnapshot)
                case .agent: AgentLockScreenView(snapshot: AgentSnapshot(state: context.state))
                }
            }
            .activityBackgroundTint(CapturePalette.card)
            .activitySystemActionForegroundColor(CapturePalette.label)
            .widgetURL(Self.link(context.attributes.kind, context.state))
        } dynamicIsland: { context in
            let island = switch context.attributes.kind {
            case .capture: CaptureIsland.make(context.captureSnapshot)
            case .agent: AgentIsland.make(AgentSnapshot(state: context.state))
            }
            // Default side margins leave ~100 pt beside the camera; 12 pt gives
            // the pendant and a short title room without shrinking text.
            return island
                .widgetURL(Self.link(context.attributes.kind, context.state))
                .keylineTint(CapturePalette.led)
                .contentMargins(.horizontal, 12, for: .expanded)
        }
    }

    static func link(_ kind: OmiActivityAttributes.Kind, _ state: OmiActivityAttributes.ContentState) -> URL? {
        switch kind {
        case .capture: WidgetLink.home
        case .agent: state.taskID.flatMap(WidgetLink.task) ?? WidgetLink.home
        }
    }
}

extension ActivityViewContext where Attributes == OmiActivityAttributes {
    var captureSnapshot: CaptureSnapshot {
        CaptureSnapshot(state: state, isStale: isStale)
    }
}

/// Island.dc.html: 372 x 172 with 18/22 padding, one 40 pt row, a 22 pt waveform and 38 pt
/// buttons, 12 pt apart. iOS caps the expanded island near 160 pt and puts the camera between the
/// leading and trailing regions, so the row is split around it and the subtitle (no room beside
/// the camera on any iPhone) is left to the Lock Screen card.
enum CaptureIsland {
    static func make(_ snapshot: CaptureSnapshot) -> DynamicIsland {
        DynamicIsland {
            DynamicIslandExpandedRegion(.leading) {
                CaptureIslandLeading(snapshot: snapshot)
            }
            DynamicIslandExpandedRegion(.trailing) {
                IslandClock(value: snapshot.clock, ended: snapshot.ended)
            }
            DynamicIslandExpandedRegion(.bottom) {
                CaptureIslandBottom(snapshot: snapshot)
            }
        } compactLeading: {
            // HomeScreen.json: 20 pt pendant, 10 pt from the island edge.
            CapturePendant(active: snapshot.isReceivingAudio, size: 20)
                .modifier(CaptureEndTransition(ended: snapshot.ended))
        } compactTrailing: {
            CaptureCompactClock(value: snapshot.clock)
                .modifier(CaptureEndTransition(ended: snapshot.ended))
        } minimal: {
            CapturePendant(active: snapshot.isReceivingAudio, size: 20)
                .modifier(CaptureEndTransition(ended: snapshot.ended))
        }
    }
}

enum AgentIsland {
    static func make(_ snapshot: AgentSnapshot) -> DynamicIsland {
        DynamicIsland {
            DynamicIslandExpandedRegion(.leading) {
                AgentIslandLeading(snapshot: snapshot)
            }
            DynamicIslandExpandedRegion(.trailing) {
                IslandClock(value: snapshot.clock, ended: false)
            }
            DynamicIslandExpandedRegion(.bottom) {
                AgentIslandBottom(snapshot: snapshot)
            }
        } compactLeading: {
            AgentArt(snapshot: snapshot, size: 20)
        } compactTrailing: {
            CaptureCompactClock(value: snapshot.clock)
        } minimal: {
            AgentArt(snapshot: snapshot, size: 20)
        }
    }
}

private typealias PreviewState = OmiActivityAttributes.ContentState

#Preview("Recording", as: .content, using: OmiActivityAttributes(kind: .capture)) {
    OmiLiveActivity()
} contentStates: {
    PreviewState.capture(id: "rec", startedAt: .now.addingTimeInterval(-136), source: .omi, status: .listening, canPause: true)
    PreviewState.capture(id: "rec", startedAt: .now.addingTimeInterval(-136), source: .iPhone, status: .paused, elapsed: 136,
                         canPause: true)
}

#Preview("Omi at work", as: .content, using: OmiActivityAttributes(kind: .agent)) {
    OmiLiveActivity()
} contentStates: {
    PreviewState(id: "run", phase: .working, startedAt: .now.addingTimeInterval(-42), title: "Find a dentist near the office",
                 step: "Searching the web", otherRuns: 1)
    PreviewState(id: "run", phase: .finished, startedAt: .now.addingTimeInterval(-300), elapsed: 300,
                 title: "Find a dentist near the office")
}
