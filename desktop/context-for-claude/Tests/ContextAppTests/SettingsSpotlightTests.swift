import AppKit
import SwiftUI
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
    /// grant, when the pane cannot be read at all — keeps the window as the scrim's hole and the
    /// sentence beside it, and has neither a glow nor an arrow.
    func testTheFramingSceneKeepsTheWindowAndAimsAtNothing() {
        let framed = SettingsWindowFrame(
            window: CGRect(x: 0, y: 33, width: 723, height: 948), instruction: "Switch it on.")
        guard let scene = SettingsSpotlightScene.make(framing: framed, display: laptop, space: space)
        else { return XCTFail("a window on screen must still light the pane out of the desktop") }
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

    /// **The dotted line is never drawn round the whole window.**
    ///
    /// The report, in the user's words: *"The dotted line should be exactly on Context for Claude
    /// here for accessibility."* They were standing on Privacy & Security ▸ Accessibility with their
    /// own row in the list and its switch off, and the overlay had dashed the entire System Settings
    /// window — sidebar, title bar and forty other applications' rows inside the boundary.
    ///
    /// The row cannot be found from there. Measured on macOS 26.5.2 (25F84) from an untrusted
    /// process: every read of System Settings' accessibility tree returns `kAXErrorAPIDisabled`,
    /// including the attribute *name* list, including `AXUIElementCopyElementAtPosition`, and
    /// including the same read asked through System Events. `PermissionChoreography`'s header has
    /// the full set. So the honest answer is not a better boundary, it is **no boundary**: the
    /// dashes are this overlay's word for *this particular thing*, and this tier has no particular
    /// thing. It keeps the scrim's hole and the sentence, both of which are true.
    func testTheFramingTierDashesNothingAtAll() {
        let framed = SettingsWindowFrame(
            window: CGRect(x: 0, y: 33, width: 723, height: 948), instruction: "Switch it on.",
            cause: .awaitingTrust)
        guard let scene = SettingsSpotlightScene.make(framing: framed, display: laptop, space: space)
        else { return XCTFail("expected a scene") }
        XCTAssertEqual(
            scene.dashedRegions, [],
            "the window is dashed again — that is a dotted boundary round forty rows, told as if it "
                + "were round one")
        // The tier is not silent, though. The window is still what the scrim opens a hole in, so
        // System Settings is the only lit thing left on the display.
        XCTAssertEqual(scene.area, framed.window)
    }

    /// The counterpart, so the assertion above cannot be passing because nothing is ever dashed. A
    /// located row **is** dashed, and what is dashed is the row rather than anything containing it.
    func testALocatedRowIsStillDashed() throws {
        let window = CGRect(x: 0, y: 33, width: 723, height: 948)
        let row = CGRect(x: 243, y: 282, width: 460, height: 40)
        let located = SettingsSpotlightTarget(
            row: row, toggle: CGRect(x: 647, y: 288, width: 56, height: 30), isOn: false,
            focus: CGRect(x: 647, y: 285, width: 56, height: 36),
            area: CGRect(x: 233, y: 122, width: 480, height: 700),
            list: CGRect(x: 243, y: 142, width: 460, height: 640), isListed: true,
            gesture: .click, window: window)
        guard let scene = SettingsSpotlightScene.make(
            target: located, caption: "Switch it on.", display: laptop, space: space)
        else { return XCTFail("expected a scene") }

        let dashed = try XCTUnwrap(scene.dashedRegions.first)
        XCTAssertEqual(scene.dashedRegions.count, 1)
        XCTAssertEqual(dashed.rect, row, "the dashes belong on the row that was measured")
        XCTAssertLessThan(
            dashed.rect.height * dashed.rect.width,
            (scene.area?.height ?? 0) * (scene.area?.width ?? 0) / 4,
            "a 'row' the size of a quarter of the pane is the old boundary under a new name")
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

// MARK: - The bootstrap tier, on the rendered frame

/// **The complaint, answered in pixels.**
///
/// `testTheFramingTierDashesNothingAtAll` asserts the model, and the model is the seam the drawing
/// consumes — but "what gets dashed" ultimately lives in `SettingsSpotlightCanvas`, so the claim is
/// worth making where the user made it: on the frame. This renders the shipping canvas over the
/// shipping scene and looks for the overlay's blue along the window's own edge, which is exactly
/// where the reported boundary was.
///
/// Restoring the branch that dashed `scene.area` fails it immediately — measured, not asserted in a
/// comment: 750 accent pixels down the left edge and 600 along the top. That is what makes it a
/// regression test rather than a description.
final class SpotlightFramingBoundaryTests: XCTestCase {
    private let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    private var space: ScreenSpace { ScreenSpace(displays: [display]) }
    private let window = CGRect(x: 300, y: 60, width: 723, height: 860)

    @MainActor
    func testNoDottedBoundaryIsDrawnRoundTheSystemSettingsWindow() throws {
        let framed = SettingsWindowFrame(
            window: window,
            instruction: "In System Settings, open Privacy & Security ▸ Accessibility and switch on "
                + PaneFixture.appName + ".",
            cause: .awaitingTrust)
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(framing: framed, display: display, space: space))
        let bitmap = try Self.render(scene)

        // A band straddling the window's left edge, clear of the caption plate (which sits to the
        // right of the window) and of the display's own edges. The boundary was drawn 11 pt outside
        // the window, so this band is where it lived.
        let edge = CGRect(x: window.minX - 24, y: window.minY + 120, width: 48, height: 500)
        XCTAssertEqual(
            Self.accentPixels(in: edge, of: bitmap), 0,
            "the System Settings window is being dashed again — a dotted boundary round the whole "
                + "pane says 'somewhere in here', and the row it is standing in for is one of forty")

        let top = CGRect(x: window.minX + 100, y: window.minY - 24, width: 400, height: 48)
        XCTAssertEqual(Self.accentPixels(in: top, of: bitmap), 0, "nor along its top edge")
    }

    /// The negative control. Without it the counts above could be measuring a renderer that drew
    /// nothing at all — the same clean frame a broken canvas produces.
    @MainActor
    func testThePointingTierStillDrawsTheAccentSoTheCountMeansSomething() throws {
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)
        guard case .pointing(let target) = guidance else {
            throw XCTSkip("the drag scene must resolve for this to mean anything")
        }
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(
                target: target, caption: "Drag it up", display: display, space: space))
        let slot = try XCTUnwrap(scene.dropSlot)
        let bitmap = try Self.render(scene)
        XCTAssertGreaterThan(
            Self.accentPixels(
                in: CGRect(x: slot.minX, y: slot.minY - 10, width: slot.width, height: 20),
                of: bitmap),
            20,
            "the canvas drew no accent anywhere, so a zero count proves nothing about the framing "
                + "tier")
    }

    // MARK: Pixels

    /// `ImageRenderer` over the shipping canvas at scale 1, so a point is a pixel and the scene's
    /// own coordinates address it. The same technique `SpotlightDropSlotTests` uses.
    @MainActor
    private static func render(_ scene: SettingsSpotlightScene) throws -> NSBitmapImageRep {
        let renderer = ImageRenderer(
            content: ZStack {
                Color.white
                SettingsSpotlightCanvas(scene: scene, phase: 0.5, handPhase: 0.05)
            }
            .frame(width: scene.bounds.width, height: scene.bounds.height))
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.cgImage, "the spotlight did not render")
        return try XCTUnwrap(
            NSBitmapImageRep(cgImage: image).converting(to: .sRGB, renderingIntent: .default))
    }

    /// Pixels that are unmistakably the overlay's blue rather than the white ground, the grey scrim
    /// or the black caption plate. A wide margin on purpose: the dashes are composited over a
    /// blurred dark ribbon, so the exact value moves and only the direction is stable.
    private static func accentPixels(in rect: CGRect, of bitmap: NSBitmapImageRep) -> Int {
        var count = 0
        for x in stride(from: Int(rect.minX), to: Int(rect.maxX), by: 2) {
            for y in stride(from: Int(rect.minY), to: Int(rect.maxY), by: 2) {
                guard x >= 0, y >= 0, x < bitmap.pixelsWide, y < bitmap.pixelsHigh,
                    let pixel = bitmap.colorAt(x: x, y: y)
                else { continue }
                let blue = Double(pixel.blueComponent)
                if blue - Double(pixel.redComponent) > 0.20 && blue > 0.35 { count += 1 }
            }
        }
        return count
    }
}

