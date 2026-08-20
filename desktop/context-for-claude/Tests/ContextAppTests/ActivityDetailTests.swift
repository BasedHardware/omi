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

    /// Written against `backend/models/transcript_segment.py`, which is what
    /// `GET /v1/conversations/{id}` actually serialises: `id`, `text`, `speaker` (`"SPEAKER_00"`),
    /// `speaker_id`, **`is_user`**, `person_id`, `start`, `end`.
    ///
    /// `is_user` is the field this screen moved endpoints for. The MCP projection did not carry it,
    /// so no account line could ever be attributed to the reader; here it can, and the two claims
    /// the label makes — "You" for the user's own voice, a number for everyone else's — are both
    /// asserted. `person_id` is present in the fixture and deliberately not rendered: it is an id,
    /// not a name, and resolving it is a lookup this screen does not make.
    func testAnAccountTranscriptNamesTheReadersOwnVoiceAndNumbersTheRest() throws {
        let json = """
            {
              "id": "abc",
              "started_at": "2025-06-11T09:00:00Z",
              "finished_at": "2025-06-11T09:30:00Z",
              "structured": {
                "title": "Pricing", "overview": "  We held it.  ",
                "category": "work", "emoji": "💸"
              },
              "transcript_segments": [
                {"id": "s1", "text": "Where did we land?", "speaker": "SPEAKER_00",
                 "speaker_id": 0, "is_user": true, "start": 0.0, "end": 2.0},
                {"id": "s2", "text": "Holding it.", "speaker": "SPEAKER_01", "speaker_id": 1,
                 "is_user": false, "person_id": "p-42", "start": 7.4, "end": 9.0},
                {"id": "s3", "text": "   ", "speaker": "SPEAKER_01", "speaker_id": 1,
                 "is_user": false, "start": 11.0, "end": 12.0}
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
        XCTAssertEqual(body.lines.map(\.speaker), ["You", "Speaker 2"])
        XCTAssertEqual(body.lines.map(\.isYou), [true, false])
        XCTAssertEqual(body.lines.map(\.offset), [0, 7.4])
    }

    /// A document written before `is_user` existed, or one where it did not survive whatever wrote
    /// it. The line is somebody else's, never the reader's: the safe half of the guess is the one
    /// that does not put words in their mouth.
    ///
    /// `speaker_id` is absent here too, so this also pins the fallback to parsing the raw
    /// `"SPEAKER_03"` label — which is exactly where the backend derives `speaker_id` from.
    func testALineWithNoIsUserIsSomebodyElsesAndItsNumberComesFromTheRawLabel() throws {
        let json = """
            {
              "id": "abc",
              "transcript_segments": [
                {"id": "s1", "text": "Anyone?", "speaker": "SPEAKER_03", "start": 0.0, "end": 1.0},
                {"id": "s2", "text": "Here.", "start": 2.0, "end": 3.0}
              ]
            }
            """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try decoder.decode(
            ActivityDetailWire.FullConversation.self, from: Data(json.utf8)
        ).body()

        XCTAssertEqual(body.lines.map(\.speaker), ["Speaker 4", "Speaker"])
        XCTAssertEqual(body.lines.map(\.isYou), [false, false])
    }

    /// `other` is the backend's own "we didn't work one out", so a chip saying it is a chip saying
    /// nothing.
    func testTheCategoryChipDropsTheBackendsPlaceholder() {
        XCTAssertNil(ActivityDetailWire.category("other"))
        XCTAssertNil(ActivityDetailWire.category("  "))
        XCTAssertEqual(ActivityDetailWire.category("work"), "work")
    }

    // MARK: - The summary half, which is what the click is actually for

    /// **The regression this screen was rebuilt for.** A conversation detail that decodes only the
    /// overview and the segments can only ever be a transcript with a sentence over it; the account
    /// sends the action items and the apps' readings in the same response, and the reference
    /// (`MainWindow/Pages/ConversationDetailView.swift`) puts them on the page ahead of the lines.
    ///
    /// Written against `backend/models/conversation.py` and `backend/models/structured.py`:
    /// `Conversation` carries `source`, `status`, `deferred` and `apps_results`; `Structured`
    /// carries `action_items`, each with `description`, `completed` and `source_segment_ids`.
    func testTheSummaryHalfOfAConversationIsDecodedAndNotJustItsTranscript() throws {
        let json = """
            {
              "id": "abc",
              "source": "desktop",
              "status": "completed",
              "structured": {
                "title": "Pricing", "overview": "We held it.", "category": "work", "emoji": "💸",
                "action_items": [
                  {"description": "Send the migration plan", "completed": false,
                   "source_segment_ids": ["s2"]},
                  {"description": "Book the room", "completed": true},
                  {"description": "   "}
                ],
                "events": [{"title": "Beta review", "start": "2025-06-12T09:00:00Z"}]
              },
              "apps_results": [
                {"app_id": "app-1", "content": "Three things stood out."},
                {"app_id": "app-2", "content": "  "}
              ],
              "transcript_segments": [
                {"id": "s2", "text": "Holding it.", "speaker": "SPEAKER_01", "start": 7.4}
              ]
            }
            """
        let body = try decode(json)

        XCTAssertEqual(body.source, "Desktop")
        // `completed` is the ordinary case, and the reference draws no badge for it.
        XCTAssertNil(body.status)

        // The blank item is dropped rather than drawn as an empty row, exactly as a blank segment is.
        XCTAssertEqual(body.actionItems.map(\.text), ["Send the migration plan", "Book the room"])
        XCTAssertEqual(body.actionItems.map(\.isCompleted), [false, true])
        // The link back into the transcript, which is what makes a summary-first screen navigable.
        XCTAssertEqual(body.actionItems.first?.sourceSegmentIDs, ["s2"])
        XCTAssertEqual(body.actionItems.last?.sourceSegmentIDs, [])

        XCTAssertEqual(body.appResults.map(\.content), ["Three things stood out."])
        XCTAssertTrue(body.hasSummary)
    }

    /// Two identical commitments are two rows. The reference keys its list on the description
    /// itself, which silently collapses them into one; identity comes from position here so that a
    /// conversation in which somebody said the same thing twice still reads as twice.
    func testTwoIdenticalActionItemsStayTwoRows() throws {
        let json = """
            {
              "id": "abc",
              "structured": {"action_items": [{"description": "Follow up"}, {"description": "Follow up"}]}
            }
            """
        let body = try decode(json)
        XCTAssertEqual(body.actionItems.count, 2)
        XCTAssertNotEqual(body.actionItems[0].id, body.actionItems[1].id)
    }

    /// `deferred` and `processing` are two mechanisms and one sentence — the reference's own
    /// enrichment branch treats them as one (`deferred || status == .processing`), and the reader is
    /// being told the same thing either way: the summary is not here yet.
    func testAnUnfinishedConversationSaysSoAndAFinishedOneDoesNot() {
        XCTAssertEqual(ActivityDetailWire.status("processing", deferred: false), .processing)
        XCTAssertEqual(ActivityDetailWire.status("completed", deferred: true), .processing)
        XCTAssertEqual(ActivityDetailWire.status(nil, deferred: true), .processing)
        XCTAssertEqual(ActivityDetailWire.status("in_progress", deferred: nil), .inProgress)
        XCTAssertEqual(ActivityDetailWire.status("merging", deferred: nil), .merging)
        XCTAssertEqual(ActivityDetailWire.status("failed", deferred: nil), .failed)
        // The ordinary case, an absent field, and a status this client has never heard of all mean
        // "no badge" — a badge invented for an unrecognised status is a badge about the client.
        XCTAssertNil(ActivityDetailWire.status("completed", deferred: false))
        XCTAssertNil(ActivityDetailWire.status(nil, deferred: nil))
        XCTAssertNil(ActivityDetailWire.status("quantum_folding", deferred: false))
        // Only `failed` is the account giving up; everything else is still in flight.
        XCTAssertTrue(ActivityConversationStatus.processing.isWorking)
        XCTAssertFalse(ActivityConversationStatus.failed.isWorking)
    }

    /// The source chip follows the rule the category chip already follows: a value this client has
    /// no word for is dropped, not rendered as "Unknown". `ConversationSource._missing_` folds every
    /// unrecognised value into `unknown` on the way out, so this is a chip that would appear on
    /// perfectly ordinary conversations to say nothing about them.
    func testTheSourceChipNamesTheDeviceOrIsNotDrawn() {
        XCTAssertEqual(ActivityDetailWire.sourceLabel("desktop"), "Desktop")
        XCTAssertEqual(ActivityDetailWire.sourceLabel("phone_call"), "Phone")
        XCTAssertEqual(ActivityDetailWire.sourceLabel("apple_watch"), "Apple Watch")
        XCTAssertNil(ActivityDetailWire.sourceLabel("unknown"))
        XCTAssertNil(ActivityDetailWire.sourceLabel("sdcard"))
        XCTAssertNil(ActivityDetailWire.sourceLabel(nil))
    }

    /// A conversation the account finished and made nothing of. Not a failure and not a wait — and
    /// the distinction is what lets the page say which of the three it is looking at.
    func testAConversationTheAccountMadeNothingOfHasNoSummary() throws {
        let body = try decode(
            """
            {"id": "abc", "status": "completed",
             "transcript_segments": [{"id": "s1", "text": "Morning.", "start": 0.0}]}
            """)
        XCTAssertFalse(body.hasSummary)
        XCTAssertNil(body.status)
        XCTAssertEqual(body.lines.count, 1)
    }

    // MARK: - Which pane a conversation opens on

    /// **The bug, as a test.** An account conversation opens on its summary and reaches the
    /// transcript through a control — the reference's architecture — and a click that landed
    /// straight on a wall of speech was the whole of the report.
    func testAnAccountConversationOpensOnItsSummary() {
        XCTAssertEqual(
            ActivityDetailPane.resolve(isLocal: false, transcriptOpen: false), .summary)
        XCTAssertEqual(
            ActivityDetailPane.resolve(isLocal: false, transcriptOpen: true), .transcript)
    }

    /// …and the one departure, which is forced rather than chosen: a conversation the account never
    /// saw has no summary half at all, so putting its lines behind a button would be an empty page
    /// pointing at the only content there is.
    func testALocalConversationOpensOnItsLinesBecauseItHasNothingElse() {
        XCTAssertEqual(ActivityDetailPane.resolve(isLocal: true, transcriptOpen: false), .transcript)
        XCTAssertEqual(ActivityDetailPane.resolve(isLocal: true, transcriptOpen: true), .transcript)
    }

    /// A conversation only this Mac heard is read from this Mac and **never from the account**, and
    /// the body it comes back with claims only what a capture database can know: the lines, and that
    /// they were heard here. An overview, a category or an action item on a conversation the account
    /// never saw would be this screen inventing the half it exists to show.
    func testALocalConversationIsReadFromThisMacAndClaimsNothingItCannotKnow() async {
        let source = ActivityConversationSource(
            isAirgapped: { false },
            isSignedIn: { true },
            fetch: { id in
                XCTFail("a local conversation must never be fetched from the account (\(id))")
                throw OmiAPIError.http(404, "")
            },
            local: { session in
                XCTAssertEqual(session, 7)
                return .body(
                    ActivityConversationBody(
                        source: ActivityDetailCopy.localSourceLabel,
                        lines: ActivityDetailWire.lines(from: [
                            Hit(kind: "said", at: 0, text: "Morning.", sessionId: session)
                        ])))
            })

        let answer = await source.read(
            conversation(id: ActivityConversation.localID(7), source: .local, start: at(hour: 9), minutes: 4))

        guard case .body(let body) = answer else { return XCTFail("expected a local body") }
        XCTAssertEqual(body.source, ActivityDetailCopy.localSourceLabel)
        XCTAssertEqual(body.lines.map(\.text), ["Morning."])
        XCTAssertNil(body.overview)
        XCTAssertNil(body.category)
        XCTAssertNil(body.status)
        XCTAssertTrue(body.actionItems.isEmpty)
        XCTAssertTrue(body.appResults.isEmpty)
        XCTAssertFalse(body.hasSummary)
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

    /// The reference's grammar, which is words and not an en dash: `<day> from h:mm a to h:mm a`,
    /// and `<day> at h:mm a` for a conversation with no width. The clause carries its own
    /// preposition so the header only ever joins it to the day.
    func testAConversationStatesItsWindowInTheReferencesGrammar() {
        XCTAssertEqual(
            ActivityFormat.window(from: at(hour: 9), duration: 0),
            "at \(ActivityFormat.time(at(hour: 9)))")
        XCTAssertEqual(
            ActivityFormat.window(from: at(hour: 9), duration: 1_800),
            "from \(ActivityFormat.time(at(hour: 9))) to \(ActivityFormat.time(at(hour: 9, minute: 30)))")
    }

    // MARK: - Prose that arrived as markdown

    /// **The regression the app-insights card was rebuilt for.** An app's reading arrives as
    /// markdown and used to be printed verbatim — literal `**Sleep Times**` with `- ` hanging off
    /// every bullet, which is a pane showing its own payload.
    func testAnAppsReadingIsSplitIntoHeadingsBulletsAndParagraphs() {
        let blocks = ActivityDetailProse.blocks(
            of: """
                **Decisions**
                - The tier is held.
                * The plan goes out Thursday.

                ## Still open
                Nobody owns the rename.
                """)

        XCTAssertEqual(
            blocks,
            [
                .heading(ActivityDetailProse.inline("Decisions")),
                .bullet(ActivityDetailProse.inline("The tier is held.")),
                .bullet(ActivityDetailProse.inline("The plan goes out Thursday.")),
                .heading(ActivityDetailProse.inline("Still open")),
                .paragraph(ActivityDetailProse.inline("Nobody owns the rename.")),
            ])
        // The syntax is consumed, not printed: the rendered run carries neither the asterisks nor
        // the dash.
        guard case .heading(let first) = blocks[0] else { return XCTFail("expected a heading") }
        XCTAssertEqual(String(first.characters), "Decisions")
        // A blank line separates blocks and is never a block of its own — an empty `Text` would put
        // a whole line box where the stack's own spacing belongs.
        XCTAssertEqual(blocks.count, 5)
    }

    /// A sentence that merely *begins* with a bold clause is a sentence. Promoting it to a heading
    /// would silently restyle ordinary prose the moment an app emphasised its first two words.
    func testOnlyAWhollyEmphasisedLineIsAHeading() {
        guard case .paragraph = ActivityDetailProse.blocks(of: "**Priya** owns the migration.")[0]
        else { return XCTFail("a bold opening clause is not a heading") }
        guard case .heading = ActivityDetailProse.blocks(of: "**Priya**")[0] else {
            return XCTFail("a wholly emphasised line is a heading")
        }
    }

    /// The fold lands between blocks rather than mid-word, so a collapsed reading never shows half
    /// a bullet or a heading with nothing under it.
    func testAFoldedReadingIsCutAtALineBoundary() {
        let content = "**Decisions**\n- The tier is held.\n- The plan goes out Thursday."
        XCTAssertEqual(
            ActivityAppResultCard.folded(content, at: 40), "**Decisions**\n- The tier is held.\n…")
        // A first line already past the limit has no boundary to snap back to, and keeps the blunt
        // cut rather than collapsing to nothing.
        XCTAssertEqual(ActivityAppResultCard.folded("one long unbroken line", at: 8), "one long…")
    }

    // MARK: - Helpers

    /// One conversation off the wire, through the decoder `OmiAPI` really configures.
    ///
    /// `.convertFromSnakeCase` is not decoration: it is what turns `action_items`,
    /// `source_segment_ids`, `apps_results` and `transcript_segments` into the properties this
    /// screen reads, and a fixture decoded any other way would pass while the app decoded nothing.
    private func decode(_ json: String) throws -> ActivityConversationBody {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            ActivityDetailWire.FullConversation.self, from: Data(json.utf8)
        ).body()
    }

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
