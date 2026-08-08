import AppKit
import OmiTheme
import SwiftUI

/// The Rewind timeline track: a horizontal bar of per-app coloured segments with app-icon badges
/// pinned along it, hour marks beneath, and a playhead handle.
///
/// **The track is time-linear, and that is the substantive change from the strip it replaces.**
/// `TimeBasedTimelineNSView` mapped a pixel to an *array index* — `frameXPositions` was filled by
/// walking the screenshot array and spacing entries evenly across the bar — so a three-hour gap
/// between two consecutive rows occupied exactly the same width as a three-second one. Every
/// consequence of that is a bug the user can see: "drag left to go back in time" is not true, because
/// how far back a pixel travels depends on how densely that stretch happened to be captured; a lunch
/// break is invisible; and two frames either side of an overnight gap sit adjacent. Here x maps to
/// the capture's `timestamp` over the visible window and the frame is found by binary search, which
/// makes the track an honest picture of a day.
///
/// It is drawn in AppKit rather than SwiftUI for three reasons that are all about the pointer:
/// pixel-exact hit testing during a drag, a scroll wheel that pans, and a hover tooltip that has to
/// be able to escape the window's rounded bounds without being clipped.
@MainActor
final class RewindTrackNSView: NSView, ShellWindowDragExcluding {

  /// Total height of the control: the bar, plus room for the badges that straddle it and the hour
  /// labels beneath.
  static let height: CGFloat = 56
  private static let barHeight: CGFloat = 26
  private static let badgeSize: CGFloat = 18
  /// The narrowest visible segment that may still carry a badge.
  ///
  /// Deliberately smaller than `badgeSize`: the badge is allowed to overhang its own segment, because
  /// at day zoom almost every segment is narrower than 18 points and requiring containment is what
  /// reduces a whole day to one badge. Overlap between *badges* is what actually has to be prevented,
  /// and `badgePlacements()` does that directly.
  private static let minimumBadgeWidth: CGFloat = 4
  private static let cornerRadius: CGFloat = 6

  // MARK: - Input

  private(set) var blocks: [RewindActivityBlock] = []
  /// Capture instants, ascending. Kept as a plain `[Double]` rather than `[Screenshot]` so the hit
  /// test is a binary search over contiguous memory and never touches a struct with eleven fields.
  private(set) var instants: [Double] = []
  private(set) var searchResultIndices: Set<Int>?
  var trackStart: Double = 0
  var trackSpan: Double = 1
  var spanBounds: ClosedRange<Double> = 60...86_400
  var playheadAt: Double?

  /// Called with an index while the user scrubs. Coalesced to one call per display frame — see
  /// `reportScrub`.
  var onSelect: ((Int) -> Void)?
  /// Called when a scrub gesture is over, with the index the pointer finally rested on.
  var onScrubEnd: ((Int) -> Void)?
  /// Called while the user pinches, with the span to show.
  var onZoom: ((Double, Double) -> Void)?

  private var tooltipWindow: NSWindow?
  private var tooltipContent: RewindTrackTooltipView?
  private var trackingAreaAdded: NSTrackingArea?
  private var isScrubbing = false
  private var lastReportedIndex: Int?
  private var pendingScrubIndex: Int?
  private var pinch: (anchor: Double, fraction: Double, startSpan: Double)?
  private var colorCache: [String: NSColor] = [:]

  override var isFlipped: Bool { true }

  override init(frame frameRect: NSRect) {
    super.init(frame: frameRect)
    wantsLayer = true
    // The glass panel is pinned to `.aqua` (see `InkGlass.appearanceName`), but `glassContent()`
    // pins only SwiftUI's `colorScheme` — an environment value an `NSViewRepresentable`'s AppKit
    // view never sees. Without this line every dynamic `NSColor` below resolves in the *machine's*
    // appearance, so on a Dark Mac the playhead and the hour labels render near-white onto a
    // light-pinned panel and disappear. Pinned to the same appearance the glass is.
    appearance = InkGlass.appearance
  }

