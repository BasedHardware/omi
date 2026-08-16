import Combine
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

    private func accountConversation(
        id: String, start: Date, minutes: Double, title: String = "Team Refines Omi Update Video",
        emoji: String = "🎬", overview: String? = nil
    ) -> ActivityAccountConversation {
        ActivityAccountConversation(
            id: id,
            title: title,
            emoji: emoji,
            startedAt: start.timeIntervalSince1970,
            finishedAt: start.addingTimeInterval(minutes * 60).timeIntervalSince1970,
            overview: overview)
    }

    private func accountMemory(
        id: String, at timestamp: Date, content: String = "prefers async",
        conversation: String? = nil
    ) -> ActivityAccountMemory {
        ActivityAccountMemory(
            id: id, content: content, at: timestamp.timeIntervalSince1970,
            conversationID: conversation)
    }

    private func accountTask(
        id: String, at timestamp: Date, text: String = "send the deck", completed: Bool = false
    ) -> ActivityAccountTask {
        ActivityAccountTask(
            id: id, text: text, completed: completed, at: timestamp.timeIntervalSince1970)
    }

    /// - Parameter isAirgapped: stated rather than defaulted so no test in this file consults
    ///   `ExclusionEngine.shared` — the answer would then depend on the machine the suite runs on.
    private func compose(
        sessions: [SessionSummary] = [],
        uploads: [Int64: [String]] = [:],
        account: ActivityAccountFeed = .unreachable,
        screen: [Date: ActivityDayScreen] = [:],
        isAirgapped: Bool = false
    ) -> [ActivityDay] {
        ActivityComposer.compose(
            sessions: sessions, uploads: uploads, account: account, screen: screen,
            calendar: Self.calendar, isAirgapped: { isAirgapped })
    }

    /// The id a local session takes in the merged stream, so the assertions below read as the rule
    /// rather than as a string somebody typed twice.
    private func localRow(_ sessionID: Int64) -> String {
        "conv:\(ActivityConversation.localID(sessionID))"
    }

    private func localShotRow(_ sessionID: Int64) -> String {
        "conv-shot:\(ActivityConversation.localID(sessionID))"
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
        XCTAssertEqual(
            days[1].rows.map(\.id), [localRow(2), localRow(1)],
            "the later conversation leads")
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
        XCTAssertEqual(rows.map(\.id), [localRow(1), localShotRow(1), "shot:10"])

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
        let attached = rows.first { $0.id == localShotRow(1) }
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

        let soloed = ActivityComposer.filter(days, kind: .rewind, query: "")
        XCTAssertEqual(soloed.flatMap(\.rows).map(\.kind), [.rewind])
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

        let filtered = ActivityComposer.filter(days, kind: .all, query: "slack")
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
            days, kind: .all, query: "", earliest: at(day: 10, hour: 12))
        XCTAssertEqual(filtered.flatMap(\.rows).map(\.id), [localRow(2)])
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
        XCTAssertEqual(rows.map(\.id), [localRow(1), localShotRow(1)])
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
            session: session(id: 2, start: at(day: 10, hour: 14), minutes: 8.15, lines: 4)
        ).counted(momentCount: 6)
        XCTAssertEqual(full.subtitle, "8m 9s · 4 spoken lines · 6 screen moments")

        let instant = ActivityConversation(
            session: session(id: 3, start: at(day: 10, hour: 14), minutes: 0, lines: 0))
        XCTAssertEqual(
            instant.subtitle, ActivityFormat.time(at(day: 10, hour: 14)),
            "a row with no counts still says when it happened")

        // An account conversation is a summary, not a recording: it has no spoken lines to count, so
        // the clause is dropped rather than printed as "0 spoken lines". What it can state is what
        // it produced — the shipping app's own clause set.
        let fromAccount = ActivityConversation(
            account: accountConversation(id: "a1", start: at(day: 10, hour: 14), minutes: 8.15))
        XCTAssertEqual(fromAccount.subtitle, "8m 9s")
        XCTAssertEqual(
            fromAccount.counted(memoryCount: 2, momentCount: 6).subtitle,
            "8m 9s · 2 memories · 6 screen moments")
        XCTAssertEqual(fromAccount.title, "Team Refines Omi Update Video")
        XCTAssertEqual(fromAccount.emoji, "🎬")
    }

    /// **A row is never given a title nobody wrote.** This surface used to build one out of the
    /// capture session's app hint — "Arc conversation", "Warp conversation" — which named the window
    /// the sound came through rather than what was said, disagreed with what the same conversation is
    /// called everywhere else in Omi, and was indistinguishable from a real title. The shipping app's
    /// two fallbacks are the whole vocabulary for an unnamed conversation, and they are the same two
    /// on both halves of this stream.
    func testAConversationNobodyTitledSaysSoRatherThanNamingTheApp() {
        let local = ActivityConversation(
            session: session(id: 1, start: at(day: 10, hour: 14), minutes: 5, app: "Arc"))
        XCTAssertEqual(local.title, "Untitled conversation")
        XCTAssertEqual(local.emoji, "💬")
        XCTAssertTrue(
            local.searchText.contains("arc"),
            "the app the sound came through is still reachable by a typed query, just not a headline")

        // The account's own untitled conversations land on exactly the same two strings.
        let untitled = ActivityConversation(
            account: accountConversation(
                id: "a1", start: at(day: 10, hour: 14), minutes: 5, title: "  ", emoji: " "))
        XCTAssertEqual(untitled.title, "Untitled conversation")
        XCTAssertEqual(untitled.emoji, "💬")
    }

    /// **The overview is search material, not row copy.** It is a paragraph about what the
    /// conversation was about; the row states what it *was*. The shipping app carries it into
    /// `searchText` and nowhere else, and a typed query still has to reach it.
    func testTheOverviewIsSearchableAndIsNotSaidOnTheRow() {
        let conversation = ActivityConversation(
            account: accountConversation(
                id: "a1", start: at(day: 10, hour: 14), minutes: 8.15,
                overview: "We agreed to hold the enterprise tier until the beta lands.")
        ).counted(momentCount: 6)
        XCTAssertTrue(conversation.searchText.contains("enterprise tier"))
        XCTAssertFalse(conversation.subtitle.contains("enterprise"))
        XCTAssertEqual(conversation.subtitle, "8m 9s · 6 screen moments")
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

    /// **The scope line has to fit the column it is drawn in**, and unshortened it does not:
    /// `ActivityFormat.day` emits `EEEE d MMMM yyyy` outside the current year, whose widest form
    /// overhangs the 154 pt rail by nearly 30 pt and wraps — orphaning "Wednesday 30" directly above
    /// the bars, where a bare number-and-word line reads as another count.
    ///
    /// The weekday is the one word carrying nothing the date does not already say, so it is what
    /// goes; everything that fits keeps it. Measured against the column rather than asserted from a
    /// hand-picked date, which is how the overhang went unseen in the first place.
    func testTheRailScopeDropsTheWeekdayOnlyWhenTheFullDayWillNotFit() {
        XCTAssertEqual(
            ActivityHourRail.headlineScope("Wednesday 30 September 2026"), "30 September 2026",
            "the formatter's widest output, against a 154 pt column")
        XCTAssertEqual(
            ActivityHourRail.headlineScope("Tuesday 22 September 2026"), "22 September 2026")

        XCTAssertEqual(ActivityHourRail.headlineScope("Today"), "Today")
        XCTAssertEqual(ActivityHourRail.headlineScope("Yesterday"), "Yesterday")
        XCTAssertEqual(
            ActivityHourRail.headlineScope("Wednesday 6 August"), "Wednesday 6 August",
            "fits, so it keeps its weekday")

        XCTAssertEqual(
            ActivityHourRail.headlineScope("Supercalifragilisticexpialidociously"),
            "Supercalifragilisticexpialidociously",
            "a single word there is no weekday to drop from keeps its text rather than losing the day")
        XCTAssertNil(ActivityHourRail.headlineScope("   "), "no day yet is no scope to claim")
    }

    // MARK: - The kind axis

    /// `everything` is the absence of a filter, not a third kind of row. A row that held it would be
    /// invisible to both chips.
    func testNoRowIsEverAll() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            account: ActivityAccountFeed(
                memories: [accountMemory(id: "m1", at: at(day: 10, hour: 11))],
                tasks: [accountTask(id: "t1", at: at(day: 10, hour: 12))]),
            screen: screen(10, [moment(id: 60, at: start.addingTimeInterval(60))]))

        XCTAssertFalse(days.flatMap(\.rows).contains { $0.kind == .all })
        XCTAssertEqual(
            ActivityKind.chips, [.all, .conversations, .memories, .tasks, .rewind])
        XCTAssertEqual(
            ActivityKind.chips.map(\.title),
            ["All", "Conversations", "Memories", "Tasks", "Rewind"])
    }

    // MARK: - The account half

    /// **The account's telling of a conversation wins over this Mac's.** They are one conversation
    /// described twice — the Mac heard the speech, the account summarised it — and showing both would
    /// print every conversation on the spine as a pair the moment somebody signs in.
    func testALocalSessionOverlappingAnAccountConversationIsDroppedForIt() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [
                // Starts a minute after the account's, which is the ordinary case: two clocks, one
                // conversation.
                session(id: 1, start: start.addingTimeInterval(60), minutes: 28),
                // Hours away from anything the account knows about.
                session(id: 2, start: at(day: 10, hour: 20), minutes: 10, app: "Slack"),
            ],
            account: ActivityAccountFeed(
                conversations: [accountConversation(id: "a1", start: start, minutes: 30)]))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(
            rows.map(\.id), [localRow(2), "conv:a1"],
            "the overlapping local session is gone; the one with no counterpart survives")

        guard case .conversation(let survivor) = rows[0].content,
            case .conversation(let fromAccount) = rows[1].content
        else { return XCTFail("both rows are conversations") }
        XCTAssertEqual(survivor.source, .local)
        XCTAssertEqual(survivor.title, "Untitled conversation", "no title means no title")
        XCTAssertEqual(fromAccount.source, .account)
        XCTAssertEqual(fromAccount.title, "Team Refines Omi Update Video")
        XCTAssertEqual(
            try! XCTUnwrap(days.first).conversationCount, 2,
            "the day counts the conversations it kept, not the records it read")
    }

    /// **The uploader already knows which account conversation a session became, and that beats the
    /// clock.** `ConversationUploader` records the ids the backend handed back, so a session and its
    /// summary can be recognised as one conversation even when their windows do not overlap — which
    /// is routine, because the account times a conversation from the recording it received and this
    /// Mac from the first line it heard. Without the link the two clocks disagreeing printed the day
    /// as a pair: the real title, and an untitled duplicate of the same conversation beside it.
    func testAnUploadedSessionMergesIntoItsAccountConversationEvenWhenTheClocksDisagree() {
        let days = compose(
            sessions: [session(id: 1, start: at(day: 10, hour: 14), minutes: 28)],
            uploads: [1: ["a1"]],
            account: ActivityAccountFeed(
                conversations: [
                    // Two hours off: the same conversation, timed from the upload rather than from
                    // the first line heard. Nothing here overlaps.
                    accountConversation(id: "a1", start: at(day: 10, hour: 16), minutes: 30)
                ]))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), ["conv:a1"], "one conversation, one row")
        guard case .conversation(let only) = rows[0].content else {
            return XCTFail("the surviving row is the account's telling")
        }
        XCTAssertEqual(only.title, "Team Refines Omi Update Video")
        XCTAssertEqual(only.emoji, "🎬")
    }

    /// A session split across several uploads became several account conversations, and **any one of
    /// them being on a loaded page accounts for the session** — the parts are that conversation, so
    /// drawing the local row beside them would be drawing it a third time.
    func testASessionSplitAcrossSeveralUploadsIsAccountedForByAnyOfItsParts() {
        let days = compose(
            sessions: [session(id: 1, start: at(day: 10, hour: 9), minutes: 120)],
            uploads: [1: ["a1", "a2"]],
            account: ActivityAccountFeed(
                conversations: [
                    accountConversation(id: "a2", start: at(day: 10, hour: 20), minutes: 30)
                ]))

        XCTAssertEqual(try! XCTUnwrap(days.first).rows.map(\.id), ["conv:a2"])
    }

    /// **A session whose account counterpart has not been paged in yet keeps its row.** Same rule as
    /// a memory naming a conversation the stream is not holding: paging is a matter of timing, and a
    /// row that vanishes until the page lands is a day that under-reports itself. It merges the
    /// moment the account answers.
    func testAnUploadedSessionWhoseConversationIsNotLoadedKeepsItsRow() {
        let days = compose(
            sessions: [session(id: 1, start: at(day: 10, hour: 14), minutes: 28)],
            uploads: [1: ["a1"]],
            account: ActivityAccountFeed(conversations: [], reachable: true))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), [localRow(1)])
        guard case .conversation(let local) = rows[0].content else {
            return XCTFail("the surviving row is this Mac's telling")
        }
        XCTAssertEqual(local.source, .local)
        XCTAssertEqual(local.title, "Untitled conversation")
        XCTAssertEqual(local.subtitle, "28m 0s · 4 spoken lines")
    }

    /// **The link is the stronger rule, and it overrules an accidental overlap.** Two conversations
    /// can share a stretch of the day — a call while a meeting recording is still running — and the
    /// clock alone cannot tell that apart from one conversation described twice. The queue can: this
    /// session became `a2`, so `a1` sitting on top of it is somebody else's row.
    func testAnUploadedSessionIsNotDroppedForAConversationItDidNotBecome() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start.addingTimeInterval(60), minutes: 28)],
            uploads: [1: ["a2"]],
            account: ActivityAccountFeed(
                conversations: [accountConversation(id: "a1", start: start, minutes: 30)]))

        XCTAssertEqual(
            try! XCTUnwrap(days.first).rows.map(\.id), [localRow(1), "conv:a1"],
            "overlapping the wrong conversation is not being that conversation")
    }

    /// **A session the queue is still holding is not untitled, it is not yet uploaded — and the
    /// stream draws neither a title nor a placeholder for it.** Titles are written by the account
    /// when the transcript lands, so a queued session can only draw `Untitled conversation`, the
    /// string that means "nobody named this one". On the Mac this was found on, eighteen of the
    /// day's twenty sessions were queued behind a paused backend and the panel showed fifteen rows
    /// where the shipping app showed nine, the whole top of the list untitled and the real titles
    /// buried underneath. Each of those rows is about to *become* the account conversation, so the
    /// row is deferred rather than drawn twice.
    ///
    /// **What was on screen while it happened still draws**, on a run of its own — the stretch of
    /// the day is accounted for, and the backlog itself is stated where a backlog belongs, in the
    /// menu bar's "N conversations waiting to upload".
    func testASessionTheQueueIsStillHoldingDrawsNoConversationRow() {
        let start = at(day: 10, hour: 14)
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            // The queue holds it and owes it to an account; nothing has come back yet.
            uploads: [1: []],
            account: ActivityAccountFeed(conversations: [], reachable: true),
            screen: screen(10, [moment(id: 90, at: start.addingTimeInterval(600))]))

        let day = try! XCTUnwrap(days.first)
        XCTAssertEqual(
            day.rows.map(\.id), ["shot:90"],
            "no conversation row — and the frames captured during it are still on the day")
        XCTAssertEqual(day.conversationCount, 0, "a row that is not drawn is not counted either")
        XCTAssertFalse(day.rows[0].isAttached, "with no conversation to sit under, the run is loose")
    }

    /// **The queue saying nothing about a session is the case that keeps its row**, and it is the
    /// common one: a session captured while signed out is parked with no owner (`claimOrphans`), a
    /// session `skipped` for having nothing uploadable in it is finished with, and a session that
    /// predates the queue was never in it. None of them is waiting on a title that is coming, so
    /// each is a local conversation and draws as one — which is what stops a signed-out day from
    /// claiming nobody spoke.
    func testASessionTheQueueIsNotHoldingKeepsItsRow() {
        let days = compose(
            sessions: [
                session(id: 1, start: at(day: 10, hour: 9), minutes: 20),
                session(id: 2, start: at(day: 10, hour: 17), minutes: 20),
            ],
            uploads: [:],
            account: ActivityAccountFeed(conversations: [], reachable: true))

        XCTAssertEqual(
            try! XCTUnwrap(days.first).rows.map(\.id), [localRow(2), localRow(1)],
            "a session no upload is coming for is a conversation this Mac held")
    }

    /// **Airgap Mode is the queue saying "never", not "not yet".** Nothing is uploaded while the
    /// switch is on and the account feed is suppressed with it, so a panel that also deferred every
    /// queued session would show that user no conversations at all — the exact "you did not speak
    /// today" this whole surface exists to avoid. The entries stay in the queue, the rows stay on
    /// the day.
    func testAQueuedSessionKeepsItsRowWhileAirgapModeHoldsTheQueue() {
        let days = compose(
            sessions: [session(id: 1, start: at(day: 10, hour: 14), minutes: 30)],
            uploads: [1: []],
            isAirgapped: true)

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), [localRow(1)])
        guard case .conversation(let local) = rows[0].content else {
            return XCTFail("the surviving row is this Mac's telling")
        }
        XCTAssertEqual(local.source, .local)
    }

    /// Memories and tasks are their own rows, grouped by the run they came out of, and a memory the
    /// account named no conversation for **does not attach**: landing inside a conversation's window
    /// is a coincidence, and an attachment drawn from a timestamp is a claim the record does not
    /// support. A task never attaches at all — its seam carries no conversation id to attach by.
    func testMemoriesWithNoConversationAndTasksClusterIntoRowsAndNeverAttach() {
        let start = at(day: 10, hour: 14)
        let gap = ActivityComposer.momentClusterGap
        let days = compose(
            sessions: [session(id: 1, start: start, minutes: 30)],
            account: ActivityAccountFeed(
                memories: [
                    // Both inside the conversation's window, and close enough to be one run.
                    accountMemory(id: "m1", at: start.addingTimeInterval(120)),
                    accountMemory(id: "m2", at: start.addingTimeInterval(300)),
                    // Past the gap, so a second row.
                    accountMemory(id: "m3", at: start.addingTimeInterval(-gap - 1)),
                ],
                tasks: [accountTask(id: "t1", at: start.addingTimeInterval(180))]))

        let rows = try! XCTUnwrap(days.first).rows
        XCTAssertEqual(rows.map(\.id), ["mem:m2", "task:t1", localRow(1), "mem:m3"])
        XCTAssertTrue(
            rows.allSatisfy { !$0.isAttached },
            "nothing the account sent is a child of a conversation")

        guard case .memories(let run) = rows[0].content else { return XCTFail("a run of memories") }
        XCTAssertEqual(run.map(\.id), ["m2", "m1"], "newest first inside the row too")

        let day = try! XCTUnwrap(days.first)
        XCTAssertEqual(day.memoryCount, 3)
        XCTAssertEqual(day.taskCount, 1)
        XCTAssertEqual(
            day.matchCount, 5, "three memories, one task and one conversation — things, not rows")
    }

    /// **A memory the account attributes to a conversation is shown on that conversation's day, not
    /// on the day it was written.** Extraction runs after the fact, so a late conversation leaves a
    /// memory stamped the following morning — and filing that on its own instant is how a fact ends
    /// up on a day the user did not live it, under a day header the conversation is not even on.
    ///
    /// It also has to sit *directly under* its conversation once it is there: its timestamp puts it
    /// at the top of the day, so nothing but the re-seat can hold it to the thing it came out of.
    func testAMemoryFromALoadedConversationIsShownUnderItOnThatConversationsDay() throws {
        let days = compose(
            account: ActivityAccountFeed(
                conversations: [
                    accountConversation(id: "a1", start: at(day: 10, hour: 9), minutes: 40)
                ],
                memories: [
                    // The next morning by the clock, and the account says which conversation it came
                    // out of.
                    accountMemory(id: "m1", at: at(day: 11, hour: 9), conversation: "a1"),
                    // Nothing to attach to, hours after the conversation ended: stays where it is.
                    accountMemory(id: "loose", at: at(day: 10, hour: 20)),
                ]))

        XCTAssertEqual(
            days.map(\.id), [startOfDay(10)],
            "the attached memory did not open a day of its own on the day it was written")

        let day = try XCTUnwrap(days.first)
        XCTAssertEqual(
            day.rows.map(\.id), ["mem:loose", "conv:a1", "conv-mem:a1"],
            "re-seated under its conversation, not sorted to the top of the day by its timestamp")
        XCTAssertTrue(try XCTUnwrap(day.rows.last).isAttached)

        guard case .memories(let attached) = try XCTUnwrap(day.rows.last).content else {
            return XCTFail("the attached row is a memory")
        }
        XCTAssertEqual(attached.map(\.id), ["m1"])
        XCTAssertEqual(
            day.memoryCount, 2,
            "the header counts the memories the day shows, attached ones included")
        XCTAssertEqual(day.matchCount, 3)
    }

    /// **A memory naming a conversation the stream is not holding must not vanish.** The account
    /// pages independently of this window, so a memory routinely outlives the conversation's page —
    /// and dropping it, or filing it against a conversation that is not on screen to hold it, would
    /// silently delete a fact from the record. It stands on its own timestamp instead.
    func testAMemoryNamingAConversationTheStreamDoesNotHoldStillStandsOnItsOwnDay() throws {
        let days = compose(
            account: ActivityAccountFeed(
                conversations: [
                    accountConversation(id: "a1", start: at(day: 10, hour: 9), minutes: 40)
                ],
                memories: [
                    accountMemory(id: "m1", at: at(day: 11, hour: 9), conversation: "unloaded")
                ]))

        XCTAssertEqual(days.map(\.id), [startOfDay(11), startOfDay(10)])

        let day = try XCTUnwrap(days.first)
        XCTAssertEqual(day.rows.map(\.id), ["mem:m1"])
        XCTAssertFalse(
            try XCTUnwrap(day.rows.first).isAttached,
            "nothing on this day produced it, so it is a child of nothing")
        XCTAssertEqual(day.memoryCount, 1)
    }

    /// A day of nothing but memories still gets a header, and the header says what is in it.
    func testADayHeaderNamesEveryKindItHolds() {
        let days = compose(
            account: ActivityAccountFeed(
                memories: [accountMemory(id: "m1", at: at(day: 10, hour: 11))],
                tasks: [
                    accountTask(id: "t1", at: at(day: 10, hour: 12)),
                    accountTask(id: "t2", at: at(day: 10, hour: 13)),
                ]))

        let day = try! XCTUnwrap(days.first)
        XCTAssertEqual(day.subtitle, "1 memory · 2 tasks")
        XCTAssertEqual(day.thingCount, 3)
    }

    /// **Every kind the header counts is a kind the list drew, one for one.**
    ///
    /// The day header carries four numbers and only one of them is read off the rows
    /// (`ActivityDay.matchCount`); the other three are sums the composer keeps beside them, which is
    /// exactly the drift the reference avoids by deriving its memory and task counts from the rows.
    /// Soloing a kind is what makes the two comparable — a soloed stream draws nothing else — and it
    /// is also how this was checked on the real screen: `219 results · of 3,339`, `216 results`,
    /// `200 results`, against a header sum of 219 conversations, 216 memories and 200 tasks.
    ///
    /// The memory column is the one that could realistically drift: a day's memories are two
    /// populations (loose ones on their own clock, attached ones re-seated from another day) summed
    /// in two places, and only this catches a header counting one the list did not draw.
    func testEveryDayHeaderCountAgreesWithTheRowsTheListDraws() {
        let days = compose(
            account: ActivityAccountFeed(
                conversations: [
                    accountConversation(id: "c1", start: at(day: 10, hour: 9), minutes: 30),
                    accountConversation(id: "c2", start: at(day: 10, hour: 14), minutes: 20),
                ],
                memories: [
                    // Attached: extracted from c1 and timestamped the *next* morning, so it is
                    // counted on day 10 and would be counted on day 11 by any sum built from its own
                    // clock.
                    accountMemory(id: "m1", at: at(day: 11, hour: 8), conversation: "c1"),
                    accountMemory(id: "m2", at: at(day: 10, hour: 10)),
                    accountMemory(id: "m3", at: at(day: 10, hour: 10, minute: 20)),
                    // Names a conversation nothing in this stream holds: loose, on its own day.
                    accountMemory(id: "m4", at: at(day: 11, hour: 15), conversation: "gone"),
                ],
                tasks: [
                    accountTask(id: "t1", at: at(day: 10, hour: 16)),
                    accountTask(id: "t2", at: at(day: 10, hour: 16, minute: 10)),
                    accountTask(id: "t3", at: at(day: 11, hour: 9)),
                ]),
            screen: screen(10, [moment(id: 1, at: at(day: 10, hour: 20))]))

        for (kind, counted) in [
            (ActivityKind.conversations, \ActivityDay.conversationCount),
            (ActivityKind.memories, \ActivityDay.memoryCount),
            (ActivityKind.tasks, \ActivityDay.taskCount),
            (ActivityKind.rewind, \ActivityDay.momentCount),
        ] {
            let soloed = ActivityComposer.filter(days, kind: kind, query: "")
            XCTAssertEqual(
                soloed.reduce(0) { $0 + $1.matchCount },
                days.reduce(0) { $0 + $1[keyPath: counted] },
                "the headers count \(kind.title) the list does not draw")
        }
    }

    /// **The corner counts the account's rows, including on days this Mac has no capture for.**
    ///
    /// The report that opened this said the corner was "almost exactly the frame count" and was
    /// therefore ignoring the account. It was not: `3,334` was 2,700 showable frames plus 634
    /// account rows, and the resemblance to the 3,345 rows in `frames` was a coincidence — the
    /// surface counts *showable* frames (`imagePath IS NOT NULL`), which were 2,702 of them.
    ///
    /// What makes that worth a test rather than a note is the second half: the local day walk only
    /// ever reaches days that hold capture, so a corpus summed from day headers would miss the
    /// account's rows entirely unless the composer opens days for them. On the real account it opens
    /// 26 of them — 8 days of capture, 34 days composed.
    @MainActor
    func testTheCorpusCountsAccountRowsOnDaysThisMacNeverCaptured() {
        let days = compose(
            account: ActivityAccountFeed(
                conversations: [
                    accountConversation(id: "c1", start: at(day: 3, hour: 9), minutes: 30)
                ],
                memories: [accountMemory(id: "m1", at: at(day: 4, hour: 11))],
                tasks: [accountTask(id: "t1", at: at(day: 5, hour: 12))]),
            screen: screen(10, [moment(id: 1, at: at(day: 10, hour: 20))]))

        XCTAssertEqual(days.count, 4, "three account days the capture walk would never have opened")
        XCTAssertEqual(
            ActivityStore(days: days, calendar: Self.calendar).corpusTotal, 4,
            "one frame plus a conversation, a memory and a task")
    }

    /// **An unreachable account is not an empty one.** The local half of the stream still composes —
    /// a signed-out Mac shows the screen moments it has — and the empty copy says something else
    /// entirely when there is nothing left to show.
    func testAnUnreachableAccountStillLeavesTheLocalStreamStanding() {
        let anchor = at(day: 10, hour: 9)
        let days = compose(
            account: .unreachable,
            screen: screen(10, [moment(id: 70, at: anchor), moment(id: 71, at: anchor)]))

        XCTAssertEqual(days.flatMap(\.rows).map(\.kind), [.rewind])
        XCTAssertEqual(try! XCTUnwrap(days.first).momentCount, 2)

        let unreachable = ActivityEmptyCopy.resolve(
            isPreparing: false, readFailure: nil, query: "", kind: .memories,
            accountReachable: false)
        let empty = ActivityEmptyCopy.resolve(
            isPreparing: false, readFailure: nil, query: "", kind: .memories,
            accountReachable: true)
        XCTAssertNotEqual(
            unreachable, empty,
            "\"nobody answered\" and \"there was nothing\" are different claims")
        XCTAssertEqual(unreachable.headline, "I couldn't reach your Omi account.")
        XCTAssertEqual(empty.headline, "Nothing captured in this window yet.")
    }

    /// **Every reason an account is unreachable is a different sentence**, because each one leaves
    /// the reader in a different place. A rejected key is one action away from fixed; being signed
    /// out is not a fault; Airgap Mode is a switch they turned on. And none of the four may ever
    /// read like the fifth state — an account that genuinely holds nothing.
    func testEachUnreachableReasonSaysSomethingTheReaderCanActOn() throws {
        func copy(_ reason: ActivityAccountUnreachableReason?) -> ActivityEmptyCopy {
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: nil, query: "", kind: .memories,
                accountReachable: false, accountUnreachableReason: reason)
        }
        let genuinelyEmpty = ActivityEmptyCopy.resolve(
            isPreparing: false, readFailure: nil, query: "", kind: .memories, accountReachable: true)

        let rejected = copy(.keyRejected)
        XCTAssertEqual(
            rejected.headline, "Omi couldn't authenticate this Mac, so your account can't be read.")
        XCTAssertEqual(
            copy(.keyUnavailable), rejected,
            "a key that was never minted and one the account refused are the same thing to do about")
        XCTAssertTrue(
            try XCTUnwrap(rejected.detail).contains("not an empty account"),
            "the one thing an expired key must never be reported as")

        XCTAssertEqual(copy(.signedOut).headline, "Sign in to Omi to see your account here.")
        XCTAssertEqual(
            copy(.airgapped).headline, "Airgap Mode is on, so your Omi account isn't being read.")
        // No reason given — a preview, a fake, a reader with nothing to say — keeps the sentence
        // this surface has always shown rather than inventing a cause.
        XCTAssertEqual(copy(.noAnswer), copy(nil))
        XCTAssertEqual(copy(nil).headline, "I couldn't reach your Omi account.")

        for reason in [ActivityAccountUnreachableReason.airgapped, .signedOut, .keyUnavailable, .keyRejected, .noAnswer] {
            XCTAssertNotEqual(
                copy(reason), genuinelyEmpty,
                "\(reason) must never render as an account that holds nothing")
        }
    }

    /// **A machine that could not be asked outranks an account that answered.**
    ///
    /// The failure this pins was observed on a real launch: the capture database's first open threw,
    /// so no read ever ran, `readFailure` stayed nil and `isPreparing` was false — and the empty
    /// state fell all the way through to the account, telling somebody holding 2,837 captured frames
    /// to "Sign in to Omi to see your account here". True, irrelevant, and the most misleading
    /// sentence available at that moment.
    func testADatabaseThatNeverOpenedIsReportedBeforeTheAccountIs() throws {
        func copy(_ capture: ActivityCaptureAvailability) -> ActivityEmptyCopy {
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: nil, capture: capture, query: "", kind: .all,
                accountReachable: false, accountUnreachableReason: .signedOut)
        }

        XCTAssertEqual(copy(.opening).headline, "This Mac's capture isn't open yet.")
        XCTAssertEqual(copy(.unavailable).headline, "This Mac's capture didn't open.")
        XCTAssertEqual(
            copy(.open).headline, "Sign in to Omi to see your account here.",
            "an open database still lets the account explain itself")

        // …and neither of the two says the local half is on screen, because at that instant it is
        // not. That promise is what made the observed frame contradict itself.
        for capture in [ActivityCaptureAvailability.opening, .unavailable] {
            XCTAssertFalse(
                try XCTUnwrap(copy(capture).detail).contains("still show up here"),
                "\(capture) must not promise rows it has none of")
        }
        XCTAssertTrue(
            try XCTUnwrap(copy(.unavailable).detail).contains("open it again"),
            "a wait that gave up has to leave the reader somewhere to go")
        XCTAssertNotEqual(
            copy(.opening), copy(.unavailable),
            "\"being opened\" and \"never opened\" are a wait and a failure, not one state")
    }

    /// **A soloed chip decides which sources are even in scope**, and therefore what an empty list
    /// is allowed to blame.
    ///
    /// Two ways this went wrong, both visible in the render harness: `Rewind` — which shows nothing
    /// from the account at all — reported an account failure as the reason a day held no screen
    /// capture; and `Memories` — which excludes screen moments by definition — promised that "screen
    /// moments from this Mac still show up here" on a list that was filtering them out.
    func testAnEmptyChipOnlyBlamesTheSourcesItActuallyShows() throws {
        func copy(_ kind: ActivityKind) -> ActivityEmptyCopy {
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: nil, query: "", kind: kind,
                accountReachable: false, accountUnreachableReason: .signedOut)
        }

        XCTAssertEqual(
            copy(.rewind).headline, "Nothing captured in this window yet.",
            "the account is not a source of screen moments and may not be blamed for their absence")
        XCTAssertEqual(copy(.rewind).detail, "Screen moments appear here while screen capture is on.")

        for kind in [ActivityKind.conversations, .memories, .tasks] {
            let detail = try XCTUnwrap(copy(kind).detail)
            XCTAssertFalse(
                detail.contains("Screen moments"),
                "\(kind) excludes screen moments, so it may not promise them")
            XCTAssertTrue(detail.hasPrefix(kind.title))
        }
        XCTAssertTrue(
            try XCTUnwrap(copy(.all).detail).contains("Screen moments from this Mac still show up here"),
            "the merged view really is still showing them, and says so")
    }

    /// The local half's failures are the local half's. A soloed `Memories` is not explained by a
    /// database this surface was not asking anything of.
    func testTheLocalHalfsFailuresAreOnlyReportedWhereTheLocalHalfIsShown() {
        let readFailure = ActivityStore.readFailureNote
        XCTAssertEqual(
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: readFailure, capture: .unavailable, query: "",
                kind: .memories, accountReachable: true
            ).headline,
            "Nothing captured in this window yet.")
        XCTAssertEqual(
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: readFailure, capture: .unavailable, query: "",
                kind: .all, accountReachable: true
            ).headline,
            "Couldn't read this Mac's capture.")
    }

    /// A read that could not run must never be reported as a search that found nothing — including
    /// when there is a query on screen to blame it on.
    func testAClosedDatabaseIsNotReportedAsAQueryThatMatchedNothing() {
        XCTAssertEqual(
            ActivityEmptyCopy.resolve(
                isPreparing: false, readFailure: nil, capture: .opening, query: "invoice",
                kind: .all, accountReachable: true
            ).headline,
            "This Mac's capture isn't open yet.")
    }

    // MARK: - The corpus line

    /// The corner has two jobs and they are not the same sentence: at rest it says how much is being
    /// held, under a filter how much survived. Collapsing them is how a surface ends up claiming
    /// "0 moments captured" the moment somebody types a letter.
    func testTheCorpusSentenceSaysWhichQuestionItIsAnswering() {
        XCTAssertEqual(
            ActivityCount.sentence(matching: 12, total: 2_278, isFiltering: false, isSettled: false),
            "2,278 so far · still counting everything Omi has kept")
        XCTAssertEqual(
            ActivityCount.sentence(matching: 12, total: 2_278, isFiltering: false, isSettled: true),
            "2,278 things in everything Omi has kept",
            "the total is moments *plus* conversations, memories and tasks — see `ActivityCount.unit`")
        XCTAssertEqual(
            ActivityCount.sentence(matching: 1, total: 2_278, isFiltering: true, isSettled: true),
            "1 result · of 2,278 in everything Omi has kept")
        XCTAssertEqual(
            ActivityCount.sentence(matching: 0, total: 1, isFiltering: false, isSettled: true),
            "1 thing in everything Omi has kept",
            "the noun agrees with the number it is beside")
    }

    /// **The corner's two numbers must count the same unit.**
    ///
    /// The rows only ever hold the *sample* — `ActivityStore.project` keeps at most `sampleCeiling`
    /// frames of a day — while the day header counts every frame there was. Summing the sample on
    /// one side of `N results · of M` and the real capture on the other made a chip that excluded
    /// nothing look like a chip that had thrown away nine captures in ten: the render harness caught
    /// `51 results · of 2,954 in everything Omi has kept` with `Rewind` lit over 2,845 frames.
    func testASurvivingStripIsCountedInRealFramesAndNotInTiles() throws {
        let start = at(day: 10, hour: 9)
        // Ten sampled frames standing for a thousand — the ratio a day of three-second capture
        // really produces once `sampleCeiling` bites.
        let sampled = (0..<10).map { moment(id: Int64(200 + $0), at: start.addingTimeInterval(Double($0) * 60)) }
        let days = compose(account: .empty, screen: screen(10, sampled, total: 1_000))
        let day = try XCTUnwrap(days.first)

        XCTAssertEqual(day.momentCount, 1_000, "the header counts the day, not the sample")
        XCTAssertEqual(
            day.matchCount, 1_000,
            "an unfiltered day must match its own header, or the corner reports a filter nobody applied")

        // Soloing `Rewind` excludes nothing here, so the corner must say so.
        let soloed = ActivityComposer.filter(days, kind: .rewind, query: "")
        XCTAssertEqual(soloed.reduce(0) { $0 + $1.matchCount }, 1_000)
        XCTAssertEqual(
            ActivityCount.sentence(
                matching: 1_000, total: day.thingCount, isFiltering: true, isSettled: true),
            "1,000 results · of 1,000 in everything Omi has kept")
    }

    /// The same scaling reaches the two sentences a reader actually looks at: what a conversation
    /// says it caught, and what the strip under it says it is showing. They are one number stated
    /// twice and they may never disagree.
    func testAConversationAndItsStripAgreeAboutHowMuchTheyStandFor() throws {
        let start = at(day: 10, hour: 9)
        let inside = (0..<4).map { moment(id: Int64(300 + $0), at: start.addingTimeInterval(Double($0) * 60)) }
        let days = compose(
            account: ActivityAccountFeed(
                conversations: [accountConversation(id: "c1", start: start, minutes: 30)]),
            screen: screen(10, inside, total: 400))
        let rows = try XCTUnwrap(days.first).rows

        guard case .conversation(let conversation)? = rows.first?.content else {
            return XCTFail("the conversation is the first row of the day")
        }
        guard case .moments(let shown, let total)? = rows.dropFirst().first?.content else {
            return XCTFail("its strip is directly under it")
        }
        XCTAssertEqual(conversation.momentCount, total)
        XCTAssertEqual(total, 400, "four sampled frames of a four-hundred-frame day stand for all of it")
        XCTAssertEqual(shown.count, 4)
        XCTAssertTrue(conversation.subtitle.contains("400 screen moments"))
    }

    /// A day whose capture never reached the sampling ceiling is its own sample, and nothing is
    /// scaled. The identity case, because it is the one every other test in this file runs in.
    func testAnUnsampledDayIsCountedExactly() throws {
        let start = at(day: 10, hour: 9)
        let all = (0..<3).map { moment(id: Int64(400 + $0), at: start.addingTimeInterval(Double($0) * 60)) }
        let day = try XCTUnwrap(compose(account: .empty, screen: screen(10, all)).first)
        XCTAssertEqual(day.matchCount, 3)
        XCTAssertEqual(MomentScale(sampled: 3, captured: 3).forRun(of: 2), 2)
    }

    /// **The window has a top as well as a bottom.**
    ///
    /// Tasks are read unwindowed on purpose and are placed on their *due* date, so the feed
    /// routinely carries commitments from outside the window the chips asked for. With only an
    /// `earliest` bound, picking `Yesterday` composed a `TODAY` header above it out of tasks due
    /// today — and a task due next week put a day in the *future* at the top of a stream whose whole
    /// claim is that it is a record of the past.
    func testTheTimeWindowBoundsBothEndsOfTheStream() throws {
        let days = compose(
            account: ActivityAccountFeed(
                tasks: [
                    accountTask(id: "yesterday", at: at(day: 10, hour: 11)),
                    accountTask(id: "today", at: at(day: 11, hour: 11)),
                    accountTask(id: "due-next-week", at: at(day: 18, hour: 11)),
                ]))
        XCTAssertEqual(days.count, 3, "unbounded, every dated task is its own day")

        // The window the `Yesterday` chip asks for: one day, half-open at the top.
        let bounded = ActivityComposer.filter(
            days, kind: .all, query: "",
            earliest: startOfDay(10),
            latest: startOfDay(11).addingTimeInterval(-0.001))
        XCTAssertEqual(bounded.map(\.id), [startOfDay(10)])
    }

    /// **The corner may not claim a corpus it is only showing half of.**
    ///
    /// Three of the five kinds live in the account, and the empty copy that reports a silent account
    /// is only reachable when the stream is *completely* empty — which, on any Mac with screen
    /// capture on, it never is. So a signed-out user saw a full-looking list of their screen moments
    /// under a line promising "everything Omi has kept".
    func testTheCorpusLineNarrowsItsScopeWhenTheAccountDidNotAnswer() {
        XCTAssertEqual(
            ActivityCount.sentence(
                matching: 0, total: 743, isFiltering: false, isSettled: true,
                scope: ActivityCount.scope(accountUnreachable: .signedOut)),
            "743 things in what this Mac has kept")
        XCTAssertEqual(
            ActivityCount.sentence(
                matching: 0, total: 743, isFiltering: false, isSettled: true,
                scope: ActivityCount.scope(accountUnreachable: nil)),
            "743 things in everything Omi has kept")
        // No reason recorded means no read has come back unreachable, so the wide claim stands and
        // the line cannot flicker to the narrow one during the opening moments.
        XCTAssertEqual(ActivityCount.scope(accountUnreachable: nil), ActivityCount.scope)
    }

    /// The wait for a database that is not open yet has to outlast the thing that opens it.
    ///
    /// **A value assertion, not a behavioural one** — it pins a number against another component's
    /// documented cadence rather than executing a wait. `Engine`'s maintenance loop re-runs
    /// `ensureStorage()` every 30 seconds; this wait was 60 polls of 0.5 s, which is exactly one of
    /// those, so it expired on the very tick that would have answered it and the panel sat empty for
    /// the rest of the session with a live database underneath it.
    func testTheStoreWaitOutlastsMoreThanOneOfTheEnginesRetries() {
        let engineRetryCadence: TimeInterval = 30
        let wait = Double(ActivityStore.storeWaitAttempts) * 0.5
        XCTAssertGreaterThan(
            wait, engineRetryCadence * 2,
            "a wait that ends on the first retry is a wait that never sees the second")
    }

    /// **"Still counting" and "there was nothing" are different claims, and the corner could only
    /// make the first one.**
    ///
    /// `corpusTotal` is `nil` for both — nothing read yet, and nothing to read — so on a Mac that has
    /// genuinely captured nothing the corner said "Counting what you've captured…" for the rest of
    /// the session, opposite a body that already said "Nothing captured in this window yet." Caught
    /// in the render harness with the two sentences on screen together.
    func testTheCornerStopsCountingOnceThereIsNothingLeftToCount() {
        XCTAssertNotEqual(ActivityCount.nothingYet, ActivityCount.counting)
        XCTAssertFalse(
            ActivityCount.nothingYet.hasSuffix("…"),
            "an ellipsis is the tell that something is still running")
    }

    /// **The store says which of the three it is in, from the provider alone.**
    ///
    /// The observed launch is exactly this: the database's first open threw, so `Engine`'s provider
    /// answered `nil`, no read ever ran, and `readFailure` stayed nil. Reproduced with an injected
    /// provider rather than by breaking a real database — the user's capture history is not a
    /// fixture.
    @MainActor
    func testAStoreThatCannotBeOpenedSaysSoRatherThanLookingLikeAnEmptyOne() {
        let store = ActivityStore(store: { nil }, calendar: Self.calendar)
        XCTAssertEqual(store.capture, .open, "nothing has been asked yet")

        store.start()
        XCTAssertEqual(
            store.capture, .opening,
            "a provider with no database is a third state, not an empty answer")
        XCTAssertNil(store.readFailure, "nothing was read, so nothing threw — which is the trap")
        XCTAssertFalse(store.isPreparing, "and nothing is being prepared either")

        // Which is what the copy has to be resolved from: the same inputs the real surface hands it.
        XCTAssertEqual(
            ActivityEmptyCopy.resolve(
                isPreparing: store.isPreparing, readFailure: store.readFailure,
                capture: store.capture, query: store.currentQuery, kind: store.kind,
                accountReachable: store.accountReachable,
                accountUnreachableReason: store.accountUnreachableReason
            ).headline,
            "This Mac's capture isn't open yet.")
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

// MARK: - Signing in is a repair the ladder cannot make

extension ActivityCompositionTests {

    /// A panel that read the account before the session landed must ask again when it lands.
    ///
    /// **This is the one unreachable state the retry ladder is right to refuse.** `healsOnItsOwn`
    /// classifies `.signedOut` as unhealable, correctly — waiting does not sign anybody in — so
    /// without an event to hang the re-read on, the first answer is the only answer. On a real
    /// launch that answer arrived 40 ms too early: the panel opens with the app, `OmiAuth.restore()`
    /// reads the Keychain off the main actor, and the account was asked and answered "signed out"
    /// before the restored session existed. The user then sat in front of a signed-in app being told
    /// to sign in.
    @MainActor
    func testSigningInMakesThePanelAskTheAccountAgain() async {
        let signIns = CurrentValueSubject<Bool, Never>(false)
        let reads = ReadCounter()
        let store = ActivityStore(
            store: { nil },
            account: CountingAccount(reads: reads),
            signIns: signIns.eraseToAnyPublisher())

        store.start()
        await Self.settle()
        let beforeSignIn = await reads.count
        XCTAssertEqual(beforeSignIn, 1, "the panel asks once when it opens")

        signIns.send(true)
        await Self.settle()
        let afterSignIn = await reads.count
        XCTAssertEqual(afterSignIn, 2, "and asks again the moment a session appears")

        // Signing out is not a repair and must not spend a read: the copy already on screen is the
        // right one, and asking again could only confirm it.
        signIns.send(false)
        await Self.settle()
        let afterSignOut = await reads.count
        XCTAssertEqual(afterSignOut, 2, "signing out asks nothing")
    }

    /// **A full page is not a finished count, and the corner may not present one as the other.**
    ///
    /// The account is read a page at a time, so the newest `accountCeiling` rows of each kind are
    /// all the *first* read can ever have counted. On the real account every source came back at the
    /// cap — 200 conversations, 200 memories, 200 tasks — while the shipping Omi app beside it had
    /// paged 1,996 rows in and was still going; the corner nevertheless said `3,334 things in
    /// everything Omi has kept`, in the settled form, as a finished figure.
    ///
    /// So the store reads again while the answer keeps growing, and settles only when it stops. The
    /// reference resolves the same sentence from `SpineHydrator.state == .whole` and reads
    /// `4,491 so far · still counting` until every page is in.
    @MainActor
    func testTheCornerSettlesOnlyOnceTheAccountHasNoMorePagesToGive() async {
        let account = PagingAccount(pages: 3, rowsPerPage: 200, at: at(day: 10, hour: 9))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await Self.settle()

        let reads = await account.reads
        XCTAssertEqual(reads, 4, "three pages, then the read that finds there is no fourth")
        XCTAssertEqual(store.corpusTotal, 600, "every page is counted, not just the first")
        XCTAssertTrue(store.corpusSettled, "the account ran out of pages, so the count is finished")
        XCTAssertEqual(
            ActivityCount.sentence(
                matching: 0, total: store.corpusTotal ?? 0, isFiltering: false,
                isSettled: store.corpusSettled),
            "600 things in everything Omi has kept")
    }

    /// And the corner may not claim a finished count while pages are still landing.
    ///
    /// Held mid-walk by an account that hands over one page and then stops answering: the rows on
    /// screen are real and the reader may read them, but they are not everything Omi has kept and
    /// the sentence has to say so.
    @MainActor
    func testAPartialAccountKeepsTheCornerCounting() async {
        let account = PagingAccount(pages: 1, rowsPerPage: 200, at: at(day: 10, hour: 9), thenFails: true)
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await Self.settle()

        XCTAssertEqual(store.corpusTotal, 200)
        XCTAssertFalse(
            store.corpusSettled,
            "a source that stopped answering has rows behind it, and a full page is not an inventory")
        XCTAssertEqual(
            ActivityCount.sentence(
                matching: 0, total: store.corpusTotal ?? 0, isFiltering: false,
                isSettled: store.corpusSettled),
            "200 so far · still counting everything Omi has kept")
    }

    /// **Hydration is bounded, whatever the account does.** A reader whose pages never run out — a
    /// backend paging forever, an account growing faster than it is read — must cost a bounded
    /// number of requests rather than a loop that owns the session.
    @MainActor
    func testAnAccountThatNeverRunsOutIsStillReadABoundedNumberOfTimes() async {
        let account = PagingAccount(pages: .max, rowsPerPage: 1, at: at(day: 10, hour: 9))
        let store = ActivityStore(store: { nil }, account: account, calendar: Self.calendar)

        store.start()
        await Self.settle()

        let reads = await account.reads
        XCTAssertEqual(
            reads, ActivityStore.maximumAccountReads + 1,
            "the first read, then the budget — and then it stops asking")
        XCTAssertFalse(store.corpusSettled, "it stopped early, so it may not claim to have it all")
    }

    /// The ask has to be a number the reader will actually honour, or a page and an inventory are
    /// indistinguishable: this asked for 300, was clamped to 200 three times over, and read the
    /// clamp as the whole account.
    func testTheAccountCeilingIsTheOneTheReaderEnforces() {
        XCTAssertEqual(ActivityStore.accountCeiling, OmiActivityFeed.maxPerSource)
    }

    private static func settle() async {
        for _ in 0..<20 { await Task.yield() }
        try? await Task.sleep(for: .milliseconds(50))
    }

    // MARK: - The header's leading control

    /// **`Filter` is bare on a resting row, and that is the whole of the rule.**
    ///
    /// The five chips a line below it are pills, so a pill on this control put it in their visual
    /// class — a sixth kind you could solo, sitting above the five you actually can. The shipping
    /// Omi Activity page draws the same row's leading control bare for the same reason.
    ///
    /// It is a test rather than a screenshot because the two states that *do* fill it are the ones
    /// a screenshot never catches: a soloed kind, where the fill is the only thing on the row saying
    /// the list is narrowed at all, and hover, which is the control's only remaining affordance.
    func testTheFilterControlIsBareUntilItIsCarryingSomething() {
        XCTAssertFalse(
            ActivitySurfaceLayout.filterControlIsFilled(kind: .all, isHovering: false),
            "a resting, unfiltered row draws Filter as its label, not as a sixth chip")

        XCTAssertTrue(
            ActivitySurfaceLayout.filterControlIsFilled(kind: .all, isHovering: true),
            "the pointer has to get feedback, or the control is undiscoverable")

        for kind in ActivityKind.chips where kind != .all {
            XCTAssertTrue(
                ActivitySurfaceLayout.filterControlIsFilled(kind: kind, isHovering: false),
                "a soloed \(kind.title) has to show that the list is being narrowed")
        }
    }
}

private actor ReadCounter {
    private(set) var count = 0
    func bump() { count += 1 }
}

private struct CountingAccount: ActivityAccountReading {
    let reads: ReadCounter
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        await reads.bump()
        return .unreachable
    }
}

