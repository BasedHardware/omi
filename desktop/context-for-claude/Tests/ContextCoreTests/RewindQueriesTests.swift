import ContextCore
import Foundation
import XCTest

/// `RewindQueries` is the only place `frames.imagePath` is selected, so these cover the two things
/// the timeline window cannot defend itself against: a row shaped in a way the schema permits but
/// capture has never produced, and a frame array whose order or completeness the binary search
/// depends on.
final class RewindQueriesTests: XCTestCase {
    private var fixture: Fixture!
    private var store: ContextStore { fixture.store }

    override func setUpWithError() throws {
        // Unseeded: this suite writes frames with exactly the shapes it is asserting about, and the
        // shared corpus's three frames would only add noise to the counts.
        fixture = try Fixture(seeded: false)
    }

    override func tearDown() {
        fixture.tearDown()
        fixture = nil
    }

    private static let base: Double = 1_760_000_000

    @discardableResult
    private func insert(
        at offset: Double,
        app: String? = "Cursor",
        bundleId: String? = nil,
        title: String? = nil,
        image: String? = "/tmp/frame.heic"
    ) throws -> Int64 {
        try store.insertFrame(
            Frame(
                capturedAt: Self.base + offset,
                appName: app,
                bundleId: bundleId,
                windowTitle: title,
                imagePath: image))
    }

    // MARK: - The image-path contract

    /// The whole reason the query exists: rows with no image must never reach the window, because a
    /// `RewindFrame` promises a path and the scrubber dereferences it. 8.7% of the rows in the real
    /// database are image-less.
    func testFramesExcludesRowsWithNoImage() throws {
        try insert(at: 0, image: "/tmp/a.heic")
        try insert(at: 10, image: nil)
        try insert(at: 20, image: "/tmp/b.heic")

        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 100)

