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
    nonisolated static func windowFrame(bundleID: String = systemSettingsBundleID) -> CGRect? {
        window(bundleID: bundleID)?.frame
    }

    /// The same window, with the identifier the window server knows it by.
    ///
    /// Split out from `windowFrame` rather than duplicated because the two answers must be the same
    /// window: `SettingsPaneReader` captures the pixels of `id` and then measures normalised text
    /// boxes against `frame`, and a pass that photographed one window and did the arithmetic against
    /// another would put a confident arrow a whole window's width away from the row.
    ///
    /// Largest rather than frontmost: System Settings puts sheets, popovers and its own tooltips in
    /// the same list, and the pane the user is looking at is the big one. Layer 0 excludes the
    /// menu-bar and floating layers outright.
    nonisolated static func window(bundleID: String = systemSettingsBundleID) -> (id: CGWindowID, frame: CGRect)? {
        let pids = Set(
            NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
                .map(\.processIdentifier))
        guard !pids.isEmpty else { return nil }
        guard
            let listing = CGWindowListCopyWindowInfo(
                [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else { return nil }

        var best: (id: CGWindowID, frame: CGRect)?
        for window in listing {
            guard let pid = window[kCGWindowOwnerPID as String] as? pid_t, pids.contains(pid),
                (window[kCGWindowLayer as String] as? Int) == 0,
                let number = window[kCGWindowNumber as String] as? CGWindowID,
                let raw = window[kCGWindowBounds as String] as? NSDictionary,
                let bounds = CGRect(dictionaryRepresentation: raw)
            else { continue }
            // A collapsed or zero-size entry is a window the user cannot see; treating one as the
            // pane would put the boundary around a point.
            guard bounds.width > 200, bounds.height > 200 else { continue }
            if best == nil || bounds.width * bounds.height > best!.frame.width * best!.frame.height {
                best = (number, bounds)
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

// MARK: - The hand

/// A hand performing the drag: where it is, how closed it is, and whether it is carrying anything —
/// as a pure function of a 0…1 phase.
///
/// **This is the instruction, not an ornament.** A dashed box around a row and a second one around a
/// list says the two are related; an arrow between them says *this goes there*; only something that
/// closes on the row, moves it, and lets go says **drag**. macOS 26's own affordance is a gesture the
/// user has never performed in a Privacy pane before, and the failure mode is not "they cannot find
/// the row" — it is "they click the row and nothing happens". Demonstrating the gesture is the only
/// form of guidance that answers that.
///
/// Pure and separate from the drawing for the same reason `ArrowPlan` is: the claims worth making
/// about it — that it starts on the row, that it is closed for the whole of the carry, that it
/// arrives inside the list, that the loop has no visible seam — are claims about *this*, and can be
/// asserted at every phase without rendering anything.
struct DragHandPlan: Equatable, Sendable {
    /// The grab point: where the fingers meet. On the source row at the start, inside the
    /// destination at the end, on the arrow's own curve in between — so the hand and the arrow can
    /// never disagree about the path.
    var position: CGPoint
    /// 0 open, 1 closed. Interpolated rather than switched, because the closing *is* the "grab".
    var grip: CGFloat
    /// Fades in before the reach and out after the release, so the loop restarts unseen. A hand that
    /// snapped back to the row every 2 seconds would read as a glitch.
    var opacity: CGFloat
    /// Whether the row travels with the hand at this instant.
    var isCarrying: Bool

    // The beats, as fractions of one loop. Named because the numbers are a rhythm and a rhythm read
    // as four bare literals inside an interpolation is a rhythm nobody can adjust.

    /// Fades in over the row, hand open.
    static let reach: CGFloat = 0.14
    /// Closed on it.
    static let grasp: CGFloat = 0.28
    /// Arrived inside the list, still holding.
    static let arrive: CGFloat = 0.72
    /// Let go.
    static let release: CGFloat = 0.86

    /// The plan at `phase`, travelling `arrow`.
    static func at(_ phase: CGFloat, along arrow: ArrowPlan) -> DragHandPlan {
        let t = phase.clampedToUnit

        let travel: CGFloat
        if t <= grasp {
            travel = 0
        } else if t >= arrive {
            travel = 1
        } else {
            // Eased, because a hand that moves at a constant speed reads as a machine. Ease-in-out
            // is what a person's arm does.
            travel = ((t - grasp) / (arrive - grasp)).easedInOut
        }

        let grip: CGFloat
        if t <= reach {
            grip = 0
        } else if t < grasp {
            grip = ((t - reach) / (grasp - reach)).clampedToUnit
        } else if t <= arrive {
            grip = 1
        } else if t < release {
            grip = 1 - ((t - arrive) / (release - arrive)).clampedToUnit
        } else {
            grip = 0
        }

        // In over the first half of the reach, out over what is left after the release. Both ends
        // are dead time in the gesture, which is exactly what makes them the right place to fade.
        let fadeIn = (t / (reach * 0.6)).clampedToUnit
        let fadeOut = ((1 - t) / max(1 - release, 0.001)).clampedToUnit
        return DragHandPlan(
            position: arrow.point(at: travel),
            grip: grip,
            opacity: min(fadeIn, fadeOut),
            // The carry ends at `arrive`, not at `release`. `release` is when the *hand* finishes
            // opening; the row is let go the moment it starts, because that is what opening a hand
            // does. Carrying it through the release beat draws a row still stuck to a hand that is
            // visibly no longer holding it — which `testTheGripIsClosedForEveryInstantTheRowIsCarried`
            // caught, and which is the difference between "it dropped it in the list" and "it took it
            // with it".
            isCarrying: t >= grasp && t <= arrive)
    }
}

extension CGFloat {
    fileprivate var clampedToUnit: CGFloat { Swift.min(Swift.max(self, 0), 1) }
    /// Smoothstep. The one easing curve in this file, spelled once.
    fileprivate var easedInOut: CGFloat {
        let t = clampedToUnit
        return t * t * (3 - 2 * t)
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
    /// The whole settings area. **Not drawn as a boundary any more** — it is the scrim's hole and the
    /// rect the arrow is laid clear of, and it is still what the `framing` tier outlines when the
    /// pane cannot be read at all. `nil` when nothing could be measured.
    ///
    /// It used to be the one dotted boundary, and that was the defect: a window-sized dashed box
    /// says "somewhere in here", which on a pane with two lists and a row below them is not an
    /// instruction. What is dashed now is `destination` and `source` — the two particular rects the
    /// gesture is actually between.
    var area: CGRect?
    /// **Where the thing has to end up**: the list inside the pane. The arrow aims into it and the
    /// caption sits clear of it, and it is **never dashed** — see `dropSlot`. `nil` for a gesture
    /// that moves nothing.
    var destination: CGRect?
    /// **The one row-sized slot inside `destination` the thing actually lands in.** Dashed and
    /// tinted; the only drop affordance drawn.
    ///
    /// This is the defect the reference screenshots were sent to describe. `destination` used to be
    /// what got the dashes, and `destination` is a whole list — so the overlay drew one big dashed
    /// rectangle around every row in the pane, which is the "not the entire thing" the report is
    /// about. A box around a list says "somewhere in here"; a box around a single row-height strip
    /// at the edge the row is coming from says where it goes.
    ///
    /// `nil` for a gesture that moves nothing, and computed rather than measured: System Settings
    /// does not answer a frame for a slot that does not exist yet. Everything it is derived from —
    /// the list, and the height of the row being dragged — was measured, and it is clipped back into
    /// the list, so it can be generous about *which* row and never wrong about where the list is.
    var dropSlot: CGRect?
    /// The glowing control. `nil` when we know where the window is and nothing about its contents:
    /// the region is still drawn, and nothing claims to know which control to press.
    var focus: CGRect?
    /// **The thing being acted on**: the row to drag, or the row whose switch is to be flipped.
    /// Dashed, and never tinted — only the destination is a target.
    var source: CGRect?
    /// `nil` for the same reason as `focus`. **An arrow is only ever drawn when there is a measured
    /// control at the end of it** — that invariant is this type's whole job.
    var arrow: ArrowPlan?
    /// The sentence. Beside the arrow when there is one, over the boundary when there is not.
    var caption: String
    /// The name on the travelling token — this application, as System Settings lists it.
    ///
    /// Carried on the scene rather than read from the bundle at draw time so the token is a pure
    /// function of the scene like everything else here, and so the render harness draws the same
    /// frame the app does.
    var subject: String = ""
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
        exclusions: [CGRect] = [],
        subject: String = PermissionChoreography.appDisplayName
    ) -> SettingsSpotlightScene? {
        guard let displayGlobal = space.globalFrame(of: display) else { return nil }
        guard displayGlobal.intersects(target.focus) else { return nil }

        func local(_ rect: CGRect) -> CGRect {
            rect.offsetBy(dx: -displayGlobal.minX, dy: -displayGlobal.minY)
        }
        let bounds = CGRect(origin: .zero, size: displayGlobal.size)
        let focus = local(target.focus)
        /// Everything measured is clipped to the display as well as to the window: a settings area
        /// that runs past the bottom of the screen would otherwise be outlined across the dock.
        func onDisplay(_ rect: CGRect?) -> CGRect? {
            rect.map(local).map { $0.intersection(bounds) }.flatMap { $0.isNull ? nil : $0 }
        }
        let area = onDisplay(target.area)
        let list = onDisplay(target.list)

        let arrow: ArrowPlan
        var glow = focus
        var source: CGRect?
        var destination: CGRect?
        var slot: CGRect?
        switch target.gesture {
        case .click where target.isListed:
            // The row is right there. **The dashes go round the row, not round the pane** — the
            // particular thing, which is the whole difference between showing somebody where to look
            // and gesturing at a window.
            source = onDisplay(target.row)
            arrow = .pointing(at: focus, keepClearOf: area, within: bounds)
        case .click:
            // Not listed, and the pane offers a **+**. The list is still where the app has to end up,
            // so it is still the drop target — the glow on **+** is what says how to get it there —
            // but what is *drawn* as the target is the slot a new row would appear in, arriving from
            // the **+** below it. A dashed box around the whole list would be the same "somewhere in
            // here" the drag case was reported for.
            destination = list
            slot = list.map { landingSlot(in: $0, arrivingFrom: focus) }
            arrow = .pointing(at: focus, keepClearOf: area, within: bounds)
        case .drag(let from):
            let localSource = local(from)
            source = localSource
            // `clamped` already made `focus` the list for a drag; `list` is the same rect and is what
            // this is *about*, so it is what the arrow aims into — but only as far as the slot.
            let landing = list ?? focus
            destination = landing
            let slotted = landingSlot(in: landing, arrivingFrom: localSource)
            slot = slotted
            // The glow follows the slot rather than staying on the whole list. `drawFocusGlow`
            // refuses to ring a rect that is already dashed, and that refusal is what keeps a drag
            // from carrying two competing highlights; pointing it at the list instead would put a
            // white ring back around every row in the pane.
            glow = slotted
            arrow = .dragging(from: localSource, to: slotted)
        }

        return SettingsSpotlightScene(
            bounds: bounds,
            area: area,
            destination: destination,
            dropSlot: slot,
            focus: glow,
            source: source,
            arrow: arrow,
            caption: caption,
            subject: subject,
            exclusions: exclusions.map(local),
            backingScaleFactor: display.backingScaleFactor)
    }

    /// **The one row's worth of list the thing has to land in.**
    ///
    /// A pure function over two measured rects, because "the dotted highlight is around the row and
    /// not around the list" is a claim with a wrong answer available and the wrong answer is a
    /// screenshot away from looking deliberate.
    ///
    /// The slot goes at the edge of `list` nearest whatever is arriving — the foot for a row loose
    /// below the pane, the head for one above it — because that is the edge the arrow crosses and
    /// the edge a real drop would land on. Its height is the arriving row's, floored so a bare label
    /// frame does not produce a sliver, and clipped back into the list so nothing is ever drawn
    /// outside the thing it is a slot in.
    static func landingSlot(in list: CGRect, arrivingFrom source: CGRect) -> CGRect {
        let height = min(max(source.height, 30), max(list.height, 1))
        let inset = min(6, list.width / 8)
        let y = source.midY > list.midY ? list.maxY - height : list.minY
        let slot = CGRect(
            x: list.minX + inset, y: y, width: max(list.width - inset * 2, 1), height: height)
        let clipped = slot.intersection(list)
        return clipped.isNull || clipped.isEmpty ? list : clipped
    }

    /// One rect the overlay may dash, and what the dashes are claiming about it.
    struct DashedRegion: Equatable, Sendable {
        var rect: CGRect
        /// Matched to the element being surrounded. A 14 pt radius round a 32 pt row is a lozenge,
        /// and reads as a shape of ours rather than as an outline of theirs.
        var cornerRadius: CGFloat
        /// How far outside `rect` the dashes are laid.
        var inset: CGFloat
        /// Tinted inside, which is what makes a rect read as somewhere a thing can be *put* rather
        /// than as something already selected.
        var isDropTarget: Bool
    }

    /// **Every rect this overlay is allowed to dash — and during the Accessibility grant there are
    /// none.**
    ///
    /// The dashes are this overlay's word for *this particular thing*. That is the whole reason
    /// `dropSlot` exists: `destination` is a list, and one dashed rectangle around a list says
    /// "somewhere in here", which is a gesture at a pane rather than an instruction.
    ///
    /// The `framing` tier is the same sentence one level up, and for a long time it was drawn
    /// anyway: it knows a window and, by construction, **nothing about what is inside it**, and it
    /// dashed the window. A user standing on Privacy & Security ▸ Accessibility, looking straight at
    /// their own row with the switch off, saw a dotted boundary drawn around all forty rows and the
    /// sidebar and the title bar — and reported it, in as many words, as the dotted line being
    /// around the wrong thing. It was: the window is measured, but *measured* is only half the
    /// claim, and the other half — that this is the thing to act on — was not ours to make.
    ///
    /// So the tier keeps what it can honestly say. The window is still the scrim's hole, so
    /// everything else on the display dims and System Settings is the only lit thing left; the
    /// sentence still sits beside it naming the pane and the row. Neither claims a target. The row
    /// itself cannot be located until the grant lands — see `PermissionChoreography`'s header for
    /// the measurements that close every route to it — and the instant it does, this list stops
    /// being empty.
    var dashedRegions: [DashedRegion] {
        var regions: [DashedRegion] = []
        // The drop target first, so the source row's outline is stroked over it where they touch.
        if let dropSlot {
            regions.append(
                DashedRegion(rect: dropSlot, cornerRadius: 9, inset: 4, isDropTarget: true))
        }
        if let source {
            regions.append(DashedRegion(rect: source, cornerRadius: 8, inset: 5, isDropTarget: false))
        }
        return regions
    }

    /// **Something was resolved and something will therefore be drawn.**
    ///
    /// The predicate the defect this file's regression test is named for turns on: guidance can be
    /// *requested* for a capability and come back as a scene that puts nothing on screen, and from
    /// the call site those two are indistinguishable — the overlay window is created either way and
    /// the user simply sees nothing. A scene that claims to be pointing has to have a control at the
    /// end of the arrow and at least one region to draw round.
    var isDrawable: Bool { focus != nil && (destination != nil || source != nil || area != nil) }

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
        // A drag has two ends and a hand travelling between them, and the sentence may sit on
        // neither. Beside the whole gesture is the only place left — which is also where the
        // reference puts it, for the same reason.
        if let arrow, let region = destination, source != nil, !confirmed {
            let gap: CGFloat = 30
            let middle = arrow.point(at: 0.5).y
            if bounds.maxX - region.maxX > 340 { return .rightOf(CGPoint(x: region.maxX + gap, y: middle)) }
            if region.minX - bounds.minX > 340 { return .leftOf(CGPoint(x: region.minX - gap, y: middle)) }
            // No room either side of the pane: above the list, which is the one band the gesture
            // never crosses.
            return .above(CGPoint(x: region.midX, y: region.minY))
        }
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
/// **Coloured in one place only, and never with the machine's accent.** The two dashed regions and
/// the arrow between them are `Ink.accent` — a fixed `systemBlue`, guarded by `InkAccentTests`,
/// never `NSColor.controlAccentColor`, which on a machine set to Purple would put purple over
/// another application's window (`INV-UI-1`). Everything else is still white.
///
/// The colour is not decoration: it is what separates *our* dashed rectangles from System Settings'
/// own dashed row, which sits inside the same pane and is also dashed. Two dashed boxes in the same
/// colour a foot apart, one theirs and one ours, is a worse instruction than either alone.
///
/// The dark ribbon under every stroke stays, and is why a hue is affordable at all. The window this
/// lands on belongs to System Settings, whose background is light or dark depending on a setting we
/// do not control and cannot read reliably; a continuous dark band under the dashes gives the blue
/// the same ground either way.
struct SettingsSpotlightCanvas: View {
    var scene: SettingsSpotlightScene
    /// 0…1, wrapping. Drives the marching dashes, the glow's breath and the token that runs along
    /// the arrow. Frozen by the caller under Reduce Motion.
    var phase: Double
    /// 0…1, wrapping. The hand's own clock.
    ///
    /// Separate from `phase` for one reason: under Reduce Motion the two want to be frozen at
    /// *different* instants. The dashes and the token are still at the end of their travel
    /// (`stillPhase`); a hand frozen there has already let go and faded out, which is a still frame
    /// showing no gesture at all. See `stillHandPhase`.
    var handPhase: Double

    init(scene: SettingsSpotlightScene, phase: Double, handPhase: Double? = nil) {
        self.scene = scene
        self.phase = phase
        self.handPhase = handPhase ?? phase
    }

    /// The phase a still frame is shown at: dashes at rest and the token arrived at the tip, which
    /// is the frame the motion existed to arrive at.
    static let stillPhase: Double = 0.999

    /// The phase the **hand** is frozen at under Reduce Motion: arrived in the list, still closed on
    /// the row it carried there.
    ///
    /// `DragHandPlan.arrive`, and not `stillPhase`, because the two motions end in different places.
    /// This is the single frame that carries the whole instruction — a closed hand and a row, inside
    /// the destination — which is what "collapses to a static, still-legible state" has to mean for a
    /// gesture. Frozen anywhere after `release` it is a hand holding nothing, and frozen at 0 it is a
    /// hand resting on a row, which is the *problem* rather than the answer.
    static let stillHandPhase: Double = Double(DragHandPlan.arrive)

    var body: some View {
        Canvas(rendersAsynchronously: false) { context, size in
            let bounds = CGRect(origin: .zero, size: size)
            drawScrim(in: &context, bounds: bounds)
            drawRegions(in: &context)
            drawFocusGlow(in: &context)
            drawArrow(in: &context)
            drawDrag(in: &context)
            drawCaption(in: &context, bounds: bounds)
        }
        .allowsHitTesting(false)
    }

    // MARK: Pieces

    /// How far outside a region the scrim's hole stops.
    ///
    /// The hole stops **inside** the dashes, so a dotted line lands on the dimmed side of the edge
    /// rather than on System Settings' own background. A white line on a light window is invisible
    /// whatever you do to it; a white line on the dimming is unmissable, and precision is read at
    /// that edge — a point of misalignment on a dimmed border is glaringly obvious, which is exactly
    /// why it is trustworthy when it is right.
    private static let holeInset: CGFloat = 4

    /// The dashed stroke. ~2 pt, 6 on / 4 off — fine enough to sit *inside* a pane without reading as
    /// a border the pane grew, which a heavy dash does.
    private static let dashWidth: CGFloat = 2
    private static let dash: [CGFloat] = [6, 4]
    /// One dash plus one gap: the distance the pattern has to march to land back on itself, so a
    /// wrapping phase produces a seamless loop instead of a jump.
    private static let dashPeriod: CGFloat = 10

    /// A wash over everything except the regions the gesture is between and our own windows.
    private func drawScrim(in context: inout GraphicsContext, bounds: CGRect) {
        // Nothing measured means nothing to spotlight, and dimming a whole display to say so would
        // be an overlay shouting about its own failure.
        let openings = holes()
        guard !openings.isEmpty else { return }
        var wash = Path(bounds)
        for hole in openings {
            // **Subtracted, not added with an even-odd fill.** Even-odd counts windings, so a hole
            // that overlaps another hole is a hole that fills itself back in: the settings area and
            // the destination are routinely the *same* rect — any pane with one list — and the first
            // cut of this dimmed the very list it had just cut out, which the render harness showed
            // immediately and no assertion would have.
            wash = wash.subtracting(
                Path(
                    roundedRect: hole.insetBy(dx: -Self.holeInset, dy: -Self.holeInset),
                    cornerRadius: 10))
        }
        context.fill(wash, with: .color(.black.opacity(0.34)))
    }

    /// What the scrim leaves undimmed.
    ///
    /// The **whole settings area**, not just the two regions — the user has to be able to read the
    /// rest of the pane to know they are in the right place, and a pane dimmed everywhere but two
    /// rectangles reads as broken rendering. The regions are picked out by their dashes, which is
    /// what dashes are for.
    private func holes() -> [CGRect] {
        var holes: [CGRect] = []
        if let area = scene.area { holes.append(area) }
        if let destination = scene.destination { holes.append(destination) }
        if let source = scene.source { holes.append(source) }
        holes.append(contentsOf: scene.exclusions)
        return holes
    }

    /// **The dashed regions, and none of them is ever a list or a window.**
    ///
    /// Which rects those are is `scene.dashedRegions`' answer and not this method's, so the rule can
    /// be asserted as a value rather than only inferred from pixels. What is left here is how one
    /// gets drawn.
    ///
    /// Two shapes come out of it in practice: a rounded rectangle round the **drop slot** with a
    /// tint inside it, and a second one round the source row. The tint is the only thing that
    /// distinguishes them and it is doing real work — a drop target has to look like somewhere a
    /// thing can be *put*, and an outline alone looks like something already selected.
    ///
    /// And on the `framing` tier the loop runs zero times, which is the point of it: a tier that
    /// knows a window and nothing inside it has nothing particular to point at, and dashing the
    /// window said otherwise.
    private func drawRegions(in context: inout GraphicsContext) {
        for region in scene.dashedRegions {
            drawRegion(
                in: &context, rect: region.rect, cornerRadius: region.cornerRadius,
                filled: region.isDropTarget, inset: region.inset)
        }
    }

    /// One dashed region: dark ribbon, bloom, tint, dashes.
    ///
    /// The dashes march rather than sitting still, which is what makes an outline read as "this
    /// region" instead of as a decoration somebody left on the screen. `cornerRadius` is the caller's
    /// because it has to match the element being surrounded — a 14 pt radius round a 32 pt row is a
    /// lozenge, and reads as a shape of ours rather than as an outline of theirs.
    private func drawRegion(
        in context: inout GraphicsContext, rect: CGRect, cornerRadius: CGFloat, filled: Bool,
        inset: CGFloat
    ) {
        let line = ScreenSpace.snapped(Self.dashWidth, to: scene.backingScaleFactor)
        let outer = rect.insetBy(dx: -inset, dy: -inset)
        let path = Path(roundedRect: outer, cornerRadius: cornerRadius)
        // Solid once the grant lands: the dashes were saying "look here", and the looking is done.
        let style =
            scene.confirmed
            ? StrokeStyle(lineWidth: line, lineCap: .round)
            : StrokeStyle(
                lineWidth: line, lineCap: .round, dash: Self.dash,
                dashPhase: -CGFloat(phase) * Self.dashPeriod)

        // A dark ribbon, laid **continuously** under the dashes rather than dash-for-dash.
        //
        // This is what makes a thin blue line visible on a light pane. Haloing each dash individually
        // does not work — the halo is wider than a 6 pt dash, so the two merge and the outline reads
        // as a row of grey blobs. A continuous dark band gives every dash the same ground, whatever
        // is underneath it.
        var ribbon = context
        ribbon.addFilter(.blur(radius: 4))
        ribbon.stroke(
            path, with: .color(.black.opacity(0.42)),
            style: StrokeStyle(lineWidth: line + 10, lineCap: .round))

        if filled {
            // The drop target. Faint on purpose — the rows underneath have to stay readable, and a
            // wash strong enough to be noticed on its own is a wash that hides the list it marks.
            context.fill(path, with: .color(Ink.accent.opacity(0.13)))
        }

        // The blue's own bloom, so the region has a presence at the edge of vision.
        var bloom = context
        bloom.addFilter(.blur(radius: 7))
        bloom.stroke(
            path, with: .color(Ink.accent.opacity(0.55)), style: StrokeStyle(lineWidth: line + 5))

        context.stroke(path, with: .color(Ink.accent), style: style)
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
        // A drag's focus *is* the drop slot, which the dashed region already surrounds. Ringing it a
        // second time draws two different highlights round one rect and says there are two things to
        // look at. `destination` is checked too, for the tiers that never grew a slot.
        guard focus != scene.destination, focus != scene.dropSlot else { return }
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
            shaft, with: .color(.black.opacity(0.45)),
            style: StrokeStyle(lineWidth: 8, lineCap: .round))
        context.stroke(
            shaft, with: .color(Ink.accent),
            style: StrokeStyle(lineWidth: 4, lineCap: .round))

        // The head is stroked dark first so the fill keeps a rim on a light window; a stroke rather
        // than a second larger fill, which would lengthen the tip and move where it points.
        let head = headPath(at: arrow.tip, heading: arrow.heading(at: 1))
        context.stroke(
            head, with: .color(.black.opacity(0.45)),
            style: StrokeStyle(lineWidth: 4, lineJoin: .round))
        context.fill(head, with: .color(Ink.accent))

        // The travelling token is the *click* gesture's motion. A drag has the hand instead, and two
        // things moving along one curve at two speeds is a race rather than an instruction.
        guard scene.source == nil || scene.destination == nil else { return }
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

    // MARK: The gesture

    /// **The hand performing the drag**, with the row travelling under it.
    ///
    /// Drawn, not an SF Symbol and certainly not anyone's asset: it has to close, and a glyph cannot.
    /// Two passes — a dark silhouette then the white hand over it — so the shape keeps a rim on a
    /// pane whose lightness is not ours to know, and so the fingers overlapping the palm never show a
    /// seam between them.
    private func drawDrag(in context: inout GraphicsContext) {
        guard !scene.confirmed, let arrow = scene.arrow, let source = scene.source,
            scene.destination != nil
        else { return }
        let hand = DragHandPlan.at(CGFloat(handPhase), along: arrow)
        guard hand.opacity > 0.01 else { return }

        drawCarriedToken(in: &context, hand: hand, source: source)
        drawHand(in: &context, hand: hand)
    }

    /// **The floating Context for Claude row, in the hand's grip.**
    ///
    /// Without something in the hand the hand is a cursor wandering across the pane; with it the
    /// gesture is unmistakable, because moving the thing is what a drag *is*. And what is being moved
    /// has to be recognisable as *this app*: the pane it lands on is a list of applications, and a
    /// blank rectangle travelling into it says a row goes there without saying whose.
    ///
    /// So the token carries the mark and the name — the same two things System Settings puts on the
    /// real row, drawn in white on a dark plate so it reads over either appearance.
    ///
    /// Floored to a legible size rather than drawn at the source's exact size. The rect the
    /// Accessibility API answers for a loose row is often the *label* alone, and a 146 × 24 plate
    /// with an icon in it is a smudge; the dashes stay on the measured rect, and only the thing being
    /// carried is grown.
    private func drawCarriedToken(
        in context: inout GraphicsContext, hand: DragHandPlan, source: CGRect
    ) {
        guard hand.isCarrying else { return }
        let size = CGSize(width: max(source.width, 210), height: max(source.height, 44))
        let carried = CGRect(
            x: hand.position.x - size.width / 2, y: hand.position.y - size.height / 2,
            width: size.width, height: size.height)
        let path = Path(roundedRect: carried, cornerRadius: 9)

        var shadow = context
        shadow.addFilter(.blur(radius: 10))
        shadow.fill(
            Path(roundedRect: carried.offsetBy(dx: 0, dy: 6), cornerRadius: 9),
            with: .color(.black.opacity(0.42 * hand.opacity)))
        // Dark rather than translucent: this passes over both the pane and the desktop on its way
        // up, and a plate that changes legibility mid-travel reads as a rendering fault.
        context.fill(path, with: .color(.black.opacity(0.80 * hand.opacity)))
        context.stroke(
            path, with: .color(Ink.accent.opacity(hand.opacity)),
            style: StrokeStyle(lineWidth: 2, dash: Self.dash))

        let inset: CGFloat = 8
        let side = min(carried.height - inset * 2, 30)
        let tile = CGRect(
            x: carried.minX + inset, y: carried.midY - side / 2, width: side, height: side)
        drawMark(in: &context, tile: tile, opacity: hand.opacity)

        let room = CGSize(width: carried.maxX - tile.maxX - inset * 2, height: carried.height)
        guard !scene.subject.isEmpty, room.width > 8 else { return }
        var name = context.resolve(
            Text(scene.subject).font(.system(size: 14, weight: .medium)).foregroundStyle(.white))
        name.shading = .color(.white.opacity(hand.opacity))
        let measured = name.measure(in: room)
        context.draw(
            name,
            in: CGRect(
                x: tile.maxX + inset, y: carried.midY - measured.height / 2,
                width: min(measured.width, room.width), height: measured.height))
    }

    /// The app's own mark on a tile: a round head, two eyes and two little legs.
    ///
    /// Transcribed from `MenuBar/ContextMark`'s 20 × 20 design box rather than reusing it, and the
    /// reason is a boundary rather than an oversight. `ContextMark` vends a **main-actor** AppKit
    /// template `NSImage`, which is the right shape for a status item and the wrong one here: this is
    /// a non-isolated `Canvas` renderer that draws paths, and reaching a main-actor image out of it
    /// would mean either an `assumeIsolated` that traps if SwiftUI ever renders off the main thread,
    /// or an `Image` threaded through a `Sendable` scene. The geometry is the shared thing and it is
    /// a dozen numbers, copied once; `SpotlightDropSlotTests` renders the token and asserts the plate
    /// is not blank, so a mark that stopped drawing is caught even though a mark that drifted is not.
    ///
    /// `ContextMark` draws in AppKit's y-up space; every y below is that geometry subtracted from 20,
    /// because a `Canvas` is y-down.
    private func drawMark(in context: inout GraphicsContext, tile: CGRect, opacity: CGFloat) {
        let scale = min(tile.width, tile.height) / 20
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: tile.minX + x * scale, y: tile.minY + (20 - y) * scale)
        }
        func box(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat, _ height: CGFloat) -> CGRect {
            CGRect(
                x: tile.minX + x * scale, y: tile.minY + (20 - y - height) * scale,
                width: width * scale, height: height * scale)
        }
        let white = GraphicsContext.Shading.color(.white.opacity(opacity))

        context.stroke(
            Path(ellipseIn: box(3.4, 5.9, 13.2, 12.6)), with: white,
            style: StrokeStyle(lineWidth: 1.9 * scale))
        for x in [7.9, 12.1] as [CGFloat] {
            context.fill(Path(ellipseIn: box(x - 0.78, 11.0, 1.56, 2.1)), with: white)
        }

        // Straight down out of the head, then a short foot curving outward. Written out twice rather
        // than mirrored: the source drawing is not symmetric to the pixel and a mirror would be a
        // different mark that happens to look similar.
        var legs = Path()
        legs.move(to: point(7.7, 6.4))
        legs.addLine(to: point(7.3, 3.3))
        legs.addCurve(to: point(5.8, 2.6), control1: point(7.2, 2.7), control2: point(6.5, 2.5))
        legs.move(to: point(12.3, 6.4))
        legs.addLine(to: point(12.7, 3.3))
        legs.addCurve(to: point(14.2, 2.6), control1: point(12.8, 2.7), control2: point(13.5, 2.5))
        context.stroke(
            legs, with: white,
            style: StrokeStyle(lineWidth: 1.7 * scale, lineCap: .round, lineJoin: .round))
    }

    private func drawHand(in context: inout GraphicsContext, hand: DragHandPlan) {
        let palm = CGRect(x: -13, y: 3, width: 27, height: 26)
        let segments = Self.fingerSegments(grip: hand.grip)

        func pass(_ shading: GraphicsContext.Shading, widen: CGFloat, opacity: Double) {
            var pass = context
            pass.opacity = opacity
            pass.translateBy(x: hand.position.x, y: hand.position.y)
            pass.fill(
                Path(roundedRect: palm.insetBy(dx: -widen / 2, dy: -widen / 2), cornerRadius: 12 + widen / 2),
                with: shading)
            for segment in segments {
                var line = Path()
                line.move(to: segment.from)
                line.addLine(to: segment.to)
                pass.stroke(
                    line, with: shading,
                    style: StrokeStyle(lineWidth: segment.width + widen, lineCap: .round))
            }
        }

        // Silhouette first, whole hand at once. Drawing each finger's rim as it is laid down would
        // put a dark line across the palm wherever a finger crosses it.
        pass(.color(.black.opacity(0.5)), widen: 5, opacity: Double(hand.opacity))
        pass(.color(.white), widen: 0, opacity: Double(hand.opacity))
    }

    /// The four fingers and the thumb, as capsules. Each shortens toward the palm as the grip closes,
    /// which is what a hand closing looks like from the front; the thumb folds across instead.
    ///
    /// Local coordinates, origin at the **grab point** — where the fingertips meet when closed — so
    /// the plan's `position` can be a point on the arrow's own curve and the hand hangs off it.
    private static func fingerSegments(grip: CGFloat) -> [(from: CGPoint, to: CGPoint, width: CGFloat)] {
        // x, knuckle y, open length, closed length, width
        let fingers: [(CGFloat, CGFloat, CGFloat, CGFloat, CGFloat)] = [
            (-8.5, 11, 23, 6, 8),
            (0.5, 10, 27, 7, 8.5),
            (9, 11, 23, 6, 8),
            (16, 14, 16, 4, 7),
        ]
        var segments = fingers.map { finger -> (from: CGPoint, to: CGPoint, width: CGFloat) in
            let (x, knuckle, open, closed, width) = finger
            let length = open + (closed - open) * grip
            return (CGPoint(x: x, y: knuckle), CGPoint(x: x, y: knuckle - length), width)
        }
        // The thumb swings in rather than retracting: open it sticks out to the side, closed it lies
        // across the front of the fist.
        let tip = CGPoint(
            x: -22 + 9 * grip,
            y: 13 + 4 * grip)
        segments.append((CGPoint(x: -10, y: 22), tip, 8.5))
        return segments
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
        for obstacle in [scene.source, scene.destination, scene.focus].compactMap({ $0 }) {
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

}

/// The canvas with a clock attached. Split so the drawing above stays a pure function of `phase`
/// and can be rendered at any phase from a test.
struct SettingsSpotlightView: View {
    var scene: SettingsSpotlightScene
    /// One full trip of the token along the arrow.
    static let period: Double = 2.1

    var body: some View {
        if InkReduceMotion.isEnabled {
            // Reduce Motion gets the still frame each motion was heading for: the token at the tip,
            // the dashes at rest, and the hand arrived in the list still holding the row. The
            // instruction is unchanged; only the travelling is gone.
            SettingsSpotlightCanvas(
                scene: scene, phase: SettingsSpotlightCanvas.stillPhase,
                handPhase: SettingsSpotlightCanvas.stillHandPhase)
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
