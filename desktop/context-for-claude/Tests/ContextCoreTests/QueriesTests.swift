import ContextCore
import Foundation
import XCTest

/// The read layer: what Claude actually sees.
///
/// Every assertion here is over the seeded corpus in `Fixture`, so a failure names a behaviour
/// ("recall stopped merging screen hits") rather than a row count that happened to change.
final class QueriesTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        fixture = try Fixture()
    }

    override func tearDownWithError() throws {
        fixture?.tearDown()
        fixture = nil
    }

    // MARK: - Recall

    func testRecallMergesSpeechAndScreenNewestFirst() throws {
        // "roadmap" was said once and was on screen once, an hour and a half apart.
        let hits = try Queries.recall(fixture.store, query: "roadmap")

        XCTAssertEqual(hits.map(\.kind), ["said", "screen"])
        XCTAssertEqual(hits.map(\.at), [Fixture.base + 7210, Fixture.base + 130])
        XCTAssertEqual(hits.first?.text, "thinking out loud about the roadmap")
        XCTAssertEqual(hits.last?.app, "Google Chrome")
        XCTAssertEqual(hits.last?.window, "Roadmap — Notion")
        XCTAssertEqual(hits.first?.sessionId, fixture.sessionB)
    }

    func testRecallAttributesSpeakersAndCarriesAHumanTimestamp() throws {
        let hits = try Queries.recall(fixture.store, query: "migration")

        let hit = try XCTUnwrap(hits.first)
        // Mic is the user, the system tap is everyone else — the whole of Context for Claude's diarization.
        XCTAssertEqual(hit.kind, "heard")
        XCTAssertEqual(hit.when, ContextTime.describe(Fixture.base + 30))
        XCTAssertEqual(hit.sessionId, fixture.sessionA)
    }

    func testRecallRespectsLimitSinceAndUntil() throws {
        // "pricing" matches two spoken lines (+10, +60) and one frame (+100).
        let all = try Queries.recall(fixture.store, query: "pricing")
        XCTAssertEqual(all.map(\.at), [Fixture.base + 100, Fixture.base + 60, Fixture.base + 10])

        let capped = try Queries.recall(fixture.store, query: "pricing", limit: 2)
        XCTAssertEqual(capped.map(\.at), [Fixture.base + 100, Fixture.base + 60])

        // The cap applies after the merge, not per source — otherwise a limit of 2 would return
        // two speech hits and two screen hits.
        XCTAssertEqual(try Queries.recall(fixture.store, query: "pricing", limit: 1).count, 1)

        let since = try Queries.recall(fixture.store, query: "pricing", since: Fixture.base + 50)
        XCTAssertEqual(since.map(\.at), [Fixture.base + 100, Fixture.base + 60])

        let until = try Queries.recall(fixture.store, query: "pricing", until: Fixture.base + 70)
        XCTAssertEqual(until.map(\.at), [Fixture.base + 60, Fixture.base + 10])

        let window = try Queries.recall(
            fixture.store, query: "pricing", since: Fixture.base + 50, until: Fixture.base + 70)
        XCTAssertEqual(window.map(\.at), [Fixture.base + 60])
    }

    func testRecallSurvivesHostileInput() throws {
        // Anything a person or a model might type. None of it may reach SQLite as FTS5 syntax.
        let hostile = [
            "\"", "*", "AND", "OR", "NOT x", "a:b", "🙂", "", "   ", "\t\n",
            "\"unterminated", "foo*", "NEAR(a b)", "-excluded", "^caret", "a AND b OR NOT c",
            "pricing\" OR segments_fts MATCH \"", "()", "column:value*",
        ]

        for query in hostile {
            XCTAssertNoThrow(
                try Queries.recall(fixture.store, query: query),
                "recall threw on \(query.debugDescription)")
        }
    }

    func testFTSExpressionQuotesTermsAndDropsOperators() throws {
        // Terms are quoted and OR-joined: ambient recall should surface anything related rather than
        // return nothing because one word of the phrase was missing.
        XCTAssertEqual(Queries.ftsExpression(for: "pricing"), "\"pricing\"")
        XCTAssertEqual(Queries.ftsExpression(for: "pricing change"), "\"pricing\" OR \"change\"")
        // Operators are stripped, not escaped — an operator that survives is a syntax error waiting
        // for the one user who types it.
        XCTAssertEqual(Queries.ftsExpression(for: "NOT x"), "\"x\"")
        XCTAssertEqual(Queries.ftsExpression(for: "\"pricing\""), "\"pricing\"")
        XCTAssertNotNil(Queries.ftsExpression(for: "a:b"))

        // Nothing left to search for is nil, so the caller answers "no results" instead of handing
        // SQLite an empty MATCH.
        for empty in ["", "   ", "\"", "*", "AND", "🙂", "()"] {
            XCTAssertNil(
                Queries.ftsExpression(for: empty),
                "\(empty.debugDescription) should not produce an expression")
        }
    }

    func testFTSExpressionReadsAPunctuatedWordTheWayTheIndexTokenizedIt() throws {
        // The index tokenizes with `porter unicode61`, which breaks `SCA-219` into `sca` and `219`.
        // Stripping the hyphen asked for `sca219`, a token no document it built can contain, so
        // every ticket id and hyphenated name was unfindable by the exact string a person types.
        // Both readings go out: the split one finds the row the index stored, the joined one finds a
        // document that wrote the same identifier without punctuation.
        XCTAssertEqual(Queries.ftsExpression(for: "SCA-219"), "\"SCA\" OR \"219\" OR \"SCA219\"")
        XCTAssertEqual(Queries.ftsExpression(for: "omi-eng"), "\"omi\" OR \"eng\" OR \"omieng\"")
        // An apostrophe is not an FTS operator, so it used to survive into the phrase
        // `"Priyanka's"` — two adjacent tokens no document says. unicode61 does not join across it,
        // so neither do we.
        XCTAssertEqual(Queries.ftsExpression(for: "Priyanka's"), "\"Priyanka\" OR \"s\"")
        // An unpunctuated word still reads the same both ways and must not be searched for twice.
        XCTAssertEqual(Queries.ftsExpression(for: "pricing"), "\"pricing\"")
    }

    func testRecallFindsAPunctuatedIdentifierByTheNameItIsWrittenUnder() throws {
        let scratch = try makeEmptyFixture()
        try scratch.addFrame(
            at: Fixture.base + 100, app: "Cursor", window: "SCA-219: Parity Pack v0 — omi",
            ocr: "SCA-219 Parity Pack v0: one PR (dev whitelist capture).")
        let sessionId = try scratch.store.openSession(at: Fixture.base, appHint: "zoom.us")
        try scratch.addSegment(
            session: sessionId, at: Fixture.base + 10, source: .mic,
            "remind me to email Priyanka about the vendor contract")

        // Every reading of the identifier reaches the one row that holds it: the whole string, the
        // half a person remembers, and the possessive they would actually type.
        for query in ["SCA-219", "219", "sca"] {
            let hits = try Queries.recall(scratch.store, query: query)
            XCTAssertEqual(
                hits.first?.window, "SCA-219: Parity Pack v0 — omi",
                "\(query.debugDescription) lost the window that shows it")
        }
        XCTAssertEqual(
            try Queries.recall(scratch.store, query: "Priyanka's").first?.text,
            "remind me to email Priyanka about the vendor contract")
    }

    func testAGenuineMatchStillOutranksNewerIncidentalOnes() throws {
        // The regression the ranking was built for, re-run over a query whose identifier now splits:
        // a titled window against six newer bookmark bars whose only tie to the query is "pack".
        // Reading one typed word as several terms must not change who wins — coverage counts words.
        let scratch = try makeEmptyFixture()
        try scratch.addFrame(
            at: Fixture.base + 1_500, app: "Cursor", window: "SCA-219: Parity Pack v0 — omi",
            ocr: "SCA-219 Parity Pack v0: one PR (dev whitelist capture). Reviewers asked for a "
                + "smaller diff before the parity pack lands.")
        for (i, title) in ["Inbox (12) - Gmail", "Hacker News", "Amazon | Bulk pack deals",
                           "Notion - Sprint board", "GitHub - pull requests", "YouTube"].enumerated() {
            try scratch.addFrame(
                at: Fixture.base + 1_600 + Double(i) * 60, app: "Arc", window: title,
                ocr: "Bookmarks Bar: Pack Tracker - Battery Pack - Pack Reviews - Vacation packing "
                    + "list - Six Pack Fitness.")
        }

        let hits = try Queries.recall(scratch.store, query: "Omi parity pack SCA-219")
        XCTAssertEqual(hits.first?.window, "SCA-219: Parity Pack v0 — omi")
        // And the incidental ones are floored out rather than padding the answer to `limit`.
        XCTAssertEqual(hits.filter { $0.app == "Arc" }.count, 0, "bookmark bars survived the floor")
    }

    // MARK: - Confidence

    func testHitsCarryTheTranscriberConfidenceAndMarkTheUncertainOnes() throws {
        let scratch = try makeEmptyFixture()
        let sessionId = try scratch.store.openSession(at: Fixture.base, appHint: "zoom.us")
        // 0.57 is the real score from the dogfooding session where background music came back as
        // the user's own first-person speech; 0.94 is where an ordinary clean line lands.
        try addSegment(scratch, session: sessionId, at: Fixture.base + 10,
                       "and I will always love you hallway", confidence: 0.57)
        try addSegment(scratch, session: sessionId, at: Fixture.base + 30,
                       "we agreed on the hallway conversation", confidence: 0.94)

        let byText = try Dictionary(
            uniqueKeysWithValues: Queries.recall(scratch.store, query: "hallway").map { ($0.text, $0) })
        XCTAssertEqual(byText.count, 2, "recall lost a line")

        let uncertain = try XCTUnwrap(byText["and I will always love you hallway"])
        let certain = try XCTUnwrap(byText["we agreed on the hallway conversation"])
        XCTAssertEqual(uncertain.confidence, 0.57)
        XCTAssertEqual(certain.confidence, 0.94)
        // Marked, not removed: the reader is told the line is shaky and still gets to see it.
        XCTAssertTrue(uncertain.isLowConfidence)
        XCTAssertFalse(certain.isLowConfidence)

        // The same value has to survive every path that builds a speech hit, or a reader gets one
        // answer from `recall` and a different one from `transcript` about the same line.
        let transcript = try Queries.transcript(scratch.store, sessionId: sessionId)
        XCTAssertEqual(transcript.map(\.confidence), [0.57, 0.94])
        XCTAssertEqual(transcript.map(\.isLowConfidence), [true, false])
    }

    func testLowConfidenceLinesAreMarkedRatherThanFilteredOut() throws {
        let scratch = try makeEmptyFixture()
        let now = ContextTime.now
        let sessionId = try scratch.store.openSession(at: now - 600, appHint: nil)
        // Everything the transcriber has ever emitted sits at or above ~0.5, so this is the whole
        // bottom of the observed range — the case most tempting to hide, and the one that must not
        // be hidden. A record that looks cleaner than the capture actually was is a lie.
        try addSegment(scratch, session: sessionId, at: now - 300, "barely audible aside", confidence: 0.5)
        try addSegment(scratch, session: sessionId, at: now - 120, "clearly stated decision", confidence: 0.97)

        let recall = try Queries.recall(scratch.store, query: "barely audible aside")
        XCTAssertEqual(recall.map(\.text), ["barely audible aside"], "recall dropped a low-confidence line")
        XCTAssertTrue(try XCTUnwrap(recall.first).isLowConfidence)

        let recent = try Queries.recent(scratch.store, minutes: 30)
        XCTAssertEqual(recent.map(\.text), ["clearly stated decision", "barely audible aside"])
        XCTAssertEqual(recent.map(\.isLowConfidence), [false, true])
        XCTAssertEqual(recent.map(\.confidence), [0.97, 0.5])

        XCTAssertEqual(try Queries.transcript(scratch.store, sessionId: sessionId).count, 2)
    }

    func testAnUnscoredLineIsUnknownRatherThanLowConfidence() throws {
        // The seeded corpus predates the column: every one of its lines has a NULL confidence, which
        // is exactly the state of a database captured before this shipped. None of it may come back
        // flagged — an absent score is not a bad one, and marking a year of good transcript as
        // doubtful would discredit the record as thoroughly as presenting music as speech.
        let hits = try Queries.recall(fixture.store, query: "pricing")
            + Queries.transcript(fixture.store, sessionId: fixture.sessionA)
            + Queries.screen(fixture.store)

        XCTAssertFalse(hits.isEmpty)
        for hit in hits {
            XCTAssertNil(hit.confidence, "\(hit.kind) hit invented a score: \(hit.text)")
            XCTAssertFalse(hit.isLowConfidence, "an unscored line was marked uncertain: \(hit.text)")
        }
    }

    func testTheConfidenceFloorSitsBetweenTheMusicBandAndOrdinarySpeech() throws {
        // Guards the number itself. Scores in this app's logs run ~0.5–0.99 and the music lines sat
        // low; a floor that drifted below 0.57 would stop catching them, and one that drifted up
        // into the 0.9s would flag nearly everything and mean nothing.
        XCTAssertGreaterThan(Hit.lowConfidenceFloor, 0.57)
        XCTAssertLessThan(Hit.lowConfidenceFloor, 0.9)

        let below = Hit(kind: "said", at: Fixture.base, text: "x", confidence: Hit.lowConfidenceFloor - 0.01)
        let onTheFloor = Hit(kind: "said", at: Fixture.base, text: "x", confidence: Hit.lowConfidenceFloor)
        let unscored = Hit(kind: "said", at: Fixture.base, text: "x")
        XCTAssertTrue(below.isLowConfidence)
        XCTAssertFalse(onTheFloor.isLowConfidence, "the floor itself is not below the floor")
        XCTAssertFalse(unscored.isLowConfidence)
        XCTAssertNil(unscored.confidence)
    }

    // MARK: - Speaker attribution

    func testHitsCarryTheBackendSpeakerAndPersonOnEverySpeechPath() throws {
        let scratch = try makeEmptyFixture()
        let now = ContextTime.now
        let sessionId = try scratch.store.openSession(at: now - 600, appHint: "zoom.us")
        // The case the whole cloud move exists for: two people on one call, arriving through the
        // same system tap, told apart by the backend and one of them matched to a real person.
        try addSegment(
            scratch, session: sessionId, at: now - 300, "I will send the contract tonight",
            source: .system, speakerLabel: "SPEAKER_00", personId: "person-sarah")
        try addSegment(
            scratch, session: sessionId, at: now - 240, "can we push it to Monday",
            source: .system, speakerLabel: "SPEAKER_01")
        try addSegment(
            scratch, session: sessionId, at: now - 180, "let me check the calendar",
            source: .mic, speakerLabel: "SPEAKER_02", personId: "person-me")

        // Every path that builds a speech hit has to agree, or a reader gets one answer from
        // `recall` and a different one from `transcript` about the same line.
        let recalled = try XCTUnwrap(
            Queries.recall(scratch.store, query: "contract").first)
        XCTAssertEqual(recalled.speakerLabel, "SPEAKER_00")
        XCTAssertEqual(recalled.personId, "person-sarah")
        // `kind` is untouched: which side of the microphone a line arrived on is a fact this app
        // observed itself, and a resolved person does not overrule it.
        XCTAssertEqual(recalled.kind, "heard")

        let recent = try Queries.recent(scratch.store, minutes: 30)
        XCTAssertEqual(
            recent.map(\.text),
            ["let me check the calendar", "can we push it to Monday", "I will send the contract tonight"])
        XCTAssertEqual(recent.map(\.speakerLabel), ["SPEAKER_02", "SPEAKER_01", "SPEAKER_00"])
        XCTAssertEqual(recent.map(\.personId), ["person-me", nil, "person-sarah"])

        let transcript = try Queries.transcript(scratch.store, sessionId: sessionId)
        XCTAssertEqual(transcript.map(\.speakerLabel), ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"])
        XCTAssertEqual(transcript.map(\.personId), ["person-sarah", nil, "person-me"])
        // Two `heard` lines with different labels are two people — more than `kind` alone can say,
        // and the reason the label is kept even when no person matched.
        XCTAssertEqual(transcript.prefix(2).map(\.kind), ["heard", "heard"])
        XCTAssertNotEqual(transcript[0].speakerLabel, transcript[1].speakerLabel)
    }

    func testAnUnattributedLineStaysUnattributedRatherThanBecomingAClaim() throws {
        // The seeded corpus predates the columns: every line in it was transcribed locally, where
        // nothing diarizes and nobody is identified. None of it may come back carrying a speaker or
        // a person — an absent attribution rendered as a present one is a quote put in someone's
        // mouth, and this database is the durable record behind it.
        // `recent` is measured from the wall clock and the corpus is anchored to a fixed epoch, so
        // the window is deliberately wide enough to reach it however long from now this test runs.
        let hits = try Queries.recall(fixture.store, query: "pricing")
            + Queries.recent(fixture.store, minutes: 10 * 365 * 24 * 60)
            + Queries.transcript(fixture.store, sessionId: fixture.sessionA)
            + Queries.screen(fixture.store)

        XCTAssertFalse(hits.isEmpty)
        for hit in hits {
            XCTAssertNil(hit.speakerLabel, "\(hit.kind) hit invented a speaker: \(hit.text)")
            XCTAssertNil(hit.personId, "\(hit.kind) hit invented a person: \(hit.text)")
        }
        // And the sessions those lines belong to claim nobody either.
        for summary in try Queries.sessions(fixture.store) {
            XCTAssertEqual(summary.personIds, [], "session \(summary.id) invented an attendee")
        }
    }

    func testSessionsReportWhoTheBackendResolvedInTheOrderTheySpoke() throws {
        // "my call with Sarah" is the query this enables: pick the session by who was in it rather
        // than by reading every transcript looking for a name.
        let scratch = try makeEmptyFixture()
        let sessionId = try scratch.store.openSession(at: Fixture.base, appHint: "zoom.us")
        try addSegment(
            scratch, session: sessionId, at: Fixture.base + 10, "morning both",
            source: .mic, speakerLabel: "SPEAKER_02", personId: "person-me")
        try addSegment(
            scratch, session: sessionId, at: Fixture.base + 30, "I will send the contract tonight",
            source: .system, speakerLabel: "SPEAKER_00", personId: "person-sarah")
        // An unmatched voice contributes nothing to the roster: a diarization label is not a person,
        // and listing it as one would be exactly the claim the id-only design refuses to make.
        try addSegment(
            scratch, session: sessionId, at: Fixture.base + 40, "can we push it to Monday",
            source: .system, speakerLabel: "SPEAKER_01")
        // Sarah again, later: the roster is who was there, not how often they spoke.
        try addSegment(
            scratch, session: sessionId, at: Fixture.base + 60, "Monday works for me",
            source: .system, speakerLabel: "SPEAKER_00", personId: "person-sarah")

        // A second session with nobody resolved, to prove the field is per session and that an
        // ordinary local conversation still reports an empty roster rather than the previous one.
        let localSessionId = try scratch.store.openSession(at: Fixture.base + 7_200, appHint: "Slack")
        try scratch.addSegment(
            session: localSessionId, at: Fixture.base + 7_210, source: .mic,
            "thinking out loud about the roadmap")

        let summaries = try Queries.sessions(scratch.store)
        let byID = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0) })

        let call = try XCTUnwrap(byID[sessionId])
        // Order is first-spoken, so the roster reads like the conversation did.
        XCTAssertEqual(call.personIds, ["person-me", "person-sarah"])
        XCTAssertEqual(call.lineCount, 4, "the roster query disturbed the header counts")
        XCTAssertTrue(call.bothSidesPresent)

        let local = try XCTUnwrap(byID[localSessionId])
        XCTAssertEqual(local.personIds, [])
        // Empty is "nobody was identified", never "the user was alone" — that is a different field.
        XCTAssertFalse(local.bothSidesPresent)
    }

    // MARK: - Recent and screen

    func testRecentWindowIsMinutesNotSeconds() throws {
        let scratch = try makeEmptyFixture()
        let now = ContextTime.now
        let sessionId = try scratch.store.openSession(at: now - 4_000, appHint: nil)
        try scratch.addSegment(session: sessionId, at: now - 3_600, source: .mic, "an hour ago")
        try scratch.addSegment(session: sessionId, at: now - 60, source: .mic, "a minute ago")
        try scratch.addFrame(at: now - 120, app: "Xcode", window: "two minutes ago")

        let hits = try Queries.recent(scratch.store, minutes: 30)

        XCTAssertEqual(hits.map(\.text), ["a minute ago", "two minutes ago"])
    }

    func testScreenFiltersByAppSubstringNewestFirst() throws {
        // Callers pass "Chrome" and mean "Google Chrome".
        let hits = try Queries.screen(fixture.store, app: "Chrome")

        XCTAssertEqual(hits.map(\.at), [Fixture.base + 130, Fixture.base + 100])
        XCTAssertEqual(Set(hits.map(\.kind)), ["screen"])
        XCTAssertEqual(hits.first?.app, "Google Chrome")
        XCTAssertEqual(try Queries.screen(fixture.store, app: "Xcode").count, 1)
        XCTAssertEqual(try Queries.screen(fixture.store, limit: 1).map(\.at), [Fixture.base + 7300])
    }

    // MARK: - Sessions

    func testSessionsSummariseBothSidedAndOneSidedConversations() throws {
        let summaries = try Queries.sessions(fixture.store)

        XCTAssertEqual(summaries.map(\.id), [fixture.sessionB, fixture.sessionA])

        let both = try XCTUnwrap(summaries.last)
        XCTAssertEqual(both.lineCount, 3)
        XCTAssertTrue(both.bothSidesPresent, "a session with mic and system audio is a conversation")
        XCTAssertEqual(both.appHint, "zoom.us")
        XCTAssertEqual(both.endedAt, Fixture.base + 600)
        XCTAssertEqual(both.durationSeconds, 600)
        XCTAssertTrue(both.preview.contains("we decided to ship the pricing change"),
                      "preview lost the opening line: \(both.preview)")
        XCTAssertTrue(both.preview.contains("sounds good"),
                      "preview lost the other side: \(both.preview)")

        let oneSided = try XCTUnwrap(summaries.first)
        XCTAssertEqual(oneSided.lineCount, 1)
        XCTAssertFalse(oneSided.bothSidesPresent, "one voice is the user talking, not a call")
        XCTAssertNil(oneSided.endedAt, "session B is still open")
        // An open session still has a duration: whatever it has captured so far.
        XCTAssertEqual(oneSided.durationSeconds, 15)
        XCTAssertTrue(oneSided.preview.contains("thinking out loud about the roadmap"))
    }

    func testSessionsRespectLimitSinceAndUntil() throws {
        XCTAssertEqual(try Queries.sessions(fixture.store, limit: 1).map(\.id), [fixture.sessionB])
        XCTAssertEqual(
            try Queries.sessions(fixture.store, since: Fixture.base + 7_000).map(\.id),
            [fixture.sessionB])
        XCTAssertEqual(
            try Queries.sessions(fixture.store, until: Fixture.base + 1_000).map(\.id),
            [fixture.sessionA])
    }

    func testTranscriptIsChronologicalAndAttributed() throws {
        let lines = try Queries.transcript(fixture.store, sessionId: fixture.sessionA)

        // Reverse of every other query on purpose: a conversation only reads forwards.
        XCTAssertEqual(lines.map(\.at), [Fixture.base + 10, Fixture.base + 30, Fixture.base + 60])
        XCTAssertEqual(lines.map(\.kind), ["said", "heard", "said"])
        XCTAssertEqual(lines.compactMap(\.sessionId), Array(repeating: fixture.sessionA, count: 3))
        XCTAssertEqual(lines.first?.text, "we decided to ship the pricing change on Friday")

        XCTAssertEqual(try Queries.transcript(fixture.store, sessionId: 9_999), [])
    }

    // MARK: - Activity

    func testActivityCollapsesRunsSplitsOnGapsAndDropsGlances() throws {
        let scratch = try makeEmptyFixture()
        let base = Fixture.base

        // 40 s in Chrome.
        for offset in stride(from: 0.0, through: 40.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Google Chrome",
                                 window: offset == 0 ? "Docs" : "Pricing rollout — Docs")
        }
        // App switch closes the block: 20 s in Xcode.
        for offset in stride(from: 45.0, through: 65.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Xcode", window: "Store.swift")
        }
        // Same app again, but 335 s later — the user walked away, so this is a second block.
        for offset in stride(from: 400.0, through: 420.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Xcode", window: "Queries.swift")
        }
        // 5 s in Finder: a glance, not a stretch of work.
        try scratch.addFrame(at: base + 500, app: "Finder", window: "Downloads")
        try scratch.addFrame(at: base + 505, app: "Finder", window: "Downloads")

        let blocks = try Queries.activity(scratch.store, since: base - 60, until: base + 900)

        XCTAssertEqual(blocks.map(\.app), ["Google Chrome", "Xcode", "Xcode"])
        XCTAssertEqual(blocks.map(\.startedAt), [base, base + 45, base + 400])
        XCTAssertEqual(blocks.map(\.durationSeconds), [40, 20, 20])
        XCTAssertFalse(blocks.contains { $0.app == "Finder" }, "a 5 s glance is noise, not a block")
        // The most descriptive title the app showed during the stretch.
        XCTAssertEqual(blocks.first?.window, "Pricing rollout — Docs")
        XCTAssertEqual(blocks.last?.window, "Queries.swift")

        // The window is a filter, not a hint.
        let narrowed = try Queries.activity(scratch.store, since: base + 100, until: base + 900)
        XCTAssertEqual(narrowed.map(\.startedAt), [base + 400])
        XCTAssertEqual(try Queries.activity(scratch.store, since: base + 700, until: base + 900), [])
    }

    /// The two facts about a block's sample text that survive the frames it was made of.
    ///
    /// `activity` folds the range one row at a time rather than holding it — a year of capture is
    /// 547,500 rows carrying ~780 MiB of OCR, and the collapse is a few thousand blocks — so
    /// everything the sample depends on has to be decidable as frames arrive. These are the two
    /// orderings that make that non-obvious: screen text is the fallback for a stretch that showed
    /// **no** title at all, and it stays the fallback even when the untitled frame comes first.
    func testActivitySamplesScreenTextOnlyWhenTheStretchShowedNoTitle() throws {
        let scratch = try makeEmptyFixture()
        let base = Fixture.base

        // A stretch with no window title anywhere: the sample is the first legible screen text.
        for offset in stride(from: 0.0, through: 40.0, by: 5.0) {
            try scratch.addFrame(
                at: base + offset, app: "Terminal", window: nil,
                ocr: offset == 0 ? "   " : "swift build --package-path desktop")
        }
        // A stretch whose first frame has no title and whose later frames do: the title wins.
        for offset in stride(from: 400.0, through: 440.0, by: 5.0) {
            try scratch.addFrame(
                at: base + offset, app: "Cursor",
                window: offset == 400 ? nil : "Queries.swift — omi",
                ocr: "private static func activity")
        }

        let blocks = try Queries.activity(scratch.store, since: base - 60, until: base + 900)

        XCTAssertEqual(blocks.map(\.app), ["Terminal", "Cursor"])
        XCTAssertNil(blocks.first?.window)
        XCTAssertEqual(blocks.first?.sampleText, "swift build --package-path desktop")
        XCTAssertEqual(blocks.last?.window, "Queries.swift — omi")
        XCTAssertEqual(
            blocks.last?.sampleText, "Queries.swift — omi",
            "a stretch that showed a title must never fall back to screen text")
    }

    // MARK: - Status

    func testStatusReportsCountsAndCoverage() throws {
        let status = try Queries.status(fixture.store)

        XCTAssertEqual(status.segmentCount, 4)
        XCTAssertEqual(status.frameCount, 3)
        XCTAssertEqual(status.sessionCount, 2)
        // Coverage spans speech and screen together: the oldest line and the newest frame.
        XCTAssertEqual(status.oldestAt, Fixture.base + 10)
        XCTAssertEqual(status.newestAt, Fixture.base + 7_300)
        XCTAssertTrue(status.coverage.contains(ContextTime.describe(Fixture.base + 10)),
                      "coverage lost its start: \(status.coverage)")
        XCTAssertTrue(status.coverage.contains(ContextTime.describe(Fixture.base + 7_300)),
                      "coverage lost its end: \(status.coverage)")
        XCTAssertFalse(status.databasePath.isEmpty)
    }

    func testStatusOnAnEmptyStoreSaysSoRatherThanGuessing() throws {
        let scratch = try makeEmptyFixture()

        let status = try Queries.status(scratch.store)

        XCTAssertEqual(status.segmentCount, 0)
        XCTAssertNil(status.oldestAt)
        XCTAssertNil(status.newestAt)
        XCTAssertEqual(status.coverage, "no data captured yet")
    }

    func testStatusIsNotCapturingWithoutALiveHeartbeat() throws {
        // Inject an absent heartbeat so this never depends on whether Context for Claude is
        // running on the developer machine.
        let status = try Queries.status(fixture.store, heartbeat: .fixed(nil))

        XCTAssertFalse(status.capturing, "an absent heartbeat means the app is not running")
        XCTAssertEqual(status.pausedReason, "Context for Claude is not running")
    }

    func testStatusPassesThroughCapturingPlusTranscriptionGap() throws {
        // Intel cloud-ASR gap while sensors stay live: MCP `status` must keep both facts.
        let gap =
            "Transcription needs a network connection to Omi — audio is still captured but nothing is being transcribed"
        let heartbeat = CaptureState(
            capturing: true,
            pausedReason: gap,
            updatedAt: ContextTime.now)

        let status = try Queries.status(fixture.store, heartbeat: .fixed(heartbeat))

        XCTAssertTrue(status.capturing)
        XCTAssertEqual(status.pausedReason, gap)
        XCTAssertEqual(
            status.localCaptureHeadline,
            "Context for Claude is capturing right now — \(gap).")
        XCTAssertTrue(status.localCaptureHeadline.contains("capturing right now"))
        XCTAssertTrue(status.localCaptureHeadline.contains(gap))
    }

    func testStatusHeadlineWhenCapturingWithoutGap() {
        let status = StatusInfo(
            capturing: true,
            pausedReason: nil,
            capabilities: [],
            segmentCount: 0,
            frameCount: 0,
            sessionCount: 0,
            oldestAt: nil,
            newestAt: nil,
            databasePath: "/tmp/context.db")
        XCTAssertEqual(
            status.localCaptureHeadline,
            "Context for Claude is capturing right now.")
    }

    func testHeartbeatGoesStaleOnSchedule() throws {
        // The rule `status` depends on, tested without touching the real heartbeat file.
        let url = fixture.root.appendingPathComponent("capture-state.json")
        let now = ContextTime.now

        try JSONEncoder().encode(CaptureState(capturing: true, updatedAt: now)).write(to: url)
        XCTAssertEqual(CaptureState.read(from: url)?.isStale, false)

        let old = CaptureState(capturing: true, updatedAt: now - CaptureState.stalenessSeconds - 60)
        try JSONEncoder().encode(old).write(to: url)
        XCTAssertEqual(CaptureState.read(from: url)?.isStale, true)

        XCTAssertNil(CaptureState.read(from: fixture.root.appendingPathComponent("absent.json")))
    }

    // MARK: - Helpers

    /// A second, empty store for the tests that need to author their own corpus. Torn down with the
    /// test rather than in `tearDown`, so no test can see another's rows.
    private func makeEmptyFixture() throws -> Fixture {
        let scratch = try Fixture(seeded: false)
        addTeardownBlock { scratch.tearDown() }
        return scratch
    }

    /// A scored line. `Fixture.addSegment` writes the shape the rest of the corpus needs — no score,
    /// which is the right default everywhere else — so the confidence tests build theirs here.
    private func addSegment(
        _ fixture: Fixture,
        session: Int64,
        at startedAt: Double,
        _ text: String,
        confidence: Double?
    ) throws {
        _ = try fixture.store.insertSegment(
            Segment(
                sessionId: session,
                startedAt: startedAt,
                endedAt: startedAt + 5,
                source: .mic,
                text: text,
                confidence: confidence))
    }

    /// A line the backend attributed. `Fixture.addSegment` writes the locally transcribed shape —
    /// no speaker, no person, which is the truth everywhere else in the corpus — so the attribution
    /// tests build theirs here.
    private func addSegment(
        _ fixture: Fixture,
        session: Int64,
        at startedAt: Double,
        _ text: String,
        source: SegmentSource,
        speakerLabel: String?,
        personId: String? = nil
    ) throws {
        _ = try fixture.store.insertSegment(
            Segment(
                sessionId: session,
                startedAt: startedAt,
                endedAt: startedAt + 5,
                source: source,
                text: text,
                speakerLabel: speakerLabel,
                personId: personId))
    }
}
