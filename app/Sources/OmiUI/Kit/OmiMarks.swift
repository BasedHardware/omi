import SwiftUI

/// The Omi avatar mark: the wordless circle-and-dot glyph.
struct OmiAvatarShape: View {
    var body: some View {
        ZStack {
            Circle().inset(by: 6)
                .stroke(style: StrokeStyle(lineWidth: 2, lineCap: .round))
            Circle().frame(width: 14, height: 14)
        }
    }
}

// MARK: - Loading mark (OmiLoadingMark port: the animated Omi dot)

/// The Omi mark: a single ink dot breathing while work is in flight.
/// Reduce Motion holds it still.
struct OmiLoadingMark: View {
    var size: CGFloat
    var ink: Color

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    var body: some View {
        Circle()
            .fill(ink)
            .frame(width: size * 0.22, height: size * 0.22)
            .scaleEffect(pulsing ? 1.25 : 0.9)
            .opacity(pulsing ? 1.0 : 0.55)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(
                    // 900ms pulse token; SwiftUI durations are seconds.
                    .easeInOut(duration: reduceMotion ? 0.0 : 0.9)
                    .repeatForever(autoreverses: true)
                ) {
                    pulsing = true
                }
            }
            .frame(width: size, height: size)
            .accessibilityLabel("Loading")
    }
}
