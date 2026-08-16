import OmiTheme
import SwiftUI

struct OmiThinkingMark: View {
  @State private var angle: Double = 0

  private static let dotCount = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33
  /// The comet's tail, in the ink itself: on a light-pinned panel a trail of white
  /// dots is a trail of nothing. The head is `Ink.primary` and the tail fades out
  /// behind it, which is the same read in either appearance.
  private static let trail: [Color] = (0..<dotCount).map { index in
    Ink.primary.opacity(1.0 - Double(index) * 0.1)
  }

  var body: some View {
    omiMark(dotColors: Self.trail)
      .rotationEffect(.degrees(angle))
      .onAppear {
        angle = 0
        OmiMotion.withGated(.linear(duration: 0.9).repeatForever(autoreverses: false)) {
          angle = 360
        }
      }
      .accessibilityElement(children: .ignore)
      .accessibilityLabel("Thinking")
  }

  private func omiMark(dotColors: [Color]) -> some View {
    GeometryReader { geometry in
      let size = min(geometry.size.width, geometry.size.height)
      let center = CGPoint(
        x: geometry.size.width / 2,
        y: geometry.size.height / 2
      )
      let dotDiameter = size * Self.dotDiameterRatio
      let ringRadius = size * Self.ringRadiusRatio

      ZStack {
        ForEach(0..<Self.dotCount, id: \.self) { index in
          let angle = Double(index) / Double(Self.dotCount) * Double.pi * 2 - Double.pi
          Circle()
            .fill(dotColors.indices.contains(index) ? dotColors[index] : Ink.primary.opacity(0.96))
            .frame(width: dotDiameter, height: dotDiameter)
            .position(
              x: center.x + CGFloat(cos(angle)) * ringRadius,
              y: center.y + CGFloat(sin(angle)) * ringRadius
            )
        }
      }
    }
    .drawingGroup(opaque: false, colorMode: .linear)
    .accessibilityHidden(true)
  }
}

struct TypingIndicator: View {
  var body: some View {
    OmiThinkingMark()
      .frame(width: 24, height: 24)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      // A stadium, like every other pill in this system.
      .background(Capsule(style: .continuous).fill(Ink.rowFill))
  }
}

enum ChatWorkingStatus {
  /// The motion the transcript mark is allowed for `message` — or `nil` for a still mark.
  ///
  /// **The mark turns only while it is the row's one report of work.** Once a tool call is in
  /// flight the row already carries a tool card that spins *and names what is running*
  /// ("Searching the web"), so a mark turning beside it is a second spinner for a single
  /// activity: motion with no meaning of its own, immediately next to something already saying
  /// more. It drops to its resting frame there and goes on being what it is the rest of the
  /// time — the assistant's identity, not a progress bar.
  ///
  /// This is the rule app personas have always followed: `ChatBubble` withholds their
  /// `TypingIndicator` when the last group has a running tool. Omi's own mark was the one
  /// indicator that did not.
  ///
  /// Still is also cheap. `nil` puts `ChatOmiMark` on its static branch, which *destroys* the
  /// per-frame `TimelineView` rather than leaving it repainting behind the card — the only
  /// version of "stop" the run loop honours.
  static func motion(for message: ChatMessage?) -> ChatMarkMotion? {
    guard let message, message.sender == .ai, message.isStreaming else { return nil }
    guard !hasInFlightTool(message) else { return nil }
    return .gather
  }

  private static func hasInFlightTool(_ message: ChatMessage) -> Bool {
    message.contentBlocks.contains { block in
      if case .toolCall(_, _, let status, _, _, _) = block {
        return status.isInFlight
      }
      return false
    }
  }
}
