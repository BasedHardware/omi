import ActivityKit
import SwiftUI
import UIKit
import WidgetKit
#if compiler(>=6.4)
import AppIntents
#endif

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
    /// Capture needs the user: paused, or the pendant unheard.
    static let attention = Color(red: 0xFF / 255, green: 0xB5 / 255, blue: 0x47 / 255)
    /// The pendant is about to stop capturing.
    static let critical = Color(red: 0xFF / 255, green: 0x7A / 255, blue: 0x6E / 255)
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

    /// Transcription can reconnect while audio is still captured and saved.
    var isReceivingAudio: Bool {
        !isStale && !state.paused && ["listening", "recording", "reconnecting"].contains(state.status)
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
            CaptureCard(snapshot: context.omiSnapshot)
                .activityBackgroundTint(CapturePalette.card)
                .activitySystemActionForegroundColor(CapturePalette.label)
                .widgetURL(captureURL(context.attributes.recordingId))
        } dynamicIsland: { context in
            let snapshot = context.omiSnapshot
            if let notice = snapshot.notice {
                return noticeIsland(snapshot: snapshot, notice: notice, id: context.attributes.recordingId)
            }
            let island = DynamicIsland {
                // Island.dc.html: 372 x 172 with 18/22 padding, one 40 pt row, a
                // 22 pt waveform and 38 pt buttons, 12 pt apart. iOS caps the
                // expanded island near 160 pt and puts the camera between the
                // leading and trailing regions, so the row is split around it and
                // the subtitle (no room beside the camera on any iPhone) is left
                // to the Lock Screen card.
                DynamicIslandExpandedRegion(.leading) {
                    CaptureIslandLeading(snapshot: snapshot)
                        .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    CaptureClock(snapshot: snapshot, size: 30)
                        .frame(maxHeight: .infinity, alignment: .center)
                        // Clear of the island's ~44 pt top corner curve.
                        .padding(.top, 6)
                        .padding(.trailing, 4)
                        .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    // Measured on a 402 pt iPhone: the bottom region starts ~78 pt
                    // into a 160 pt island, which leaves exactly 22 + 10 + 38.
                    VStack(spacing: 10) {
                        CaptureWaveform(snapshot: snapshot, height: 22)
                        CaptureActions(snapshot: snapshot, height: 38, secondaryFill: 0.14)
                    }
                    .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
                }
            } compactLeading: {
                // HomeScreen.json: 20 pt pendant, 10 pt from the island edge.
                CapturePendant(active: snapshot.isReceivingAudio, size: 20)
                    .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
            } compactTrailing: {
                // Turned sideways the trailing slot is about as wide as the island, so the
                // clock gives way to a dot rather than clipping to "2:1".
                ViewThatFits(in: .horizontal) {
                    CaptureCompactClock(snapshot: snapshot)
                    Circle().fill(CapturePalette.led).frame(width: 8, height: 8)
                }
                    .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
            } minimal: {
                CapturePendant(active: snapshot.isReceivingAudio, size: 20)
                    .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
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

/// Pendant capture shows a card only while it needs the user (CapturePresentationPolicy): one
/// glyph and one value, and a button only where a tap fixes it.
@available(iOS 16.1, *)
private func noticeIsland(snapshot: CaptureSnapshot, notice: CaptureNotice, id: String) -> DynamicIsland {
    let island = DynamicIsland {
        DynamicIslandExpandedRegion(.leading) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    CaptureNoticeGlyph(notice: notice, size: 32)
                    CaptureNoticeTitle(snapshot: snapshot, notice: notice).fixedSize()
                }
                CaptureNoticeGlyph(notice: notice, size: 32)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .padding(.top, 6)
            .padding(.leading, 4)
            .dynamicTypeSize(...DynamicTypeSize.large)
        }
        DynamicIslandExpandedRegion(.trailing) {
            CaptureNoticeValue(snapshot: snapshot, notice: notice, size: 22)
                .frame(maxHeight: .infinity, alignment: .center)
                .padding(.top, 6)
                .padding(.trailing, 4)
        }
        DynamicIslandExpandedRegion(.bottom) {
            VStack(spacing: 10) {
                // The longest title has no room beside the camera.
                if notice == .unheard {
                    CaptureNoticeTitle(snapshot: snapshot, notice: notice)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                CaptureNoticeDetail(snapshot: snapshot, notice: notice, height: 38)
            }
        }
    } compactLeading: {
        // The pendant says this is Omi; the symbol says what is wrong. Values wait for the
        // expanded island, so nothing here can clip when the island turns sideways.
        CapturePendant(active: snapshot.isReceivingAudio, size: 20)
    } compactTrailing: {
        CaptureNoticeSymbol(notice: notice).font(.system(size: 15, weight: .semibold))
            .padding(.trailing, 4)
    } minimal: {
        CapturePendant(active: snapshot.isReceivingAudio, size: 20)
            .overlay(alignment: .bottomTrailing) {
                Circle().fill(notice.tint).frame(width: 8, height: 8)
                    .overlay(Circle().stroke(.black, lineWidth: 1.5))
            }
    }
    .widgetURL(captureURL(id))
    .keylineTint(notice.tint)
    if #available(iOS 17.0, *) {
        return island.contentMargins(.horizontal, 12, for: .expanded)
    }
    return island
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

/// The Lock Screen presentation: a notice when capture needs the user, else the recording card.
@available(iOS 16.1, *)
struct CaptureCard: View {
    let snapshot: CaptureSnapshot

    var body: some View {
        if let notice = snapshot.notice {
            CaptureNoticeLockScreenView(snapshot: snapshot, notice: notice)
        } else {
            CaptureLockScreenView(snapshot: snapshot)
        }
    }
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
        .modifier(CaptureEndTransition(ended: snapshot.state.status == "ended"))
    }
}

