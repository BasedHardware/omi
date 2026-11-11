import XCTest

@testable import ContextApp

/// The drag recogniser, fed the samples a real trackpad and a real wheel produce.
///
/// This is the file the fix is actually proven in. The timeline beat asked for a two-finger drag and
/// nothing in the app listened for one, so "a natural gesture satisfies it" is a claim about a
/// threshold and a set of accepted event shapes — and there is no trackpad in a test process to
/// check it with. Every case below is a shape the recogniser has to accept or reject *by rule*.
final class TutorialDragTests: XCTestCase {

    /// A trackpad's precise deltas, as `scrollWheel` reports them.
    private func swipe(_ deltaX: Double, deltaY: Double = 0, at: Double) -> TutorialDrag.Sample {
        TutorialDrag.Sample(deltaX: deltaX, deltaY: deltaY, isPrecise: true, at: at)
    }

    /// A notched wheel, whose deltas are counted in lines rather than points.
    private func notch(_ deltaY: Double, at: Double) -> TutorialDrag.Sample {
        TutorialDrag.Sample(deltaX: 0, deltaY: deltaY, isPrecise: false, at: at)
    }

    // MARK: - What has to be accepted

    /// One ordinary flick. A real two-finger swipe arrives as a burst of events a few points each;
    /// this is the shape that used to have nowhere to go.
    func testAnOrdinaryFlickIsRecognised() {
        var drag = TutorialDrag()
        var fired = false
        var at = 100.0
        // Twelve events of −6 points: about 70 points of travel, which is a short flick.
        for _ in 0..<12 {
            at += 0.008
            if drag.received(swipe(-6, at: at)) { fired = true }
        }
        XCTAssertTrue(fired, "a light two-finger flick has to satisfy this beat first time")
    }

    /// Both directions. Which way is "back" depends on the user's own natural-scrolling setting,
    /// which this app does not get to read, so a gate that accepted one sign would refuse half of
    /// everybody for doing exactly what the card asked.
    func testEitherDirectionCounts() {
        for sign in [-1.0, 1.0] {
            var drag = TutorialDrag()
            var fired = false
            var at = 0.0
            for _ in 0..<10 {
                at += 0.01
                if drag.received(swipe(sign * 8, at: at)) { fired = true }
            }
            XCTAssertTrue(fired, "a drag of sign \(sign) is still a drag")
        }
    }

    /// A vertical drag on a horizontal track. The track pans on either axis for exactly this reason
    /// — a mouse with no horizontal wheel would otherwise be unable to move it at all — so the beat
    /// must not be stricter than the control it is teaching.
    func testAVerticalDragCounts() {
        var drag = TutorialDrag()
        var fired = false
        var at = 0.0
        for _ in 0..<10 {
            at += 0.01
            if drag.received(swipe(0, deltaY: -9, at: at)) { fired = true }
        }
        XCTAssertTrue(fired)
    }

    /// Momentum. The tail of a flick arrives with no `phase` set at all, which is precisely why this
    /// recogniser has no phase rule: filtering to `.began`/`.changed` would drop the part of the
    /// gesture the user can still see moving.
    func testTheMomentumTailStillCounts() {
        var drag = TutorialDrag()
        var fired = false
        var at = 0.0
        // A gesture too small on its own, then its momentum.
        for delta in [-4.0, -5.0, -4.0] {
            at += 0.01
            XCTAssertFalse(drag.received(swipe(delta, at: at)))
        }
        for delta in [-9.0, -7.0, -6.0, -5.0, -3.0, -2.0] {
            at += 0.016
            if drag.received(swipe(delta, at: at)) { fired = true }
        }
        XCTAssertTrue(fired, "the momentum tail is part of the same gesture")
    }

    /// A notched wheel. Its deltas are lines, not points: four notches report about four units, and
    /// a threshold measured in points would never see them.
    func testANotchedWheelCounts() {
        var drag = TutorialDrag()
        var fired = false
        var at = 0.0
        for _ in 0..<5 {
            at += 0.1
            if drag.received(notch(-1, at: at)) { fired = true }
        }
        XCTAssertTrue(fired, "a mouse wheel is a legitimate way to move the timeline")
    }

    /// Two separate small flicks, one after the other, add up. Someone who nudges twice has dragged.
    func testTwoSmallFlicksInARowAddUp() {
        var drag = TutorialDrag()
        var fired = false
        for burst in 0..<2 {
            var at = Double(burst) * 0.5
            for _ in 0..<3 {
                at += 0.01
                if drag.received(swipe(-8, at: at)) { fired = true }
            }
        }
        XCTAssertTrue(fired)
    }

    // MARK: - What has to be rejected

    /// A hand resting on the pad. Single-point twitches minutes apart are not a gesture, and the
    /// idle gap is what keeps them from silently accumulating into one.
    func testStrayTwitchesMinutesApartAreNotAGesture() {
        var drag = TutorialDrag()
        var at = 0.0
        for _ in 0..<50 {
            at += 30
            XCTAssertFalse(
                drag.received(swipe(-1, at: at)),
                "an hour of twitches must never add up to a drag")
        }
    }

    /// Zero-delta events — macOS sends them around phase changes — move nothing and must not restart
    /// or advance anything.
    func testEmptyEventsAreIgnored() {
        var drag = TutorialDrag()
        for step in 0..<20 {
            XCTAssertFalse(drag.received(swipe(0, deltaY: 0, at: Double(step))))
        }
        XCTAssertEqual(drag.travelled, 0)
    }

    /// A drag a few points long is not a drag. The threshold is generous, not absent.
    func testATinyNudgeIsNotEnough() {
        var drag = TutorialDrag()
        var at = 0.0
        var travelled = 0.0
        while travelled < TutorialDrag.travelRequired - 6 {
            at += 0.01
            travelled += 5
            XCTAssertFalse(drag.received(swipe(-5, at: at)))
        }
    }

    // MARK: - Firing exactly once

    /// The callback must not fire again on the momentum that follows the event that crossed the bar.
    func testItReportsTheCrossingOnceAndNeverAgain() {
        var drag = TutorialDrag()
        var firings = 0
        var at = 0.0
        for _ in 0..<60 {
            at += 0.01
            if drag.received(swipe(-20, at: at)) { firings += 1 }
        }
        XCTAssertEqual(firings, 1, "a beat that fires twice is a beat that fires on noise")
    }

    func testResetForgetsEverything() {
        var drag = TutorialDrag()
        _ = drag.received(swipe(-30, at: 0))
        XCTAssertEqual(drag.travelled, 30)
        drag.reset()
        XCTAssertEqual(drag.travelled, 0)
        XCTAssertFalse(
            drag.received(swipe(-30, at: 0.01)),
            "travel from before the reset cannot count towards after it")
    }

    // MARK: - The numbers themselves

    /// The threshold is a fraction of a real gesture rather than a fraction of a swipe across the
    /// whole trackpad. If this ever drifts upwards, the beat starts refusing people again.
    func testTheThresholdIsWellInsideOneRealFlick() {
        XCTAssertLessThanOrEqual(
            TutorialDrag.travelRequired, 60,
            "a threshold this high stops being met by a natural gesture")
        XCTAssertGreaterThan(TutorialDrag.travelRequired, 0)
        XCTAssertGreaterThan(TutorialDrag.pointsPerLine, 1, "a wheel line is worth more than a point")
    }
}
