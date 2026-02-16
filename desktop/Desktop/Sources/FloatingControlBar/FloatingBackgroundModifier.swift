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
struct FloatingBackgroundModifier: ViewModifier {
    let cornerRadius: CGFloat
    @ObservedObject private var settings = ShortcutSettings.shared

    func body(content: Content) -> some View {
        content
            .background(
                Group {
                    if settings.solidBackground {
                        Color(nsColor: NSColor(white: 0.12, alpha: 1.0))
                    } else {
                        VisualEffectView(material: .fullScreenUI, blendingMode: .behindWindow, alphaValue: 0.6)
                    }
                }
            )
            .cornerRadius(cornerRadius)
    }
}

extension View {
    func floatingBackground(cornerRadius: CGFloat = 20) -> some View {
        modifier(FloatingBackgroundModifier(cornerRadius: cornerRadius))
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
