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
    static let ledOff = Color(red: 0x3A / 255, green: 0x40 / 255, blue: 0x4B / 255)
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

/// The pendant seen straight on: glass dome, machined rim, graphite core, one LED
/// (lib.py `pendant`: rim 0.86, core 0.70, LED max(4, 0.052 d) with its glow).
struct CapturePendant: View {
    let active: Bool
    let size: CGFloat

    var body: some View {
        let rim = size * 0.86
        let core = size * 0.70
        let led = max(4, size * 0.052)
        ZStack {
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: .white.opacity(0.06), location: 0),
                    .init(color: .white.opacity(0.05), location: 0.58),
                    .init(color: Color(red: 220 / 255, green: 228 / 255, blue: 240 / 255).opacity(0.17), location: 0.80),
                    .init(color: .white.opacity(0.07), location: 1),
                ], center: UnitPoint(x: 0.5, y: 0.42), startRadius: 0, endRadius: size * 0.77))
                .overlay(Circle().strokeBorder(Color.white.opacity(0.2), lineWidth: 0.5))
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: .clear, location: 0.76),
                    .init(color: Color(red: 205 / 255, green: 216 / 255, blue: 232 / 255).opacity(0.28), location: 0.84),
                    .init(color: Color(red: 236 / 255, green: 241 / 255, blue: 248 / 255).opacity(0.62), location: 0.91),
                    .init(color: Color(red: 205 / 255, green: 216 / 255, blue: 232 / 255).opacity(0.2), location: 0.97),
                    .init(color: .clear, location: 1),
                ], center: .center, startRadius: 0, endRadius: rim * 0.71))
                .frame(width: rim, height: rim)
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: Color(red: 0x7A / 255, green: 0x80 / 255, blue: 0x8A / 255), location: 0),
                    .init(color: Color(red: 0x40 / 255, green: 0x45 / 255, blue: 0x4E / 255), location: 0.20),
                    .init(color: Color(red: 0x1B / 255, green: 0x1E / 255, blue: 0x24 / 255), location: 0.52),
                    .init(color: Color(red: 0x0C / 255, green: 0x0D / 255, blue: 0x10 / 255), location: 0.80),
                    .init(color: Color(red: 0x08 / 255, green: 0x09 / 255, blue: 0x0B / 255), location: 1),
                ], center: UnitPoint(x: 0.68, y: 0.24), startRadius: 0, endRadius: core * 1.02))
                .frame(width: core, height: core)
            ledView.frame(width: led, height: led)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    @ViewBuilder private var ledView: some View {
        if active {
            // .pd-led: white core → #D2E6FF → #4C9BFF with a 3/12 px blue glow.
            Circle()
                .fill(RadialGradient(stops: [
                    .init(color: .white, location: 0),
                    .init(color: Color(red: 0xD2 / 255, green: 0xE6 / 255, blue: 0xFF / 255), location: 0.30),
                    .init(color: CapturePalette.led, location: 0.72),
                ], center: .center, startRadius: 0, endRadius: max(2, size * 0.026)))
                .shadow(color: CapturePalette.led.opacity(0.95), radius: 1.5)
                .shadow(color: CapturePalette.led.opacity(0.5), radius: 6)
        } else {
            Circle().fill(CapturePalette.ledOff)
        }
    }
}

/// Voice Memos-style strip (lib.py `wave_strip`: 2 pt bars, 2.5 pt gaps,
/// rgba(236,238,242,.55), left edge fading in over 24%). The OS cannot loop
/// animations in a Live Activity, so the app sends new loudness bins about once
/// a second while voice is heard and each update slides the strip left.
/// Silence settles it to a hairline. Unmetered sources keep the still strip.
@available(iOS 16.1, *)
private struct CaptureWaveform: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    private static let barWidth: CGFloat = 2
    private static let gap: CGFloat = 2.5

    var body: some View {
        let state = snapshot.state
        GeometryReader { geometry in
            // Never derive layout from an unbounded proposal; it cannot be placed.
            let width = geometry.size.width.isFinite ? max(0, geometry.size.width) : 0
            let count = max(1, Int((width + Self.gap) / (Self.barWidth + Self.gap)))
            // Metered bars are keyed by absolute bin, so an update slides them left
            // rather than redrawing them. The still strip is keyed by position.
            let origin = state.metered ? state.levelsEnd : 0
            if state.metered && !state.voice {
                // Nothing heard: one hairline instead of a row of dots.
                Capsule()
                    .fill(CapturePalette.label.opacity(opacity))
                    .frame(width: width, height: 1.5)
                    .frame(width: width, height: height)
            } else {
                HStack(alignment: .center, spacing: Self.gap) {
                    ForEach((origin - count + 1)...origin, id: \.self) { bin in
                        Capsule()
                            .fill(CapturePalette.label.opacity(opacity))
                            .frame(width: Self.barWidth, height: barHeight(age: origin - bin))
                    }
                }
                .frame(width: width, height: height, alignment: .trailing)
                .clipped()
            }
        }
        .frame(height: height)
        .mask(LinearGradient(stops: [
            .init(color: .clear, location: 0),
            .init(color: .black, location: 0.24),
            .init(color: .black, location: 1),
        ], startPoint: .leading, endPoint: .trailing))
        .accessibilityHidden(true)
    }

    private var opacity: Double {
        let state = snapshot.state
        if state.metered { return state.voice ? 0.55 : 0.28 }
        return snapshot.isReceivingAudio ? 0.55 : 0.2
    }

    private func barHeight(age: Int) -> CGFloat {
        let state = snapshot.state
        guard state.metered else { return max(3, height * Self.designLevel(age)) }
        // Silence is a hairline; heard audio rises from it (levels are a dB curve).
        guard state.voice, age < state.levels.count else { return 2 }
        let level = CGFloat(state.levels[state.levels.count - 1 - age]) / 100
        return max(2, height * level)
    }

    // lib.py `_hs(n, seed=1.0, lo=0.14)`.
    private static func designLevel(_ index: Int) -> CGFloat {
        let i = Double(index)
        let a = abs(sin(i * 0.37 + 1) * sin(i * 0.113 + 2.1))
        let b = abs(sin(i * 1.7 + 0.5)) * 0.35
        return CGFloat(0.14 + 0.86 * min(1, a * 0.85 + b * 0.5))
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
