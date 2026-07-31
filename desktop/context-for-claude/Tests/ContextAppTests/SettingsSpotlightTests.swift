import AppKit
import XCTest

@testable import ContextApp

//  The System Settings spotlight, in the parts that have a wrong answer available.
//
//  Everything asserted here is a pure function, and that is deliberate. The overlay's failures are
//  the kind nobody reproduces: a monitor stacked above the laptop, a 1× panel beside a 2× one, a
//  window dragged half off the edge, System Settings answering a frame from before the last
//  relayout. None of those exist on the machine the code was written on, and all of them exist on
//  somebody's desk. Making the geometry a value that can be handed arrangements rather than a
//  method that reads `NSScreen` is what lets the suite own them.

// MARK: - Coordinate space

final class ScreenSpaceTests: XCTestCase {
    /// A laptop alone.
    private let single = ScreenSpace(displays: [
        DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    ])

    /// A 2× laptop at the origin with a 1× monitor **above** it — the arrangement that produces
    /// negative CoreGraphics y, which is where a per-display flip goes wrong.
    private let stacked = ScreenSpace(displays: [
        DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2),
        DisplayGeometry(appKitFrame: CGRect(x: 200, y: 982, width: 1_920, height: 1_080), backingScaleFactor: 1),
    ])

    func testFlipsAroundThePrimaryDisplaysHeight() {
        // A System Settings window at the top-left of the primary, 33 pt down for the menu bar —
        // the real frame measured on macOS 26.5.2.
        let settings = CGRect(x: 0, y: 33, width: 723, height: 948)
        XCTAssertEqual(
            single.appKit(from: settings),
            CGRect(x: 0, y: 982 - 33 - 948, width: 723, height: 948))
    }

    /// The bug this type exists to prevent.
    ///
    /// `NSScreen.screens.first` is *usually* the display at (0, 0) and is not promised to be. The
    /// code this replaced used it in two places, and on a one-monitor machine that is invisible
    /// forever. Anchoring on the zero-origin display is what makes it invisible on every machine.
    func testAnchorsOnTheZeroOriginDisplayAndNotOnTheFirstOneListed() {
        let reordered = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: -1_920, y: 40, width: 1_920, height: 1_080)),
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982)),
        ])
        XCTAssertEqual(reordered.primary?.appKitFrame.size, CGSize(width: 1_512, height: 982))
        // Same window, same answer as the single-display case: the flip depends on the primary's
        // height and on nothing else.
        XCTAssertEqual(
            reordered.appKit(from: CGRect(x: 0, y: 33, width: 723, height: 948)),
            CGRect(x: 0, y: 1, width: 723, height: 948))
    }

    /// A display above the primary occupies **negative** CoreGraphics y. One formula covers it; a
    /// flip applied per display would mirror the overlay onto the wrong monitor.
    func testADisplayAboveThePrimaryHasNegativeCoreGraphicsY() {
        let above = stacked.displays[1]
        XCTAssertEqual(
            stacked.globalFrame(of: above),
            CGRect(x: 200, y: -1_080, width: 1_920, height: 1_080))

        // A window near the top of that monitor.
        let window = CGRect(x: 300, y: -1_000, width: 723, height: 948)
        XCTAssertEqual(stacked.appKit(from: window), CGRect(x: 300, y: 982 + 1_000 - 948, width: 723, height: 948))
        XCTAssertEqual(stacked.display(holding: window)?.appKitFrame, above.appKitFrame)
    }

    func testTheTwoConversionsAreExactInverses() {
        for rect in [
            CGRect(x: 0, y: 33, width: 723, height: 948),
            CGRect(x: -1_800, y: -900, width: 400, height: 300),
            CGRect(x: 2_000, y: 1_500, width: 10, height: 10),
        ] {
            guard let there = stacked.appKit(from: rect), let back = stacked.global(from: there) else {
                return XCTFail("both conversions should answer for \(rect)")
            }
            XCTAssertEqual(back, rect)
        }
    }

    /// The mistake this whole type is arranged to make impossible.
    ///
    /// Accessibility, `CGWindowList` and AppKit all answer in **points**. A 2× display does not
    /// have twice the coordinates of a 1× one, it has twice the pixels per coordinate — so the
    /// backing scale must not appear anywhere in the arithmetic. Two identical arrangements that
    /// differ only in density must produce identical geometry.
    func testTheConversionIsIndifferentToBackingScale() {
        let retina = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
        ])
        let plain = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 1)
        ])
        let odd = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 1.5)
        ])
        let window = CGRect(x: 60, y: 120, width: 723, height: 948)
        XCTAssertEqual(retina.appKit(from: window), plain.appKit(from: window))
        XCTAssertEqual(retina.appKit(from: window), odd.appKit(from: window))
    }

    /// Mixed density still has to pick the right display, and report its own scale — which is what
    /// the line widths are snapped to.
    func testPicksTheDisplayHoldingMostOfTheWindowAndCarriesItsOwnScale() {
        let mixed = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2),
            DisplayGeometry(appKitFrame: CGRect(x: 1_512, y: 0, width: 1_920, height: 1_080), backingScaleFactor: 1),
        ])
        // Straddling the seam, mostly on the right-hand 1× panel.
        let straddling = CGRect(x: 1_400, y: 200, width: 723, height: 400)
        XCTAssertEqual(mixed.display(holding: straddling)?.backingScaleFactor, 1)
        // And mostly on the laptop.
        let mostlyLeft = CGRect(x: 900, y: 200, width: 700, height: 400)
        XCTAssertEqual(mixed.display(holding: mostlyLeft)?.backingScaleFactor, 2)
    }

    /// A rect can legitimately be nowhere: a window dragged off the side, a display unplugged
    /// between the lookup and the draw. `nil` is the honest answer and the caller degrades on it.
    func testARectOnNoDisplayIsReportedAsSuchRatherThanClampedOntoOne() {
        XCTAssertNil(single.display(holding: CGRect(x: 4_000, y: 4_000, width: 100, height: 40)))
        XCTAssertFalse(single.isOnScreen(CGRect(x: -900, y: 0, width: 100, height: 40)))
        XCTAssertTrue(single.isOnScreen(CGRect(x: 0, y: 33, width: 723, height: 948)))
    }

    func testSnapsLineWidthsToWholeDevicePixels() {
        XCTAssertEqual(ScreenSpace.snapped(2.5, to: 2), 2.5, "5 physical pixels on a 2× display")
        XCTAssertEqual(ScreenSpace.snapped(2.5, to: 1), 3, "no half pixels on a 1× display")
        // A scaled mode. 1 pt is 1.5 pixels and would land as a grey smear, which on a dotted
        // boundary reads as a rendering fault rather than as a deliberate line; 1.333 pt is 2.
        XCTAssertEqual(ScreenSpace.snapped(1, to: 1.5), 4.0 / 3.0, accuracy: 0.0001)
        // Never divides by zero for a display that reports nothing sensible.
        XCTAssertEqual(ScreenSpace.snapped(2, to: 0), 2)
    }

    /// A measured centre is trusted; a measured size is not. System Settings answers 9 × 9 for a
    /// **+** button drawn at about 24 × 24, so the floor grows the rect **around its own centre** —
    /// generous about how big, never wrong about where.
    func testGrowingASliverKeepsItsCentre() {
        let reported = CGRect(x: 250, y: 964, width: 9, height: 9)
        let grown = reported.atLeast(width: 24, height: 24)
        XCTAssertEqual(grown.midX, reported.midX)
        XCTAssertEqual(grown.midY, reported.midY)
        XCTAssertEqual(grown.size, CGSize(width: 24, height: 24))
        // Already big enough is left alone.
        let row = CGRect(x: 243, y: 122, width: 460, height: 40)
        XCTAssertEqual(row.atLeast(width: 24, height: 24), row)
    }
}