        XCTAssertEqual(frames.map(\.imagePath), ["/tmp/a.heic", "/tmp/b.heic"])
    }

    /// `frameCount` must agree with the array it describes — the window sizes its track from one and
    /// scrubs the other, and a disagreement would be invisible until the track ran off the end.
    func testFrameCountMatchesFrames() throws {
        try insert(at: 0)
        try insert(at: 10, image: nil)
        try insert(at: 20)
        try insert(at: 30)

        let range = (Self.base - 1, Self.base + 100)
        let frames = try RewindQueries.frames(store, since: range.0, until: range.1)
        let count = try RewindQueries.frameCount(store, since: range.0, until: range.1)

        XCTAssertEqual(count, frames.count)
        XCTAssertEqual(count, 3)
    }

    /// Ascending order is a precondition of `nearestIndex(to:)`, and it is asserted here rather than
    /// assumed because a binary search over an unsorted array fails silently by returning the wrong
    /// frame rather than by crashing.
    func testFramesAreAscendingByCapturedAt() throws {
        try insert(at: 50)
        try insert(at: 10)
        try insert(at: 30)

        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 100)

        XCTAssertEqual(frames.map(\.capturedAt), [Self.base + 10, Self.base + 30, Self.base + 50])
    }

    func testFramesRespectsTheTimeWindow() throws {
        try insert(at: -100)
        try insert(at: 50)
        try insert(at: 5_000)

        let frames = try RewindQueries.frames(store, since: Self.base, until: Self.base + 100)

        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.capturedAt, Self.base + 50)
    }

    // MARK: - Nullable appName

    /// `appName` is nullable in the schema even though capture always populates it. A null must be
    /// named, not crashed on and not dropped — dropping it would lose time from the day.
    func testNullAppNameBecomesUnknownRatherThanCrashing() throws {
        try insert(at: 0, app: nil)
        try insert(at: 10, app: "   ")

        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 100)

        XCTAssertEqual(frames.count, 2)
        XCTAssertEqual(frames.map(\.appName), [RewindQueries.unknownApp, RewindQueries.unknownApp])
    }

    // MARK: - Coverage

    func testCoverageIsNilWhenNothingShowableWasCaptured() throws {
        // A row with no image is real history but cannot be opened on, so it must not widen the
        // date picker's range.
        try insert(at: 0, image: nil)

        XCTAssertNil(try RewindQueries.coverage(store))
    }

    /// Image-less rows at **both** ends, because the two bounds are asked for separately: SQLite can
    /// only answer a bare `MIN` or a bare `MAX` by seeking to one end of the index, so `coverage`
    /// runs two statements, and a predicate dropped from either one widens the date picker onto a day
    /// the window cannot open.
    func testCoverageSpansOldestToNewestShowableFrame() throws {
        try insert(at: 1, image: nil)
        try insert(at: 100)
        try insert(at: 900)
        try insert(at: 5_000, image: nil)

        let coverage = try RewindQueries.coverage(store)

        XCTAssertEqual(coverage?.lowerBound, Self.base + 100)
        XCTAssertEqual(coverage?.upperBound, Self.base + 900)
    }

    // MARK: - Seeking the next day that has something on it

    /// **The seek steps over the empty days**, which is the whole reason it exists.
    ///
    /// Coverage says the record runs from here to there; it does not say which days inside that span
    /// hold anything, and on the real database eight consecutive days hold nothing at all. A "previous
    /// day" control built on the calendar rather than on this would walk those eight one at a time.
    func testNearestCaptureSkipsTheDaysThatHoldNothing() throws {
        let day: Double = 86_400
        try insert(at: 0)
        try insert(at: 3_600)
        // Three empty days, then the next capture.
        try insert(at: 4 * day)

        // Forward from the end of the first day lands on the fourth, not on the second or third.
        let forward = try XCTUnwrap(
            RewindQueries.nearestCapture(store, from: Self.base + day, direction: .forward))
        XCTAssertEqual(forward, Self.base + 4 * day)

        // …and backward from the start of the fourth day lands on the *last* capture of the first,
        // which is where somebody travelling backwards through time arrives.
        let backward = try XCTUnwrap(
            RewindQueries.nearestCapture(store, from: Self.base + 4 * day, direction: .backward))
        XCTAssertEqual(backward, Self.base + 3_600)
    }

    /// The ends of the record are nil, which is what dims the two day controls.
    func testNearestCaptureIsNilBeyondTheEndsOfTheRecord() throws {
        try insert(at: 0)

        XCTAssertNil(try RewindQueries.nearestCapture(store, from: Self.base, direction: .forward))
        XCTAssertNil(try RewindQueries.nearestCapture(store, from: Self.base, direction: .backward))
    }

    /// **Strictly** past the instant asked about, and only rows that have a picture.
    ///
    /// Both halves are how the seek would silently stop working. An inclusive comparison answers
    /// "the previous day" with the day the caller is already standing on, so the control would look
    /// enabled and do nothing; an image-less row answers with a day that opens to an empty stage,
    /// which is the failure the control is meant to skip.
    func testNearestCapturePassesOverTheInstantItselfAndOverImagelessRows() throws {
        try insert(at: 0)
        try insert(at: 60, image: nil)
        try insert(at: 120)

        let next = try XCTUnwrap(
            RewindQueries.nearestCapture(store, from: Self.base, direction: .forward))
        XCTAssertEqual(next, Self.base + 120, "the seek stopped on itself or on an image-less row")

        let previous = try XCTUnwrap(
            RewindQueries.nearestCapture(store, from: Self.base + 120, direction: .backward))
        XCTAssertEqual(previous, Self.base)
    }

    // MARK: - Bundle ids

    /// The mechanism that lets one new sighting of an app give its whole back catalogue an icon.
    func testBundleIdsByAppLearnsFromAnyRowThatRecordedOne() throws {
        try insert(at: 0, app: "Cursor", bundleId: nil)
        try insert(at: 10, app: "Cursor", bundleId: "com.todesktop.230313mzl4w4u92")
        try insert(at: 20, app: "Arc", bundleId: nil)

        let map = try RewindQueries.bundleIdsByApp(store)

        XCTAssertEqual(map["Cursor"], "com.todesktop.230313mzl4w4u92")
        // An app that has never recorded one stays absent rather than mapping to something invented.
        XCTAssertNil(map["Arc"])
    }

    /// An app rebuilt under a new identifier must resolve to the current one, not the retired one.
    func testBundleIdsByAppPrefersTheNewestSighting() throws {
        try insert(at: 0, app: "Thing", bundleId: "com.old.thing")
        try insert(at: 10, app: "Thing", bundleId: "com.new.thing")

        XCTAssertEqual(try RewindQueries.bundleIdsByApp(store)["Thing"], "com.new.thing")
    }

    // MARK: - Migration

    /// The migration is additive, so a database written before it stays readable and its rows keep
    /// their values — the legacy-principal case for the new column.
    func testRowsPredatingTheBundleIdColumnRemainValidAndReadNil() throws {
        let id = try insert(at: 0, app: "Cursor", bundleId: nil, title: "main.swift")

        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 100)

        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.id, id)
        XCTAssertNil(frames.first?.bundleId, "an unrecorded bundle id must stay nil, never a guess")
        XCTAssertEqual(frames.first?.windowTitle, "main.swift")
    }

    // MARK: - Time-linear lookup

    /// The search the whole time-linear track rests on.
    func testNearestIndexFindsTheClosestFrameInTime() throws {
        for offset in [0.0, 100.0, 200.0, 1_000.0] { try insert(at: offset) }
        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 10_000)

        XCTAssertEqual(frames.nearestIndex(to: Self.base - 500), 0, "before the first frame clamps")
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 100), 1, "exact hit")
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 104), 1, "rounds down to the nearer")
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 196), 2, "rounds up to the nearer")
        // Scrubbing into a gap lands on the closest capture rather than on nothing, which is what
        // makes a time-linear track usable across an idle stretch.
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 600), 2)
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 900), 3)
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 99_999), 3, "after the last frame clamps")
    }

    func testNearestIndexOnAnEmptyDayIsNil() {
        XCTAssertNil([RewindFrame]().nearestIndex(to: Self.base))
    }

    /// A day with one frame is the degenerate case a binary search gets wrong most easily.
    func testNearestIndexWithASingleFrame() throws {
        try insert(at: 500)
        let frames = try RewindQueries.frames(store, since: Self.base - 1, until: Self.base + 10_000)

        XCTAssertEqual(frames.nearestIndex(to: Self.base), 0)
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 500), 0)
        XCTAssertEqual(frames.nearestIndex(to: Self.base + 9_000), 0)
    }
}