  required init?(coder: NSCoder) { fatalError("not used") }

  /// Pushes new state in and redraws. One entry point so the representable cannot set half of it.
  func apply(
    blocks: [RewindActivityBlock],
    instants: [Double],
    searchResultIndices: Set<Int>?,
    trackStart: Double,
    trackSpan: Double,
    spanBounds: ClosedRange<Double>,
    playheadAt: Double?
  ) {
    self.blocks = blocks
    self.instants = instants
    self.searchResultIndices = searchResultIndices
    self.trackStart = trackStart
    self.trackSpan = max(1, trackSpan)
    self.spanBounds = spanBounds
    // **Not while the pointer is down.** During a drag the playhead is the pointer's own continuous
    // instant; the index the page is holding lags it by a frame and is quantised to whole captures,
    // so adopting it here would make the handle stutter backwards under the finger moving it.
    // `mouseUp` settles it onto a real capture, which is the one moment the quantised value is right.
    if !isScrubbing {
      self.playheadAt = playheadAt
      // The page can move the playhead without us — an arrow key, a search result, a new day. Letting
      // the last *reported* index go stale would make the next scrub back onto it a no-op, stranding
      // the page where the keyboard left it.
      lastReportedIndex = nil
    }
    needsDisplay = true
  }

  // MARK: - Geometry

  private var barRect: NSRect {
    NSRect(
      x: 0,
      y: (Self.height - Self.barHeight) / 2 - 6,
      width: bounds.width,
      height: Self.barHeight)
  }

  private func x(for instant: Double) -> CGFloat {
    guard trackSpan > 0 else { return 0 }
    return CGFloat((instant - trackStart) / trackSpan) * bounds.width
  }

  private func instant(atX x: CGFloat) -> Double {
    guard bounds.width > 0 else { return trackStart }
    let clamped = min(max(0, x), bounds.width)
    return trackStart + Double(clamped / bounds.width) * trackSpan
  }

  /// The capture nearest an instant, by binary search.
  ///
  /// The strip this replaces scanned every frame position on every mouse event to find the closest
  /// one; at a day of capture that is a linear pass per pointer sample.
  func nearestIndex(to instant: Double) -> Int? {
    guard !instants.isEmpty else { return nil }
    var low = 0
    var high = instants.count - 1
    if instant <= instants[low] { return low }
    if instant >= instants[high] { return high }
    while low + 1 < high {
      let mid = (low + high) / 2
      if instants[mid] <= instant { low = mid } else { high = mid }
    }
    return (instant - instants[low]) <= (instants[high] - instant) ? low : high
  }

  // MARK: - Drawing

  override func draw(_ dirtyRect: NSRect) {
    let bar = barRect
    let shape = NSBezierPath(
      roundedRect: bar, xRadius: Self.cornerRadius, yRadius: Self.cornerRadius)

    // The empty channel. `quaternaryLabelColor` rather than a fixed grey: it is a faint wash of the
    // label colour, so a track with no capture in it reads as empty rather than as a black slab.
    NSColor.quaternaryLabelColor.setFill()
    shape.fill()

    drawHourTicks(in: bar)

    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    for block in blocks { draw(block, in: bar) }
    if let searchResultIndices, !searchResultIndices.isEmpty {
      drawSearchMarkers(searchResultIndices, in: bar)
    }
    NSGraphicsContext.restoreGraphicsState()

    NSColor.separatorColor.setStroke()
    shape.lineWidth = 1
    shape.stroke()

    for placement in badgePlacements() { drawBadge(placement, in: bar) }
    drawPlayhead(in: bar)
  }

