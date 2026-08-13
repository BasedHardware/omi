import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// **The handoff from a search result to the timeline.**
///
/// The search surface answers over two indexes and draws a page of cards; before this, pressing one
/// did nothing, because there was no way to say *when* to a window whose only entry point opened
/// whatever day it happened to be on. Every claim here is about that seam:
///
/// - an instant resolves to the **local day** that contains it, by the calendar rather than by
///   arithmetic, and
/// - handing that instant to a loaded model moves it there — switching days when it has to, and
///   surviving being asked *before* the window has read anything at all, which is the order the
///   "open the timeline at this moment" path actually arrives in.
///
/// Deliberately not asserted through `RewindWindow`: that would open a real window, activate the
/// app, and put a timeline over whoever is running the suite. The window is four lines over the
/// model (`present` then `focus`), and the model is where the decisions are.
final class TimelineHandoffTests: XCTestCase {

    // MARK: - Which day an instant belongs to

    /// The instant→day rule is stated once, and it is a **calendar** question.
    ///
    /// The tempting implementation is `floor(instant / 86_400) * 86_400`, and it is wrong twice: it
    /// answers in UTC, so every user west of Greenwich gets the previous day for their whole
    /// evening, and it assumes a day is 24 hours, which is false twice a year. Both failures land on
    /// the same feature — a result opening the day *next to* the one it happened on — and neither is
    /// visible in a screenshot, so they are pinned here against a fixed zone.
    func testAnInstantResolvesToTheLocalDayThatContainsIt() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/Los_Angeles"))

        func day(_ components: DateComponents) throws -> Date {
            var parts = components
            parts.calendar = calendar
            parts.timeZone = calendar.timeZone
            return try XCTUnwrap(parts.date)
        }

        let midnight = try day(DateComponents(year: 2026, month: 7, day: 29, hour: 0, minute: 0))
        let lateEvening = try day(
            DateComponents(year: 2026, month: 7, day: 29, hour: 23, minute: 59, second: 59))
        let earlyMorning = try day(
            DateComponents(year: 2026, month: 7, day: 29, hour: 0, minute: 0, second: 1))

        // Every instant of the day belongs to that day's midnight — including the two ends, where an
        // off-by-a-second lands a result on the wrong day entirely.
        for instant in [midnight, earlyMorning, lateEvening] {
            XCTAssertEqual(
                RewindModel.day(containing: instant.timeIntervalSince1970, calendar: calendar),
                midnight,
                "\(instant) resolved to a different day than the one it happened on")
        }

        // …and the next second is the next day, so the rule is a partition rather than a rounding.
        let nextMidnight = try day(DateComponents(year: 2026, month: 7, day: 30, hour: 0, minute: 0))
        XCTAssertEqual(
            RewindModel.day(containing: nextMidnight.timeIntervalSince1970, calendar: calendar),
            nextMidnight)

