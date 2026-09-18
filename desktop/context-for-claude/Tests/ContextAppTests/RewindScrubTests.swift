import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// **Scrubbing as motion rather than as a slideshow.**
///
/// The complaint this file exists for was that the timeline "does not feel like rewinding through a
/// video — it feels like screenshots", and the cause was one fact with three faces: the playhead was
/// an *index* into the frame array, so no position existed between two captures. There was nothing
/// for a dissolve to be a fraction of, the handle jumped in three-second quanta, and a scroll delta
/// smaller than half a capture interval rounded back to where it started and was thrown away.
///
/// Everything asserted here is decidable without a screen, which is the point: the blend weight, the
/// prefetch window, the cache bound and the settle are arithmetic, and arithmetic that is wrong by a
/// few percent produces a control that still *works* — it just feels wrong, which is invisible in a
/// screenshot and impossible to argue about after the fact.
final class RewindScrubTests: XCTestCase {

    private static let base: Double = 1_760_000_000

    /// Captures at the real 3 s tick unless a test is about a gap.
    private static func captures(_ count: Int, spacing: Double = 3, from start: Double = base)
        -> [RewindFrame]
    {
        (0..<count).map {
            RewindFrame(
                id: Int64($0), capturedAt: start + Double($0) * spacing, appName: "Cursor",
                imagePath: "/tmp/rewind-scrub-\($0).heic")
        }
    }

    // MARK: - Where the playhead is between two captures

    /// The resting state, and the one the settle guarantees: a real photograph at full weight.
    func testAPlayheadOnACaptureShowsThatCaptureAloneAtFullWeight() throws {
        let frames = Self.captures(5)

        for index in frames.indices {
            let blend = try XCTUnwrap(RewindScrub.blend(at: frames[index].capturedAt, in: frames))
            XCTAssertEqual(blend.dominant, index)
            XCTAssertEqual(
                blend.weight, 0, accuracy: 0.000_001,
                "a playhead parked on capture \(index) is showing part of another one")
        }
    }

    /// …and the defined midpoint. Half of each, which is the only weight that is not a preference.
    func testMidwayBetweenTwoCapturesIsAnEvenBlendOfBoth() throws {
        let frames = Self.captures(5)
        let middle = (frames[1].capturedAt + frames[2].capturedAt) / 2

        let blend = try XCTUnwrap(RewindScrub.blend(at: middle, in: frames))

        XCTAssertEqual(blend.base, 1)
        XCTAssertEqual(blend.next, 2)
        XCTAssertEqual(blend.weight, 0.5, accuracy: 0.000_001)
        // The tie goes to the earlier capture, exactly as `nearestIndex(to:)` breaks it. If these two
        // rules ever disagree, the picture on the stage and the clock above it name different
        // moments — for one frame of animation, on every scrub, which reads as the label flickering.
        XCTAssertEqual(blend.dominant, frames.nearestIndex(to: middle))
    }

    /// **The dissolve is a transition, not a state.**
    ///
    /// It holds each capture at full weight for the first and last third of the interval. Without the
    /// plateau, a playhead resting anywhere but exactly on a capture would show a permanent double
    /// exposure of two different screens — a picture that never existed, held as steadily as one that
    /// did, which is a worse answer than the hard cut this replaces.
    func testTheDissolveHoldsEachCaptureBeforeItStartsAndAfterItFinishes() {
        XCTAssertEqual(RewindScrub.ramp(0), 0, accuracy: 0.000_001)
        XCTAssertEqual(RewindScrub.ramp(RewindScrub.blendStart), 0, accuracy: 0.000_001)
        XCTAssertEqual(RewindScrub.ramp(RewindScrub.blendEnd), 1, accuracy: 0.000_001)
        XCTAssertEqual(RewindScrub.ramp(1), 1, accuracy: 0.000_001)
        XCTAssertEqual(RewindScrub.ramp(0.5), 0.5, accuracy: 0.000_001)

        // Strictly increasing in between, and never outside 0…1 anywhere — a weight that overshot
        // would drive an opacity SwiftUI clamps silently, hiding the error.
        var previous = -1.0
        for step in 0...200 {
            let weight = RewindScrub.ramp(Double(step) / 200)
            XCTAssertGreaterThanOrEqual(weight, 0)
            XCTAssertLessThanOrEqual(weight, 1)
            XCTAssertGreaterThanOrEqual(weight, previous, "the dissolve went backwards")
            previous = weight
        }

        // Eased rather than linear at the ends, which is what stops the fade being visible *as a
        // switch*: the eye catches a discontinuity in the rate long before one in the opacity.
        let justInside = RewindScrub.ramp(RewindScrub.blendStart + 0.01)
        let linear = 0.01 / (RewindScrub.blendEnd - RewindScrub.blendStart)
        XCTAssertLessThan(justInside, linear, "a straight ramp starts with a corner")
    }