  /// Which blocks get a badge, and where.
  ///
  /// Placement is by descending duration with overlap rejection, rather than "every block wide enough
  /// to hold one". The naive rule collapses at day zoom, where a 24-hour window over ~1,140 points
  /// makes even a twenty-minute stretch about 16 points wide. Longest-first is the right priority
  /// because the stretches worth recognising at a glance are the long ones, and rejecting a badge
  /// that would collide with one already placed keeps the row legible at every zoom without hiding
  /// the segments themselves — a segment is always drawn, whether or not it earned a badge.
  private func badgePlacements() -> [(block: RewindActivityBlock, centreX: CGFloat)] {
    let ordered = blocks.enumerated().sorted { lhs, rhs in
      if lhs.element.duration != rhs.element.duration {
        return lhs.element.duration > rhs.element.duration
      }
      // Stable tiebreak, so the badge row does not reshuffle between redraws.
      return lhs.offset < rhs.offset
    }

    let spacing = Self.badgeSize + 5
    var placed: [(block: RewindActivityBlock, centreX: CGFloat)] = []
    for (_, block) in ordered {
      let left = x(for: block.startedAt)
      let right = x(for: block.endedAt)
      guard right >= 0, left <= bounds.width else { continue }
      let visibleLeft = max(0, left)
      let visibleRight = min(bounds.width, right)
      guard visibleRight - visibleLeft >= Self.minimumBadgeWidth else { continue }

      // Centred on the visible part, then pulled inside the track's ends so a badge on the first or
      // last segment is not half cut off.
      let centre = min(
        max((visibleLeft + visibleRight) / 2, Self.badgeSize / 2 + 1),
        bounds.width - Self.badgeSize / 2 - 1)
      guard !placed.contains(where: { abs($0.centreX - centre) < spacing }) else { continue }
      placed.append((block, centre))
    }
    return placed
  }

  private func draw(_ block: RewindActivityBlock, in bar: NSRect) {
    let left = x(for: block.startedAt)
    let right = x(for: block.endedAt)
    guard right >= 0, left <= bounds.width else { return }
    let clippedLeft = max(0, left)
    // A sub-pixel block still happened; give it a visible sliver rather than nothing.
    let width = max(2, min(bounds.width, right) - clippedLeft)
    color(forApp: block.app).setFill()
    NSRect(x: clippedLeft, y: bar.minY, width: width, height: bar.height).fill()
  }

  /// The app's track colour, memoised for the length of this view's life.
  ///
  /// `RewindPalette` is the single definition of the hue — this only remembers the answer, because
  /// deriving it involves a string hash and the drawing loop asks the same question every redraw.
  private func color(forApp app: String) -> NSColor {
    if let hit = colorCache[app] { return hit }
    let colour = RewindPalette.nsColor(forApp: app)
    colorCache[app] = colour
    return colour
  }

  private func drawSearchMarkers(_ indices: Set<Int>, in bar: NSRect) {
    NSColor.systemOrange.withAlphaComponent(0.9).setFill()
    for index in indices where index >= 0 && index < instants.count {
      let markerX = x(for: instants[index])
      guard markerX >= -2, markerX <= bounds.width + 2 else { continue }
      NSRect(x: markerX - 1, y: bar.minY, width: 2, height: bar.height).fill()
    }
  }

