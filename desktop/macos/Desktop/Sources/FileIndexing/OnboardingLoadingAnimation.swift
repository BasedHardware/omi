import OmiTheme
import SwiftUI

/// Orbital ring loading animation for the onboarding file-indexing step.
/// Renders a partial gradient arc that fills as `progress` increases,
/// orbiting glow particles, and a breathing center pulse.
///
/// Every mark was `Color.white` on a near-black card, which on the light-pinned panel is the panel
/// — the whole animation drew nothing. It is `Ink` throughout now, so it darkens on light glass and
/// lightens on a dark mat from one set of values.
struct OnboardingLoadingAnimation: View {
  /// 0.0 … 1.0
  var progress: Double

  var body: some View {
    // `paused:` is what Reduce Motion means to a `TimelineView`: the schedule stops advancing, so
    // the orbit and the breath hold still while `progress` — which is information, not motion —
    // keeps redrawing the arc. A perpetual animation that ignores the setting is the one kind that
    // can never be waited out.
    TimelineView(.animation(paused: InkReduceMotion.isEnabled)) { timeline in
      let time = timeline.date.timeIntervalSinceReferenceDate
      Canvas { context, size in
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let radius: CGFloat = min(size.width, size.height) / 2 - 20

        // --- Center pulse ---
        let pulseScale = 0.15 + 0.08 * sin(time * 1.8)
        let pulseRadius = radius * pulseScale
        let pulseGradient = Gradient(colors: [
          Ink.primary.opacity(0.4),
          Ink.primary.opacity(0.0),
        ])
        let pulseShading = GraphicsContext.Shading.radialGradient(
          pulseGradient,
          center: center,
          startRadius: 0,
          endRadius: pulseRadius
        )
        context.fill(
          Circle().path(
            in: CGRect(
              x: center.x - pulseRadius,
              y: center.y - pulseRadius,
              width: pulseRadius * 2,
              height: pulseRadius * 2
            )), with: pulseShading)

        // --- Orbital ring (background track) ---
        var trackPath = Path()
        trackPath.addArc(
          center: center, radius: radius,
          startAngle: .degrees(0), endAngle: .degrees(360),
          clockwise: false)
        // `separator` and not the reading rung: this ring is the *unfilled* half of a progress
        // readout, and `Ink.secondary` is `labelColor` at 0.80 — beside the `Ink.primary` arc drawn
        // over it at 1.0 the two are the same mark, so the ring would read as already complete. The
        // faint-line token is what a track is.
        context.stroke(
          trackPath, with: .color(Ink.separator),
          lineWidth: 3)

        // --- Orbital ring (filled arc) ---
        let arcEnd = progress * 360.0
        if arcEnd > 0 {
          var arcPath = Path()
          arcPath.addArc(
            center: center, radius: radius,
            startAngle: .degrees(-90),
            endAngle: .degrees(-90 + arcEnd),
            clockwise: false)
          let arcGradient = Gradient(colors: [
            Ink.primary,
            Ink.secondary,
          ])
          context.stroke(
            arcPath,
            with: .linearGradient(
              arcGradient,
              startPoint: CGPoint(x: center.x, y: center.y - radius),
              endPoint: CGPoint(x: center.x + radius, y: center.y)),
            style: StrokeStyle(lineWidth: 3, lineCap: .round))
        }

        // --- Orbiting particles ---
        let particleSpeeds: [Double] = [0.6, 0.9, 1.3, 1.7]
        let particleSizes: [CGFloat] = [4, 3, 3.5, 2.5]
        let particleOpacities: [Double] = [0.9, 0.7, 0.8, 0.6]

        for i in 0..<particleSpeeds.count {
          let angle = time * particleSpeeds[i] + Double(i) * .pi / 2
          let px = center.x + cos(angle) * radius
          let py = center.y + sin(angle) * radius
          let pSize = particleSizes[i]
          let pRect = CGRect(x: px - pSize, y: py - pSize, width: pSize * 2, height: pSize * 2)

          // Glow
          let glowSize = pSize * 3
          let glowRect = CGRect(x: px - glowSize, y: py - glowSize, width: glowSize * 2, height: glowSize * 2)
          let glowGradient = Gradient(colors: [
            Ink.secondary.opacity(particleOpacities[i] * 0.5),
            Ink.secondary.opacity(0),
          ])
          context.fill(
            Circle().path(in: glowRect),
            with: .radialGradient(
              glowGradient, center: CGPoint(x: px, y: py),
              startRadius: 0, endRadius: glowSize))

          // Dot
          context.fill(
            Circle().path(in: pRect),
            with: .color(Ink.primary.opacity(particleOpacities[i])))
        }
      }
    }
    .frame(width: 180, height: 180)
  }
}
