import OmiTheme
import SwiftUI

/// The Second Brain wallpaper: a soft horizon glow over three slowly drifting
/// ridgeline hills. Pure decoration — recreated from the design's CSS
/// radial-gradient glow + three elliptical hill shapes. Monochrome in both themes.
///
/// Motion: hills drift ≤9% over 8–15s alternating cycles; the horizon glow pulses
/// on a 7s cycle. These are the only looping animations here (allowed by the design).
struct SBWallpaper: View {
  @Environment(\.sbTheme) private var sb
  @State private var animate = false

  var body: some View {
    GeometryReader { geo in
      let w = geo.size.width
      let h = geo.size.height
      ZStack {
        // Base background.
        sb.background

        // Horizon glow — low center + faint top-left, gently pulsing.
        RadialGradient(
          gradient: Gradient(colors: [sb.glowTint, .clear]),
          center: UnitPoint(x: 0.5, y: 0.9),
          startRadius: 0,
          endRadius: max(w, h) * 0.75
        )
        .opacity(animate ? 1.0 : 0.5)
        .animation(.easeInOut(duration: 7).repeatForever(autoreverses: true), value: animate)

        RadialGradient(
          gradient: Gradient(colors: [sb.ink(.w04), .clear]),
          center: UnitPoint(x: 0.22, y: -0.05),
          startRadius: 0,
          endRadius: max(w, h) * 0.55
        )

        // Three ridgeline hills, back-to-front, each drifting on its own slow cycle.
        hill(color1: sb.hillC, color2: sb.hillC2, width: w * 1.5, height: h * 0.78,
             baseX: w * 0.5, baseY: h * 1.16, drift: animate ? w * 0.06 : -w * 0.02,
             duration: 8)
        hill(color1: sb.hillB, color2: sb.hillB2, width: w * 1.35, height: h * 0.80,
             baseX: w * 0.62, baseY: h * 1.14, drift: animate ? -w * 0.07 : w * 0.03,
             duration: 15)
        hill(color1: sb.hillA, color2: sb.hillA2, width: w * 1.25, height: h * 0.78,
             baseX: w * 0.32, baseY: h * 1.18, drift: animate ? w * 0.08 : -w * 0.03,
             duration: 11)
      }
      .ignoresSafeArea()
    }
    .ignoresSafeArea()
    .onAppear { animate = true }
    .accessibilityHidden(true)
  }

  private func hill(
    color1: Color, color2: Color, width: CGFloat, height: CGFloat,
    baseX: CGFloat, baseY: CGFloat, drift: CGFloat, duration: Double
  ) -> some View {
    Ellipse()
      .fill(
        LinearGradient(
          colors: [color1, color2],
          startPoint: .top,
          endPoint: .bottom
        )
      )
      .frame(width: width, height: height)
      .position(x: baseX + drift, y: baseY)
      .animation(.easeInOut(duration: duration).repeatForever(autoreverses: true), value: drift)
  }
}