// MARK: - The arrow

final class ArrowPlanTests: XCTestCase {
    /// The display, and the settings area on it, as measured on macOS 26.5.2.
    private let bounds = CGRect(x: 0, y: 0, width: 1_512, height: 982)
    private let area = CGRect(x: 243, y: 122, width: 460, height: 859)
    /// The switch on our row in the Accessibility pane, grown to a glowable size.
    private let toggle = CGRect(x: 647, y: 288, width: 56, height: 30)

    /// The claim the whole overlay rests on: the arrow points **at** the control, from outside it.
    /// A tip inside the control hides the thing being pointed at; a tip far from it points at
    /// nothing in particular.
    func testTheTipLandsJustOutsideTheControlItPointsAt() {
        let plan = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        XCTAssertFalse(toggle.contains(plan.tip), "the tip must not cover the control")
        let gap = min(
            abs(plan.tip.x - toggle.maxX), abs(plan.tip.x - toggle.minX),
            abs(plan.tip.y - toggle.maxY), abs(plan.tip.y - toggle.minY))
        XCTAssertEqual(gap, ArrowPlan.tipGap, accuracy: 0.5)
    }

    /// The switch sits at the right-hand end of every Privacy row with the rest of the display
    /// beyond it, so the arrow comes in from the right and never lies across the list.
    func testComesInFromTheSideWithRoomAndLeavesTheListAlone() {
        let plan = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        XCTAssertEqual(plan.approach, .fromRight)
        XCTAssertGreaterThan(plan.tail.x, area.maxX, "the tail is outside the settings area")
        XCTAssertTrue(bounds.contains(plan.tail), "and on the display")
    }

