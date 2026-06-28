import AppKit

enum SpatialOverlayGeometry {
  static func screen(from nsScreen: NSScreen) -> SpatialOverlayScreen {
    SpatialOverlayScreen(
      id: nsScreen.localizedName,
      frame: nsScreen.frame,
      visibleFrame: nsScreen.visibleFrame,
      scale: nsScreen.backingScaleFactor
    )
  }

  static func screen(containing rect: CGRect, in screens: [SpatialOverlayScreen])
    -> SpatialOverlayScreen?
  {
    screens
      .map { screen in (screen, screen.frame.intersection(rect).spatialOverlayArea) }
      .filter { $0.1 > 0 }
      .sorted { lhs, rhs in lhs.1 > rhs.1 }
      .first?.0
  }

  static func screen(containing point: CGPoint, in screens: [SpatialOverlayScreen])
    -> SpatialOverlayScreen?
  {
    screens.first { $0.frame.contains(point) }
  }

  static func screenForTarget(windowFrame: CGRect, targetPoint: CGPoint? = nil)
    -> SpatialOverlayScreen?
  {
    let screens = NSScreen.screens.map(screen(from:))
    if let targetPoint, let screen = screen(containing: targetPoint, in: screens) {
      return screen
    }
    return screen(containing: windowFrame, in: screens) ?? screens.first
  }

  static func screenFrameForTopLeftNormalization(preferredScreen: NSScreen? = NSScreen.main)
    -> NSRect
  {
    preferredScreen?.frame ?? .zero
  }

  static func appKitFrame(topLeftOrigin: CGPoint, size: CGSize, screenFrame: CGRect) -> CGRect {
    CGRect(
      x: topLeftOrigin.x,
      y: screenFrame.maxY - topLeftOrigin.y - size.height,
      width: size.width,
      height: size.height
    )
  }

  static func appKitFrame(topLeftFrame frame: CGRect, screenFrame: CGRect) -> CGRect {
    appKitFrame(topLeftOrigin: frame.origin, size: frame.size, screenFrame: screenFrame)
  }

  static func imageRectToWindowRect(_ imageRect: CGRect, imageSize: CGSize, windowFrame: CGRect)
    -> CGRect
  {
    guard imageSize.width > 0, imageSize.height > 0 else { return .zero }

    let scaleX = windowFrame.width / imageSize.width
    let scaleY = windowFrame.height / imageSize.height
    return CGRect(
      x: windowFrame.minX + imageRect.minX * scaleX,
      y: windowFrame.maxY - imageRect.maxY * scaleY,
      width: imageRect.width * scaleX,
      height: imageRect.height * scaleY
    )
  }

  static func frameAnchoredBelow(
    anchorFrame: CGRect,
    contentSize: CGSize,
    minimumWidth: CGFloat,
    gap: CGFloat
  ) -> CGRect {
    let width = max(contentSize.width, minimumWidth)
    return CGRect(
      x: anchorFrame.midX - width / 2,
      y: anchorFrame.minY - gap - contentSize.height,
      width: width,
      height: contentSize.height
    )
  }

  static func clamped(_ frame: CGRect, to visibleFrame: CGRect, padding: CGFloat = 0) -> CGRect {
    guard visibleFrame.width > 0, visibleFrame.height > 0 else { return frame }

    let minX = visibleFrame.minX + padding
    let maxX = max(minX, visibleFrame.maxX - frame.width - padding)
    let minY = visibleFrame.minY + padding
    let maxY = max(minY, visibleFrame.maxY - frame.height - padding)

    return CGRect(
      x: min(max(frame.minX, minX), maxX),
      y: min(max(frame.minY, minY), maxY),
      width: frame.width,
      height: frame.height
    )
  }

  static func clamped(_ value: CGFloat, min minValue: CGFloat, max maxValue: CGFloat) -> CGFloat {
    guard minValue <= maxValue else { return minValue }
    return Swift.min(Swift.max(value, minValue), maxValue)
  }

  static func glowEdgeFrame(
    for edge: GlowEdge,
    around targetRect: CGRect,
    thickness: CGFloat,
    overlap: CGFloat
  ) -> CGRect {
    switch edge {
    case .top:
      return CGRect(
        x: targetRect.minX - thickness,
        y: targetRect.maxY - overlap,
        width: targetRect.width + thickness * 2,
        height: thickness + overlap
      )
    case .bottom:
      return CGRect(
        x: targetRect.minX - thickness,
        y: targetRect.minY - thickness,
        width: targetRect.width + thickness * 2,
        height: thickness + overlap
      )
    case .left:
      return CGRect(
        x: targetRect.minX - thickness,
        y: targetRect.minY - thickness,
        width: thickness + overlap,
        height: targetRect.height + thickness * 2
      )
    case .right:
      return CGRect(
        x: targetRect.maxX - overlap,
        y: targetRect.minY - thickness,
        width: thickness + overlap,
        height: targetRect.height + thickness * 2
      )
    }
  }
}

extension CGRect {
  fileprivate var spatialOverlayArea: CGFloat {
    guard !isNull, !isInfinite else { return 0 }
    return max(0, width) * max(0, height)
  }
}
