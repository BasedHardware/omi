import ContextCore
import XCTest

@testable import ContextApp

/// What the Activity list is allowed to say about a day.
///
/// Every claim here is one a screenshot cannot make and a refactor can quietly break: that the list
/// still runs newest-first, that a frame attaches to the conversation it actually happened inside,
/// that a day header still counts the *day* rather than what survived a filter, and that the hour
/// rail still runs the same direction as the list beside it.
///
/// The composer is a pure function of its inputs precisely so this file can exist: composition is
/// the part with rules in it, and rules that can only be checked by looking at a window are rules
/// that drift.
final class ActivityCompositionTests: XCTestCase {

    // MARK: - Fixtures

    /// Fixed to UTC so day grouping is the same claim on every machine that runs this.
    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }()

    private func at(day: Int, hour: Int, minute: Int = 0) -> Date {
        Self.calendar.date(
            from: DateComponents(year: 2025, month: 6, day: day, hour: hour, minute: minute))!
    }

    private func startOfDay(_ day: Int) -> Date {
        Self.calendar.startOfDay(for: at(day: day, hour: 12))
    }

    private func session(
        id: Int64, start: Date, minutes: Double, app: String? = "Zoom", lines: Int = 4,
        preview: String = "we talked about pricing"
    ) -> SessionSummary {
        SessionSummary(
            id: id,
            startedAt: start.timeIntervalSince1970,
            endedAt: start.addingTimeInterval(minutes * 60).timeIntervalSince1970,
            durationSeconds: minutes * 60,
            appHint: app,
            lineCount: lines,
            bothSidesPresent: true,
            preview: preview)
    }

    private func moment(id: Int64, at timestamp: Date, app: String = "Xcode") -> ActivityMoment {
        ActivityMoment(
            id: id, timestamp: timestamp, appName: app, bundleId: nil, windowTitle: nil,
            imagePath: "/frames/\(id).heic")
    }

    private func screen(_ day: Int, _ moments: [ActivityMoment], total: Int? = nil)
        -> [Date: ActivityDayScreen]
    {
        var hourCounts = [Int](repeating: 0, count: 24)
        for moment in moments {
            hourCounts[Self.calendar.component(.hour, from: moment.timestamp)] += 1
        }
        return [
            startOfDay(day): ActivityDayScreen(
                total: total ?? moments.count, hourCounts: hourCounts, sampled: moments)
        ]
    }

    private func compose(
        sessions: [SessionSummary] = [], screen: [Date: ActivityDayScreen] = [:]
    ) -> [ActivityDay] {
        ActivityComposer.compose(sessions: sessions, screen: screen, calendar: Self.calendar)
    }

    // MARK: - Order

    /// **Newest first, days and rows alike.** The whole surface is an argument that the list runs
    /// the same direction as the clock beside it, and an ascending day would break that silently:
    /// nothing about a single screenshot of one day would look wrong.
    func testDaysAndRowsRunNewestFirst() {
        let days = compose(
            sessions: [
                session(id: 1, start: at(day: 10, hour: 9), minutes: 5),
                session(id: 2, start: at(day: 10, hour: 17), minutes: 5),
                session(id: 3, start: at(day: 11, hour: 8), minutes: 5),
            ])

        XCTAssertEqual(days.map(\.id), [startOfDay(11), startOfDay(10)])
        XCTAssertEqual(days[1].rows.map(\.id), ["conv:2", "conv:1"], "the later conversation leads")
        XCTAssertEqual(
            days.flatMap(\.rows).map(\.anchor), days.flatMap(\.rows).map(\.anchor).sorted(by: >))
    }

    // MARK: - Attachment

    /// A frame captured inside a conversation's window belongs to that conversation, renders
    /// **immediately after it**, and is indented. A frame outside every window stands on its own.
    func testFramesAttachOnlyInsideAConversationsWindowAndSitDirectlyUnderIt() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            screen: screen(
                10,
                [
                    // Well before the conversation, and far enough away to be its own cluster.
                    moment(id: 10, at: at(day: 10, hour: 9)),
                    moment(id: 11, at: start.addingTimeInterval(60)),
                    moment(id: 12, at: start.addingTimeInterval(20 * 60)),
                ]))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), ["conv:1", "conv-shot:1", "shot:10"])

        let attached = rows[1]
        XCTAssertTrue(attached.isAttached, "a frame inside the window is a child of the row above")
        guard case .moments(let shown, let total) = attached.content else {
            return XCTFail("the attached row is a strip")
        }
        XCTAssertEqual(shown.map(\.id), [12, 11], "newest first inside the strip too")
        XCTAssertEqual(total, 2)

        XCTAssertFalse(rows[2].isAttached, "a frame outside every window stands on its own")
    }

    /// **The two-pointer pass must not walk off the end.** A frame newer than every conversation
    /// advances the cursor past all of them; if that advance were driven by `finishedAt` rather than
    /// by `startedAt`, every *older* frame behind it would then find no conversation to belong to
    /// and the whole day would come apart into loose strips.
    func testAFrameNewerThanEveryConversationDoesNotOrphanTheOnesBehindIt() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            screen: screen(
                10,
                [
                    // After the conversation ended, and after it started — the cursor-walking case.
                    moment(id: 20, at: at(day: 10, hour: 23)),
                    moment(id: 21, at: start.addingTimeInterval(5 * 60)),
                ]))

        let rows = try! XCTUnwrap(days.first).rows
        let attached = rows.first { $0.id == "conv-shot:1" }
        XCTAssertNotNil(attached, "the frame inside the window must still find its conversation")
        guard case .moments(let shown, _)? = attached?.content else {
            return XCTFail("the attached row is a strip")
        }
        XCTAssertEqual(shown.map(\.id), [21])
        XCTAssertTrue(
            rows.contains { $0.id == "shot:20" }, "the newer frame is a loose strip of its own")
    }

    // MARK: - Filtering

    /// Soloing a kind flattens every attachment: with nothing above a strip to own the minute, the
    /// strip has to state its own time, which is what `isAttached == false` turns on.
    func testSoloingAKindFlattensAttachment() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            screen: screen(10, [moment(id: 30, at: start.addingTimeInterval(60))]))

        XCTAssertTrue(days[0].rows.contains { $0.isAttached }, "unfiltered, the strip is a child")

        let soloed = ActivityComposer.filter(days, kind: .screen, query: "")
        XCTAssertEqual(soloed.flatMap(\.rows).map(\.kind), [.screen])
        XCTAssertTrue(
            soloed.flatMap(\.rows).allSatisfy { !$0.isAttached },
            "a soloed row has nothing above it to inherit a timestamp from")
    }

    /// A day with nothing left is dropped **whole** — header and all. A sticky day header over no
    /// rows is a heading for content that is not there.
    func testAQueryDropsAnEmptyDayWholeRatherThanLeavingItsHeader() {
        let days = compose(
            sessions: [
                session(id: 1, start: at(day: 10, hour: 9), minutes: 5, app: "Zoom"),
                session(id: 2, start: at(day: 11, hour: 9), minutes: 5, app: "Slack"),
            ])
        XCTAssertEqual(days.count, 2)

        let filtered = ActivityComposer.filter(days, kind: .everything, query: "slack")
        XCTAssertEqual(filtered.map(\.id), [startOfDay(11)])
    }

    /// **The day header counts the day, not the filter.** A header that shrank with the query would
    /// leave nothing on screen able to say what was being hidden — and the count is the whole of a
    /// collapsed day.
    func testDayHeaderCountsSurviveFiltering() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [
                session(id: 1, start: start, minutes: 30, app: "Zoom"),
                session(id: 2, start: at(day: 10, hour: 18), minutes: 5, app: "Slack"),
            ],
            screen: screen(10, [moment(id: 40, at: start.addingTimeInterval(60))], total: 1_204))

        let unfiltered = try! XCTUnwrap(days.first)
        XCTAssertEqual(unfiltered.momentCount, 1_204)
        XCTAssertEqual(unfiltered.conversationCount, 2)

        let filtered = try! XCTUnwrap(
            ActivityComposer.filter(days, kind: .conversations, query: "slack").first)
        XCTAssertEqual(filtered.rows.count, 1, "the filter really did narrow the rows")
        XCTAssertEqual(filtered.momentCount, 1_204, "the header still describes the whole day")
        XCTAssertEqual(filtered.conversationCount, 2)
    }

    /// The time bound drops rows that fall before it, and takes the day with them when nothing is
    /// left.
    func testTheEarliestBoundDropsRowsBeforeIt() {
        let days = compose(
            sessions: [
                session(id: 1, start: at(day: 10, hour: 9), minutes: 5),
                session(id: 2, start: at(day: 10, hour: 18), minutes: 5),
            ])

        let filtered = ActivityComposer.filter(
            days, kind: .everything, query: "", earliest: at(day: 10, hour: 12))
        XCTAssertEqual(filtered.flatMap(\.rows).map(\.id), ["conv:2"])
    }

    // MARK: - Clusters

    /// Forty-five minutes ends a run. Under it, two frames are one strip; over it, they are two —
    /// which is what stops a morning and an evening becoming one row.
    func testClustersSplitOnTheFortyFiveMinuteGap() {
        let anchor = at(day: 10, hour: 9)
        let gap = ActivityComposer.momentClusterGap

        let together = ActivityComposer.clusters(of: [
            moment(id: 1, at: anchor),
            moment(id: 2, at: anchor.addingTimeInterval(-gap)),
        ])
        XCTAssertEqual(together.count, 1, "exactly the gap is still one run — the split is on >")

        let apart = ActivityComposer.clusters(of: [
            moment(id: 1, at: anchor),
            moment(id: 2, at: anchor.addingTimeInterval(-gap - 1)),
        ])
        XCTAssertEqual(apart.map { $0.map(\.id) }, [[1], [2]])
    }

    /// A cluster draws at most `momentsPerStrip` tiles and **retains the true total**: a strip that
    /// silently shows 8 of 184 is a strip that lies about the day.
    func testAStripCapsWhatItShowsAndKeepsWhatThereWas() {
        let anchor = at(day: 10, hour: 9)
        let moments = (0..<20).map { index in
            moment(id: Int64(100 + index), at: anchor.addingTimeInterval(Double(index) * 60))
        }
        let days = compose(screen: screen(10, moments))

        guard case .moments(let shown, let total)? = days.first?.rows.first?.content else {
            return XCTFail("a day of nothing but frames is one strip")
        }
        XCTAssertEqual(shown.count, ActivityComposer.momentsPerStrip)
        XCTAssertEqual(total, 20)
    }

    // MARK: - Dedupe

    /// A repeated record is a repeated SwiftUI identity, which in a `ForEach` is undefined behaviour
    /// rather than a cosmetic duplicate. First sighting wins, order preserved.
    func testARepeatedRecordProducesOneRow() {
        let start = at(day: 10, hour: 14)
        let repeated = session(id: 1, start: start, minutes: 30)
        let frame = moment(id: 50, at: start.addingTimeInterval(60))

        let days = compose(
            sessions: [repeated, repeated],
            screen: screen(10, [frame, frame], total: 2))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), ["conv:1", "conv-shot:1"])
        guard case .moments(let shown, let total) = rows[1].content else {
            return XCTFail("the attached row is a strip")
        }
        XCTAssertEqual(shown.map(\.id), [50], "the same frame twice is one tile")
        XCTAssertEqual(total, 1)
    }

    // MARK: - Counting

    /// **`matchCount` counts things, not rows.** One strip can stand for a hundred and eighty-four
    /// frames, and a count line that reported rows would tell the user their day was eleven moments
    /// long.
    func testMatchCountCountsThingsNotRows() {
        let anchor = at(day: 10, hour: 9)
        let moments = (0..<20).map { index in
            moment(id: Int64(200 + index), at: anchor.addingTimeInterval(Double(index) * 60))
        }
        let days = compose(
            sessions: [session(id: 1, start: at(day: 10, hour: 18), minutes: 5)],
            screen: screen(10, moments))

        let day = try! XCTUnwrap(days.first)
        XCTAssertEqual(day.rows.count, 2, "one conversation and one capped strip")
        XCTAssertEqual(day.matchCount, 21, "one conversation plus twenty frames")
    }

    // MARK: - Sampling

    /// The sample is spread across the run rather than taken off the front. Taking the first N would
    /// show a busy day as its last twenty minutes and leave the rest of it looking empty.
    func testEvenSamplingSpreadsAcrossTheRunAndIsANoOpUnderTheCeiling() {
        let anchor = at(day: 10, hour: 0)
        let moments = (0..<100).map { index in
            moment(id: Int64(index), at: anchor.addingTimeInterval(Double(index) * 60))
        }

        let sampled = ActivityComposer.evenlySampled(moments, ceiling: 10)
        XCTAssertEqual(sampled.count, 10)
        XCTAssertEqual(sampled.map(\.id), [0, 10, 20, 30, 40, 50, 60, 70, 80, 90])

        XCTAssertEqual(
            ActivityComposer.evenlySampled(moments, ceiling: 240).map(\.id), moments.map(\.id),
            "a run under the ceiling is returned whole")
        XCTAssertTrue(ActivityComposer.evenlySampled(moments, ceiling: 0).isEmpty)
    }

    // MARK: - Copy

    func testDurationReadsAsTimeRatherThanSeconds() {
        XCTAssertEqual(ActivityFormat.duration(42), "42s")
        XCTAssertEqual(ActivityFormat.duration(489), "8m 9s")
        XCTAssertEqual(ActivityFormat.duration(3_840), "1h 04m")
        XCTAssertEqual(ActivityFormat.duration(0), "0s")
    }

    /// Zero clauses are dropped rather than shown as "0 screen moments", which reads as a defect
    /// rather than as an absence — and a row with nothing to say falls back to its time.
    func testAConversationSubtitleDropsItsEmptyClauses() {
        let quiet = ActivityConversation(
            session: session(id: 1, start: at(day: 10, hour: 14), minutes: 8.15, lines: 0))
        XCTAssertEqual(quiet.subtitle, "8m 9s")

        let full = ActivityConversation(
            session: session(id: 2, start: at(day: 10, hour: 14), minutes: 8.15, lines: 4),
            momentCount: 6)
        XCTAssertEqual(full.subtitle, "8m 9s · 4 spoken lines · 6 screen moments")

        let instant = ActivityConversation(
            session: session(id: 3, start: at(day: 10, hour: 14), minutes: 0, lines: 0))
        XCTAssertEqual(
            instant.subtitle, ActivityFormat.time(at(day: 10, hour: 14)),
            "a row with no counts still says when it happened")
    }

    func testPluralAgreesWithItsCountAndGroupsItsDigits() {
        XCTAssertEqual(ActivityFormat.plural(1, "moment", "moments"), "1 moment")
        XCTAssertEqual(ActivityFormat.plural(0, "moment", "moments"), "0 moments")
        XCTAssertEqual(ActivityFormat.number(1_204).filter(\.isNumber), "1204")
        XCTAssertGreaterThan(
            ActivityFormat.number(1_204).count, 4, "four figures are grouped, not run together")
    }

    /// Nobody reads their own morning as a date.
    func testDayNamesTheTwoDaysADateIsTheWrongAnswerFor() {
        let calendar = Calendar.current
        let now = Date()
        XCTAssertEqual(ActivityFormat.day(now, calendar: calendar, now: now), "Today")

        let yesterday = calendar.date(byAdding: .day, value: -1, to: now)!
        XCTAssertEqual(ActivityFormat.day(yesterday, calendar: calendar, now: now), "Yesterday")

        // 400 days always crosses a year boundary, which is the branch that adds the year.
        let old = calendar.date(byAdding: .day, value: -400, to: now)!
        let label = ActivityFormat.day(old, calendar: calendar, now: now)
        XCTAssertFalse(["Today", "Yesterday"].contains(label))
        XCTAssertTrue(
            label.contains(String(calendar.component(.year, from: old))),
            "a day outside this year has to say which year it was: \(label)")
    }

    func testHourLabelsNameNoonAndMidnightRatherThanZero() {
        XCTAssertEqual(ActivityFormat.hourLabel(0), "12 AM")
        XCTAssertEqual(ActivityFormat.hourLabel(6), "6 AM")
        XCTAssertEqual(ActivityFormat.hourLabel(12), "12 PM")
        XCTAssertEqual(ActivityFormat.hourLabel(18), "6 PM")
        XCTAssertEqual(ActivityFormat.hourLabel(23), "11 PM")
    }

    // MARK: - The rail

    /// **The rail runs the same direction as the list beside it, and that is the whole point of it.**
    /// An ascending rail next to a newest-first list puts 6 AM at the top of a column whose top row
    /// is 11 PM, and the two disagree about which way time runs.
    func testTheHourRailRunsLatestFirst() {
        XCTAssertEqual(ActivityHourRail.renderedHours.first, 23)
        XCTAssertEqual(ActivityHourRail.renderedHours.last, 0)
        XCTAssertEqual(ActivityHourRail.renderedHours.count, 24)
        XCTAssertEqual(Set(ActivityHourRail.renderedHours).count, 24, "every hour, exactly once")
        XCTAssertEqual(
            ActivityHourRail.renderedHours, ActivityHourRail.renderedHours.sorted(by: >),
            "descending, like the list")
    }

    /// `nil` is not zero. A day nobody has read yet has no count, and printing a confident `0` for
    /// it is a claim about the machine the rail has no evidence for.
    func testTheRailDistinguishesAnUnreadDayFromAnEmptyOne() {
        XCTAssertEqual(ActivityHourRail.headlineNumber(nil), "—")
        XCTAssertEqual(ActivityHourRail.headlineCaption(nil), "counting screen moments")
        XCTAssertEqual(ActivityHourRail.headlineNumber(0), "0")
        XCTAssertEqual(ActivityHourRail.headlineCaption(0), "screen moments")
        XCTAssertEqual(ActivityHourRail.headlineCaption(1), "screen moment")
        XCTAssertNil(ActivityHourRail.footer(conversationCount: 0), "no blank line for no answer")
    }

    // MARK: - The kind axis

    /// `everything` is the absence of a filter, not a third kind of row. A row that held it would be
    /// invisible to both chips.
    func testNoRowIsEverEverything() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            screen: screen(10, [moment(id: 60, at: start.addingTimeInterval(60))]))

        XCTAssertFalse(days.flatMap(\.rows).contains { $0.kind == .everything })
        XCTAssertEqual(ActivityKind.chips, [.everything, .conversations, .screen])
        XCTAssertEqual(
            ActivityKind.chips.map(\.title), ["Activity", "Conversations", "Screens"])
    }

    // MARK: - The day walk

    /// The walk covers the whole window, newest first, and stops at its ceiling rather than at the
    /// oldest row in a database that may be years deep.
    func testTheDayWalkIsNewestFirstAndBounded() {
        let coverage = at(day: 1, hour: 0).timeIntervalSince1970...at(day: 10, hour: 23)
            .timeIntervalSince1970
        let days = ActivityStore.enumerateDays(
            coverage: coverage, since: nil, until: nil, calendar: Self.calendar)
        XCTAssertEqual(days.first, startOfDay(10))
        XCTAssertEqual(days.last, startOfDay(1))
        XCTAssertEqual(days.count, 10)

        XCTAssertEqual(
            ActivityStore.enumerateDays(
                coverage: coverage, since: nil, until: nil, calendar: Self.calendar, ceiling: 3),
            [startOfDay(10), startOfDay(9), startOfDay(8)])

        XCTAssertTrue(
            ActivityStore.enumerateDays(
                coverage: nil, since: nil, until: nil, calendar: Self.calendar
            ).isEmpty,
            "a machine that has captured nothing has no days to walk")
    }
}
