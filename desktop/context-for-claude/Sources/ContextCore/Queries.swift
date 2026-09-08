import ContextCoreCxx
import Foundation
import GRDB

/// Every read the app and the MCP server perform. Nothing in here writes, so it is safe against a
/// read-only WAL connection opened while the app is still capturing.
public enum Queries {

    /// Where `status` gets the live-capture signal from. Tests inject `.fixed` so they never write
    /// the real Application Support heartbeat.
    public enum HeartbeatSource: Sendable, Equatable {
        case live
        case fixed(CaptureState?)
    }

    // MARK: - Tuning

    /// The window title is the signal and the OCR is the detail — enough to recognise a page,
    /// not enough to re-read it through a tool result.
    private static let screenTextLimit = 600
    private static let sessionPreviewLimit = 240
    private static let sessionPreviewLines = 3
    private static let activitySampleLimit = 120
    /// A longer gap means the user walked away, not that they kept working in the same app.
    private static let activityGapSeconds: Double = 120
    /// Anything shorter is a glance, and a day made of glances is noise rather than a shape.
    private static let activityMinimumSeconds: Double = 15

    // MARK: - Confidence
    //
    // Every speech hit carries the transcriber's own score for the line, and every hit under
    // `Hit.lowConfidenceFloor` comes back **marked** (`isLowConfidence`) rather than removed. The
    // bar itself, and the reasoning for the number, live on `Hit` — the reader of a hit has to be
    // able to see them without reaching into the query layer.
    //
    // Filtering by confidence is deliberately not offered, not even as an option that defaults off.
    // The argument this app makes is that it says what it does and does not know; a result set with
    // the uncertain lines quietly missing looks *more* reliable than the record actually is, which
    // is the same lie as presenting a 0.5 line as fact, told in the other direction. A reader that
    // wants a stricter bar has the raw number and can apply it — and can still see what it excluded.
    //
    // Screen hits have no score at all: OCR is a different pipeline with a different failure mode,
    // and inventing a confidence for it would be worse than admitting there is none.

    // MARK: - Attribution
    //
    // Speech hits carry the backend's diarization label and its matched person id, and `sessions`
    // reports the people a conversation contained. All of it is **ids, never names**, and that is a
    // deliberate boundary rather than an omission.
    //
    // A name is a current property of the user's Omi account: people get renamed, merged, and
    // re-enrolled, and none of that comes back to rewrite rows written months earlier. A name copied
    // into a row at capture time is therefore a claim that decays with nothing to correct it — and
    // the failure it produces is the worst one this layer can produce, a model quoting the wrong
    // person by name with a durable local database behind it. An id ages into whoever the person
    // becomes.
    //
    // Resolution belongs one layer up, and already lives there: the MCP reader holds its own Omi
    // credential and already renders account-side speaker names. Caching names here as well would
    // create two copies that disagree, and the stale one would be the one that looks authoritative.
    // It would also turn a local file the user is invited to delete into a list of their contacts'
    // names rather than opaque handles.
    //
    // What the reader gets without any credential is still real: lines sharing a person id are the
    // same person, and lines with different diarization labels are different voices. Absent stays
    // absent — a line nothing identified must render exactly as it did before any of this existed.

    // MARK: - Recall ranking
    //
    // `recall` used to OR every query term together and then sort purely by recency. Searching
    // "Omi parity pack SCA-219" therefore returned ten hits — effectively the whole database — and
    // buried the one genuine match (a window titled "SCA-219: Parity Pack v0: one PR (dev whitelist
    // capture)") in eighth place, below three captures of a browser bookmark bar whose only
    // connection to the query was the word "pack".
    //
    // That is worse than an annoying result order. `status` reports an exact coverage window, which
    // licenses a reader to treat an empty result *inside* that window as evidence something did not
    // happen. A true match ranked below incidental noise — or pushed past `limit` entirely — turns a
    // ranking bug into a confident false statement. So relevance decides the order and recency only
    // breaks near-ties.
    //
    // The scoring formula and floor live in the portable C++ core (`ctx_recall_score` and
    // `ctx_relevance_floor`) so every host — macOS, Windows, or any future one — agrees on the same
    // answer. The constants are documented in `core/include/context_core/context_core.h`.

    /// bm25 column weights for `frames_fts(ocrText, windowTitle, appName)`.
    ///
    /// A term in the window title is a claim about what the user was actually looking at. The same
    /// term in OCR may be a bookmark, a sidebar link, or a notification that happened to be on
    /// screen — that is literally what outranked the real match. 10x is the ratio at which one title
    /// occurrence beats several body occurrences in a long page. The app name sits between them: it
    /// is a real signal for "find that thing in Slack", but it is identical across every frame from
    /// that app, so it must never outweigh a title.
    private static let frameOCRWeight = 1.0
    private static let frameTitleWeight = 10.0
    private static let frameAppWeight = 3.0

    /// How many rows per table to score before capping to `limit`.
    ///
    /// The pool is ordered by bm25, so a cut here can only ever discard the weakest matches. Cutting
    /// by recency first — the old behaviour — could drop the best match before ranking ever saw it.
    private static let candidatePoolFactor = 4
    private static let candidatePoolMinimum = 200

    // MARK: - Moments
    //
    // Screen capture runs every three seconds. A window a person sits in front of for twenty minutes
    // is four hundred rows that are, to a reader, one event — and `limit` used to be spent on them,
    // so `recall "periphery"` handed back a page of the same terminal and `screen` answered "the
    // newest sixty observations" with thirteen minutes of one editor. Raw matching was never the
    // hard part; turning those rows back into moments is.
    //
    // A moment is a run of frames from one window that keeps showing substantially the same thing.
    // It carries the whole run's time span and the number of frames it stands for, so collapsing
    // hides nothing: a reader can always ask `screen` for the span itself and get the frames back.
    //
    // The grouping algorithm lives in the portable C++ core (`ctx_moment_groups`) so every host
    // agrees on the same answer. The constants are documented in
    // `core/include/context_core/context_core.h`. This Swift layer builds flat buffers from
    // `[MomentInput]` and delegates to the C ABI.

    /// Distinct words compared per frame. Bounds the pass over a pathological page; real captures on
    /// this machine peak around 500. Stays in Swift because it caps the word extraction
    /// (`words(in:)`), not the grouping — `ctx_moment_groups` trusts the caller's word arrays.
    private static let momentWordCeiling = 800

    /// Raw frames to read before collapsing, when the caller asked for `limit` moments.
    ///
    /// `limit` counts moments now, so the pool has to be big enough that collapsing does not
    /// under-deliver — this is the whole of the "unfiltered `screen` covers thirteen minutes"
    /// defect. The ceiling bounds the work: 2,000 frames is nearly two hours of unbroken capture,
    /// and far more in practice.
    private static let momentPoolFactor = 25
    private static let momentPoolMinimum = 600
    private static let momentPoolCeiling = 2000

    private static func momentPool(for limit: Int) -> Int {
        guard limit < momentPoolCeiling / momentPoolFactor else { return momentPoolCeiling }
        return min(momentPoolCeiling, max(limit * momentPoolFactor, momentPoolMinimum))
    }

    // MARK: - Search

