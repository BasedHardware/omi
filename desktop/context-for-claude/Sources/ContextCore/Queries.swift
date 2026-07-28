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

    // MARK: - Search

    /// Full-text search across speech and screen text, newest first.
    ///
    /// Rank is deliberately *not* blended across the two FTS tables: their scores are not
    /// comparable, and for ambient context recency is the better default anyway.
    public static func recall(
        _ store: ContextStore,
        query: String,
        since: Double? = nil,
        until: Double? = nil,
        limit: Int = 40
    ) throws -> [Hit] {
        guard limit > 0, let match = ftsExpression(for: query) else { return [] }

        let hits: [Hit] = try store.read { db in
            let spoken = try matchedSegments(db, match: match, since: since, until: until, limit: limit)
            let seen = try matchedFrames(db, match: match, since: since, until: until, limit: limit)
            return spoken + seen
        }
        return cap(newestFirst(hits), to: limit)
    }

    /// Everything captured in the last `minutes`, speech and screen merged.
    public static func recent(_ store: ContextStore, minutes: Int = 30, limit: Int = 120) throws -> [Hit] {
        guard limit > 0 else { return [] }
        let since = ContextTime.now - Double(max(0, minutes)) * 60

        let hits: [Hit] = try store.read { db in
            let spoken = try segmentRows(db, since: since, until: nil, limit: limit).map(segmentHit)
            let seen = try frameRows(db, since: since, until: nil, app: nil, limit: limit).map(frameHit)
            return spoken + seen
        }
        return cap(newestFirst(hits), to: limit)
    }

    /// Screen observations, newest first, optionally narrowed to one app.
    public static func screen(
        _ store: ContextStore,
        since: Double? = nil,
        until: Double? = nil,
        app: String? = nil,
        limit: Int = 60
    ) throws -> [Hit] {
        guard limit > 0 else { return [] }
        return try store.read { db in
            try frameRows(db, since: since, until: until, app: app, limit: limit).map(frameHit)
        }
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
        let terms = query
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
            .map { "\"\($0)\"" }

        guard !terms.isEmpty else { return nil }
        return terms.joined(separator: " OR ")
    }

    // MARK: - Row fetching

    private static func matchedSegments(
        _ db: Database,
        match: String,
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Hit] {
        var sql = """
            SELECT s.startedAt AS at, s.source AS source, s.text AS text, s.sessionId AS sessionId
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
        sql += "\nORDER BY s.startedAt DESC\nLIMIT ?"
        args.append(limit)

        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map(segmentHit)
    }

    private static func matchedFrames(
        _ db: Database,
        match: String,
        since: Double?,
        until: Double?,
        limit: Int
    ) throws -> [Hit] {
        var sql = """
            SELECT f.capturedAt AS at, f.appName AS appName, f.windowTitle AS windowTitle, f.ocrText AS ocrText
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
        sql += "\nORDER BY f.capturedAt DESC\nLIMIT ?"
        args.append(limit)

        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map(frameHit)
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