    /// System Settings dragged to the right-hand edge: there is no longer room on the right, so the
    /// arrow has to come from somewhere else rather than run off the display.
    func testFlipsSidesWhenThereIsNoRoomOnTheObviousOne() {
        let shifted = CGRect(x: 1_450, y: 288, width: 56, height: 30)
        let shiftedArea = CGRect(x: 1_040, y: 122, width: 460, height: 859)
        let plan = ArrowPlan.pointing(at: shifted, keepClearOf: shiftedArea, within: bounds)
        XCTAssertNotEqual(plan.approach, .fromRight)
        XCTAssertTrue(bounds.contains(plan.tail))
        XCTAssertFalse(shifted.contains(plan.tip))
    }

    /// The tail is clamped into the display even when the arrow's full reach would not fit. It
    /// shortens; it never turns around.
    func testTheTailStaysOnTheDisplayAndTheArrowNeverReverses() {
        let cramped = CGRect(x: 0, y: 0, width: 400, height: 300)
        let control = CGRect(x: 300, y: 140, width: 56, height: 30)
        let plan = ArrowPlan.pointing(at: control, keepClearOf: nil, within: cramped)
        XCTAssertTrue(cramped.insetBy(dx: -1, dy: -1).contains(plan.tail))
        // Whatever side was chosen, the tail is on the far side of the tip from the control.
        let outward = plan.approach.outward
        let along = (plan.tail.x - plan.tip.x) * outward.dx + (plan.tail.y - plan.tip.y) * outward.dy
        XCTAssertGreaterThanOrEqual(along, 0, "the tail must stay on the outward side of the tip")
    }

    /// A drag is the other shape: the tip lands **inside** the destination, because that is where
    /// the thing has to end up. An arrow that stops short of its target describes a different
    /// gesture.
    func testADragArrowRunsFromTheSourceIntoTheDestination() {
        let source = CGRect(x: 300, y: 900, width: 300, height: 40)
        let list = CGRect(x: 243, y: 144, width: 460, height: 680)
        let plan = ArrowPlan.dragging(from: source, to: list)
        XCTAssertTrue(source.contains(plan.tail))
        XCTAssertTrue(list.contains(plan.tip))
        XCTAssertEqual(plan.approach, .fromBelow, "the row is below the list it goes into")
    }

    /// The curve is read at two places — the head's angle at `t = 1` and the token's position at
    /// `t = phase` — and both have to agree with the path that is stroked.
    func testTheCurveStartsAtTheTailAndEndsAtTheTip() {
        let plan = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        XCTAssertEqual(plan.point(at: 0).x, plan.tail.x, accuracy: 0.001)
        XCTAssertEqual(plan.point(at: 0).y, plan.tail.y, accuracy: 0.001)
        XCTAssertEqual(plan.point(at: 1).x, plan.tip.x, accuracy: 0.001)
        XCTAssertEqual(plan.point(at: 1).y, plan.tip.y, accuracy: 0.001)
        // The head faces the way the curve is going, not the way the target happens to lie.
        let heading = plan.heading(at: 1)
        XCTAssertTrue(heading.isFinite)
    }

    /// Planning is a function, not a process: the same inputs draw the same arrow every tick. A
    /// bow that flipped sides between frames would read as a glitch.
    func testPlanningIsDeterministic() {
        let a = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        let b = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        XCTAssertEqual(a, b)
    }

