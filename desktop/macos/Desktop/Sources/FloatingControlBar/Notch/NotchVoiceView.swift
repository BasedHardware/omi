import SwiftUI

/// The expanded voice content below the morphing Omi orb. Listening shows a
/// "Listening…" caption with the live transcript beneath it (faded, so you can
/// check we heard you right without confusing it with the reply). Responding
/// reveals Omi's reply at the speaking cadence. Reports its measured height so
/// the panel grows as lines wrap (fixed width, capped at 30% of the screen);
/// long content scrolls and auto-follows the newest line. Tapping the reply
/// opens the full conversation.
struct NotchVoiceView: View {
  /// The text to show (transcript or reply).
  let text: String
  /// Caption shown while listening.
  let placeholder: String
  /// Non-nil for the reply: tapping opens the main window.
  let onOpenApp: (() -> Void)?
  /// True while the reply is still streaming (drives the tap-hint timing).
  let followsTail: Bool
  /// Vertical space reserved at the top for the camera housing + the orb.
  let topReserve: CGFloat
  let onHeightChange: (CGFloat) -> Void

  @State private var lastContentHeight: CGFloat = 0

  private var isReply: Bool { onOpenApp != nil }
  /// The tap hint only appears once a reply has settled (not while streaming).
  private var showsOpenHint: Bool { isReply && !followsTail && !text.isEmpty }
  private var hintHeight: CGFloat { showsOpenHint ? 26 : 0 }

  var body: some View {
    VStack(spacing: 0) {
      Color.clear.frame(height: topReserve)
      ScrollViewReader { proxy in
        ScrollView(.vertical, showsIndicators: true) {
          VStack(spacing: 0) {
            transcript
              .padding(.horizontal, 30)
              .padding(.bottom, 14)
              .id("voiceTop")
            Color.clear.frame(height: 1).id("voiceBottom")
          }
          .onGeometryChange(for: CGFloat.self) {
            $0.size.height
          } action: { height in
            onHeightChange(topReserve + height + hintHeight)
            // Follow the reveal: as content grows, keep the newest line in view.
            if height > lastContentHeight + 1 {
              withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo("voiceBottom", anchor: .bottom) }
            }
            lastContentHeight = height
          }
        }
      }
      if showsOpenHint {
        openHint.transition(.opacity)
      }
    }
    .animation(.easeInOut(duration: 0.2), value: showsOpenHint)
  }

  @ViewBuilder
  private var transcript: some View {
    if text.isEmpty && isReply {
      // Reply is starting (audio can lead the first text token); the speaking
      // orb carries it until words arrive.
      Color.clear.frame(height: 1)
    } else {
      content
        .frame(maxWidth: .infinity)
        .contentShape(Rectangle())
        .onTapGesture { onOpenApp?() }
        .accessibilityAddTraits(isReply ? .isButton : [])
    }
  }

  @ViewBuilder
  private var content: some View {
    if isReply {
      // Omi's reply: paced to the speaking cadence, justified, with the live
      // shimmer while it streams.
      StreamingReplyText(fullText: text, size: 13, opacity: 0.9)
        .shimmer()
    } else {
      // Listening: caption + the live transcript beneath it, faded so it reads
      // as a tentative "here's what we're hearing", distinct from the reply.
      // No shimmer here — it must stay calm and clearly faded.
      VStack(spacing: 4) {
        Text(placeholder)
          .font(.system(size: 11, weight: .medium))
          .foregroundStyle(.white.opacity(0.5))
        if !text.isEmpty {
          JustifiedText(text: text, size: 12, weight: .regular, opacity: 0.5)
        }
      }
    }
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
}

// MARK: - Shimmer

extension View {
  /// A slow light sweep across the glyphs — the "live / streaming" shimmer used
  /// on the voice-state text. No-op under reduced motion.
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