    /// The picture and the timestamp above it must never name different captures. Swept rather than
    /// spot-checked, because the two rules are stated in different files.
    func testTheDominantCaptureIsAlwaysTheNearestOne() throws {
        let frames = Self.captures(12)
        let span = frames[frames.count - 1].capturedAt - frames[0].capturedAt

        for step in 0...400 {
            let instant = frames[0].capturedAt + span * Double(step) / 400
            let blend = try XCTUnwrap(RewindScrub.blend(at: instant, in: frames))
            XCTAssertEqual(
                blend.dominant, frames.nearestIndex(to: instant),
                "at \(instant - frames[0].capturedAt)s the blend and the nearest-capture rule disagree")
        }
    }

    /// **A real gap in the capture cuts; it does not fade.**
    ///
    /// Fading a screen from before lunch into one from after it would narrate a continuity that never
    /// happened — the honest rendering of an hour nobody recorded is a cut. One dropped capture is
    /// still adjacent, though, and must keep dissolving.
    func testAGapTooWideToBeAdjacentCutsInsteadOfFading() throws {
        let apart = [
            RewindFrame(id: 1, capturedAt: Self.base, appName: "Cursor", imagePath: "/tmp/a.heic"),
            RewindFrame(
                id: 2, capturedAt: Self.base + 3_600, appName: "Arc", imagePath: "/tmp/b.heic"),
        ]

        let early = try XCTUnwrap(RewindScrub.blend(at: Self.base + 600, in: apart))
        XCTAssertNil(early.next, "an hour of nothing is not a dissolve")
        XCTAssertEqual(early.weight, 0)
        XCTAssertEqual(early.dominant, 0)

        // …and it switches at the midpoint, where the nearest-capture rule switches too.
        let late = try XCTUnwrap(RewindScrub.blend(at: Self.base + 3_000, in: apart))
        XCTAssertEqual(late.dominant, 1)
        XCTAssertEqual(late.dominant, apart.nearestIndex(to: Self.base + 3_000))

        // One dropped capture — 6 s at the 3 s tick — is still two neighbours.
        let dropped = Self.captures(3, spacing: 6)
        let blend = try XCTUnwrap(
            RewindScrub.blend(at: dropped[0].capturedAt + 3, in: dropped))
        XCTAssertEqual(blend.next, 1)
        XCTAssertEqual(blend.weight, 0.5, accuracy: 0.000_001)

        // The boundary itself, pinned from both sides so the constant cannot drift unnoticed.
        let atLimit = Self.captures(2, spacing: RewindScrub.maximumBlendGap)
        XCTAssertNotNil(
            try XCTUnwrap(
                RewindScrub.blend(
                    at: atLimit[0].capturedAt + RewindScrub.maximumBlendGap / 2, in: atLimit)
            ).next)
        let pastLimit = Self.captures(2, spacing: RewindScrub.maximumBlendGap + 0.5)
        XCTAssertNil(
            try XCTUnwrap(
                RewindScrub.blend(
                    at: pastLimit[0].capturedAt + RewindScrub.maximumBlendGap / 2, in: pastLimit)
            ).next)
    }

    /// Outside the captured range there is nothing to be between, and nothing is extrapolated.
    func testOutsideTheCapturedRangeThePlayheadClampsToARealCapture() throws {
        let frames = Self.captures(4)

        let before = try XCTUnwrap(RewindScrub.blend(at: Self.base - 9_999, in: frames))
        XCTAssertEqual(before.dominant, 0)
        XCTAssertNil(before.next)
        XCTAssertEqual(before.weight, 0)

        let after = try XCTUnwrap(RewindScrub.blend(at: Self.base + 9_999, in: frames))
        XCTAssertEqual(after.dominant, frames.count - 1)
        XCTAssertNil(after.next)
        XCTAssertEqual(after.weight, 0)

        XCTAssertNil(RewindScrub.blend(at: Self.base, in: []), "a day with nothing showable")
    }

