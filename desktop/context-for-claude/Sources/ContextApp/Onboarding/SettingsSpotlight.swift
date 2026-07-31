import AppKit
import SwiftUI

//  Where the overlay is allowed to draw, and the arithmetic that decides it.
//
//  This file is the geometry half of the System Settings choreography; `PermissionChoreography`
//  is the decision half and owns everything about *what* we may claim. Split that way because the
//  two fail differently. A wrong decision points confidently at the wrong control. A wrong
//  conversion points confidently at empty screen — and it does it silently, on somebody else's
//  monitor arrangement, months after the code was written and on a machine the author never had.
//
//  So every conversion in here is a pure function over an explicit list of displays, with no
//  `NSScreen` reachable from it. That is not tidiness: it is the only way the multi-display cases
//  get exercised at all. Nobody has a monitor above their laptop *and* one to the left of it *and*
//  a 1× panel beside a 2× panel wired up while they run the test suite. `ScreenSpaceTests` has all
//  of them.

// MARK: - The two coordinate systems

/// One display, as the two coordinate systems disagree about it.
///
/// `backingScaleFactor` is carried but never multiplied into a position, and that is the point.
/// Accessibility, `CGWindowList` and AppKit all answer in **points**; a 2× display does not have
/// twice the coordinates of a 1× one, it has twice the pixels per coordinate. The classic overlay
/// bug on a mixed-density desk is a scale factor that got into the arithmetic because "Retina" and
/// "coordinates" sound related. `ScreenSpaceTests.testTheConversionIsIndifferentToBackingScale`
/// exists to make that mistake fail immediately rather than on somebody's second monitor.
struct DisplayGeometry: Equatable, Sendable {
    /// The display in AppKit's global space: y **up**, origin at the bottom-left of whichever
    /// display sits at (0, 0).
    var appKitFrame: CGRect
    /// Points to pixels on this display. Used only by `snapped(_:)`, for line widths.
    var backingScaleFactor: CGFloat = 2

    init(appKitFrame: CGRect, backingScaleFactor: CGFloat = 2) {
        self.appKitFrame = appKitFrame
        self.backingScaleFactor = backingScaleFactor
    }

    @MainActor
    init(_ screen: NSScreen) {
        appKitFrame = screen.frame
        backingScaleFactor = screen.backingScaleFactor
    }
}

/// Converts between the coordinate system the Accessibility API answers in and the one `NSWindow`
/// is placed in.
///
/// - **Global CoreGraphics** — what `AXPosition`, `CGWindowListCopyWindowInfo` and `CGEvent` use.
///   Origin at the **top-left** of the primary display, y increasing **downward**.
/// - **Global AppKit** — what `NSScreen.frame` and `NSWindow.setFrame` use. Origin at the
///   **bottom-left** of the primary display, y increasing **upward**.
///
/// The conversion depends on exactly one number: the height of the primary display. It does *not*
/// depend on which display the rect is on, and it is not applied per display — a rect on a monitor
/// stacked above the primary has a **negative** CoreGraphics y, and the single formula below is
/// already right about it. Applying the flip per display, which is the intuitive thing to write, is
/// how an overlay ends up mirrored onto the wrong monitor.
///
/// The primary is the display whose AppKit origin is `(0, 0)` — **not** `NSScreen.screens.first`.
/// They are usually the same object and occasionally are not, and the code this replaced used
/// `screens.first` in two places. On a one-monitor machine that is invisible forever.
struct ScreenSpace: Equatable, Sendable {
    var displays: [DisplayGeometry]

    init(displays: [DisplayGeometry]) {
        self.displays = displays
    }

    @MainActor
    static var live: ScreenSpace {
        ScreenSpace(displays: NSScreen.screens.map(DisplayGeometry.init))
    }

    /// The display everything else is measured from. `nil` only when there are no displays at all,
    /// which is a headless session and a case that has to degrade rather than crash.
    var primary: DisplayGeometry? {
        displays.first { $0.appKitFrame.origin == .zero } ?? displays.first
    }

    // MARK: Conversions

    /// Global CoreGraphics → global AppKit.
    func appKit(from global: CGRect) -> CGRect? {
        guard let primary else { return nil }
        return CGRect(
            x: global.origin.x,
            y: primary.appKitFrame.maxY - global.origin.y - global.height,
            width: global.width,
            height: global.height)
    }

    /// Global AppKit → global CoreGraphics. The exact inverse of `appKit(from:)`; asserted as such,
    /// because a conversion pair that is not an involution is a conversion pair that drifts.
    func global(from appKit: CGRect) -> CGRect? {
        guard let primary else { return nil }
        return CGRect(
            x: appKit.origin.x,
            y: primary.appKitFrame.maxY - appKit.origin.y - appKit.height,
            width: appKit.width,
            height: appKit.height)
    }

    /// A display's own frame in CoreGraphics coordinates. The overlay window covers exactly one of
    /// these, which is what makes every other rect in the overlay a plain translation.
    func globalFrame(of display: DisplayGeometry) -> CGRect? {
        global(from: display.appKitFrame)
    }

    // MARK: Which display

    /// The display that holds most of `global`, or `nil` when the rect is on none of them.
    ///
    /// `nil` is a real answer and the caller must treat it as one: a rect can legitimately be
    /// nowhere — a window dragged mostly off the side, a display unplugged between the lookup and
    /// the draw, a stale frame from an application mid-relayout. Drawing "somewhere near it" is the
    /// mispositioned overlay this whole surface is arranged to avoid, so the honest answer is to
    /// stop pointing.
    func display(holding global: CGRect) -> DisplayGeometry? {
        var best: (display: DisplayGeometry, area: CGFloat)?
        for display in displays {
            guard let frame = globalFrame(of: display) else { continue }
            let overlap = frame.intersection(global)
            guard !overlap.isNull else { continue }
            let area = overlap.width * overlap.height
            guard area > 0 else { continue }
            if best == nil || area > best!.area { best = (display, area) }
        }
        return best?.display
    }

    /// Whether `global` is somewhere a person can actually look. A rect that overlaps no display is
    /// the signal to degrade to words.
    func isOnScreen(_ global: CGRect) -> Bool {
        display(holding: global) != nil
    }