  private func drawBadge(_ placement: (block: RewindActivityBlock, centreX: CGFloat), in bar: NSRect) {
    let block = placement.block
    let size = Self.badgeSize
    let rect = NSRect(
      x: placement.centreX - size / 2, y: bar.midY - size / 2, width: size, height: size)

    // A white ring, so the badge reads as sitting *on* the track rather than punched through it, and
    // so a dark icon stays visible over a dark segment. A literal rather than
    // `controlBackgroundColor`: this view is pinned to the glass's light appearance, and white is
    // what that resolves to — spelling it as the semantic colour would invite a future reader to
    // "fix" the pin and get a black ring on a light panel.
    let ring = NSBezierPath(ovalIn: rect.insetBy(dx: -1.5, dy: -1.5))
    NSColor.white.setFill()
    ring.fill()

    if let icon = AppIconCache.shared.getIcon(for: block.app, size: size) {
      NSGraphicsContext.saveGraphicsState()
      NSBezierPath(ovalIn: rect).addClip()
      Self.drawIcon(icon, in: rect)
      NSGraphicsContext.restoreGraphicsState()
    } else {
      // The monogram fallback, in the app's own track colour so the badge still agrees with its
      // segment.
      RewindPalette.nsColor(forApp: block.app).setFill()
      NSBezierPath(ovalIn: rect).fill()
      let letter = String(block.app.prefix(1)).uppercased()
      let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: size * 0.55, weight: .semibold),
        .foregroundColor: NSColor.white,
      ]
      let text = NSAttributedString(string: letter, attributes: attributes)
      let textSize = text.size()
      text.draw(
        at: NSPoint(x: rect.midX - textSize.width / 2, y: rect.midY - textSize.height / 2))
    }
  }

  /// One app icon, into a badge, the right way up.
  ///
  /// **`respectFlipped: true`, and the four-argument overload it replaces is why an icon drawn into a
  /// flipped view comes out mirrored.** `NSImage.draw(in:from:operation:fraction:)` is documented as
  /// behaving like the six-argument form with `respectFlipped: false` — it ignores the flipped state
  /// of the current context and draws in AppKit's bottom-left orientation regardless. This view is
  /// `isFlipped` (the track measures time left-to-right and everything else here top-down), so the
  /// icon would come out mirrored about its horizontal axis. It is invisible on the few icons that
  /// happen to be vertically symmetric, which is how such a defect survives review.
  ///
  /// **Template images are tinted; full-colour artwork is never touched.** `isTemplate` is the app's
  /// own declaration that its icon is a monochrome stencil meant to take on the surrounding label
  /// colour. Drawn as-is that stencil is opaque black, which disappears into a dark badge, so it is
  /// composited with `labelColor`. A real icon is drawn exactly as its author drew it.
  static func drawIcon(_ icon: NSImage, in rect: NSRect) {
    icon.draw(
      in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
    guard icon.isTemplate else { return }
    NSColor.labelColor.set()
    rect.fill(using: .sourceAtop)
  }

  /// How an hour label is set.
  ///
  /// A named seam rather than a literal built inside `draw`, because the colour on this line is the
  /// one thing here a guard has to be able to read. Rebuilt per call on purpose: `NSColor(Ink.secondary)`
  /// is a *dynamic* colour and resolving it at draw time is what lets it follow the appearance this
  /// view is pinned to.
  ///
  /// `Ink.secondary` and not `tertiaryLabelColor`: the system's third label step is black at 0.259,
  /// which on the shipped glass ground measures far under WCAG AA for 9 pt text. See `Ink.tertiary`
  /// for the two-rung rule glass surfaces are held to.
  static var hourLabelAttributes: [NSAttributedString.Key: Any] {
    [
      .font: NSFont.systemFont(ofSize: 9, weight: .regular),
      .foregroundColor: NSColor(Ink.secondary),
    ]
  }

  /// Hour marks, which are what make the time-linearity legible: evenly spaced ticks prove the axis
  /// is time, and a wide empty stretch between two segments is visibly a gap of a known length.
  private func drawHourTicks(in bar: NSRect) {
    let step = tickInterval
    guard step > 0 else { return }
    let attributes = Self.hourLabelAttributes
    let formatter = Self.tickFormatter(forInterval: step)
    var instant = (trackStart / step).rounded(.up) * step
    while instant <= trackStart + trackSpan {
      let tickX = x(for: instant)
      NSColor.separatorColor.setFill()
      NSRect(x: tickX, y: bar.maxY, width: 1, height: 4).fill()

      let label = NSAttributedString(
        string: formatter.string(from: Date(timeIntervalSince1970: instant)),
        attributes: attributes)
      let size = label.size()
      // Only when it fits without colliding with the view's edge.
      if tickX - size.width / 2 >= 0, tickX + size.width / 2 <= bounds.width {
        label.draw(at: NSPoint(x: tickX - size.width / 2, y: bar.maxY + 5))
      }
      instant += step
    }
  }

  /// A tick spacing that yields at most twelve marks at the current zoom, chosen from a ladder of
  /// intervals a person actually thinks in.
  var tickInterval: Double {
    Self.tickInterval(forSpan: trackSpan)
  }

  static func tickInterval(forSpan span: Double) -> Double {
    let candidates: [Double] = [
      60, 300, 600, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600,
    ]
    return candidates.first { span / $0 <= 12 } ?? 24 * 3600
  }

  /// How a tick is labelled, which depends on how far apart the ticks are.
  ///
  /// **The reference labels every tick `h a`, and that is only right while the ticks are an hour or
  /// more apart.** Zoomed in — or on a day with ten minutes of capture in it, which is what a day
  /// looks like just after midnight — the ladder picks a one-minute interval and every label on the
  /// track reads `12 AM`. Five identical labels are worse than none: they say the axis is not moving.
  /// Below an hour the minutes are the information, and the hour is the one thing the reader can
  /// infer from the pill under the frame.
  /// Both are built once. `drawHourTicks` runs on every redraw, and a redraw happens on every pointer
  /// sample of a scrub; constructing a `DateFormatter` there would put a locale lookup on the frame
  /// budget this rebuild exists to protect.
  static func tickFormatter(forInterval interval: Double) -> DateFormatter {
    interval >= 3600 ? hourTickFormatter : minuteTickFormatter
  }

  private static let hourTickFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "h a"
    return formatter
  }()

  private static let minuteTickFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "h:mm"
    return formatter
  }()

  private func drawPlayhead(in bar: NSRect) {
    guard let playheadAt else { return }
    let position = x(for: playheadAt)
    guard position >= -1, position <= bounds.width + 1 else { return }

    let width: CGFloat = 3
    let rect = NSRect(
      x: position - width / 2, y: bar.minY - 4, width: width, height: bar.height + 8)
    let path = NSBezierPath(roundedRect: rect, xRadius: 1.5, yRadius: 1.5)
    // `labelColor` inverts with the appearance, which is what a handle over arbitrary segment colours
    // needs. The appearance it inverts with is the pinned one — see `init`.
    NSColor.labelColor.setFill()
    path.fill()
    NSColor.white.setStroke()
    path.lineWidth = 1
    path.stroke()
  }

  // MARK: - Pointer

  override func updateTrackingAreas() {
    super.updateTrackingAreas()
    if let trackingAreaAdded { removeTrackingArea(trackingAreaAdded) }
    let area = NSTrackingArea(
      rect: bounds,
      options: [.mouseEnteredAndExited, .mouseMoved, .activeInKeyWindow, .inVisibleRect],
      owner: self,
      userInfo: nil)
    addTrackingArea(area)
    trackingAreaAdded = area
  }

  override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

  /// **The scrubber keeps its own drags.**
  ///
  /// `NSView`'s default answer to this is yes for any view that is not opaque, and the shell's window
  /// is `isMovableByWindowBackground` (see `ShellWindowChrome`) so that the parts of a mostly-desktop
  /// window that are not a control drag it. This *is* a control, and it is the one control in the app
  /// whose entire gesture is a drag: without opting out, `mouseDown` seeks once and then AppKit takes
  /// the first `mouseDragged` to move the window, so dragging the playhead walks the whole window
  /// sideways and never advances the day. A click still seeks, which is what makes the failure look
  /// like a rendering quirk rather than a dead gesture.
  override var mouseDownCanMoveWindow: Bool { false }

  override func resetCursorRects() {
    super.resetCursorRects()
    addCursorRect(bounds, cursor: .pointingHand)
  }

  override func mouseDown(with event: NSEvent) {
    isScrubbing = true
    hideTooltip()
    scrub(to: event)
  }

  override func mouseDragged(with event: NSEvent) {
    guard isScrubbing else { return }
    scrub(to: event)
  }

  /// The drag is over. The playhead is wherever the pointer left it, so the final index is delivered
  /// unconditionally — a coalesced scrub may have dropped the last pixel of travel.
  override func mouseUp(with event: NSEvent) {
    guard isScrubbing else { return }
    isScrubbing = false
    let point = convert(event.locationInWindow, from: nil)
    playheadAt = instant(atX: point.x)
    needsDisplay = true
    if let index = nearestIndex(to: instant(atX: point.x)) {
      pendingScrubIndex = nil
      lastReportedIndex = index
      onScrubEnd?(index)
    }
  }

  /// Moves the playhead and reports the frame under it.
  ///
  /// **The playhead is moved here, locally, and the SwiftUI index update is coalesced to one per
  /// display frame.** Both halves matter. Redrawing this view is a handful of rect fills; pushing a
  /// new `currentIndex` into `RewindPage` re-evaluates the whole page body, and a smooth drag across
  /// a day changes the index every three or four pixels. Measured on the live app, that SwiftUI
  /// re-render was four times the cost of the drawing it was there to accompany.
  private func scrub(to event: NSEvent) {
    let point = convert(event.locationInWindow, from: nil)
    let at = instant(atX: point.x)
    playheadAt = at
    needsDisplay = true
    guard let index = nearestIndex(to: at), index != lastReportedIndex else { return }
    reportScrub(index)
  }

  private func reportScrub(_ index: Int) {
    let hadPending = pendingScrubIndex != nil
    pendingScrubIndex = index
    guard !hadPending else { return }
    // One hop through the main queue coalesces every pointer sample that arrives in the same
    // turn of the run loop into a single SwiftUI update.
    DispatchQueue.main.async { [weak self] in
      guard let self, let pending = self.pendingScrubIndex else { return }
      self.pendingScrubIndex = nil
      guard pending != self.lastReportedIndex else { return }
      self.lastReportedIndex = pending
      self.onSelect?(pending)
    }
  }

  /// A trackpad pinch zooms the track: how much *time* it spans, not how large anything is drawn.
  override func magnify(with event: NSEvent) {
    let point = convert(event.locationInWindow, from: nil)
    handleMagnification(Double(event.magnification), phase: event.phase, atX: point.x)
  }

  /// The pinch state machine, split from `magnify(with:)` because an `NSEvent` of a gesture type
  /// cannot be constructed outside the window server — so this is the seam a test can drive, and it
  /// is the production path from the first line after the event is unpacked.
  func handleMagnification(_ delta: Double, phase: NSEvent.Phase, atX x: CGFloat) {
    guard bounds.width > 0, trackSpan > 0 else { return }
    if phase.contains(.ended) || phase.contains(.cancelled) {
      // Dropped rather than wound down: the next gesture must start from whatever the track ended up
      // showing, so two pinches in a row compose instead of the second replaying the first.
      pinch = nil
      return
    }
    if phase.contains(.began) || pinch == nil {
      let fraction = min(max(0, Double(x / bounds.width)), 1)
      pinch = (trackStart + fraction * trackSpan, fraction, trackSpan)
    }
    guard let gesture = pinch else { return }
    let span = min(max(gesture.startSpan / (1 + delta * 4), spanBounds.lowerBound), spanBounds.upperBound)
    onZoom?(gesture.anchor - gesture.fraction * span, span)
  }

  override func mouseMoved(with event: NSEvent) {
    showTooltip(for: event)
  }

  override func mouseExited(with event: NSEvent) {
    hideTooltip()
  }

  // MARK: - Tooltip

  /// The tooltip window, **built once and moved thereafter**.
  ///
  /// The strip this replaces tore down and rebuilt a borderless `NSWindow` around a fresh
  /// `NSHostingView` on every `mouseMoved`, and asked it for `fittingSize` each time — a SwiftUI
  /// graph instantiated and thrown away per pointer sample. Here one window holds one plain `NSView`
  /// and the text is handed to it; nothing is allocated while the pointer moves.
  private func showTooltip(for event: NSEvent) {
    let point = convert(event.locationInWindow, from: nil)
    guard let index = nearestIndex(to: instant(atX: point.x)), let window else {
      hideTooltip()
      return
    }
    let capturedAt = instants[index]
    let label =
      "\(appName(at: capturedAt))  ·  \(Self.tooltipFormatter.string(from: Date(timeIntervalSince1970: capturedAt)))"

    let attributes: [NSAttributedString.Key: Any] = [
      .font: NSFont.systemFont(ofSize: 11, weight: .medium),
      .foregroundColor: NSColor.labelColor,
    ]
    let text = NSAttributedString(string: label, attributes: attributes)
    let padding = NSSize(width: 18, height: 10)
    let size = NSSize(
      width: text.size().width + padding.width, height: text.size().height + padding.height)

    let onScreen = window.convertPoint(toScreen: event.locationInWindow)
    let origin = NSPoint(x: onScreen.x - size.width / 2, y: onScreen.y + 26)

    if let tooltipWindow {
      tooltipWindow.setFrame(NSRect(origin: origin, size: size), display: true)
      tooltipContent?.update(text)
      return
    }

    let container = RewindTrackTooltipView(frame: NSRect(origin: .zero, size: size))
    container.appearance = InkGlass.appearance
    container.update(text)

    let tooltip = NSWindow(
      contentRect: NSRect(origin: origin, size: size),
      styleMask: .borderless,
      backing: .buffered,
      defer: false)
    tooltip.animationBehavior = .none
    tooltip.backgroundColor = .clear
    tooltip.isOpaque = false
    tooltip.level = .floating
    tooltip.ignoresMouseEvents = true
    tooltip.isReleasedWhenClosed = false
    tooltip.appearance = InkGlass.appearance
    tooltip.contentView = container
    tooltip.orderFront(nil)
    tooltipWindow = tooltip
    tooltipContent = container
  }

  private func appName(at instant: Double) -> String {
    blocks.first { instant >= $0.startedAt && instant <= $0.endedAt }?.app
      ?? blocks.last?.app ?? ""
  }

  private func hideTooltip() {
    tooltipWindow?.orderOut(nil)
    tooltipWindow = nil
    tooltipContent = nil
  }

  override func viewWillMove(toWindow newWindow: NSWindow?) {
    super.viewWillMove(toWindow: newWindow)
    // If this view is removed from its window while a tooltip is showing, mouse-exit never fires, so
    // the borderless floating tooltip window would be orphaned on screen. Tear it down here — and
    // drop any gesture whose `.ended` will now never arrive, so the next install does not resume a
    // pinch the user finished in another window.
    if newWindow == nil {
      hideTooltip()
      pinch = nil
      isScrubbing = false
    }
  }

  private static let tooltipFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "h:mm:ss a"
    return formatter
  }()
}

/// The tooltip's own content view. A plain `NSView` drawing a capsule rather than an `NSHostingView`,
/// so the tooltip window has no SwiftUI in it at all — see the note on `showTooltip`.
private final class RewindTrackTooltipView: NSView {
  private var text = NSAttributedString()

  override var isFlipped: Bool { true }

  func update(_ text: NSAttributedString) {
    self.text = text
    needsDisplay = true
  }

  override func draw(_ dirtyRect: NSRect) {
    let shape = NSBezierPath(roundedRect: bounds, xRadius: 7, yRadius: 7)
    NSColor.white.setFill()
    shape.fill()
    NSColor.separatorColor.setStroke()
    shape.lineWidth = 1
    shape.stroke()
    let size = text.size()
    text.draw(at: NSPoint(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2))
  }
}
