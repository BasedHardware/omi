import Foundation
import GRDB

/// Every read the app and the MCP server perform. Nothing in here writes, so it is safe against a
/// read-only WAL connection opened while the app is still capturing.
public enum Queries {

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
    //     coverage  = distinct query terms present in the document / distinct query terms   (0, 1]
    //     lexical   = max(0, -bm25) / best max(0, -bm25) in the *same* FTS table            [0, 1]
    //     relevance = 0.6 * coverage + 0.4 * lexical                                        [0, 1]
    //     recency   = exp(-(newestCandidateAt - at) / 3 days)                               (0, 1]
    //     score     = relevance * (0.75 + 0.25 * recency)                                   [0, 1]
    //
    // Coverage carries the larger weight because it is the only term that means the same thing in
    // both tables: bm25 magnitudes depend on each table's row count, average document length, and
    // term distribution, so a raw score is comparable only against other scores from the same table.
    // Normalising within a table and then blending on coverage is what makes a merged ranking honest
    // rather than a coin toss between two different scales.
    //
    // Recency is a multiplier capped at `recencyPull`, not an additive term, so it is bounded by
    // construction: an infinitely old hit still keeps 75% of its relevance. A newer hit can therefore
    // only overturn a relevance gap smaller than 25% — the bookmark-bar captures were fresher than
    // the real match and must never win on that alone.
    private static let coverageWeight = 0.6
    private static let lexicalWeight = 0.4
    /// The most of a hit's relevance that age is allowed to take away.
    private static let recencyPull = 0.25
    /// e-folding time. Three days is roughly the horizon over which "I was just looking at this"
    /// stops being a reason to prefer one match over a better one.
    private static let recencyDecaySeconds: Double = 3 * 24 * 60 * 60

    /// Hits scoring below this fraction of the best hit are dropped instead of padding the result to
    /// `limit`. Relative rather than absolute because scores are only meaningful within one query:
    /// there is no absolute number that separates "relevant" from "noise" across every corpus.
    ///
    /// 0.40 is chosen against the floor of a full-coverage hit. A document containing *every*
    /// distinct query term scores at least `0.6 * 1.0 * 0.75 = 0.45`, and no score can exceed 1.0, so
    /// the floor can never remove a hit that matched the whole query however old it is. It only ever
    /// trims partial-coverage hits — which is exactly the bookmark bar, and exactly the case where
    /// padding to `limit` misleads a reader into thinking the database is full of matches.
    private static let relevanceFloorFraction = 0.4

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
    // **Grouping.** Frames are keyed on `(app, window title reduced to its words)` and grouped in
    // time order. Reducing the title to words is not cosmetic: Warp's Claude Code spinner cycles
    // ✳/⠂/⠐ *inside the title* between consecutive frames, so exact title matching shatters one
    // 2.8-hour terminal session into ~150 one-frame "moments". The same normalisation absorbs
    // unsaved-changes dots and unread badges.
    //
    // Grouping is per key rather than strictly adjacent, because a person alternates between two
    // windows every few frames; adjacency would restart both moments on every switch and dedupe
    // almost nothing (measured: 2× versus 5× on this machine's corpus).
    //
    // **Materiality.** A moment ends when the next frame of that window arrives `momentGapSeconds`
    // or more later, or when it shows materially new text. "Materially" cannot be a fixed similarity
    // threshold, because the two cases that must come out differently look the same to one: a static
    // page re-OCR'd and a chat window that gained a message both overlap their predecessor by ~95%.
    // What separates them is *novelty* — words the moment has never contained — and how much novelty
    // is normal **for that window**. A terminal that rewrites a third of itself every three seconds
    // is not starting a new moment every three seconds; a page that has been still and suddenly
    // gains a paragraph is.
    //
    // So the bar is `max(momentNoveltyFloor, momentChurnMultiple × the window's own recent churn)`,
    // cleared in both fraction and absolute words, plus one escape hatch
    // (`momentNoveltyDominantFraction`) for a frame too short to ever reach the word minimum.
    // Calibrated against four labelled runs from this machine's real capture, all of which the
    // constants below satisfy:
    //
    //   still marketing page, Arc, 7 frames   0–2 novel words per frame          → 1 moment
    //   still article, Arc, 8 frames          0–1 novel words per frame          → 1 moment
    //   iMessage thread, 9 frames             19 novel at 15% vs a 12.5% bar     → 2 moments
    //   editor, file switched, 32 frames      254 novel at 54% vs a 27% bar      → 3 moments
    //
    // The third row is the one that decides the design: 15% overlap-loss is indistinguishable from a
    // re-OCR by any fixed threshold, and only reads as material because that chat had been sitting
    // at 4% churn.
    //
    // Cost is one pass: a hashed word set per frame, one subtraction against the moment's running
    // set. 1,128 frames — this machine's entire history — group in well under a tenth of a second.

