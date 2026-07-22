import SwiftUI

/// The Omi identity as one continuous element across a whole voice turn. The
/// same 8 marks morph between two layouts and never cross-fade:
/// - listening / speaking: a horizontal audio waveform (the 8 marks become
///   bars that bounce to the mic level while you talk, and to the TTS output
///   level while Omi speaks);
/// - thinking: the 8 marks reform into the Omi dot-ring and rotate.
///
/// Rendered once (a persistent overlay in `NotchView`) so switching phase
/// animates the morph in place rather than swapping views.
struct NotchVoiceOrb: View {
  enum Mode: Equatable { case listening, thinking, speaking }
  let mode: Mode

  @State private var model = OrbModel()
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    TimelineView(.animation) { timeline in
      Canvas { context, size in
        let level: CGFloat
        switch mode {
        case .listening: level = CGFloat(AudioLevelMonitor.shared.microphoneLevel)
        case .speaking: level = CGFloat(AudioLevelMonitor.shared.playbackLevel)
        case .thinking: level = 0
        }
        model.advance(to: timeline.date, level: level, mode: mode, reduceMotion: reduceMotion)
        model.draw(into: &context, size: size)
      }
    }
    .accessibilityHidden(true)
  }
}

/// Per-frame state for `NotchVoiceOrb`: 8 marks that spring toward an audio
/// target (waveform), a `morph` scalar (0 = ring, 1 = bars) that eases on mode
/// change, and a rotation accumulator used only while it is a ring.
@MainActor
final class OrbModel {
  private static let count = 8

  private var values = [CGFloat](repeating: 0, count: count)
  private var velocities = [Double](repeating: 0, count: count)
  private var morph: CGFloat = 0
  private var rotation: Double = 0
  private var lastTime: CFTimeInterval?
  private var envelope: Double = 0

  private let phases: [Double] = (0..<count).map { Double($0) * 1.9 }
  private let speeds: [Double] = (0..<count).map { 6.0 + 2.5 * sin(Double($0) * 1.3) }

  // Underdamped spring -> visible bounce (same feel as VoiceWaveformBars).
  private let stiffness: Double = 200
  private let damping: Double = 10

  func advance(to date: Date, level: CGFloat, mode: NotchVoiceOrb.Mode, reduceMotion: Bool) {
    let now = date.timeIntervalSinceReferenceDate
    let dt = lastTime.map { min(0.032, max(0.0, now - $0)) } ?? (1.0 / 60.0)
    lastTime = now

    let bars = mode != .thinking
    let morphTarget: CGFloat = bars ? 1 : 0
    // Ease the layout morph so the logo ring visibly stretches into the
    // waveform (and back); snap when reduced motion is on.
    morph += (morphTarget - morph) * CGFloat(reduceMotion ? 1 : min(1, dt * 5))
    rotation += (mode == .thinking && !reduceMotion) ? dt * 2.4 : 0

    let lvl = Double(max(0, level))
    envelope = max(lvl, envelope - 0.7 * dt)
    let norm = envelope > 0.04 ? min(1.0, lvl / envelope) : 0.0
    let gained = pow(norm, 0.75)

    for i in 0..<Self.count {
      let target: Double
      if bars {
        let idle = 0.14 + 0.12 * (0.5 + 0.5 * sin(now * speeds[i] + phases[i]))
        let wobble = 0.55 + 0.45 * sin(now * speeds[i] + phases[i])
        target = max(idle, min(1.0, gained * wobble))
      } else {
        target = 0
      }
      let x = Double(values[i])
      let accel = stiffness * (target - x) - damping * velocities[i]
      velocities[i] += accel * dt
      values[i] = CGFloat(max(0.0, min(1.0, x + velocities[i] * dt)))
    }
  }

  func draw(into context: inout GraphicsContext, size: CGSize) {
    let n = Self.count
    let side = min(size.width, size.height)
    let center = CGPoint(x: size.width / 2, y: size.height / 2)
    // Match NotchOmiMark exactly so the ring reads as the Omi logo: the same 8
    // dots that then stretch into the waveform bars.
    let ringRadius = side * 0.33
    let dotDiameter = side * 0.18

    let span = size.width * 0.86
    let step = span / CGFloat(n)
    let barWidth = min(step * 0.5, 5)
    let minBarH = barWidth
    let maxBarH = size.height * 0.92
    let barStartX = (size.width - span) / 2 + step / 2

    for i in 0..<n {
      let angle = 2 * Double.pi * Double(i) / Double(n) - Double.pi / 2 + rotation
      let ringPoint = CGPoint(
        x: center.x + ringRadius * CGFloat(cos(angle)),
        y: center.y + ringRadius * CGFloat(sin(angle))
      )
      let barPoint = CGPoint(x: barStartX + step * CGFloat(i), y: center.y)
      let point = lerp(ringPoint, barPoint, morph)

      let barH = minBarH + (maxBarH - minBarH) * values[i]
      let markW = lerp(dotDiameter, barWidth, morph)
      let markH = lerp(dotDiameter, barH, morph)

      // Trailing fade while it's a ring (the thinking spinner); solid as bars.
      let trail = 1.0 - Double(i) * 0.09
      let opacity = lerp(CGFloat(trail), 1, morph)

      let rect = CGRect(
        x: point.x - markW / 2, y: point.y - markH / 2, width: markW, height: markH)
      context.fill(
        Path(roundedRect: rect, cornerRadius: markW / 2),
        with: .color(.white.opacity(Double(opacity)))
      )
    }
  }

  private func lerp(_ a: CGFloat, _ b: CGFloat, _ t: CGFloat) -> CGFloat { a + (b - a) * t }
  private func lerp(_ a: CGPoint, _ b: CGPoint, _ t: CGFloat) -> CGPoint {
    CGPoint(x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t))
  }
}