        // **The arithmetic answer is a different answer.** Stated explicitly so that swapping the
        // calendar out for a division is a failing test rather than a silent regression: at 23:59
        // Pacific, UTC has already turned over.
        let naive = (lateEvening.timeIntervalSince1970 / 86_400).rounded(.down) * 86_400
        XCTAssertNotEqual(
            naive, midnight.timeIntervalSince1970,
            "dividing by 86,400 happened to agree here — pick an instant where it does not")
    }

    /// …and the day either side of a clock change is still one day, however many hours it has.
    ///
    /// 8 March 2026 is 23 hours long in US Pacific. A fixed-width day walks off the end of it, which
    /// is how a result from Sunday evening opens Monday for the one week of the year nobody would
    /// think to test.
    func testADayThatIsNotTwentyFourHoursLongIsStillOneDay() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/Los_Angeles"))

        var parts = DateComponents(year: 2026, month: 3, day: 8, hour: 22, minute: 0)
        parts.calendar = calendar
        parts.timeZone = calendar.timeZone
        let springForwardEvening = try XCTUnwrap(parts.date)

        let resolved = RewindModel.day(
            containing: springForwardEvening.timeIntervalSince1970, calendar: calendar)
        XCTAssertEqual(calendar.component(.day, from: resolved), 8)
        XCTAssertEqual(calendar.component(.hour, from: resolved), 0)
        // The day really is short — otherwise this test is asserting nothing about DST.
        let nextDay = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: resolved))
        XCTAssertEqual(
            nextDay.timeIntervalSince(resolved), 23 * 3_600,
            "this date is no longer a clock change in this zone; pick one that is")
    }

    // MARK: - Moving a loaded timeline to a moment

    /// Three days of capture in a real store, and a model that has opened on the newest of them.
    ///
    /// A real `ContextStore` rather than an injected array for the same reason `RewindZoomTests`
    /// uses one: `RewindModel` reads through `RewindQueries` and has no seam for a fixture, and the
    /// day boundaries every assertion below is stated against come from `Calendar.current` — so they
    /// are whatever the machine running this thinks a day is, which is exactly what the app will
    /// think too. Nothing here depends on the wall clock: the days are fixed instants.
    private struct Capture {
        let store: ContextStore
        let model: RewindModel
        /// Local midnight of each captured day, oldest first.
        let days: [Date]
        /// Seconds between consecutive frames.
        let spacing: Double
    }

    private var temporaryRoots: [URL] = []

    override func tearDownWithError() throws {
        for root in temporaryRoots { try? FileManager.default.removeItem(at: root) }
        temporaryRoots.removeAll()
    }

    /// - Parameter loadNow: whether the model has already read a day. False is the "opening the
    ///   window *at* a moment" order, where the focus arrives before the first read.
    @MainActor
    private func makeCapture(
        dayCount: Int = 3, spacing: Double = 900, loadNow: Bool = true, name: String = "handoff"
    ) throws -> Capture {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(name)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        temporaryRoots.append(root)

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        // A fixed instant, so the days below are the same three days on every machine and in every
        // month. The local calendar still decides where their boundaries fall.
        let newest = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: 1_760_000_000))
        var days: [Date] = []
        for back in stride(from: dayCount - 1, through: 0, by: -1) {
            days.append(
                try XCTUnwrap(Calendar.current.date(byAdding: .day, value: -back, to: newest)))
        }

        for day in days {
            let start = day.timeIntervalSince1970
            // Frames from 06:00 to 22:00, which is a plausible waking day and leaves both ends of
            // the day genuinely empty — so "nearest frame" has something to be nearest *to*.
            var at = start + 6 * 3_600
            while at < start + 22 * 3_600 {
                _ = try store.insertFrame(
                    Frame(
                        capturedAt: at, appName: "Cursor", bundleId: nil, windowTitle: "context.db",
                        ocrText: "focus fixture", imagePath: "/tmp/handoff-frame.heic"))
                at += spacing
            }
        }

        let model = RewindModel(store: store, day: days[days.count - 1])
        if loadNow {
            model.loadInitial()
            XCTAssertFalse(model.frames.isEmpty, "the fixture did not load")
        }
        return Capture(store: store, model: model, days: days, spacing: spacing)
    }

    /// **A result from another day opens that day.**
    ///
    /// The defect this closes, stated exactly: `scrub(to:)` maps an instant onto the nearest frame
    /// *in the loaded day*, so an instant from last week resolves to the first frame of today and
    /// the click reads as the timeline ignoring it. `focus(on:)` loads the day first, and the
    /// difference between the two is asserted side by side so a refactor that quietly routes the
    /// card back through `scrub` fails here.
    @MainActor
    func testFocusingAMomentFromAnotherDayLoadsThatDayAndParksThePlayheadOnIt() throws {
        let fixture = try makeCapture()
        let model = fixture.model
        let oldest = fixture.days[0]
        XCTAssertEqual(model.day, fixture.days[2], "the window opens on the newest day with captures")

        // Mid-afternoon, two days back — a moment the loaded day has no frame anywhere near.
        let target = oldest.timeIntervalSince1970 + 15 * 3_600

        // What the old seam could do: scrub alone stays on the loaded day and lands on its edge.
        model.scrub(to: target)
        XCTAssertEqual(model.day, fixture.days[2], "scrub must not change the day — that is focus's job")
        let scrubbed = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertGreaterThan(
            abs(scrubbed - target), 12 * 3_600,
            "a scrub landed near the target without loading its day, so this test proves nothing")

        // …and what the seam does.
        model.focus(on: target)
        XCTAssertEqual(model.day, oldest)
        let landed = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertLessThanOrEqual(
            abs(landed - target), fixture.spacing,
            "the playhead is \(abs(landed - target)) s from the moment, further than one capture apart")
        // The track window follows, or the playhead would be parked outside what the track shows.
        XCTAssertTrue((model.trackStart...model.trackEnd).contains(landed))
    }

    /// Focusing twice inside one day does not re-read it, and still moves the playhead.
    ///
    /// The guard in `load(day:)` is what makes this true; without it, activating a second result
    /// from the same afternoon would re-run the day's two queries and reset the track zoom under the
    /// user for no reason.
    @MainActor
    func testFocusingAnotherMomentInTheSameDayMovesThePlayheadWithoutReloading() throws {
        let fixture = try makeCapture()
        let model = fixture.model
        let day = fixture.days[2].timeIntervalSince1970

        model.focus(on: day + 8 * 3_600)
        let framesLoaded = model.frames
        let morning = try XCTUnwrap(model.currentFrame?.capturedAt)

        model.focus(on: day + 20 * 3_600)
        let evening = try XCTUnwrap(model.currentFrame?.capturedAt)

        XCTAssertGreaterThan(evening, morning + 11 * 3_600)
        XCTAssertEqual(
            model.frames.map(\.id), framesLoaded.map(\.id),
            "the day was re-read for a move inside it")
    }

    /// **Opening the window at a moment works even though the ask arrives first.**
    ///
    /// This is the ordering the "closed timeline" path really has: `RewindWindow.present(store:at:)`
    /// builds the model and asks for the instant, and only afterwards does the view appear and run
    /// `loadInitial()` — which picks the *newest* day on its own. Scrubbing at ask-time would
    /// therefore be undone a frame later, and the user would watch their week-old result open on
    /// today. The control half of the test is the same fixture without a focus, which must still
    /// open on the newest day.
    @MainActor
    func testAskingForAMomentBeforeTheFirstReadStillOpensThatMomentsDay() throws {
        let control = try makeCapture(loadNow: false, name: "handoff-control")
        control.model.loadInitial()
        XCTAssertEqual(
            control.model.day, control.days[2],
            "with nothing asked for, the window still opens on the newest day that has captures")

        let fixture = try makeCapture(loadNow: false)
        let model = fixture.model
        let target = fixture.days[0].timeIntervalSince1970 + 9 * 3_600

        // Asked before anything has been read — the model has no frames to scrub through yet.
        XCTAssertTrue(model.frames.isEmpty)
        model.focus(on: target)

        model.loadInitial()

        XCTAssertEqual(model.day, fixture.days[0], "the opening read chose the newest day anyway")
        let landed = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertLessThanOrEqual(abs(landed - target), fixture.spacing)
    }

    /// A day that was heard but not seen still opens, and stays honest about being empty.
    ///
    /// Speech and screens are captured independently, so a result can legitimately point at a day
    /// with no frames at all — the Mac was asleep, or the screen recording permission was off. The
    /// day loads and the stage says nothing was captured; it does not silently land on the nearest
    /// *other* day's picture, which would be a confident wrong answer about what the user asked to
    /// see.
    @MainActor
    func testAMomentOnADayWithNoFramesOpensThatDayEmptyRatherThanSomewhereElse() throws {
        let fixture = try makeCapture()
        let model = fixture.model
        // A day before the fixture's oldest, which has nothing in it at all.
        let silent = try XCTUnwrap(
            Calendar.current.date(byAdding: .day, value: -1, to: fixture.days[0]))

        model.focus(on: silent.timeIntervalSince1970 + 11 * 3_600)

        XCTAssertEqual(model.day, silent)
        XCTAssertTrue(model.frames.isEmpty)
        XCTAssertNil(model.currentFrame, "an empty day has no frame, and inventing one would be a lie")
        XCTAssertNil(model.loadError, "an empty day is not a failed read, and must not say it was")
    }

    // MARK: - Both kinds of result, end to end

    /// **A screen hit and a spoken hit both travel by the same instant, and both land.**
    ///
    /// Run through the production path rather than over hand-built values: a real store, a real
    /// query through `SearchResultsModel`, and the moments it returns handed to the model exactly as
    /// the card's action hands them over. The claim is the one that makes the feature work for the
    /// half of the surface that has no picture — a conversation card carries the moment the line was
    /// *spoken*, and opening it shows what was on screen while it was being said.
    @MainActor
    func testActivatingEitherKindOfResultLandsOnTheMomentItNames() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("handoff-kinds-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))

        let today = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: 1_760_000_000))
        let lastWeek = try XCTUnwrap(Calendar.current.date(byAdding: .day, value: -7, to: today))

        // Last week: the frame that matches, plus a frame every ten minutes around it so the
        // playhead has somewhere to land for the spoken hit too.
        //
        // Deliberately *not* on a ten-minute boundary. Two frames sharing an instant would make
        // "the nearest frame to this moment" ambiguous, and the assertion below would then be about
        // the tie-break in `nearestIndex` rather than about the handoff.
        let seenAt = lastWeek.timeIntervalSince1970 + 14 * 3_600 + 137
        let spokenAt = lastWeek.timeIntervalSince1970 + 16 * 3_600
        var at = lastWeek.timeIntervalSince1970 + 9 * 3_600
        while at < lastWeek.timeIntervalSince1970 + 20 * 3_600 {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: at, appName: "Cursor", bundleId: nil, windowTitle: "context.db",
                    ocrText: "background", imagePath: "/tmp/handoff-bg.heic"))
            at += 600
        }
        _ = try store.insertFrame(
            Frame(
                capturedAt: seenAt, appName: "Preview", bundleId: nil,
                windowTitle: "Invoice 2026-07", ocrText: "amount due 412.00",
                imagePath: "/tmp/handoff-invoice.heic"))
        let session = try store.openSession(at: spokenAt - 120, appHint: "zoom.us")
        _ = try store.insertSegment(
            Segment(
                sessionId: session, startedAt: spokenAt, endedAt: spokenAt + 3, source: .mic,
                text: "I will send the invoice before Friday"))

        // Today, so the timeline has a *different* day to be sitting on when the results arrive.
        _ = try store.insertFrame(
            Frame(
                capturedAt: today.timeIntervalSince1970 + 10 * 3_600, appName: "Finder",
                bundleId: nil, windowTitle: "Downloads", ocrText: "screenshots",
                imagePath: "/tmp/handoff-today.heic"))

        let results = SearchResultsModel(store: { store })
        results.ask("invoice")
        XCTAssertNil(results.loadError)

        let screen = try XCTUnwrap(results.moments.first { $0.kind == .screen })
        let spoken = try XCTUnwrap(results.moments.first { $0.kind == .conversation })
        // The instant a card travels by, for each kind. A screen hit is the frame's capture time; a
        // spoken hit is when the line started — not the session's, which is where the conversation
        // began and can be hours earlier.
        XCTAssertEqual(screen.capturedAt, seenAt, accuracy: 0.001)
        XCTAssertEqual(spoken.capturedAt, spokenAt, accuracy: 0.001)

        let model = RewindModel(store: store)
        model.loadInitial()
        XCTAssertEqual(model.day, today, "the timeline opens on today, so both hits require a day change")

        model.focus(on: screen.capturedAt)
        XCTAssertEqual(model.day, lastWeek)
        XCTAssertEqual(
            model.currentFrame?.id, screen.frame?.id,
            "the screen result opened a different frame than the one on the card")

        // Back to today between the two, so the conversation hit is a real day change of its own
        // rather than riding on the previous one.
        model.load(day: today)
        XCTAssertEqual(model.day, today)

        model.focus(on: spoken.capturedAt)
        XCTAssertEqual(model.day, lastWeek)
        let heard = try XCTUnwrap(model.currentFrame?.capturedAt)
        XCTAssertLessThanOrEqual(
            abs(heard - spokenAt), 600,
            "the conversation result landed \(abs(heard - spokenAt)) s from the line, more than one "
                + "capture apart — the timeline is not showing what was on screen while it was said")
        XCTAssertNil(spoken.frame, "a spoken line has no frame; the instant is all it can travel by")
    }

    // MARK: - Which result the keyboard is on

    /// **The arrow keys step through the page, and Return opens whatever they are on.**
    ///
    /// The keyboard is the only route into the results that exists: the field holds the first
    /// responder for the life of the surface and the cards cannot take focus, so without this the
    /// feature is pointer-only. Clamped rather than wrapping — see `SearchResultsModel.move`.
    ///
    /// **The stepping rule changed with the panel**, and the expected values here changed with it:
    /// ↓ used to mean "the next card in the ranking", which on a three-across grid moved the
    /// highlight *sideways*. It now moves a row, and ←/→ carry the ranking. The geometry is
    /// `SearchResultsModel.destination`, exercised exhaustively — ragged rows, short pages, the
    /// empty page — in `SearchSurfaceTests`; what this covers is the model driving it, on the same
    /// four-card page as before.
    @MainActor
    func testTheKeyboardStepsThroughTheResultsAndStopsAtBothEnds() {
        // Four cards, three across: rows [0 1 2] [3].
        let moments = (1...4).map { Self.screenMoment(id: Int64($0), at: 1_700_000_000 + Double($0)) }
        let model = SearchResultsModel(moments: moments, query: "invoice")

        // At rest the keyboard is in the field, which is what makes Return mean "ask again".
        XCTAssertNil(model.selection)
        XCTAssertNil(model.selectedMoment)

        model.move(.down)
        XCTAssertEqual(model.selectedMoment?.id, moments[0].id, "↓ enters at the best answer")

        model.move(.right)
        model.move(.right)
        XCTAssertEqual(model.selectedMoment?.id, moments[2].id, "→ walks the ranking")

        model.move(.left)
        XCTAssertEqual(model.selectedMoment?.id, moments[1].id)

        for _ in 0..<10 { model.move(.down) }
        XCTAssertEqual(
            model.selectedMoment?.id, moments[3].id,
            "the selection wrapped or ran off the end — either one loses the user's place")
        for _ in 0..<10 { model.move(.up) }
        XCTAssertEqual(
            model.selectedMoment?.id, moments[0].id,
            "↑ off the top row must hold the selection, not drop it and re-enter at the far end")

        // ↑ from the field enters at the far end, which is what an "up from nothing" press means.
        model.clearSelection()
        model.move(.up)
        XCTAssertEqual(model.selectedMoment?.id, moments[3].id)

        // An empty answer has nothing to select, and pressing the key at it is not an error.
        let empty = SearchResultsModel(moments: [])
        empty.move(.down)
        XCTAssertNil(empty.selection)
    }

    /// A selection the next answer no longer contains is dropped, and one it still holds is kept.
    ///
    /// Both halves matter. Keeping a stale id would leave Return pointing at a card that is not on
    /// screen; dropping one that survived would cost somebody their place every time a chip merely
    /// reordered the page.
    @MainActor
    func testASelectionSurvivesAReReadOnlyWhileItsMomentDoes() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("handoff-selection-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))

        let base: Double = 1_760_000_000
        _ = try store.insertFrame(
            Frame(
                capturedAt: base, appName: "Preview", bundleId: nil, windowTitle: "Invoice 2026-07",
                ocrText: "amount due", imagePath: "/tmp/handoff-sel-1.heic"))
        _ = try store.insertFrame(
            Frame(
                capturedAt: base + 30, appName: "Finder", bundleId: nil, windowTitle: "Downloads",
                ocrText: "screenshots", imagePath: "/tmp/handoff-sel-2.heic"))

        let model = SearchResultsModel(store: { store })
        model.ask("")
        XCTAssertEqual(model.moments.count, 2)

        // Step to the end of the page. With nothing typed the order is pure recency, so the last
        // card is the older of the two frames — the invoice.
        for _ in 0..<5 { model.move(.down) }
        let invoice = try XCTUnwrap(model.selectedMoment)
        XCTAssertTrue(
            invoice.title.contains("Invoice"),
            "the browsing order is no longer newest-first, so this fixture selects the wrong card")

        // Still in the answer after a narrower question, so the place is kept.
        model.ask("invoice")
        XCTAssertEqual(
            model.selectedMoment?.id, invoice.id,
            "a moment that survived the re-read lost its selection anyway")

        // …and gone from it after one it cannot satisfy.
        model.ask("screenshots")
        XCTAssertNil(
            model.selection,
            "Return would have opened a card that is no longer on screen")
    }

    // MARK: - Fixtures

    private static func screenMoment(id: Int64, at: Double) -> SearchMoment {
        SearchMoment(
            rowId: id, title: "Invoice \(id)", source: "Preview", appName: "Preview",
            bundleId: nil, capturedAt: at, frame: nil)
    }
}
