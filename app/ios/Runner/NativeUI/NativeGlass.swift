import SwiftUI

/// Glass belongs to the controls above content; reading surfaces keep an opaque background.
struct NativeGlassControls<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        if #available(iOS 26.0, *) { GlassEffectContainer(spacing: 12, content: content) }
        else { content() }
    }
}

struct NativeGlassButtonStyle: ViewModifier {
    var menu = false
    func body(content: Content) -> some View {
        if menu {
            if #available(iOS 26.0, *) {
                content.padding(.horizontal, 12).padding(.vertical, 7)
                    .glassEffect(.regular.interactive(), in: .capsule)
            } else { content.padding(7).background(.ultraThinMaterial, in: Capsule()) }
        } else if #available(iOS 26.0, *) { content.buttonStyle(.glass) }
        else { content.buttonStyle(.bordered) }
    }
}

struct NativeGlassComposerStyle: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular.interactive(), in: .rect(cornerRadius: 22))
        } else {
            content.background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
        }
    }
}