/// End settles the content before the system dismisses the card. Recording has
/// already finished; this transition never delays capture or processing.
@available(iOS 16.1, *)
private struct CaptureEndTransition: ViewModifier {
    let ended: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced

    func body(content: Content) -> some View {
        content
            .opacity(ended ? 0 : 1)
            .scaleEffect(ended && !reduceMotion && !luminanceReduced ? 0.98 : 1)
            .animation(reduceMotion || luminanceReduced ? nil :
                .timingCurve(0.42, 0, 0.58, 1, duration: 0.2), value: ended)
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
        // The pendant's audio is not verified yet: no Listening claim, as in the app.
        case "unverified": return "Omi pendant"
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
        // The title already names the pendant.
        if state.status == "unverified" { return detail.map { Text($0) } ?? Text(verbatim: "") }
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
            if snapshot.isStale || state.status == "unverified" {
                Text("—")
            } else if state.paused || state.status == "ended" {
                // Frozen value in the same format the live timer uses.
                let seconds = max(0, state.elapsed)
                Text(seconds >= 3600
                    ? String(format: "%d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60)
                    : String(format: "%d:%02d", seconds / 60, seconds % 60))
            } else {
                // A live timer reserves width for its range's longest value, so
                // the range ends at the next hour; the app republishes just after
                // each hour to extend it.
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

/// omi-liquid-dock2.html: fixed 2 pt bars, 2.2 pt gaps, a 1.6 s breath and
/// 0.13 s phase offsets repeating every 13 bars. While capture runs, the system
/// animates the breath on its own clock regardless of speech, with no activity
/// updates. Stopped, paused or finished, the bars lie flat in a line.
@available(iOS 16.1, *)
private struct CaptureWaveform: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced
    @Environment(\.redactionReasons) private var redactionReasons
    private static let barWidth: CGFloat = 2
    private static let gap: CGFloat = 2.2
    /// `@keyframes lvl{50%{transform:scaleY(.45)}}`.
    private static let exhaled: CGFloat = 0.45
    private static let ripple = 13
    static let period = 1.6
    private static let phaseOffset = 0.13
    /// Every bar's height while capture is not running: the wave's shortest bar.
    private static let flat: CGFloat = 3
    /// The design's `lv` list: bar heights as a share of the strip.
    private static let levels: [CGFloat] = [
        0.22, 0.35, 0.5, 0.3, 0.62, 0.8, 0.45, 0.28, 0.55, 0.9, 0.7, 0.38, 0.25, 0.42, 0.66, 0.52, 0.3,
        0.2, 0.35, 0.58, 0.76, 0.6, 0.4, 0.33, 0.48, 0.7, 0.85, 0.5, 0.3, 0.24, 0.4, 0.62, 0.45, 0.3,
        0.52, 0.72, 0.56, 0.36, 0.28, 0.44, 0.6, 0.8, 0.64, 0.4, 0.3, 0.5, 0.66, 0.42, 0.3, 0.26,
    ]

    private var running: Bool {
        !snapshot.isStale && !snapshot.state.paused && !["ended", "unverified"].contains(snapshot.state.status)
    }

    /// Seconds of capture, the breath's clock. Start shifts `startedAt` by the
    /// stopped time.
    private var captureTime: Double {
        Date().timeIntervalSince1970 - snapshot.state.startedAt
    }

    /// Bar heights at `seconds` of capture. CSS's negative delays start neighboring
    /// bars at different phases; the breath is 1 at phase 0 and `exhaled` at its middle.
    private func heights(count: Int, at seconds: Double?) -> [CGFloat] {
        (0..<count).map { index in
            let full = max(3, height * Self.levels[index % Self.levels.count])
            guard let seconds else { return full }
            let time = (seconds + Double(index % Self.ripple) * Self.phaseOffset)
                .truncatingRemainder(dividingBy: Self.period)
            let breath = (1 - cos(time / Self.period * 2 * .pi)) / 2
            return full * (1 - (1 - Self.exhaled) * CGFloat(breath))
        }
    }

    var body: some View {
        let still = reduceMotion || luminanceReduced
        // The card is archived once per environment, within a size limit. The locked Lock Screen
        // shows the privacy copy, so it moves too; only the loading placeholder holds still.
        let flipbook = running && !still && !redactionReasons.contains(.placeholder) ? CaptureFlipbook.shared : nil
        let time = captureTime
        GeometryReader { geometry in
            // Never derive layout from an unbounded proposal; it cannot be placed.
            let width = geometry.size.width.isFinite ? max(0, geometry.size.width) : 0
            let count = max(1, Int((width + Self.gap) / (Self.barWidth + Self.gap)))
            Group {
                if let flipbook {
                    ZStack {
                        ForEach(0..<CaptureFlipbook.frames, id: \.self) { frame in
                            CaptureBars(heights: heights(count: count, at: flipbook.time(of: frame)),
                                        width: Self.barWidth, gap: Self.gap)
                                .mask { flipbook.window(for: frame, startedAt: snapshot.state.startedAt) }
                        }
                    }
                } else if running {
                    // Reduce Motion and Always-On rest at full height; without the flipbook the
                    // wave shows the phase it had when the card was drawn.
                    CaptureBars(heights: heights(count: count, at: still ? nil : time), width: Self.barWidth, gap: Self.gap)
                } else {
                    CaptureBars(heights: Array(repeating: Self.flat, count: count), width: Self.barWidth, gap: Self.gap)
                }
            }
            .frame(width: width, height: height)
            .clipped()
        }
        .frame(height: height)
        .foregroundStyle(CapturePalette.label)
        .accessibilityHidden(true)
    }
}

/// Capsule bars, centered on the strip and drawn as one path.
@available(iOS 16.1, *)
private struct CaptureBars: Shape {
    let heights: [CGFloat]
    let width: CGFloat
    let gap: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let used = CGFloat(heights.count) * (width + gap) - gap
        let left = rect.midX - used / 2
        for (index, height) in heights.enumerated() {
            let bar = CGRect(x: left + CGFloat(index) * (width + gap), y: rect.midY - height / 2,
                             width: width, height: height)
            path.addRoundedRect(in: bar, cornerSize: CGSize(width: width / 2, height: width / 2))
        }
        return path
    }
}

/// The breath as a flipbook the system plays on its own clock: `frames` exact
/// phases of the wave, each behind a window that one turn per breath brings over
/// the strip for its share of the loop. The windows ride a circle far below the
/// strip, so each crosses it in under 10 ms; neighbors overlap slightly, so the strip
/// is never empty.
@available(iOS 16.1, *)
struct CaptureFlipbook {
    /// 20 frames a second. Each window costs one system clock; iOS 18 stalls with
    /// a hundred or more in a card.
    static let frames = 32
    private static let radius: CGFloat = 10_000
    private static let windowHeight: CGFloat = 400
    private let turn: any ViewModifier

    /// Played only where it was verified on a card (iOS 18, 26, 27); earlier
    /// versions keep the still wave beside the ticking clock.
    static let shared: CaptureFlipbook? = {
        guard #available(iOS 18.0, *) else { return nil }
        return CaptureClockRotation.effect(period: CaptureWaveform.period).map(CaptureFlipbook.init)
    }()

    /// Seconds of capture that `frame` shows: the middle of its slot.
    func time(of frame: Int) -> Double {
        (Double(frame) + 0.5) / Double(Self.frames) * CaptureWaveform.period
    }

    /// Covers the strip while capture time is within `frame`'s slot of the breath.
    func window(for frame: Int, startedAt: Double) -> some View {
        let slot = 2 * Self.radius * CGFloat(tan(Double.pi / Double(Self.frames))) * 1.02
        // The clock turns with Unix time; offset it to capture time.
        let start = (startedAt / CaptureWaveform.period).truncatingRemainder(dividingBy: 1)
        let angle = -360 * ((Double(frame) + 0.5) / Double(Self.frames) + start)
        // iOS 18 turns about the center whatever the anchor, so the window is moved out
        // from its center, turned about it, and the pivot is then moved below the strip.
        return Rectangle()
            .frame(width: slot, height: Self.windowHeight)
            .offset(y: -Self.radius)
            .rotationEffect(.degrees(angle))
            .clockRotation(turn)
            .offset(y: Self.radius)
    }
}

/// The rotation WidgetKit's clock-hand widgets use. The system turns it on its
/// own clock, with no timeline or activity update. WidgetKit has shipped it since
/// iOS 16 without declaring it in the SDK, so it is decoded at run time; if it is
/// ever missing, the wave holds still instead.
@available(iOS 16.1, *)
enum CaptureClockRotation {
    static func effect(period: Double) -> (any ViewModifier)? {
        guard let type = _typeByName("9WidgetKit24_ClockHandRotationEffectV")
            as? any (ViewModifier & Decodable).Type else { return nil }
        // In GMT a day is a whole number of turns, so the angle is Unix time mod period.
        let json = #"{"period":\#(period),"timeZone":{"identifier":"GMT"},"anchor":[0.5,0.5],"honorIdealizedDate":false}"#
        func decode<Effect: ViewModifier & Decodable>(_: Effect.Type) -> (any ViewModifier)? {
            try? JSONDecoder().decode(Effect.self, from: Data(json.utf8))
        }
        return decode(type)
    }
}

private extension View {
    func clockRotation(_ effect: any ViewModifier) -> AnyView {
        func apply<Effect: ViewModifier>(_ effect: Effect) -> AnyView { AnyView(modifier(effect)) }
        return apply(effect)
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
        // No buttons without the card's App Intent (OmiCaptureIntents.swift).
        #if compiler(>=6.4)
        if #available(iOS 17.0, *), !snapshot.isStale, state.status != "ended" {
            HStack(spacing: 8) {
                // Shared by the Lock Screen and expanded Island. Start/Stop keep the existing
                // resume/pause behavior; Start is offered only after a user stops capture.
                if state.canPause {
                    if state.status != "paused" {
                        action("Stop", value: "pause", enabled: true)
                    } else if state.source != "phone" {
                        action("Start", value: "resume", enabled: true)
                    } else if #available(iOS 18.0, *) {
                        button("Start", intent: OmiCaptureRecordingIntent(
                            recordingId: snapshot.recordingId, revision: state.conversationRevision))
                    }
                    // iOS 17 has no audio recording intent, so a stopped phone mic starts again
                    // only in Omi, which tapping the card opens.
                }
                // End always closes this card, saving the conversation first when there is one
                // (LiveActivityManager).
                action("End", value: state.canFinish ? "finish" : "close", enabled: true, primary: true)
            }
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
        }
        #endif
    }

