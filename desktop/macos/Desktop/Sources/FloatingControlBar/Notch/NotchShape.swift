import SwiftUI

/// The notch silhouette: top corners curve inward from the screen edge (small
/// radius), bottom corners flare outward (large radius). Both radii animate
/// independently so the shape morphs smoothly between closed and open.
struct NotchShape: Shape {
  private var topCornerRadius: CGFloat
  private var bottomCornerRadius: CGFloat

  init(
    topCornerRadius: CGFloat = NotchMetrics.cornerClosed.top,
    bottomCornerRadius: CGFloat = NotchMetrics.cornerClosed.bottom
  ) {
    self.topCornerRadius = topCornerRadius
    self.bottomCornerRadius = bottomCornerRadius
  }

  var animatableData: AnimatablePair<CGFloat, CGFloat> {
    get { .init(topCornerRadius, bottomCornerRadius) }
    set {
      topCornerRadius = newValue.first
      bottomCornerRadius = newValue.second
    }
  }

  func path(in rect: CGRect) -> Path {
    var path = Path()

    path.move(to: CGPoint(x: rect.minX, y: rect.minY))

    path.addQuadCurve(
      to: CGPoint(x: rect.minX + topCornerRadius, y: rect.minY + topCornerRadius),
      control: CGPoint(x: rect.minX + topCornerRadius, y: rect.minY)
    )

    path.addLine(
      to: CGPoint(x: rect.minX + topCornerRadius, y: rect.maxY - bottomCornerRadius)
    )

    path.addQuadCurve(
      to: CGPoint(x: rect.minX + topCornerRadius + bottomCornerRadius, y: rect.maxY),
      control: CGPoint(x: rect.minX + topCornerRadius, y: rect.maxY)
    )

    path.addLine(
      to: CGPoint(x: rect.maxX - topCornerRadius - bottomCornerRadius, y: rect.maxY)
    )

    path.addQuadCurve(
      to: CGPoint(x: rect.maxX - topCornerRadius, y: rect.maxY - bottomCornerRadius),
      control: CGPoint(x: rect.maxX - topCornerRadius, y: rect.maxY)
    )

    path.addLine(
      to: CGPoint(x: rect.maxX - topCornerRadius, y: rect.minY + topCornerRadius)
    )

    path.addQuadCurve(
      to: CGPoint(x: rect.maxX, y: rect.minY),
      control: CGPoint(x: rect.maxX - topCornerRadius, y: rect.minY)
    )

    path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
    return path
  }
}
