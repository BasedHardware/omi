import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The timeline's **state** over a real store: what the window is looking at, what it says it is
/// looking at, and whether the two agree after time has passed.
///
/// A real `ContextStore` for the same reason `TimelineHandoffTests` uses one — `RewindModel` reads
/// through `RewindQueries` and has no seam for a fixture, and the day boundaries every assertion is
/// stated against come from `Calendar.current`, which is what the app will use too. Nothing here
/// depends on the wall clock: every instant is fixed.
final class RewindStateTests: XCTestCase {

    private var temporaryRoots: [URL] = []

    override func tearDownWithError() throws {
        for root in temporaryRoots { try? FileManager.default.removeItem(at: root) }
        temporaryRoots.removeAll()
    }

    /// A store on disk, empty. Frames are inserted by the test that wants them, because the shapes
    /// below differ in exactly the detail each one is about.
    private func makeStore(_ name: String) throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(name)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        temporaryRoots.append(root)
        return try ContextStore(url: root.appendingPathComponent("context.db"))
    }

    /// A fixed day, so these are the same instants on every machine and in every month. The local
    /// calendar still decides where the day's boundaries fall.
    private var fixedDay: Date {
        Calendar.current.startOfDay(for: Date(timeIntervalSince1970: 1_760_000_000))
    }

    /// `count` frames of one app, three seconds apart, starting at `start`.
    ///
    /// - Parameter hasImage: whether each row keeps its picture. `false` is not a hypothetical:
    ///   8.7% of the rows on the real database have no `imagePath`, because the dedupe gate records
    ///   an app/title transition without paying for a capture — which is why they cluster at exactly
    ///   the boundaries the segment chevrons navigate by.
    @discardableResult
    private func insertRun(
        _ store: ContextStore, app: String, start: Double, count: Int, spacing: Double = 3,
        hasImage: Bool = true
    ) throws -> Double {
        var at = start
        for _ in 0..<count {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: at, appName: app, windowTitle: "\(app) window",
                    ocrText: "\(app) text",
                    imagePath: hasImage ? "/tmp/rewind-state-frame.heic" : nil))
            at += spacing
        }
        return at - spacing
    }

    // MARK: - The segment chevrons

    /// **A day whose block boundary has no picture on it**, which is the shape the real database has.
    ///
    /// - `Alpha` — a whole block, every row with an image.
    /// - `Beta` — begins on an image-less row, then has pictures. Its `startedAt` therefore names an
    ///   instant the scrubbable array does not contain.
    /// - `Delta` — a block with *no* pictures at all.
    /// - `Gamma` — a whole block again.
    private struct Segments {
        let model: RewindModel
        let alphaStart: Double
        let betaStart: Double
        let betaFirstPicture: Double
        let gammaStart: Double
    }

    @MainActor
    private func makeSegments(_ name: String) async throws -> Segments {
        let store = try makeStore(name)
        let day = fixedDay
        let alphaStart = day.timeIntervalSince1970 + 10 * 3_600

        // 12 frames × 3 s is 33 s of run, comfortably over the 15 s a block has to last to survive
        // `Queries.activity`.
        try insertRun(store, app: "Alpha", start: alphaStart, count: 12)
        let betaStart = alphaStart + 36
        // The transition row: a new app, no picture. This is the row that makes `startedAt`
        // unreachable from the frame array.
        try insertRun(store, app: "Beta", start: betaStart, count: 1, hasImage: false)
        try insertRun(store, app: "Beta", start: betaStart + 3, count: 11)
        let deltaStart = betaStart + 39
        try insertRun(store, app: "Delta", start: deltaStart, count: 12, hasImage: false)
        let gammaStart = deltaStart + 36
        try insertRun(store, app: "Gamma", start: gammaStart, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        XCTAssertEqual(model.blocks.count, 4, "the fixture did not produce the four blocks it means to")
        return Segments(
            model: model, alphaStart: alphaStart, betaStart: betaStart,
            betaFirstPicture: betaStart + 3, gammaStart: gammaStart)
    }

    /// **"Next segment" always moves, and it moves into the segment it names.**
    ///
    /// The defect, exactly. `goToAdjacentSegment` parked on the next block's `startedAt`, and
    /// `park(at:)` resolves an instant to the *nearest* capture with ties going to the earlier one.
    /// At an app switch with no gap, the block before ends three seconds before the block after
    /// begins, so when the boundary row itself has no picture the nearest capture to it is the last
    /// frame of the segment being left. The playhead did not move; the next press recomputed the
    /// same candidate from the same position; and the chevron was dead for the rest of the day while
    /// still drawing itself as available.
    ///
    /// The second assertion is what stops this proving nothing: it states that the old rule really
    /// did resolve backwards on this fixture, so a revert fails here rather than passing quietly.
    @MainActor
    func testTheNextSegmentChevronMovesPastTheSegmentItLeft() async throws {
        let fixture = try await makeSegments("segments-forward")
        let model = fixture.model

        // The old rule, stated: the nearest capture to Beta's start is one of Alpha's.
        let nearestToBoundary = try XCTUnwrap(model.frames.nearestIndex(to: fixture.betaStart))
        XCTAssertEqual(
            model.frames[nearestToBoundary].appName, "Alpha",
            "the boundary resolves forwards on this fixture, so it cannot demonstrate the stall")

        model.park(at: fixture.alphaStart)
        XCTAssertEqual(model.currentFrame?.appName, "Alpha")

        XCTAssertTrue(model.hasNextSegment)
        model.goToAdjacentSegment(forward: true)
        XCTAssertEqual(
            model.currentFrame?.capturedAt, fixture.betaFirstPicture,
            "the chevron landed on \(model.currentFrame?.appName ?? "nothing") — it must land on the "
                + "first frame of the next segment that actually has one")

        // …and again, which skips `Delta` entirely: a block with no pictures has nothing to show, so
        // stopping on it would be a press that does nothing.
        model.goToAdjacentSegment(forward: true)
        XCTAssertEqual(model.currentFrame?.capturedAt, fixture.gammaStart)
        XCTAssertEqual(model.currentFrame?.appName, "Gamma")
        XCTAssertFalse(model.hasNextSegment, "there is nothing after the last block")
    }

    /// The same claim backwards, and the end-to-end one: pressing until it stops visits every
    /// segment that has a picture, and never the same one twice.
    @MainActor
    func testSteppingThroughTheSegmentsTerminatesAndNeverRepeatsItself() async throws {
        let fixture = try await makeSegments("segments-walk")
        let model = fixture.model
        model.park(at: fixture.alphaStart)

        var visited: [Double] = []
        while model.hasNextSegment {
            model.goToAdjacentSegment(forward: true)
            let at = try XCTUnwrap(model.currentFrame?.capturedAt)
            XCTAssertFalse(visited.contains(at), "the chevron landed on \(at) twice — it is stalling")
            visited.append(at)
            XCTAssertLessThan(visited.count, model.blocks.count + 1, "the walk is not terminating")
        }
        XCTAssertEqual(visited, [fixture.betaFirstPicture, fixture.gammaStart])

        while model.hasPreviousSegment {
            model.goToAdjacentSegment(forward: false)
            let at = try XCTUnwrap(model.currentFrame?.capturedAt)
            visited.append(at)
            XCTAssertLessThan(visited.count, 2 * model.blocks.count + 1, "the walk is not terminating")
        }
        XCTAssertEqual(
            Array(visited.dropFirst(2)), [fixture.betaFirstPicture, fixture.alphaStart],
            "walking back must visit the same segments the walk forward did")
    }

    /// **The chevron is lit exactly when pressing it does something.**
    ///
    /// The enabled state and the action used to be two separate readings — "is there a later block"
    /// against "where does parking on its start land" — and the stall above was the gap between
    /// them: a control drawn as available that could not move. They are one question now, and this
    /// asserts it at the one position where the two readings disagreed.
    @MainActor
    func testTheChevronsEnabledStateAgreesWithWhatPressingItDoes() async throws {
        let fixture = try await makeSegments("segments-enabled")
        let model = fixture.model

        // Standing on the last frame of `Alpha` — the exact position where "there is a later block"
        // and "parking on that block's start goes anywhere" came apart.
        model.park(at: fixture.betaStart - 3)
        XCTAssertEqual(model.currentFrame?.appName, "Alpha")
        XCTAssertTrue(model.hasNextSegment)
        let before = model.currentFrame?.capturedAt
        model.goToAdjacentSegment(forward: true)
        XCTAssertNotEqual(
            model.currentFrame?.capturedAt, before,
            "a chevron drawn as available did nothing when it was pressed")

        // …and at the end of the record, where it is dark and pressing it must be a no-op.
        model.park(at: try XCTUnwrap(model.frames.last?.capturedAt))
        XCTAssertFalse(model.hasNextSegment)
        let last = model.currentFrame?.capturedAt
        model.goToAdjacentSegment(forward: true)
        XCTAssertEqual(model.currentFrame?.capturedAt, last, "a dark chevron must not move anything")
    }

    // MARK: - Catching up with capture

    /// **The window reads its day once, and the app keeps writing.**
    ///
    /// `RewindWindow` holds the model for the life of the process and every route back into the
    /// timeline reuses it, so before `refresh()` the second open of a day showed the first open's
    /// frames — the track simply stopped at whatever hour the window first happened to be opened.
    @MainActor
    func testReopeningTheTimelineSeesWhatCaptureWroteWhileItWasAway() async throws {
        let store = try makeStore("refresh-catchup")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        let firstRead = model.frames.count
        XCTAssertEqual(model.frames.count, 12)

        // Capture goes on while the window is up.
        try insertRun(store, app: "Alpha", start: start + 36, count: 12)

        model.refresh()
        await model.settle()
        XCTAssertGreaterThan(
            model.frames.count, firstRead,
            "the timeline never re-read its day, so everything captured since the window opened is "
                + "unreachable from it")
        XCTAssertEqual(model.frames.count, 24)
        XCTAssertEqual(model.frames.last?.capturedAt, start + 69)
    }

    /// **A moment captured since the last read opens on that moment, not on the stale last frame.**
    ///
    /// The sharp form of the staleness, and the reason it is a correctness bug rather than a
    /// freshness one. `focus(on:)` loads the instant's day, and `load(day:)` is a no-op when that day
    /// is already the loaded one; `setPlayheadInstant` then clamps to the last frame it knows about.
    /// So an activity tile for something captured five minutes ago landed the playhead an hour
    /// earlier and the date pill stated *that* time — a window quietly showing a different moment
    /// than the one that was clicked.
    @MainActor
    func testAMomentCapturedSinceTheLastReadLandsOnThatMoment() async throws {
        let store = try makeStore("refresh-focus")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        let staleLast = try XCTUnwrap(model.frames.last?.capturedAt)

        // An hour later, on the same day.
        let newMoment = start + 3_600
        try insertRun(store, app: "Beta", start: newMoment, count: 12)

        model.focus(on: newMoment)
        await model.settle()

        XCTAssertEqual(
            model.currentFrame?.capturedAt, newMoment,
            "the card named \(newMoment) and the window landed on \(model.currentFrame?.capturedAt ?? -1)")
        XCTAssertNotEqual(
            model.currentFrame?.capturedAt, staleLast,
            "the playhead was clamped to the last frame of the stale read")
        XCTAssertEqual(model.currentFrame?.appName, "Beta")
    }

    /// **A refresh must not move anything the user put where it is.**
    ///
    /// The failure this trades against: a timeline that re-parked on the newest capture every time
    /// it caught up would take the playhead away from whoever is scrubbing it. Catching up is about
    /// what is *reachable*, never about where the playhead is pointing.
    @MainActor
    func testARefreshLeavesThePlayheadAndTheTrackWindowWhereTheUserPutThem() async throws {
        let store = try makeStore("refresh-untouched")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 40)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()

        // Somewhere in the middle, zoomed in, with the frame image scaled up.
        let parked = start + 30
        model.park(at: parked)
        model.zoomTrack(in: true)
        model.zoomTrack(in: true)
        model.zoomImage(in: true)
        let span = model.trackSpan
        let trackStart = model.trackStart
        let imageZoom = model.imageZoom

        try insertRun(store, app: "Alpha", start: start + 200, count: 40)
        model.refresh()
        await model.settle()

        XCTAssertEqual(model.playheadAt, parked, "the refresh moved the playhead")
        XCTAssertEqual(model.currentFrame?.capturedAt, parked)
        XCTAssertEqual(model.trackSpan, span, "the refresh undid the track zoom")
        XCTAssertEqual(model.trackStart, trackStart, "the refresh panned the visible window")
        XCTAssertEqual(model.imageZoom, imageZoom, "the refresh undid the frame-image zoom")
        XCTAssertEqual(model.frames.count, 80, "…and it did not catch up at all")
    }

    /// **Appearing again is not a reason to start over.**
    ///
    /// `loadInitial()` runs from `RewindView.onAppear`, and a view can appear more than once for one
    /// window — it is ordered out and back in, and the hosting view is re-attached. Re-reading from
    /// scratch would pick the newest day again and discard the one the user navigated to.
    @MainActor
    func testAppearingAgainKeepsTheDayTheUserNavigatedTo() async throws {
        let store = try makeStore("refresh-reappear")
        let newest = fixedDay
        let older = try XCTUnwrap(Calendar.current.date(byAdding: .day, value: -2, to: newest))
        try insertRun(store, app: "Alpha", start: older.timeIntervalSince1970 + 9 * 3_600, count: 12)
        try insertRun(store, app: "Beta", start: newest.timeIntervalSince1970 + 9 * 3_600, count: 12)

        let model = RewindModel(store: store, day: newest)
        model.loadInitial()
        await model.settle()
        XCTAssertEqual(model.day, newest, "the window opens on the newest day with captures")

        model.load(day: older)
        await model.settle()
        XCTAssertEqual(model.day, older)

        model.loadInitial()
        await model.settle()
        XCTAssertEqual(
            model.day, older,
            "the view appearing again threw the user back to the newest day")
    }

    /// A day the window is standing on that had nothing on it when it was read picks up the first
    /// capture made on it, rather than staying empty until something else forces a reload.
    @MainActor
    func testADayThatWasEmptyWhenItWasReadPicksUpItsFirstCapture() async throws {
        let store = try makeStore("refresh-empty")
        let day = fixedDay
        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        XCTAssertTrue(model.frames.isEmpty)
        XCTAssertNil(model.playheadAt)

        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)
        model.refresh()
        await model.settle()

        XCTAssertEqual(model.frames.count, 12)
        XCTAssertEqual(model.playheadAt, start, "the playhead has to land on something once one exists")
        XCTAssertEqual(model.currentFrame?.capturedAt, start)
    }

    // MARK: - Reads that do not hold up the window

    /// **The first read does not happen in the turn of the run loop that asked for it.**
    ///
    /// Every read here grows with the user's history — a year of capture is half a million rows —
    /// and `loadInitial()` used to run four of them on the main actor before the window could draw
    /// anything. Two partial indexes cut the measured cost from ~1.4 s to ~0.2 s, which is a smaller
    /// hitch and still a hitch, and still one whose size is the user's own history.
    ///
    /// Asserted as a fact about *when the answer arrives* rather than as a duration: `loadInitial()`
    /// returns with nothing read, which is only possible if the read is somewhere else. A timing
    /// assertion would be a test that fails on a loaded machine.
    ///
    /// The second half is what the window shows in the meantime, and why it is not the empty copy.
    @MainActor
    func testTheFirstReadHappensOffTheMainActorAndSaysSoWhileItRuns() async throws {
        let store = try makeStore("read-off-main")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 40)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()

        XCTAssertTrue(
            model.frames.isEmpty,
            "the day was read before `loadInitial()` returned, which is the hitch itself")
        XCTAssertTrue(
            model.isReadingDay,
            "a window with no frames and no read in flight is a day that was captured on nothing — "
                + "the stage would print that over every day for the length of its own read")
        XCTAssertFalse(model.hasLoaded)

        await model.settle()

        XCTAssertEqual(model.frames.count, 40)
        XCTAssertFalse(model.isReadingDay)
        XCTAssertTrue(model.hasLoaded)
    }

    /// **A day change clears, a refresh does not.** The two reads differ in what they replace, so
    /// they differ in what the window shows while they run.
    ///
    /// A day change replaces everything: the date pill names the new day the moment it is asked
    /// for, so leaving the old day's frames on the stage would be one day's picture under another
    /// day's label. It clears and says it is reading. A refresh replaces nothing until it lands —
    /// the day on screen was read successfully and is still true — so it changes nothing at all
    /// while it runs, and `isReadingDay` stays false.
    @MainActor
    func testADayChangeSaysItIsReadingWhereARefreshShowsTheDayItAlreadyHas() async throws {
        let store = try makeStore("read-states")
        let day = fixedDay
        let older = try XCTUnwrap(Calendar.current.date(byAdding: .day, value: -2, to: day))
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)
        try insertRun(store, app: "Beta", start: older.timeIntervalSince1970 + 9 * 3_600, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        XCTAssertEqual(model.frames.count, 12)

        // A refresh: nothing moves, and nothing claims to be reading.
        try insertRun(store, app: "Alpha", start: start + 36, count: 12)
        model.refresh()
        XCTAssertFalse(model.isReadingDay, "a refresh replaced the day it was refreshing")
        XCTAssertEqual(model.frames.count, 12, "a refresh emptied the window while it ran")
        XCTAssertEqual(model.currentFrame?.appName, "Alpha")
        await model.settle()
        XCTAssertEqual(model.frames.count, 24)

        // A day change: the old day goes at once, because the pill already names the new one.
        model.load(day: older)
        XCTAssertTrue(model.isReadingDay)
        XCTAssertTrue(model.frames.isEmpty, "the previous day's picture stayed under the new day's pill")
        XCTAssertNil(model.loadError, "a day being read is not a day that failed to read")
        await model.settle()
        XCTAssertEqual(model.frames.count, 12)
        XCTAssertEqual(model.currentFrame?.appName, "Beta")
        XCTAssertFalse(model.isReadingDay)
    }

    /// **A read that lands after the day it was for has been left is thrown away.**
    ///
    /// The reads run off the main actor now, so their order of arrival is not the order they were
    /// asked in: a user stepping days quickly — the chevrons are two clicks apart — can have
    /// yesterday's read land after today's. Absorbing it would put one day's frames under another
    /// day's date pill with nothing on screen admitting the difference, which is the same class of
    /// lie `refresh()` exists to prevent.
    ///
    /// Driven through the production landing path with a generation the window has already left.
    /// The control at the end is what stops this proving nothing: the *same* read, handed over with
    /// the current generation, does land — so what is asserted is the discard rule and not an
    /// absorb that quietly does nothing.
    @MainActor
    func testAReadFromADayTheWindowHasAlreadyLeftIsDiscarded() async throws {
        let store = try makeStore("read-out-of-order")
        let day = fixedDay
        let older = try XCTUnwrap(Calendar.current.date(byAdding: .day, value: -2, to: day))
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)
        try insertRun(store, app: "Beta", start: older.timeIntervalSince1970 + 9 * 3_600, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()

        // The read of the day the user is about to leave, held back as a slow one would be.
        let stale = model.readGeneration
        let staleRead = RewindDayRead(
            frames: model.frames, blocks: model.blocks, previousDayCapture: nil,
            nextDayCapture: nil, failure: nil)

        model.load(day: older)
        await model.settle()
        XCTAssertNotEqual(model.readGeneration, stale, "the day change did not start a new read")
        let landed = model.frames.map(\.id)
        XCTAssertEqual(model.currentFrame?.appName, "Beta")

        model.absorb(day: staleRead, generation: stale)
        XCTAssertEqual(
            model.frames.map(\.id), landed,
            "a read of the day the user left overwrote the day they are on")
        XCTAssertEqual(model.currentFrame?.appName, "Beta")

        // The control: the same read, from the generation that is current, is absorbed.
        model.absorb(day: staleRead, generation: model.readGeneration)
        XCTAssertEqual(model.currentFrame?.appName, "Alpha")
    }

    /// **A read landing under a gesture leaves the gesture alone.**
    ///
    /// `refresh()` promises it moves nothing the user put where it is, and the promise got harder to
    /// keep when the read stopped being instantaneous: the playhead, the visible window and the
    /// image zoom can all move *while the read is in flight*, and the absorb lands on top of
    /// whatever they are then — not on what they were when it was asked.
    ///
    /// The ordering is real rather than simulated. The read runs on a detached task; everything
    /// between `refresh()` and `settle()` runs on the main actor without suspending, so the landing
    /// is guaranteed to come after the scrub and the zooms, which is precisely the race.
    @MainActor
    func testAReadLandingUnderAGestureDoesNotMoveThePlayheadOrEitherZoom() async throws {
        let store = try makeStore("read-under-gesture")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 40)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()

        try insertRun(store, app: "Alpha", start: start + 200, count: 40)
        model.refresh()

        // …and the user keeps working while it reads.
        let parked = start + 30
        model.park(at: parked)
        model.zoomTrack(in: true)
        model.zoomTrack(in: true)
        model.zoomImage(in: true)
        let span = model.trackSpan
        let trackStart = model.trackStart
        let imageZoom = model.imageZoom

        await model.settle()

        XCTAssertEqual(model.playheadAt, parked, "the read that landed moved the playhead")
        XCTAssertEqual(model.currentFrame?.capturedAt, parked)
        XCTAssertEqual(model.trackSpan, span, "the read that landed undid the track zoom")
        XCTAssertEqual(model.trackStart, trackStart, "the read that landed panned the visible window")
        XCTAssertEqual(model.imageZoom, imageZoom, "the read that landed undid the frame-image zoom")
        XCTAssertEqual(model.frames.count, 80, "…and it did not catch up at all")
    }

    // MARK: - Live Text

    /// **A request that outlives the frame it was made for is re-asked, not dropped.**
    ///
    /// Recognition takes most of a second and only one pass runs at a time, so both callers are
    /// refused outright while one is in flight: pressing the control during a pass, or stepping a
    /// frame with it already on, left *nothing* scheduled — the discarded result was the only work
    /// there was, and the control stayed dark until it was toggled off and on again.
    ///
    /// The decision is asserted rather than the Vision pass around it: what the platform recognises
    /// is the platform's, and what we do when a result lands late is the half that shipped wrong.
    /// Turning the control off withdraws the request, so a late result must not chase the playhead
    /// on behalf of somebody who stopped asking.
    func testALiveTextRequestThatOutlivesItsFrameIsReAsked() {
        XCTAssertTrue(RewindModel.shouldRerunRecognition(showsLiveText: true))
        XCTAssertFalse(RewindModel.shouldRerunRecognition(showsLiveText: false))
    }

    // MARK: - Operating the track without a pointer

    /// **The track is a slider, and it was not an element at all.**
    ///
    /// Everything it shows is drawn in `draw(_:)`, and a custom `NSView` is not an accessibility
    /// element unless it says so — so the window's primary control had no role, no label and no
    /// value, and where in the day the timeline was sitting was unreadable by anyone not looking at
    /// the screen. The value is read off the same `playheadAt` the handle is drawn from and the same
    /// frame a click would select, so what is announced and what is shown cannot drift apart.
    @MainActor
    func testTheTrackReportsItselfAsASliderAndNamesTheMomentItIsOn() throws {
        let view = RewindTrackView(frame: NSRect(x: 0, y: 0, width: 600, height: RewindTrackView.height))
        let start = fixedDay.timeIntervalSince1970 + 10 * 3_600
        let frames = (0..<12).map {
            RewindFrame(
                id: Int64($0), capturedAt: start + Double($0) * 3, appName: "Alpha",
                imagePath: "/tmp/rewind-state-frame.heic")
        }
        view.apply(
            blocks: [], frames: frames, trackStart: start, trackSpan: 3_600,
            playheadAt: start + 6)

        XCTAssertTrue(view.isAccessibilityElement())
        XCTAssertEqual(view.accessibilityRole(), .slider)
        XCTAssertEqual(view.accessibilityLabel(), "Timeline")
        let value = try XCTUnwrap(view.accessibilityValue() as? String)
        XCTAssertTrue(value.contains("Alpha"), "the value must name what owned the screen: \(value)")
        XCTAssertFalse(
            value.contains("197"), "the value must be a time a person reads, not an epoch: \(value)")
    }

    /// **The poll pays for a count, not for a day.**
    ///
    /// The gate an open timeline asks on a timer. It has to be exactly as truthful as the read it
    /// stands in for — a gate that said "nothing new" while there was would make the live refresh
    /// silently do nothing, which is the bug it exists to fix wearing a different hat.
    @MainActor
    func testThePollNoticesNewCapturesWithoutReadingTheDay() async throws {
        let store = try makeStore("refresh-poll")
        let day = fixedDay
        let start = day.timeIntervalSince1970 + 9 * 3_600
        try insertRun(store, app: "Alpha", start: start, count: 12)

        let model = RewindModel(store: store, day: day)
        model.loadInitial()
        await model.settle()
        let unreadAfterRead = await model.hasUnreadCaptures()
        XCTAssertFalse(unreadAfterRead, "nothing has been written since the read")

        // An image-less row is real history and is counted by the activity query, but it is not
        // showable — so it must not make the poll claim there is a frame to catch up with.
        try insertRun(store, app: "Alpha", start: start + 36, count: 1, hasImage: false)
        let unreadAfterImagelessRow = await model.hasUnreadCaptures()
        XCTAssertFalse(
            unreadAfterImagelessRow,
            "a row with no picture is not a capture the frame array can show")

        try insertRun(store, app: "Alpha", start: start + 39, count: 4)
        let unreadAfterCapture = await model.hasUnreadCaptures()
        XCTAssertTrue(unreadAfterCapture)
        // The whole of what the live-capture poll does, driven exactly as `RewindWindow`'s timer
        // drives it: the count and the day both happen off the main actor.
        await model.refreshIfCapturesLanded()
        await model.settle()
        let unreadAfterRefresh = await model.hasUnreadCaptures()
        XCTAssertFalse(unreadAfterRefresh, "the refresh did not take the captures the poll saw")
    }

    /// **The tooltip goes when the timeline does.**
    ///
    /// It is a borderless `.floating` window, and the only two things that used to take it down were
    /// a mouse-exit and the view leaving its window — neither of which happens when the timeline is
    /// merely ordered out. Close the window with the pointer sitting over the track and the pill was
    /// left floating above every other application, naming a moment from a window that is gone.
    /// Parenting it to the timeline hands that rule to AppKit, which already has it.
    @MainActor
    func testTheHoverTooltipIsTakenDownWithTheTimeline() throws {
        let host = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 600, height: 200),
            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        defer { host.orderOut(nil) }

        let view = RewindTrackView(frame: NSRect(x: 0, y: 0, width: 600, height: RewindTrackView.height))
        host.contentView?.addSubview(view)
        host.orderFront(nil)

        let start = fixedDay.timeIntervalSince1970 + 10 * 3_600
        view.apply(
            blocks: [], frames: (0..<12).map {
                RewindFrame(
                    id: Int64($0), capturedAt: start + Double($0) * 3, appName: "Alpha",
                    imagePath: "/tmp/rewind-state-frame.heic")
            }, trackStart: start, trackSpan: 3_600, playheadAt: start)

        view.showTooltip(atX: 120, near: NSPoint(x: 200, y: 200), in: host)
        XCTAssertTrue(view.tooltipIsVisible, "hovering the track shows the moment under the pointer")

        host.orderOut(nil)
        XCTAssertFalse(
            view.tooltipIsVisible,
            "the timeline was ordered out and its tooltip stayed on screen above everything else")
    }

    /// Increment and decrement step **one capture**, which is the same movement the arrow keys make.
    ///
    /// Seconds would have been the easy choice and the wrong one: a fixed number of them lands
    /// between two frames at a fine zoom and on the same frame at a coarse one, where "the next
    /// capture" means the same thing at every zoom and always moves the picture.
    @MainActor
    func testTheTrackCanBeSteppedWithoutAPointer() {
        let view = RewindTrackView(frame: NSRect(x: 0, y: 0, width: 600, height: RewindTrackView.height))
        var steps: [Int] = []
        view.onStep = { steps.append($0) }

        XCTAssertTrue(view.accessibilityPerformIncrement())
        XCTAssertTrue(view.accessibilityPerformDecrement())
        XCTAssertEqual(steps, [1, -1])

        // The Settings preview draws this track over synthetic data with no playhead to move, and
        // reports itself as an unadjustable slider rather than one whose controls do nothing.
        let preview = RewindTrackView(frame: NSRect(x: 0, y: 0, width: 600, height: 56))
        XCTAssertFalse(preview.accessibilityPerformIncrement())
        XCTAssertFalse(preview.accessibilityPerformDecrement())
    }
}