    #if compiler(>=6.4)
    @available(iOS 17.0, *)
    private func action(_ label: LocalizedStringKey, value: String, enabled: Bool, primary: Bool = false) -> some View {
        button(label, intent: OmiCaptureIntent(recordingId: snapshot.recordingId,
                                               revision: state.conversationRevision, action: value),
               enabled: enabled, primary: primary)
    }

    @available(iOS 17.0, *)
    private func button(_ label: LocalizedStringKey, intent: some AppIntent, enabled: Bool = true,
                        primary: Bool = false) -> some View {
        // Busy blocks duplicate intents without recoloring the whole action row.
        let available = enabled && !state.busy
        return Button(intent: intent) {
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
    #endif
}

/// The system's plain style dims every busy button. Keep these fills stable while
/// the intent is disabled; the status subtitle already explains that it is updating.
private struct CaptureActionStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}

// MARK: - Notices

@available(iOS 16.1, *)
extension CaptureSnapshot {
    var notice: CaptureNotice? { state.notice.flatMap(CaptureNotice.init(rawValue:)) }
}

extension CaptureNotice {
    var tint: Color { self == .battery ? CapturePalette.critical : CapturePalette.attention }

    var symbol: String {
        switch self {
        case .muted: return "mic.slash.fill"
        case .unheard: return "waveform.slash"
        case .battery: return "battery.25"
        }
    }
}

@available(iOS 16.1, *)
private struct CaptureNoticeSymbol: View {
    let notice: CaptureNotice

