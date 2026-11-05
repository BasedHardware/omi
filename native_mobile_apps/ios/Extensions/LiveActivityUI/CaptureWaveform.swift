import SwiftUI

/// omi-liquid-dock2.html: fixed 2 pt bars, 2.2 pt gaps, a 1.6 s breath and
/// 0.13 s phase offsets repeating every 13 bars. While capture runs, the system
/// animates the breath on its own clock regardless of speech, with no activity
/// updates. Stopped, paused or finished, the bars lie flat in a line.
struct CaptureWaveform: View {
    /// Audio is coming in (or, for a run, Omi is working).
    let running: Bool
    /// The breath's clock starts here.
    let startedAt: Date
    let height: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced
    @Environment(\.redactionReasons) private var redactionReasons
    private static let barWidth: CGFloat = 2
    private static let gap: CGFloat = 2.2
    /// `@keyframes lvl{50%{transform:scaleY(.45)}}`.
    private static let exhaled: CGFloat = 0.45
    private static let ripple = 13
    nonisolated static let period = 1.6
    private static let phaseOffset = 0.13
    /// Every bar's height while capture is not running: the wave's shortest bar.
    private static let flat: CGFloat = 3
    /// The design's `lv` list: bar heights as a share of the strip.
    private static let levels: [CGFloat] = [
        0.22, 0.35, 0.5, 0.3, 0.62, 0.8, 0.45, 0.28, 0.55, 0.9, 0.7, 0.38, 0.25, 0.42, 0.66, 0.52, 0.3,
        0.2, 0.35, 0.58, 0.76, 0.6, 0.4, 0.33, 0.48, 0.7, 0.85, 0.5, 0.3, 0.24, 0.4, 0.62, 0.45, 0.3,
        0.52, 0.72, 0.56, 0.36, 0.28, 0.44, 0.6, 0.8, 0.64, 0.4, 0.3, 0.5, 0.66, 0.42, 0.3, 0.26,
    ]

    /// Bar heights at `seconds` of capture. CSS's negative delays start neighboring
    /// bars at different phases; the breath is 1 at phase 0 and `exhaled` at its middle.
    private func heights(count: Int, at seconds: Double?) -> [CGFloat] {
        (0 ..< count).map { index in
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
        let time = Date.now.timeIntervalSince(startedAt)
        GeometryReader { geometry in
            // Never derive layout from an unbounded proposal; it cannot be placed.
            let width = geometry.size.width.isFinite ? max(0, geometry.size.width) : 0
            let count = max(1, Int((width + Self.gap) / (Self.barWidth + Self.gap)))
            Group {
                if let flipbook {
                    ZStack {
                        ForEach(0 ..< CaptureFlipbook.frames, id: \.self) { frame in
                            CaptureBars(heights: heights(count: count, at: flipbook.time(of: frame)),
                                        width: Self.barWidth, gap: Self.gap)
                                .mask { flipbook.window(for: frame, startedAt: startedAt.timeIntervalSince1970) }
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
struct CaptureFlipbook {
    /// 20 frames a second. Each window costs one system clock; iOS 18 stalls with
    /// a hundred or more in a card.
    static let frames = 32
    private static let radius: CGFloat = 10000
    private static let windowHeight: CGFloat = 400
    private let turn: any ViewModifier

    /// Played where it was verified on a card (iOS 18, 26, 27, in the Flutter app).
    @MainActor static let shared: CaptureFlipbook? = CaptureClockRotation.effect(period: CaptureWaveform.period)
        .map(CaptureFlipbook.init)

    /// Seconds of capture that `frame` shows: the middle of its slot.
    func time(of frame: Int) -> Double {
        (Double(frame) + 0.5) / Double(Self.frames) * CaptureWaveform.period
    }

    /// Covers the strip while capture time is within `frame`'s slot of the breath.
    @MainActor func window(for frame: Int, startedAt: Double) -> some View {
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
enum CaptureClockRotation {
    static func effect(period: Double) -> (any ViewModifier)? {
        guard let type = _typeByName("9WidgetKit24_ClockHandRotationEffectV")
            as? any(ViewModifier & Decodable).Type else { return nil }
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
        func apply(_ effect: some ViewModifier) -> AnyView {
            AnyView(modifier(effect))
        }
        return apply(effect)
    }
}
