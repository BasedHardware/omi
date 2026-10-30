import AppIntents
import OmiExtras
import SwiftUI

/// Everything a recording's presentation draws, independent of ActivityKit so the
/// same views can be rendered for layout verification.
struct CaptureSnapshot {
    typealias State = OmiActivityAttributes.ContentState

    let state: State
    let isStale: Bool

    var ended: Bool {
        state.status == .ended
    }

    /// The pendant's light: audio is coming in.
    var isReceivingAudio: Bool {
        !isStale && (state.status == .listening || state.status == .recording)
    }

    var clock: ActivityClockValue {
        ActivityClockValue(kind: .recording, startedAt: state.startedAt, clockEnd: state.clockEnd, frozen: state.elapsed, unknown: isStale)
    }
}

/// A stable 160 pt card, including padding, fits the Lock Screen height limit.
/// Reserve two subtitle lines so an action update does not move the wave or controls.
struct CaptureLockScreenView: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                CapturePendant(active: snapshot.isReceivingAudio, size: 36 * CaptureLayout.heroScale)
                CaptureStatusView(snapshot: snapshot, showSource: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                CaptureClock(value: snapshot.clock, size: 30)
            }
            .frame(height: 58)
            CaptureWaveform(running: snapshot.isReceivingAudio, startedAt: snapshot.state.startedAt, height: 22)
            CaptureActions(snapshot: snapshot, height: 40, secondaryFill: 0.12)
        }
        .modifier(ActivityCard())
        .modifier(CaptureEndTransition(ended: snapshot.ended))
    }
}

/// The expanded island's bottom region. Measured on a 402 pt iPhone: the bottom region starts
/// ~78 pt into a 160 pt island, which leaves exactly 22 + 10 + 38.
struct CaptureIslandBottom: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        VStack(spacing: 10) {
            CaptureWaveform(running: snapshot.isReceivingAudio, startedAt: snapshot.state.startedAt, height: 22)
            CaptureActions(snapshot: snapshot, height: 38, secondaryFill: 0.14)
        }
        .modifier(CaptureEndTransition(ended: snapshot.ended))
    }
}

/// The expanded island's trailing region: the clock, clear of the island's ~44 pt top corner curve.
struct IslandClock: View {
    let value: ActivityClockValue
    let ended: Bool

    var body: some View {
        CaptureClock(value: value, size: 30)
            .frame(maxHeight: .infinity, alignment: .center)
            .padding(.top, 6)
            .padding(.trailing, 4)
            .modifier(CaptureEndTransition(ended: ended))
    }
}

/// Art and title beside the camera. Where the title does not fit next to the art it is dropped
/// rather than shrunk; text never scales down.
struct IslandLeading<Art: View>: View {
    let title: LocalizedStringKey
    @ViewBuilder let art: () -> Art

    var body: some View {
        // Measured beside the camera: ~111 pt, so 4 + 32 + 6 + "Listening" (~66).
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) {
                art()
                Text(title, bundle: .activity)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(CapturePalette.label)
                    .lineLimit(1)
                    .fixedSize()
            }
            art()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        // Clear of the island's ~44 pt top corner curve.
        .padding(.top, 6)
        .padding(.leading, 4)
        // The island is height-capped; keep its text inside the budget.
        .dynamicTypeSize(...DynamicTypeSize.large)
    }
}

struct CaptureIslandLeading: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        IslandLeading(title: CaptureStatusView.title(snapshot)) {
            CapturePendant(active: snapshot.isReceivingAudio, size: 32)
        }
        .modifier(CaptureEndTransition(ended: snapshot.ended))
    }
}

struct CaptureStatusView: View {
    let snapshot: CaptureSnapshot
    let showSource: Bool

    private var state: CaptureSnapshot.State {
        snapshot.state
    }

    static func title(_ snapshot: CaptureSnapshot) -> LocalizedStringKey {
        if snapshot.isStale { return "Open Omi to reconnect" }
        switch snapshot.state.status {
        case .ended: return "Finished"
        case .paused: return "Paused"
        case .recording: return "Recording"
        case .listening: return "Listening"
        }
    }

    private var source: LocalizedStringKey {
        switch state.source {
        case .iPhone: "iPhone microphone"
        case .watch: "Apple Watch"
        case .omi, nil: "Omi pendant"
        }
    }

    /// What is happening to the audio right now; nil falls back to the source.
    private var detail: LocalizedStringKey? {
        switch state.status {
        case .listening: "Transcribing live"
        case .recording: "Transcribe Later"
        case .paused, .ended: nil
        }
    }

    private var subtitle: Text {
        let source = Text(source, bundle: .activity)
        guard let detail else { return source }
        let text = Text(detail, bundle: .activity)
        return showSource ? source + Text(verbatim: " · ") + text : text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // subheadline 15/600 and footnote 13 from the type ramp.
            Text(Self.title(snapshot), bundle: .activity)
                .contentTransition(.identity)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(CapturePalette.label)
                .lineLimit(1)
            subtitle
                .contentTransition(.identity)
                .font(.footnote)
                .foregroundStyle(CapturePalette.secondary)
                .lineLimit(2)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// Equal capsules 8 pt apart: secondary rgba(255,255,255,.12/.14) at 15 pt / 600, primary
/// #ECEEF2 with ink text at 15 pt / 700. Stop holds the audio back, Start brings it back, End
/// saves the conversation and closes the card.
struct CaptureActions: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    let secondaryFill: Double

    var body: some View {
        if !snapshot.isStale, !snapshot.ended {
            HStack(spacing: 8) {
                if snapshot.state.canPause {
                    if snapshot.state.status == .paused {
                        button("Start", intent: ResumeCaptureIntent())
                    } else {
                        button("Stop", intent: PauseCaptureIntent())
                    }
                }
                button("End", intent: StopCaptureIntent(), primary: true)
            }
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
        }
    }

    private func button(_ label: LocalizedStringKey, intent: some AppIntent, primary: Bool = false) -> some View {
        Button(intent: intent) {
            Text(label, bundle: .activity)
                .contentTransition(.identity)
                .font(.subheadline.weight(primary ? .bold : .semibold))
                .lineLimit(1)
                // Long translations shrink a little rather than cut off.
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, minHeight: height)
                .foregroundStyle(primary ? CapturePalette.ink : CapturePalette.label)
                .background(primary ? CapturePalette.label : Color.white.opacity(secondaryFill), in: Capsule())
        }
        .buttonStyle(CaptureActionStyle())
    }
}

/// The system's plain style dims a pressed button; keep these fills stable.
private struct CaptureActionStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}