    /// Under Reduce Motion the phase is frozen rather than the guidance removed, and it is frozen at
    /// the frame the motion was travelling *towards* — the token arrived at the control.
    ///
    /// Asserted on the geometry rather than on which branch of the view runs: freezing at phase 0
    /// would compile, satisfy "no animation", and leave a still overlay whose only moving part had
    /// stopped at the far end of the arrow pointing at nothing.
    func testTheReduceMotionStillFrameIsTheOneTheMotionWasHeadingFor() {
        let plan = ArrowPlan.pointing(at: toggle, keepClearOf: area, within: bounds)
        let still = plan.point(at: CGFloat(SettingsSpotlightCanvas.stillPhase))
        XCTAssertEqual(still.x, plan.tip.x, accuracy: 1.5)
        XCTAssertEqual(still.y, plan.tip.y, accuracy: 1.5)
    }
}

// MARK: - Degrading against the window server

final class SettingsTargetClampingTests: XCTestCase {
    private let window = CGRect(x: 0, y: 33, width: 723, height: 948)

    private func target(focus: CGRect, area: CGRect? = nil) -> SettingsSpotlightTarget {
        SettingsSpotlightTarget(
            row: focus, toggle: focus, isOn: false, focus: focus,
            area: area ?? CGRect(x: 243, y: 85, width: 460, height: 1_500),
            list: CGRect(x: 243, y: 122, width: 460, height: 1_400), window: window)
    }

    /// One authority per question. The application being measured knows what its controls are and is
    /// unreliable about where they are during a relayout; the window server knows the window.
    /// Measured on macOS 26.5.2: after a resize System Settings reported an `AXScrollArea` 880 pt
    /// tall inside a 470 pt window, so an inner frame is never its own bound.
    func testAreaAndListAreTrimmedToTheWindowTheWindowServerReported() {
        let trimmed = PermissionChoreography.clamped(
            target(focus: CGRect(x: 647, y: 289, width: 56, height: 30)), to: window)
        XCTAssertEqual(trimmed?.area?.maxY, window.maxY, "the boundary stops at the window")
        XCTAssertEqual(trimmed?.list?.maxY, window.maxY)
    }

    /// The row scrolled away. There is **no `AXScrollToVisible`** on these rows, so it cannot be
    /// brought back for the user — and a highlight clamped to the window edge would land on whatever
    /// row took its place. Refusing is the whole point.
    func testAControlOutsideTheWindowRefusesToBePointedAt() {
        XCTAssertNil(
            PermissionChoreography.clamped(
                target(focus: CGRect(x: 647, y: 1_400, width: 56, height: 30)), to: window))
    }

    /// A drag whose source has scrolled out is equally unpointable: an arrow needs both ends.
    func testADragWithItsSourceOutsideTheWindowRefusesToo() {
        var dragging = target(focus: CGRect(x: 243, y: 122, width: 460, height: 400))
        dragging.gesture = .drag(source: CGRect(x: 251, y: 1_600, width: 300, height: 32))
        XCTAssertNil(PermissionChoreography.clamped(dragging, to: window))
    }

    /// No window means no clamping — which is how the pure decision tests, which model no window
    /// server at all, keep working.
    func testNoWindowMeansNoClamping() {
        let untouched = target(focus: CGRect(x: 647, y: 289, width: 56, height: 30))
        XCTAssertEqual(PermissionChoreography.clamped(untouched, to: .zero), untouched)
    }
}

// MARK: - The scene

final class SettingsSpotlightSceneTests: XCTestCase {
    private let laptop = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    private var space: ScreenSpace { ScreenSpace(displays: [laptop, second]) }
    private let second = DisplayGeometry(
        appKitFrame: CGRect(x: 1_512, y: 0, width: 1_920, height: 1_080), backingScaleFactor: 1)

    private func target(focus: CGRect) -> SettingsSpotlightTarget {
        SettingsSpotlightTarget(
            row: CGRect(x: 243, y: 282, width: 460, height: 40), toggle: focus, isOn: false,
            focus: focus, area: CGRect(x: 243, y: 122, width: 460, height: 859),
            list: CGRect(x: 243, y: 122, width: 460, height: 859), gesture: .click,
            window: CGRect(x: 0, y: 33, width: 723, height: 948))
    }

