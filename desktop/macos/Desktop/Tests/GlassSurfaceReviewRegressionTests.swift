import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class GlassSurfaceReviewRegressionTests: XCTestCase {

  func testReduceTransparencyObserverRefreshesMountedSurfaceImmediately() {
    let notificationCenter = NotificationCenter()
    let state = MutableAccessibilityState()
    let observer = InkReduceTransparencyObserver(
      notificationCenter: notificationCenter,
      readIsEnabled: { state.value })

    XCTAssertFalse(observer.isEnabled)

    state.value = true
    notificationCenter.post(name: InkReduceTransparency.didChangeNotification, object: nil)

    XCTAssertTrue(
      observer.isEnabled,
      "a mounted SwiftUI surface must see Reduce Transparency on the notification turn, not on a later unrelated rebuild"
    )

    state.value = false
    notificationCenter.post(name: InkReduceTransparency.didChangeNotification, object: nil)
    XCTAssertFalse(observer.isEnabled)
  }

  func testInkGlassPanelClipsReturnedContentButNotAnOuterOverlay() throws {
    let panelSize = CGSize(width: 100, height: 100)
    let canvasSize = CGSize(width: 160, height: 160)

    let panel = ZStack(alignment: .topLeading) {
      Color.clear
      Rectangle()
        .fill(Color.red)
        .frame(width: 30, height: 30)
        .offset(x: 85, y: 85)
    }
    .frame(width: panelSize.width, height: panelSize.height, alignment: .topLeading)
    .inkGlassPanel(cornerRadius: 20, shadow: nil, reduceTransparency: true)
    // This is intentionally attached after the panel modifier. It is an outer glow/overlay and must
    // retain its own extent rather than being caught by the panel's content clip.
    .overlay(alignment: .topLeading) {
      Rectangle()
        .fill(Color.blue)
        .frame(width: 10, height: 10)
        .offset(x: 105, y: 105)
    }

    let canvas = ZStack(alignment: .topLeading) {
      Color.clear.frame(width: canvasSize.width, height: canvasSize.height)
      panel
    }

    // Inside the corner's curve the returned content is on the panel. This is the control: without
    // it a harness that rendered nothing at all would sail through the clip assertion below.
    let insideTheCorner = try renderedColor(canvas, size: canvasSize, at: CGPoint(x: 90, y: 90))
    XCTAssertTrue(
      isReturnedRedContent(insideTheCorner),
      "the returned red content must paint inside the panel's rounded corner")

    // …and eight points further out, past the curve, the same rectangle must be gone. Asserted as
    // "not the returned red" rather than as a colour: what is left there is the panel's own glass,
    // whose lightness belongs to the appearance and is not a fact this test may depend on.
    let clippedCorner = try renderedColor(canvas, size: canvasSize, at: CGPoint(x: 98, y: 98))
    XCTAssertFalse(
      isReturnedRedContent(clippedCorner),
      "the returned red content must not paint through the panel's rounded corner")

    let outerOverlay = try renderedColor(canvas, size: canvasSize, at: CGPoint(x: 108, y: 108))
    XCTAssertGreaterThan(outerOverlay.blueComponent, 0.6)
    XCTAssertLessThan(outerOverlay.redComponent, 0.5)
  }

  func testTransparentTitlebarWearEnforcesFullSizeContentViewPairing() {
    for kind in [WindowGlass.Kind.titled, .summoned] {
      let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 480, height: 320),
        styleMask: [.titled, .closable],
        backing: .buffered,
        defer: true)

      WindowGlass.wear(window, as: kind)

      XCTAssertTrue(window.styleMask.contains(.fullSizeContentView), String(describing: kind))
      XCTAssertTrue(window.titlebarAppearsTransparent, String(describing: kind))
    }
  }

  /// Whether a pixel is the test's red rectangle rather than glass, the blue overlay, or nothing.
  ///
  /// A channel comparison instead of an absolute level: `inkGlassPanel` pins its own colour scheme
  /// and its ground is a system colour, so "how light is the glass" is not something this test may
  /// assert — but "is this pixel dominated by red" is true of the rectangle under any appearance
  /// and false of every neutral.
  private func isReturnedRedContent(_ color: NSColor) -> Bool {
    color.alphaComponent > 0.5
      && color.redComponent - color.greenComponent > 0.25
      && color.redComponent - color.blueComponent > 0.25
  }

  /// Renders through a real `NSHostingView` rather than through `ImageRenderer`.
  ///
  /// `inkGlassPanel` mounts `InkGlassHitRegionReporter`, an `NSViewRepresentable`, so the panel
  /// keeps the pointer inside the window's ownership. `ImageRenderer` cannot draw a representable:
  /// it substitutes a placeholder graphic for the whole panel, and every pixel read back then
  /// describes the placeholder instead of the glass — which is silent, because a placeholder still
  /// has colours to assert against. An AppKit view hierarchy draws the real surface.
  private func renderedColor(_ view: some View, size: CGSize, at point: CGPoint) throws -> NSColor {
    let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height))
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    guard let representation = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
      throw XCTSkip("AppKit did not vend a bitmap for the SwiftUI glass surface")
    }
    host.cacheDisplay(in: host.bounds, to: representation)
    guard let image = representation.cgImage else {
      throw XCTSkip("The cached glass surface bitmap carried no image")
    }

    var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
    guard
      let context = CGContext(
        data: &pixels,
        width: image.width,
        height: image.height,
        bitsPerComponent: 8,
        bytesPerRow: image.width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      )
    else {
      throw XCTSkip("Could not create an image inspection context")
    }
    context.draw(
      image,
      in: CGRect(origin: .zero, size: CGSize(width: image.width, height: image.height)))

    // The bitmap comes back at the display's backing scale, which is not this test's to choose, so
    // the probe point stays in points and is converted here.
    let scale = CGFloat(image.width) / size.width
    let x = min(max(Int(point.x * scale), 0), image.width - 1)
    let y = min(max(Int(point.y * scale), 0), image.height - 1)
    let offset = (y * image.width + x) * 4
    return NSColor(
      srgbRed: CGFloat(pixels[offset]) / 255,
      green: CGFloat(pixels[offset + 1]) / 255,
      blue: CGFloat(pixels[offset + 2]) / 255,
      alpha: CGFloat(pixels[offset + 3]) / 255)
  }
}

@MainActor
private final class MutableAccessibilityState: @unchecked Sendable {
  var value = false
}
