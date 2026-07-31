import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// The mark delivering a card's copy.
///
/// Everything asserted here is a claim about *rhythm* or about *material*, which is deliberate: the
/// mark has no mouth, so "it looks like it is speaking" is entirely a claim about timing, and timing
/// is the one part of an animation that can be checked without looking at it. The two render tests
/// at the bottom cover the one thing arithmetic cannot — that the blink is a blink and not a
/// disappearance.
final class TalkingMarkTests: XCTestCase {

    // MARK: - Reduce Motion

    /// The setting's whole promise, in one assertion: with no clock to read, the pose is `.rest`,
    /// and `.rest` moves nothing.
    ///
    /// This is why `TalkingMarkPose` exists as a value at all. The alternative — four `if
    /// InkReduceMotion.isEnabled` branches inside a `ViewBuilder` — is unassertable, because
    /// `NSWorkspace.accessibilityDisplayShouldReduceMotion` is a machine setting a hermetic test
    /// cannot flip. Reducing the whole decision to "elapsed is nil" puts it inside reach.
    func testReduceMotionResolvesToAPoseThatMovesNothing() {
        let phrase = SpokenCadence(start: Date(), wordCount: 6)
        let still = TalkingMarkMotion.pose(elapsed: nil, phrase: phrase)

        XCTAssertEqual(still, .rest)
        XCTAssertTrue(still.isStill)
        XCTAssertEqual(still.lift, 0, "no bob")
        XCTAssertEqual(still.stretch, 0, "no squash or stretch")
        XCTAssertEqual(still.lean, 0, "no weight shift")
        XCTAssertEqual(still.eyeOpen, 1, "no blink — the eyes are simply open")
    }

    /// …and the same call with a clock is not still, so the test above cannot pass by the animation
    /// having quietly died everywhere.
    func testThePoseIsNotStillWhileThePhraseIsBeingSaid() {
        let phrase = SpokenCadence(start: Date(), wordCount: 6)
        let moving = TalkingMarkMotion.pose(
            elapsed: phrase.duration * TalkingMarkMotion.breathPeak, phrase: phrase)

        XCTAssertFalse(moving.isStill)
        XCTAssertGreaterThan(moving.lift, 0)
        XCTAssertGreaterThan(moving.stretch, 0)
    }

    // MARK: - The breath

    /// One rise and one fall per phrase, starting and ending at rest, and never above the top of
    /// its own travel.
    ///
    /// The last clause is the one worth having: an overshoot — a spring settling past its target —
    /// is what turns a small creature taking a breath into a bouncing toy, and it is the single
    /// easiest thing to reach for when a motion feels too subtle.
    func testTheBreathIsOneRiseAndFallWithNoOvershoot() {
        let peak = TalkingMarkMotion.breathPeak
        XCTAssertEqual(TalkingMarkMotion.breath(progress: 0), 0, accuracy: 1e-9)
        XCTAssertEqual(TalkingMarkMotion.breath(progress: 1), 0, accuracy: 1e-9)
        XCTAssertEqual(TalkingMarkMotion.breath(progress: peak), 1, accuracy: 1e-9)

        var previous = TalkingMarkMotion.breath(progress: 0)
        for step in 1...400 {
            let t = Double(step) / 400
            let value = TalkingMarkMotion.breath(progress: t)
            XCTAssertGreaterThanOrEqual(value, 0, "the mark never sinks below where it started")
            XCTAssertLessThanOrEqual(value, 1 + 1e-9, "no overshoot past the top of the breath")
            if t <= peak {
                XCTAssertGreaterThanOrEqual(value, previous - 1e-9, "rising up to the peak, at \(t)")
            } else {
                XCTAssertLessThanOrEqual(value, previous + 1e-9, "settling after the peak, at \(t)")
            }
            previous = value
        }
    }

    /// The curve leaves and arrives at a standstill. A raised cosine's derivative is zero at both
    /// ends; `sin(πt)`'s is at its maximum there, which is what made it the wrong curve.
    func testTheBreathStartsAndEndsAtAStandstill() {
        let h = 1e-4
        let startSlope = (TalkingMarkMotion.breath(progress: h) - 0) / h
        let endSlope = (0 - TalkingMarkMotion.breath(progress: 1 - h)) / h
        XCTAssertEqual(startSlope, 0, accuracy: 0.01, "the mark eases into the breath")
        XCTAssertEqual(endSlope, 0, accuracy: 0.01, "and eases out of it rather than stopping dead")
    }