    // MARK: Pixels

    /// Rounds a length to whole device pixels on a display of `scale`.
    ///
    /// The only place the backing scale is allowed to touch anything. A 1 pt hairline on a 2×
    /// display is 2 physical pixels and lands crisply; the same hairline on a 1.5× scaled mode is
    /// 1.5 pixels and lands as a grey smear, which on a dotted boundary reads as a rendering fault
    /// rather than as a deliberate line.
    static func snapped(_ value: CGFloat, to scale: CGFloat) -> CGFloat {
        guard scale > 0 else { return value }
        return (value * scale).rounded() / scale
    }
}

extension CGRect {
    /// The same rect grown around its own centre to at least `width` × `height`.
    ///
    /// Used where a measured **centre** is trustworthy and a measured **size** is not: System
    /// Settings answers 9 × 9 for a **+** button drawn at about 24 × 24, and a 36 × 16 switch is
    /// too slight to glow legibly. Growing around a measured centre can be generous but never
    /// wrong about *where* — which is the only property this overlay is not allowed to get wrong.
    func atLeast(width: CGFloat, height: CGFloat) -> CGRect {
        let w = Swift.max(self.width, width)
        let h = Swift.max(self.height, height)
        return CGRect(x: midX - w / 2, y: midY - h / 2, width: w, height: h)
    }
}

// MARK: - Where the window is, without asking permission

/// System Settings' window and the displays, read from the window server.
///
/// The Accessibility API can answer both of these and is not allowed to during the one step that
/// needs them most: guiding the user to *grant* Accessibility. `CGWindowListCopyWindowInfo` has no
/// such requirement — since macOS 10.15 only `kCGWindowName` is gated behind Screen Recording, and
/// bounds, owner and layer are not — so this keeps working from a completely ungranted first run.
///
/// It is deliberately the *only* thing consulted before the grant lands. Everything else the
/// overlay would like to know about that pane is unknowable at that moment, and inventing it is
/// what a confidently wrong arrow is made of.
enum SettingsWindowProbe {
    static let systemSettingsBundleID = "com.apple.systempreferences"