    /// The overlay window covers a display, so getting from global CoreGraphics into the view is a
    /// translation and nothing else. On the primary that translation is zero, which is exactly why
    /// a bug here is invisible on one monitor.
    func testGeometryIsTranslatedByTheDisplaysOriginAndNothingElse() {
        let onLaptop = target(focus: CGRect(x: 647, y: 288, width: 56, height: 30))
        guard let scene = SettingsSpotlightScene.make(
            target: onLaptop, caption: "x", display: laptop, space: space)
        else { return XCTFail("a target on the laptop must produce a scene") }
        XCTAssertEqual(scene.focus, onLaptop.focus, "no offset on the display at the origin")
        XCTAssertEqual(scene.bounds, CGRect(x: 0, y: 0, width: 1_512, height: 982))
        XCTAssertEqual(scene.backingScaleFactor, 2)
    }

    /// The same target on the second display. The second display's CoreGraphics origin is
    /// `(1512, -98)` — its AppKit frame is taller than the primary, so it hangs *above* the primary's
    /// top edge — and the scene has to subtract exactly that.
    func testTheSameTargetOnASecondDisplayIsOffsetByThatDisplaysOrigin() {
        guard let secondGlobal = space.globalFrame(of: second) else { return XCTFail("no frame") }
        XCTAssertEqual(secondGlobal.origin, CGPoint(x: 1_512, y: -98))

        let focus = CGRect(x: 2_100, y: 200, width: 56, height: 30)
        var moved = target(focus: focus)
        moved.area = CGRect(x: 1_700, y: 100, width: 460, height: 800)
        moved.window = CGRect(x: 1_600, y: 60, width: 723, height: 948)
        guard let scene = SettingsSpotlightScene.make(
            target: moved, caption: "x", display: second, space: space)
        else { return XCTFail("a target on the second display must produce a scene") }
        XCTAssertEqual(scene.focus, CGRect(x: 2_100 - 1_512, y: 200 + 98, width: 56, height: 30))
        XCTAssertEqual(scene.backingScaleFactor, 1, "and carries that display's own density")
    }

    /// The boundary is clipped to the display. An area that runs past the bottom of the screen
    /// would otherwise be outlined across the dock and the desktop below it.
    func testTheBoundaryIsClippedToTheDisplay() {
        var overflowing = target(focus: CGRect(x: 647, y: 288, width: 56, height: 30))
        overflowing.area = CGRect(x: 243, y: 122, width: 460, height: 2_000)
        guard let scene = SettingsSpotlightScene.make(
            target: overflowing, caption: "x", display: laptop, space: space)
        else { return XCTFail("expected a scene") }
        XCTAssertEqual(scene.area?.maxY, 982)
    }

    /// A target on a display the scene is not being built for produces nothing, rather than
    /// something drawn at the edge of the wrong screen.
    func testATargetThatIsNotOnThisDisplayProducesNoScene() {
        let elsewhere = target(focus: CGRect(x: 2_100, y: 200, width: 56, height: 30))
        XCTAssertNil(
            SettingsSpotlightScene.make(target: elsewhere, caption: "x", display: laptop, space: space))
    }

    /// The invariant that makes the arrow trustworthy: **no arrow without a measured control at the
    /// end of it.** The framing scene — everything we can honestly draw during the Accessibility
    /// grant, when the pane cannot be read at all — has a boundary and a sentence and neither a glow
    /// nor an arrow.
    func testTheFramingSceneOutlinesTheWindowAndAimsAtNothing() {
        let framed = SettingsWindowFrame(
            window: CGRect(x: 0, y: 33, width: 723, height: 948), instruction: "Switch it on.")
        guard let scene = SettingsSpotlightScene.make(framing: framed, display: laptop, space: space)
        else { return XCTFail("a window on screen must still be outlined") }
        XCTAssertEqual(scene.area, CGRect(x: 0, y: 33, width: 723, height: 948))
        XCTAssertNil(scene.focus)
        XCTAssertNil(scene.arrow)
        XCTAssertEqual(scene.caption, "Switch it on.")
        // And the sentence goes *beside* the region, not over it: a plate laid across System
        // Settings' own header is our instruction covering theirs.
        XCTAssertEqual(
            scene.captionPlacement,
            .rightOf(CGPoint(x: 723 + 26, y: 33 + 474)))
    }