    /// Ten minutes. Deliberately generous: the frames being grouped are already filtered (by a
    /// search term, or by `app`), so "the next matching frame" is not "the next frame" — a person
    /// can sit in one window for minutes between two frames that mention the thing being searched
    /// for. Longer than this and they went and did something else.
    private static let momentGapSeconds: Double = 600
    /// The novelty bar for a window with no established churn, and the floor under every bar. Below
    /// this is OCR wobble: the same page read twice never agrees to the word.
    private static let momentNoveltyFloor = 0.10
    /// A fraction alone would let one new word split a nine-word window. This is roughly a sentence:
    /// the least new text a reader would call a different thing.
    private static let momentNoveltyMinimumWords = 12
    /// A frame this fraction new is a new moment however few words it has — the escape hatch for a
    /// window too short to ever clear `momentNoveltyMinimumWords`.
    ///
    /// Deliberately near the top of the range: it is meant to fire only for "almost nothing here was
    /// here before", leaving every ordinary content change to the churn-relative bar. Measured, 0.6
    /// costs a fifth of the collapse (1128 frames → 267 moments rather than 214) for cases that bar
    /// already catches; 0.8 costs 3 moments in 1128.
    private static let momentNoveltyDominantFraction = 0.8
    /// How far above a window's own churn a frame must land to count as a new moment. Calibrated
    /// against the four labelled cases in the notes above; at 4.0 the new-message case stops firing
    /// and at 2.5 the collapse gets measurably worse for nothing.
    private static let momentChurnMultiple = 3.0
    /// EWMA weight on the newest observation. High enough to follow a window that changes character,
    /// low enough that one garbled OCR pass does not move the bar.
    private static let momentChurnSmoothing = 0.3
    /// Distinct words compared per frame. Bounds the pass over a pathological page; real captures on
    /// this machine peak around 500.
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
        guard limit > 0, let match = ftsExpression(for: query) else { return [] }
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
                    preview: try preview(db, sessionId: id)
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
                    SELECT startedAt AS at, source, text, sessionId
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
    public static func activity(_ store: ContextStore, since: Double, until: Double) throws -> [ActivityBlock] {
        let frames: [FrameRow] = try store.read { db in
            try Row.fetchAll(
                db,
                sql: """
                    SELECT capturedAt, appName, windowTitle, ocrText
                    FROM frames
                    WHERE capturedAt >= ? AND capturedAt <= ?
                      AND appName IS NOT NULL AND TRIM(appName) <> ''
                    ORDER BY capturedAt ASC, id ASC
                    """,
                arguments: [since, until]
            ).map(FrameRow.init)
        }
        return blocks(from: frames)
    }

    // MARK: - Status

    /// Capture health plus coverage, so a reader can tell "never happened" from "not captured".
    public static func status(_ store: ContextStore) throws -> StatusInfo {
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
        let state = CaptureState.read()
        let live = state.map { !$0.isStale } ?? false
        let capturing = live && (state?.capturing ?? false)
        let pausedReason: String?
        if capturing {
            pausedReason = nil
        } else if live {
            pausedReason = state?.pausedReason ?? "Capture is paused"
        } else {
            pausedReason = "Context for Claude is not running"
        }

        return StatusInfo(
            capturing: capturing,
            pausedReason: pausedReason,
            // Permission grants outlive the process, so last-known capabilities beat none at all.
            capabilities: state?.capabilities ?? [],
            segmentCount: totals.segments,
            frameCount: totals.frames,
            sessionCount: totals.sessions,
            oldestAt: totals.oldest,
            newestAt: totals.newest,
            databasePath: ContextPaths.databaseURL.path
        )
    }

    // MARK: - FTS sanitization

    /// Characters that make FTS5 read a human phrase as syntax.
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

    /// The terms behind `ftsExpression`, in query order and with duplicates left intact so the
    /// expression it builds is byte-for-byte what it always was.
    ///
    /// Extracted rather than duplicated: the coverage boost has to score the exact set of terms the
    /// MATCH searched for, or a document could be credited for a term the index never looked at.
    private static func sanitizedTerms(in query: String) -> [String] {
        query
            .split(whereSeparator: { $0.isWhitespace })
            .map { token -> String in
                let kept = token.unicodeScalars.filter { !ftsOperatorCharacters.contains($0) }
                return String(kept.map { Character($0) })
            }
            .filter { term in
                // A term with no letter or digit tokenizes to nothing, and an empty FTS5 phrase is
                // itself a syntax error.
                guard term.rangeOfCharacter(from: .alphanumerics) != nil else { return false }
                return !ftsOperatorWords.contains(term.uppercased())
            }
    }

