import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The timeline track's zoom: the span bounds, the anchoring rule, and how a trackpad pinch is
/// accumulated across the events of one gesture.
///
/// All of it is arithmetic, and all of it is the kind of arithmetic that is wrong in ways nobody
/// notices from a screenshot — a zoom that drifts a few seconds per step, a bound that leaks, a pinch
/// that squares its own output because the value it multiplies came back through the model. So the
/// pure parts are checked exactly, and the two paths that reach them — the magnifier buttons and the
/// gesture — are checked against a real `RewindModel` to prove they land on the *same* window rather
/// than on two windows that happen to look alike.
final class RewindZoomTests: XCTestCase {

    // MARK: - The window arithmetic

    /// The promise the whole feature rests on: the moment under the pointer does not move.
    ///
    /// Checked across a range of fractions and over repeated zooms, because the failure this guards is
    /// cumulative — an anchoring rule that is right to within a rounding error still walks the track
    /// out from under the user after six presses of a button.
    func testTheAnchoredMomentKeepsItsPlaceOnTheTrack() {
        let day = 0.0...86_400
        let bounds = RewindZoom.minimumSpan...RewindZoom.maximumSpan
        let anchor = 43_200.0  // Midday, far enough from both edges that no clamp can be involved.

        for fraction in [0.0, 0.25, 0.5, 0.75, 1.0] {
            var span = 21_600.0
            for step in 0..<6 {
                let window = RewindZoom.window(
                    for: RewindZoom.Target(span: span, anchor: anchor, fraction: fraction),
                    spanBounds: bounds,
                    within: day)

                XCTAssertEqual(
                    window.start + fraction * window.span, anchor, accuracy: 0.001,
                    "the anchor drifted at fraction \(fraction), step \(step)")
                XCTAssertEqual(
                    RewindZoom.fraction(of: anchor, in: window), fraction, accuracy: 0.000_001,
                    "…and it must still read back as sitting in the same place")
                span /= 2
            }
        }
    }

    /// Both bounds, and the fact that the loaded day outranks the constant ceiling.
    func testTheSpanClampsAtBothEndsAndTheDayOverridesBoth() {
        let day = 0.0...86_400
        let bounds = RewindZoom.minimumSpan...RewindZoom.maximumSpan
        func span(_ requested: Double, within window: ClosedRange<Double> = 0.0...86_400) -> Double {
            RewindZoom.window(
                for: RewindZoom.Target(span: requested, anchor: 43_200, fraction: 0.5),
                spanBounds: bounds,
                within: window
            ).span
        }

        XCTAssertEqual(span(6 * 3600), 6 * 3600, accuracy: 0.001, "an in-range request is honoured")

        // The floor. Zero and a negative are included because a bad caller is likelier than a bad
        // trackpad, and the arithmetic downstream divides by this.
        XCTAssertEqual(span(1), RewindZoom.minimumSpan, accuracy: 0.001)
        XCTAssertEqual(span(0), RewindZoom.minimumSpan, accuracy: 0.001)
        XCTAssertEqual(span(-5_000), RewindZoom.minimumSpan, accuracy: 0.001)

        // The ceiling.
        XCTAssertEqual(span(10 * 86_400), RewindZoom.maximumSpan, accuracy: 0.001)

        // …and the day beats the ceiling. A 23-hour day is not hypothetical: it is what the clocks
        // going forward produces, and the track must not offer the hour that does not exist.
        XCTAssertEqual(span(86_400, within: 0.0...(23 * 3600)), 23 * 3600, accuracy: 0.001)
    }