    /// Two rows stamped at the same instant is a clock fault, not an interval, and the fraction it
    /// implies divides by zero. Real capture directories contain them.
    func testDuplicateCaptureTimestampsStillProduceAWeightInRange() throws {
        let frames = [
            RewindFrame(id: 1, capturedAt: Self.base, appName: "A", imagePath: "/tmp/a.heic"),
            RewindFrame(id: 2, capturedAt: Self.base + 3, appName: "B", imagePath: "/tmp/b.heic"),
            RewindFrame(id: 3, capturedAt: Self.base + 3, appName: "C", imagePath: "/tmp/c.heic"),
            RewindFrame(id: 4, capturedAt: Self.base + 6, appName: "D", imagePath: "/tmp/d.heic"),
        ]
        let blend = try XCTUnwrap(RewindScrub.blend(at: Self.base + 3, in: frames))
        XCTAssertTrue(blend.weight.isFinite)
        XCTAssertGreaterThanOrEqual(blend.weight, 0)
        XCTAssertLessThanOrEqual(blend.weight, 1)
    }

    // MARK: - What the stage actually draws

    /// **The dissolve is opportunistic**, and that is what makes it free.
    ///
    /// It engages only when both captures are already decoded. Waiting on a decode to start a fade
    /// would put a stall in the middle of the gesture this exists to smooth, and at a wide zoom —
    /// where one pixel of drag crosses twenty captures — it would double the decode load for a fade
    /// nobody could see. Degrading to a cut is never wrong: a cut is what the timeline did on every
    /// step before any of this existed.
    func testTheDissolveOnlyEngagesWhenBothCapturesAreAlreadyDecoded() {
        let blend = RewindScrub.Blend(base: 3, next: 4, weight: 0.5)

        let both = RewindScrub.layers(for: blend, baseIsDecoded: true, nextIsDecoded: true)
        XCTAssertEqual(both, RewindScrub.Layers(base: 3, over: 4, weight: 0.5))

        let waiting = RewindScrub.layers(for: blend, baseIsDecoded: true, nextIsDecoded: false)
        XCTAssertEqual(
            waiting, RewindScrub.Layers(base: 3, over: nil, weight: 0),
            "a fade that waits for a decode is a stall in the middle of the gesture")

        // The capture under the playhead is not decoded but its neighbour is: showing the real
        // neighbour beats showing nothing. It is three seconds away and it is a photograph.
        let neighbour = RewindScrub.layers(for: blend, baseIsDecoded: false, nextIsDecoded: true)
        XCTAssertEqual(neighbour, RewindScrub.Layers(base: 4, over: nil, weight: 0))

        // Neither decoded draws nothing, which is the caller's signal to hold whatever is already on
        // screen rather than blanking it — blanking and coming back is a flicker on every step.
        let cold = RewindScrub.layers(for: blend, baseIsDecoded: false, nextIsDecoded: false)
        XCTAssertEqual(cold, RewindScrub.Layers(base: nil, over: nil, weight: 0))

        // A weight of zero is not a dissolve however much is resident.
        let resting = RewindScrub.Blend(base: 3, next: 4, weight: 0)
        XCTAssertNil(
            RewindScrub.layers(for: resting, baseIsDecoded: true, nextIsDecoded: true).over)
    }

    // MARK: - Prefetch

    /// The same eleven decodes, aimed where the playhead is going.
    ///
    /// The count is what the decoded-frame budget is sized against, so it must not grow; the *aim* is
    /// what stops a moving scrub spending half its decodes on captures it has already passed. The
    /// trailing two stay because a scrub reverses constantly — the user overshoots and comes back.
    func testThePrefetchWindowIsAimedWhereThePlayheadIsGoingAndNeverGrows() throws {
        let count = 500

        for direction in [-1, 0, 1] {
            for index in [0, 1, 12, 250, count - 2, count - 1] {
                let window = try XCTUnwrap(
                    RewindScrub.prefetchWindow(around: index, direction: direction, count: count))
                XCTAssertTrue(window.contains(index), "the playhead's own capture must be warmed")
                XCTAssertLessThanOrEqual(
                    window.count, RewindScrub.prefetchWindowWidth,
                    "the window grew past what FrameLoader.memoryBudgetBytes is sized for")
                XCTAssertGreaterThanOrEqual(window.lowerBound, 0)
                XCTAssertLessThan(window.upperBound, count)
                // Both halves of a dissolve are inside it whichever way the playhead is moving.
                XCTAssertTrue(window.contains(max(0, index - 1)))
                XCTAssertTrue(window.contains(min(count - 1, index + 1)))
            }
        }

        let forward = try XCTUnwrap(RewindScrub.prefetchWindow(around: 250, direction: 1, count: count))
        XCTAssertEqual(forward, (250 - RewindScrub.prefetchTrail)...(250 + RewindScrub.prefetchLead))
        let back = try XCTUnwrap(RewindScrub.prefetchWindow(around: 250, direction: -1, count: count))
        XCTAssertEqual(back, (250 - RewindScrub.prefetchLead)...(250 + RewindScrub.prefetchTrail))
        XCTAssertGreaterThan(
            forward.upperBound - 250, 250 - forward.lowerBound,
            "a moving scrub must decode ahead of itself, not behind")

        let resting = try XCTUnwrap(RewindScrub.prefetchWindow(around: 250, direction: 0, count: count))
        XCTAssertEqual(
            resting, (250 - RewindScrub.prefetchRadius)...(250 + RewindScrub.prefetchRadius),
            "a playhead that is not moving has no direction to favour")

        XCTAssertNil(RewindScrub.prefetchWindow(around: 0, direction: 0, count: 0))
        XCTAssertNil(RewindScrub.prefetchWindow(around: 7, direction: 0, count: 3))
    }