    /// Case-folded distinct terms: the denominator of the coverage boost. Typing a word twice must
    /// not make a document that contains it look twice as relevant.
    private static func distinctTerms(in query: String) -> [String] {
        var seen: Set<String> = []
        return sanitizedTerms(in: query).compactMap { term in
            let folded = term.lowercased()
            return seen.insert(folded).inserted ? folded : nil
        }
    }

    // MARK: - Row fetching

    private static func matchedSegments(
        _ db: Database,
        match: String,
        terms: [String],
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Candidate] {
        var sql = """
            SELECT s.startedAt AS at, s.source AS source, s.text AS text, s.sessionId AS sessionId,
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

    private static func matchedFrames(
        _ db: Database,
        match: String,
        terms: [String],
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Candidate] {
        var sql = """
            SELECT f.capturedAt AS at, f.appName AS appName, f.windowTitle AS windowTitle, f.ocrText AS ocrText,
                   bm25(frames_fts, \(frameOCRWeight), \(frameTitleWeight), \(frameAppWeight)) AS bm25Score
            FROM frames_fts
            JOIN frames f ON f.rowid = frames_fts.rowid
            WHERE frames_fts MATCH ?
            """
        var args: [(any DatabaseValueConvertible)?] = [match]
        if let since {
            sql += "\n  AND f.capturedAt >= ?"
            args.append(since)
        }
        if let until {
            sql += "\n  AND f.capturedAt <= ?"
            args.append(until)
        }
        sql += "\nORDER BY bm25Score ASC, f.capturedAt DESC\nLIMIT ?"
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
                // Coverage reads the untruncated row: `frameHit` clips OCR for the reader, and a
                // term that fell off the end of the snippet is still a term the frame contained.
                return [window, app, ocr].compactMap { $0 }.joined(separator: " ")
            },
            signature: { frameSignature($0) })
    }

    private static func segmentRows(_ db: Database, since: Double?, until: Double?, limit: Int) throws -> [Row] {
        var sql = """
            SELECT startedAt AS at, source, text, sessionId
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
            conditions.append("appName LIKE ?")
            args.append("%\(app)%")
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
        terms: [String],
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
        let scored = pool.map { candidate -> Scored in
            let relevance = coverageWeight * candidate.coverage + lexicalWeight * candidate.lexical
            let age = max(0, newest - candidate.hit.at)
            let recency = exp(-age / recencyDecaySeconds)
            return Scored(
                hit: candidate.hit,
                score: relevance * (1 - recencyPull + recencyPull * recency),
                frame: candidate.frame)
        }

        // Moments are formed on the *scored* candidate set, before the floor and the cap. Collapsing
        // afterwards would be pointless — `limit` would already have been spent on near-duplicates —
        // and collapsing before scoring would leave the grouper picking a representative blind.
        let moments = collapsedMoments(scored)

        guard let best = moments.map(\.score).max() else { return [] }
        let floor = relevanceFloorFraction * best

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

    /// Fraction of the distinct query terms this document actually contains.
    ///
    /// The point of the OR expression is that nothing is lost; the point of this number is that a
    /// document matching three of four terms outranks one matching a single incidental word. Never
    /// returns zero: the row is in the result set because FTS matched *something*, so a zero here
    /// would only ever mean our tokenizer and the porter-stemmed index disagreed.
    private static func coverage(of document: String, terms: [String]) -> Double {
        guard !terms.isEmpty else { return 1 }
        let tokens = documentTokens(document)
        let matched = terms.reduce(into: 0) { total, term in
            if tokens.contains(term) || tokens.contains(where: { inflected($0, matches: term) }) {
                total += 1
            }
        }
        return Double(max(1, matched)) / Double(terms.count)
    }

    /// Lowercased word tokens of a document, indexed under *both* readings of a punctuated
    /// identifier.
    ///
    /// The query side strips FTS operator characters, so `SCA-219` arrives as the term `sca219`; the
    /// unicode61 tokenizer splits on them, so the index holds `sca` and `219`. Emitting only one
    /// reading loses coverage credit for a document the index genuinely matched — `SCA-219` under
    /// the split reading, `omi-eng` under the joined one — and under-credited coverage is the
    /// direction that costs a true match its place, which is the whole bug. Emitting both can only
    /// credit terms that FTS itself matched.
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

    /// A window with a moment currently open. `churn` outlives the moment on purpose: how much a
    /// window normally changes is a property of the window, not of the stretch being grouped, and
    /// resetting it on every break makes the bar collapse to `momentNoveltyFloor` and shatter the
    /// next moment in the same way.
    private struct OpenMoment {
        var group: Int
        var lastAt: Double
        var words: Set<Int>
        var churn: Double?
    }

    /// Groups frames into moments, returning the indices belonging to each.
    ///
    /// `frames` must be in ascending time order. Groups come back in the order they opened, and
    /// every index appears in exactly one — nothing is dropped here, only gathered.
    private static func momentGroups(_ frames: [MomentInput]) -> [[Int]] {
        var groups: [[Int]] = []
        // Parallel arrays keyed by window: mutating `open[slot].words` in place is what keeps the
        // running set from being copied on every frame.
        var open: [OpenMoment] = []
        var slots: [String: Int] = [:]

        for (index, frame) in frames.enumerated() {
            let key = frame.signature.key
            guard let slot = slots[key] else {
                groups.append([index])
                open.append(
                    OpenMoment(
                        group: groups.count - 1,
                        lastAt: frame.at,
                        words: frame.signature.words,
                        churn: nil))
                slots[key] = open.count - 1
                continue
            }

            var startsMoment = frame.at - open[slot].lastAt >= momentGapSeconds
            if !startsMoment, !frame.signature.words.isEmpty {
                var novel = 0
                for word in frame.signature.words where !open[slot].words.contains(word) {
                    novel += 1
                }
                let fraction = Double(novel) / Double(frame.signature.words.count)
                // The first comparison a window ever gets cannot end a moment: there is no churn to
                // judge it against, and it is exactly the frame most likely to be a half-rendered
                // page. Measured, this alone is the difference between the still Periphery site
                // reading as one moment and reading as two.
                if let churn = open[slot].churn {
                    // Two ways to be new, because the word minimum alone has a hole. Requiring 12
                    // novel words stops a re-OCR of a long page from breaking on jitter — but it
                    // also means a *short* frame can never break at all, however different it is. A
                    // chat window whose whole content is "ok sounds good" is three words: entirely
                    // new, and silently swallowed into the previous moment. So a frame that is
                    // overwhelmingly novel counts regardless of how few words it has.
                    let bar = max(momentNoveltyFloor, momentChurnMultiple * churn)
                    if fraction >= momentNoveltyDominantFraction
                        || (novel >= momentNoveltyMinimumWords && fraction > bar) {
                        startsMoment = true
                    }
                }
                // The bar learns from every frame, including the one that just broke the moment:
                // that frame is evidence about the window too.
                open[slot].churn = open[slot].churn
                    .map { (1 - momentChurnSmoothing) * $0 + momentChurnSmoothing * fraction }
                    ?? fraction
            }

            if startsMoment {
                groups.append([index])
                open[slot].group = groups.count - 1
                open[slot].lastAt = frame.at
                open[slot].words = frame.signature.words
            } else {
                groups[open[slot].group].append(index)
                open[slot].lastAt = frame.at
                open[slot].words.formUnion(frame.signature.words)
            }
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
            sessionId: representative.sessionId
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
        let kind = SegmentSource(rawValue: source ?? "") == .mic ? "said" : "heard"
        return Hit(kind: kind, at: at ?? 0, text: text ?? "", sessionId: sessionId)
    }

    private static func frameHit(_ row: Row) -> Hit {
        let at: Double? = row["at"]
        let app: String? = row["appName"]
        let window: String? = row["windowTitle"]
        let ocr: String? = row["ocrText"]
        return Hit(
            kind: "screen",
            at: at ?? 0,
            text: screenText(app: app, window: window, ocr: ocr),
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
    private static func screenText(app: String?, window: String?, ocr: String?) -> String {
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

    private static func blocks(from frames: [FrameRow]) -> [ActivityBlock] {
        var result: [ActivityBlock] = []
        var run: [FrameRow] = []

        func close() {
            defer { run = [] }
            guard let first = run.first, let last = run.last else { return }
            guard last.at - first.at >= activityMinimumSeconds else { return }

            // The longest title is the most descriptive one the app showed during the stretch.
            let title = run
                .compactMap { collapsedNonEmpty($0.window) }
                .max(by: { $0.count < $1.count })
            let sample = title.map { truncate($0, to: activitySampleLimit) }
                ?? run.compactMap { collapsedNonEmpty($0.ocr) }.first.map { truncate($0, to: activitySampleLimit) }

            result.append(
                ActivityBlock(
                    app: first.app,
                    window: title,
                    startedAt: first.at,
                    endedAt: last.at,
                    sampleText: sample
                )
            )
        }

        for frame in frames {
            if let previous = run.last, previous.app != frame.app || frame.at - previous.at > activityGapSeconds {
                close()
            }
            run.append(frame)
        }
        close()
        return result
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
