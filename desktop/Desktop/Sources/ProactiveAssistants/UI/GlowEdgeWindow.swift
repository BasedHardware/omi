import AppKit
import SwiftUI

/// Which edge of the target window this glow window represents
enum GlowEdge {
    case top
    case bottom
    case left
    case right
}

/// A transparent, click-through window that displays glow on one edge of a target window.
/// By using 4 separate edge windows positioned AROUND (not on top of) the target window,
/// we avoid blocking hover events in the target window's content area.
class GlowEdgeWindow: NSWindow {
    let edge: GlowEdge

    /// Thickness of the glow effect (extends outward from window edge)
    static let glowThickness: CGFloat = 20

    /// How much the edge window overlaps INTO the target window (for seamless appearance)
    static let overlap: CGFloat = 4

    init(edge: GlowEdge) {
        self.edge = edge

        super.init(
            contentRect: .zero,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        // Make window transparent and floating
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false

        // Float above other windows
        self.level = .popUpMenu

        // Click-through - don't intercept any mouse events
        self.ignoresMouseEvents = true

        // Don't show in mission control or app switcher
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        // No title bar behaviors
        self.isMovableByWindowBackground = false
        self.titlebarAppearsTransparent = true
        self.titleVisibility = .hidden

        // Disable window animations to prevent crashes
        self.animationBehavior = .none
    }

    /// Calculate the frame for this edge window based on the target window's bounds
    func calculateFrame(for targetRect: NSRect) -> NSRect {
        let thickness = Self.glowThickness
        let overlap = Self.overlap

        switch edge {
        case .top:
            // Position above the target window, overlapping slightly
            return NSRect(
                x: targetRect.minX - thickness,
                y: targetRect.maxY - overlap,
                width: targetRect.width + (thickness * 2),
                height: thickness + overlap
            )
        case .bottom:
            // Position below the target window, overlapping slightly
            return NSRect(
                x: targetRect.minX - thickness,
                y: targetRect.minY - thickness,
                width: targetRect.width + (thickness * 2),
                height: thickness + overlap
            )
        case .left:
            // Position to the left of the target window, overlapping slightly
            return NSRect(
                x: targetRect.minX - thickness,
                y: targetRect.minY - thickness,
                width: thickness + overlap,
                height: targetRect.height + (thickness * 2)
            )
        case .right:
            // Position to the right of the target window, overlapping slightly
            return NSRect(
                x: targetRect.maxX - overlap,
                y: targetRect.minY - thickness,
                width: thickness + overlap,
                height: targetRect.height + (thickness * 2)
            )
        }
    }

    /// Update the window frame to position around the target window
    func updateFrame(for targetRect: NSRect) {
        let frame = calculateFrame(for: targetRect)
        self.setFrame(frame, display: true)
    }
}

/// A SwiftUI view that displays an animated glow effect for a single edge
/// Uses the same MeshGradient animation as the original GlowBorderView
struct GlowEdgeView: View {
    let edge: GlowEdge
    let colorMode: GlowColorMode

    @State private var phase: CGFloat = 0
    @State private var opacity: Double = 0

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Main glow layer with blur
                animatedGradient
                    .mask(edgeFadeMask)
                    .blur(radius: 8)

                // Sharper inner layer for definition
                animatedGradient
                    .mask(edgeFadeMask)
                    .blur(radius: 2)
                    .opacity(0.8)
            }
            .opacity(opacity)
        }
        .onAppear {
            startAnimation()
        }
    }

    /// Mask that fades the glow toward the window interior
    @ViewBuilder
    private var edgeFadeMask: some View {
        switch edge {
        case .top:
            LinearGradient(
                colors: [.white, .white, .clear],
                startPoint: .top,
                endPoint: .bottom
            )
        case .bottom:
            LinearGradient(
                colors: [.clear, .white, .white],
                startPoint: .top,
                endPoint: .bottom
            )
        case .left:
            LinearGradient(
                colors: [.white, .white, .clear],
                startPoint: .leading,
                endPoint: .trailing
            )
        case .right:
            LinearGradient(
                colors: [.clear, .white, .white],
                startPoint: .leading,
                endPoint: .trailing
            )
        }
    }

    /// The animated gradient - uses MeshGradient on macOS 15+, falls back to AngularGradient
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
        let wobble = Float(sin(phase * .pi * 2) * 0.05)
        let wobble2 = Float(cos(phase * .pi * 2) * 0.05)

        return [
            SIMD2(0.0, 0.0),
            SIMD2(0.5 + wobble, 0.0),
            SIMD2(1.0, 0.0),
            SIMD2(0.0, 0.5 + wobble2),
            SIMD2(0.5 + wobble2, 0.5 + wobble),
            SIMD2(1.0, 0.5 - wobble2),
            SIMD2(0.0, 1.0),
            SIMD2(0.5 - wobble, 1.0),
            SIMD2(1.0, 1.0)
        ]
    }

    /// Generate mesh colors with phase-based shifting
    private func meshColors(phase: CGFloat) -> [Color] {
        let shift = phase
        let base = colorMode.baseHue

        return [
            Color(hue: normalizeHue(base + shift * 0.05), saturation: 0.9, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.04 + shift * 0.03), saturation: 0.85, brightness: 0.95),
            Color(hue: normalizeHue(base - 0.03 - shift * 0.05), saturation: 0.9, brightness: 0.85),
            Color(hue: normalizeHue(base + 0.07 + shift * 0.04), saturation: 0.8, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.02), saturation: 0.7, brightness: 1.0),
            Color(hue: normalizeHue(base - 0.05 - shift * 0.04), saturation: 0.85, brightness: 0.9),
            Color(hue: normalizeHue(base - 0.02 - shift * 0.03), saturation: 0.9, brightness: 0.85),
            Color(hue: normalizeHue(base + 0.02 + shift * 0.05), saturation: 0.85, brightness: 0.9),
            Color(hue: normalizeHue(base + 0.06 + shift * 0.03), saturation: 0.9, brightness: 0.88)
        ]
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

        // Schedule fade out
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation(.easeOut(duration: 0.5)) {
                opacity = 0.0
            }
        }
    }
}
