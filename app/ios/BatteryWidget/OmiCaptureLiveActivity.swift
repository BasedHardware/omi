import ActivityKit
import SwiftUI
import UIKit
import WidgetKit

// Values below come from the omi-ios-v2 design package: tokens/tokens.json,
// generator/s_system.py (LockScreen, Island) and specs/geometry/iphone16.
// Text and controls keep one size on every iPhone; only the pendant (hero art)
// scales with the device, as the in-app Live screen does on SE/mini/16/Max.

/// Liquid Dock tokens (the app's `OmiColors`).
enum CapturePalette {
    static let label = Color.white
    static let secondary = Color(red: 0xA9 / 255, green: 0xAE / 255, blue: 0xB9 / 255)
    static let ink = Color(red: 0x0A / 255, green: 0x0B / 255, blue: 0x0F / 255)
    static let led = Color(red: 0x4C / 255, green: 0x9B / 255, blue: 0xFF / 255)
    static let ledOff = Color(red: 0x33 / 255, green: 0x38 / 255, blue: 0x42 / 255)
    /// The dock's glass: rgba(20,22,27,.94).
    static let card = Color(red: 20 / 255, green: 22 / 255, blue: 27 / 255).opacity(0.94)
}

/// The app's listening wave (Liquid Dock): the prototype's bar heights, each easing down to 45 %
/// and back, neighbours a beat apart. The OS cannot loop animations in a Live Activity, so every
/// update (about once a second while audio flows) moves the ripple a quarter turn on and the
/// view eases there across the second: one continuous ripple.
enum CaptureRipple {
    static let levels: [Double] = [
        0.22, 0.35, 0.5, 0.3, 0.62, 0.8, 0.45, 0.28, 0.55, 0.9, 0.7, 0.38, 0.25, 0.42, 0.66, 0.52, 0.3, 0.2, 0.35, 0.58,
        0.76, 0.6, 0.4, 0.33, 0.48, 0.7, 0.85, 0.5, 0.3, 0.24, 0.4, 0.62, 0.45, 0.3, 0.52, 0.72, 0.56, 0.36, 0.28, 0.44,
        0.6, 0.8, 0.64, 0.4, 0.3, 0.5, 0.66, 0.42, 0.3, 0.26,
    ]

    /// Height factor of bar [index] at update [tick] (bins of 125 ms: 8 a second).
    static func pulse(_ index: Int, tick: Int) -> Double {
        let phase = (Double(tick) / 32 + Double(index % 13) * 0.13 / 1.6).truncatingRemainder(dividingBy: 1)
        return 1 - 0.55 * (0.5 - 0.5 * cos(2 * Double.pi * phase))
    }
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
                // A live wave in the LED blue, like the bars of a call: any device, one mark.
                CaptureMiniWave(snapshot: snapshot)
                    .padding(.leading, 4)
            } compactTrailing: {
                CaptureCompactClock(snapshot: snapshot)
            } minimal: {
                CaptureMiniWave(snapshot: snapshot)
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

/// LockScreen.json (393 pt): 14 pt top/bottom, 16 pt sides, a 48 pt row
/// (36 pt pendant, 12 pt gap, title/subtitle, 30 pt clock), 12 pt, a 26 pt
/// waveform, 12 pt, 40 pt buttons.
@available(iOS 16.1, *)
struct CaptureLockScreenView: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                CapturePendant(active: snapshot.isReceivingAudio, size: 36 * CaptureLayout.heroScale)
                CaptureStatus(snapshot: snapshot, showSource: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                CaptureClock(snapshot: snapshot, size: 30)
            }
            .frame(minHeight: 48)
            CaptureWaveform(snapshot: snapshot, height: 26)
            CaptureActions(snapshot: snapshot, height: 40, secondaryFill: 0.12)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .foregroundStyle(CapturePalette.label)
        // glass-thick top highlight: rgba(255,255,255,.06) fading out by 50%.
        .background(LinearGradient(stops: [
            .init(color: .white.opacity(0.06), location: 0),
            .init(color: .clear, location: 0.5),
        ], startPoint: .top, endPoint: .bottom))
        .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
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
        case "paused", "interrupted": return "Paused"
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
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(CapturePalette.label)
                .lineLimit(1)
            if !titleOnly {
                subtitle
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
        .multilineTextAlignment(.trailing)
        .foregroundStyle(CapturePalette.label)
        .lineLimit(1)
        .accessibilityLabel(Text("Recording duration"))
    }
}

