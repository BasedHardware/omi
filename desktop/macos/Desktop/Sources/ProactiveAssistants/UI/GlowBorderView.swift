import SwiftUI

/// Color mode for the glow effect
enum GlowColorMode {
    case focused    // Green - user is focused
    case distracted // Red - user is distracted

    /// Base hue for the color mode (HSL color wheel: 0 = red, 0.33 = green)
    var baseHue: Double {
        switch self {
        case .focused: return 0.38      // Green
        case .distracted: return 0.0    // Red
        }
    }

    /// Hue variation range for animation
    var hueRange: ClosedRange<Double> {
        switch self {
        case .focused: return 0.33...0.45     // Green to cyan
        case .distracted: return 0.95...1.05  // Red to orange (wraps around 1.0)
        }
    }
}

/// A SwiftUI view that displays an animated glow border effect
struct GlowBorderView: View {
    /// The size of the target window (the glow border will surround this)
    let targetSize: CGSize

    /// The color mode for the glow (focused = green, distracted = red)
    let colorMode: GlowColorMode

    /// Border thickness for the glow effect
    let borderWidth: CGFloat = 20

    /// Padding added around the target window for glow overflow
    let glowPadding: CGFloat = 30

    /// Controls the animation phase
    @State private var phase: CGFloat = 0

    /// Controls overall opacity for fade in/out
    @State private var opacity: Double = 0

    var body: some View {
        // The total size includes padding for glow overflow
        let totalWidth = targetSize.width + (glowPadding * 2)
        let totalHeight = targetSize.height + (glowPadding * 2)

        ZStack {
            // Animated gradient as the glow
            animatedGradient
                .frame(width: totalWidth, height: totalHeight)
                // Mask to only show the border area (hollow out the center)
                .mask(
                    borderMask(
                        totalSize: CGSize(width: totalWidth, height: totalHeight),
                        innerSize: targetSize,
                        cornerRadius: 12
                    )
                )
                // Add blur for soft glow effect
                .blur(radius: 8)

            // Sharper inner border for definition
            animatedGradient
                .frame(width: totalWidth, height: totalHeight)
                .mask(
                    borderMask(
                        totalSize: CGSize(width: totalWidth, height: totalHeight),
                        innerSize: CGSize(
                            width: targetSize.width + 4,
                            height: targetSize.height + 4
                        ),
                        cornerRadius: 12
                    )
                )
                .blur(radius: 2)
                .opacity(0.8)
        }
        .opacity(opacity)
        .onAppear {
            startAnimation()
        }
    }