    // MARK: - The eyes

    /// A line begins with a blink, the blink completes, and then the eyes are simply open until the
    /// resting rate comes round again.
    func testALineBeginsWithABlinkAndThenBlinksAtRest() {
        let blink = TalkingMarkMotion.blinkSeconds
        let period = TalkingMarkMotion.blinkPeriod

        XCTAssertEqual(TalkingMarkMotion.eyeOpen(elapsed: 0), 1, accuracy: 1e-9, "open on the first frame")
        XCTAssertEqual(
            TalkingMarkMotion.eyeOpen(elapsed: blink * TalkingMarkMotion.blinkCloseFraction),
            TalkingMarkMotion.blinkFloor, accuracy: 1e-9,
            "shut at the bottom of the stroke")
        XCTAssertEqual(TalkingMarkMotion.eyeOpen(elapsed: blink), 1, accuracy: 1e-9, "and open again")

        // Nothing between blinks.
        for t in stride(from: blink + 0.01, to: period - 0.01, by: 0.05) {
            XCTAssertEqual(TalkingMarkMotion.eyeOpen(elapsed: t), 1, accuracy: 1e-9, "at \(t)")
        }
        // And it comes round again, so a card left standing keeps someone in it.
        XCTAssertLessThan(
            TalkingMarkMotion.eyeOpen(elapsed: period + blink * TalkingMarkMotion.blinkCloseFraction),
            0.2, "the resting rate")
    }

    /// The eye never closes completely: it is a fill, and a fill scaled to nothing is an absence
    /// rather than a lid.
    func testTheEyeNeverScalesToNothing() {
        for step in 0...2000 {
            let value = TalkingMarkMotion.eyeOpen(elapsed: Double(step) / 100)
            XCTAssertGreaterThanOrEqual(value, TalkingMarkMotion.blinkFloor - 1e-9)
            XCTAssertLessThanOrEqual(value, 1 + 1e-9)
        }
    }

    // MARK: - The cadence

    /// The reveal runs left to right, one word at a time, and stops.
    ///
    /// Strictly increasing is the whole difference between a character speaking and the scattered
    /// stagger every other headline uses: a random order reads as a shimmer, and a shimmer is not
    /// attributable to anybody.
    func testTheRevealIsMonotonicAndTerminates() {
        for words in 1...40 {
            let cadence = SpokenCadence(start: Date(), wordCount: words)
            XCTAssertGreaterThan(cadence.duration, 0, "\(words) words")
            XCTAssertEqual(cadence.normalizedDelay(wordIndex: 0), 0, "the first word is not kept waiting")

            var previous = -1.0
            for index in 0..<words {
                let delay = cadence.normalizedDelay(wordIndex: index)
                XCTAssertGreaterThan(delay, previous, "word \(index) of \(words) waits longer than word \(index - 1)")
                XCTAssertLessThanOrEqual(delay, 1, "no word is scheduled after the phrase has ended")
                previous = delay
            }

            // The last word finishes exactly as the phrase does — the reveal terminates, and it
            // terminates *at* the end rather than leaving dead air or being cut off.
            XCTAssertEqual(
                cadence.normalizedDelay(wordIndex: words - 1) + cadence.normalizedRamp, 1,
                accuracy: 1e-9, "\(words) words")
        }
    }

    /// Nobody waits longer than they do today.
    ///
    /// This is the rule the whole feature is bounded by: `scheduleSettle` is untouched, so a card's
    /// button appears exactly when it always did, and a phrase is not allowed to still be arriving
    /// long after it. A long line speaks faster instead of running longer.
    func testNoPhraseTakesLongerThanTheRevealItReplaces() {
        for words in 1...200 {
            let cadence = SpokenCadence(start: Date(), wordCount: words)
            XCTAssertLessThanOrEqual(
                cadence.duration, InkMotion.wordReveal + 1e-9,
                "a \(words)-word phrase must not outlast the reveal it replaces")
        }
        // Short lines still get the full, comfortable beat rather than being compressed for nothing.
        XCTAssertEqual(SpokenCadence(start: Date(), wordCount: 4).pace, SpokenCadence.secondsPerWord)
    }