    /// The largest ordinary window belonging to System Settings, in global CoreGraphics
    /// coordinates. `nil` when it is not running or has no window on screen.
    ///
    /// Largest rather than frontmost: System Settings puts sheets, popovers and its own tooltips in
    /// the same list, and the pane the user is looking at is the big one. Layer 0 excludes the
    /// menu-bar and floating layers outright.
    nonisolated static func windowFrame(bundleID: String = systemSettingsBundleID) -> CGRect? {
        let pids = Set(
            NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
                .map(\.processIdentifier))
        guard !pids.isEmpty else { return nil }
        guard
            let listing = CGWindowListCopyWindowInfo(
                [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else { return nil }

        var best: CGRect?
        for window in listing {
            guard let pid = window[kCGWindowOwnerPID as String] as? pid_t, pids.contains(pid),
                (window[kCGWindowLayer as String] as? Int) == 0,
                let raw = window[kCGWindowBounds as String] as? NSDictionary,
                let bounds = CGRect(dictionaryRepresentation: raw)
            else { continue }
            // A collapsed or zero-size entry is a window the user cannot see; treating one as the
            // pane would put the boundary around a point.
            guard bounds.width > 200, bounds.height > 200 else { continue }
            if best == nil || bounds.width * bounds.height > best!.width * best!.height {
                best = bounds
            }
        }
        return best
    }

    /// The displays, as `ScreenSpace` wants them — from CoreGraphics rather than from `NSScreen`.
    ///
    /// `NSScreen` is main-actor state and the solver runs off the main actor precisely so it stops
    /// blocking it; hopping back for the display list would hand the cost straight back, and
    /// `DispatchQueue.main.sync` from a solver the main actor may be awaiting is a deadlock waiting
    /// for a busy moment. `CGGetActiveDisplayList` is thread-safe and answers the same geometry.
    ///
    /// `CGDisplayBounds` is already in the global CoreGraphics space, so this converts *back* to
    /// AppKit — the one place the flip runs in that direction, and `ScreenSpace` is its inverse.
    nonisolated static func displays() -> [DisplayGeometry] {
        var count: UInt32 = 0
        guard CGGetActiveDisplayList(0, nil, &count) == .success, count > 0 else { return [] }
        var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
        guard CGGetActiveDisplayList(count, &ids, &count) == .success else { return [] }

        // The primary is the display whose CoreGraphics origin is (0, 0); its height is the only
        // number the flip needs.
        let primaryHeight = ids.map(CGDisplayBounds).first { $0.origin == .zero }?.height
            ?? CGDisplayBounds(CGMainDisplayID()).height

        return ids.map { id in
            let cg = CGDisplayBounds(id)
            let mode = CGDisplayCopyDisplayMode(id)
            let scale = mode.map { CGFloat($0.pixelWidth) / CGFloat(max($0.width, 1)) } ?? 2
            return DisplayGeometry(
                appKitFrame: CGRect(
                    x: cg.minX, y: primaryHeight - cg.maxY, width: cg.width, height: cg.height),
                backingScaleFactor: scale)
        }
    }
}

// MARK: - What we found, and what has to happen to it

/// The gesture the user has to perform. There is no `.maybe`: the type is what keeps an arrow from
/// being drawn for an action nobody established.
enum SettingsGesture: Equatable, Sendable {
    /// Press the focused control.
    case click
    /// Drag `source` into the focused control. Both rects were really measured — the arrow is only
    /// ever drawn between two things that were found.
    case drag(source: CGRect)
}

/// Everything the overlay knows about one target in System Settings. Global CoreGraphics
/// coordinates throughout, because that is what the Accessibility API answers in and converting
/// early is how the two systems get mixed.
///
/// `row`, `toggle` and `isOn` are the located row in its original terms and are what the choreography
/// tests assert on. The rest is what the drawing needs and the row alone could never supply: the
/// boundary to outline, the list to drop into, and the one control to glow.
struct SettingsSpotlightTarget: Equatable, Sendable {
    /// The row, label through switch. What the ring used to be drawn around.
    var row: CGRect
    /// The switch on that row.
    var toggle: CGRect
    /// The switch's state, read off the switch.
    var isOn: Bool

    /// The control to act on and glow. The switch for a click on a listed row, the **+** button for
    /// an application that is not listed yet, the list itself for a drag.
    var focus: CGRect
    /// The whole settings area — list, its caption, its **+** and **−** buttons — clipped to what is
    /// actually visible. `nil` when the pane's shape was not one we could measure, in which case no
    /// boundary is drawn rather than a boundary being invented.
    var area: CGRect?
    /// The list the rows live in. `nil` for the same reason.
    var list: CGRect?
    /// Whether this application is in the pane's list at all.
    ///
    /// Not derivable from the rects, and the first cut tried: it compared `focus` to `toggle`, which
    /// are never equal because the switch is grown to a glowable size. The caption then told a user
    /// looking straight at their own row to click **+**. A separate answer to a separate question.
    var isListed: Bool
    /// What the user has to do.
    var gesture: SettingsGesture
    /// System Settings' window at the moment of the lookup.
    ///
    /// The tracker's anchor. Re-walking the accessibility tree costs a thousand-odd synchronous
    /// messages to another application; reading one window's frame costs two. Holding the frame the
    /// solve was taken against is what lets a window *drag* — the common case, and the one where a
    /// stale overlay is most obvious — be followed by translating the last answer instead of asking
    /// for a new one sixty times a second.
    var window: CGRect

    init(
        row: CGRect,
        toggle: CGRect,
        isOn: Bool,
        focus: CGRect? = nil,
        area: CGRect? = nil,
        list: CGRect? = nil,
        isListed: Bool = true,
        gesture: SettingsGesture = .click,
        window: CGRect = .zero
    ) {
        self.row = row
        self.toggle = toggle
        self.isOn = isOn
        self.isListed = isListed
        self.focus = focus ?? toggle
        self.area = area
        self.list = list
        self.gesture = gesture
        self.window = window
    }

    /// The same target, moved by `delta`. Every rect moves together: a window drag translates its
    /// whole contents and nothing inside it moves relative to anything else.
    func translated(by delta: CGVector) -> SettingsSpotlightTarget {
        func move(_ rect: CGRect) -> CGRect { rect.offsetBy(dx: delta.dx, dy: delta.dy) }
        var moved = self
        moved.row = move(row)
        moved.toggle = move(toggle)
        moved.focus = move(focus)
        moved.area = area.map(move)
        moved.list = list.map(move)
        moved.window = move(window)
        if case .drag(let source) = gesture { moved.gesture = .drag(source: move(source)) }
        return moved
    }

    /// Everything the user is meant to look at. What has to be on a display for the overlay to be
    /// worth drawing.
    var hull: CGRect {
        var box = focus.union(area ?? focus)
        if case .drag(let source) = gesture { box = box.union(source) }
        return box
    }
}

// MARK: - The arrow

/// A quadratic Bézier with a head on the end, planned once and drawn at whatever phase the
/// animation is at.
///
/// Pure, and separated from the drawing, because "the arrow points at the thing" is a claim with a
/// wrong answer available and the wrong answer is invisible in code review. `ArrowPlanTests` checks
/// the claim directly: the tip is outside the control it points at and within a fixed gap of its
/// nearest edge, the tail is on screen, and the approach flips sides when the obvious side has no
/// room.
struct ArrowPlan: Equatable, Sendable {
    /// Where the arrow begins.
    var tail: CGPoint
    /// The Bézier's control point. What gives the arrow its bow — a straight line reads as a
    /// divider, a bowed one reads as a gesture.
    var control: CGPoint
    /// The point of the head.
    var tip: CGPoint
    /// The side of the target the head comes in from. Carried so the caption can be put somewhere
    /// the arrow is not.
    var approach: Approach

    enum Approach: Equatable, Sendable {
        case fromLeft, fromRight, fromAbove, fromBelow

        /// The unit vector pointing *away* from the target, in y-down coordinates.
        var outward: CGVector {
            switch self {
            case .fromLeft: return CGVector(dx: -1, dy: 0)
            case .fromRight: return CGVector(dx: 1, dy: 0)
            case .fromAbove: return CGVector(dx: 0, dy: -1)
            case .fromBelow: return CGVector(dx: 0, dy: 1)
            }
        }
    }

    /// How far the tip stops short of the control it points at. Touching it would hide the thing
    /// being pointed at, which is the one thing an arrow may not do.
    static let tipGap: CGFloat = 15
    /// How long the arrow is, measured back from the tip. Long enough to be followed from across a
    /// display, short enough not to cross the whole pane.
    static let reach: CGFloat = 200
    /// How far the curve bows off the straight line, as a fraction of its length.
    static let bow: CGFloat = 0.26

    // MARK: Planning

    /// An arrow that points at `focus` from outside it.
    ///
    /// `keepClearOf` is the settings area: the arrow is laid across the desktop and the rest of the
    /// window rather than across the list, so it never covers a row the user is trying to read.
    /// `bounds` is the display, and the arrow stays inside it — an arrow that runs off the edge is
    /// an arrow whose tail the user never finds.
    ///
    /// All rects y-down, which is both the CoreGraphics convention the target arrives in and the
    /// SwiftUI convention it is drawn in, so nothing is flipped anywhere in this type.
    static func pointing(at focus: CGRect, keepClearOf area: CGRect?, within bounds: CGRect) -> ArrowPlan {
        let approach = bestApproach(for: focus, avoiding: area, within: bounds)
        let outward = approach.outward
        let tip = CGPoint(
            x: focus.midX + outward.dx * (focus.width / 2 + tipGap),
            y: focus.midY + outward.dy * (focus.height / 2 + tipGap))

        // Back off along the approach, then clamp into the display. Clamping can shorten the arrow
        // but never turns it around: the tail stays on the outward side of the tip.
        let raw = CGPoint(x: tip.x + outward.dx * reach, y: tip.y + outward.dy * reach)
        let inset = bounds.insetBy(dx: 24, dy: 24)
        let tail = CGPoint(
            x: min(max(raw.x, inset.minX), inset.maxX),
            y: min(max(raw.y, inset.minY), inset.maxY))

        return ArrowPlan(tail: tail, control: bowedControl(from: tail, to: tip), tip: tip, approach: approach)
    }

    /// An arrow from one measured rect into another: the drag.
    ///
    /// The tip lands **inside** the destination, because that is where the thing has to end up. A
    /// drag arrow that stops short of its target is describing a different gesture.
    static func dragging(from source: CGRect, to destination: CGRect) -> ArrowPlan {
        let tail = CGPoint(x: source.midX, y: source.midY)
        // Aimed at the destination's near edge rather than its middle: for a tall list, the middle
        // is a long way from the row the user is dragging past and reads as pointing at nothing in
        // particular.
        let entry = source.midY > destination.midY ? destination.maxY - 26 : destination.minY + 26
        let tip = CGPoint(x: destination.midX, y: min(max(entry, destination.minY), destination.maxY))
        let approach: Approach = tail.y > tip.y ? .fromBelow : .fromAbove
        return ArrowPlan(tail: tail, control: bowedControl(from: tail, to: tip), tip: tip, approach: approach)
    }

    /// Which side of `focus` the arrow can come in from.
    ///
    /// Preference order is right, left, below, above — the switch in every Privacy pane sits at the
    /// right-hand end of its row, with the rest of the display beyond it, so "from the right" is the
    /// answer nearly always and the rest are what keep the nearly honest.
    private static func bestApproach(for focus: CGRect, avoiding area: CGRect?, within bounds: CGRect) -> Approach {
        let candidates: [(Approach, CGFloat)] = [
            (.fromRight, bounds.maxX - focus.maxX),
            (.fromLeft, focus.minX - bounds.minX),
            (.fromBelow, bounds.maxY - focus.maxY),
            (.fromAbove, focus.minY - bounds.minY),
        ]
        let needed = tipGap + reach * 0.55
        // A side that clears the settings area outright is preferred, however tight, over one that
        // has room but lays the arrow across the list.
        if let clear = candidates.first(where: { room($0.0, focus: focus, area: area) && $0.1 >= needed }) {
            return clear.0
        }
        if let roomy = candidates.first(where: { $0.1 >= needed }) { return roomy.0 }
        return candidates.max(by: { $0.1 < $1.1 })?.0 ?? .fromRight
    }

    /// Whether approaching from this side keeps the arrow off the settings area.
    private static func room(_ approach: Approach, focus: CGRect, area: CGRect?) -> Bool {
        guard let area else { return true }
        switch approach {
        case .fromRight: return focus.maxX >= area.maxX - 1
        case .fromLeft: return focus.minX <= area.minX + 1
        case .fromBelow: return focus.maxY >= area.maxY - 1
        case .fromAbove: return focus.minY <= area.minY + 1
        }
    }

    private static func bowedControl(from tail: CGPoint, to tip: CGPoint) -> CGPoint {
        let mid = CGPoint(x: (tail.x + tip.x) / 2, y: (tail.y + tip.y) / 2)
        let span = CGVector(dx: tip.x - tail.x, dy: tip.y - tail.y)
        let length = max(hypot(span.dx, span.dy), 1)
        // Perpendicular, consistently to one side so repeated draws never flip the curve.
        let normal = CGVector(dx: -span.dy / length, dy: span.dx / length)
        let offset = length * bow
        return CGPoint(x: mid.x + normal.dx * offset, y: mid.y + normal.dy * offset)
    }

    // MARK: Reading the curve

    /// The point at `t` along the curve, `t` in 0…1.
    func point(at t: CGFloat) -> CGPoint {
        let u = 1 - t
        return CGPoint(
            x: u * u * tail.x + 2 * u * t * control.x + t * t * tip.x,
            y: u * u * tail.y + 2 * u * t * control.y + t * t * tip.y)
    }

    /// The direction of travel at `t`, in radians. The head is rotated by this so it always faces
    /// where the curve is going rather than where the target happens to be.
    func heading(at t: CGFloat) -> CGFloat {
        let u = 1 - t
        let dx = 2 * u * (control.x - tail.x) + 2 * t * (tip.x - control.x)
        let dy = 2 * u * (control.y - tail.y) + 2 * t * (tip.y - control.y)
        if dx == 0 && dy == 0 { return 0 }
        return atan2(dy, dx)
    }

    /// The whole curve as a path, for stroking.
    var path: Path {
        var path = Path()
        path.move(to: tail)
        path.addQuadCurve(to: tip, control: control)
        return path
    }
}

// MARK: - The scene

/// Everything the overlay draws, in the overlay window's own coordinates: y **down**, origin at the
/// window's top-left, which is also the display's top-left. The window covers exactly one display,
/// so getting here from global CoreGraphics coordinates is a translation and nothing else — no
/// flip, no per-display origin, no scale. That is the whole reason the window is display-sized.
struct SettingsSpotlightScene: Equatable, Sendable {
    /// The display, in local coordinates: always `(0, 0, w, h)`.
    var bounds: CGRect
    /// The part of `bounds` no permanent system chrome sits in — `NSScreen.visibleFrame`, which is
    /// the display less the menu bar and less the Dock wherever the user keeps it.
    ///
    /// `nil` when nobody measured it, and `usableBounds` then falls back to the whole display. Only
    /// the words-alone tier consults it: every other tier is anchored to something it measured in
    /// System Settings, and this is the one that has nothing to anchor to.
    var visibleBounds: CGRect?
    /// The dotted boundary. `nil` when nothing at all could be measured, which never happens in
    /// practice — a scene exists because something was.
    var area: CGRect?
    /// The glowing control. `nil` when we know where the window is and nothing about its contents:
    /// the boundary is still drawn, and nothing claims to know which control to press.
    var focus: CGRect?
    /// What the user is dragging, when they are dragging.
    var source: CGRect?
    /// `nil` for the same reason as `focus`. **An arrow is only ever drawn when there is a measured
    /// control at the end of it** — that invariant is this type's whole job.
    var arrow: ArrowPlan?
    /// The sentence. Beside the arrow when there is one, over the boundary when there is not.
    var caption: String
    /// Rects the dimming scrim must not cover — our own windows, so the card that is talking the
    /// user through this does not get dimmed by its own overlay.
    var exclusions: [CGRect] = []
    /// Points to pixels on the display this lands on, for snapping line widths.
    var backingScaleFactor: CGFloat = 2
    /// The grant landed. The arrow and its token go — an arrow still pointing at a switch the user
    /// has already flipped is asking for something that is done — and what is left is the boundary,
    /// a steady glow and a tick.
    var confirmed: Bool = false

    /// Builds the scene for a target that has already been established to be on `display`.
    ///
    /// Returns `nil` when the target is not on that display after all — the last check before
    /// anything is drawn, and the one that turns a stale frame into a sentence instead of into an
    /// arrow over the desktop.
    static func make(
        target: SettingsSpotlightTarget,
        caption: String,
        display: DisplayGeometry,
        space: ScreenSpace,
        exclusions: [CGRect] = []
    ) -> SettingsSpotlightScene? {
        guard let displayGlobal = space.globalFrame(of: display) else { return nil }
        guard displayGlobal.intersects(target.focus) else { return nil }

        func local(_ rect: CGRect) -> CGRect {
            rect.offsetBy(dx: -displayGlobal.minX, dy: -displayGlobal.minY)
        }
        let bounds = CGRect(origin: .zero, size: displayGlobal.size)
        let focus = local(target.focus)
        // The boundary is clipped to the display as well as to the window: a settings area that
        // runs past the bottom of the screen would otherwise be outlined across the dock.
        let area = target.area.map(local).map { $0.intersection(bounds) }.flatMap { $0.isNull ? nil : $0 }

        let arrow: ArrowPlan
        var source: CGRect?
        switch target.gesture {
        case .click:
            arrow = .pointing(at: focus, keepClearOf: area, within: bounds)
        case .drag(let from):
            let localSource = local(from)
            source = localSource
            arrow = .dragging(from: localSource, to: focus)
        }

        return SettingsSpotlightScene(
            bounds: bounds,
            area: area,
            focus: focus,
            source: source,
            arrow: arrow,
            caption: caption,
            exclusions: exclusions.map(local),
            backingScaleFactor: display.backingScaleFactor)
    }

    /// The scene for a window we can see and cannot read into: a boundary and a sentence, no glow
    /// and no arrow.
    static func make(
        framing frame: SettingsWindowFrame,
        display: DisplayGeometry,
        space: ScreenSpace,
        exclusions: [CGRect] = []
    ) -> SettingsSpotlightScene? {
        guard let displayGlobal = space.globalFrame(of: display) else { return nil }
        guard displayGlobal.intersects(frame.window) else { return nil }
        func local(_ rect: CGRect) -> CGRect {
            rect.offsetBy(dx: -displayGlobal.minX, dy: -displayGlobal.minY)
        }
        let bounds = CGRect(origin: .zero, size: displayGlobal.size)
        let area = local(frame.window).intersection(bounds)
        guard !area.isNull else { return nil }
        return SettingsSpotlightScene(
            bounds: bounds,
            area: area,
            focus: nil,
            source: nil,
            arrow: nil,
            caption: frame.instruction,
            exclusions: exclusions.map(local),
            backingScaleFactor: display.backingScaleFactor)
    }

    /// Where the caption's plate is pinned. The arrow's tail when there is an arrow — the sentence
    /// belongs to the gesture — and the top of the boundary when there is not.
    /// Where the caption's plate goes, and which way it hangs off that point.
    enum CaptionPlacement: Equatable, Sendable {
        /// Above the point, falling below it when there is no room.
        case above(CGPoint)
        /// Centred vertically, clear of the boundary on that side. What the boundary-only case uses:
        /// a plate laid over System Settings' own header would be our sentence covering theirs.
        case rightOf(CGPoint)
        case leftOf(CGPoint)
    }

    /// What the plate is allowed to use when it has nothing else to go on: the measured usable area,
    /// or the whole display when nothing measured it.
    var usableBounds: CGRect {
        guard let visibleBounds else { return bounds }
        let inside = visibleBounds.intersection(bounds)
        return inside.isNull || inside.isEmpty ? bounds : inside
    }

    var captionPlacement: CaptionPlacement {
        if let arrow, !confirmed { return .above(arrow.tail) }
        guard let area else {
            // **Words alone: nothing was located, so nothing may be pointed at.** The plate is
            // anchored to the only rect this tier actually has — the display's usable area, menu bar
            // and Dock measured out of it — and pinned to the foot of it.
            //
            // The foot, and not the top, because of what the two bands are. This sentence is shown
            // *because* System Settings could not be found, so the plate has to sit where it is
            // least likely to cover the pane the user is being told to read — and the top band of a
            // display is exactly where window title bars and pane headers live, macOS having placed
            // them there. A plate pinned there both hides the header it lands on and reads as a
            // label on it, which is the one thing this tier exists to avoid.
            //
            // It replaces `minY + 140`, which was neither: 140 pt is a fixed distance into a
            // display of unknown height, and it put the plate squarely over the pane's own header.
            let usable = usableBounds
            return .above(CGPoint(x: usable.midX, y: usable.maxY))
        }
        // A boundary with nothing aimed at it. The plate goes beside the region when the display has
        // room, so it does not cover the pane it is talking about.
        let gap: CGFloat = 26
        if bounds.maxX - area.maxX > 360 { return .rightOf(CGPoint(x: area.maxX + gap, y: area.midY)) }
        if area.minX - bounds.minX > 360 { return .leftOf(CGPoint(x: area.minX - gap, y: area.midY)) }
        return .above(CGPoint(x: area.midX, y: area.minY))
    }
}

// MARK: - Drawing

/// The overlay's pixels, as a pure function of the scene and a 0…1 animation phase.
///
/// A `Canvas` and not a stack of layers or a tree of shapes, for two reasons. It is one draw call
/// over a display-sized transparent window, which is what makes a 30 Hz phase affordable while the
/// user is working in another application. And it is renderable: `ImageRenderer` over this exact
/// view is how the boundary, the glow and the arrow were checked at a dozen phases without a live
/// System Settings in front of them, which is the only way to iterate on something that otherwise
/// only exists for four seconds in the middle of somebody's first run.
///
/// **Never coloured.** Every stroke here is white over a dark halo. The window it lands on belongs
/// to System Settings, whose background is light or dark depending on a setting we do not control
/// and cannot read reliably, so a single colour would be invisible half the time — hence the halo
/// under every white line rather than a colour chosen to contrast with a guess. The accent is
/// deliberately not used: it is whatever the user picked in Appearance, and this app never draws
/// purple.
struct SettingsSpotlightCanvas: View {
    var scene: SettingsSpotlightScene
    /// 0…1, wrapping. Drives the marching dashes, the glow's breath and the token that runs along
    /// the arrow. Frozen by the caller under Reduce Motion.
    var phase: Double

    /// The phase a still frame is shown at: dashes at rest and the token arrived at the tip, which
    /// is the frame the motion existed to arrive at.
    static let stillPhase: Double = 0.999

    var body: some View {
        Canvas(rendersAsynchronously: false) { context, size in
            let bounds = CGRect(origin: .zero, size: size)
            drawScrim(in: &context, bounds: bounds)
            drawBoundary(in: &context)
            drawSource(in: &context)
            drawFocusGlow(in: &context)
            drawArrow(in: &context)
            drawCaption(in: &context, bounds: bounds)
        }
        .allowsHitTesting(false)
    }

    // MARK: Pieces

    /// How far outside the settings area the dotted boundary is drawn, and how far outside it the
    /// scrim's hole stops.
    ///
    /// The order matters and is the difference between a boundary you can see and one you cannot.
    /// The hole stops **inside** the boundary, so the dotted line lands on the dimmed side of the
    /// edge rather than on System Settings' own background. A white line on a light window is
    /// invisible whatever you do to it; a white line on the dimming is unmissable, and precision is
    /// read at that edge — a point of misalignment on a dimmed border is glaringly obvious, which is
    /// exactly why it is trustworthy when it is right.
    private static let holeInset: CGFloat = 4
    private static let boundaryInset: CGFloat = 11

    /// A wash over everything except the settings area, the thing being dragged and our own windows.
    private func drawScrim(in context: inout GraphicsContext, bounds: CGRect) {
        // Nothing measured means nothing to spotlight, and dimming a whole display to say so would
        // be an overlay shouting about its own failure.
        guard scene.area != nil else { return }
        var wash = Path(bounds)
        for hole in holes() {
            wash.addPath(
                Path(
                    roundedRect: hole.insetBy(dx: -Self.holeInset, dy: -Self.holeInset),
                    cornerRadius: 10))
        }
        context.fill(wash, with: .color(.black.opacity(0.34)), style: FillStyle(eoFill: true))
    }

    private func holes() -> [CGRect] {
        var holes: [CGRect] = []
        if let area = scene.area { holes.append(area) }
        if let source = scene.source { holes.append(source) }
        holes.append(contentsOf: scene.exclusions)
        return holes
    }

    /// The white dotted boundary around the whole settings area.
    ///
    /// The dashes march toward the target rather than sitting still, which is what makes an outline
    /// read as "this region" instead of as a decoration somebody left on the screen.
    private func drawBoundary(in context: inout GraphicsContext) {
        guard let area = scene.area else { return }
        let line = ScreenSpace.snapped(3, to: scene.backingScaleFactor)
        let path = Path(
            roundedRect: area.insetBy(dx: -Self.boundaryInset, dy: -Self.boundaryInset),
            cornerRadius: 14)
        let period: CGFloat = 16  // one dash plus one gap
        // Solid once the grant lands: the dashes were saying "look here", and the looking is done.
        let style =
            scene.confirmed
            ? StrokeStyle(lineWidth: line, lineCap: .round)
            : StrokeStyle(
                lineWidth: line, lineCap: .round, dash: [9, 7], dashPhase: -CGFloat(phase) * period)

        // A dark ribbon, laid **continuously** under the dashes rather than dash-for-dash.
        //
        // This is what makes a white boundary white. System Settings' window is light or dark
        // depending on a setting we cannot read, and a white line on a light window disappears
        // however wide you make it. Haloing each dash individually does not fix it either — the halo
        // is wider than a 9 pt dash, so the two merge and the boundary reads as a row of grey blobs,
        // which is exactly how the first cut of this looked. A continuous dark band gives every dash
        // the same dark background, whatever is underneath.
        var ribbon = context
        ribbon.addFilter(.blur(radius: 5))
        ribbon.stroke(
            path, with: .color(.black.opacity(0.5)),
            style: StrokeStyle(lineWidth: line + 13, lineCap: .round))

        // A soft white bloom over it, so the region has a presence at the edge of vision. White,
        // never a hue.
        var bloom = context
        bloom.addFilter(.blur(radius: 8))
        bloom.stroke(path, with: .color(.white.opacity(0.4)), style: StrokeStyle(lineWidth: line + 7))

        context.stroke(path, with: .color(.white), style: style)
    }

    /// The thing being dragged, outlined so "what" is as clear as "where".
    private func drawSource(in context: inout GraphicsContext) {
        guard let source = scene.source else { return }
        // Outside the scrim's hole, for the same reason the boundary is: on the dimming, where white
        // is legible.
        let path = Path(
            roundedRect: source.insetBy(dx: -Self.boundaryInset + 2, dy: -Self.boundaryInset + 2),
            cornerRadius: 10)
        var bloom = context
        bloom.addFilter(.blur(radius: 7))
        bloom.stroke(path, with: .color(.white.opacity(0.4)), style: StrokeStyle(lineWidth: 9))
        context.stroke(path, with: .color(.black.opacity(0.55)), style: StrokeStyle(lineWidth: 5))
        context.stroke(path, with: .color(.white), style: StrokeStyle(lineWidth: 2.5))
    }

    /// The glow around the one control that has to be acted on.
    ///
    /// Four passes, and every one is doing something the others cannot. A wide white bloom that
    /// breathes, so the eye finds it from across a display. A ring that **expands outward and
    /// fades**, which is what makes a highlight read as *pointing at this* rather than as a box
    /// somebody drew. A dark rim, because the control it surrounds sits on a background whose
    /// lightness we do not control. And a crisp white ring, because precision is the point — a soft
    /// glow alone leaves the user guessing at the edge of what they are meant to hit.
    private func drawFocusGlow(in context: inout GraphicsContext) {
        guard let focus = scene.focus else { return }
        let breath = scene.confirmed ? 1 : 0.5 + 0.5 * sin(phase * 2 * .pi)
        let ring = Path(roundedRect: focus.insetBy(dx: -8, dy: -8), cornerRadius: 11)

        // The same dark ribbon the boundary gets, and for the same reason: the switch sits on a row
        // whose lightness is not ours to know.
        var ribbon = context
        ribbon.addFilter(.blur(radius: 5))
        ribbon.stroke(ring, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 16))

        var bloom = context
        bloom.addFilter(.blur(radius: 16 + 6 * breath))
        bloom.stroke(
            ring, with: .color(.white.opacity(0.65 + 0.3 * breath)), style: StrokeStyle(lineWidth: 16))

        if !scene.confirmed {
            // The expanding ring. One pass of it per animation cycle, growing 26 pt and fading out.
            let grow = CGFloat(phase)
            let expanded = Path(
                roundedRect: focus.insetBy(dx: -8 - 26 * grow, dy: -8 - 26 * grow),
                cornerRadius: 11 + 26 * grow)
            context.stroke(
                expanded, with: .color(.white.opacity(0.55 * (1 - grow))),
                style: StrokeStyle(lineWidth: 3))
        }

        context.fill(ring, with: .color(.white.opacity(0.12 + 0.1 * breath)))
        context.stroke(ring, with: .color(.black.opacity(0.55)), style: StrokeStyle(lineWidth: 6))
        context.stroke(
            ring, with: .color(.white),
            style: StrokeStyle(lineWidth: ScreenSpace.snapped(3, to: scene.backingScaleFactor)))

        if scene.confirmed { drawTick(in: &context, on: focus) }
    }

    /// A tick over the control, once the grant lands. Drawn rather than an SF Symbol so it is the
    /// same white and the same weight as everything else here.
    private func drawTick(in context: inout GraphicsContext, on focus: CGRect) {
        let size = min(max(min(focus.width, focus.height) * 0.7, 16), 26)
        let centre = CGPoint(x: focus.midX, y: focus.midY)
        var tick = Path()
        tick.move(to: CGPoint(x: centre.x - size * 0.36, y: centre.y + size * 0.02))
        tick.addLine(to: CGPoint(x: centre.x - size * 0.08, y: centre.y + size * 0.28))
        tick.addLine(to: CGPoint(x: centre.x + size * 0.38, y: centre.y - size * 0.28))
        context.stroke(
            tick, with: .color(.black.opacity(0.55)),
            style: StrokeStyle(lineWidth: 7, lineCap: .round, lineJoin: .round))
        context.stroke(
            tick, with: .color(.white),
            style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
    }

    /// The arrow: a bowed shaft, a solid head, and a token that runs the length of it.
    ///
    /// The token is what makes a drag legible. A static arrow between two boxes says the two are
    /// related; something travelling from one to the other says *move this there*, which is the
    /// whole instruction.
    private func drawArrow(in context: inout GraphicsContext) {
        // An arrow still pointing at a switch the user has already flipped is asking for something
        // that is done.
        guard !scene.confirmed, let arrow = scene.arrow else { return }
        let shaft = arrow.path

        context.stroke(
            shaft, with: .color(.black.opacity(0.5)),
            style: StrokeStyle(lineWidth: 8, lineCap: .round))
        context.stroke(
            shaft, with: .color(.white.opacity(0.95)),
            style: StrokeStyle(lineWidth: 4, lineCap: .round))

        // The head is stroked dark first so the white fill keeps a rim on a light window; a stroke
        // rather than a second larger fill, which would lengthen the tip and move where it points.
        let head = headPath(at: arrow.tip, heading: arrow.heading(at: 1))
        context.stroke(
            head, with: .color(.black.opacity(0.5)),
            style: StrokeStyle(lineWidth: 4, lineJoin: .round))
        context.fill(head, with: .color(.white))

        drawToken(in: &context, arrow: arrow)
    }

    /// The travelling token. Fades in off the tail and out at the tip so the loop has no seam.
    private func drawToken(in context: inout GraphicsContext, arrow: ArrowPlan) {
        let t = CGFloat(phase)
        let opacity = min(1, min(t / 0.18, (1 - t) / 0.18))
        guard opacity > 0.02 else { return }
        let at = arrow.point(at: t)
        let dot = CGRect(x: at.x - 7, y: at.y - 7, width: 14, height: 14)

        var bloom = context
        bloom.addFilter(.blur(radius: 9))
        bloom.fill(Path(ellipseIn: dot.insetBy(dx: -5, dy: -5)), with: .color(.white.opacity(0.6 * opacity)))
        context.fill(Path(ellipseIn: dot), with: .color(.white.opacity(0.95 * opacity)))
    }

    private func headPath(at tip: CGPoint, heading: CGFloat) -> Path {
        let length: CGFloat = 26
        let half: CGFloat = 13
        var path = Path()
        path.move(to: .zero)
        path.addLine(to: CGPoint(x: -length, y: -half))
        path.addLine(to: CGPoint(x: -length * 0.68, y: 0))
        path.addLine(to: CGPoint(x: -length, y: half))
        path.closeSubpath()
        return path.applying(
            CGAffineTransform(rotationAngle: heading).concatenating(
                CGAffineTransform(translationX: tip.x, y: tip.y)))
    }

    /// The sentence. Placed at the arrow's tail, on the side the arrow came from, so it reads as
    /// the label on the gesture rather than as a caption on the pane.
    private func drawCaption(in context: inout GraphicsContext, bounds: CGRect) {
        guard !scene.caption.isEmpty else { return }
        var text = context.resolve(
            Text(scene.caption)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white))
        text.shading = .color(.white)
        let measured = text.measure(in: CGSize(width: 320, height: 200))

        let padding = CGSize(width: 16, height: 11)
        let size = CGSize(width: measured.width + padding.width * 2, height: measured.height + padding.height * 2)
        var origin: CGPoint
        var anchorY: CGFloat
        switch scene.captionPlacement {
        case .above(let anchor):
            anchorY = anchor.y
            origin = CGPoint(x: anchor.x - size.width / 2, y: anchor.y - size.height - 20)
            // Below the anchor when there is no room above it.
            if origin.y < bounds.minY + 12 { origin.y = anchor.y + 20 }
        case .rightOf(let anchor):
            anchorY = anchor.y
            origin = CGPoint(x: anchor.x, y: anchor.y - size.height / 2)
        case .leftOf(let anchor):
            anchorY = anchor.y
            origin = CGPoint(x: anchor.x - size.width, y: anchor.y - size.height / 2)
        }
        // Clamped last, so the plate is always whole and always on the display.
        origin.x = min(max(origin.x, bounds.minX + 12), bounds.maxX - size.width - 12)
        origin.y = min(max(origin.y, bounds.minY + 12), bounds.maxY - size.height - 12)

        // Never over the thing it is describing. A plate covering the row it says to drag is the
        // instruction hiding its own subject, and the drag tail sits *on* that row by construction.
        var plate = CGRect(origin: origin, size: size)
        for obstacle in [scene.source, scene.focus].compactMap({ $0 }) {
            guard plate.intersects(obstacle.insetBy(dx: -10, dy: -10)) else { continue }
            let above = obstacle.minY - size.height - 22
            let below = obstacle.maxY + 22
            plate.origin.y =
                above >= bounds.minY + 12 && anchorY <= obstacle.midY
                ? above : min(below, bounds.maxY - size.height - 12)
        }
        context.fill(Path(roundedRect: plate, cornerRadius: 11), with: .color(.black.opacity(0.82)))
        context.stroke(
            Path(roundedRect: plate, cornerRadius: 11), with: .color(.white.opacity(0.28)),
            style: StrokeStyle(lineWidth: 1))
        context.draw(
            text,
            in: CGRect(
                x: plate.minX + padding.width, y: plate.minY + padding.height,
                width: measured.width, height: measured.height))
    }

    private func haloed(_ style: StrokeStyle, by extra: CGFloat) -> StrokeStyle {
        StrokeStyle(
            lineWidth: style.lineWidth + extra, lineCap: style.lineCap, dash: style.dash,
            dashPhase: style.dashPhase)
    }
}

/// The canvas with a clock attached. Split so the drawing above stays a pure function of `phase`
/// and can be rendered at any phase from a test.
struct SettingsSpotlightView: View {
    var scene: SettingsSpotlightScene
    /// One full trip of the token along the arrow.
    static let period: Double = 2.1

