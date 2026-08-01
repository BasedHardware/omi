import AppKit
import XCTest

@testable import ContextApp

/// **The card is always wholly on screen, whatever height it grows to.**
///
/// Observed live: the permissions card sat partly below the bottom edge of the display with the
/// "I'll do this later" button cut off. That button is the *only* escape from a permission the user
/// does not want to grant — `PermissionGate` has no timeout and no default answer by design — so
/// clipping it strands the run on a card with no way forward.
///
/// The cause was arithmetic that was safe until it was not. `centredFrame` centred the window in
/// `visibleFrame` and then added an unconditional optical nudge of `visible.height * 0.05`, with no
/// clamp anywhere. That needs the usable area to be at least `windowHeight / 0.9` tall. At the old
/// 520 pt card that was 702 pt and every Mac cleared it; the card then grew to 640 to stop the
/// permissions copy truncating, which took the requirement to 836 pt — more than a 13-inch display
/// with a Dock actually has.
///
/// So the property under test is not "640 fits". It is **"any height is clamped"**, swept over the
/// displays this app could plausibly open on, because the next card that grows must not be able to
/// reintroduce this. A test pinned to the current constant would have passed before the growth and
/// after it.
/// `@MainActor` only because `OnboardingWindow.windowSize` is: the placement itself is
/// `nonisolated` and is a pure function of its two arguments, which is the point of it.
@MainActor
final class OnboardingWindowPlacementTests: XCTestCase {

    /// Usable areas, not display sizes: `visibleFrame` is already the display less the menu bar and
    /// less the Dock wherever the user keeps it, which is the only rect the placement may use.
    ///
    /// The origins are deliberately non-zero in several of these. A card placed correctly on the
    /// primary display and wrongly on a second one is the classic version of this bug, and it is
    /// invisible on a one-monitor machine.
    private static let usableAreas: [(name: String, rect: NSRect)] = [
        ("16-inch, bottom Dock", NSRect(x: 0, y: 79, width: 1_728, height: 995)),
        ("14-inch, bottom Dock", NSRect(x: 0, y: 79, width: 1_512, height: 865)),
        ("13-inch Air, bottom Dock", NSRect(x: 0, y: 79, width: 1_470, height: 839)),
        ("13-inch scaled to Larger Text", NSRect(x: 0, y: 74, width: 1_280, height: 720)),
        ("13-inch scaled small, big Dock", NSRect(x: 0, y: 96, width: 1_152, height: 586)),
        ("1080p external", NSRect(x: 0, y: 79, width: 1_920, height: 977)),
        ("left Dock", NSRect(x: 88, y: 0, width: 1_424, height: 957)),
        ("second display, above the primary", NSRect(x: 1_512, y: 982, width: 1_920, height: 1_055)),
        ("second display, negative origin", NSRect(x: -1_920, y: -300, width: 1_920, height: 1_055)),
        ("an iPad sidecar in portrait", NSRect(x: 0, y: 25, width: 834, height: 1_060)),
    ]

    /// Every height the card has been, plus the ones it could plausibly become, plus two that are
    /// frankly absurd — the absurd ones are what prove the clamp is a clamp rather than a bigger
    /// constant.
    private static let cardHeights: [CGFloat] = [420, 520, 600, 640, 700, 780, 900, 1_100, 1_600]

    /// **The property.** For every usable area and every card height, the frame is inside the usable
    /// area — unless the card is genuinely bigger than the area, in which case it is pinned to the
    /// top-left and its overflow is only ever off the bottom or the right.
    func testACardOfAnyHeightIsPlacedWhollyInsideTheUsableArea() {
        for (name, visible) in Self.usableAreas {
            for height in Self.cardHeights {
                let size = NSSize(width: OnboardingWindow.cardSize.width + 112, height: height + 112)
                let frame = OnboardingWindow.placement(of: size, in: visible)

                XCTAssertEqual(frame.size, size, "\(name) at \(height): the card is never resized")

                if size.height <= visible.height {
                    XCTAssertGreaterThanOrEqual(
                        frame.minY, visible.minY - 0.5,
                        "\(name) at \(height): the card hangs off the bottom of the screen, which is "
                            + "where the \"I'll do this later\" button lives")
                    XCTAssertLessThanOrEqual(
                        frame.maxY, visible.maxY + 0.5,
                        "\(name) at \(height): the card runs under the menu bar")
                } else {
                    XCTAssertEqual(
                        frame.maxY, visible.maxY, accuracy: 0.5,
                        "\(name) at \(height): a card taller than the screen keeps its head — losing "
                            + "the headline means the user cannot tell what they are looking at")
                }

                if size.width <= visible.width {
                    XCTAssertGreaterThanOrEqual(frame.minX, visible.minX - 0.5, "\(name) at \(height)")
                    XCTAssertLessThanOrEqual(frame.maxX, visible.maxX + 0.5, "\(name) at \(height)")
                } else {
                    XCTAssertEqual(frame.minX, visible.minX, accuracy: 0.5, "\(name) at \(height)")
                }
            }
        }
    }