    /// Words are counted the way the reveal tokenises them — per segment, so an emphasis break
    /// mid-phrase splits a token and both sides agree it did. Disagree here and the last word's beat
    /// lands somewhere other than the end of the phrase.
    func testWordsAreCountedTheWayTheRevealTokenisesThem() {
        let hero: [RandomizedText.Segment] = [
            .init("I keep "), .init("Claude", .bold), .init(" caught up on what you "),
            .init("see and say", .bold), .init("."),
        ]
        XCTAssertEqual(SpokenCadence.wordCount(of: hero), 12, "'say' and '.' are two tokens, not one word")
        XCTAssertEqual(SpokenCadence.wordCount(of: [.init("  ")]), 0)
        XCTAssertEqual(SpokenCadence.wordCount(of: [.init("First…")]), 1)
    }

    // MARK: - Accessibility

    /// VoiceOver reads the sentence somebody wrote, not the runs it was cut into for emphasis.
    func testTheCopyIsReadAsOneStringAndNotAsWordFragments() {
        let hero: [(String, Emphasis)] = [
            ("I keep ", .plain), ("Claude", .bold), (" caught up on what you ", .plain),
            ("see and say", .bold), (".", .plain),
        ]
        XCTAssertEqual(
            TalkingMark.plainCopy(of: hero),
            "I keep Claude caught up on what you see and say.")
    }

    // MARK: - The arrangement

    /// Both gaps are a fraction of the type being spoken, so the day `Ink`'s scale grows they grow
    /// with it instead of reading as a collision at the new size.
    ///
    /// Asserted as a *ratio* between two real roles rather than against point values, which is the
    /// only form of this claim that survives the numbers changing. This is the surviving half of the
    /// test that used to check a bubble's padding, corner and tail: those are gone, and what is left
    /// is the only geometry the mark and its words still have between them.
    func testTheSpacingIsSizedFromTheTypeBeingSpoken() {
        let hero = TalkingMarkLayout(lead: InkType.introHero)
        let step = TalkingMarkLayout(lead: InkType.stepHeadline)
        let ratio = InkType.introHero.lineHeight / InkType.stepHeadline.lineHeight
        XCTAssertGreaterThan(ratio, 1, "the two roles have to differ for this test to mean anything")

        // Rounded to whole points, so the tolerance is what rounding two values can cost.
        for (larger, smaller, name) in [
            (hero.gap, step.gap, "the gap to the mark"),
            (hero.asideSpacing, step.asideSpacing, "the gap to the aside"),
        ] {
            XCTAssertGreaterThan(larger, smaller, "\(name) grows with the type")
            XCTAssertEqual(larger / smaller, ratio, accuracy: 0.12, "\(name) is a fraction of the line box")
        }

        // The mark, by contrast, is *not* per-role: it is the same creature on every card, so it
        // must not grow and shrink as the headline role changes between screens.
        XCTAssertEqual(hero.markSize, step.markSize, "the mark is one size through the whole flow")
    }

    /// The mark's head sits on the first line's centre — beside the line it is saying, not beside
    /// the middle of the paragraph.
    ///
    /// This used to be a claim about a tail pointing at a head. There is no tail; the claim is the
    /// same one, and it is now the *only* thing tying the drawing to the copy, so it matters more
    /// rather than less.
    func testTheMarksHeadLandsOnTheLineItIsSaying() {
        for role in [InkType.introHero, InkType.stepHeadline, InkType.firstTitle] {
            let metrics = TalkingMarkLayout(lead: role)
            let headCentre = metrics.markOffsetY + metrics.markSize * TalkingMarkLayout.markHeadCentreFraction
            XCTAssertEqual(headCentre, metrics.firstLineCentreY, accuracy: 1e-9, "\(role.size) pt")

            // And the first line is where the copy starts, not somewhere down the paragraph.
            XCTAssertTrue(
                (0...role.lineHeight).contains(metrics.firstLineCentreY),
                "the head sits beside the first line at \(role.size) pt")
        }
    }

    /// Nothing draws a ground, a border or a tail under the copy any more, and the horizontal cost
    /// of the arrangement is the mark plus one gap — nothing else.
    ///
    /// The regression this stands against is concrete: the bubble's tail and its two paddings took
    /// 57 pt out of a 488 pt reading column *before* the mark's own box, and when `introHero` went
    /// 32 → 34 pt the welcome hero stopped fitting. Stated as an inequality against the column so it
    /// keeps meaning something if either number moves.
    func testTheCopyPaysForNothingButTheMarkAndOneGap() {
        let metrics = TalkingMarkLayout(lead: InkType.introHero)
        let cost = metrics.markSize + metrics.gap

        XCTAssertLessThan(
            cost, InkLayout.contentMaxWidth * 0.16,
            "the mark and its gap take \(cost) pt of a \(InkLayout.contentMaxWidth) pt column")
        XCTAssertGreaterThan(metrics.gap, 0, "the mark still has to stand apart from the words")
    }