    var body: some View {
        if InkReduceMotion.isEnabled {
            // Reduce Motion gets the still frame the motion was heading for: the token at the tip,
            // the dashes at rest. The instruction is unchanged; only the travelling is gone.
            SettingsSpotlightCanvas(scene: scene, phase: SettingsSpotlightCanvas.stillPhase)
        } else {
            TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { context in
                SettingsSpotlightCanvas(
                    scene: scene,
                    phase: context.date.timeIntervalSinceReferenceDate
                        .truncatingRemainder(dividingBy: Self.period) / Self.period)
            }
        }
    }
}

// MARK: - The window

/// The borderless, click-through window the overlay lives in.
///
/// Sized to a whole display rather than to the thing being pointed at, which is the change that
/// makes the rest of this file simple: the window's frame is a display's `NSScreen.frame` verbatim,
/// so it needs no coordinate conversion at all, and everything drawn inside it is the target
/// translated by the display's origin. The overlay this replaced resized its window to the row on
/// every tick and flipped coordinates each time — two chances per tick to be wrong, on a path with
/// no test covering it.
///
/// `ignoresMouseEvents` is not an optimisation. The overlay covers an entire display including the
/// switch it is pointing at, and a window that swallowed clicks would block the exact interaction it
/// exists to teach.
@MainActor
enum SpotlightWindow {
    static func make(covering display: DisplayGeometry) -> NSPanel {
        let panel = SpotlightPanel(
            contentRect: display.appKitFrame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false)
        configure(panel)
        return panel
    }

