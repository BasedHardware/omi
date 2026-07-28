import SwiftUI

package enum OmiChrome {
  package static let windowRadius: CGFloat = 26
  package static let cardRadius: CGFloat = 24
  package static let sectionRadius: CGFloat = 20
  package static let controlRadius: CGFloat = 16
  package static let chipRadius: CGFloat = 14
  /// Small controls: compact buttons, inputs, thumbnails.
  package static let smallControlRadius: CGFloat = 12
  /// Small elements: badges, list chips, inline pills.
  package static let elementRadius: CGFloat = 8
  /// Tags and micro badges.
  package static let badgeRadius: CGFloat = 6
  /// Progress bars, underline indicators, hairline strips.
  package static let stripRadius: CGFloat = 3
}

private struct OmiPanelModifier: ViewModifier {
  let fill: Color
  let radius: CGFloat
  let stroke: Color?
  let shadowOpacity: Double
  let shadowRadius: CGFloat
  let shadowY: CGFloat

  func body(content: Content) -> some View {
    content
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(fill)
      )
      .overlay {
        if let stroke {
          RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(stroke, lineWidth: 1)
        }
      }
      .shadow(color: .black.opacity(shadowOpacity), radius: shadowRadius, x: 0, y: shadowY)
  }
}

extension View {
  package func omiPanel(
    fill: Color = OmiColors.backgroundSecondary,
    radius: CGFloat = OmiChrome.cardRadius,
    stroke: Color? = OmiColors.border.opacity(0.28),
    shadowOpacity: Double = 0.14,
    shadowRadius: CGFloat = 18,
    shadowY: CGFloat = 10
  ) -> some View {
    modifier(
      OmiPanelModifier(
        fill: fill,
        radius: radius,
        stroke: stroke,
        shadowOpacity: shadowOpacity,
        shadowRadius: shadowRadius,
        shadowY: shadowY
      )
    )
  }

  package func omiControlSurface(
    fill: Color = OmiColors.backgroundTertiary,
    radius: CGFloat = OmiChrome.controlRadius,
    stroke: Color? = nil
  ) -> some View {
    modifier(
      OmiPanelModifier(
        fill: fill,
        radius: radius,
        stroke: stroke,
        shadowOpacity: 0.08,
        shadowRadius: 8,
        shadowY: 4
      )
    )
  }
}