    // MARK: - Fitting the card

    /// **The regression this whole change exists for.** The welcome hero has to fit the reading
    /// column, with room, at the size it actually ships at.
    ///
    /// It did not. `InkType.introHero` went 32 → 34 pt in one change and the speech bubble arrived in
    /// another; neither alone overflowed, and together the line ran off the right of the card — the
    /// last word past the edge, on the very first screen of the product. Nothing failed, because
    /// nothing measured the card.
    ///
    /// So this measures it, through the view the app renders, at the width the app gives it, on the
    /// copy the app says. The bar is the rightmost *inked* pixel, which is the only definition of
    /// "fits" that a wrap, a clip and an overflow cannot each satisfy differently: a `Text` that has
    /// run out of room draws past its frame, and the frame is the bitmap's edge.
    ///
    /// **"Fits" is a claim about height**, and it has to be.
    ///
    /// A headline cannot run off the side of a card: `Text` never draws outside its frame — too
    /// little room and it wraps, and a word it cannot break it wraps *mid-word*. What too little
    /// width actually costs is **lines**, and lines are height, and the window is a fixed 720 × 640
    /// that does not scroll. That is the whole shape of the regression: the hero went 32 → 34 pt and
    /// the bubble took 52 pt of horizontal budget, the line needed a third row to hold itself, and
    /// the card grew past the bottom of the window it is drawn in.
    ///
    /// So the measurement is the hero's laid-out height against the height the page padding leaves,
    /// and the bar is generous on purpose — a headline that is already using half the card has no
    /// room for the button under it.
    @MainActor
    func testTheWelcomeHeroFitsTheHeightTheCardHasForIt() throws {
        XCTAssertTrue(InkTestFonts.registered, "no font files found next to the package")
        let column = InkLayout.contentMaxWidth
        let available = OnboardingWindow.cardSize.height - 2 * InkLayout.pagePaddingVertical

        let laidOut = try ink(
            of: TalkingMark(
                lead: OnboardingView.welcomeLead,
                leadStyle: .introHero,
                // Far enough in the past that the phrase has been fully said, so this measures the
                // finished line rather than however much of it a given frame had revealed.
                start: Date().addingTimeInterval(-5)),
            width: column,
            height: available)

        XCTAssertGreaterThan(laidOut.bottom, 0, "the welcome hero drew nothing")
        XCTAssertLessThan(
            laidOut.bottom, available * 0.4,
            "the welcome hero is \(laidOut.bottom) pt tall in a card with \(available) pt, "
                + "leaving too little for the button under it")
        // And it is inside the measure it was given, which is the other half of fitting.
        XCTAssertLessThanOrEqual(laidOut.right, column, "the hero reaches \(laidOut.right) pt")
    }

    /// …and the measurement is genuinely capable of failing: squeeze the same copy into a column it
    /// cannot hold and it grows exactly the way the real regression grew.
    ///
    /// Without this, the test above would pass just as happily on a measurement that could never
    /// report an overflow at all.
    @MainActor
    func testTheFitMeasurementCatchesAHeroThatHasOutgrownItsCard() throws {
        let available = OnboardingWindow.cardSize.height - 2 * InkLayout.pagePaddingVertical
        let laidOut = try ink(
            of: TalkingMark(
                lead: OnboardingView.welcomeLead,
                leadStyle: .introHero,
                start: Date().addingTimeInterval(-5)),
            width: 150,
            height: available)

        XCTAssertGreaterThanOrEqual(
            laidOut.bottom, available * 0.4,
            "a column this narrow must measure as outgrowing the card")
    }