    // MARK: - The decoded-frame cache

    private func image() -> NSImage { NSImage(size: NSSize(width: 1, height: 1)) }

    /// **The ceiling is a ceiling.** This is the property `NSCache` never offered — its
    /// `totalCostLimit` is advisory, which the comment it replaced admitted out loud — and it is the
    /// one that matters for a window a user leaves open all day.
    func testTheCacheNeverExceedsItsBudget() {
        var cache = FrameMemoryCache(budgetBytes: 1_000)

        for id in 0..<500 {
            cache.insert(image(), id: Int64(id), bytes: 137)
            XCTAssertLessThanOrEqual(
                cache.bytes, 1_000, "the budget was exceeded after inserting frame \(id)")
        }
        XCTAssertEqual(cache.bytes, cache.count * 137, "the accounting drifted from what is held")
        XCTAssertGreaterThan(cache.count, 0, "a cache that holds nothing proves nothing")

        // Re-inserting the same id replaces rather than double-counting it, which is how a bound
        // leaks without ever visibly breaking.
        let held = cache.count
        let bytes = cache.bytes
        for _ in 0..<20 { cache.insert(image(), id: 499, bytes: 137) }
        XCTAssertEqual(cache.count, held)
        XCTAssertEqual(cache.bytes, bytes)
    }

    /// **Least recently *read* goes first**, which is precisely the rule that keeps a dissolve's two
    /// captures resident: they are the two the stage read last. `NSCache`'s order is unspecified, so
    /// it could drop the frame under the playhead and keep one from an hour ago.
    func testTheLeastRecentlyReadFrameIsTheOneEvicted() {
        var cache = FrameMemoryCache(budgetBytes: 300)
        for id in 0..<3 { cache.insert(image(), id: Int64(id), bytes: 100) }
        XCTAssertEqual(cache.count, 3)

        // Read 0, making 1 the oldest by read order rather than by insert order.
        XCTAssertNotNil(cache.image(for: 0))
        cache.insert(image(), id: 3, bytes: 100)

        XCTAssertTrue(cache.holds(0), "the frame that was just read was evicted")
        XCTAssertFalse(cache.holds(1), "the least recently read frame survived")
        XCTAssertTrue(cache.holds(2))
        XCTAssertTrue(cache.holds(3))
        XCTAssertEqual(cache.bytes, 300)
    }

    /// A single frame larger than the whole budget is not admitted, rather than admitted and then
    /// evicting everything including itself. Decoding it twice beats a ceiling that can be crossed.
    func testAFrameLargerThanTheWholeBudgetIsNotAdmitted() {
        var cache = FrameMemoryCache(budgetBytes: 300)
        cache.insert(image(), id: 1, bytes: 100)

        cache.insert(image(), id: 2, bytes: 5_000)

        XCTAssertFalse(cache.holds(2))
        XCTAssertTrue(cache.holds(1), "an inadmissible frame must not evict the ones that fit")
        XCTAssertEqual(cache.bytes, 100)

        cache.removeAll()
        XCTAssertEqual(cache.bytes, 0)
        XCTAssertEqual(cache.count, 0)
        XCTAssertNil(cache.image(for: 1))
    }

