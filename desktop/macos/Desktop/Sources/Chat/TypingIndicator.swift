import SwiftUI
import OmiTheme

struct OmiThinkingMark: View {
  @State private var angle: Double = 0

  private static let dotCount = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33
  private static let trail: [Color] = (0..<dotCount).map { index in
    Color.white.opacity(1.0 - Double(index) * 0.1)
  }

  var body: some View {
    omiMark(dotColors: Self.trail)
      .rotationEffect(.degrees(angle))
      .onAppear {
        angle = 0
        withAnimation(.linear(duration: 0.9).repeatForever(autoreverses: false)) {
          angle = 360
        }
      }
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
            .fill(dotColors.indices.contains(index) ? dotColors[index] : Color.white.opacity(0.96))
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
      .padding(.horizontal, 14)
      .padding(.vertical, 8)
      .background(OmiColors.backgroundTertiary)
      .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
  }
}
