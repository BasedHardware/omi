import AppKit
import ContextCore
import SwiftUI

/// The timeline track: a horizontal bar of per-app coloured segments with app-icon badges pinned
/// along it, and a playhead handle.
///
/// **The track is time-linear, and that is the substantive change from the implementation this was
/// ported from.** Theirs maps a pixel to an *array index* — `frameXPositions` is filled by walking
/// the screenshot array and spacing entries evenly across the bar — so a three-hour gap between two
/// consecutive rows occupies exactly the same width as a three-second one. Every consequence of that
/// is a bug the user can see: "scroll left to go back in time" is not true, because how far back a
/// pixel travels depends on how densely that stretch happened to be captured; a lunch break is
/// invisible; and two frames either side of an overnight gap sit adjacent. Here x maps to
/// `capturedAt` over the visible window and the frame is found by binary search
/// (`Array<RewindFrame>.nearestIndex(to:)`), which makes the track an honest picture of a day and
/// makes "zoom" mean the one obvious thing: the width of the visible time window.
///
/// It is drawn in AppKit rather than SwiftUI for three reasons that are all about the pointer:
/// pixel-exact hit testing during a drag, a scroll wheel that pans, and a hover tooltip that has to
/// be able to escape the window's rounded bounds without being clipped. The last of those is why
/// there is a floating tooltip window here at all, and why the teardown below matters.
final class RewindTrackView: NSView {

    /// Total height of the control: the bar, plus room for the badges that straddle it and the hour
    /// labels beneath.
    static let height: CGFloat = 56
    private static let barHeight: CGFloat = 26
    private static let badgeSize: CGFloat = 18
    /// The narrowest visible segment that may still carry a badge.
    ///
    /// Deliberately smaller than `badgeSize`: the badge is allowed to overhang its own segment,
    /// because at day zoom almost every segment is narrower than 18 points and requiring containment
    /// is what reduced a whole day to one badge. Overlap between *badges* is what actually has to be
    /// prevented, and `badgePlacements()` does that directly.
    ///
    /// Tuned against a real day rather than reasoned about: 22 points drew **1** badge for a full day
    /// of capture, 8 points drew **4**, and 4 points fills the row. A floor still exists so a segment
    /// that is a rounding error wide cannot take a slot from a real one — and because placement is
    /// longest-first, the slots go to the stretches worth recognising whatever this value is.
    private static let minimumBadgeWidth: CGFloat = 4
    private static let cornerRadius: CGFloat = 6

    // MARK: - Input

    var blocks: [ActivityBlock] = []
    var frames: [RewindFrame] = []
    var trackStart: Double = 0
    var trackSpan: Double = 1
    /// The range `trackSpan` may move within, so a pinch stops where the buttons stop.
    var spanBounds: ClosedRange<Double> = RewindZoom.minimumSpan...RewindZoom.maximumSpan
    var playheadAt: Double?

    /// Called with an instant when the user scrubs. The model turns it into a frame.
    var onScrub: ((Double) -> Void)?
    /// Called with a signed number of seconds when the user scrolls. Positive is forward in time.
    var onTravel: ((Double) -> Void)?
    /// Called when a scrub gesture is over — the pointer released, or the scroll and the inertia
    /// behind it run out. The model settles the playhead onto a real capture; see `RewindModel.endScrub`.
    var onScrubEnd: (() -> Void)?
    /// Called while the user pinches. The model turns it into a visible window.
    var onZoom: ((RewindZoom.Target) -> Void)?
    /// Called with +1 or −1 when the track is stepped without a pointer. One capture per step.
    var onStep: ((Int) -> Void)?

    private var tooltipWindow: NSWindow?
    private var trackingAreaAdded: NSTrackingArea?