    /// The speculative decodes are capped; the frame under the playhead is not.
    ///
    /// The cap is about a fast scrub at a wide zoom, where every pointer move names an entirely
    /// different window: uncapped, sixty events a second each launch eleven decodes and several
    /// hundred concurrent tasks take the cores the UI needs — a stutter caused by the work that
    /// exists to prevent one. Asserted synchronously, before any decode can complete, which is what
    /// makes it hermetic.
    @MainActor
    func testSpeculativeDecodesAreCappedAndThePlayheadsOwnFrameIsNot() {
        let loader = FrameLoader()
        let frames = Self.captures(30).map {
            RewindFrame(
                id: $0.id, capturedAt: $0.capturedAt, appName: $0.appName,
                imagePath: "/nonexistent/rewind-scrub-\($0.id).heic")
        }

        loader.prefetch(frames)
        XCTAssertEqual(loader.inFlightCount, FrameLoader.maximumConcurrentDecodes)

        loader.load(frames[29]) { _ in }
        XCTAssertEqual(
            loader.inFlightCount, FrameLoader.maximumConcurrentDecodes + 1,
            "the capture under the playhead must never be dropped for the cap")
    }

    // MARK: - The tail of a gesture

    /// A released flick keeps travelling in proportion to how fast it was going, and a standstill
    /// does not travel at all.
    func testAReleasedScrubCoastsInProportionToItsSpeed() {
        XCTAssertEqual(RewindGlide.projectedRest(from: 100, velocity: 0), 100, accuracy: 0.000_1)
        XCTAssertEqual(
            RewindGlide.projectedRest(from: 100, velocity: 50),
            100 + 50 * RewindGlide.coastSeconds, accuracy: 0.000_1)
        // Backwards is the same gesture with the other sign, not a special case.
        XCTAssertLessThan(RewindGlide.projectedRest(from: 100, velocity: -50), 100)
    }

    /// The settle eases *out* — fast off the mark, slow into the frame — and lands exactly on its
    /// target rather than a rounding error short of it. A 99/1 composite at rest is still a composite.
    func testTheSettleEasesOutAndLandsExactlyOnItsTarget() throws {
        let glide = try XCTUnwrap(RewindGlide(from: 1_000, to: 1_010, visibleSpan: 3_600))

        XCTAssertEqual(glide.instant(atElapsed: 0), 1_000, accuracy: 0.000_1)
        XCTAssertEqual(glide.instant(atElapsed: glide.duration), 1_010, accuracy: 0.000_1)
        XCTAssertEqual(glide.instant(atElapsed: 99), 1_010, accuracy: 0.000_1, "past the end it holds")
        XCTAssertTrue(glide.isFinished(atElapsed: glide.duration))
        XCTAssertFalse(glide.isFinished(atElapsed: glide.duration / 2))

        // Decelerating: the first half of the time covers more than half the distance. An ease-in-out
        // would accelerate again after the user had already stopped, which reads as the timeline
        // taking over rather than as momentum running out.
        let halfway = glide.instant(atElapsed: glide.duration / 2)
        XCTAssertGreaterThan(halfway, 1_005)

        var previous = -Double.infinity
        for step in 0...50 {
            let value = glide.instant(atElapsed: glide.duration * Double(step) / 50)
            XCTAssertGreaterThanOrEqual(value, previous, "the settle went backwards")
            previous = value
        }
    }

    /// The duration is measured against the *visible* track, so the same distance on screen takes the
    /// same time at every zoom — and it stays inside a band a settle is allowed to occupy.
    func testTheSettleDurationIsZoomRelativeAndBounded() throws {
        let nudge = try XCTUnwrap(RewindGlide(from: 0, to: 1, visibleSpan: 86_400))
        let far = try XCTUnwrap(RewindGlide(from: 0, to: 80_000, visibleSpan: 86_400))
        XCTAssertLessThan(nudge.duration, far.duration)

        for span in [120.0, 3_600, 86_400] {
            for distance in [0.5, 5.0, 500.0, 200_000.0] {
                let glide = try XCTUnwrap(RewindGlide(from: 0, to: distance, visibleSpan: span))
                XCTAssertGreaterThanOrEqual(glide.duration, RewindGlide.minimumSettle)
                XCTAssertLessThanOrEqual(glide.duration, RewindGlide.maximumSettle)
            }
        }

        // The same fraction of the visible track settles in the same time whatever the zoom.
        let zoomedOut = try XCTUnwrap(RewindGlide(from: 0, to: 8_640, visibleSpan: 86_400))
        let zoomedIn = try XCTUnwrap(RewindGlide(from: 0, to: 12, visibleSpan: 120))
        XCTAssertEqual(zoomedOut.duration, zoomedIn.duration, accuracy: 0.000_1)

        XCTAssertNil(
            RewindGlide(from: 1_000, to: 1_000, visibleSpan: 3_600),
            "a settle to where you already are is a timer for nothing")
    }

    // MARK: - The model, over a real day