    /// At the edges of the day the anchor cannot stay under the pointer, and the window slides instead
    /// of showing time the day does not contain. The moment still ends up visible, which is the part
    /// that makes sliding acceptable rather than merely convenient.
    func testTheWindowNeverLeavesTheLoadedDay() {
        let day = 0.0...86_400
        let bounds = RewindZoom.minimumSpan...RewindZoom.maximumSpan

        let early = RewindZoom.window(
            for: RewindZoom.Target(span: 3_600, anchor: 60, fraction: 0.9),
            spanBounds: bounds, within: day)
        XCTAssertEqual(early.start, 0, accuracy: 0.001, "there is no time before midnight to show")
        XCTAssertEqual(early.span, 3_600, accuracy: 0.001, "sliding, not shrinking")
        XCTAssertTrue((early.start...early.end).contains(60))

        let late = RewindZoom.window(
            for: RewindZoom.Target(span: 3_600, anchor: 86_340, fraction: 0.1),
            spanBounds: bounds, within: day)
        XCTAssertEqual(late.end, 86_400, accuracy: 0.001)
        XCTAssertEqual(late.span, 3_600, accuracy: 0.001)
        XCTAssertTrue((late.start...late.end).contains(86_340))
    }

    func testFractionIsWhereOnTheTrackAMomentSitsAndIsClampedToIt() {
        let window = RewindZoom.Window(start: 1_000, span: 200)

        XCTAssertEqual(RewindZoom.fraction(of: 1_000, in: window), 0, accuracy: 0.000_1)
        XCTAssertEqual(RewindZoom.fraction(of: 1_100, in: window), 0.5, accuracy: 0.000_1)
        XCTAssertEqual(RewindZoom.fraction(of: 1_200, in: window), 1, accuracy: 0.000_1)

        // Off the track entirely. Clamped rather than reported, because a fraction of 40 fed back into
        // `window(for:…)` would place the window thirty-nine track-widths from the moment it names.
        XCTAssertEqual(RewindZoom.fraction(of: 9_000, in: window), 1, accuracy: 0.000_1)
        XCTAssertEqual(RewindZoom.fraction(of: -9_000, in: window), 0, accuracy: 0.000_1)
        // A track showing no time at all has no position to report; the middle is the honest default.
        XCTAssertEqual(
            RewindZoom.fraction(of: 1_100, in: RewindZoom.Window(start: 1_100, span: 0)), 0.5)
    }

    // MARK: - The pinch accumulator

    /// One gesture's deltas compound. Pinned exactly, because both ways of getting this wrong produce
    /// a control that still moves — it just moves by the wrong amount, which is invisible until
    /// somebody compares it to another app.
    func testOnePinchCompoundsItsDeltasRatherThanReadingEachAsTheWholeGesture() {
        var pinch = RewindPinch(
            anchor: 43_200, fraction: 0.5, startSpan: 8 * 3600,
            spanBounds: RewindZoom.minimumSpan...RewindZoom.maximumSpan)

        var target = pinch.target
        for _ in 0..<10 { target = pinch.advance(by: 0.05) }

        XCTAssertEqual(pinch.magnification, pow(1.05, 10), accuracy: 0.000_001)
        XCTAssertEqual(target.span, 8 * 3600 / pow(1.05, 10), accuracy: 0.001)
        // The delta read as if it were the gesture's total scale: the zoom would barely move.
        XCTAssertNotEqual(target.span, 8 * 3600 / 1.05, accuracy: 60)

        // The anchor and its place on the track are the gesture's, not the current event's — a
        // trackpad reports a moving pointer during a pinch and the moment being zoomed on must not
        // wander with it.
        XCTAssertEqual(target.anchor, 43_200)
        XCTAssertEqual(target.fraction, 0.5)
    }

    /// Spread and close back again and you are on the span you started on — exactly, not nearly. This
    /// is the property that would fail if the gesture multiplied a running value instead of scaling a
    /// captured one.
    func testAPinchThatReversesLandsBackOnTheSpanItStartedFrom() {
        let start = 4 * 3600.0
        var pinch = RewindPinch(
            anchor: 43_200, fraction: 0.5, startSpan: start,
            spanBounds: RewindZoom.minimumSpan...RewindZoom.maximumSpan)

        for _ in 0..<5 { _ = pinch.advance(by: 0.2) }
        XCTAssertLessThan(pinch.target.span, start, "spreading the fingers zooms in")

        // The exact inverse of a 1.2 step.
        for _ in 0..<5 { _ = pinch.advance(by: 1 / 1.2 - 1) }
        XCTAssertEqual(pinch.target.span, start, accuracy: 0.000_1)
    }