    /// The pinch in progress, or nil between gestures. See `RewindPinch` for why this is held across
    /// events rather than recomputed from each one.
    private var pinch: RewindPinch?

    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    /// Pushes new state in and redraws. One entry point so the representable cannot set half of it.
    func apply(
        blocks: [ActivityBlock],
        frames: [RewindFrame],
        trackStart: Double,
        trackSpan: Double,
        playheadAt: Double?,
        spanBounds: ClosedRange<Double> = RewindZoom.minimumSpan...RewindZoom.maximumSpan
    ) {
        self.blocks = blocks
        self.frames = frames
        self.trackStart = trackStart
        self.trackSpan = max(1, trackSpan)
        self.spanBounds = spanBounds
        self.playheadAt = playheadAt
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

    // MARK: - Drawing

    override func draw(_ dirtyRect: NSRect) {
        let bar = barRect
        let shape = NSBezierPath(
            roundedRect: bar, xRadius: Self.cornerRadius, yRadius: Self.cornerRadius)

        // The empty channel. `quaternaryLabelColor` rather than a fixed grey: it is a faint wash of
        // the label colour, so it darkens a light window and lightens a dark one — a track with no
        // capture in it must read as empty in both appearances.
        NSColor.quaternaryLabelColor.setFill()
        shape.fill()

        drawHourTicks(in: bar)

        NSGraphicsContext.saveGraphicsState()
        shape.addClip()
        for block in blocks { draw(block, in: bar) }
        NSGraphicsContext.restoreGraphicsState()

        NSColor.separatorColor.setStroke()
        shape.lineWidth = 1
        shape.stroke()

        for placement in badgePlacements() { drawBadge(placement, in: bar) }
        drawPlayhead(in: bar)
    }

    /// Which blocks get a badge, and where.
    ///
    /// Placement is by descending duration with overlap rejection, rather than "every block wide
    /// enough to hold one". The naive rule collapses at day zoom, where a 24-hour window over ~1,180
    /// points makes even a twenty-minute stretch about 16 points wide: measured on the real database
    /// it drew exactly **one** badge for a full day of capture, which is not the "app-icon badges
    /// pinned at their positions along the track" the spec asks for. Longest-first is the right
    /// priority because the stretches worth recognising at a glance are the long ones, and rejecting
    /// a badge that would collide with one already placed keeps the row legible at every zoom
    /// without hiding the segments themselves — a segment is always drawn, whether or not it earned
    /// a badge.
    private func badgePlacements() -> [(block: ActivityBlock, centreX: CGFloat)] {
        let ordered = blocks.enumerated().sorted { lhs, rhs in
            if lhs.element.durationSeconds != rhs.element.durationSeconds {
                return lhs.element.durationSeconds > rhs.element.durationSeconds
            }
            // Stable tiebreak, so the badge row does not reshuffle between redraws.
            return lhs.offset < rhs.offset
        }

        let spacing = Self.badgeSize + 5
        var placed: [(block: ActivityBlock, centreX: CGFloat)] = []
        for (_, block) in ordered {
            let left = x(for: block.startedAt)
            let right = x(for: block.endedAt)
            // Off-screen entirely.
            guard right >= 0, left <= bounds.width else { continue }
            let visibleLeft = max(0, left)
            let visibleRight = min(bounds.width, right)
            guard visibleRight - visibleLeft >= Self.minimumBadgeWidth else { continue }

            // Centred on the visible part, then pulled inside the track's ends so a badge on the
            // first or last segment is not half cut off.
            let centre = min(
                max((visibleLeft + visibleRight) / 2, Self.badgeSize / 2 + 1),
                bounds.width - Self.badgeSize / 2 - 1)
            guard !placed.contains(where: { abs($0.centreX - centre) < spacing }) else { continue }
            placed.append((block, centre))
        }
        return placed
    }

    private func draw(_ block: ActivityBlock, in bar: NSRect) {
        let left = x(for: block.startedAt)
        let right = x(for: block.endedAt)
        guard right >= 0, left <= bounds.width else { return }
        let clippedLeft = max(0, left)
        // A sub-pixel block still happened; give it a visible sliver rather than nothing.
        let width = max(2, min(bounds.width, right) - clippedLeft)
        let rect = NSRect(x: clippedLeft, y: bar.minY, width: width, height: bar.height)
        RewindPalette.nsColor(forApp: block.app).setFill()
        rect.fill()
    }

    private func drawBadge(_ placement: (block: ActivityBlock, centreX: CGFloat), in bar: NSRect) {
        let block = placement.block
        let size = Self.badgeSize
        let rect = NSRect(
            x: placement.centreX - size / 2, y: bar.midY - size / 2, width: size, height: size)

        // A ring in the window's own background colour, so the badge reads as sitting *on* the track
        // rather than punched through it, and so a dark icon stays visible over a dark segment.
        let ring = NSBezierPath(ovalIn: rect.insetBy(dx: -1.5, dy: -1.5))
        NSColor.controlBackgroundColor.setFill()
        ring.fill()

        let icon = MainActor.assumeIsolated {
            AppIconCache.shared.icon(appName: block.app)
        }
        if let icon {
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath(ovalIn: rect).addClip()
            Self.drawIcon(icon, in: rect)
            NSGraphicsContext.restoreGraphicsState()
        } else {
            // The monogram fallback, in the app's own track colour so the badge still agrees with
            // its segment.
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
                at: NSPoint(
                    x: rect.midX - textSize.width / 2, y: rect.midY - textSize.height / 2))
        }
    }