    /// How far down and right a view laid out at a fixed width puts ink.
    ///
    /// White on black at 2×, thresholded well above the faintest antialiased edge so a word still
    /// fading in does not count. The frame is the bitmap, so nothing outside it is counted — which is
    /// the point for the height: a card that has outgrown the window is clipped by exactly this.
    @MainActor
    private func ink(
        of view: some View, width: CGFloat, height: CGFloat
    ) throws -> (bottom: CGFloat, right: CGFloat) {
        let scale: CGFloat = 2
        let renderer = ImageRenderer(
            content: ZStack(alignment: .topLeading) {
                Color.black
                view.environment(\.colorScheme, .dark)
            }
            .frame(width: width, height: height))
        renderer.scale = scale

        let image = try XCTUnwrap(renderer.cgImage, "ImageRenderer produced no bitmap")
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        _ = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard
                let context = CGContext(
                    data: raw.baseAddress, width: image.width, height: image.height,
                    bitsPerComponent: 8, bytesPerRow: image.width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }

        var bottom = 0
        var right = 0
        for y in 0..<image.height {
            for x in 0..<image.width where bytes[(y * image.width + x) * 4] > 96 {
                bottom = max(bottom, y + 1)
                right = max(right, x + 1)
            }
        }
        return (CGFloat(bottom) / scale, CGFloat(right) / scale)
    }

    // MARK: - Renders

    /// The blink is a lid, not a disappearance: the eye rows change and every other row of the
    /// drawing is untouched.
    ///
    /// A render rather than arithmetic because this is the one claim arithmetic cannot make. The
    /// mark has no mouth, so the eyes carry the whole performance, and an "eye" that scales to
    /// nothing for two frames reads as a rendering fault rather than as a blink — which is exactly
    /// what `draw.eyes` would have done, and why `eyeOpen` is a separate, vertical-only control.
    @MainActor
    func testABlinkClosesTheEyesAndTouchesNothingElse() throws {
        let size: CGFloat = 132
        let open = try render(eyeOpen: 1, size: size)
        let shut = try render(eyeOpen: TalkingMarkMotion.blinkFloor, size: size)

        let changed = try XCTUnwrap(Self.changedRows(open, shut), "the blink drew nothing")

        // The eyes' own band, from the geometry rather than from a number typed here.
        let scale = size / CinematicMarkGeometry.box
        let centre = (size - CinematicMarkGeometry.box * scale) / 2
            + CinematicMarkGeometry.eyeCentres[0].y * scale
        let radius = CinematicMarkGeometry.eyeRadii.height * scale
        XCTAssertGreaterThanOrEqual(
            changed.top, centre - radius * 1.35,
            "the blink reached above the eyes — the head is moving when it should not be")
        XCTAssertLessThanOrEqual(
            changed.bottom, centre + radius * 1.35,
            "the blink reached below the eyes — the legs are moving when they should not be")
    }

    /// The words really do arrive left to right, through the view the app actually renders.
    ///
    /// Everything above asserts `SpokenCadence`; this asserts that `RandomizedText` is *wired to
    /// it*. Delete the cadence branch in the reveal plan and every arithmetic test here still
    /// passes while the line goes back to resolving in a scattered order — which is the difference
    /// between a character speaking and a headline shimmering, and is invisible to anything that
    /// does not look at pixels.
    ///
    /// Measured as the rightmost inked column, sampled through the phrase: under a spoken cadence it
    /// only ever grows, and early on the line's right-hand half is still empty.
    @MainActor
    func testTheWordsArriveLeftToRightThroughTheRealReveal() throws {
        try XCTSkipIf(
            InkReduceMotion.isEnabled,
            "Reduce Motion reveals the line at once, which is its job — the ordering is untestable here")

        let words = 6
        let cadence = { (elapsed: Double) in
            SpokenCadence(start: Date().addingTimeInterval(-elapsed), wordCount: words)
        }
        let full = try XCTUnwrap(rightmostInk(cadence(2.0)), "the finished line drew nothing")

        var previous = 0
        for elapsed in [0.05, 0.35, 0.65, 0.95] {
            let edge = try XCTUnwrap(rightmostInk(cadence(elapsed)), "nothing drawn at \(elapsed)s")
            XCTAssertGreaterThanOrEqual(edge, previous, "the line never un-draws, at \(elapsed)s")
            XCTAssertLessThanOrEqual(edge, full + 2, "and never overruns the finished line, at \(elapsed)s")
            previous = edge
        }
        XCTAssertEqual(previous, full, accuracy: 2, "the last word lands by the end of the phrase")

        // The discriminating half: one beat in, the back of the line is still blank. A scattered
        // stagger puts ink at both ends immediately and fails here.
        let earliest = try XCTUnwrap(rightmostInk(cadence(0.05)))
        XCTAssertLessThan(
            Double(earliest), Double(full) * 0.5,
            "a beat into the phrase only the front of the line has been said")
    }