    /// Full-text search across speech and screen text, best match first.
    ///
    /// Scores from `segments_fts` and `frames_fts` are not directly comparable, so each table is
    /// normalised against its own best hit and the two are then blended on query-term coverage,
    /// which does mean the same thing in both. See the ranking notes above for the weights and why
    /// they are what they are.
    public static func recall(
        _ store: ContextStore,
        query: String,
        since: Double? = nil,
        until: Double? = nil,
        limit: Int = 40
    ) throws -> [Hit] {
        guard limit > 0 else { return [] }
        // A query the tokenizer cannot represent at all — a lone emoji, a glyph, any script
        // `unicode61` treats as punctuation — produces no terms and therefore no MATCH. Returning
        // nothing there is the dangerous answer: it is indistinguishable from a search that ran and
        // found nothing, which is exactly the licence a reader has to conclude the thing never
        // happened. The text is in the database; only the index cannot hold it. So scan for it
        // literally, bounded by the same limit, on the one path where the index has already refused.
        guard let match = ftsExpression(for: query) else {
            // Only for content the tokenizer drops but a person still means: emoji, pictographs,
            // symbols like ✳. A query of bare punctuation — a lone quote, a star, an FTS keyword —
            // also yields no terms, but scanning for it matches every row that happens to contain
            // that character, which is noise dressed as an answer. The test is therefore not "did
            // the index refuse" but "is there something here worth looking for literally".
            guard carriesUnindexableContent(query) else { return [] }
            return try literalScan(store, needle: query, since: since, until: until, limit: limit)
        }
        let terms = distinctTerms(in: query)
        // `limit` is caller-supplied, so the widening saturates rather than trapping.
        let pool = limit >= Int.max / candidatePoolFactor
            ? Int.max
            : max(limit * candidatePoolFactor, candidatePoolMinimum)

        let matched: [Candidate] = try store.read { db in
            let spoken = try matchedSegments(
                db, match: match, terms: terms, since: since, until: until, limit: pool)
            // Frames collapse into moments before the cap, so the frame pool has to be deep enough
            // that the collapse has something to work with — otherwise `limit` moments would still
            // cost `limit` frames and nothing would have been gained.
            let seen = try matchedFrames(
                db, match: match, terms: terms, since: since, until: until,
                limit: max(pool, momentPoolMinimum))
            return spoken + seen
        }
        // The index answered nothing. That is usually the truth, and the scan below then returns
        // nothing too — the honest empty answer survives. But it is also what happens when the text
        // is present in a form the tokenizer cannot reach it by: a stem that folded differently, a
        // word welded to punctuation, a script it segments unlike the query. Those were silently
        // reported as absent, and absence is the one answer a reader acts on irreversibly.
        //
        // Only on empty, so it costs nothing whenever the index did its job.
        if matched.isEmpty {
            return try literalScan(store, needle: query, since: since, until: until, limit: limit)
        }
        return cap(ranked(matched), to: limit)
    }

    /// Everything captured in the last `minutes`, speech and screen merged.
    ///
    /// Screen rows arrive as moments, so half an hour of sitting in one window is one line rather
    /// than six hundred, and the speech it happened around is not pushed out by them.
    public static func recent(_ store: ContextStore, minutes: Int = 30, limit: Int = 120) throws -> [Hit] {
        guard limit > 0 else { return [] }
        let since = ContextTime.now - Double(max(0, minutes)) * 60

        let hits: [Hit] = try store.read { db in
            let spoken = try segmentRows(db, since: since, until: nil, limit: limit).map(segmentHit)
            let frames = try frameRows(
                db, since: since, until: nil, app: nil, limit: momentPool(for: limit))
            return spoken + screenMoments(frames)
        }
        return cap(newestFirst(hits), to: limit)
    }

    /// Screen observations, newest first, optionally narrowed to one app.
    ///
    /// `limit` counts **moments**, not frames. That is the difference between "the last sixty
    /// observations" meaning the last thirteen minutes of one editor and it meaning the last several
    /// hours of everything — and it is why the pool read here is much larger than `limit`.
    public static func screen(
        _ store: ContextStore,
        since: Double? = nil,
        until: Double? = nil,
        app: String? = nil,
        limit: Int = 60
    ) throws -> [Hit] {
        guard limit > 0 else { return [] }
        let rows = try store.read { db in
            try frameRows(db, since: since, until: until, app: app, limit: momentPool(for: limit))
        }
        // A moment straddling the oldest edge of the pool reports only the frames inside it. That
        // undercount is bounded to one moment, and it is the one `limit` discards anyway.
        return cap(newestFirst(screenMoments(rows)), to: limit)
    }

    /// `screen`, plus whether the answer was truncated.
    ///
    /// The distinction matters more than it looks: "these are the 40 observations" and "these are
    /// the newest 40 of more" license different conclusions, and only the second is true when a
    /// cap was hit. A caller that cannot tell them apart will report a bounded slice as complete.
    public static func screenPage(
        _ store: ContextStore,
        since: Double? = nil,
        until: Double? = nil,
        app: String? = nil,
        limit: Int = 60
    ) throws -> (hits: [Hit], truncated: Bool) {
        guard limit > 0 else { return ([], false) }
        // Asks for one more than it will return. Capping exactly at the limit makes a truncated
        // answer indistinguishable from a complete one — the caller counts `limit` hits and cannot
        // tell whether that was all there was, so it renders a bounded slice as the whole record.
        // The extra moment is discarded; its existence is the entire signal. `screen` keeps its
        // contract of returning at most `limit`, because callers depend on that.
        let overFetched = try screen(store, since: since, until: until, app: app, limit: limit + 1)
        return (cap(overFetched, to: limit), overFetched.count > limit)
    }

    // MARK: - Conversations

    /// Session headers, newest first. Enough for a reader to decide which transcript to pull.
    public static func sessions(
        _ store: ContextStore,
        since: Double? = nil,
        until: Double? = nil,
        limit: Int = 30
    ) throws -> [SessionSummary] {
        guard limit > 0 else { return [] }

        return try store.read { db in
            var sql = """
                SELECT s.id AS id,
                       s.startedAt AS startedAt,
                       s.endedAt AS endedAt,
                       s.appHint AS appHint,
                       COUNT(g.id) AS lineCount,
                       MAX(g.endedAt) AS lastLineAt,
                       MAX(CASE WHEN g.source = 'mic' THEN 1 ELSE 0 END) AS hasMic,
                       MAX(CASE WHEN g.source = 'system' THEN 1 ELSE 0 END) AS hasSystem
                FROM sessions s
                LEFT JOIN segments g ON g.sessionId = s.id
                """
            var args: [(any DatabaseValueConvertible)?] = []
            var conditions: [String] = []
            if let since {
                conditions.append("s.startedAt >= ?")
                args.append(since)
            }
            if let until {
                conditions.append("s.startedAt <= ?")
                args.append(until)
            }
            if !conditions.isEmpty {
                sql += "\nWHERE " + conditions.joined(separator: " AND ")
            }
            sql += "\nGROUP BY s.id\nORDER BY s.startedAt DESC\nLIMIT ?"
            args.append(limit)

            let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
            return try rows.map { row in
                let rawID: Int64? = row["id"]
                let rawStartedAt: Double? = row["startedAt"]
                let rawLineCount: Int? = row["lineCount"]
                let rawHasMic: Int? = row["hasMic"]
                let rawHasSystem: Int? = row["hasSystem"]
                let endedAt: Double? = row["endedAt"]
                let lastLineAt: Double? = row["lastLineAt"]
                let appHint: String? = row["appHint"]

                let id = rawID ?? 0
                let startedAt = rawStartedAt ?? 0
                // An open session still has a real duration — the last line it recorded.
                let finishedAt = endedAt ?? lastLineAt ?? startedAt

                return SessionSummary(
                    id: id,
                    startedAt: startedAt,
                    endedAt: endedAt,
                    durationSeconds: max(0, finishedAt - startedAt),
                    appHint: appHint,
                    lineCount: rawLineCount ?? 0,
                    bothSidesPresent: (rawHasMic ?? 0) > 0 && (rawHasSystem ?? 0) > 0,
                    preview: try preview(db, sessionId: id),
                    personIds: try people(db, sessionId: id)
                )
            }
        }
    }

