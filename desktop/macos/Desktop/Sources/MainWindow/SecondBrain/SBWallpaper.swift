import OmiTheme
import SwiftUI

/// The Second Brain backdrop: a soft horizon glow over three slowly drifting ridgelines.
///
/// **On glass this draws no background of its own, and that is the whole change.** It used to open
/// with an opaque `sb.background` fill, which is a second ground — it slid a solid sheet between the
/// desktop and the `.behindWindow` blur, so the panel behind it rendered as a flat slab over one
/// desktop and a muddy one over another (`WindowGlass`'s file header is about exactly this failure).
/// The desktop *is* the wallpaper now; these ridgelines are a wash on top of it.
///
/// They are alphas on `Ink.primary` rather than the old hand-mixed near-blacks for the same reason
/// the rest of the palette is: one value darkens a light panel and lightens a dark one, and it
/// composites correctly over a vibrant material. Neutral throughout (INV-UI-1).
///
/// Motion: ridgelines drift ≤9% over 8–15s alternating cycles; the horizon glow breathes on a 7s
/// cycle. Every one of those is routed through `InkReduceMotion`, so Reduce Motion stops them dead
/// rather than merely slowing them down.
struct SBWallpaper: View {
  @State private var animate = false

  /// The ridgelines, back to front. Alphas rather than colours: the ground under them is a
  /// translucent panel, not a known fill, so only a relative darkening composites predictably.
  private static let ridgelines: [(top: Double, bottom: Double)] = [
    (0.055, 0.020), (0.045, 0.016), (0.035, 0.012),
  ]

  var body: some View {
    GeometryReader { geo in
      let w = geo.size.width
      let h = geo.size.height
      ZStack {
        // Horizon glow. `Ink.glow` (white) rather than a tint: this is a light source, and
        // INV-UI-1 wants that light neutral.
        RadialGradient(
          gradient: Gradient(colors: [Ink.glow.opacity(0.22), .clear]),
          center: UnitPoint(x: 0.5, y: 0.9),
          startRadius: 0,
          endRadius: max(w, h) * 0.75
        )
        .opacity(animate ? 1.0 : 0.5)
        .animation(
          InkReduceMotion.animation(.easeInOut(duration: 7).repeatForever(autoreverses: true)),
          value: animate)

        RadialGradient(
          gradient: Gradient(colors: [Ink.glow.opacity(0.12), .clear]),
          center: UnitPoint(x: 0.22, y: -0.05),
          startRadius: 0,
          endRadius: max(w, h) * 0.55
        )

        hill(
          Self.ridgelines[2], width: w * 1.5, height: h * 0.78,
          baseX: w * 0.5, baseY: h * 1.16, drift: animate ? w * 0.06 : -w * 0.02,
          duration: 8)
        hill(
          Self.ridgelines[1], width: w * 1.35, height: h * 0.80,
          baseX: w * 0.62, baseY: h * 1.14, drift: animate ? -w * 0.07 : w * 0.03,
          duration: 15)
        hill(
          Self.ridgelines[0], width: w * 1.25, height: h * 0.78,
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
    _ shade: (top: Double, bottom: Double), width: CGFloat, height: CGFloat,
    baseX: CGFloat, baseY: CGFloat, drift: CGFloat, duration: Double
  ) -> some View {
    Ellipse()
      .fill(
        LinearGradient(
          colors: [Ink.primary.opacity(shade.top), Ink.primary.opacity(shade.bottom)],
          startPoint: .top,
          endPoint: .bottom
        )
      )
      .frame(width: width, height: height)
      .position(x: baseX + drift, y: baseY)
      .animation(
        InkReduceMotion.animation(.easeInOut(duration: duration).repeatForever(autoreverses: true)),
        value: drift)
  }
}