// MARK: - Tracking

final class SpotlightTrackPolicyTests: XCTestCase {
    private let policy = SpotlightTrackPolicy()
    private let window = CGRect(x: 0, y: 33, width: 723, height: 948)

    /// A boundary drawn only because the Accessibility grant has not landed yet — the bootstrap
    /// tier, and the one the whole Accessibility step is spent in.
    private var awaitingTrust: PermissionGuidance {
        .framing(
            SettingsWindowFrame(window: window, instruction: "Switch it on.", cause: .awaitingTrust))
    }
    /// The same rect reached the expensive way: we *are* trusted, the tree was walked, and the row
    /// was still not found.
    private var unreadable: PermissionGuidance {
        .framing(
            SettingsWindowFrame(window: window, instruction: "Switch it on.", cause: .unreadable))
    }
    private var pointing: PermissionGuidance {
        .pointing(
            SettingsSpotlightTarget(
                row: CGRect(x: 243, y: 282, width: 460, height: 40),
                toggle: CGRect(x: 647, y: 288, width: 56, height: 30), isOn: false, window: window))
    }

    /// The measurement that dictates the whole design. Re-reading the window's bounds costs a
    /// fraction of a millisecond; walking the tree to find the row costs ~270 ms, and the old
    /// overlay did the second one 2.5 times a second on the main actor — a live trace caught a
    /// 727 ms tick. So an unchanged window between full solves must do **nothing**.
    func testAnUnchangedWindowBetweenSolvesDoesNothing() {
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: window,
                showing: pointing),
            .hold)
    }

    /// A move is the common case and is answered without touching the tree at all.
    func testAMovedWindowTranslatesInsteadOfRewalkingTheTree() {
        let moved = window.offsetBy(dx: 240, dy: -60)
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: moved,
                showing: pointing),
            .translate(CGVector(dx: 240, dy: -60)))
    }

    /// A resize relays the pane out: every row moves relative to the window, so nothing can be
    /// carried over.
    func testAResizedWindowForcesAFullSolve() {
        let resized = CGRect(x: 0, y: 33, width: 723, height: 470)
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: resized,
                showing: pointing),
            .solve)
    }

    func testTheTreeIsRewalkedOnlyOnItsOwnSlowSchedule() {
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: policy.fullSolve, windowThen: window, windowNow: window,
                showing: pointing),
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
            policy.decide(
                sinceLastSolve: .milliseconds(40), windowThen: window, windowNow: nil,
                showing: pointing),
            .hold)
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: policy.fullSolve, windowThen: window, windowNow: nil,
                showing: pointing),
            .solve)
    }

    // MARK: Noticing the grant

    /// **A due solve is never starved by a window that keeps moving.**
    ///
    /// `decide` answered `translate` before it consulted the schedule, and the tracker does not
    /// reset its clock on a translation — so for as long as the origin differed from one tick to the
    /// next, the solve that would have noticed the grant never ran. Dragging System Settings does
    /// exactly that for as long as the mouse is down, which is when somebody hunting for a row is
    /// most likely to be moving the window out of their own way.
    ///
    /// Driven the way the tick loop drives it: a window creeping 4 pt per tick, far past the point a
    /// solve was due.
    func testADueSolveIsNotStarvedByAWindowThatKeepsMoving() {
        var moving = window
        var elapsed = Duration.zero
        for _ in 0..<200 {
            let next = moving.offsetBy(dx: 4, dy: 0)
            elapsed += policy.tick
            if policy.decide(
                sinceLastSolve: elapsed, windowThen: moving, windowNow: next, showing: pointing)
                == .solve
            {
                return
            }
            moving = next
        }
        XCTFail(
            "200 ticks of a moving window and never one solve — a grant landing during a drag is "
                + "invisible for as long as the drag lasts")
    }

    /// **The bootstrap tier is watched at tick rate, because it costs a tick to watch.**
    ///
    /// `fullSolve` is 800 ms because the tree walk costs up to 727 ms. The `awaitingTrust` tier
    /// performs no walk at all — `liveGuidance` returns at the `AXElement.isTrusted` guard — and the
    /// whole pass measured 0.55 ms on macOS 26.5.2, of which the tracker was already paying 0.42 ms
    /// every tick to read the window frame. Rationing it on the walk's schedule left the overlay
    /// degraded for up to 800 ms after the user had already flipped the switch.
    func testTheGrantIsWatchedAtTickRateRatherThanOnTheWalksSchedule() {
        XCTAssertLessThanOrEqual(
            policy.trustWatch, policy.tick,
            "the grant has to be seen on the first tick after it lands, not on the walk's schedule")
        XCTAssertEqual(policy.interval(after: awaitingTrust), policy.trustWatch)
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: policy.tick, windowThen: window, windowNow: window,
                showing: awaitingTrust),
            .solve,
            "a boundary that is only a boundary because we are not trusted yet has to re-ask every "
                + "tick — the answer is free to take and is about to change")
    }

    /// The other half of it, or the fast schedule would just be the schedule. A pane we **are**
    /// trusted for and still could not read costs a whole walk to re-ask, and nothing the user is
    /// about to do makes it cheaper.
    func testAPaneWeAreTrustedForAndStillCannotReadKeepsTheSlowSchedule() {
        XCTAssertEqual(policy.interval(after: unreadable), policy.fullSolve)
        XCTAssertEqual(
            policy.decide(
                sinceLastSolve: policy.tick, windowThen: window, windowNow: window,
                showing: unreadable),
            .hold,
            "re-walking the tree every 40 ms is the 727 ms main-actor stall this policy exists for")
        XCTAssertEqual(policy.interval(after: pointing), policy.fullSolve)
        XCTAssertEqual(policy.interval(after: nil), policy.fullSolve)
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

// MARK: - The spotlight was requested and nothing was drawn
//
//  The defect this section exists for was not a rendering fault, a coordinate fault or an
//  accessibility fault. On a cold first run the card said "System Settings is open on the right row",
//  System Settings *was* open on the right row, and no boundary, no glow and no arrow appeared —
//  because **nothing ever asked for one**. `PermissionOverlay.show` had two call sites: the by-hand
//  offer, which is only ever Accessibility, and the finale, which only runs at `step == .done`. The
//  gate's own `waitingInSettings` phase — the one microphone, system audio and screen recording all
//  pass through — asked for nothing.
//
//  Two claims, and both have to hold or the overlay is decorative:
//
//  1. **Something asks.** `PermissionGate.spotlightSubject` is the single predicate, so "should
//     anything be pointing right now" has one answer rather than one per call site.
//  2. **What comes back draws.** Guidance can be requested and still resolve to a scene that puts
//     nothing on screen, and from the call site the two are indistinguishable — the window is created
//     either way and the user simply sees nothing.

final class SpotlightIsActuallyRequestedTests: XCTestCase {

    /// Claim 1, for **every** capability rather than the one that was reported. Screen recording is
    /// how the defect was found; microphone and system audio were equally unpointed at.
    func testEveryCapabilityTheGateWaitsOnGetsASpotlight() {
        for capability in Capability.allCases {
            XCTAssertEqual(
                PermissionGate.spotlightSubject(of: .waitingInSettings(capability)), capability,
                "the gate stands in System Settings for \(capability.rawValue) and nothing points at "
                    + "the row — which is the whole of the defect, on that capability")
        }
    }

    /// And the phases that must **not** point, because pointing there would be wrong rather than
    /// merely missing: a TCC dialog is up, the pane has not been opened yet, or the grant has landed
    /// and the confirmation beat owns the overlay.
    func testNoOtherPhaseClaimsToBePointing() {
        let quiet: [PermissionGate.Phase] = [
            .idle, .explaining(.screen), .prompting(.screen), .confirming(.screen), .blocked,
            .complete,
        ]
        for phase in quiet {
            XCTAssertNil(
                PermissionGate.spotlightSubject(of: phase),
                "\(phase) must not put an overlay over System Settings")
        }
    }

    /// **Claim 2, end to end, for the capability the defect was reported on.**
    ///
    /// A real pane shape, through the real decision, into the real scene builder — and the assertion
    /// is that what comes out *draws*: a resolved control, both regions, and an arrow between them.
    /// A scene with `focus == nil` and no regions is what "the overlay appeared and was empty" looks
    /// like from the model, and it is the state this asserts cannot be reached from a pane we can
    /// read.
    func testScreenRecordingGuidanceProducesADrawableSceneAndNotAnEmptyOne() {
        let display = DisplayGeometry(
            appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
        let space = ScreenSpace(displays: [display])

        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)

        guard case .pointing(let target) = guidance else {
            return XCTFail(
                "a readable Screen Recording pane must produce something to point at, got \(guidance)")
        }
        guard let scene = SettingsSpotlightScene.make(
            target: target,
            caption: PermissionChoreography.caption(
                for: target.gesture, appName: PaneFixture.appName, isOn: target.isOn,
                listed: target.isListed),
            display: display, space: space)
        else { return XCTFail("the target is on this display and must produce a scene") }

        XCTAssertTrue(
            scene.isDrawable,
            "guidance was requested for screen recording and the scene draws nothing — this is the "
                + "defect: the overlay window is created, and the user sees an empty screen")
        XCTAssertNotNil(scene.focus, "no resolved target means no arrow may be drawn at all")
        XCTAssertNotNil(scene.destination, "the list is the drop target and has to be drawn")
        XCTAssertNotNil(scene.source, "the row being dragged has to be drawn")
        XCTAssertNotNil(scene.arrow)
        XCTAssertEqual(scene.caption, "Drag \(PaneFixture.appName) up into the list")
    }

    /// The honest degrade, asserted in the same breath — because the cheapest way to make the test
    /// above pass forever is to draw a confident box around a guess.
    func testAPaneThatCannotBeReadStillRefusesToPointAtAnything() {
        let display = DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982))
        let space = ScreenSpace(displays: [display])
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [], windowFrame: .zero, space: space)
        guard case .instruction = guidance else {
            return XCTFail("nothing was readable, so nothing may be aimed: got \(guidance)")
        }
    }
}