    /// The animated gradient - uses MeshGradient on macOS 15+, falls back to LinearGradient
    @ViewBuilder
    private var animatedGradient: some View {
        if #available(macOS 15.0, *) {
            meshGradientView
        } else {
            fallbackGradientView
        }
    }

    /// MeshGradient for macOS 15+
    @available(macOS 15.0, *)
    private var meshGradientView: some View {
        let animatedPhase = phase
        return MeshGradient(
            width: 3,
            height: 3,
            points: meshPoints(phase: animatedPhase),
            colors: meshColors(phase: animatedPhase)
        )
    }

    /// Fallback gradient for older macOS versions
    private var fallbackGradientView: some View {
        let shift = phase
        let base = colorMode.baseHue
        return AngularGradient(
            gradient: Gradient(colors: [
                Color(hue: normalizeHue(base + shift * 0.05), saturation: 0.9, brightness: 0.9),
                Color(hue: normalizeHue(base + 0.04 + shift * 0.03), saturation: 0.85, brightness: 0.95),
                Color(hue: normalizeHue(base - 0.03 - shift * 0.05), saturation: 0.9, brightness: 0.85),
                Color(hue: normalizeHue(base + 0.07 + shift * 0.04), saturation: 0.8, brightness: 0.9),
                Color(hue: normalizeHue(base + 0.02), saturation: 0.7, brightness: 1.0),
                Color(hue: normalizeHue(base - 0.05 - shift * 0.04), saturation: 0.85, brightness: 0.9),
                Color(hue: normalizeHue(base + shift * 0.05), saturation: 0.9, brightness: 0.9)
            ]),
            center: .center,
            startAngle: .degrees(phase * 360),
            endAngle: .degrees(phase * 360 + 360)
        )
    }

    /// Normalize hue to 0-1 range (handles wrap-around for red hues near 0/1)
    private func normalizeHue(_ hue: Double) -> Double {
        var h = hue
        while h < 0 { h += 1 }
        while h > 1 { h -= 1 }
        return h
    }

    /// Generate mesh points with subtle animation
    private func meshPoints(phase: CGFloat) -> [SIMD2<Float>] {
        // Small offsets for organic movement
        let wobble = Float(sin(phase * .pi * 2) * 0.05)
        let wobble2 = Float(cos(phase * .pi * 2) * 0.05)

        return [
            // Top row
            SIMD2(0.0, 0.0),
            SIMD2(0.5 + wobble, 0.0),
            SIMD2(1.0, 0.0),
            // Middle row
            SIMD2(0.0, 0.5 + wobble2),
            SIMD2(0.5 + wobble2, 0.5 + wobble),  // Center point moves
            SIMD2(1.0, 0.5 - wobble2),
            // Bottom row
            SIMD2(0.0, 1.0),
            SIMD2(0.5 - wobble, 1.0),
            SIMD2(1.0, 1.0)
        ]
    }

    /// Generate mesh colors with phase-based shifting
    private func meshColors(phase: CGFloat) -> [Color] {
        // Cycle through hues based on phase and color mode
        let shift = phase
        let base = colorMode.baseHue

        return [
            // Top row - brighter colors
            Color(hue: normalizeHue(base + shift * 0.05), saturation: 0.9, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.04 + shift * 0.03), saturation: 0.85, brightness: 0.95),
            Color(hue: normalizeHue(base - 0.03 - shift * 0.05), saturation: 0.9, brightness: 0.85),
            // Middle row - color variations
            Color(hue: normalizeHue(base + 0.07 + shift * 0.04), saturation: 0.8, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.02), saturation: 0.7, brightness: 1.0),  // Bright center
            Color(hue: normalizeHue(base - 0.05 - shift * 0.04), saturation: 0.85, brightness: 0.9),
            // Bottom row - deeper colors
            Color(hue: normalizeHue(base - 0.02 - shift * 0.03), saturation: 0.9, brightness: 0.85),
            Color(hue: normalizeHue(base + 0.02 + shift * 0.05), saturation: 0.85, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.06 + shift * 0.03), saturation: 0.9, brightness: 0.88)
        ]
    }

    /// Create a mask that shows only the border area
    private func borderMask(totalSize: CGSize, innerSize: CGSize, cornerRadius: CGFloat) -> some View {
        // Outer rounded rectangle (full size)
        // Minus inner rounded rectangle (window area)
        let outerRect = RoundedRectangle(cornerRadius: cornerRadius + glowPadding / 2)
        let innerRect = RoundedRectangle(cornerRadius: cornerRadius)

        return ZStack {
            outerRect
            innerRect
                .frame(width: innerSize.width, height: innerSize.height)
                .blendMode(.destinationOut)
        }
        .compositingGroup()
    }

    /// Start the glow animation sequence
    private func startAnimation() {
        // Fade in
        withAnimation(.easeIn(duration: 0.3)) {
            opacity = 1.0
        }

        // Animate the mesh movement
        withAnimation(
            .easeInOut(duration: 1.5)
            .repeatCount(3, autoreverses: true)
        ) {
            phase = 1.0
        }

        // Schedule fade out after the animation completes
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation(.easeOut(duration: 0.5)) {
                opacity = 0.0
            }
        }
    }
}

#Preview("Focused (Green)") {
    ZStack {
        Color.black.opacity(0.3)
        GlowBorderView(targetSize: CGSize(width: 800, height: 600), colorMode: .focused)
    }
    .frame(width: 900, height: 700)
}

#Preview("Distracted (Red)") {
    ZStack {
        Color.black.opacity(0.3)
        GlowBorderView(targetSize: CGSize(width: 800, height: 600), colorMode: .distracted)
    }
    .frame(width: 900, height: 700)
}
