import SwiftUI

/// Playful, compact mic visualizer shown in the floating control bar while
/// push-to-talk is active — a few chunky bars that bounce to the user's voice
/// (HeyClicky-style), replacing the old pulsing red dot.
///
/// Animation notes (this is what makes it actually move):
/// - `TimelineView(.animation)` is the clock. The Canvas closure **uses
///   `timeline.date`** every frame (via `model.advance(to:)`) so SwiftUI treats
///   the drawing as changed each tick and redraws — without referencing the
///   per-frame date the Canvas is cached and freezes (the original bug).
/// - We read `AudioLevelMonitor.shared.microphoneLevel` (one RMS scalar, ~5 Hz)
///   each frame and spring the bars toward it at 60fps, so 5 Hz data still looks
///   smooth. Per-bar phase + a center arch make it feel alive, not mechanical.
/// - `paused: !isActive` stops the loop when PTT isn't listening; the bars are a
///   live `@State` model (no retained history), so each session starts fresh and
///   never shows a frozen "last word."
struct VoiceWaveformBars: View {
    let isActive: Bool

    private static let barCount = 5
    private static let barWidth: CGFloat = 4
    private static let barSpacing: CGFloat = 3
    private static let barHeight: CGFloat = 18
    private static let fillGradient = Gradient(colors: [OmiColors.purpleAccent, OmiColors.purplePrimary])

    @State private var model: WaveBarsModel

    init(isActive: Bool) {
        self.isActive = isActive
        _model = State(initialValue: WaveBarsModel(barCount: Self.barCount))
    }

    private var width: CGFloat {
        let n = CGFloat(Self.barCount)
        return n * Self.barWidth + (n - 1) * Self.barSpacing
    }

    var body: some View {
        TimelineView(.animation(paused: !isActive)) { timeline in
            Canvas { context, size in
                let level = isActive ? CGFloat(AudioLevelMonitor.shared.microphoneLevel) : 0
                model.advance(to: timeline.date, level: level, active: isActive)
                draw(into: &context, size: size)
            }
        }
        .frame(width: width, height: Self.barHeight)
        .accessibilityHidden(true)
    }

    private func draw(into context: inout GraphicsContext, size: CGSize) {
        let minH: CGFloat = 2
        let maxH = size.height
        let step = Self.barWidth + Self.barSpacing
        let centerY = size.height / 2

        for i in 0..<Self.barCount {
            let x = CGFloat(i) * step
            let h = max(minH, minH + (maxH - minH) * model.values[i])
            let path = Path(
                roundedRect: CGRect(x: x, y: centerY - h / 2, width: Self.barWidth, height: h),
                cornerRadius: Self.barWidth / 2
            )
            context.fill(
                path,
                with: .linearGradient(
                    Self.fillGradient,
                    startPoint: CGPoint(x: x, y: centerY - h / 2),
                    endPoint: CGPoint(x: x, y: centerY + h / 2)
                )
            )
        }
    }
}

/// Per-bar bounce state for `VoiceWaveformBars`. Advanced once per frame from a
/// single mic level. Reference type so it persists across the Canvas redraws.
@MainActor
final class WaveBarsModel {
    let barCount: Int
    private(set) var values: [CGFloat]
    private var velocities: [Double]

    private let phases: [Double]
    private let speeds: [Double]
    private let weights: [Double]
    private var lastTime: CFTimeInterval?
    private var envelope: Double = 0 // decaying recent-peak follower for auto-gain

    // Underdamped spring -> visible bounce/overshoot (ζ ≈ 0.35).
    private let stiffness: Double = 200
    private let damping: Double = 10

    init(barCount: Int) {
        self.barCount = barCount
        values = Array(repeating: 0, count: barCount)
        velocities = Array(repeating: 0, count: barCount)
        phases = (0..<barCount).map { Double($0) * 1.9 }
        speeds = (0..<barCount).map { 6.0 + 2.5 * sin(Double($0) * 1.3) }
        // Center bars taller -> a friendly arch.
        let mid = Double(barCount - 1) / 2
        weights = (0..<barCount).map { i in
            0.72 + 0.45 * (1.0 - abs(Double(i) - mid) / max(mid, 1.0))
        }
    }

    func advance(to date: Date, level: CGFloat, active: Bool) {
        let now = date.timeIntervalSinceReferenceDate
        // Clamp dt small so the spring integration stays stable.
        let dt: Double = lastTime.map { min(0.032, max(0.0, now - $0)) } ?? (1.0 / 60.0)
        lastTime = now

        let lvl = Double(max(0, level))
        // Auto-gain: normalize against a decaying recent peak so the bars use the
        // full height no matter how loud the mic actually is (fixes "barely moving").
        envelope = max(lvl, envelope - 0.7 * dt)
        let norm = envelope > 0.04 ? min(1.0, lvl / envelope) : 0.0
        let gained = pow(norm, 0.75)

        for i in 0..<barCount {
            // Lively idle bounce so it always feels alive while listening.
            let idle = active ? (0.14 + 0.12 * (0.5 + 0.5 * sin(now * speeds[i] + phases[i]))) : 0.0
            let wobble = 0.55 + 0.45 * sin(now * speeds[i] + phases[i])
            let target = max(idle, min(1.0, gained * weights[i] * wobble))

            // Critically-underdamped spring (semi-implicit Euler) -> bouncy overshoot.
            let x = Double(values[i])
            let accel = stiffness * (target - x) - damping * velocities[i]
            velocities[i] += accel * dt
            let nx = x + velocities[i] * dt
            values[i] = CGFloat(max(0.0, min(1.0, nx)))
        }
    }
}