    // MARK: Words alone

    /// **The words-alone plate is placed by measurement, not by a constant.**
    ///
    /// It was pinned to `bounds.midX, bounds.minY + 140` — a fixed distance into a display of
    /// unknown height, and the top band of a display is exactly where window title bars and pane
    /// headers live. It landed over System Settings' own header, which is both our sentence covering
    /// theirs and a sentence reading as a label on a control we explicitly failed to find.
    ///
    /// This tier genuinely has no tracked rect to measure against — `framingOrWords` only reaches it
    /// when there is no System Settings window rect at all, or the rect is on no display, which is
    /// the definition of the tier. What it *does* have is the display's usable area, so that is what
    /// the plate is anchored to: the foot of it, clear of the Dock.
    func testTheWordsAlonePlateHangsOffTheFootOfTheUsableArea() {
        // A 1512 × 982 display with a 25 pt menu bar and a 74 pt Dock along the bottom.
        let visible = CGRect(x: 0, y: 25, width: 1_512, height: 883)
        let scene = SettingsSpotlightScene(
            bounds: CGRect(x: 0, y: 0, width: 1_512, height: 982), visibleBounds: visible,
            area: nil, focus: nil, source: nil, arrow: nil,
            caption: "Scroll down to Context for Claude and switch it on.")

        XCTAssertEqual(scene.captionPlacement, .above(CGPoint(x: 756, y: 908)))
        // Which is the whole point: nowhere near the band a pane's header occupies.
        guard case .above(let anchor) = scene.captionPlacement else { return XCTFail("above") }
        XCTAssertGreaterThan(
            anchor.y, scene.bounds.midY,
            "the unanchored sentence must sit in the lower half of the display, not over the band "
                + "macOS puts title bars and pane headers in")
    }

    /// The Dock is not always at the bottom. A Dock on the left moves the usable area's left edge,
    /// and the plate has to move with it rather than staying where a constant put it — which is the
    /// difference between measuring and assuming.
    func testTheWordsAlonePlateFollowsTheUsableAreaRatherThanTheDisplay() {
        let bounds = CGRect(x: 0, y: 0, width: 1_512, height: 982)
        func anchor(visible: CGRect?) -> CGPoint {
            let scene = SettingsSpotlightScene(
                bounds: bounds, visibleBounds: visible, area: nil, focus: nil, source: nil,
                arrow: nil, caption: "x")
            guard case .above(let point) = scene.captionPlacement else { return .zero }
            return point
        }

        let bottomDock = anchor(visible: CGRect(x: 0, y: 25, width: 1_512, height: 883))
        let leftDock = anchor(visible: CGRect(x: 88, y: 25, width: 1_424, height: 957))
        XCTAssertNotEqual(bottomDock, leftDock, "the plate has to follow the chrome it is clearing")
        XCTAssertEqual(leftDock.x, 88 + 1_424 / 2, "centred on the usable area, not on the display")
        XCTAssertEqual(leftDock.y, 982, "a side Dock leaves the foot of the display usable")
    }

    /// Nothing measured the chrome — a headless space, a display that answered nothing — and the
    /// placement still has to be a rect, not a crash and not a constant. It falls back to the
    /// display, which is the largest honest answer available.
    func testTheWordsAlonePlateFallsBackToTheWholeDisplayWhenNothingMeasuredTheChrome() {
        let bounds = CGRect(x: 0, y: 0, width: 1_512, height: 982)
        let scene = SettingsSpotlightScene(
            bounds: bounds, visibleBounds: nil, area: nil, focus: nil, source: nil, arrow: nil,
            caption: "x")
        XCTAssertEqual(scene.usableBounds, bounds)
        XCTAssertEqual(scene.captionPlacement, .above(CGPoint(x: 756, y: 982)))
    }

    /// A visible frame that does not overlap the display at all — a stale rect from a monitor that
    /// has been unplugged — is discarded rather than used to place a plate off screen.
    func testAnUnusableVisibleFrameIsIgnored() {
        let bounds = CGRect(x: 0, y: 0, width: 1_512, height: 982)
        let scene = SettingsSpotlightScene(
            bounds: bounds, visibleBounds: CGRect(x: 4_000, y: 4_000, width: 100, height: 100),
            area: nil, focus: nil, source: nil, arrow: nil, caption: "x")
        XCTAssertEqual(scene.usableBounds, bounds)
    }