    /// **The regression, named: a card of any height is clamped fully on screen at every yield
    /// position.**
    ///
    /// This is the assertion that fails on the code that shipped, and it is stated over *positions*
    /// rather than over one frame because placing the card correctly once is not what was missing —
    /// re-checking it ever was. The window is `isMovableByWindowBackground` and borderless, so AppKit
    /// never constrains it; `visibleFrame` changes under it while it is faded out mid-yield. Nothing
    /// brought it back, so whatever position it had when it yielded is the position it returned to.
    func testACardOfAnyHeightIsReclaimedFromEveryYieldPosition() {
        let visible = NSRect(x: 0, y: 79, width: 1_512, height: 865)
        for height in Self.cardHeights {
            let size = NSSize(width: OnboardingWindow.cardSize.width + 112, height: height + 112)
            guard size.height <= visible.height, size.width <= visible.width else { continue }

            // Every way a card ends up somewhere it should not be: dragged off each edge, off a
            // corner, and left entirely on a display that is no longer there.
            let strays: [(String, NSPoint)] = [
                ("off the bottom", NSPoint(x: 300, y: visible.minY - 120)),
                ("just off the bottom, clipping the escape button", NSPoint(x: 300, y: visible.minY - 12)),
                ("off the top, under the menu bar", NSPoint(x: 300, y: visible.maxY - size.height + 90)),
                ("off the left", NSPoint(x: visible.minX - 200, y: 300)),
                ("off the right", NSPoint(x: visible.maxX - size.width + 200, y: 300)),
                ("off the bottom-right corner", NSPoint(x: visible.maxX - 40, y: visible.minY - 300)),
                ("on a display that has gone", NSPoint(x: -3_000, y: -3_000)),
            ]
            for (where_, origin) in strays {
                let reclaimed = OnboardingWindow.reclaimed(
                    NSRect(origin: origin, size: size), into: visible)
                XCTAssertTrue(
                    visible.contains(reclaimed),
                    "at \(height) pt, \(where_): the card came back at \(reclaimed), which is not "
                        + "inside the usable area \(visible) — the \"I'll do this later\" button is "
                        + "the only escape from an unanswered permission and it is off screen")
            }
        }
    }

    /// And a card the user put somewhere deliberately is left alone. A reclaim that recentred on
    /// every yield would fight the person using it, three times per permission run.
    func testACardAlreadyOnScreenIsNotMoved() {
        let visible = NSRect(x: 0, y: 79, width: 1_512, height: 865)
        let moved = NSRect(x: 120, y: 120, width: 832, height: 752)
        XCTAssertEqual(OnboardingWindow.reclaimed(moved, into: visible), moved)
    }

    /// The optical nudge still happens where there is room for it — the fix is a clamp, not a
    /// removal. Optical centre reads as centred where geometric centre reads as low, and a card that
    /// suddenly sat 40 pt lower on every Mac would be a second defect shipped to fix the first.
    func testTheOpticalNudgeSurvivesWhereThereIsRoomForIt() {
        let roomy = NSRect(x: 0, y: 79, width: 1_728, height: 995)
        let frame = OnboardingWindow.placement(of: OnboardingWindow.windowSize, in: roomy)
        XCTAssertGreaterThan(
            frame.midY, roomy.midY,
            "with room to spare the card still sits above true centre")
        XCTAssertEqual(frame.midX, roomy.midX, accuracy: 0.5, "and stays horizontally centred")
    }

    /// The card is placed against the *usable* area, so a Dock on the left moves it right. Measuring
    /// against `screen.frame` instead would put it half under the Dock and pass every centring test.
    func testItFollowsTheUsableAreaRatherThanTheDisplay() {
        let leftDock = NSRect(x: 88, y: 0, width: 1_424, height: 957)
        let frame = OnboardingWindow.placement(of: OnboardingWindow.windowSize, in: leftDock)
        XCTAssertGreaterThanOrEqual(frame.minX, leftDock.minX)
        XCTAssertEqual(frame.midX, leftDock.midX, accuracy: 0.5)
    }
}