    var body: some View {
        Image(systemName: notice.symbol)
            .foregroundStyle(notice.tint)
            .accessibilityHidden(true)
    }
}

/// The notice's symbol on a tinted disc.
@available(iOS 16.1, *)
private struct CaptureNoticeGlyph: View {
    let notice: CaptureNotice
    let size: CGFloat

    var body: some View {
        CaptureNoticeSymbol(notice: notice)
            .font(.system(size: size * 0.47, weight: .semibold))
            .frame(width: size, height: size)
            .background(notice.tint.opacity(0.18), in: Circle())
    }
}

@available(iOS 16.1, *)
private struct CaptureNoticeTitle: View {
    let snapshot: CaptureSnapshot
    let notice: CaptureNotice

    private var title: LocalizedStringKey {
        if snapshot.isStale { return "Open Omi to reconnect" }
        if snapshot.state.actionFailed { return "Open Omi to continue" }
        switch notice {
        case .muted: return "Paused"
        case .unheard: return "No audio from pendant"
        case .battery: return "Omi pendant"
        }
    }

    var body: some View {
        Text(title)
            .contentTransition(.identity)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(CapturePalette.label)
            .lineLimit(1)
    }
}

/// How long capture has been paused or unheard, or the battery left.
@available(iOS 16.1, *)
private struct CaptureNoticeValue: View {
    let snapshot: CaptureSnapshot
    let notice: CaptureNotice
    @ScaledMetric private var size: CGFloat

