import AppKit
import WebKit

/// The shell has two compositions. Home owns a query island in addition to
/// the persistent navigation and result islands; every other route owns one
/// page island below navigation.
enum GlassHostLayout: Equatable {
  case home
  case page

  static func resolve(from url: URL) -> GlassHostLayout {
    let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    let value = { (name: String) in items.first(where: { $0.name == name })?.value }
    if let route = value("route") { return route == "home" ? .home : .page }
    if let fixture = value("qa") { return fixture == "home" ? .home : .page }
    // The production surface defaults to Home when no explicit route exists.
    return .home
  }
}

/// WebKit consumes mouse-down events even over visually empty page regions,
/// which prevents `isMovableByWindowBackground` from making the navigation
/// island behave like the native Swift shell. Keep one explicit native drag
/// lane over the bar's unused centre while leaving every web control exposed.
@MainActor
private final class WindowDragRegionView: NSView {
  override var isOpaque: Bool { false }
  override var mouseDownCanMoveWindow: Bool { true }

  override func mouseDown(with event: NSEvent) {
    window?.performDrag(with: event)
  }
}

/// Native material behind the shared surface. Geometry deliberately matches
/// the desktop CSS and the summoned-shell composition in PR #11117: independent
/// glass islands with the desktop visible between them, never one opaque canvas.
@MainActor
final class GlassHostView: NSView {
  private let topGlass = GlassPanelView(cornerRadius: 26)
  private let heroGlass = GlassPanelView(cornerRadius: 22)
  private let contentGlass = GlassPanelView(cornerRadius: 22)
  private let topBarDragRegion = WindowDragRegionView(frame: .zero)
  let webView: WKWebView
  private(set) var composition: GlassHostLayout
  private var interactiveIslands: [NSBezierPath] = []
  private let webContentMask = CAShapeLayer()

  init(frame: NSRect, webView: WKWebView, composition: GlassHostLayout) {
    self.webView = webView
    self.composition = composition
    super.init(frame: frame)
    wantsLayer = true
    layer?.backgroundColor = NSColor.clear.cgColor
    addSubview(topGlass)
    addSubview(heroGlass)
    addSubview(contentGlass)
    addSubview(webView)
    addSubview(topBarDragRegion, positioned: .above, relativeTo: webView)
    webContentMask.fillColor = NSColor.black.cgColor
    webView.layer?.mask = webContentMask
    webView.translatesAutoresizingMaskIntoConstraints = false
    NSLayoutConstraint.activate([
      webView.leadingAnchor.constraint(equalTo: leadingAnchor),
      webView.trailingAnchor.constraint(equalTo: trailingAnchor),
      webView.topAnchor.constraint(equalTo: topAnchor),
      webView.bottomAnchor.constraint(equalTo: bottomAnchor),
    ])
  }

  required init?(coder: NSCoder) { nil }

  func setComposition(_ composition: GlassHostLayout) {
    guard self.composition != composition else { return }
    self.composition = composition
    needsLayout = true
  }

  override func layout() {
    super.layout()
    let gutter: CGFloat = 16
    let bottom: CGFloat = 20
    let top: CGFloat = 18
    let navHeight: CGFloat = 52
    topGlass.frame = NSRect(x: gutter, y: bounds.height - top - navHeight,
                            width: max(0, bounds.width - gutter * 2), height: navHeight)
    // The reference bar's left route cluster and right utility cluster remain
    // native-web interactive. The flexible middle is a large, deterministic
    // repositioning handle at every supported window width.
    let leftControlsWidth = min(520, max(0, topGlass.bounds.width - 200))
    let rightControlsWidth: CGFloat = 150
    topBarDragRegion.frame = NSRect(
      x: topGlass.frame.minX + leftControlsWidth,
      y: topGlass.frame.minY,
      width: max(0, topGlass.bounds.width - leftControlsWidth - rightControlsWidth),
      height: navHeight)

    switch composition {
    case .home:
      let navToHeroGap: CGFloat = 8
      let heroHeight: CGFloat = 64
      let heroToResultsGap: CGFloat = 12
      heroGlass.isHidden = false
      heroGlass.frame = NSRect(
        x: gutter,
        y: bounds.height - top - navHeight - navToHeroGap - heroHeight,
        width: max(0, bounds.width - gutter * 2),
        height: heroHeight)
      contentGlass.frame = NSRect(
        x: gutter,
        y: bottom,
        width: max(0, bounds.width - gutter * 2),
        height: max(
          0,
          bounds.height - top - navHeight - navToHeroGap - heroHeight
            - heroToResultsGap - bottom))
    case .page:
      let gap: CGFloat = 16
      heroGlass.isHidden = true
      heroGlass.frame = .zero
      contentGlass.frame = NSRect(
        x: gutter,
        y: bottom,
        width: max(0, bounds.width - gutter * 2),
        height: max(0, bounds.height - top - navHeight - gap - bottom))
    }

    let visiblePanels = [topGlass, heroGlass, contentGlass].filter { !$0.isHidden }
    interactiveIslands = visiblePanels.map {
      NSBezierPath(roundedRect: $0.frame, xRadius: $0.cornerRadius, yRadius: $0.cornerRadius)
    }
    let webPath = CGMutablePath()
    for panel in visiblePanels {
      // GlassHost is unflipped AppKit coordinates; WKWebView is flipped.
      // Convert rather than mirroring by hand so resizing keeps the mask exact.
      let webRect = webView.convert(panel.frame, from: self)
      webPath.addRoundedRect(
        in: webRect,
        cornerWidth: panel.cornerRadius,
        cornerHeight: panel.cornerRadius)
    }
    // WKWebView still allocates an opaque IOSurface on some macOS builds even
    // when both its page and NSView report clear. Masking that surface to the
    // actual islands makes the composition invariant independent of that
    // implementation detail; native panels own the shadows outside this path.
    webContentMask.frame = webView.bounds
    webContentMask.path = webPath
  }

