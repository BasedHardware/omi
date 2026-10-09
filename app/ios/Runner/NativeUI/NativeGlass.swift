import SwiftUI

/// Shared presentation metrics, so cards, blocks and rows agree across Home and every surface.
enum NativeMetrics {
    /// Matches the system's inset-grouped cell: 26 pt with Liquid Glass (iOS 26+), 10 pt before.
    static var cardRadius: CGFloat {
        if #available(iOS 26.0, *) { return 26 }
        return 10
    }
    /// Code blocks, tables, thumbnails and the reader's current-line highlight.
    static let blockRadius: CGFloat = 12
    /// The minimum tappable row and control height.
    static let rowHeight: CGFloat = 44
    /// Selection marks and tags. The renderer's own tint is monochrome and the app defines no accent
    /// colour, so `Color.accentColor` would resolve to that tint; this is the system accent.
    static let accent = Color(uiColor: .systemBlue)
}

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
