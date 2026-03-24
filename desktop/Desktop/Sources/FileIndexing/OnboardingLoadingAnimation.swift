import SwiftUI

/// Orbital ring loading animation for the onboarding file-indexing step.
/// Renders a partial gradient arc that fills as `progress` increases,
/// orbiting glow particles, and a breathing center pulse.
struct OnboardingLoadingAnimation: View {
    /// 0.0 … 1.0
    var progress: Double

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                let center = CGPoint(x: size.width / 2, y: size.height / 2)
                let radius: CGFloat = min(size.width, size.height) / 2 - 20

                // --- Center pulse ---
                let pulseScale = 0.15 + 0.08 * sin(time * 1.8)
                let pulseRadius = radius * pulseScale
                let pulseGradient = Gradient(colors: [
                    OmiColors.purplePrimary.opacity(0.4),
                    OmiColors.purplePrimary.opacity(0.0),
                ])
                let pulseShading = GraphicsContext.Shading.radialGradient(
                    pulseGradient,
                    center: center,
                    startRadius: 0,
                    endRadius: pulseRadius
                )
                context.fill(Circle().path(in: CGRect(
                    x: center.x - pulseRadius,
                    y: center.y - pulseRadius,
                    width: pulseRadius * 2,
                    height: pulseRadius * 2
                )), with: pulseShading)

                // --- Orbital ring (background track) ---
                var trackPath = Path()
                trackPath.addArc(center: center, radius: radius,
                                 startAngle: .degrees(0), endAngle: .degrees(360),
                                 clockwise: false)
                context.stroke(trackPath, with: .color(OmiColors.purplePrimary.opacity(0.12)),
                               lineWidth: 3)

                // --- Orbital ring (filled arc) ---
                let arcEnd = progress * 360.0
                if arcEnd > 0 {
                    var arcPath = Path()
                    arcPath.addArc(center: center, radius: radius,
                                   startAngle: .degrees(-90),
                                   endAngle: .degrees(-90 + arcEnd),
                                   clockwise: false)
                    let arcGradient = Gradient(colors: [
                        OmiColors.purplePrimary,
                        OmiColors.purpleSecondary,
                    ])
                    context.stroke(arcPath,
                                   with: .linearGradient(arcGradient,
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
                        OmiColors.purpleSecondary.opacity(particleOpacities[i] * 0.5),
                        OmiColors.purpleSecondary.opacity(0),
                    ])
                    context.fill(Circle().path(in: glowRect),
                                 with: .radialGradient(glowGradient, center: CGPoint(x: px, y: py),
                                                       startRadius: 0, endRadius: glowSize))

                    // Dot
                    context.fill(Circle().path(in: pRect),
                                 with: .color(.white.opacity(particleOpacities[i])))
                }
            }
        }
        .frame(width: 180, height: 180)
    }
}
