import SwiftUI

/// Shared visual effect view for all floating UI elements
struct VisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

/// Shared background style for all floating windows
struct FloatingBackgroundModifier: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    VisualEffectView(material: .hudWindow, blendingMode: .behindWindow)
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

/// Shared spinner view
struct LoadingSpinner: View {
    @State private var isSpinning = false

    var body: some View {
        Image("app_launcher_icon")
            .resizable()
            .foregroundColor(.primary)
            .colorInvert()
            .rotationEffect(.degrees(isSpinning ? 360 : 0))
            .onAppear {
                isSpinning = true
            }
            .animation(
                .linear(duration: 1)
                .repeatForever(autoreverses: false),
                value: isSpinning
            )
    }
}