// MARK: - Two regions, not one window
//
//  "The dotted lines should be on the particular section." The overlay used to draw **one** dashed
//  rectangle around the whole settings area, which on a pane holding two lists and a loose row below
//  them says "somewhere in here" — a gesture at a window rather than an instruction. What is dashed
//  now is the destination and the source: the two particular rects the gesture is between.

final class SpotlightRegionTests: XCTestCase {
    private let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    private var space: ScreenSpace { ScreenSpace(displays: [display]) }

    private func dragScene() -> SettingsSpotlightScene? {
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)
        guard case .pointing(let target) = guidance else { return nil }
        return SettingsSpotlightScene.make(
            target: target, caption: "Drag it up", display: display, space: space)
    }

    /// The destination is the **list**, and the source is the **row** — each drawn round the element
    /// it belongs to, and both strictly inside the window rather than being it.
    func testTheRegionsAreTheListAndTheRowRatherThanTheWholePane() throws {
        let scene = try XCTUnwrap(dragScene())
        let destination = try XCTUnwrap(scene.destination)
        let source = try XCTUnwrap(scene.source)

        XCTAssertEqual(destination, PaneFixture.dragPaneList, "the drop target is the list itself")
        XCTAssertEqual(source, PaneFixture.dragPaneStrayRow, "the source is the loose row")
        XCTAssertFalse(
            destination.contains(source),
            "the row is below the list, not inside it — a source drawn inside its own destination "
                + "describes no movement at all")
        // The complaint, stated as arithmetic: neither dashed region may be the size of the pane.
        let window = PaneFixture.dragPaneWindow
        for (name, region) in [("destination", destination), ("source", source)] {
            XCTAssertLessThan(
                region.width * region.height, window.width * window.height * 0.5,
                "the \(name) covers half the window — that is the coarse boundary this replaced")
        }
    }

    /// The arrow runs **from the row up into the list**, and its tip lands inside the destination:
    /// a drag arrow that stops short of its target is describing a different gesture.
    func testTheArrowRunsFromTheRowUpIntoTheList() throws {
        let scene = try XCTUnwrap(dragScene())
        let arrow = try XCTUnwrap(scene.arrow)
        let destination = try XCTUnwrap(scene.destination)
        let source = try XCTUnwrap(scene.source)

        XCTAssertTrue(source.insetBy(dx: -2, dy: -2).contains(arrow.tail), "it starts on the row")
        XCTAssertTrue(destination.contains(arrow.tip), "and ends inside the list")
        XCTAssertLessThan(arrow.tip.y, arrow.tail.y, "up the pane, which is the half of the "
            + "instruction the user cannot infer from the pane itself")
        XCTAssertEqual(arrow.approach, .fromBelow)
    }

    /// A listed row is a click, not a drag — and the dashes go round **that row**, not round the
    /// pane. Same complaint, the other gesture.
    func testAClickOnAListedRowDashesTheRowAndNotThePane() throws {
        let row = CGRect(x: 611, y: 289, width: 442, height: 40)
        let target = SettingsSpotlightTarget(
            row: row, toggle: CGRect(x: 1_017, y: 301, width: 36, height: 16), isOn: false,
            focus: CGRect(x: 1_007, y: 296, width: 56, height: 30),
            area: CGRect(x: 603, y: 145, width: 460, height: 500),
            list: CGRect(x: 603, y: 145, width: 460, height: 500), isListed: true, gesture: .click,
            window: PaneFixture.dragPaneWindow)
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(target: target, caption: "x", display: display, space: space))

        XCTAssertEqual(scene.source, row, "the dashes belong on the row being pointed at")
        XCTAssertNil(scene.destination, "a click moves nothing, so there is no drop target")
        XCTAssertNotNil(scene.focus, "and the switch still glows")
    }

    /// The degrade keeps its shape: when only the window is known, **no** region claims to be a row
    /// — and, since the report, no region claims to be anything at all. `isDrawable` is false and
    /// `dashedRegions` is empty; what is left is the scrim's hole over a measured window and the
    /// sentence beside it.
    func testTheFramingTierNamesNoRowAndDashesNothing() throws {
        let framed = SettingsWindowFrame(
            window: CGRect(x: 360, y: 34, width: 723, height: 948), instruction: "Switch it on.")
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(framing: framed, display: display, space: space))
        XCTAssertNil(scene.destination)
        XCTAssertNil(scene.source)
        XCTAssertNil(scene.focus)
        XCTAssertFalse(scene.isDrawable, "nothing was resolved, so nothing is being pointed at")
        XCTAssertEqual(
            scene.dashedRegions, [],
            "the window was dashed as though it were the row — the reported defect")
        XCTAssertNotNil(scene.area, "but it is still the hole the scrim opens, so the pane is lit")
    }

    /// The sentence goes beside the whole gesture. It may sit on neither end of a drag: a plate over
    /// the row hides the thing being dragged, and a plate over the list hides where it goes.
    func testTheDragCaptionSitsBesideTheGestureRatherThanOnEitherEndOfIt() throws {
        let scene = try XCTUnwrap(dragScene())
        guard case .rightOf(let anchor) = scene.captionPlacement else {
            return XCTFail("with a display this wide the sentence belongs beside the pane")
        }
        let destination = try XCTUnwrap(scene.destination)
        XCTAssertGreaterThan(anchor.x, destination.maxX, "clear of the list it is talking about")
    }
}