/// The Omi orb (the app's `OmiOrb`): the device's dark dome seen straight on, one LED near its
/// top, in the live blue with its glow while audio is captured, grey otherwise.
struct CapturePendant: View {
    let active: Bool
    let size: CGFloat

    var body: some View {
        let led = max(4, size * 0.13)
        ZStack {
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: Color(red: 0x7A / 255, green: 0x80 / 255, blue: 0x8A / 255), location: 0),
                    .init(color: Color(red: 0x40 / 255, green: 0x45 / 255, blue: 0x4E / 255), location: 0.20),
                    .init(color: Color(red: 0x1B / 255, green: 0x1E / 255, blue: 0x24 / 255), location: 0.52),
                    .init(color: Color(red: 0x0C / 255, green: 0x0D / 255, blue: 0x10 / 255), location: 0.80),
                    .init(color: Color(red: 0x08 / 255, green: 0x09 / 255, blue: 0x0B / 255), location: 1),
                ], center: UnitPoint(x: 0.68, y: 0.24), startRadius: 0, endRadius: size * 0.72))
                .overlay(Circle().strokeBorder(Color.white.opacity(0.25), lineWidth: 0.5))
            Group {
                if active {
                    Circle()
                        .fill(CapturePalette.led)
                        .shadow(color: CapturePalette.led.opacity(0.6), radius: 4)
                } else {
                    Circle().fill(CapturePalette.ledOff)
                }
            }
            .frame(width: led, height: led)
            .offset(y: -size * 0.18)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// The listening wave on the Lock Screen and in the expanded island: the app's ripple (bars
/// 2 pt wide, 2.2 pt apart, heights from the prototype). While audio flows each update eases the
/// ripple on across the second; heard voice lifts it to full height, a quiet room keeps it softer.
/// Paused, it settles to a hairline; a source that cannot be metered shows the still wave.
@available(iOS 16.1, *)
private struct CaptureWaveform: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    private static let barWidth: CGFloat = 2
    private static let gap: CGFloat = 2.2

    var body: some View {
        let state = snapshot.state
        GeometryReader { geometry in
            // Never derive layout from an unbounded proposal; it cannot be placed.
            let width = geometry.size.width.isFinite ? max(0, geometry.size.width) : 0
            let count = max(1, Int((width + Self.gap) / (Self.barWidth + Self.gap)))
            if !state.levels.isEmpty {
                let amplitude = state.voice ? 1.0 : 0.62
                HStack(alignment: .center, spacing: Self.gap) {
                    ForEach(0..<count, id: \.self) { index in
                        Capsule()
                            .fill(CapturePalette.label.opacity(0.92))
                            .frame(
                                width: Self.barWidth,
                                height: barHeight(index, amplitude: amplitude, tick: state.levelsEnd)
                            )
                    }
                }
                .frame(width: width, height: height, alignment: .leading)
                .animation(.easeInOut(duration: 1.0), value: state.levelsEnd)
            } else if state.metered || state.paused {
                // Nothing to draw: one hairline instead of a row of dots.
                Capsule()
                    .fill(CapturePalette.label.opacity(0.24))
                    .frame(width: width, height: 1.5)
                    .frame(width: width, height: height)
            } else {
                HStack(alignment: .center, spacing: Self.gap) {
                    ForEach(0..<count, id: \.self) { index in
                        Capsule()
                            .fill(CapturePalette.label.opacity(snapshot.isReceivingAudio ? 0.55 : 0.2))
                            .frame(width: Self.barWidth, height: barHeight(index, amplitude: 0.8, tick: 0))
                    }
                }
                .frame(width: width, height: height, alignment: .leading)
            }
        }
        .frame(height: height)
        .clipped()
        .accessibilityHidden(true)
    }

    private func barHeight(_ index: Int, amplitude: Double, tick: Int) -> CGFloat {
        let base = CaptureRipple.levels[index % CaptureRipple.levels.count]
        let h = height * CGFloat(base * amplitude * CaptureRipple.pulse(index, tick: tick))
        return max(3, h)
    }
}