    /// The bound holds, and — the part that is easy to get wrong — the first reversed event moves the
    /// track again.
    ///
    /// Clamping the span the gesture *produces* instead of the magnification it accumulates passes the
    /// first half of this and fails the second: the overshoot is remembered, so a user who keeps
    /// pinching after the track has bottomed out has to pay every bit of it back before anything
    /// happens, and the control reads as broken rather than as bounded.
    func testThePinchStopsAtBothBoundsAndAnswersTheFirstReversal() {
        let bounds = RewindZoom.minimumSpan...(24 * 3600.0)
        var pinch = RewindPinch(
            anchor: 43_200, fraction: 0.5, startSpan: 4 * 3600, spanBounds: bounds)

        // Far past the floor: sixty 20% steps is a magnification of ~56,000 where 120 would do.
        for _ in 0..<60 { _ = pinch.advance(by: 0.2) }
        XCTAssertEqual(pinch.target.span, bounds.lowerBound, accuracy: 0.000_1)

        let reversed = pinch.advance(by: -0.2).span
        XCTAssertGreaterThan(reversed, bounds.lowerBound, "the floor must not ratchet")
        XCTAssertEqual(reversed, bounds.lowerBound / 0.8, accuracy: 0.000_1)

        // The same at the ceiling, from the other direction.
        for _ in 0..<60 { _ = pinch.advance(by: -0.2) }
        XCTAssertEqual(pinch.target.span, bounds.upperBound, accuracy: 0.000_1)
        XCTAssertLessThan(pinch.advance(by: 0.2).span, bounds.upperBound, "nor the ceiling")
    }

    /// A single absurd event cannot strand the gesture. `NSEvent.magnification` is a `CGFloat` and
    /// nothing in its type stops it being −1, which would multiply the accumulator by zero.
    func testAnAbsurdDeltaCannotCollapseTheGesture() {
        var pinch = RewindPinch(
            anchor: 0, fraction: 0.5, startSpan: 3_600,
            spanBounds: RewindZoom.minimumSpan...RewindZoom.maximumSpan)

        let after = pinch.advance(by: -50).span
        XCTAssertTrue(after.isFinite)
        XCTAssertLessThanOrEqual(after, RewindZoom.maximumSpan)
        XCTAssertGreaterThan(pinch.magnification, 0)
        // …and the gesture still answers the next event.
        XCTAssertLessThan(pinch.advance(by: 0.2).span, after)
    }

    // MARK: - The gesture, through the view that receives it

    /// The pointer is the anchor. Driven through `handleMagnification`, which is everything
    /// `magnify(with:)` does after unpacking the event — an `NSEvent` of a gesture type cannot be
    /// constructed outside the window server, so this is the closest seam to the real one.
    @MainActor
    func testPinchingOverTheTrackZoomsAboutThePointerRatherThanTheTrackCentre() throws {
        let view = RewindTrackView(
            frame: NSRect(x: 0, y: 0, width: 1_000, height: RewindTrackView.height))
        view.apply(
            blocks: [], frames: [], trackStart: 0, trackSpan: 3_600, playheadAt: nil,
            spanBounds: RewindZoom.minimumSpan...RewindZoom.maximumSpan)

        var targets: [RewindZoom.Target] = []
        view.onZoom = { targets.append($0) }

        // A quarter of the way along an hour-wide track is fifteen minutes in.
        view.handleMagnification(0.1, phase: .began, atX: 250)
        view.handleMagnification(0.1, phase: .changed, atX: 250)

        XCTAssertEqual(targets.count, 2)
        let last = try XCTUnwrap(targets.last)
        XCTAssertEqual(last.anchor, 900, accuracy: 0.000_1)
        XCTAssertEqual(last.fraction, 0.25, accuracy: 0.000_1)
        XCTAssertEqual(last.span, 3_600 / (1.1 * 1.1), accuracy: 0.001)
    }

