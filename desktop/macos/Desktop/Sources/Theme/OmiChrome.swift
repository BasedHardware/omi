import SwiftUI

package enum OmiChrome {
  package static let windowRadius: CGFloat = 26
  package static let cardRadius: CGFloat = 22
  package static let sectionRadius: CGFloat = 18
  package static let controlRadius: CGFloat = 14
  package static let chipRadius: CGFloat = 12
  /// Small controls: compact buttons, inputs, thumbnails.
  package static let smallControlRadius: CGFloat = 12
  /// Small elements: badges, list chips, inline pills.
  package static let elementRadius: CGFloat = 10
  /// Tags and micro badges.
  package static let badgeRadius: CGFloat = 6
  /// Progress bars, underline indicators, hairline strips.
  package static let stripRadius: CGFloat = 3
}

/// Double-bezel panel: outer fill + hairline stroke + inset top highlight +
/// soft tinted shadow. Reads as machined glass sitting on the canvas.
private struct OmiPanelModifier: ViewModifier {
  let fill: Color
  let radius: CGFloat
  let stroke: Color?
  let shadowOpacity: Double
  let shadowRadius: CGFloat
  let shadowY: CGFloat
  let highlight: Bool

  func body(content: Content) -> some View {
    content
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(fill)
          .overlay {
            if highlight {
              RoundedRectangle(cornerRadius: radius, style: .continuous)
                .stroke(
                  LinearGradient(
                    colors: [
                      Color.white.opacity(0.14),
                      Color.white.opacity(0.02),
                      Color.clear,
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                  ),
                  lineWidth: 1
                )
                .padding(0.5)
                .allowsHitTesting(false)
            }
          }
      )
      .overlay {
        if let stroke {
          RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(stroke, lineWidth: 1)
        }
      }
      .shadow(
        color: Color(hex: 0x05060A).opacity(shadowOpacity),
        radius: shadowRadius,
        x: 0,
        y: shadowY
      )
  }
}

extension View {
  package func omiPanel(
    fill: Color = OmiColors.backgroundSecondary,
    radius: CGFloat = OmiChrome.cardRadius,
    stroke: Color? = OmiColors.border.opacity(0.45),
    shadowOpacity: Double = 0.35,
    shadowRadius: CGFloat = 22,
    shadowY: CGFloat = 12,
    highlight: Bool = true
  ) -> some View {
    modifier(
      OmiPanelModifier(
        fill: fill,
        radius: radius,
        stroke: stroke,
        shadowOpacity: shadowOpacity,
        shadowRadius: shadowRadius,
        shadowY: shadowY,
        highlight: highlight
      )
    )
  }

  package func omiControlSurface(
    fill: Color = OmiColors.backgroundTertiary,
    radius: CGFloat = OmiChrome.controlRadius,
    stroke: Color? = OmiColors.border.opacity(0.35),
    highlight: Bool = true
  ) -> some View {
    modifier(
      OmiPanelModifier(
        fill: fill,
        radius: radius,
        stroke: stroke,
        shadowOpacity: 0.22,
        shadowRadius: 10,
        shadowY: 4,
        highlight: highlight
      )
    )
  }
}
