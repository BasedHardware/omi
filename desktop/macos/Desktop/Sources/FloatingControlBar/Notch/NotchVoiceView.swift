import SwiftUI

/// The expanded voice content below the morphing Omi orb: the live transcript
/// while listening, or the streaming / lingering reply while responding,
/// centered under the orb. Reports its measured height so the panel grows in
/// height as words wrap to new lines (the width is fixed). The reply is a tap
/// target that opens the main app window (full text chat lives in the app now).
struct NotchVoiceView: View {
  /// The text to show (transcript or reply). Empty shows the placeholder while
  /// listening, or just the orb while responding.
  let text: String
  let placeholder: String
  /// Heavier weight for the user's spoken words; lighter for Omi's reply.
  let emphasized: Bool
  /// Non-nil for the reply: tapping opens the main window.
  let onOpenApp: (() -> Void)?
  /// Vertical space reserved at the top for the camera housing + the orb.
  let topReserve: CGFloat
  let onHeightChange: (CGFloat) -> Void

  var body: some View {
    VStack(spacing: 0) {
      Color.clear.frame(height: topReserve)
      transcript
        .padding(.horizontal, 24)
        .padding(.bottom, 14)
    }
    .onGeometryChange(for: CGFloat.self) {
      $0.size.height
    } action: {
      onHeightChange($0)
    }
  }

  @ViewBuilder
  private var transcript: some View {
    if text.isEmpty && onOpenApp != nil {
      // Reply is starting (audio can lead the first text token); the speaking
      // orb carries it until words arrive.
      Color.clear.frame(height: 1)
    } else {
      styledText
    }
  }

  private var styledText: some View {
    // ponytail: voice replies are short — clips at half-screen and the tap
    // opens the app for the full conversation. Add an inner ScrollView if long
    // spoken replies become common.
    Text(text.isEmpty ? placeholder : text)
      .font(.system(size: 13, weight: emphasized ? .medium : .regular))
      .foregroundStyle(.white.opacity(text.isEmpty ? 0.5 : 0.9))
      .multilineTextAlignment(.center)
      .frame(maxWidth: .infinity, alignment: .center)
      .fixedSize(horizontal: false, vertical: true)
      .shimmer()
      .contentShape(Rectangle())
      .onTapGesture { onOpenApp?() }
      .accessibilityAddTraits(onOpenApp != nil ? .isButton : [])
  }
}

// MARK: - Shimmer

extension View {
  /// A slow light sweep across the glyphs — the "live / streaming" shimmer used
  /// on every voice-state label. No-op under reduced motion.
  func shimmer() -> some View { modifier(ShimmerModifier()) }
}

private struct ShimmerModifier: ViewModifier {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  func body(content: Content) -> some View {
    if reduceMotion {
      content
    } else {
      content.overlay {
        GeometryReader { geo in
          TimelineView(.animation) { timeline in
            let period = 2.2
            let t = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: period)
            let travel = geo.size.width + 160
            let x = CGFloat(t / period) * travel - 80
            LinearGradient(
              colors: [.clear, .white.opacity(0.85), .clear],
              startPoint: .leading, endPoint: .trailing
            )
            .frame(width: 80)
            .offset(x: x)
            .blendMode(.plusLighter)
          }
        }
        .mask(content)
        .allowsHitTesting(false)
      }
    }
  }
}