    /// The measured tiers are untouched: a scene with a boundary still puts the plate beside the
    /// boundary, whatever the display's chrome is doing.
    func testTheUsableAreaDoesNotDisturbTheTiersThatMeasuredSomething() {
        let framed = SettingsWindowFrame(
            window: CGRect(x: 0, y: 33, width: 723, height: 948), instruction: "Switch it on.")
        guard var scene = SettingsSpotlightScene.make(framing: framed, display: laptop, space: space)
        else { return XCTFail("expected a scene") }
        let before = scene.captionPlacement
        scene.visibleBounds = CGRect(x: 0, y: 25, width: 1_512, height: 883)
        XCTAssertEqual(scene.captionPlacement, before)
    }

    /// With no room beside it, the plate falls back to hanging off the top of the boundary rather
    /// than off the edge of the display.
    func testTheBoundaryOnlyCaptionFallsBackToTheTopWhenThereIsNoRoomBeside() {
        let wide = DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 800, height: 982))
        let space = ScreenSpace(displays: [wide])
        let framed = SettingsWindowFrame(
            window: CGRect(x: 20, y: 33, width: 723, height: 948), instruction: "Switch it on.")
        guard let scene = SettingsSpotlightScene.make(framing: framed, display: wide, space: space)
        else { return XCTFail("expected a scene") }
        guard case .above = scene.captionPlacement else {
            return XCTFail("no room either side: the plate belongs above the boundary")
        }
    }

    /// A window drag translates the window's whole contents; nothing inside it moves relative to
    /// anything else. That is what makes the cheap tracking tick exact rather than an approximation
    /// of the expensive one.
    func testTranslatingATargetMovesEveryRectTogether() {
        let source = CGRect(x: 300, y: 900, width: 300, height: 40)
        var dragging = target(focus: CGRect(x: 243, y: 122, width: 460, height: 859))
        dragging.gesture = .drag(source: source)
        let moved = dragging.translated(by: CGVector(dx: 120, dy: -40))

        XCTAssertEqual(moved.focus, dragging.focus.offsetBy(dx: 120, dy: -40))
        XCTAssertEqual(moved.area, dragging.area?.offsetBy(dx: 120, dy: -40))
        XCTAssertEqual(moved.window, dragging.window.offsetBy(dx: 120, dy: -40))
        guard case .drag(let movedSource) = moved.gesture else { return XCTFail("gesture lost") }
        XCTAssertEqual(movedSource, source.offsetBy(dx: 120, dy: -40))
    }
}

// MARK: - Tracking

final class SpotlightTrackPolicyTests: XCTestCase {
    private let policy = SpotlightTrackPolicy()
    private let window = CGRect(x: 0, y: 33, width: 723, height: 948)

    /// The measurement that dictates the whole design. Re-reading the window's bounds costs a
    /// fraction of a millisecond; walking the tree to find the row costs ~270 ms, and the old
    /// overlay did the second one 2.5 times a second on the main actor — a live trace caught a
    /// 727 ms tick. So an unchanged window between full solves must do **nothing**.
    func testAnUnchangedWindowBetweenSolvesDoesNothing() {
        XCTAssertEqual(
            policy.decide(sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: window),
            .hold)
    }

    /// A move is the common case and is answered without touching the tree at all.
    func testAMovedWindowTranslatesInsteadOfRewalkingTheTree() {
        let moved = window.offsetBy(dx: 240, dy: -60)
        XCTAssertEqual(
            policy.decide(sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: moved),
            .translate(CGVector(dx: 240, dy: -60)))
    }

    /// A resize relays the pane out: every row moves relative to the window, so nothing can be
    /// carried over.
    func testAResizedWindowForcesAFullSolve() {
        let resized = CGRect(x: 0, y: 33, width: 723, height: 470)
        XCTAssertEqual(
            policy.decide(sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: resized),
            .solve)
    }

