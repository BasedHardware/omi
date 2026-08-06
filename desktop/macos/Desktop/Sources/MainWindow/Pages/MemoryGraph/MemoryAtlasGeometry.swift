import CoreGraphics

enum MemoryAtlasGeometry {
  static func constrainedToDisk(
    _ point: CGPoint,
    in area: CGRect,
    radiusFraction: CGFloat = 0.5
  ) -> CGPoint {
    let center = CGPoint(x: area.midX, y: area.midY)
    let radius = min(area.width, area.height) * max(0, min(radiusFraction, 0.5))
    let delta = CGPoint(x: point.x - center.x, y: point.y - center.y)
    let distance = hypot(delta.x, delta.y)
    guard distance > radius else { return point }
    return CGPoint(x: center.x + delta.x / distance * radius, y: center.y + delta.y / distance * radius)
  }
}