// MARK: - The hand

final class DragHandPlanTests: XCTestCase {
    private let arrow = ArrowPlan.dragging(
        from: CGRect(x: 611, y: 520, width: 420, height: 32),
        to: CGRect(x: 603, y: 145, width: 460, height: 300))

    private func plan(_ phase: CGFloat) -> DragHandPlan { .at(phase, along: arrow) }

    /// The gesture, in order: on the row with an open hand, closed on it, travelling, arrived, let
    /// go. Asserted as a sequence rather than at one instant, because "it animates" is not the claim
    /// — "it performs the drag" is.
    func testItReachesGraspsTravelsAndReleasesInThatOrder() {
        XCTAssertEqual(plan(0.02).grip, 0, "open, over the row")
        XCTAssertEqual(plan(0.02).position, arrow.tail)

        XCTAssertGreaterThan(plan(0.21).grip, 0, "closing")
        XCTAssertLessThan(plan(0.21).grip, 1)

        XCTAssertEqual(plan(DragHandPlan.grasp).grip, 1, "closed before it moves")
        XCTAssertEqual(plan(DragHandPlan.grasp).position, arrow.tail, "and it has not moved yet")

        XCTAssertEqual(plan(DragHandPlan.arrive).position, arrow.tip, "arrived inside the list")
        XCTAssertEqual(plan(DragHandPlan.arrive).grip, 1, "still holding when it gets there")

        XCTAssertEqual(plan(0.95).grip, 0, "let go")
    }