    /// One app icon, into a badge, the right way up.
    ///
    /// **`respectFlipped: true`, and the four-argument overload it replaces is the reason every logo
    /// on the timeline was upside down.** `NSImage.draw(in:from:operation:fraction:)` is documented
    /// as behaving like the six-argument form with `respectFlipped: false` — it ignores the flipped
    /// state of the current context and draws in AppKit's bottom-left orientation regardless. This
    /// view is `isFlipped` (the track measures time left-to-right and everything else here top-down),
    /// so the icon came out mirrored about its horizontal axis: Finder's face upside down, Chrome's
    /// ring inverted, Safari's needle pointing the wrong way. It is invisible on the few icons that
    /// happen to be vertically symmetric, which is presumably how it survived.
    ///
    /// **Template images are tinted; full-colour artwork is never touched.** `isTemplate` is the
    /// app's own declaration that its icon is a monochrome stencil meant to take on the surrounding
    /// label colour — a handful of system agents ship one. Drawn as-is that stencil is opaque black,
    /// which disappears into a dark badge ring, so it is composited with `labelColor` and follows the
    /// appearance like every other stencil on the machine. A real icon is full-colour artwork and is
    /// drawn exactly as its author drew it: no tint, no rendering mode, no blend. The distinction is
    /// the image's own flag, never a decision made here — forcing a real icon through the template
    /// path is the other half of the same defect class this method exists to close.
    static func drawIcon(_ icon: NSImage, in rect: NSRect) {
        icon.draw(
            in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true,
            hints: nil)
        guard icon.isTemplate else { return }
        NSColor.labelColor.set()
        rect.fill(using: .sourceAtop)
    }

