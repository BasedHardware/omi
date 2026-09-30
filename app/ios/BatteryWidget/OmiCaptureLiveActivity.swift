import ActivityKit
import SwiftUI
import UIKit
import WidgetKit

// Values below come from the omi-ios-v2 design package: tokens/tokens.json,
// generator/s_system.py (LockScreen, Island) and specs/geometry/iphone16.
// Text and controls keep one size on every iPhone; only the pendant (hero art)
// scales with the device, as the in-app Live screen does on SE/mini/16/Max.

/// Midnight Graphite tokens.
enum CapturePalette {
    static let label = Color(red: 0xEC / 255, green: 0xEE / 255, blue: 0xF2 / 255)
    static let secondary = Color(red: 0x9A / 255, green: 0xA1 / 255, blue: 0xAD / 255)
    static let ink = Color(red: 0x0A / 255, green: 0x0C / 255, blue: 0x10 / 255)
    static let led = Color(red: 0x4C / 255, green: 0x9B / 255, blue: 0xFF / 255)
    /// material.glassThick (dark): rgba(26,29,37,.88).
    static let card = Color(red: 26 / 255, green: 29 / 255, blue: 37 / 255).opacity(0.88)
}

/// Device scaling from tokens.json `layout.KH`.
enum CaptureLayout {
    /// clamp((height − safeTop − safeBottom) / 764, 0.8, 1.1). The extension has
    /// no window insets, so they come from the design's device profiles.
    static var heroScale: CGFloat {
        let height = UIScreen.main.bounds.height
        let safeTop: CGFloat = height >= 874 ? 62 : height >= 852 ? 54 : height >= 812 ? 48 : 20
        let safeBottom: CGFloat = height >= 812 ? 34 : 0
        return min(1.1, max(0.8, (height - safeTop - safeBottom) / 764))
    }
}

/// Everything a capture presentation draws, independent of ActivityKit so the
/// same views can be rendered for layout verification.
@available(iOS 16.1, *)
struct CaptureSnapshot {
    let recordingId: String
    let state: OmiCaptureAttributes.ContentState
    let isStale: Bool

    var isReceivingAudio: Bool {
        !isStale && !state.paused && (state.status == "listening" || state.status == "recording")
    }

    /// A live timer's ideal width is unbounded, so the clock always gets a
    /// fixed slot, in ems of its font size: the design's 30 pt "02:16" is
    /// 95.5 pt wide (3.2 em); h:mm:ss after the first hour needs 4.3 em.
    var clockEms: CGFloat {
        let elapsed = state.paused || state.status == "ended"
            ? Double(state.elapsed) : Date().timeIntervalSince1970 - state.startedAt
        return elapsed >= 3600 ? 4.3 : 3.2
    }
}

@available(iOS 16.1, *)
extension ActivityViewContext where Attributes == OmiCaptureAttributes {
    var omiSnapshot: CaptureSnapshot {
        var stale = false
        if #available(iOS 16.2, *) { stale = isStale }
        return CaptureSnapshot(recordingId: attributes.recordingId, state: state, isStale: stale)
    }
}

@available(iOS 16.1, *)
struct OmiCaptureLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: OmiCaptureAttributes.self) { context in
            CaptureLockScreenView(snapshot: context.omiSnapshot)
                .activityBackgroundTint(CapturePalette.card)
                .activitySystemActionForegroundColor(CapturePalette.label)
                .widgetURL(captureURL(context.attributes.recordingId))
        } dynamicIsland: { context in
            let snapshot = context.omiSnapshot
            let island = DynamicIsland {
                // Island.dc.html: 372 x 172 with 18/22 padding, one 40 pt row, a
                // 22 pt waveform and 38 pt buttons, 12 pt apart. iOS caps the
                // expanded island near 160 pt and puts the camera between the
                // leading and trailing regions, so the row is split around it and
                // the subtitle (no room beside the camera on any iPhone) is left
                // to the Lock Screen card.
                DynamicIslandExpandedRegion(.leading) {
                    CaptureIslandLeading(snapshot: snapshot)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    CaptureClock(snapshot: snapshot, size: 30)
                        .frame(maxHeight: .infinity, alignment: .center)
                        // Clear of the island's ~44 pt top corner curve.
                        .padding(.top, 6)
                        .padding(.trailing, 4)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    // Measured on a 402 pt iPhone: the bottom region starts ~78 pt
                    // into a 160 pt island, which leaves exactly 22 + 10 + 38.
                    VStack(spacing: 10) {
                        CaptureWaveform(snapshot: snapshot, height: 22)
                        CaptureActions(snapshot: snapshot, height: 38, secondaryFill: 0.14)
                    }
                }
            } compactLeading: {
                // HomeScreen.json: 20 pt pendant, 10 pt from the island edge.
                CapturePendant(active: snapshot.isReceivingAudio, size: 20)
            } compactTrailing: {
                CaptureCompactClock(snapshot: snapshot)
            } minimal: {
                CapturePendant(active: snapshot.isReceivingAudio, size: 20)
            }
            .widgetURL(captureURL(context.attributes.recordingId))
            .keylineTint(CapturePalette.led)
            // Default side margins leave ~100 pt beside the camera; 12 pt gives
            // the pendant and a short title room without shrinking text.
            if #available(iOS 17.0, *) {
                return island.contentMargins(.horizontal, 12, for: .expanded)
            }
            return island
        }
    }
}