    init(snapshot: CaptureSnapshot, notice: CaptureNotice, size: CGFloat) {
        self.snapshot = snapshot
        self.notice = notice
        _size = ScaledMetric(wrappedValue: size, relativeTo: .title)
    }

    var body: some View {
        Group {
            if snapshot.isStale {
                Text("—")
            } else if notice == .battery {
                Text(verbatim: "\(max(0, snapshot.state.pendantBattery ?? 0))%")
            } else {
                // A live count from when it began, in a slot sized for an hour or more.
                let since = Date(timeIntervalSince1970: snapshot.state.noticeSince ?? Date().timeIntervalSince1970)
                Text(timerInterval: since...since.addingTimeInterval(7 * 24 * 3600), countsDown: false)
                    .frame(width: size * 4.3, alignment: .trailing)
            }
        }
        .font(.system(size: size, weight: .semibold))
        .monospacedDigit()
        .multilineTextAlignment(.trailing)
        .contentTransition(.identity)
        .foregroundStyle(notice.tint)
        .lineLimit(1)
    }
}

/// Below the title: Start for a pause, the charge left for a low battery, nothing otherwise.
@available(iOS 16.1, *)
private struct CaptureNoticeDetail: View {
    let snapshot: CaptureSnapshot
    let notice: CaptureNotice
    let height: CGFloat

    var body: some View {
        switch notice {
        case .muted:
            CaptureNoticeResume(snapshot: snapshot, height: height)
        case .battery:
            GeometryReader { geometry in
                let level = CGFloat(min(100, max(0, snapshot.state.pendantBattery ?? 0))) / 100
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.12))
                    Capsule().fill(notice.tint).frame(width: max(6, geometry.size.width * level))
                }
            }
            .frame(height: 6)
            .accessibilityHidden(true)
        case .unheard:
            EmptyView()
        }
    }
}

@available(iOS 16.1, *)
private struct CaptureNoticeResume: View {
    let snapshot: CaptureSnapshot
    let height: CGFloat

    var body: some View {
        #if compiler(>=6.4)
        if #available(iOS 17.0, *), !snapshot.isStale, snapshot.state.canPause {
            Button(intent: OmiCaptureIntent(recordingId: snapshot.recordingId,
                                            revision: snapshot.state.conversationRevision, action: "resume")) {
                Text("Start")
                    .contentTransition(.identity)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(maxWidth: .infinity, minHeight: height)
                    .foregroundStyle(CapturePalette.ink)
                    .background(CapturePalette.label, in: Capsule())
            }
            .buttonStyle(CaptureActionStyle())
            .disabled(snapshot.state.busy)
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
        }
        #endif
    }
}

@available(iOS 16.1, *)
struct CaptureNoticeLockScreenView: View {
    let snapshot: CaptureSnapshot
    let notice: CaptureNotice

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                CaptureNoticeGlyph(notice: notice, size: 36)
                CaptureNoticeTitle(snapshot: snapshot, notice: notice)
                    .frame(maxWidth: .infinity, alignment: .leading)
                CaptureNoticeValue(snapshot: snapshot, notice: notice, size: 24)
            }
            .frame(height: 40)
            CaptureNoticeDetail(snapshot: snapshot, notice: notice, height: 40)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .foregroundStyle(CapturePalette.label)
        .dynamicTypeSize(...DynamicTypeSize.xLarge)
    }
}