    func testTheTreeIsRewalkedOnlyOnItsOwnSlowSchedule() {
        XCTAssertEqual(
            policy.decide(sinceLastSolve: policy.fullSolve, windowThen: window, windowNow: window),
            .solve)
        XCTAssertGreaterThanOrEqual(
            policy.fullSolve, .milliseconds(500),
            "the expensive walk must stay far slower than the cheap tick")
        XCTAssertLessThanOrEqual(
            policy.tick, .milliseconds(50),
            "and the cheap tick fast enough that a dragged window does not leave the overlay behind")
    }

    /// A window that has gone is not a reason to walk the tree every 40 ms hunting for it.
    func testAMissingWindowStillWaitsForTheSlowSchedule() {
        XCTAssertEqual(
            policy.decide(sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: nil), .hold)
        XCTAssertEqual(
            policy.decide(sinceLastSolve: policy.fullSolve, windowThen: window, windowNow: nil), .solve)
    }
}

final class SpotlightHysteresisTests: XCTestCase {
    private let pointing = PermissionGuidance.pointing(
        SettingsSpotlightTarget(
            row: CGRect(x: 243, y: 282, width: 460, height: 40),
            toggle: CGRect(x: 647, y: 288, width: 56, height: 30), isOn: false))
    private let words = PermissionGuidance.instruction("Open System Settings.")

    /// Measured on macOS 26.5.2: System Settings routinely answers with **zero** accessibility
    /// windows while its window is plainly on screen. Believing the first empty answer makes the
    /// overlay flap between an arrow and a sentence while nothing visible has changed, and flapping
    /// is indistinguishable from being broken.
    func testATransientLossKeepsTheGoodAnswerOnScreen() {
        var steadying = SpotlightHysteresis()
        XCTAssertEqual(steadying.settle(pointing), pointing)
        XCTAssertEqual(steadying.settle(words), pointing, "one empty answer is not a disappearance")
        XCTAssertEqual(steadying.settle(pointing), pointing)
    }

    /// It is hysteresis, not denial. A loss that persists is believed, and the overlay degrades.
    func testAPersistentLossIsBelievedAndDegrades() {
        var steadying = SpotlightHysteresis(tolerance: 2)
        _ = steadying.settle(pointing)
        XCTAssertEqual(steadying.settle(words), pointing)
        XCTAssertEqual(steadying.settle(words), pointing)
        XCTAssertEqual(steadying.settle(words), words, "past the tolerance, the truth wins")
    }

    /// Guidance that becomes *available* is shown at once. Nobody should wait three ticks for help
    /// that has arrived.
    func testAnImprovementIsBelievedImmediately() {
        var steadying = SpotlightHysteresis()
        XCTAssertEqual(steadying.settle(words), words)
        XCTAssertEqual(steadying.settle(pointing), pointing)
    }
}

// MARK: - The window

final class SpotlightWindowTests: XCTestCase {
    /// The overlay covers a whole display **including the switch it points at**. Every one of these
    /// is what keeps it from blocking, dimming or stealing focus from the interaction it exists to
    /// teach — asserted on a real window rather than on a description of one.
    @MainActor
    func testTheOverlayNeverBlocksOrStealsTheInteractionItTeaches() {
        let display = DisplayGeometry(
            appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
        let window = SpotlightWindow.make(covering: display)
        defer { window.orderOut(nil) }

        XCTAssertTrue(window.ignoresMouseEvents, "the overlay must be click-through")
        XCTAssertFalse(window.canBecomeKey, "taking key status would unfocus System Settings")
        XCTAssertFalse(window.canBecomeMain)
        XCTAssertFalse(window.isOpaque)
        XCTAssertEqual(window.backgroundColor, .clear)
        XCTAssertFalse(window.hasShadow)
        XCTAssertEqual(window.animationBehavior, .none)
        XCTAssertGreaterThanOrEqual(
            window.level.rawValue, Int(CGWindowLevelForKey(.statusWindow)),
            "an overlay behind the thing it describes is worse than none")
        XCTAssertTrue(window.collectionBehavior.contains(.canJoinAllSpaces))
        XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
        XCTAssertTrue(window.collectionBehavior.contains(.ignoresCycle))
        XCTAssertEqual(window.frame, display.appKitFrame, "the frame is the display's, verbatim")
        // This app records the screen. Its own guidance chrome must not land in the user's history.
        XCTAssertEqual(window.sharingType, SpotlightWindow.isCapturable ? .readOnly : .none)
    }
}