    /// The rightmost column carrying ink, in pixels, for one line of white text on black.
    @MainActor
    private func rightmostInk(_ cadence: SpokenCadence) throws -> Int? {
        let scale: CGFloat = 2
        let renderer = ImageRenderer(
            content: ZStack(alignment: .leading) {
                Color.black
                RandomizedText(
                    segments: [("alpha bravo charlie delta echo foxtrot", .plain)],
                    style: .prose,
                    color: .white,
                    cadence: cadence)
            }
            // Wide enough that the line cannot wrap, so a column index is a position in the sentence.
            .frame(width: 600, height: 40))
        renderer.scale = scale

        let image = try XCTUnwrap(renderer.cgImage, "ImageRenderer produced no bitmap")
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        _ = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard
                let context = CGContext(
                    data: raw.baseAddress, width: image.width, height: image.height,
                    bitsPerComponent: 8, bytesPerRow: image.width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }

        for x in stride(from: image.width - 1, through: 0, by: -1) {
            for y in 0..<image.height {
                let i = (y * image.width + x) * 4
                // Well above the faintest tail of a word still fading in, so a word counts as
                // "arrived" rather than "started".
                if bytes[i] > 96 { return x }
            }
        }
        return nil
    }

    /// `eyeOpen` is defaulted, and at rest it is the drawing that was there before it existed. Every
    /// call site that predates blinking — the whole cinematic — has to be pixel-unchanged.
    @MainActor
    func testTheRestingEyeIsTheDrawingItAlwaysWas() throws {
        let posed = try render(eyeOpen: TalkingMarkPose.rest.eyeOpen, size: 132)
        let untouched = try render(eyeOpen: nil, size: 132)
        XCTAssertNil(
            Self.changedRows(posed, untouched),
            "the default and the rest pose have to be the same drawing")
    }

    // MARK: Bitmaps

    /// A bitmap and the scale it was drawn at, so a row index reads back as a point. The idiom is
    /// `CinematicTests`'.
    private struct Bitmap {
        let width: Int
        let height: Int
        let scale: CGFloat
        let bytes: [UInt8]
    }

    /// The mark alone, on black so the ink has something to differ from. `eyeOpen: nil` renders the
    /// view without passing the parameter at all, which is what makes the default testable.
    @MainActor
    private func render(eyeOpen: Double?, size: CGFloat) throws -> Bitmap {
        let scale: CGFloat = 4
        let mark: AnyView =
            eyeOpen.map {
                AnyView(CinematicMarkView(draw: .complete, size: size, color: .white, eyeOpen: $0))
            } ?? AnyView(CinematicMarkView(draw: .complete, size: size, color: .white))

        let renderer = ImageRenderer(
            content: ZStack {
                Color.black
                mark
            }
            .frame(width: size, height: size))
        renderer.scale = scale

        let image = try XCTUnwrap(renderer.cgImage, "ImageRenderer produced no bitmap")
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let drew = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard
                let context = CGContext(
                    data: raw.baseAddress,
                    width: image.width,
                    height: image.height,
                    bitsPerComponent: 8,
                    bytesPerRow: image.width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }
        XCTAssertTrue(drew, "could not back the render with a bitmap")
        return Bitmap(width: image.width, height: image.height, scale: scale, bytes: bytes)
    }

    /// The band of rows two renders disagree in, in points from the top. Nil when they are identical.
    private static func changedRows(_ a: Bitmap, _ b: Bitmap) -> (top: CGFloat, bottom: CGFloat)? {
        guard a.width == b.width, a.height == b.height else { return nil }
        var first: Int?
        var last: Int?
        for y in 0..<a.height {
            for x in 0..<a.width {
                let i = (y * a.width + x) * 4
                // 8/255 keeps the faintest antialiased edge out of the band symmetrically.
                let differs = (0..<3).contains { abs(Int(a.bytes[i + $0]) - Int(b.bytes[i + $0])) > 8 }
                if differs {
                    first = first ?? y
                    last = y
                    break
                }
            }
        }
        guard let first, let last else { return nil }
        return (CGFloat(first) / a.scale, CGFloat(last + 1) / a.scale)
    }
}
