import SwiftUI

/// NSVisualEffectView wrapper for dark blur background.
struct VisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode
    var alphaValue: CGFloat

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        view.alphaValue = alphaValue
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
        nsView.alphaValue = alphaValue
    }
}

/// Background modifier using NSVisualEffectView with dark blur or solid background.
///
/// `light` swaps the dark HUD chrome for the redesign's warm-paper Ink surface so
/// the expanded Ask/response/agent conversation reads light (matching the mockup).
struct FloatingBackgroundModifier: ViewModifier {
    let cornerRadius: CGFloat
    var light: Bool = false
    @ObservedObject private var settings = ShortcutSettings.shared

    func body(content: Content) -> some View {
        content
            .background(background)
            .clipShape(.rect(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(light ? Ink.hair2 : Color.black.opacity(0.5), lineWidth: 1)
            )
    }

    @ViewBuilder
    private var background: some View {
        if light {
            // Warm-paper frosted glass for the light conversation surface.
            ZStack {
                VisualEffectView(material: .popover, blendingMode: .behindWindow, alphaValue: 1.0)
                Ink.surface.opacity(0.88)
            }
        } else if settings.solidBackground {
            Color(nsColor: NSColor(white: 0.12, alpha: 1.0))
        } else {
            ZStack {
                VisualEffectView(material: .hudWindow, blendingMode: .behindWindow, alphaValue: 0.95)
                Color.black.opacity(0.18)
            }
        }
    }
}

extension View {
    func floatingBackground(cornerRadius: CGFloat = 20, light: Bool = false) -> some View {
        modifier(FloatingBackgroundModifier(cornerRadius: cornerRadius, light: light))
    }
}

/// Simple spinning loader for the floating bar.
struct FloatingLoadingSpinner: View {
    @State private var isSpinning = false

    var body: some View {
        Circle()
            .trim(from: 0.1, to: 0.9)
            .stroke(Color.white, lineWidth: 2)
            .rotationEffect(.degrees(isSpinning ? 360 : 0))
            .onAppear { isSpinning = true }
            .animation(
                .linear(duration: 1).repeatForever(autoreverses: false),
                value: isSpinning
            )
    }
}