    /// **It never travels with an open hand.** A hand crossing the pane without gripping is a cursor
    /// moving, which is the one reading this animation cannot afford — the user's failure mode is
    /// clicking the row instead of dragging it.
    func testTheGripIsClosedForEveryInstantTheRowIsCarried() {
        for step in 0...200 {
            let phase = CGFloat(step) / 200
            let hand = plan(phase)
            guard hand.isCarrying else { continue }
            XCTAssertEqual(
                hand.grip, 1, accuracy: 0.001,
                "the hand is carrying the row at phase \(phase) with grip \(hand.grip)")
        }
    }

    /// The hand travels monotonically along the arrow and stays on it — it and the arrow can never
    /// disagree about the path, because there is only one path.
    func testItTravelsForwardsAlongTheArrowAndNeverBacktracks() {
        var previous = plan(0).position.y
        for step in 0...200 {
            let y = plan(CGFloat(step) / 200).position.y
            XCTAssertLessThanOrEqual(y, previous + 0.001, "the hand went back down the pane")
            previous = y
        }
        XCTAssertEqual(plan(1).position, arrow.tip)
    }

    /// The loop has no seam: the hand is invisible at both ends, so it never snaps from the list back
    /// to the row in view. A visible jump every two seconds reads as a rendering fault, which is
    /// worse than no animation.
    func testTheLoopHasNoVisibleSeam() {
        XCTAssertEqual(plan(0).opacity, 0, accuracy: 0.001)
        XCTAssertEqual(plan(1).opacity, 0, accuracy: 0.001)
        XCTAssertGreaterThan(plan(0.5).opacity, 0.9, "and it is solid while it does the work")
    }