    /// One session in full, in the order it was spoken.
    public static func transcript(_ store: ContextStore, sessionId: Int64) throws -> [Hit] {
        try store.read { db in
            try Row.fetchAll(
                db,
                sql: """
                    SELECT startedAt AS at, source, text, sessionId, confidence,
                           speakerLabel, personId
                    FROM segments
                    WHERE sessionId = ?
                    ORDER BY startedAt ASC, id ASC
                    """,
                arguments: [sessionId]
            ).map(segmentHit)
        }
    }

    // MARK: - Activity

    /// The shape of a stretch of time: consecutive frames of one app collapsed into single blocks.
    ///
    /// **Read as a cursor, not as an array.** `since` and `until` come from the caller and no layer
    /// bounds the rows between them — the MCP tool takes whatever date the model asks for, and the
    /// default storage strategy prunes nothing — so "every frame in the range" is a real answer of
    /// unbounded size. Measured against a synthetic year of capture, `Row.fetchAll` here returned
    /// 547,500 rows carrying 779 MiB of OCR text, all of it held at once to produce a collapse a few
    /// thousand blocks long. The fold consumes each row and lets it go, so what is held is the
    /// blocks, which is the thing the caller actually asked for.
    ///
    /// The read still walks the range over `idx_frames_capturedAt`, so the *rows* are still read;
    /// what stops is holding them.
    public static func activity(_ store: ContextStore, since: Double, until: Double) throws -> [ActivityBlock] {
        try store.read { db in
            var accumulator = BlockAccumulator()
            let cursor = try Row.fetchCursor(
                db,
                sql: """
                    SELECT capturedAt, appName, windowTitle, ocrText
                    FROM frames
                    WHERE capturedAt >= ? AND capturedAt <= ?
                      AND appName IS NOT NULL AND TRIM(appName) <> ''
                    ORDER BY capturedAt ASC, id ASC
                    """,
                arguments: [since, until])
            while let row = try cursor.next() {
                accumulator.append(FrameRow(row))
            }
            return accumulator.finish()
        }
    }

    // MARK: - Status

    /// **Whether this Mac has ever had a screen frame captured on it.**
    ///
    /// The durable answer to "did this used to work", and it has to come from the database because
    /// the cheap answer cannot. macOS reports a permission that was never granted and a permission
    /// it silently revoked with the same `false`, so the app writes down the first time each stream
    /// genuinely produces something — but a flag introduced today is absent on every install that
    /// predates it, including the one whose Screen Recording grant died when the bundle was
    /// re-signed and which therefore most needs to know the difference. The rows already on disk
    /// are the proof, so they are what seeds it.
    ///
    /// `EXISTS` rather than `COUNT(*)`: this runs once per launch on a table that holds a month of
    /// capture, and the question is "any" rather than "how many".
    public static func hasAnyFrames(_ store: ContextStore) throws -> Bool {
        try store.read { db in
            try Bool.fetchOne(db, sql: "SELECT EXISTS(SELECT 1 FROM frames)") ?? false
        }
    }

    /// Capture health plus coverage, so a reader can tell "never happened" from "not captured".
    ///
    /// Pass `heartbeat: .fixed(...)` in tests so capturing + gap copy can be asserted without
    /// writing the real Application Support heartbeat. Production callers use the default `.live`.
    public static func status(
        _ store: ContextStore,
        heartbeat: HeartbeatSource = .live
    ) throws -> StatusInfo {
        let totals: Totals = try store.read { db in
            let row = try Row.fetchOne(
                db,
                sql: """
                    SELECT (SELECT COUNT(*) FROM segments) AS segmentCount,
                           (SELECT COUNT(*) FROM frames) AS frameCount,
                           (SELECT COUNT(*) FROM sessions) AS sessionCount,
                           (SELECT MIN(startedAt) FROM segments) AS oldestSegment,
                           (SELECT MAX(startedAt) FROM segments) AS newestSegment,
                           (SELECT MIN(capturedAt) FROM frames) AS oldestFrame,
                           (SELECT MAX(capturedAt) FROM frames) AS newestFrame
                    """
            )
            return Totals(row)
        }

        // The heartbeat file is the only live signal the MCP server has; a stale one means the app
        // is gone, whatever it last claimed.
        let state: CaptureState?
        switch heartbeat {
        case .live:
            state = CaptureState.read()
        case .fixed(let injected):
            state = injected
        }
        let live = state.map { !$0.isStale } ?? false
        let capturing = live && (state?.capturing ?? false)
        // A process that is gone is `off` whatever its last beat claimed; a live one keeps its own
        // three-valued answer, which is the only way `degraded` survives the trip to Claude.
        let health: CaptureHealth = live ? (state?.health ?? .off) : .off
        let pausedReason: String?
        if capturing {
            // Sensors can be live while a gap remains (Intel cloud ASR down, mic denied, etc.).
            // Pass the heartbeat reason through so MCP `status` matches the menu bar — including
            // when health is `.capturing` and the gap is transcription-only.
            pausedReason = state?.pausedReason
        } else if live {
            // Deliberately *not* cleared for `degraded`. This branch used to be keyed on
            // `capturing`, and a degraded recorder is exactly the state whose reason a reader most
            // needs — "Screen off — Screen Recording permission not granted" is the sentence that
            // was thrown away for twenty-nine hours.
            pausedReason = state?.pausedReason ?? "Capture is paused"
        } else {
            pausedReason = "Context for Claude is not running"
        }

        return StatusInfo(
            capturing: capturing,
            health: health,
            pausedReason: pausedReason,
            // Permission grants outlive the process, so last-known capabilities beat none at all.
            capabilities: state?.capabilities ?? [],
            // Only from a live beat: a stream report from a process that has since exited says
            // nothing about now, and "screen stalled" read off a dead app is a false alarm.
            streams: live ? (state?.streams ?? []) : [],
            segmentCount: totals.segments,
            frameCount: totals.frames,
            sessionCount: totals.sessions,
            oldestAt: totals.oldest,
            newestAt: totals.newest,
            databasePath: ContextPaths.databaseURL.path
        )
    }

    // MARK: - FTS sanitization

    /// Characters that make FTS5 read a human phrase as syntax — and, because `porter unicode61`
    /// breaks a token on every one of them too, the places a typed word splits into the terms the
    /// index actually holds. See `readings(of:)`.
    private static let ftsOperatorCharacters = CharacterSet(charactersIn: "\"*:^()-")
    /// FTS5 keywords. Compared case-insensitively so `"and"` can never survive into an expression.
    private static let ftsOperatorWords: Set<String> = ["AND", "OR", "NOT", "NEAR"]

    /// Turns arbitrary human input into an FTS5 MATCH expression that cannot be a syntax error.
    ///
    /// Terms are OR-joined rather than AND-joined: a recall over ambient capture should surface
    /// anything related and let the reader judge, not return nothing because one word was missing.
    /// Returns nil when nothing survives, so callers answer with an empty result instead of
    /// handing SQLite a query like `""` or `*`.
    public static func ftsExpression(for query: String) -> String? {
        let terms = sanitizedTerms(in: query).map { "\"\($0)\"" }

        guard !terms.isEmpty else { return nil }
        return terms.joined(separator: " OR ")
    }

    /// The terms behind `ftsExpression`, in query order.
    ///
    /// Extracted rather than duplicated: the coverage boost has to score the exact set of terms the
    /// MATCH searched for, or a document could be credited for a term the index never looked at.
    private static func sanitizedTerms(in query: String) -> [String] {
        queryReadings(in: query).flatMap { $0 }
    }

