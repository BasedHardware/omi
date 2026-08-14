import ContextCore
import XCTest

@testable import ContextApp

/// What a click on the spine is allowed to open, and what the screen it opens is allowed to say.
///
/// Three claims here are the ones a refactor breaks quietly and a screenshot cannot catch: that each
/// of the three rows routes to *its own* detail rather than to a generic one, that a read which did
/// not work leaves the reader a sentence they can act on instead of a spinner or a blank sheet, and
/// that Escape means "back to the spine" while a detail is showing and only closes the panel when it
/// is not.
///
/// Every read here goes through an injected fetcher. Nothing in this file touches the account: it is
/// rate-limited in the real world, and a suite that spends a user's quota to assert a string is a
/// suite people turn off.
final class ActivityDetailTests: XCTestCase {

    // MARK: - Fixtures

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }()

    private func at(hour: Int, minute: Int = 0) -> Date {
        Self.calendar.date(
            from: DateComponents(year: 2025, month: 6, day: 11, hour: hour, minute: minute))!
    }

    private func conversation(
        id: String = "conv-1", source: ActivityConversation.Source = .account,
        start: Date, minutes: Double
    ) -> ActivityConversation {
        ActivityConversation(
            id: id, source: source, title: "Pricing review", emoji: source == .account ? "📊" : nil,
            startedAt: start, duration: minutes * 60)
    }

    /// One composed day, built through the composer rather than by hand — the containment rule is
    /// resolved against the rows the app really draws.
    private func days(
        conversations: [ActivityConversation] = [],
        memories: [ActivityAccountMemory] = [],
        tasks: [ActivityAccountTask] = []
    ) -> [ActivityDay] {
        let feed = ActivityAccountFeed(
            conversations: conversations.map {
                ActivityAccountConversation(
                    id: $0.id, title: $0.title, emoji: $0.emoji ?? "",
                    startedAt: $0.startedAt.timeIntervalSince1970,
                    finishedAt: $0.finishedAt.timeIntervalSince1970, overview: nil)
            },
            memories: memories, tasks: tasks, reachable: true)
        return ActivityComposer.compose(
            sessions: [], account: feed, screen: [:], calendar: Self.calendar)
    }

    // MARK: - A click routes to the right detail

    func testAConversationOpensItsOwnDetailAndCarriesNoContext() {
        let talk = conversation(start: at(hour: 9), minutes: 30)
        let request = ActivityDetailRequest.make(.conversation(talk), in: days(conversations: [talk]))

        XCTAssertEqual(request.subject, .conversation(talk))
        XCTAssertEqual(request.id, "conversation:conv-1")
        XCTAssertEqual(request.subject.overline, "Conversation")
        // A conversation is not context for itself. Filling `during` here would draw the same card
        // twice on one screen.
        XCTAssertNil(request.during)
    }

    func testAMemoryOpensAMemoryDetailCarryingTheConversationThatWasRunning() {
        let talk = conversation(start: at(hour: 9), minutes: 30)
        let memory = ActivityMemory(
            id: "m1", text: "Finance is copied on every invoice.", timestamp: at(hour: 9, minute: 12))
        let request = ActivityDetailRequest.make(
            .memory(memory),
            in: days(
                conversations: [talk],
                memories: [
                    ActivityAccountMemory(
                        id: "m1", content: memory.text, at: memory.timestamp.timeIntervalSince1970)
                ]))

        XCTAssertEqual(request.subject, .memory(memory))
        XCTAssertEqual(request.id, "memory:m1")
        XCTAssertEqual(request.subject.overline, "Memory")
        XCTAssertEqual(request.during?.id, talk.id)
    }

    func testATaskOpensATaskDetail() {
        let task = ActivityTask(
            id: "t1", text: "Send the migration plan", isCompleted: false,
            timestamp: at(hour: 14, minute: 5))
        let request = ActivityDetailRequest.make(.task(task), in: [])

        XCTAssertEqual(request.subject, .task(task))
        XCTAssertEqual(request.id, "task:t1")
        XCTAssertEqual(request.subject.overline, "Task")
    }

    /// The whole point of the section: it is a claim about the *clock*, never about provenance. A
    /// memory kept outside every conversation's window has no conversation, and the screen says so
    /// rather than reaching for the nearest one.
    func testAMemoryOutsideEveryWindowCarriesNoConversation() {
        let talk = conversation(start: at(hour: 9), minutes: 30)
        let memory = ActivityMemory(id: "m2", text: "Reads the digest on Sundays.", timestamp: at(hour: 17))
        let request = ActivityDetailRequest.make(
            .memory(memory),
            in: days(
                conversations: [talk],
                memories: [
                    ActivityAccountMemory(
                        id: "m2", content: memory.text, at: memory.timestamp.timeIntervalSince1970)
                ]))

        XCTAssertNil(request.during)
    }

    /// A memory and a task that share an id are two different things, and two rows that collapsed
    /// onto one identity would be a detail opening on whichever the diff happened to keep.
    func testIdentityIsPrefixedByKind() {
        let memory = ActivityMemory(id: "same", text: "a", timestamp: at(hour: 9))
        let task = ActivityTask(id: "same", text: "a", isCompleted: false, timestamp: at(hour: 9))
        XCTAssertNotEqual(
            ActivityDetailRequest.make(.memory(memory), in: []).id,
            ActivityDetailRequest.make(.task(task), in: []).id)
    }

    // MARK: - A detail that could not be read says so

    /// Every failure the account can produce, and the sentence each one renders as.
    ///
    /// **The distinctions are the test.** Collapsing them into "I couldn't reach your account" is
    /// the failure mode this table exists to prevent: three of these five are things the reader can
    /// do something about, and one of them fixes itself if they wait.
    func testEachFailureGetsItsOwnSentence() {
        let cases: [(Error, String)] = [
            (OmiAPIError.http(429, ""), ActivityDetailCopy.rateLimited),
            (OmiAPIError.http(404, ""), ActivityDetailCopy.gone),
            (OmiAPIError.http(402, ""), ActivityDetailCopy.locked),
            (OmiAPIError.http(500, ""), ActivityDetailCopy.noAnswer),
            (OmiAPIError.transport("no route"), ActivityDetailCopy.noAnswer),
            (OmiAPIError.decoding("structured"), ActivityDetailCopy.unreadable),
            (OmiAPIError.airgapMode, ActivityDetailCopy.airgapped),
        ]
        for (error, sentence) in cases {
            XCTAssertEqual(ActivityConversationSource.sentence(for: error), sentence)
        }
        // Never the server's own words: a FastAPI `detail` can quote the request back, and the
        // request carries a conversation id.
        XCTAssertFalse(
            ActivityConversationSource.sentence(for: OmiAPIError.http(500, "conversation abc123"))
                .contains("abc123"))
    }

    @MainActor
    func testARateLimitedReadLeavesAnHonestSentenceRatherThanASpinner() async {
        let model = ActivityDetailModel(
            source: FakeConversationReader(answer: .unread(ActivityDetailCopy.rateLimited)))
        model.read(conversation(start: at(hour: 9), minutes: 30))

        await settle(model) { if case .unread = $0 { return true } else { return false } }
        XCTAssertEqual(model.state, .unread(ActivityDetailCopy.rateLimited))
    }

    @MainActor
    func testARetryReReadsTheSameConversation() async {
        let reader = FakeConversationReader(answer: .unread(ActivityDetailCopy.rateLimited))
        let model = ActivityDetailModel(source: reader)
        model.read(conversation(start: at(hour: 9), minutes: 30))
        await settle(model) { if case .unread = $0 { return true } else { return false } }

        await reader.answer(.body(ActivityConversationBody(overview: "We held the tier.")))
        model.retry()
        await settle(model) { if case .read = $0 { return true } else { return false } }

        XCTAssertEqual(model.state, .read(ActivityConversationBody(overview: "We held the tier.")))
        // Twice, and both times for the same conversation — a retry that read a different thing
        // would be a button that navigates.
        let asked = await reader.asked
        XCTAssertEqual(asked, ["conv-1", "conv-1"])
    }

    /// An empty transcript is not a failure, and the two must not render as one another: the account
    /// really does keep summaries of conversations it stored no segments for.
    @MainActor
    func testAnEmptyTranscriptIsReadRatherThanUnread() async {
        let model = ActivityDetailModel(
            source: FakeConversationReader(answer: .body(ActivityConversationBody(overview: "A talk."))))
        model.read(conversation(start: at(hour: 9), minutes: 30))
        await settle(model) { if case .read = $0 { return true } else { return false } }

        guard case .read(let body) = model.state else { return XCTFail("expected a read body") }
        XCTAssertTrue(body.lines.isEmpty)
    }

    // MARK: - What the wire actually carries

    /// Written against the FastAPI response models in `backend/routers/mcp.py`:
    /// `FullConversation` = `SimpleConversation` + `transcript_segments`, and `SimpleStructured` is
    /// `title` / `overview` / `category` — **no `emoji`**, and `SimpleTranscriptSegment` has **no
    /// `is_user`**. Both absences are load-bearing on this screen, so both are asserted.
    func testTheAccountsTranscriptNeverClaimsAVoiceIsYours() throws {
        let json = """
            {
              "id": "abc",
              "started_at": "2025-06-11T09:00:00Z",
              "finished_at": "2025-06-11T09:30:00Z",
              "structured": {"title": "Pricing", "overview": "  We held it.  ", "category": "work"},
              "transcript_segments": [
                {"id": "s1", "text": "Where did we land?", "speaker_id": 0, "start": 0.0, "end": 2.0},
                {"id": "s2", "text": "Holding it.", "speaker_id": 1,
                 "speaker_name": "Priya", "start": 7.4, "end": 9.0},
                {"id": "s3", "text": "   ", "speaker_id": 1, "start": 11.0, "end": 12.0}
              ]
            }
            """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try decoder.decode(
            ActivityDetailWire.FullConversation.self, from: Data(json.utf8)
        ).body()

        XCTAssertEqual(body.overview, "We held it.")
        XCTAssertEqual(body.category, "work")
        // The blank segment is dropped rather than drawn as an empty bubble.
        XCTAssertEqual(body.lines.count, 2)
        XCTAssertEqual(body.lines.map(\.speaker), ["Speaker 1", "Priya"])
        XCTAssertEqual(body.lines.map(\.isYou), [false, false])
        XCTAssertEqual(body.lines.map(\.offset), [0, 7.4])
    }

    /// `other` is the backend's own "we didn't work one out", so a chip saying it is a chip saying
    /// nothing.
    func testTheCategoryChipDropsTheBackendsPlaceholder() {
        XCTAssertNil(ActivityDetailWire.category("other"))
        XCTAssertNil(ActivityDetailWire.category("  "))
        XCTAssertEqual(ActivityDetailWire.category("work"), "work")
    }

    /// A local session is the one source that *does* know which voice was the user's — `Hit.kind` is
    /// exactly that claim — and the offsets are measured from the first line rather than from the
    /// epoch.
    func testALocalTranscriptLabelsYourOwnVoiceAndTimesFromTheFirstLine() {
        let start = at(hour: 9).timeIntervalSince1970
        let lines = ActivityDetailWire.lines(from: [
            Hit(kind: "said", at: start, text: "Where did we land?", sessionId: 1),
            Hit(
                kind: "heard", at: start + 7, text: "Holding it.", sessionId: 1,
                speakerLabel: "SPEAKER_01"),
            Hit(kind: "heard", at: start + 12, text: "Agreed.", sessionId: 1),
        ])

        XCTAssertEqual(lines.map(\.speaker), ["You", "Speaker 2", "Someone else"])
        XCTAssertEqual(lines.map(\.isYou), [true, false, false])
        XCTAssertEqual(lines.map(\.offset), [0, 7, 12])
    }

    func testALocalConversationIdResolvesBackToItsSession() {
        XCTAssertEqual(ActivityDetailWire.localSession(ActivityConversation.localID(42)), 42)
        XCTAssertNil(ActivityDetailWire.localSession("2f8c9a"))
    }

    // MARK: - Escape

    /// Escape has two meanings on this panel and exactly one of them may be live at a time.
    ///
    /// `consume()` returning false is what leaves `SearchBarView.cancel` and `SearchPanel.sendEvent`
    /// free to close the window; returning true is what keeps it up. A hold that survived the way
    /// back would make Escape a key that does nothing.
    @MainActor
    func testEscapeMeansBackWhileADetailIsShowingAndCloseWhenItIsNot() {
        let escape = ActivityDetailEscape.shared
        escape.release()
        XCTAssertFalse(escape.isShowing)
        XCTAssertFalse(escape.consume(), "with no detail up, Escape is the panel's own")

        var wentBack = 0
        escape.hold { wentBack += 1 }
        XCTAssertTrue(escape.isShowing)
        XCTAssertTrue(escape.consume(), "a detail was showing, so Escape was consumed")
        XCTAssertEqual(wentBack, 1)

        // And the hold is gone with it: a second Escape closes the panel, which is the state the
        // reader is now looking at.
        XCTAssertFalse(escape.isShowing)
        XCTAssertFalse(escape.consume())
        XCTAssertEqual(wentBack, 1)
    }

    @MainActor
    func testLeavingTheDetailByTheBackControlReleasesEscape() {
        let escape = ActivityDetailEscape.shared
        escape.release()
        escape.hold {}
        escape.release()
        XCTAssertFalse(escape.consume())
    }

    // MARK: - Formatting

    func testTheDetailStatesTheDayTheRowCouldNotSay() {
        let instant = at(hour: 11, minute: 20)
        let stamp = ActivityFormat.stamp(instant, calendar: Self.calendar, now: at(hour: 23))
        // The day *and* the minute. The clock half is asserted against the surface's own formatter
        // rather than against literal digits: these fixtures are pinned to UTC so day grouping is
        // the same claim on every machine, and `ActivityFormat.time` renders in the local zone.
        XCTAssertEqual(stamp, "Today at \(ActivityFormat.time(instant))")
    }

    func testATranscriptOffsetReadsAsARecordingPosition() {
        XCTAssertEqual(ActivityFormat.offset(0), "0:00")
        XCTAssertEqual(ActivityFormat.offset(7.4), "0:07")
        XCTAssertEqual(ActivityFormat.offset(67), "1:07")
        XCTAssertEqual(ActivityFormat.offset(3_723), "1:02:03")
        // Never negative, whatever the clock says: a segment stamped before its own conversation
        // started is a backend rounding artefact, not a line said in the past.
        XCTAssertEqual(ActivityFormat.offset(-5), "0:00")
    }

    func testAConversationWithNoWidthStatesOneTimeRatherThanARange() {
        XCTAssertEqual(
            ActivityFormat.window(from: at(hour: 9), duration: 0), ActivityFormat.time(at(hour: 9)))
        XCTAssertTrue(ActivityFormat.window(from: at(hour: 9), duration: 1_800).contains("–"))
    }

    // MARK: - Helpers

    /// Spins the main actor until the model has settled, rather than sleeping for a guessed number
    /// of milliseconds: the read is a `Task` and the assertion is about what it produced.
    @MainActor
    private func settle(
        _ model: ActivityDetailModel,
        until matches: (ActivityDetailModel.State) -> Bool,
        file: StaticString = #filePath,
        line: UInt = #line
    ) async {
        for _ in 0..<200 {
            if matches(model.state) { return }
            await Task.yield()
        }
        XCTFail("the model never settled", file: file, line: line)
    }
}

/// A reader with a scripted answer, and a ledger of what it was asked for.
private actor FakeConversationReader: ActivityConversationReading {
    private var scripted: ActivityConversationRead
    private(set) var asked: [String] = []

    init(answer: ActivityConversationRead) {
        self.scripted = answer
    }

    func answer(_ next: ActivityConversationRead) {
        scripted = next
    }

    func read(_ conversation: ActivityConversation) async -> ActivityConversationRead {
        asked.append(conversation.id)
        return scripted
    }
}
