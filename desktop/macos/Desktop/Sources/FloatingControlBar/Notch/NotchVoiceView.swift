import SwiftUI

/// The expanded voice content below the morphing Omi orb: the live transcript
/// while listening, or the streaming / lingering reply while responding,
/// centered under the orb. Reports its measured height so the panel grows in
/// height as words wrap to new lines (fixed width, capped at 30% of the
/// screen). While the text is actively growing it auto-scrolls so the newest
/// line is always visible; once the reply settles it scrolls back to the top
/// and reveals an "Open in Omi" hint. Tapping opens the full conversation.
struct NotchVoiceView: View {
  /// The text to show (transcript or reply). Empty shows the placeholder while
  /// listening, or just the orb while responding.
  let text: String
  let placeholder: String
  /// Heavier weight for the user's spoken words; lighter for Omi's reply.
  let emphasized: Bool
  /// Non-nil for the reply: tapping opens the main window.
  let onOpenApp: (() -> Void)?
  /// True while the text is actively growing (listening, or the reply
  /// streaming): keep the newest line pinned to the bottom.
  let followsTail: Bool
  /// Vertical space reserved at the top for the camera housing + the orb.
  let topReserve: CGFloat
  let onHeightChange: (CGFloat) -> Void

  /// The tap hint only appears once a reply has settled (not while streaming).
  private var showsOpenHint: Bool { onOpenApp != nil && !followsTail && !text.isEmpty }
  private var hintHeight: CGFloat { showsOpenHint ? 26 : 0 }

  var body: some View {
    VStack(spacing: 0) {
      Color.clear.frame(height: topReserve)
      ScrollViewReader { proxy in
        ScrollView(.vertical, showsIndicators: true) {
          VStack(spacing: 0) {
            transcript
              .padding(.horizontal, 24)
              .padding(.bottom, showsOpenHint ? 4 : 14)
              .id("voiceTop")
            Color.clear.frame(height: 1).id("voiceBottom")
          }
          .onGeometryChange(for: CGFloat.self) {
            $0.size.height
          } action: { height in
            onHeightChange(topReserve + height + hintHeight)
          }
        }
        .onChange(of: text) { _, _ in
          guard followsTail else { return }
          withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo("voiceBottom", anchor: .bottom) }
        }
        .onChange(of: followsTail) { _, follows in
          if !follows { withAnimation { proxy.scrollTo("voiceTop", anchor: .top) } }
        }
      }
      if showsOpenHint {
        openHint.transition(.opacity)
      }
    }
    .animation(.easeInOut(duration: 0.2), value: showsOpenHint)
  }

  private var openHint: some View {
    Button(action: { onOpenApp?() }) {
      HStack(spacing: 3) {
        Text("Open in Omi")
        Image(systemName: "arrow.up.forward")
          .font(.system(size: 9, weight: .semibold))
      }
      .font(.system(size: 10, weight: .medium))
      .foregroundStyle(.white.opacity(0.45))
      .padding(.vertical, 6)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Open the full conversation in Omi")
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