    /// **The gesture must not read its own output back.**
    ///
    /// Applying a zoom publishes a new span on the model, which returns through `updateNSView` and
    /// overwrites the view's `trackSpan` in the middle of the gesture. A pinch that scaled *that*
    /// value on the next event would be squaring itself every frame — a gentle spread would slam the
    /// track to its floor. Holding the span captured at `.began` is what prevents it, and ending the
    /// gesture is what lets the next one start from where the track now actually is.
    @MainActor
    func testTheGestureIgnoresTheModelsEchoAndTheNextOneStartsWhereTheTrackNowIs() throws {
        let view = RewindTrackView(
            frame: NSRect(x: 0, y: 0, width: 1_000, height: RewindTrackView.height))
        func show(_ span: Double) {
            view.apply(
                blocks: [], frames: [], trackStart: 0, trackSpan: span, playheadAt: nil,
                spanBounds: RewindZoom.minimumSpan...RewindZoom.maximumSpan)
        }
        var last: RewindZoom.Target?
        view.onZoom = { last = $0 }

        show(3_600)
        view.handleMagnification(0.5, phase: .began, atX: 0)
        // What SwiftUI does next, simulated exactly: the new span comes straight back down.
        show(try XCTUnwrap(last).span)
        view.handleMagnification(0.5, phase: .changed, atX: 0)

        XCTAssertEqual(
            try XCTUnwrap(last).span, 3_600 / (1.5 * 1.5), accuracy: 0.001,
            "two 1.5× events are 2.25×, not 3.375×")

        // Lift the fingers, then pinch again: the second gesture scales what is on screen now.
        show(try XCTUnwrap(last).span)
        view.handleMagnification(0, phase: .ended, atX: 0)
        view.handleMagnification(0.5, phase: .began, atX: 0)
        XCTAssertEqual(
            try XCTUnwrap(last).span, 3_600 / (1.5 * 1.5) / 1.5, accuracy: 0.001,
            "a new gesture must not replay the previous one's magnification")
    }

    // MARK: - The two drivers, against a real model

    /// A day of capture in a real store, and a `RewindModel` loaded on it.
    private struct Loaded {
        let model: RewindModel
        let dayStart: Double
        let dayEnd: Double
        var dayLength: Double { dayEnd - dayStart }
    }

    private var temporaryRoots: [URL] = []

    override func tearDownWithError() throws {
        for root in temporaryRoots { try? FileManager.default.removeItem(at: root) }
        temporaryRoots.removeAll()
    }