  /// Empty wallpaper gaps are window drag handles, not an invisible web page.
  /// Returning the host here prevents WKWebView from swallowing those drags;
  /// controls inside an island continue through normal WebKit hit testing.
  override func hitTest(_ point: NSPoint) -> NSView? {
    guard interactiveIslands.contains(where: { $0.contains(point) }) else { return self }
    return super.hitTest(point)
  }

  override var mouseDownCanMoveWindow: Bool { true }
}

/// One faithful Ink glass island. The outer layer owns the ambient shadow;
/// clipping happens on the inner material so the shadow is not accidentally
/// cut off at the same rounded edge it is meant to describe.
@MainActor
private final class GlassPanelView: NSView {
  private let material = NSVisualEffectView(frame: .zero)
  private let scrim = NSView(frame: .zero)
  let cornerRadius: CGFloat

  init(cornerRadius: CGFloat) {
    self.cornerRadius = cornerRadius
    super.init(frame: .zero)
    wantsLayer = true
    layer?.cornerRadius = cornerRadius
    layer?.cornerCurve = .continuous
    layer?.masksToBounds = false
    layer?.shadowColor = NSColor.black.cgColor
    layer?.shadowOpacity = 0.16
    layer?.shadowOffset = NSSize(width: 0, height: -8)
    layer?.shadowRadius = 22

    material.translatesAutoresizingMaskIntoConstraints = false
    material.material = .hudWindow
    material.blendingMode = .behindWindow
    material.state = .active
    material.appearance = NSAppearance(named: .aqua)
    material.wantsLayer = true
    material.layer?.cornerRadius = cornerRadius
    material.layer?.cornerCurve = .continuous
    material.layer?.masksToBounds = true

    scrim.translatesAutoresizingMaskIntoConstraints = false
    scrim.wantsLayer = true
    material.addSubview(scrim)
    addSubview(material)
    NSLayoutConstraint.activate([
      material.leadingAnchor.constraint(equalTo: leadingAnchor),
      material.trailingAnchor.constraint(equalTo: trailingAnchor),
      material.topAnchor.constraint(equalTo: topAnchor),
      material.bottomAnchor.constraint(equalTo: bottomAnchor),
      scrim.leadingAnchor.constraint(equalTo: material.leadingAnchor),
      scrim.trailingAnchor.constraint(equalTo: material.trailingAnchor),
      scrim.topAnchor.constraint(equalTo: material.topAnchor),
      scrim.bottomAnchor.constraint(equalTo: material.bottomAnchor),
    ])
    refreshAccessibilityGround()
  }

  required init?(coder: NSCoder) { nil }

  override func layout() {
    super.layout()
    layer?.shadowPath = CGPath(roundedRect: bounds, cornerWidth: cornerRadius,
                               cornerHeight: cornerRadius, transform: nil)
    material.layer?.borderWidth = 0.75
    material.layer?.borderColor = NSColor.white.withAlphaComponent(0.34).cgColor
  }

  /// Reduce Transparency must produce a stable opaque ground rather than a
  /// half-disabled blur. Normal mode uses the measured 0.46 Ink scrim.
  private func refreshAccessibilityGround() {
    let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
    material.isHidden = false
    scrim.layer?.backgroundColor = NSColor.controlBackgroundColor
      .withAlphaComponent(reduced ? 0.98 : 0.46).cgColor
  }
}