    /// The terms behind `ftsExpression`, grouped by the word the user typed.
    private static func queryReadings(in query: String) -> [[String]] {
        query
            .split(whereSeparator: { $0.isWhitespace })
            .map(readings(of:))
            .filter { !$0.isEmpty }
    }

    /// Every reading of one typed word that the index could be holding it under.
    ///
    /// `porter unicode61` tokenises `SCA-219` into `sca` and `219`. The sanitizer used to *strip*
    /// the hyphen and search for `sca219`, a token no document the index built can ever contain — so
    /// every ticket id, version string, hyphenated name and URL fragment was unfindable by the exact
    /// string a person would type. That is worse than a missing result: the miss comes back phrased
    /// as a searched-and-found-nothing negative, which is the licence a reader has to conclude the
    /// thing never happened.
    ///
    /// A word is therefore read the way `documentTokens` already reads a document — both ways at
    /// once. An operator character splits the word in one reading and is spanned in the other, so
    /// `SCA-219` searches for `sca`, `219` *and* `sca219`, and a document that wrote the identifier
    /// either way is found. Any other punctuation is a break in both readings, because unicode61
    /// does not join across it either: `Priyanka's` has to reach `priyanka`, not ask for the
    /// two-token phrase `priyanka s` that no document says.
    ///
    /// Every reading is a run of alphanumerics, so the quoted phrase `ftsExpression` builds from one
    /// cannot contain FTS5 syntax — hostile input has nothing left to smuggle through.
    private static func readings(of token: Substring) -> [String] {
        var split: [String] = []
        var spanning: [String] = []
        var piece = ""
        var run = ""

        func endPiece() {
            guard !piece.isEmpty else { return }
            split.append(piece)
            piece = ""
        }
        func endRun() {
            guard !run.isEmpty else { return }
            spanning.append(run)
            run = ""
        }

        for scalar in token.unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                piece.unicodeScalars.append(scalar)
                run.unicodeScalars.append(scalar)
            } else if ftsOperatorCharacters.contains(scalar) {
                endPiece()
            } else {
                endPiece()
                endRun()
            }
        }
        endPiece()
        endRun()

        var seen: Set<String> = []
        return (split + spanning).filter { term in
            // An FTS5 keyword that survived would be read as syntax rather than as the word the
            // user typed.
            guard !ftsOperatorWords.contains(term.uppercased()) else { return false }
            // An unpunctuated word reads the same both ways; searching for it twice would only
            // double its weight in bm25.
            return seen.insert(term.lowercased()).inserted
        }
    }

    /// Case-folded distinct readings, still grouped by typed word: the denominator of the coverage
    /// boost counts *words*, not the terms they split into. Typing a word twice must not make a
    /// document that contains it look twice as relevant — and neither must typing one with a hyphen
    /// in it, which is the whole reason the grouping survives this far down.
    private static func distinctTerms(in query: String) -> [[String]] {
        var seen: Set<String> = []
        var groups: [[String]] = []
        for group in queryReadings(in: query) {
            let folded = group.map { $0.lowercased() }.filter { seen.insert($0).inserted }
            if !folded.isEmpty { groups.append(folded) }
        }
        return groups
    }

    // MARK: - Row fetching

    private static func matchedSegments(
        _ db: Database,
        match: String,
        terms: [[String]],
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Candidate] {
        var sql = """
            SELECT s.startedAt AS at, s.source AS source, s.text AS text, s.sessionId AS sessionId,
                   s.confidence AS confidence,
                   s.speakerLabel AS speakerLabel, s.personId AS personId,
                   bm25(segments_fts) AS bm25Score
            FROM segments_fts
            JOIN segments s ON s.rowid = segments_fts.rowid
            WHERE segments_fts MATCH ?
            """
        var args: [(any DatabaseValueConvertible)?] = [match]
        if let since {
            sql += "\n  AND s.startedAt >= ?"
            args.append(since)
        }
        if let until {
            sql += "\n  AND s.startedAt <= ?"
            args.append(until)
        }
        // bm25 is negative and more negative is better, so ascending is best-first. Recency only
        // settles ties here; it decides nothing about which rows survive the pool cut.
        sql += "\nORDER BY bm25Score ASC, s.startedAt DESC\nLIMIT ?"
        args.append(limit)

        let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
        return candidates(
            rows,
            terms: terms,
            hit: segmentHit,
            document: { row in
                let text: String? = row["text"]
                return text ?? ""
            },
            signature: { _ in nil })
    }

    /// Whether a query holds anything the index cannot represent but a reader still meant.
    ///
    /// True for emoji, pictographs and symbols — `unicode61` treats them as separators, so they are
    /// in no index and a substring scan is the only way to them. False for punctuation and
    /// whitespace, which are separators everywhere and mean nothing on their own: scanning for a
    /// bare `"` returns every row containing a quotation mark, which answers a question nobody
    /// asked. Alphanumerics are excluded because the index already holds them.
    private static func carriesUnindexableContent(_ query: String) -> Bool {
        query.unicodeScalars.contains { scalar in
            !CharacterSet.alphanumerics.contains(scalar)
                && !CharacterSet.punctuationCharacters.contains(scalar)
                && !CharacterSet.whitespacesAndNewlines.contains(scalar)
                && !CharacterSet.controlCharacters.contains(scalar)
        }
    }

    /// Substring search, for the queries no index can answer.
    ///
    /// Deliberately the narrow path and not a general fallback: it runs only when `ftsExpression`
    /// produced nothing, so a query with any searchable word never reaches it and never pays for it.
    /// `LIKE` cannot use the FTS index and scans, which is affordable exactly because this case is
    /// rare and the row cap applies to the scan itself.
    ///
    /// Case folding is left to SQLite's `LIKE`, which is ASCII-only — irrelevant here, since the
    /// characters that land on this path (emoji, symbols, pictographs) have no case at all.
    ///
    /// The escape character keeps user-supplied `%` and `_` from being treated as wildcards.
    private static let likeEscape = "\\"

    private static func likeLiteral(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "%", with: "\\%")
            .replacingOccurrences(of: "_", with: "\\_")
    }

    private static func literalScan(
        _ store: ContextStore,
        needle: String,
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Hit] {
        let trimmed = needle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        let escaped = likeLiteral(trimmed)
        let pattern = "%\(escaped)%"

        return try store.read { db -> [Hit] in
            var frameSQL = """
                SELECT capturedAt AS at, appName, windowTitle, ocrText, axText
                FROM frames
                WHERE (ocrText LIKE ? ESCAPE '\\' OR windowTitle LIKE ? ESCAPE '\\' OR axText LIKE ? ESCAPE '\\')
                """
            var frameArgs: [(any DatabaseValueConvertible)?] = [pattern, pattern, pattern]
            if let since { frameSQL += "\n  AND capturedAt >= ?"; frameArgs.append(since) }
            if let until { frameSQL += "\n  AND capturedAt <= ?"; frameArgs.append(until) }
            frameSQL += "\nORDER BY capturedAt DESC\nLIMIT ?"
            frameArgs.append(limit)

            var spokenSQL = """
                SELECT startedAt AS at, source, text, sessionId, confidence, speakerLabel, personId
                FROM segments
                WHERE text LIKE ? ESCAPE '\\'
                """
            var spokenArgs: [(any DatabaseValueConvertible)?] = [pattern]
            if let since { spokenSQL += "\n  AND startedAt >= ?"; spokenArgs.append(since) }
            if let until { spokenSQL += "\n  AND startedAt <= ?"; spokenArgs.append(until) }
            spokenSQL += "\nORDER BY startedAt DESC\nLIMIT ?"
            spokenArgs.append(limit)

            let frames = try Row.fetchAll(db, sql: frameSQL, arguments: StatementArguments(frameArgs))
            let spoken = try Row.fetchAll(db, sql: spokenSQL, arguments: StatementArguments(spokenArgs))

            // Newest first and capped, matching what the ranked path returns. There is no lexical
            // score to rank by — every row contains the needle exactly, so recency is the only
            // signal left and pretending otherwise would invent an ordering.
            let hits = (spoken.map(segmentHit) + frames.map(frameHit)).sorted { $0.at > $1.at }
            return Array(hits.prefix(limit))
        }
    }

    private static func matchedFrames(
        _ db: Database,
        match: String,
        terms: [[String]],
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Candidate] {
        // Two indexes, one result set. OCR and the accessibility tree see different halves of the
        // same window and fail in opposite directions: OCR reads everything drawn and guesses at it,
        // while the tree is exact but covers only what the application chose to expose. A frame
        // matched by either is a frame the user saw, so their union is the honest candidate set —
        // OCR alone made every window that draws its text as a canvas unfindable, and the tree alone
        // would lose every window that exposes nothing.
        //
        // `MIN(score)` keeps whichever index matched it better rather than averaging a strong match
        // against a missing one, and the GROUP BY is what stops a frame both indexes matched from
        // arriving twice.
        var sql = """
            SELECT f.capturedAt AS at, f.appName AS appName, f.windowTitle AS windowTitle,
                   f.ocrText AS ocrText, f.axText AS axText, MIN(m.score) AS bm25Score
            FROM (
                SELECT rowid AS rid,
                       bm25(frames_fts, \(frameOCRWeight), \(frameTitleWeight), \(frameAppWeight)) AS score
                FROM frames_fts WHERE frames_fts MATCH ?
                UNION ALL
                SELECT rowid AS rid, bm25(frames_ax_fts) AS score
                FROM frames_ax_fts WHERE frames_ax_fts MATCH ?
            ) m
            JOIN frames f ON f.rowid = m.rid
            WHERE 1 = 1
            """
        var args: [(any DatabaseValueConvertible)?] = [match, match]
        if let since {
            sql += "\n  AND f.capturedAt >= ?"
            args.append(since)
        }
        if let until {
            sql += "\n  AND f.capturedAt <= ?"
            args.append(until)
        }
        sql += "\nGROUP BY f.rowid\nORDER BY bm25Score ASC, f.capturedAt DESC\nLIMIT ?"
        args.append(limit)

        let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
        return candidates(
            rows,
            terms: terms,
            hit: frameHit,
            document: { row in
                let app: String? = row["appName"]
                let window: String? = row["windowTitle"]
                let ocr: String? = row["ocrText"]
                let ax: String? = row["axText"]
                // Coverage reads the untruncated row: `frameHit` clips text for the reader, and a
                // term that fell off the end of the snippet is still a term the frame contained.
                // Both readings of the window count — a term OCR mangled may be intact in the tree.
                return [window, app, ocr, ax].compactMap { $0 }.joined(separator: " ")
            },
            signature: { frameSignature($0) })
    }

    private static func segmentRows(_ db: Database, since: Double?, until: Double?, limit: Int) throws -> [Row] {
        var sql = """
            SELECT startedAt AS at, source, text, sessionId, confidence, speakerLabel, personId
            FROM segments
            """
        var args: [(any DatabaseValueConvertible)?] = []
        var conditions: [String] = []
        if let since {
            conditions.append("startedAt >= ?")
            args.append(since)
        }
        if let until {
            conditions.append("startedAt <= ?")
            args.append(until)
        }
        if !conditions.isEmpty {
            sql += "\nWHERE " + conditions.joined(separator: " AND ")
        }
        sql += "\nORDER BY startedAt DESC, id DESC\nLIMIT ?"
        args.append(limit)

        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
    }

    private static func frameRows(
        _ db: Database,
        since: Double?,
        until: Double?,
        app: String?,
        limit: Int
    ) throws -> [Row] {
        var sql = """
            SELECT capturedAt AS at, appName, windowTitle, ocrText
            FROM frames
            """
        var args: [(any DatabaseValueConvertible)?] = []
        var conditions: [String] = []
        if let since {
            conditions.append("capturedAt >= ?")
            args.append(since)
        }
        if let until {
            conditions.append("capturedAt <= ?")
            args.append(until)
        }
        if let app = app?.trimmingCharacters(in: .whitespacesAndNewlines), !app.isEmpty {
            // Substring match: callers pass "Chrome" and mean "Google Chrome".
            // Escape the user's input so "%" or "_" do not become wildcards.
            conditions.append("appName LIKE ? ESCAPE '\\'")
            args.append("%\(likeLiteral(app))%")
        }
        if !conditions.isEmpty {
            sql += "\nWHERE " + conditions.joined(separator: " AND ")
        }
        sql += "\nORDER BY capturedAt DESC, id DESC\nLIMIT ?"
        args.append(limit)

        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
    }

    private static func preview(_ db: Database, sessionId: Int64) throws -> String {
        let rows = try Row.fetchAll(
            db,
            sql: """
                SELECT source, speaker, text
                FROM segments
                WHERE sessionId = ?
                ORDER BY startedAt ASC, id ASC
                LIMIT ?
                """,
            arguments: [sessionId, sessionPreviewLines]
        )
        let lines: [String] = rows.compactMap { row in
            let source: String? = row["source"]
            let speaker: String? = row["speaker"]
            let text: String? = row["text"]
            guard let text = collapsedNonEmpty(text) else { return nil }
            return "\(speakerLabel(source: source, speaker: speaker)): \(text)"
        }
        return truncate(lines.joined(separator: " / "), to: sessionPreviewLimit)
    }

    /// The distinct Omi people the backend identified in one session, in the order they first spoke.
    ///
    /// A second small query per session rather than a `group_concat` in the header query: the ids
    /// are opaque strings from another system, and a delimiter that turns out to occur inside one
    /// would silently split a person in two. `preview` already reads per session on the same index,
    /// and both are bounded by `limit`.
    ///
    /// Ids, never names. What the account currently calls a person is a fact about the account and
    /// is answered by whoever holds the credential to ask it — this layer reports who was captured,
    /// and it has to still be right after a rename.
    private static func people(_ db: Database, sessionId: Int64) throws -> [String] {
        try String.fetchAll(
            db,
            sql: """
                SELECT personId
                FROM segments
                WHERE sessionId = ? AND personId IS NOT NULL AND TRIM(personId) <> ''
                GROUP BY personId
                ORDER BY MIN(startedAt) ASC, personId ASC
                """,
            arguments: [sessionId])
    }

    // MARK: - Ranking

    /// A hit plus the two comparable relevance signals derived from it. `lexical` is already
    /// normalised against the best hit of its own FTS table, so candidates from both tables can be
    /// scored side by side.
    private struct Candidate {
        let hit: Hit
        let coverage: Double
        let lexical: Double
        /// Set for screen frames only — what the moment grouper needs, carried from the row so the
        /// untruncated OCR is what gets compared rather than the snippet a reader sees.
        let frame: FrameSignature?
    }

    /// Turns one table's matched rows into candidates, normalising bm25 within that table.
    private static func candidates(
        _ rows: [Row],
        terms: [[String]],
        hit: (Row) -> Hit,
        document: (Row) -> String,
        signature: (Row) -> FrameSignature?
    ) -> [Candidate] {
        // SQLite returns bm25 as a negative number where more negative is a better match, and clamps
        // its IDF to a small positive value, so flipping the sign always yields a quality >= 0.
        let qualities = rows.map { row -> Double in
            let score: Double? = row["bm25Score"]
            return max(0, -(score ?? 0))
        }
        let best = qualities.max() ?? 0

        return zip(rows, qualities).map { row, quality in
            Candidate(
                hit: hit(row),
                coverage: coverage(of: document(row), terms: terms),
                // A table whose matches are all degenerate ranks on coverage and recency alone
                // rather than dividing by zero.
                lexical: best > 0 ? quality / best : 1,
                frame: signature(row))
        }
    }

    private struct Scored {
        let hit: Hit
        let score: Double
        let frame: FrameSignature?
    }

    /// Scores, floors, and orders the merged candidate set. Best match first; recency only decides
    /// between hits the lexical signals could not separate.
    private static func ranked(_ pool: [Candidate]) -> [Hit] {
        guard let newest = pool.map(\.hit.at).max() else { return [] }

        // Recency is measured against the newest candidate rather than the wall clock, so the same
        // corpus always ranks the same way however long ago it was captured.
        //
        // The formula lives in the portable C++ core so every host agrees: `ctx_recall_score`
        // blends coverage, lexical quality, and an age penalty; `ctx_relevance_floor` computes
        // the threshold below which partial-coverage hits are dropped.
        let scored = pool.map { candidate -> Scored in
            let age = max(0, newest - candidate.hit.at)
            return Scored(
                hit: candidate.hit,
                score: ctx_recall_score(candidate.coverage, candidate.lexical, age),
                frame: candidate.frame)
        }

        // Moments are formed on the *scored* candidate set, before the floor and the cap. Collapsing
        // afterwards would be pointless — `limit` would already have been spent on near-duplicates —
        // and collapsing before scoring would leave the grouper picking a representative blind.
        let moments = collapsedMoments(scored)

        guard let best = moments.map(\.score).max() else { return [] }
        let floor = ctx_relevance_floor(best)

        return moments
            .filter { $0.score >= floor }
            .sorted { lhs, rhs in
                if lhs.score != rhs.score { return lhs.score > rhs.score }
                if lhs.hit.at != rhs.hit.at { return lhs.hit.at > rhs.hit.at }
                // Deterministic ties, and speech reads better before the screen it was said in
                // front of.
                return kindRank(lhs.hit.kind) < kindRank(rhs.hit.kind)
            }
            .map(\.hit)
    }

    /// Collapses the screen half of a scored candidate set into moments. Speech passes through
    /// untouched — a transcript line is already one event.
    private static func collapsedMoments(_ scored: [Scored]) -> [Scored] {
        var result: [Scored] = []
        var frames: [(entry: Scored, signature: FrameSignature)] = []
        for entry in scored {
            if let signature = entry.frame {
                frames.append((entry, signature))
            } else {
                result.append(entry)
            }
        }
        guard !frames.isEmpty else { return result }

        // The FTS pool comes back best-match-first; the grouper walks time forwards.
        frames.sort { $0.entry.hit.at < $1.entry.hit.at }
        let inputs = frames.map { MomentInput(at: $0.entry.hit.at, signature: $0.signature) }

        for group in momentGroups(inputs) {
            guard let first = group.first, let last = group.last else { continue }
            // The moment is introduced by the frame that actually answered the query, not by
            // whichever one happened to come first. Collapsing a run down to its weakest member
            // would hand back a ranking bug wearing a dedupe's clothes.
            var bestIndex = first
            for index in group.dropFirst() {
                let contender = frames[index].entry
                let incumbent = frames[bestIndex].entry
                if contender.score > incumbent.score
                    || (contender.score == incumbent.score && contender.hit.at > incumbent.hit.at) {
                    bestIndex = index
                }
            }
            let representative = frames[bestIndex].entry
            result.append(
                Scored(
                    hit: momentHit(
                        representative.hit,
                        frames: group.count,
                        from: frames[first].entry.hit.at,
                        to: frames[last].entry.hit.at),
                    score: representative.score,
                    frame: representative.frame))
        }
        return result
    }

    /// Fraction of the distinct query *words* this document actually contains.
    ///
    /// The point of the OR expression is that nothing is lost; the point of this number is that a
    /// document matching three of four words outranks one matching a single incidental word.
    ///
    /// A word the index split into several terms is still one word: a document holding `SCA-219` in
    /// full covers it, one holding only `219` covers part of it. Counting the terms instead would
    /// let a hyphen buy a query word two votes, which is a ranking change smuggled in behind a
    /// tokenizer fix.
    ///
    /// Never returns zero: the row is in the result set because FTS matched *something*, so a zero
    /// here would only ever mean our tokenizer and the porter-stemmed index disagreed — and an
    /// under-credited match is the direction that costs a true hit its place.
    private static func coverage(of document: String, terms: [[String]]) -> Double {
        guard !terms.isEmpty else { return 1 }
        let tokens = documentTokens(document)
        let matched = terms.reduce(into: 0.0) { total, readings in
            let found = readings.filter { term in
                tokens.contains(term) || tokens.contains(where: { inflected($0, matches: term) })
            }
            total += Double(found.count) / Double(readings.count)
        }
        // The floor is for the disagreement case only. Raising a genuine partial credit to a whole
        // word would throw away exactly the distinction the grouping just bought.
        return (matched > 0 ? matched : 1) / Double(terms.count)
    }

    /// Lowercased word tokens of a document, indexed under *both* readings of a punctuated
    /// identifier.
    ///
    /// The unicode61 tokenizer splits on an operator character, so the index holds `sca` and `219`
    /// for a document that wrote `SCA-219`; a query can arrive carrying either that split reading or
    /// the joined `sca219`. Emitting only one reading here loses coverage credit for a document the
    /// index genuinely matched, and under-credited coverage is the direction that costs a true match
    /// its place. `readings(of:)` does the same on the query side, so the two now agree by
    /// construction rather than by luck.
    private static func documentTokens(_ document: String) -> Set<String> {
        var tokens: Set<String> = []
        var joined = ""
        var split = ""

        for scalar in document.unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                joined.unicodeScalars.append(scalar)
                split.unicodeScalars.append(scalar)
            } else if ftsOperatorCharacters.contains(scalar) {
                flush(&split, into: &tokens)
            } else {
                flush(&joined, into: &tokens)
                flush(&split, into: &tokens)
            }
        }
        flush(&joined, into: &tokens)
        flush(&split, into: &tokens)
        return tokens
    }

    private static func flush(_ token: inout String, into tokens: inout Set<String>) {
        guard !token.isEmpty else { return }
        tokens.insert(token.lowercased())
        token = ""
    }

    /// The suffixes the porter-stemmed index folds away but a plain token comparison would not.
    private static let inflectionSuffixes: Set<String> = ["s", "es", "d", "ed", "ing", "ly", "er", "ers"]

    /// Deliberately narrower than a prefix test: `pack` must not be credited for `package`, because
    /// crediting incidental prefixes is how a bookmark bar came to outrank a real match.
    private static func inflected(_ token: String, matches term: String) -> Bool {
        let (longer, shorter) = token.count >= term.count ? (token, term) : (term, token)
        guard shorter.count >= 3, longer.count > shorter.count, longer.hasPrefix(shorter) else {
            return false
        }
        return inflectionSuffixes.contains(String(longer.dropFirst(shorter.count)))
    }

    // MARK: - Moment grouping

    /// Everything the grouper reads out of a frame.
    ///
    /// Words are hashed because the only questions ever asked of them are "how many of these does
    /// the moment already contain" and "how many are new" — a `Set<Int>` answers both several times
    /// faster than a `Set<String>` and holds a fraction of the memory.
    private struct FrameSignature {
        let appKey: String
        let windowKey: String
        let words: Set<Int>

        /// One string so the grouper hashes once per frame. `\u{1}` cannot occur in either half.
        var key: String { appKey + "\u{1}" + windowKey }
    }

    private struct MomentInput {
        let at: Double
        let signature: FrameSignature
    }

    // MARK: - Moment grouping
    ///
    /// `frames` must be in ascending time order. Groups come back in the order they opened, and
    /// every index appears in exactly one — nothing is dropped here, only gathered.
    ///
    /// Delegates to `ctx_moment_groups` in the portable C++ core. This layer builds flat buffers
    /// (key bytes, word hashes, frame descriptors) from the Swift structures and converts the
    /// per-frame group assignments back into index groups.
    private static func momentGroups(_ frames: [MomentInput]) -> [[Int]] {
        guard !frames.isEmpty else { return [] }

        // Build flat buffers for the C ABI.
        var keyData = Data()
        var allWords = [Int64]()
        var cFrames = [ctx_moment_frame]()
        cFrames.reserveCapacity(frames.count)

        for input in frames {
            let keyBytes = Array(input.signature.key.utf8)
            let keyStart = keyData.count
            keyData.append(contentsOf: keyBytes)

            let wordStart = allWords.count
            for word in input.signature.words {
                allWords.append(Int64(truncatingIfNeeded: word))
            }

            var frame = ctx_moment_frame()
            frame.at = input.at
            frame.key_offset = keyStart
            frame.key_length = keyBytes.count
            frame.word_offset = wordStart
            frame.word_count = input.signature.words.count
            cFrames.append(frame)
        }

        var outGroupOfFrame = [Int32](repeating: 0, count: frames.count)

        // Capture lengths before entering the nested closures to avoid overlapping access violations.
        let cFrameCount = cFrames.count
        let keyDataLength = keyData.count
        let wordsCount = allWords.count

        let groupCount = cFrames.withUnsafeBufferPointer { framesPtr in
            keyData.withUnsafeMutableBytes { rawKeyPtr in
                allWords.withUnsafeBufferPointer { wordsPtr in
                    outGroupOfFrame.withUnsafeMutableBufferPointer { outPtr in
                        ctx_moment_groups(
                            framesPtr.baseAddress, cFrameCount,
                            rawKeyPtr.baseAddress?.assumingMemoryBound(to: CChar.self), keyDataLength,
                            wordsPtr.baseAddress, wordsCount,
                            outPtr.baseAddress)
                    }
                }
            }
        }

        guard groupCount > 0 else { return [] }

        var groups = [[Int]](repeating: [], count: Int(groupCount))
        for (index, group) in outGroupOfFrame.enumerated() {
            groups[Int(group)].append(index)
        }
        return groups
    }

    /// The app name is not part of the compared text: it is identical across every frame from that
    /// app, so including it would only ever dilute the novelty ratio. It is part of the *key*.
    private static func frameSignature(_ row: Row) -> FrameSignature {
        let app: String? = row["appName"]
        let window: String? = row["windowTitle"]
        let ocr: String? = row["ocrText"]
        return FrameSignature(
            appKey: (app ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            windowKey: titleKey(window),
            words: words(in: [window, ocr].compactMap { $0 }.joined(separator: " ")))
    }

    /// The window title reduced to its lowercased words.
    ///
    /// A decoration character in a title is not a different window. Measured on this machine, Warp
    /// cycles a spinner glyph through the title between consecutive three-second frames; comparing
    /// titles literally turns one long session into a run of singletons, which is the failure this
    /// whole pass exists to remove.
    private static func titleKey(_ title: String?) -> String {
        guard let title else { return "" }
        var parts: [String] = []
        var token = ""
        for scalar in title.unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                token.unicodeScalars.append(scalar)
            } else if !token.isEmpty {
                parts.append(token.lowercased())
                token.removeAll(keepingCapacity: true)
            }
        }
        if !token.isEmpty { parts.append(token.lowercased()) }
        return parts.joined(separator: " ")
    }

    /// Hashed lowercase word tokens.
    ///
    /// Deliberately not `documentTokens`: that one indexes a punctuated identifier under both its
    /// readings so coverage cannot under-credit a match the FTS index made. Here the question is
    /// "how much of this page have I already seen", and counting `sca-219` twice would quietly
    /// inflate the overlap between any two frames that contain it.
    private static func words(in text: String) -> Set<Int> {
        var result: Set<Int> = []
        var token = ""
        for scalar in text.unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                token.unicodeScalars.append(scalar)
            } else if !token.isEmpty {
                result.insert(token.lowercased().hashValue)
                token.removeAll(keepingCapacity: true)
                if result.count >= momentWordCeiling { return result }
            }
        }
        if !token.isEmpty { result.insert(token.lowercased().hashValue) }
        return result
    }

    private static let momentTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    /// The representative of a moment, with the span and the frame count spelled out in front of its
    /// text.
    ///
    /// A moment of one frame is returned untouched: a single observation must read exactly as it
    /// always did, or every caller pays for a feature that collapsed nothing.
    private static func momentHit(_ representative: Hit, frames: Int, from: Double, to: Double) -> Hit {
        guard frames > 1 else { return representative }

        let start = Date(timeIntervalSince1970: from)
        let end = Date(timeIntervalSince1970: to)
        let span: String
        if Calendar.current.isDate(start, inSameDayAs: end) {
            span = momentTimeFormatter.string(from: start) + "–" + momentTimeFormatter.string(from: end)
        } else {
            span = ContextTime.describe(from) + " – " + ContextTime.describe(to)
        }
        let prefix = "[\(frames) frames · \(span)] "

        return Hit(
            kind: representative.kind,
            at: representative.at,
            // The budget is the reader's, not the moment's: the prefix comes out of the same ~600
            // characters a single screen hit was always allowed.
            text: prefix + truncate(representative.text, to: max(1, screenTextLimit - prefix.count)),
            app: representative.app,
            window: representative.window,
            sessionId: representative.sessionId,
            // Nil in practice — only frames are collapsed — but carried rather than defaulted, so a
            // rebuilt hit can never quietly lose what the one it stands for knew.
            confidence: representative.confidence,
            speakerLabel: representative.speakerLabel,
            personId: representative.personId
        )
    }

    /// Collapses raw frame rows, newest-first as `frameRows` returns them, into moment hits.
    private static func screenMoments(_ rows: [Row]) -> [Hit] {
        let ascending = Array(rows.reversed())
        let inputs = ascending.map { row -> MomentInput in
            let at: Double? = row["at"]
            return MomentInput(at: at ?? 0, signature: frameSignature(row))
        }

        return momentGroups(inputs).compactMap { group -> Hit? in
            guard let first = group.first, let last = group.last else { return nil }
            // The newest frame speaks for the moment: it is the freshest state that window reached,
            // and it is what keeps a newest-first list honest.
            return momentHit(
                frameHit(ascending[last]),
                frames: group.count,
                from: inputs[first].at,
                to: inputs[last].at)
        }
    }

    // MARK: - Row → Hit

    private static func segmentHit(_ row: Row) -> Hit {
        let at: Double? = row["at"]
        let source: String? = row["source"]
        let text: String? = row["text"]
        let sessionId: Int64? = row["sessionId"]
        // Nil for a line stored before scores were kept, and for any caller whose SELECT does not
        // ask for the column. Both mean "unknown", which is what a nil confidence says — the one
        // reading it must never be allowed to decay into "low".
        let confidence: Double? = row["confidence"]
        // Same discipline for attribution, and a sharper edge on it: a locally transcribed line has
        // no diarization and no matched person, so nil is the honest answer and the only safe one.
        // Inventing a label here would turn "we did not identify anyone" into "we identified
        // someone", which is the one error a record of who said what cannot survive.
        let speakerLabel: String? = row["speakerLabel"]
        let personId: String? = row["personId"]
        // `kind` still comes from the capture side, never from the person: which side of the
        // microphone a line arrived on is a fact this app observed itself, and it stays true even
        // when the backend has a better name for the voice.
        let kind = SegmentSource(rawValue: source ?? "") == .mic ? "said" : "heard"
        return Hit(
            kind: kind,
            at: at ?? 0,
            text: text ?? "",
            sessionId: sessionId,
            confidence: confidence,
            speakerLabel: speakerLabel,
            personId: personId)
    }

    private static func frameHit(_ row: Row) -> Hit {
        let at: Double? = row["at"]
        let app: String? = row["appName"]
        let window: String? = row["windowTitle"]
        let ocr: String? = row["ocrText"]
        let ax: String? = row["axText"]
        return Hit(
            kind: "screen",
            at: at ?? 0,
            text: screenText(app: app, window: window, ocr: ocr, ax: ax),
            app: collapsedNonEmpty(app),
            window: collapsedNonEmpty(window)
        )
    }

    private static func speakerLabel(source: String?, speaker: String?) -> String {
        if let source, let parsed = SegmentSource(rawValue: source) { return parsed.speaker }
        return speaker ?? SegmentSource.system.speaker
    }

    /// OCR is raw layout text: newlines and column padding everywhere. Collapse it, then keep only
    /// as much as a reader can actually use.
    ///
    /// The accessibility text wins wherever there is any, because it is the application's own
    /// strings rather than a reading of its pixels: no character-level guessing, no ligature
    /// collapsed into a different word, no `rn` read as `m`. OCR stays the fallback, and for a
    /// window that exposes nothing at all it is the only thing there is.
    private static func screenText(app: String?, window: String?, ocr: String?, ax: String?) -> String {
        if let ax = collapsedNonEmpty(ax) { return truncate(ax, to: screenTextLimit) }
        if let ocr = collapsedNonEmpty(ocr) { return truncate(ocr, to: screenTextLimit) }
        if let window = collapsedNonEmpty(window) { return truncate(window, to: screenTextLimit) }
        return collapsedNonEmpty(app) ?? ""
    }

    // MARK: - Activity blocks

    private struct FrameRow {
        let at: Double
        let app: String
        let window: String?
        let ocr: String?

        init(_ row: Row) {
            let at: Double? = row["capturedAt"]
            let app: String? = row["appName"]
            self.at = at ?? 0
            self.app = app ?? ""
            window = row["windowTitle"]
            ocr = row["ocrText"]
        }
    }

    /// The run-length collapse, folded one frame at a time.
    ///
    /// **Nothing about a stretch needs the frames it was made of once they have been seen**, which is
    /// what lets this hold a fixed amount of state per open run instead of the run itself: the block
    /// wants the first frame's app and time, the last frame's time, the longest window title, and —
    /// only when no frame in the whole stretch had a title — the first legible screen text. Each of
    /// those is a value that can be updated in place as frames arrive.
    ///
    /// That is the difference between this and holding the array: a year of capture is 547,500 rows
    /// carrying ~780 MiB of OCR, and the collapse it produces is a few thousand blocks. `Queries`
    /// used to materialise the former to compute the latter, on a query whose range the caller
    /// chooses and no layer bounds.
    ///
    /// Frames must arrive in ascending time order, which is what the query's `ORDER BY` guarantees.
    private struct BlockAccumulator {
        private var result: [ActivityBlock] = []

        private var app = ""
        private var startedAt: Double = 0
        private var previousAt: Double = 0
        /// The longest collapsed title seen in the open run. Ties keep the earliest, matching what
        /// `max(by:)` over the run's titles returned.
        private var title: String?
        /// The first legible screen text of the open run, already truncated — the sample is cut to
        /// `activitySampleLimit` whatever else happens, so nothing longer is worth carrying.
        private var firstText: String?
        private var isOpen = false

        mutating func append(_ frame: FrameRow) {
            if isOpen, app != frame.app || frame.at - previousAt > activityGapSeconds {
                close()
            }
            if !isOpen {
                app = frame.app
                startedAt = frame.at
                isOpen = true
            }
            previousAt = frame.at

            // Collapsing a title allocates a new string, and a title no longer than the one already
            // held can never beat it — collapsing only ever shortens. So the raw length is a sound
            // filter, and it is a *skip* for almost every frame of a real stretch, where a window
            // keeps one title for as long as it is open. Worth 1.4 s of a 8.5 s year even on a
            // synthetic corpus that changes the title on every single frame.
            if let raw = frame.window, raw.count > (title?.count ?? 0),
                let candidate = collapsedNonEmpty(raw), candidate.count > (title?.count ?? 0)
            {
                title = candidate
            }
            if firstText == nil, let text = collapsedNonEmpty(frame.ocr) {
                firstText = truncate(text, to: activitySampleLimit)
            }
        }

        mutating func finish() -> [ActivityBlock] {
            close()
            return result
        }

        private mutating func close() {
            defer {
                title = nil
                firstText = nil
                isOpen = false
            }
            guard isOpen, previousAt - startedAt >= activityMinimumSeconds else { return }

            // The longest title is the most descriptive one the app showed during the stretch, and
            // the screen text is only ever the fallback for a stretch that showed no title at all.
            let sample = title.map { truncate($0, to: activitySampleLimit) } ?? firstText
            result.append(
                ActivityBlock(
                    app: app,
                    window: title,
                    startedAt: startedAt,
                    endedAt: previousAt,
                    sampleText: sample
                )
            )
        }
    }

    // MARK: - Totals

    private struct Totals {
        var segments = 0
        var frames = 0
        var sessions = 0
        var oldest: Double?
        var newest: Double?

        init(_ row: Row?) {
            guard let row else { return }
            let segmentCount: Int? = row["segmentCount"]
            let frameCount: Int? = row["frameCount"]
            let sessionCount: Int? = row["sessionCount"]
            segments = segmentCount ?? 0
            frames = frameCount ?? 0
            sessions = sessionCount ?? 0
            let oldestSegment: Double? = row["oldestSegment"]
            let newestSegment: Double? = row["newestSegment"]
            let oldestFrame: Double? = row["oldestFrame"]
            let newestFrame: Double? = row["newestFrame"]
            oldest = [oldestSegment, oldestFrame].compactMap { $0 }.min()
            newest = [newestSegment, newestFrame].compactMap { $0 }.max()
        }
    }

    // MARK: - Shaping

    private static func newestFirst(_ hits: [Hit]) -> [Hit] {
        hits.sorted { lhs, rhs in
            if lhs.at != rhs.at { return lhs.at > rhs.at }
            // Deterministic ties, and speech reads better before the screen it was said in front of.
            return kindRank(lhs.kind) < kindRank(rhs.kind)
        }
    }

    private static func kindRank(_ kind: String) -> Int { kind == "screen" ? 1 : 0 }

    private static func cap(_ hits: [Hit], to limit: Int) -> [Hit] {
        hits.count <= limit ? hits : Array(hits.prefix(limit))
    }

    private static func collapsed(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    private static func collapsedNonEmpty(_ text: String?) -> String? {
        guard let text else { return nil }
        let value = collapsed(text)
        return value.isEmpty ? nil : value
    }

    /// Word-boundary truncation. The result, ellipsis included, is never longer than `limit`.
    private static func truncate(_ text: String, to limit: Int) -> String {
        guard limit > 1, text.count > limit else { return text }
        let head = text.prefix(limit - 1)
        var cut = String(head)
        if let space = cut.lastIndex(of: " ") {
            let word = cut[cut.startIndex..<space]
            // Only honour the word boundary when it does not throw away most of the snippet.
            if word.count >= (limit - 1) / 2 { cut = String(word) }
        }
        return cut.trimmingCharacters(in: .whitespaces) + "…"
    }
}
