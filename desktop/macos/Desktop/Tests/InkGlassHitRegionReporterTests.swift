import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Regression: `InkGlassHitRegionReporter` is a marker for the pointer, and it has to be *both*
/// things at once — invisible to anything that measures paint, and live to `InkGlassHitRegions`.
///
/// It arrived mounted opaquely (PR #11552, `15a51fb985`) and took the desktop test lane down with
/// 75 failures across `ShellModalScrimTests` and `GlassSurfaceReviewRegressionTests`: `ImageRenderer`
/// cannot rasterise an `NSViewRepresentable`, so it drew an opaque placeholder over the marker's
/// whole host and every "the dim never reaches the window's edge" assertion read the placeholder as
/// the dim. Neither half of the pair is provable from the other — dropping the reporter would satisfy
/// the paint half and silently return the shell to passing clicks through its own modals — so both
/// are held here.
@MainActor
final class InkGlassHitRegionReporterTests: XCTestCase {

  /// The marker contributes no pixels to what the app draws.
  func testTheReporterPaintsNothing() {
    let size = CGSize(width: 60, height: 60)
    let renderer = ImageRenderer(
      content: Color.clear
        .background(InkGlassHitRegionReporter())
        .frame(width: size.width, height: size.height))
    renderer.scale = 1

    guard let image = renderer.cgImage else { return }
    let width = image.width
    let height = image.height
    var pixels = [UInt8](repeating: 0, count: width * height * 4)
    guard
      let context = CGContext(
        data: &pixels,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return XCTFail("could not read the rendered marker") }
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

    let painted = stride(from: 3, to: pixels.count, by: 4).contains { pixels[$0] > 0 }
    XCTAssertFalse(
      painted,
      "the hit-region marker painted into the app's render tree: every surface that mounts one now "
        + "measures as covering its whole host")
  }

  /// …and it still owns the pointer, which is the only reason it exists.
  func testTheReporterStillRegistersItsExtent() {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 200, height: 200),
      styleMask: [.borderless],
      backing: .buffered,
      defer: false)
    let host = NSHostingView(
      rootView: Color.clear
        .background(InkGlassHitRegionReporter())
        .frame(width: 200, height: 200))
    host.frame = NSRect(x: 0, y: 0, width: 200, height: 200)
    window.contentView = host
    host.layoutSubtreeIfNeeded()

    XCTAssertTrue(
      InkGlassHitRegions.shared.containsPoint(NSPoint(x: 100, y: 100), in: window),
      "a surface mounting the marker no longer owns the pointer, so the shell's click-through sync "
        + "would pass clicks on it straight to the app behind the window")
  }
}