private func captureURL(_ id: String) -> URL? {
    // The callback scheme is supplied by the embedding app's configuration.
    var components = URLComponents()
    components.scheme = Bundle.main.object(forInfoDictionaryKey: "OmiCaptureURLScheme") as? String ?? "omi"
    components.host = "app"
    components.path = "/capture"
    components.queryItems = [URLQueryItem(name: "recording", value: id)]
    return components.url
}

/// A stable 160 pt card, including padding, fits the Lock Screen height limit.
/// Reserve two subtitle lines so an action update does not move the wave or controls.
@available(iOS 16.1, *)
struct CaptureLockScreenView: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                CapturePendant(active: snapshot.isReceivingAudio, size: 36 * CaptureLayout.heroScale)
                CaptureStatus(snapshot: snapshot, showSource: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                CaptureClock(snapshot: snapshot, size: 30)
            }
            .frame(height: 58)
            CaptureWaveform(snapshot: snapshot, height: 22)
            CaptureActions(snapshot: snapshot, height: 40, secondaryFill: 0.12)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .foregroundStyle(CapturePalette.label)
        // glass-thick top highlight: rgba(255,255,255,.06) fading out by 50%.
        .background(LinearGradient(stops: [
            .init(color: .white.opacity(0.06), location: 0),
            .init(color: .clear, location: 0.5),
        ], startPoint: .top, endPoint: .bottom))
        .dynamicTypeSize(...DynamicTypeSize.xLarge)
    }
}

/// Pendant and title beside the camera. Where the title does not fit next to
/// the pendant it is dropped rather than shrunk; text never scales down.
@available(iOS 16.1, *)
private struct CaptureIslandLeading: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        // Measured beside the camera: ~111 pt, so 4 + 32 + 6 + "Listening" (~66).
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) {
                CapturePendant(active: snapshot.isReceivingAudio, size: 32)
                CaptureStatus(snapshot: snapshot, showSource: false, titleOnly: true)
                    .fixedSize()
            }
            CapturePendant(active: snapshot.isReceivingAudio, size: 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        // Clear of the island's ~44 pt top corner curve.
        .padding(.top, 6)
        .padding(.leading, 4)
        // The island is height-capped; keep its text inside the budget.
        .dynamicTypeSize(...DynamicTypeSize.large)
    }
}

@available(iOS 16.1, *)
private struct CaptureStatus: View {
    let snapshot: CaptureSnapshot
    let showSource: Bool
    var titleOnly = false

    private var state: OmiCaptureAttributes.ContentState { snapshot.state }

    private var title: LocalizedStringKey {
        if snapshot.isStale { return "Open Omi to reconnect" }
        if state.actionFailed { return "Open Omi to continue" }
        switch state.status {
        case "ended": return "Finished"
        case "paused": return "Paused"
        case "interrupted": return "Paused"
        case "connecting": return "Connecting…"
        case "recording": return "Recording"
        case "reconnecting": return "Reconnecting…"
        default: return "Listening"
        }
    }

    private var source: LocalizedStringKey {
        state.source == "phone" ? "Phone microphone" : "Omi pendant"
    }

    /// What is happening to the audio right now; nil falls back to the source.
    private var detail: LocalizedStringKey? {
        if state.busy { return "Updating…" }
        switch state.status {
        case "listening": return "Transcribing live"
        case "recording": return "Transcribe Later"
        case "interrupted": return "Resumes automatically"
        default: return nil
        }
    }