    private struct Loaded {
        let model: RewindModel
        let frames: [RewindFrame]
        let spacing: Double
    }

    private var temporaryRoots: [URL] = []

    override func tearDownWithError() throws {
        for root in temporaryRoots { try? FileManager.default.removeItem(at: root) }
        temporaryRoots.removeAll()
    }

    /// A real `ContextStore` at the real 3 s capture tick, because the defect these assert is
    /// specifically about deltas smaller than half of that interval.
    @MainActor
    private func loadedModel(spacing: Double = 3, count: Int = 400) async throws -> Loaded {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-scrub-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        temporaryRoots.append(root)

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        let day = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: Self.base))
        let start = day.timeIntervalSince1970 + 10 * 3_600

        for step in 0..<count {
            _ = try store.insertFrame(
                Frame(
                    // Two apps, so the day has real activity blocks and the segment chevrons have
                    // somewhere to go.
                    capturedAt: start + Double(step) * spacing,
                    appName: step < count / 2 ? "Cursor" : "Arc",
                    windowTitle: "context.db", imagePath: "/tmp/rewind-scrub-frame.heic"))
        }

        let model = RewindModel(store: store, day: day)
        // A fixed clock: everything the coast and the settle do is a function of elapsed time, and a
        // test that advanced it by sleeping would fail on a loaded machine.
        model.clock = { 0 }
        model.loadInitial()
        await model.settle()
        XCTAssertEqual(model.frames.count, count, "the fixture did not load")
        return Loaded(model: model, frames: model.frames, spacing: spacing)
    }

    /// **The regression, stated exactly.**
    ///
    /// `travel(by:)` used to re-derive its starting point from the *snapped* frame, so a delta under
    /// half a capture interval resolved straight back to where it began: it did not move the playhead
    /// a little, it moved it not at all, and nothing accumulated between events. Zoomed in to the
    /// two-minute floor that is every ordinary trackpad event — and every event of a momentum tail,
    /// whose deltas decay towards zero, at any zoom. This is what "the scrolling does not feel
    /// smooth" was, mechanically.
    @MainActor
    func testASubCaptureScrollMovesThePlayheadInsteadOfBeingDiscarded() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        let anchor = loaded.frames[200].capturedAt
        model.park(at: anchor)

        let frameBefore = try XCTUnwrap(model.currentFrame)

        model.travel(by: 1.0)

        // The old code's answer was "nothing happened at all". The new one moves exactly the second
        // it was asked for, while still showing the capture it is nearest.
        XCTAssertEqual(try XCTUnwrap(model.playheadAt), anchor + 1.0, accuracy: 0.000_1)
        XCTAssertEqual(model.currentFrame?.id, frameBefore.id, "1 s is not a new capture at a 3 s tick")

        // …and it accumulates, which is the half that was actually broken.
        for _ in 0..<9 { model.travel(by: 1.0) }
        XCTAssertEqual(try XCTUnwrap(model.playheadAt), anchor + 10.0, accuracy: 0.000_1)
        XCTAssertEqual(
            try XCTUnwrap(model.currentFrame?.capturedAt), anchor + 9, accuracy: 0.000_1,
            "ten one-second scrolls did not add up to three captures")
    }

    /// The playhead's position drives the dissolve directly, with no animation of its own — which is
    /// what keeps a fast scrub level with the pointer instead of trailing a fixed number of
    /// milliseconds behind it.
    @MainActor
    func testTheDissolveTracksThePlayheadRatherThanAFixedAnimation() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        let anchor = loaded.frames[200].capturedAt
        model.park(at: anchor)

        XCTAssertEqual(try XCTUnwrap(model.currentBlend).weight, 0, accuracy: 0.000_001)

        model.scrub(to: anchor + loaded.spacing * RewindScrub.blendStart / 2)
        XCTAssertEqual(
            try XCTUnwrap(model.currentBlend).weight, 0, accuracy: 0.000_001,
            "the first third of an interval still shows one real capture")

        model.scrub(to: anchor + loaded.spacing / 2)
        XCTAssertEqual(try XCTUnwrap(model.currentBlend).weight, 0.5, accuracy: 0.000_001)

        model.scrub(to: anchor + loaded.spacing * 0.9)
        XCTAssertEqual(try XCTUnwrap(model.currentBlend).weight, 1, accuracy: 0.000_001)
    }

    /// **A gesture always comes to rest on a photograph.**
    ///
    /// Left parked between two captures, the stage would hold a permanent composite of two different
    /// screens — an image that never existed, held as steadily as one that did.
    @MainActor
    func testASettleLandsThePlayheadOnARealCaptureWithNoDissolveLeftShowing() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        let anchor = loaded.frames[200].capturedAt

        model.park(at: anchor)
        model.scrub(to: anchor + 1.4)
        XCTAssertGreaterThan(
            try XCTUnwrap(model.currentBlend).weight, 0, "the fixture must start mid-dissolve")

        model.endScrub()
        XCTAssertTrue(model.isSettling)
        let glide = try XCTUnwrap(model.glide)
        XCTAssertEqual(glide.to, anchor, accuracy: 0.000_1, "a drag settles where it was let go")

        // Drive the ease through the same seam the timer drives, with the clock advanced by hand.
        var now = 0.0
        while model.isSettling, now < 5 {
            now += 1.0 / 120
            model.clock = { now }
            model.tickGlide()
        }

        XCTAssertFalse(model.isSettling)
        XCTAssertEqual(try XCTUnwrap(model.playheadAt), anchor, accuracy: 0.000_001)
        XCTAssertEqual(
            try XCTUnwrap(model.currentBlend).weight, 0,
            "a settled playhead is still showing part of another capture")
    }

    /// A flick carries past its last event. macOS sends most of this inertia itself and the timeline
    /// used to discard all of it; what is added here is only the overshoot that finishes it off.
    @MainActor
    func testAFlickCoastsPastWhereItsLastEventLeftIt() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        model.park(at: loaded.frames[100].capturedAt)

        // Three events of a fast scroll, each a 120 Hz tick apart.
        var now = 0.0
        for _ in 0..<3 {
            now += 1.0 / 120
            model.clock = { now }
            model.travel(by: 10)
        }
        let released = try XCTUnwrap(model.playheadAt)

        model.endScrub()

        let glide = try XCTUnwrap(model.glide, "a flick that stops on its last event stops dead")
        XCTAssertGreaterThan(glide.to, released, "the coast went backwards or nowhere")
        // Bounded, too: a coast that ran away would be worse than none.
        XCTAssertLessThan(glide.to - released, 200)

        // A single event has no elapsed time to measure a speed from — a wheel-mouse notch — so it
        // settles where it is instead of guessing a velocity and flying off.
        let wheel = try await loadedModel()
        wheel.model.park(at: wheel.frames[100].capturedAt)
        wheel.model.travel(by: 1.4)
        wheel.model.endScrub()
        XCTAssertEqual(
            try XCTUnwrap(wheel.model.glide).to, wheel.frames[100].capturedAt, accuracy: 0.000_1,
            "one notch coasted somewhere the user did not ask for")
    }

    /// Anything the user does next wins over a settle that is still running.
    @MainActor
    func testNewInputCancelsASettleInProgress() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        let anchor = loaded.frames[200].capturedAt

        func settling() -> RewindModel {
            model.park(at: anchor)
            model.scrub(to: anchor + 1.4)
            model.endScrub()
            XCTAssertTrue(model.isSettling)
            return model
        }

        settling().travel(by: 0.2)
        XCTAssertFalse(model.isSettling, "a scroll during a settle must win")

        settling().scrub(to: anchor + 30)
        XCTAssertFalse(model.isSettling, "a drag during a settle must win")

        settling().step(1)
        XCTAssertFalse(model.isSettling, "an arrow key during a settle must win")

        _ = settling()
        model.load(day: Calendar.current.startOfDay(for: Date(timeIntervalSince1970: 1)))
        XCTAssertFalse(
            model.isSettling,
            "a settle towards yesterday's capture must not survive a day change — and it must end "
                + "when the day is asked for, not when the read of it lands")
        await model.settle()
        XCTAssertFalse(model.isSettling)
    }

    /// **A moment arriving from outside the track parks on a capture; only the pointer sits between
    /// two.** A search result for a spoken line names an arbitrary instant, and there is no gesture
    /// behind it to settle, so landing mid-interval would leave a dissolve nobody is driving.
    @MainActor
    func testAMomentFromOutsideTheTrackParksOnACapture() async throws {
        let loaded = try await loadedModel()
        let model = loaded.model
        // Deliberately between two captures, which is where a spoken line's timestamp actually falls.
        let between = loaded.frames[150].capturedAt + 1.37

        model.focus(on: between)
        await model.settle()

        XCTAssertEqual(
            try XCTUnwrap(model.playheadAt), try XCTUnwrap(model.currentFrame).capturedAt,
            accuracy: 0.000_001)
        XCTAssertEqual(try XCTUnwrap(model.currentBlend).weight, 0)

        // The segment chevrons are the same class of jump.
        XCTAssertTrue(model.hasNextSegment, "the fixture needs two activity blocks")
        model.goToAdjacentSegment(forward: true)
        XCTAssertEqual(
            try XCTUnwrap(model.playheadAt), try XCTUnwrap(model.currentFrame).capturedAt,
            accuracy: 0.000_001)
        XCTAssertEqual(try XCTUnwrap(model.currentBlend).weight, 0)
    }

    // MARK: - The gesture, through the track

    private func trackView(span: Double) -> RewindTrackView {
        let view = RewindTrackView(
            frame: NSRect(x: 0, y: 0, width: 1_000, height: RewindTrackView.height))
        view.apply(
            blocks: [], frames: Self.captures(10), trackStart: Self.base, trackSpan: span,
            playheadAt: Self.base)
        return view
    }

    /// **Zooming in is what makes the control finer**, and it is finer in proportion: the same finger
    /// travel is the same fraction of the track and therefore proportionally less *time*.
    ///
    /// Worth pinning because the fine end is exactly where the old model threw the result away — 1.2 s
    /// against a 1.5 s rounding threshold — so the arithmetic being right was not enough to make the
    /// gesture work, and the arithmetic being wrong would now be silent.
    @MainActor
    func testZoomingInMakesTheSameScrollTravelProportionallyLessTime() throws {
        func travelled(atSpan span: Double) -> Double {
            var seconds = 0.0
            let view = trackView(span: span)
            view.onTravel = { seconds += $0 }
            view.handleScroll(
                deltaX: -10, deltaY: 0, isContinuous: true, phase: .changed, momentumPhase: [])
            return seconds
        }

        let wide = travelled(atSpan: 86_400)
        let narrow = travelled(atSpan: RewindZoom.minimumSpan)

        XCTAssertEqual(wide, 10.0 / 1_000 * 86_400, accuracy: 0.000_1)
        XCTAssertEqual(narrow, 10.0 / 1_000 * RewindZoom.minimumSpan, accuracy: 0.000_1)
        XCTAssertEqual(wide / narrow, 86_400 / RewindZoom.minimumSpan, accuracy: 0.001)
        XCTAssertLessThan(
            narrow, 1.5,
            "this is the delta the old model rounded away; if it is no longer under the threshold "
                + "the regression above stops proving anything")
    }

    /// When a gesture is over, and — just as important — when it is not.
    @MainActor
    func testTheGestureEndsOnALiftedFingerAndOnSpentInertiaButNotMidScroll() {
        var travels: [Double] = []
        var ends = 0
        let view = trackView(span: 3_600)
        view.onTravel = { travels.append($0) }
        view.onScrubEnd = { ends += 1 }

        view.handleScroll(
            deltaX: -10, deltaY: 0, isContinuous: true, phase: .changed, momentumPhase: [])
        XCTAssertEqual(travels.count, 1)
        XCTAssertEqual(ends, 0, "a scroll still under the fingers is not over")

        // Fingers lift. The event carries no deltas, and passing its zero on would fold a standstill
        // into the smoothed speed at the exact moment that speed is read — cancelling the coast the
        // flick had just earned.
        view.handleScroll(
            deltaX: 0, deltaY: 0, isContinuous: true, phase: .ended, momentumPhase: [])
        XCTAssertEqual(travels.count, 1, "a phase-only event must not report a standstill as travel")
        XCTAssertEqual(ends, 1)

        // The system's own inertia, which the model treats as ordinary travel and which cancels the
        // settle the lift started.
        view.handleScroll(
            deltaX: -4, deltaY: 0, isContinuous: true, phase: [], momentumPhase: .changed)
        XCTAssertEqual(travels.count, 2)
        XCTAssertEqual(ends, 1)

        view.handleScroll(
            deltaX: 0, deltaY: 0, isContinuous: true, phase: [], momentumPhase: .ended)
        XCTAssertEqual(ends, 2, "the last settle is the one that lands")

        // A wheel mouse reports neither phase and every notch stands alone, so it settles on the spot
        // — otherwise its playhead would be left mid-dissolve with no gesture ever ending.
        view.handleScroll(
            deltaX: -10, deltaY: 0, isContinuous: false, phase: [], momentumPhase: [])
        XCTAssertEqual(travels.count, 3)
        XCTAssertEqual(ends, 3)

        // A cancelled gesture is still a finished one; nothing may be left mid-dissolve.
        view.handleScroll(
            deltaX: 0, deltaY: 0, isContinuous: true, phase: .cancelled, momentumPhase: [])
        XCTAssertEqual(ends, 4)
    }
}
