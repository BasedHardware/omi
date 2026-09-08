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

  /// A panel is a squircle. Testing its bare bounds made each rounded corner a small dead zone over
  /// whatever sits behind the window.
  func testCornerCutOutsAreAirNotSurface() {
    let bounds = NSRect(x: 0, y: 0, width: 200, height: 120)
    let radius: CGFloat = 20

    let contains: (CGFloat, CGFloat) -> Bool = { x, y in
      InkGlassHitRegions.roundedRectContains(
        point: NSPoint(x: x, y: y), bounds: bounds, cornerRadius: radius)
    }

    XCTAssertTrue(contains(100, 60), "the panel's middle is surface")
    XCTAssertTrue(contains(1, 60), "a straight edge between the corners is surface")
    XCTAssertTrue(contains(100, 1), "the flat bottom edge is surface")
    XCTAssertFalse(contains(1, 1), "the bottom-left corner cut-out is air")
    XCTAssertFalse(contains(199, 119), "the top-right corner cut-out is air")
    XCTAssertTrue(
      contains(radius - radius / 4, radius - radius / 4),
      "inside the corner arc is still surface")
    XCTAssertFalse(contains(-1, 60), "outside the bounds is air")

    XCTAssertTrue(
      InkGlassHitRegions.roundedRectContains(
        point: NSPoint(x: 1, y: 1), bounds: bounds, cornerRadius: 0),
      "a square surface keeps its corners")
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

  /// The panel-hosted Settings menu inherits the page panel rather than adding a second material,
  /// so it owns no standalone glass surface and claims no hit region of its own. (The legacy
  /// sidebar shell this used to compare against is gone.)
  func testPanelHostedSettingsMenuAddsNoSecondSurface() throws {
    defer { teardownWindow() }

    for host in SidebarHost.allCases {
      let sidebar = mountSidebar(host)
      let window = try XCTUnwrap(self.window)
      let inside = NSPoint(x: sidebar.midX, y: sidebar.midY)
      let beside = NSPoint(x: sidebar.maxX + 40, y: sidebar.midY)

      XCTAssertEqual(
        InkGlassHitRegions.shared.hasSurfaces(in: window), host.expectsSurface,
        "\(host): standalone ownership must match the host")
      XCTAssertEqual(
        hasBehindWindowGlass(in: window), host.expectsSurface,
        "\(host): a standalone menu needs actual glass, not only an invisible hit marker")
      XCTAssertEqual(
        InkGlassHitRegions.shared.containsPoint(inside, in: window), host.expectsSurface,
        "\(host): every visible legacy menu must keep mouse input")
      XCTAssertFalse(
        InkGlassHitRegions.shared.containsPoint(beside, in: window),
        "the sidebar must not make the transparent space beside it interactive")
      XCTAssertEqual(
        ShellClickThroughPolicy.acceptsMouseHit(
          localPoint: inside,
          windowSize: window.frame.size,
          isResizable: false,
          contentContains: { InkGlassHitRegions.shared.containsPoint($0, in: window) }),
        host.expectsSurface)

      teardownWindow()
    }
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

  private enum SidebarHost: CaseIterable {
    case panelSettings

    var expectsSurface: Bool { false }
    var width: CGFloat { SettingsSidebarMetrics.expandedWidth }
  }

  private func mountSidebar(_ host: SidebarHost) -> NSRect {
    let windowSize = NSSize(width: 500, height: 500)
    let sidebarSize = NSSize(width: host.width, height: windowSize.height)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: windowSize),
      styleMask: [.borderless],
      backing: .buffered,
      defer: false)
    window.isOpaque = false
    window.backgroundColor = .clear

    let sidebar: AnyView
    switch host {
    case .panelSettings:
      sidebar = AnyView(settingsSidebar)
    }

    let root = HStack(spacing: 0) {
      sidebar
      Spacer(minLength: 0)
    }
    .frame(width: windowSize.width, height: windowSize.height)

    let hosting = NSHostingView(rootView: root)
    hosting.frame = NSRect(origin: .zero, size: windowSize)
    window.contentView = hosting
    NonintrusiveTestWindow.orderIn(window)
    hosting.layoutSubtreeIfNeeded()
    self.window = window

    return NSRect(origin: .zero, size: sidebarSize)
  }

  private var settingsSidebar: some View {
    SettingsSidebar(
      selectedSection: .constant(.general),
      highlightedSettingId: .constant(nil),
      onBack: {},
      appState: AppState()
    )
  }

  private func hasBehindWindowGlass(in window: NSWindow) -> Bool {
    guard let contentView = window.contentView else { return false }
    return viewTree(rootedAt: contentView).contains { view in
      guard let material = view as? NSVisualEffectView else { return false }
      return material.blendingMode == .behindWindow
    }
  }

  private func viewTree(rootedAt root: NSView) -> [NSView] {
    [root] + root.subviews.flatMap { viewTree(rootedAt: $0) }
  }

  private func teardownWindow() {
    window?.orderOut(nil)
    window = nil
  }
}