/// The compact island's live mark, like the bars of a call: five capsules in the LED blue that
/// ripple with the listening wave across each update. Grey and low when nothing is heard.
@available(iOS 16.1, *)
struct CaptureMiniWave: View {
    let snapshot: CaptureSnapshot
    private static let arch: [CGFloat] = [0.62, 0.86, 1, 0.86, 0.62]

    var body: some View {
        let state = snapshot.state
        let live = snapshot.isReceivingAudio && !state.levels.isEmpty
        HStack(alignment: .center, spacing: 2.2) {
            ForEach(0..<5, id: \.self) { index in
                Capsule()
                    .fill(live ? CapturePalette.led : CapturePalette.secondary.opacity(0.55))
                    .frame(width: 2.6, height: barHeight(index, live: live, voice: state.voice, tick: state.levelsEnd))
            }
        }
        .frame(width: 22, height: 18)
        .animation(.easeInOut(duration: 0.9), value: state.levelsEnd)
        .accessibilityHidden(true)
    }

    private func barHeight(_ index: Int, live: Bool, voice: Bool, tick: Int) -> CGFloat {
        guard live else { return 3 }
        let amplitude: CGFloat = voice ? 1 : 0.7
        return max(3, 18 * Self.arch[index] * amplitude * CGFloat(CaptureRipple.pulse(index * 3, tick: tick)))
    }
}

/// Equal capsules 8 pt apart: secondary rgba(255,255,255,.12/.14), primary
/// #ECEEF2 with ink text, 15 pt / 600.
@available(iOS 16.1, *)
private struct CaptureActions: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    let secondaryFill: Double

    private var state: OmiCaptureAttributes.ContentState { snapshot.state }

    var body: some View {
        if #available(iOS 17.0, *), !snapshot.isStale, state.status != "ended" {
            HStack(spacing: 8) {
                // Resume is offered only after the user paused; recovery states keep Pause.
                if state.canPause {
                    let resume = state.status == "paused"
                    action(resume ? "Resume" : "Pause", value: resume ? "resume" : "pause", enabled: true)
                }
                // Pendant capture keeps listening after a conversation ends; phone capture stops.
                action(state.source == "phone" ? "Stop" : "End Conversation",
                       value: "finish", enabled: state.canFinish, primary: true)
            }
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
        }
    }

    @available(iOS 17.0, *)
    private func action(_ label: LocalizedStringKey, value: String, enabled: Bool, primary: Bool = false) -> some View {
        // An unavailable primary action drops to the secondary pill so its label stays legible.
        let available = enabled && !state.busy
        let filled = primary && available
        return Button(intent: OmiCaptureIntent(recordingId: snapshot.recordingId,
                                               revision: state.conversationRevision, action: value)) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .lineLimit(1)
                .frame(maxWidth: .infinity, minHeight: height)
                .foregroundStyle(filled ? CapturePalette.ink : CapturePalette.label.opacity(available ? 1 : 0.5))
                .background(filled ? CapturePalette.label : Color.white.opacity(secondaryFill), in: Capsule())
        }
        .buttonStyle(.plain)
        .disabled(!available)
    }
}