    /// The settings that make a window an overlay. Applied in one place so `SpotlightWindowTests`
    /// can assert them on a real window rather than on a description of one.
    ///
    /// Every line here is load-bearing:
    ///
    /// - `ignoresMouseEvents` — the overlay covers a whole display *including the switch it points
    ///   at*. Without this it would swallow the exact click it exists to teach.
    /// - `nonactivatingPanel` plus `canBecomeKey == false` — if the overlay took key status,
    ///   System Settings would lose it, the switch being pointed at would stop looking focused, and
    ///   on some panes the list resets.
    /// - `statusWindow` level rather than `.floating` — `.floating` sits below other applications'
    ///   floating panels, and an overlay that is behind the thing it describes is worse than none.
    ///   One below `MenuBarSpotlight`, which has to stay on top of this.
    /// - `sharingType = .none` — this app records the screen. Its own guidance chrome must not end
    ///   up in the user's screen history. `CONTEXT_SPOTLIGHT_CAPTURABLE=1` lifts it for the one
    ///   case that needs to see the overlay in a screenshot: verifying the overlay.
    /// - `animationBehavior = .none` — AppKit's default fade on a repositioned window turns a
    ///   tracked move into a smear.
    static func configure(_ window: NSWindow) {
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.statusWindow)))
        window.ignoresMouseEvents = true
        window.isMovableByWindowBackground = false
        window.animationBehavior = .none
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        window.hidesOnDeactivate = false
        window.sharingType = isCapturable ? .readOnly : .none
    }

    /// Whether the overlay may appear in a screen capture. Off in production.
    static var isCapturable: Bool {
        ProcessInfo.processInfo.environment["CONTEXT_SPOTLIGHT_CAPTURABLE"] == "1"
    }
}

/// A panel that can never become key or main.
///
/// `canBecomeKeyWindow` is overridden rather than left to `styleMask`, because a borderless window's
/// default answer has changed between releases and this one must never be in doubt: taking key
/// status away from System Settings mid-instruction is the overlay breaking the thing it is
/// explaining.
final class SpotlightPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}
