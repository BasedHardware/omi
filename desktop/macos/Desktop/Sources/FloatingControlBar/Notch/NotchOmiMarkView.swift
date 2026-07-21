import SwiftUI

/// The Omi dotted-ring mark shown in the notch chrome. Dot colors default to
/// white; agent surfaces tint them by agent status.
struct NotchOmiMark: View {
  var dotColors: [Color] = []

  private static let dotCount = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33

  var body: some View {
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