/// An account that pages, as the real reader does: every read answers with everything handed over
/// so far, plus one more page, until there are none left.
///
/// The cumulative shape is the seam's, not a convenience — `OmiActivityFeed` holds its own cursor
/// and answers with the whole of what it has gathered, because the one thing that crosses
/// `ActivityLocalMemories` unchanged is a read and the rows it answers with.
private actor PagingAccount: ActivityAccountReading {
    let pages: Int
    let rowsPerPage: Int
    let at: Date
    /// Whether the account stops answering once its scripted pages have been handed over, rather
    /// than answering with what it holds. A source that is failing has rows behind it.
    let thenFails: Bool
    private(set) var reads = 0
    private var handed = 0

    init(pages: Int, rowsPerPage: Int, at: Date, thenFails: Bool = false) {
        self.pages = pages
        self.rowsPerPage = rowsPerPage
        self.at = at
        self.thenFails = thenFails
    }

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        reads += 1
        if handed < pages { handed += 1 }
        // A source that is failing is absent from `answered` while the rows it did hand over stay in
        // the feed — which is exactly what the real reader does with a page that did not arrive.
        return feed(answered: thenFails && handed >= pages ? [.memories, .tasks] : Set(ActivityAccountSource.allCases))
    }

    private func feed(answered: Set<ActivityAccountSource>) -> ActivityAccountFeed {
        ActivityAccountFeed(
            conversations: (0..<(handed * rowsPerPage)).map {
                ActivityAccountConversation(
                    id: "c\($0)", title: "Standup", emoji: "🎬",
                    startedAt: at.timeIntervalSince1970 + Double($0),
                    finishedAt: at.timeIntervalSince1970 + Double($0) + 60,
                    overview: nil)
            },
            answered: answered)
    }
}
