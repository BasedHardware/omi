import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The shell window is transparent and larger than the panels inside it, so it decides where to
/// pass a click through by asking which points a glass panel actually covers. These mount a real
/// panel in a real window and ask that question through the production seam.
@MainActor
final class GlassPanelHitRegionTests: XCTestCase {
  private var window: NSWindow?

  /// Reduce Transparency drops the material, and the first fix registered the panel's extent from
  /// the material's own view — so in that accessibility mode the shell had no registered surface,
  /// fell back to "everything is interactive", and the desktop dead zone came back. The panel must
  /// own its region in both modes.
  func testPanelOwnsItsRegionEvenWithReduceTransparency() throws {
    for reduceTransparency in [true, false] {
      let panel = mountPanel(reduceTransparency: reduceTransparency)
      defer { teardownWindow() }

      let inside = NSPoint(x: panel.midX, y: panel.midY)
      let outsideBeside = NSPoint(x: panel.maxX + 30, y: panel.midY)
      let outsideAbove = NSPoint(x: panel.midX, y: panel.maxY + 30)

      let window = try XCTUnwrap(self.window)
      XCTAssertTrue(
        InkGlassHitRegions.shared.hasSurfaces(in: window),
        "reduceTransparency=\(reduceTransparency): the panel must register a surface")
      XCTAssertTrue(
        InkGlassHitRegions.shared.containsPoint(inside, in: window),
        "reduceTransparency=\(reduceTransparency): the panel owns its own area")
      XCTAssertFalse(
        InkGlassHitRegions.shared.containsPoint(outsideBeside, in: window),
        "reduceTransparency=\(reduceTransparency): air beside the panel passes clicks through")
      XCTAssertFalse(
        InkGlassHitRegions.shared.containsPoint(outsideAbove, in: window),
        "reduceTransparency=\(reduceTransparency): air above the panel passes clicks through")
    }
  }

  /// The whole point of the registry: the shell policy answers the same way the registry does, so
  /// air stays click-through while the panel stays interactive.
  func testShellPolicyPassesAirThroughAndKeepsThePanelInteractive() throws {
    let panel = mountPanel(reduceTransparency: true)
    defer { teardownWindow() }
    let window = try XCTUnwrap(self.window)
    let contains: (NSPoint) -> Bool = { point in
      guard InkGlassHitRegions.shared.hasSurfaces(in: window) else { return true }
      return InkGlassHitRegions.shared.containsPoint(point, in: window)
    }

    XCTAssertTrue(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: panel.midX, y: panel.midY),
        windowSize: window.frame.size,
        isResizable: false,
        contentContains: contains))
    XCTAssertFalse(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: panel.midX, y: panel.maxY + 40),
        windowSize: window.frame.size,
        isResizable: false,
        contentContains: contains),
      "the band above the panel is air and must not swallow a click aimed at another app")
  }

  /// Mounts one glass panel inset inside a larger transparent window and returns the panel's frame
  /// in window coordinates.
  private func mountPanel(reduceTransparency: Bool) -> NSRect {
    let windowSize = NSSize(width: 400, height: 300)
    let panelSize = NSSize(width: 200, height: 120)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: windowSize),
      styleMask: [.borderless],
      backing: .buffered,
      defer: false)
    window.isOpaque = false
    window.backgroundColor = .clear

    let root = VStack {
      Color.clear
        .frame(width: panelSize.width, height: panelSize.height)
        .inkGlassPanel(cornerRadius: 20, shadow: nil, reduceTransparency: reduceTransparency)
    }
    .frame(width: windowSize.width, height: windowSize.height, alignment: .center)

    let hosting = NSHostingView(rootView: root)
    hosting.frame = NSRect(origin: .zero, size: windowSize)
    window.contentView = hosting
    window.orderFront(nil)
    hosting.layoutSubtreeIfNeeded()
    self.window = window

    return NSRect(
      x: (windowSize.width - panelSize.width) / 2,
      y: (windowSize.height - panelSize.height) / 2,
      width: panelSize.width,
      height: panelSize.height)
  }

  private func teardownWindow() {
    window?.orderOut(nil)
    window = nil
  }
}