    /// Reduce Motion gets the one frame that carries the whole instruction: closed, holding the row,
    /// inside the list. Asserted on the geometry, because freezing at phase 0 would compile, satisfy
    /// "no animation", and leave a hand resting on a row — which is the problem, not the answer.
    func testTheReduceMotionStillFrameShowsTheRowArrivedInsideTheList() {
        let still = plan(CGFloat(SettingsSpotlightCanvas.stillHandPhase))
        XCTAssertEqual(still.grip, 1)
        XCTAssertTrue(still.isCarrying, "a still hand holding nothing shows no gesture")
        XCTAssertGreaterThan(still.opacity, 0.9)
        XCTAssertTrue(
            CGRect(x: 603, y: 145, width: 460, height: 300).contains(still.position),
            "the frozen frame has to show the row where it has to end up")
    }
}

// MARK: - The one colour it draws

/// **INV-UI-1 on the overlay, which is the surface with the most to lose by getting it wrong.**
///
/// This canvas used to be white-only, and the comment saying so was itself the guard. It draws a hue
/// now — the two dashed regions and the arrow — because the pane it lands on contains System
/// Settings' *own* dashed row, and two dashed outlines in the same colour a few inches apart is a
/// worse instruction than either alone.
///
/// A hue on another application's window is exactly where the accent defect would be worst: it is
/// not our window, the user cannot restyle it, and it is drawn during the first ninety seconds of
/// the product. So it is asserted on the **rendered pixel**, through the shared `BrandColour`
/// predicate — never a second copy of the rule — and separately asserted to be the guarded token
/// rather than a blue somebody typed in here.
final class SpotlightBrandTests: XCTestCase {
    private let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)

    @MainActor
    private func drawn(over ground: Color) throws -> NSColor {
        let space = ScreenSpace(displays: [display])
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)
        guard case .pointing(let target) = guidance else {
            throw XCTSkip("the drag scene must resolve for this to mean anything")
        }
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(
                target: target, caption: "Drag it up", display: display, space: space))

        let renderer = ImageRenderer(
            content: ZStack {
                ground
                SettingsSpotlightCanvas(scene: scene, phase: 0.4, handPhase: 0.4)
            }
            .frame(width: 1_512, height: 982))
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.nsImage, "the spotlight did not render")
        return try XCTUnwrap(Self.mostSaturatedPixel(of: image), "the overlay drew no colour at all")
    }

    /// The colour it puts on screen is on brand — over a light pane **and** over a dark one, because
    /// which of the two System Settings is showing is a setting this app does not control.
    @MainActor
    func testTheSpotlightDrawsAnOnBrandColourOverEitherAppearance() throws {
        for (name, ground) in [("a light pane", Color.white), ("a dark pane", Color.black)] {
            assertReadsOnBrand(try drawn(over: ground), "the spotlight's dashed region over \(name)")
        }
    }

    /// And it is **the guarded token**, not a blue chosen here. `Ink.accent` is pinned to
    /// `systemBlue` and asserted by `InkAccentTests` never to be the machine's own accent — which on
    /// a Mac set to Purple would put purple over System Settings' window. A literal in this file
    /// would sit outside that guard entirely.
    ///
    /// Compared by hue within 8°, not by equality: the stroke is composited over a blurred dark
    /// ribbon and SwiftUI blends in linear light, which moves the measured hue a little and is not a
    /// number to pretend away. 8° still separates `systemBlue` from every other hue in the product —
    /// `systemTeal` is 20° off it and `systemIndigo` 28°.
    @MainActor
    func testTheColourIsTheGuardedAccentAndNotALiteral() throws {
        let pixel = try XCTUnwrap(BrandColour.read(try drawn(over: .white)))
        let token = try XCTUnwrap(BrandColour.read(NSColor(Ink.accent)))
        XCTAssertEqual(
            pixel.hue, token.hue, accuracy: 8,
            "the overlay renders at hue \(pixel.hue) where Ink.accent is at \(token.hue) — so the "
                + "guard over the token says nothing about what lands on System Settings' window")
    }

    /// The negative control. A guard that never rejects anything is documentation wearing a test's
    /// clothes — and purple is the specific colour INV-UI-1 exists for.
    func testTheGuardWouldRejectPurple() {
        assertReadsOffBrand(.systemPurple, "the accent macOS ships as Purple")
    }

    private static func mostSaturatedPixel(of image: NSImage) -> NSColor? {
        guard
            let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
            let bitmap = NSBitmapImageRep(cgImage: cgImage).converting(
                to: .sRGB, renderingIntent: .default)
        else { return nil }
        var best: NSColor?
        var bestChroma = 0.0
        // Every fourth pixel: this is a 1512 × 982 frame and the dashes are hundreds of pixels long,
        // so a full sweep costs seconds and finds the same colour.
        for x in stride(from: 0, to: bitmap.pixelsWide, by: 4) {
            for y in stride(from: 0, to: bitmap.pixelsHigh, by: 4) {
                guard let pixel = bitmap.colorAt(x: x, y: y), pixel.alphaComponent > 0.99 else { continue }
                let r = Double(pixel.redComponent)
                let g = Double(pixel.greenComponent)
                let b = Double(pixel.blueComponent)
                let chroma = max(r, max(g, b)) - min(r, min(g, b))
                if chroma > bestChroma {
                    bestChroma = chroma
                    best = pixel
                }
            }
        }
        return best
    }
}