    /// A real `ContextStore` rather than an injected array, because `RewindModel` has no seam for one
    /// — and because the day bounds every clamp below is stated against come from `Calendar.current`,
    /// so they are whatever the machine running this thinks a day is. Nothing here depends on the
    /// wall clock: the day is a fixed instant, and its length is measured rather than assumed.
    @MainActor
    private func loadedModel(frameSpacing: Double = 600) async throws -> Loaded {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-zoom-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        temporaryRoots.append(root)

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        let day = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: 1_760_000_000))
        let dayStart = day.timeIntervalSince1970
        // The same half-open end `RewindModel.dayBounds` uses, so the bounds under test are the
        // bounds the app has.
        let dayEnd =
            (Calendar.current.date(byAdding: .day, value: 1, to: day)?.timeIntervalSince1970
            ?? dayStart + 86_400) - 0.001

        var at = dayStart + frameSpacing
        while at < dayEnd {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: at, appName: "Cursor", windowTitle: "context.db",
                    imagePath: "/tmp/rewind-zoom-frame.heic"))
            at += frameSpacing
        }

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        XCTAssertFalse(model.frames.isEmpty, "the fixture did not load")
        return Loaded(model: model, dayStart: dayStart, dayEnd: dayEnd)
    }

    /// **The buttons and the gesture are one feature.** Same halving, expressed each way, landing on
    /// the same window down to the last fraction of a second — because both go through
    /// `setTrackWindow` and neither owns any arithmetic of its own.
    @MainActor
    func testTheMagnifierButtonsAndAPinchLandOnExactlyTheSameWindow() async throws {
        let byButton = try await loadedModel()
        let byPinch = try await loadedModel()

        let anchor = try XCTUnwrap(byButton.model.currentFrame?.capturedAt)
        let before = byButton.model.trackWindow
        let fraction = RewindZoom.fraction(of: anchor, in: before)

        byButton.model.zoomTrack(in: true)

        var gesture = RewindPinch(
            anchor: anchor, fraction: fraction, startSpan: before.span,
            spanBounds: byPinch.model.trackSpanBounds)
        // A magnification delta of 1 is a 2× spread, which halves the span — the button's step.
        byPinch.model.setTrackWindow(gesture.advance(by: 1))

        XCTAssertEqual(byPinch.model.trackSpan, byButton.model.trackSpan, accuracy: 0.000_1)
        XCTAssertEqual(byPinch.model.trackStart, byButton.model.trackStart, accuracy: 0.000_1)
        XCTAssertLessThan(byButton.model.trackSpan, before.span)
    }

    /// The bounds hold through the model, where the ceiling is the loaded day rather than the
    /// constant — and the buttons report the state they are actually in.
    @MainActor
    func testZoomingRepeatedlyStopsAtBothBoundsThroughTheModel() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model

        XCTAssertFalse(model.canZoomTrackOut, "the window opens showing the whole day")

        for _ in 0..<20 { model.zoomTrack(in: true) }
        XCTAssertEqual(model.trackSpan, RewindZoom.minimumSpan, accuracy: 0.000_1)
        XCTAssertFalse(model.canZoomTrackIn)

        // The floor is a floor, not a slow leak: one more press changes nothing at all.
        let atFloor = model.trackWindow
        model.zoomTrack(in: true)
        XCTAssertEqual(model.trackSpan, atFloor.span, accuracy: 0.000_1)
        XCTAssertEqual(model.trackStart, atFloor.start, accuracy: 0.000_1)

        for _ in 0..<20 { model.zoomTrack(in: false) }
        XCTAssertEqual(model.trackSpan, loaded.dayLength, accuracy: 0.000_1)
        XCTAssertEqual(model.trackStart, loaded.dayStart, accuracy: 0.000_1)
        XCTAssertFalse(model.canZoomTrackOut)
    }

    /// **Zoom composes with scrolling instead of fighting it.**
    ///
    /// Scrolling the track moves the playhead and the window follows the playhead. So a pinch that
    /// zoomed into the morning while the picture was still showing the evening would be undone by the
    /// very next scroll — the window would snap back across twelve hours and the stretch the user was
    /// looking at would be gone. The playhead comes along instead.
    @MainActor
    func testPinchingSomewhereElseTakesThePlayheadWithItSoTheNextScrollStaysThere() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model

        let opened = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertGreaterThan(
            opened, loaded.dayStart + 20 * 3600, "the window opens on the newest frame of the day")

        // Pinch hard on mid-morning, half a day away from the picture on screen.
        let anchor = loaded.dayStart + 10 * 3600
        model.setTrackWindow(RewindZoom.Target(span: 1_800, anchor: anchor, fraction: 0.5))

        let landed = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertEqual(landed, anchor, accuracy: 600, "the playhead follows the pinch to its anchor")
        XCTAssertTrue((model.trackStart...model.trackEnd).contains(landed))

        // …and the next scroll travels from there, leaving the zoom where the fingers put it.
        let held = model.trackWindow
        model.travel(by: 600)
        XCTAssertGreaterThan(try XCTUnwrap(model.currentFrame?.capturedAt), landed)
        XCTAssertEqual(model.trackSpan, held.span, accuracy: 0.000_1)
        XCTAssertEqual(model.trackStart, held.start, accuracy: 0.000_1)
        XCTAssertLessThan(
            model.trackStart, loaded.dayStart + 12 * 3600,
            "the window must not have snapped back to where the playhead used to be")
    }
}