    private var subtitle: Text {
        guard let detail else { return Text(source) }
        return showSource ? Text(source) + Text(" · ") + Text(detail) : Text(detail)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // subheadline 15/600 and footnote 13 from the type ramp.
            Text(title)
                .contentTransition(.identity)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(CapturePalette.label)
                .lineLimit(1)
            if !titleOnly {
                subtitle
                    .contentTransition(.identity)
                    .font(.footnote)
                    .foregroundStyle(CapturePalette.secondary)
                    .lineLimit(2)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// The 30 pt / 600 clock, flush right in a slot sized for its longest value.
@available(iOS 16.1, *)
private struct CaptureClock: View {
    let snapshot: CaptureSnapshot
    @ScaledMetric private var size: CGFloat

    init(snapshot: CaptureSnapshot, size: CGFloat) {
        self.snapshot = snapshot
        _size = ScaledMetric(wrappedValue: size, relativeTo: .title)
    }

    var body: some View {
        CaptureClockText(snapshot: snapshot)
            .font(.system(size: size, weight: .semibold))
            .frame(width: size * snapshot.clockEms, alignment: .trailing)
    }
}

/// HomeScreen.json: 15 pt / 600 clock, 14 pt from the island's trailing edge.
@available(iOS 16.1, *)
private struct CaptureCompactClock: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        CaptureClockText(snapshot: snapshot)
            .font(.system(size: 15, weight: .semibold))
            .frame(width: 15 * snapshot.clockEms, alignment: .trailing)
            .padding(.trailing, 4)
    }
}

@available(iOS 16.1, *)
private struct CaptureClockText: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        let state = snapshot.state
        Group {
            if snapshot.isStale {
                Text("—")
            } else if state.paused || state.status == "ended" {
                // Frozen value in the same format the live timer uses.
                let seconds = max(0, state.elapsed)
                Text(seconds >= 3600
                    ? String(format: "%d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60)
                    : String(format: "%d:%02d", seconds / 60, seconds % 60))
            } else {
                // A live timer reserves width for its range's longest value, so
                // the range ends at the next hour; periodic updates extend it.
                let start = Date(timeIntervalSince1970: state.startedAt)
                let hours = (max(0, Date().timeIntervalSince(start)) / 3600).rounded(.down) + 1
                Text(timerInterval: start...start.addingTimeInterval(hours * 3600), countsDown: false)
            }
        }
        .monospacedDigit()
        .contentTransition(.identity)
        .transition(.identity)
        .multilineTextAlignment(.trailing)
        .foregroundStyle(CapturePalette.label)
        .lineLimit(1)
        .accessibilityLabel(Text("Recording duration"))
    }
}

/// The Omi pendant, as the app shows it: its photo with the light on while audio is captured
/// (a soft blue glow behind it), and its lights-off photo otherwise.
@available(iOS 16.1, *)
struct CapturePendant: View {
    let active: Bool
    let size: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced

    var body: some View {
        // Keep the photo's identity and geometry stable; only its LED fades.
        ZStack {
            Image("device-omi-off").resizable().scaledToFit()
            Image("device-omi").resizable().scaledToFit().opacity(active ? 1 : 0)
        }
            .frame(width: size, height: size)
            .shadow(color: CapturePalette.led.opacity(active ? 0.45 : 0), radius: size * 0.18)
            .contentTransition(.identity)
            .animation(reduceMotion || luminanceReduced ? nil :
                .timingCurve(0.42, 0, 0.58, 1, duration: 0.25), value: active)
            .accessibilityHidden(true)
    }
}