    /// How an hour label is set.
    ///
    /// **A named seam rather than a literal built inside `draw`, because the colour on this line is
    /// the one thing here a guard has to be able to read.** `InkGlassTests` measures it on the real
    /// glass ground; a dictionary constructed inside the drawing loop would be invisible to any test
    /// and would have to be re-derived by eye. Rebuilt per call on purpose: `NSColor(Ink.secondary)`
    /// is a *dynamic* colour and resolving it at draw time is what lets it follow the appearance the
    /// timeline's glass is pinned to.
    ///
    /// **`Ink.secondary`, and it is not a style preference — `NSColor.tertiaryLabelColor` was
    /// illegible here.** This window is glass (`RewindWindow` hosts `RewindView` on `InkGlassView`),
    /// so these 9 pt labels sit on the panel's ground and not on an opaque sheet. The system's third
    /// label step is black at 0.259, which on the shipped ground measures **1.70:1 over a solid black
    /// desktop** — roughly half of the 3.60:1 that got `Ink.tertiary` banned from glass outright, and
    /// far under WCAG AA's 4.5:1 for text this size. It was invisible *before* the ground moved too
    /// (1.81:1 on the three-rung ground), so this is an old defect the glass change deepened rather
    /// than one it caused. `Ink.secondary` measures **4.54:1 over black and 7.47:1 over white**.
    ///
    /// Spelling it `NSColor(Ink.secondary)` rather than a raw AppKit colour is the point: the ladder
    /// is the app's, `Ink` is where it is defined, and a call site that reaches past it for a system
    /// label colour is exactly how a rung nobody measured got onto a glass surface. See
    /// `Ink.tertiary` for the two-rung rule and `InkGlassTests` for both guards over it.
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
        let first = (trackStart / step).rounded(.up) * step
        var instant = first
        let attributes = Self.hourLabelAttributes
        while instant <= trackStart + trackSpan {
            let tickX = x(for: instant)
            NSColor.separatorColor.setFill()
            NSRect(x: tickX, y: bar.maxY, width: 1, height: 4).fill()

            let label = NSAttributedString(
                string: Self.tickFormatter.string(from: Date(timeIntervalSince1970: instant)),
                attributes: attributes)
            let size = label.size()
            // Only when it fits without colliding with the view's edge.
            if tickX - size.width / 2 >= 0, tickX + size.width / 2 <= bounds.width {
                label.draw(at: NSPoint(x: tickX - size.width / 2, y: bar.maxY + 5))
            }
            instant += step
        }
    }

    /// A tick spacing that yields roughly six to twelve marks at the current zoom, chosen from a
    /// ladder of intervals a person actually thinks in.
    private var tickInterval: Double {
        let candidates: [Double] = [
            60, 300, 600, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600,
        ]
        return candidates.first { trackSpan / $0 <= 12 } ?? 24 * 3600
    }

    private static let tickFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h a"
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
        // `labelColor` inverts with the appearance, which is what a handle over arbitrary segment
        // colours needs — the original drew it as white at 50% and disappears on a light window.
        NSColor.labelColor.setFill()
        path.fill()
        NSColor.controlBackgroundColor.setStroke()
        path.lineWidth = 1
        path.stroke()
    }

    // MARK: - Pointer

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingAreaAdded { removeTrackingArea(trackingAreaAdded) }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .mouseMoved, .activeInKeyWindow],
            owner: self,
            userInfo: nil)
        addTrackingArea(area)
        trackingAreaAdded = area
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        scrub(to: event)
    }

    override func mouseDragged(with event: NSEvent) {
        scrub(to: event)
        showTooltip(for: event)
    }

    /// The drag is over. The playhead is wherever the pointer left it, which is very likely between
    /// two captures, so the model settles it onto one.
    override func mouseUp(with event: NSEvent) {
        onScrubEnd?()
    }

    private func scrub(to event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        onScrub?(instant(atX: point.x))
    }

    /// Scrolling travels through time, which is only meaningful because the axis is time rather than
    /// an array index.
    override func scrollWheel(with event: NSEvent) {
        handleScroll(
            deltaX: event.scrollingDeltaX,
            deltaY: event.scrollingDeltaY,
            isContinuous: event.hasPreciseScrollingDeltas,
            phase: event.phase,
            momentumPhase: event.momentumPhase)
    }

    /// The scroll's arithmetic and its gesture lifecycle, split from `scrollWheel(with:)` for exactly
    /// the reason `handleMagnification` is split from `magnify(with:)`: a scroll `NSEvent` cannot be
    /// constructed outside the window server, so this is the seam a test can drive, and it is the
    /// production path from the first line after the event is unpacked.
    ///
    /// Which way is "back" is the user's own natural-scrolling setting and this view does not try to
    /// second-guess it: the sign follows the platform, so the gesture reads the same here as it does
    /// everywhere else on their Mac. How *far* it goes is the pixels travelled as a fraction of the
    /// track, times the span the track is showing — which is what makes zooming in mean finer control
    /// rather than merely a bigger picture.
    func handleScroll(
        deltaX: CGFloat,
        deltaY: CGFloat,
        isContinuous: Bool,
        phase: NSEvent.Phase,
        momentumPhase: NSEvent.Phase
    ) {
        guard bounds.width > 0 else { return }
        // Horizontal intent wins; a vertical wheel on a horizontal track still pans, because a mouse
        // with no horizontal wheel would otherwise be unable to move at all.
        let travel = abs(deltaX) >= abs(deltaY) ? -deltaX : -deltaY
        // A phase-only event carries no deltas. Passing its zero on would fold a standstill into the
        // smoothed speed at the exact moment that speed is about to be read, cancelling the coast the
        // flick had earned.
        if travel != 0 {
            onTravel?(Double(travel / bounds.width) * trackSpan)
        }

        // **When the gesture is over.** A trackpad says so twice — `.ended` when the fingers lift,
        // and `momentumPhase.ended` when the inertia the system delivers afterwards runs out — and
        // acting on both is correct rather than redundant: the first settle is overtaken a frame
        // later by the momentum events, which cancel it, and the last one is the one that lands. A
        // wheel mouse reports neither phase at all and every notch stands alone, so it settles on the
        // spot.
        let ended =
            phase.contains(.ended) || phase.contains(.cancelled)
            || momentumPhase.contains(.ended) || momentumPhase.contains(.cancelled)
        if !isContinuous || ended {
            onScrubEnd?()
        }
    }

    /// A trackpad pinch zooms the track: how much *time* it spans, not how large anything is drawn.
    ///
    /// It is the same zoom the two magnifier buttons drive — the same bounds, the same anchoring rule,
    /// the same single mutation point on the model — and it is deliberately reached through the same
    /// `RewindZoom.Target`, so a pinch cannot leave the track in a state a button could not.
    ///
    /// AppKit delivers gesture events to the view under the pointer, exactly as it does scroll events,
    /// which is what makes "pinch while you are over the timeline" the literal behaviour rather than
    /// something this has to test for. It is not passed to `super`: forwarding a gesture we have acted
    /// on would let an ancestor act on it a second time.
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
            // Dropped rather than wound down: the next gesture must start from whatever the track
            // ended up showing, so two pinches in a row compose instead of the second replaying the
            // first's accumulated magnification.
            pinch = nil
            return
        }

        // `.began` opens a gesture, and so does a `.changed` that arrives without one. The second case
        // is defensive rather than expected: a gesture that began while the pointer was elsewhere, or
        // over a view that has since gone away, would otherwise deliver events this drops on the floor
        // and the pinch would appear dead until the user lifted their fingers and tried again.
        if phase.contains(.began) || pinch == nil {
            let fraction = min(max(0, Double(x / bounds.width)), 1)
            pinch = RewindPinch(
                anchor: trackStart + fraction * trackSpan,
                fraction: fraction,
                startSpan: trackSpan,
                spanBounds: spanBounds)
        }

        guard var gesture = pinch else { return }
        let target = gesture.advance(by: delta)
        pinch = gesture
        onZoom?(target)
    }

    override func mouseMoved(with event: NSEvent) {
        showTooltip(for: event)
    }

    override func mouseExited(with event: NSEvent) {
        hideTooltip()
    }

    // MARK: - Tooltip

    /// The frame under a point on the track, by the same time-linear mapping the scrub uses — so the
    /// tooltip can never disagree with what a click would select.
    private func frame(atX x: CGFloat) -> RewindFrame? {
        guard let index = frames.nearestIndex(to: instant(atX: x)) else { return nil }
        return frames[index]
    }

    private func showTooltip(for event: NSEvent) {
        guard let window else {
            hideTooltip()
            return
        }
        showTooltip(
            atX: convert(event.locationInWindow, from: nil).x,
            near: window.convertPoint(toScreen: event.locationInWindow),
            in: window)
    }

    /// Whether a tooltip is on screen. Exposed so the teardown rules below are assertable.
    var tooltipIsVisible: Bool { tooltipWindow?.isVisible ?? false }

    /// The tooltip's presentation, split from the event that triggers it for exactly the reason
    /// `handleScroll` and `handleMagnification` are split from theirs: an `NSEvent` carrying a real
    /// screen position cannot be constructed outside the window server, so this is the seam a test
    /// can drive, and it is the production path from the first line after the event is unpacked.
    func showTooltip(atX x: CGFloat, near onScreen: NSPoint, in window: NSWindow) {
        guard let frame = frame(atX: x) else {
            hideTooltip()
            return
        }

        let label = "\(frame.appName)  ·  \(RewindTrackView.tooltipFormatter.string(from: Date(timeIntervalSince1970: frame.capturedAt)))"
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .medium),
            .foregroundColor: NSColor.labelColor,
        ]
        let text = NSAttributedString(string: label, attributes: attributes)
        let padding = NSSize(width: 18, height: 10)
        let size = NSSize(
            width: text.size().width + padding.width, height: text.size().height + padding.height)

        let origin = NSPoint(x: onScreen.x - size.width / 2, y: onScreen.y + 26)

        if let tooltipWindow {
            tooltipWindow.setFrame(NSRect(origin: origin, size: size), display: true)
            (tooltipWindow.contentView as? TooltipContentView)?.update(text)
            return
        }

        let container = TooltipContentView(frame: NSRect(origin: .zero, size: size))
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
        tooltip.contentView = container
        // **A child of the timeline, not a peer of it.** A `.floating` borderless window ordered
        // front on its own outlives whatever put it there: the only two things that take this one
        // down are a mouse-exit and the view leaving its window, and *neither happens when the
        // timeline is simply ordered out* — ⌘W, the red button, or the tutorial's dismiss all leave
        // the pointer sitting over a track that is no longer on screen. The pill then floats over
        // the desktop, above every other application, naming a moment from a window that is gone.
        // AppKit orders a child window out with its parent and brings it back with it, which is the
        // rule this needs and the one it was not getting.
        window.addChildWindow(tooltip, ordered: .above)
        tooltipWindow = tooltip
    }

    private func hideTooltip() {
        guard let tooltip = tooltipWindow else { return }
        tooltip.parent?.removeChildWindow(tooltip)
        tooltip.orderOut(nil)
        tooltipWindow = nil
    }

    override func viewWillMove(toWindow newWindow: NSWindow?) {
        super.viewWillMove(toWindow: newWindow)
        // If this view is removed from its window (e.g. the user navigates away)
        // while a tooltip is showing, mouse-exit never fires, so the borderless
        // floating tooltip window would be orphaned on screen. Tear it down here.
        if newWindow == nil {
            hideTooltip()
            // Same reasoning one step further: a gesture whose `.ended` will never arrive would
            // otherwise still be open the next time this view is installed, and its first event would
            // resume a pinch the user finished in another window.
            pinch = nil
        }
    }

    private static let tooltipFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm:ss a"
        return formatter
    }()

    // MARK: - Accessibility

    /// **The track is a slider, and before this it was nothing at all.**
    ///
    /// A custom `NSView` is not an accessibility element unless it says so, and this one draws
    /// everything it shows — the segments, the badges, the handle — in `draw(_:)`. So VoiceOver saw
    /// an empty rectangle where the window's primary control is: the one thing on screen that says
    /// where in the day you are had no role, no label and no value, and the timeline's position was
    /// not readable by anyone not looking at it.
    ///
    /// `.slider` rather than `.group` because that is what it is — one value along a continuum — and
    /// because the role is what makes VoiceOver offer increment and decrement, which is the whole of
    /// operating it without a pointer. The step is one capture rather than a number of seconds:
    /// seconds would land between two frames at a fine zoom and on the same frame at a coarse one,
    /// where "the next capture" means the same thing at every zoom and always moves the picture.
    override func isAccessibilityElement() -> Bool { true }

    override func accessibilityRole() -> NSAccessibility.Role? { .slider }

    override func accessibilityLabel() -> String? { "Timeline" }

    /// The moment under the playhead, and what owned the screen at it.
    ///
    /// Read off the same `playheadAt` the handle is drawn from and the same frame a click would
    /// select, so what VoiceOver says and what the window shows cannot drift apart. Nil rather than
    /// a placeholder on a day with nothing on it: there is no position to report.
    override func accessibilityValue() -> Any? {
        guard let playheadAt, let index = frames.nearestIndex(to: playheadAt) else { return nil }
        let frame = frames[index]
        let time = Self.tooltipFormatter.string(from: Date(timeIntervalSince1970: frame.capturedAt))
        return "\(frame.appName) at \(time)"
    }

    override func accessibilityPerformIncrement() -> Bool {
        guard onStep != nil else { return false }
        onStep?(1)
        return true
    }

    override func accessibilityPerformDecrement() -> Bool {
        guard onStep != nil else { return false }
        onStep?(-1)
        return true
    }
}

