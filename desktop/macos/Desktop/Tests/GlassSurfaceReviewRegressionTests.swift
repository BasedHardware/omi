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

    let clippedCorner = try renderedColor(canvas, size: canvasSize, at: CGPoint(x: 98, y: 98))
    XCTAssertLessThan(
      clippedCorner.greenComponent,
      0.5,
      "the returned red content must not paint through the panel's rounded corner")
    XCTAssertLessThan(
      clippedCorner.redComponent - clippedCorner.greenComponent,
      0.25,
      "the clipped corner should be the glass/background, not the returned red overlay")

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

  private func renderedColor(_ view: some View, size: CGSize, at point: CGPoint) throws -> NSColor {
    let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
    renderer.scale = 1
    guard let image = renderer.cgImage else {
      throw XCTSkip("ImageRenderer did not produce an image for the SwiftUI glass surface")
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
    context.draw(image, in: CGRect(origin: .zero, size: size))

    let x = min(max(Int(point.x), 0), image.width - 1)
    let y = min(max(Int(point.y), 0), image.height - 1)
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