/// omi-home-v4 `.wave`: 2 pt bars 2.2 pt apart in the design's fixed level pattern, each
/// breathing between full and 45 % height, the breath rippling leftward every 13 bars.
/// The OS cannot loop animations in a Live Activity, so the app's updates step the loop:
/// while voice is heard the app updates about once a second, each update flips the breath,
/// and every bar animates to it after a delay set by its place in the ripple. Without voice
/// the strip settles at its low height. Its color stays constant during Start/Stop.
/// Custom timing curves keep motion local; reduced motion and Always On keep it still.
@available(iOS 16.1, *)
private struct CaptureWaveform: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced
    private static let barWidth: CGFloat = 2
    private static let gap: CGFloat = 2.2
    /// `@keyframes lvl{50%{transform:scaleY(.45)}}`.
    private static let exhaled: CGFloat = 0.45
    private static let ripple = 13
    /// The design's `lv` list: bar heights as a share of the strip.
    private static let levels: [CGFloat] = [
        0.22, 0.35, 0.5, 0.3, 0.62, 0.8, 0.45, 0.28, 0.55, 0.9, 0.7, 0.38, 0.25, 0.42, 0.66, 0.52, 0.3,
        0.2, 0.35, 0.58, 0.76, 0.6, 0.4, 0.33, 0.48, 0.7, 0.85, 0.5, 0.3, 0.24, 0.4, 0.62, 0.45, 0.3,
        0.52, 0.72, 0.56, 0.36, 0.28, 0.44, 0.6, 0.8, 0.64, 0.4, 0.3, 0.5, 0.66, 0.42, 0.3, 0.26,
    ]

    /// Voice is heard, so updates arrive about once a second.
    private var breathing: Bool {
        snapshot.isReceivingAudio && snapshot.state.metered && snapshot.state.voice
    }

    /// Flips on every update: `levelsEnd` counts 125 ms bins of wall clock, 8 per update.
    private var exhale: Bool {
        breathing && (snapshot.state.levelsEnd + 4) / 8 % 2 == 1
    }

    private var scale: CGFloat {
        guard snapshot.isReceivingAudio else { return Self.exhaled }
        // Unmetered sources cannot report voice; retain their steady active indicator.
        if !snapshot.state.metered { return 1 }
        guard breathing else { return Self.exhaled }
        return reduceMotion || luminanceReduced || !exhale ? 1 : Self.exhaled
    }

    var body: some View {
        let scale = self.scale
        GeometryReader { geometry in
            // Never derive layout from an unbounded proposal; it cannot be placed.
            let width = geometry.size.width.isFinite ? max(0, geometry.size.width) : 0
            let count = max(1, Int((width + Self.gap) / (Self.barWidth + Self.gap)))
            HStack(alignment: .center, spacing: Self.gap) {
                ForEach(0..<count, id: \.self) { index in
                    Capsule()
                        .frame(width: Self.barWidth,
                               height: max(3, height * Self.levels[index % Self.levels.count]))
                        .scaleEffect(x: 1, y: scale)
                        // Settle together on Stop; stagger only the active breathing wave.
                        .animation(reduceMotion || luminanceReduced ? nil :
                            .timingCurve(0.42, 0, 0.58, 1, duration: breathing ? 0.5 : 0.25)
                                .delay(breathing ? Double(Self.ripple - 1 - index % Self.ripple) * 0.02 : 0),
                            value: scale)
                }
            }
            .frame(width: width, height: height)
            .clipped()
        }
        .frame(height: height)
        .foregroundStyle(CapturePalette.label.opacity(0.75))
        .accessibilityHidden(true)
    }
}

/// Equal capsules 8 pt apart: secondary rgba(255,255,255,.12/.14) at 15 pt / 600, primary
/// #ECEEF2 with ink text at 15 pt / 700.
@available(iOS 16.1, *)
private struct CaptureActions: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    let secondaryFill: Double

    private var state: OmiCaptureAttributes.ContentState { snapshot.state }

    var body: some View {
        if #available(iOS 17.0, *), !snapshot.isStale, state.status != "ended" {
            HStack(spacing: 8) {
                // Shared by the Lock Screen and expanded Island. Start/Stop keep the existing
                // resume/pause behavior; Start is offered only after a user stops capture.
                if state.canPause {
                    let resume = state.status == "paused"
                    action(resume ? "Start" : "Stop", value: resume ? "resume" : "pause", enabled: true)
                }
                // End always closes this card, saving the conversation first when there is one
                // (LiveActivityManager).
                action("End", value: state.canFinish ? "finish" : "close", enabled: true, primary: true)
            }
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
        }
    }

    @available(iOS 17.0, *)
    private func action(_ label: LocalizedStringKey, value: String, enabled: Bool, primary: Bool = false) -> some View {
        // Busy blocks duplicate intents without recoloring the whole action row.
        let available = enabled && !state.busy
        return Button(intent: OmiCaptureIntent(recordingId: snapshot.recordingId,
                                               revision: state.conversationRevision, action: value)) {
            Text(label)
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
        .disabled(!available)
    }
}

/// The system's plain style dims every busy button. Keep these fills stable while
/// the intent is disabled; the status subtitle already explains that it is updating.
private struct CaptureActionStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}