/// The tooltip's own content view. A plain `NSView` drawing a material-backed capsule rather than an
/// `NSHostingView`, so the tooltip window has no SwiftUI in it at all — see the container-view note
/// in `RewindWindow`.
private final class TooltipContentView: NSView {
    private var text = NSAttributedString()

    override var isFlipped: Bool { true }

    func update(_ text: NSAttributedString) {
        self.text = text
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        let shape = NSBezierPath(roundedRect: bounds, xRadius: 7, yRadius: 7)
        NSColor.controlBackgroundColor.setFill()
        shape.fill()
        NSColor.separatorColor.setStroke()
        shape.lineWidth = 1
        shape.stroke()
        let size = text.size()
        text.draw(at: NSPoint(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2))
    }
}

// MARK: - SwiftUI bridge

/// Hosts `RewindTrackView` inside the SwiftUI chrome.
struct RewindTrack: NSViewRepresentable {
    let blocks: [ActivityBlock]
    let frames: [RewindFrame]
    let trackStart: Double
    let trackSpan: Double
    let playheadAt: Double?
    let onScrub: (Double) -> Void
    let onTravel: (Double) -> Void
    /// Defaulted, and therefore omissible, for the one call site that is not the timeline window:
    /// `TimelinePreview` in Settings draws this track over synthetic data with hit testing turned
    /// off, so it has no zoom to bound and no gesture to answer.
    var onScrubEnd: () -> Void = {}
    var spanBounds: ClosedRange<Double> = RewindZoom.minimumSpan...RewindZoom.maximumSpan
    var onZoom: (RewindZoom.Target) -> Void = { _ in }
    /// Defaulted for the same call site as `onZoom`: the Settings preview is synthetic and has no
    /// playhead to step. Nil-defaulting the view's own closure rather than this one is what makes
    /// the preview report itself as an unadjustable slider instead of one that does nothing.
    var onStep: ((Int) -> Void)?

    func makeNSView(context: Context) -> RewindTrackView {
        let view = RewindTrackView()
        view.onScrub = onScrub
        view.onTravel = onTravel
        view.onScrubEnd = onScrubEnd
        view.onZoom = onZoom
        view.onStep = onStep
        return view
    }

    func updateNSView(_ view: RewindTrackView, context: Context) {
        // Reassigned every update: the closures capture the model, and a stale one would scrub a
        // model that is no longer the window's.
        view.onScrub = onScrub
        view.onTravel = onTravel
        view.onScrubEnd = onScrubEnd
        view.onZoom = onZoom
        view.onStep = onStep
        view.apply(
            blocks: blocks,
            frames: frames,
            trackStart: trackStart,
            trackSpan: trackSpan,
            playheadAt: playheadAt,
            spanBounds: spanBounds)
    }
}
