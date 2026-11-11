import Foundation
import GRDB

/// The reads the app's **search surface** needs and no other layer does.
///
/// Named for the work that created it — making the search bar answer over screens as well as
/// conversations — and it is the search panel's own query layer rather than a second screen search.
/// That distinction is the whole point of the file:
///
/// - `Queries` answers *Claude*, over MCP. Its results are prose for a model: moment-collapsed,
///   relevance-floored, and stripped of every filesystem path on purpose. A grid of scrollable cards
///   cannot be built out of them, and building one would mean re-deriving the frame identity and the
///   image path the layer deliberately dropped.
/// - `RewindQueries` answers the *timeline*, and its `search` already matches frames against the
///   same two FTS indexes and already returns `imagePath`. **The surface still calls it.** Nothing
///   here re-implements it — a second imagePath-selecting screen search is precisely the duplication
///   `RewindQueries`' own header warns about.
///
/// What was missing was the other half of the question the user actually asks. The panel searched
/// screens and nothing else, so "what did we decide about pricing" found the window somebody had the
/// spreadsheet open in and never the sentence in which it was decided. `conversations` is that half.
/// `frameText` is the smaller gap beside it: a screen card that matched deep inside a page of OCR had
/// no way to say *why* it matched, and a card whose picture retention already unlinked had nothing to
/// show at all.
///
/// Everything here is read-only and safe against the read-only WAL connection, exactly like the two
/// query enums beside it.
public enum ScreenSearchQueries {

    // MARK: - Tuning

    /// How much of a frame's text a card may carry.
    ///
    /// A snippet, not a transcript of the screen: it is evidence that this frame answered the query
    /// and a legible stand-in when the picture is gone, and past a couple of hundred characters it is
    /// neither — the card truncates it anyway, and the extra bytes are paid on every row of the page.
    /// The same order of magnitude as `Queries`' own screen-text budget, for the same reason.
    public static let snippetLimit = 240

    /// How many frame ids one `IN (…)` may carry.
    ///
    /// SQLite caps the number of bound parameters in a statement (999 by default), and while the
    /// search page is far smaller than that today, a caller is free to hand over whatever it read.
    /// Truncating is the safe failure: the extra cards lose their snippet, which is a missing
    /// tooltip, where an over-long statement is an error in the middle of a search.
    public static let maximumIdBatch = 500

    // MARK: - Spoken lines

    /// One transcript line, in the shape a result card draws.
    ///
    /// Distinct from `Hit` (the MCP wire shape) because a card needs the row's **identity** — a card
    /// list has to be diffable, and the session id is what a future "open this conversation" has to
    /// travel by — and distinct from `Segment` (the write shape) because it carries the session's
    /// `appHint`, which lives in another table and is the only thing that says *where* a line was
    /// spoken.
    ///
    /// It carries no speaker *name* and never will: `Queries`' attribution note is the contract for
    /// this whole package — a name is a current property of the user's Omi account, and one copied
    /// into a local row decays with nothing to correct it. `source` says which side of the microphone
    /// the words arrived on, which is a fact this app observed itself and stays true forever.
    public struct SpokenLine: Sendable, Equatable, Identifiable {
        /// `segments.id`.
        public let id: Int64
        public let sessionId: Int64
        /// Unix epoch seconds.
        public let startedAt: Double
        /// Mic is the user; the system tap is everyone else.
        public let source: SegmentSource
        /// The words. Never empty — a blank line is not a result, so it is not one of these.
        public let text: String
        /// The frontmost app when the *session* opened, or nil. A hint about the conversation, never
        /// a claim about where this particular line was said.
        public let appHint: String?
        /// The transcriber's own score, or nil for a line stored before scores were kept. Nil means
        /// "nobody asked the model" and must never decay into "low".
        public let confidence: Double?

        public init(
            id: Int64,
            sessionId: Int64,
            startedAt: Double,
            source: SegmentSource,
            text: String,
            appHint: String? = nil,
            confidence: Double? = nil
        ) {
            self.id = id
            self.sessionId = sessionId
            self.startedAt = startedAt
            self.source = source
            self.text = text
            self.appHint = appHint
            self.confidence = confidence
        }

        /// Nil for a row this shape cannot honour: no id, or nothing legible in `text`.
        ///
        /// Dropping the blank rows here rather than in the view is what keeps "a result is something
        /// you can read" true for every consumer, including the count the panel says out loud.
        init?(_ row: Row) {
            let rawId: Int64? = row["id"]
            let rawText: String? = row["text"]
            guard let id = rawId, let text = ScreenSearchQueries.collapsedNonEmpty(rawText) else {
                return nil
            }
            let sessionId: Int64? = row["sessionId"]
            let startedAt: Double? = row["startedAt"]
            let rawSource: String? = row["source"]
            let appHint: String? = row["appHint"]
            let confidence: Double? = row["confidence"]
            self.init(
                id: id,
                sessionId: sessionId ?? 0,
                startedAt: startedAt ?? 0,
                // An unrecognised value means the row was written by something newer than this
                // binary. `.system` is the safe reading: claiming a line was the *user's* own speech
                // when we do not know is the one attribution error a record of who said what cannot
                // survive.
                source: SegmentSource(rawValue: rawSource ?? "") ?? .system,
                text: text,
                appHint: ScreenSearchQueries.collapsedNonEmpty(appHint),
                confidence: confidence)
        }
    }

    /// Transcript lines matching `query`, newest first, with how many there were in total.
    ///
    /// Deliberately shaped like `RewindQueries.search` — same argument order, same optional bounds,
    /// same `(page, total)` return — because the search panel reads the two together and merges them.
    /// Two halves of one answer that disagreed about what an empty query means, or about whether
    /// `total` counts the page or the corpus, would produce a page the surface could not describe.
    ///
    /// So, matching that contract exactly:
    ///
    /// - **An empty or unindexable query is not an error and does not return nothing.** It returns
    ///   the newest lines, which is what a search surface with nothing typed into it should show.
    /// - **`total` is counted in SQL**, not taken as `lines.count`. The array is the page the panel
    ///   can draw; the count is what it says out loud, and a surface that reports its page size as
    ///   the total tells the user there were 60 results when there were 600.
    ///
    /// Only `segments_fts` is consulted, which indexes `text` alone — there is no second index over
    /// speech the way `frames_ax_fts` sits beside `frames_fts`, because a transcript line has exactly
    /// one reading of itself.
    ///
    /// Blank lines are excluded in SQL rather than filtered afterwards, so the count and the page
    /// agree: a line with nothing in it is not something a person can be shown.
    public static func conversations(
        _ store: ContextStore,
        matching query: String,
        since: Double? = nil,
        until: Double? = nil,
        limit: Int = 60
    ) throws -> (lines: [SpokenLine], total: Int) {
        guard limit > 0 else { return ([], 0) }

        var conditions = ["TRIM(g.text) <> ''"]
        var scope: [(any DatabaseValueConvertible)?] = []
        var source = "segments g"

        // The sanitizer is `Queries`', not a second one: an expression built differently here would
        // search for different terms than the screen half of the same page, and the two would be
        // answering two questions under one query chip.
        if let match = Queries.ftsExpression(for: query) {
            source = """
                (SELECT rowid AS rid FROM segments_fts WHERE segments_fts MATCH ?) m
                JOIN segments g ON g.rowid = m.rid
                """
            scope.append(match)
        }
        if let since {
            conditions.append("g.startedAt >= ?")
            scope.append(since)
        }
        if let until {
            conditions.append("g.startedAt <= ?")
            scope.append(until)
        }
        let predicate = conditions.joined(separator: " AND ")

        return try store.read { db in
            let total = try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM \(source) WHERE \(predicate)",
                arguments: StatementArguments(scope)) ?? 0
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT g.id AS id, g.sessionId AS sessionId, g.startedAt AS startedAt,
                           g.source AS source, g.text AS text, g.confidence AS confidence,
                           s.appHint AS appHint
                    FROM \(source)
                    LEFT JOIN sessions s ON s.id = g.sessionId
                    WHERE \(predicate)
                    ORDER BY g.startedAt DESC, g.id DESC
                    LIMIT ?
                    """,
                arguments: StatementArguments(scope + [limit]))
            return (rows.compactMap(SpokenLine.init), total)
        }
    }

    // MARK: - What a frame said

    /// The text behind each of `ids`, collapsed and cut to `snippetLimit`. Ids with nothing legible
    /// are simply absent from the result.
    ///
    /// A second, tiny read rather than more columns on the search itself, and that is the point:
    /// `RewindQueries.search` stays the one screen search, and this asks a bounded follow-up question
    /// about the page it already returned. Selecting by primary key, so it costs one index seek per
    /// card rather than a scan.
    ///
    /// **The accessibility tree wins over OCR wherever there is any**, exactly as `Queries.screenText`
    /// decides it: the tree is the application's own strings, where OCR is a reading of pixels that
    /// guesses at characters. A snippet is shown to a person as evidence that this frame matched, so
    /// the reading with no character-level guessing in it is the one to show.
    public static func frameText(_ store: ContextStore, ids: [Int64]) throws -> [Int64: String] {
        let bounded = Array(ids.prefix(maximumIdBatch))
        guard !bounded.isEmpty else { return [:] }

        let placeholders = Array(repeating: "?", count: bounded.count).joined(separator: ", ")

        return try store.read { db in
            let rows = try Row.fetchAll(
                db,
                sql: "SELECT id, ocrText, axText FROM frames WHERE id IN (\(placeholders))",
                arguments: StatementArguments(bounded))
            var text: [Int64: String] = [:]
            for row in rows {
                let id: Int64? = row["id"]
                let ax: String? = row["axText"]
                let ocr: String? = row["ocrText"]
                guard let id else { continue }
                guard let readable = collapsedNonEmpty(ax) ?? collapsedNonEmpty(ocr) else { continue }
                text[id] = truncate(readable, to: snippetLimit)
            }
            return text
        }
    }

    // MARK: - Shaping

    // Small local copies of two helpers `Queries` keeps private. Reaching into that file to share
    // them would widen its surface for the sake of eight lines; the alternative — a card that shows
    // raw OCR layout, newlines and column padding included — is what these prevent.

    /// Whitespace collapsed to single spaces, or nil when nothing is left.
    static func collapsedNonEmpty(_ text: String?) -> String? {
        guard let text else { return nil }
        let value = text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return value.isEmpty ? nil : value
    }

    /// Word-boundary truncation. The result, ellipsis included, is never longer than `limit`.
    static func truncate(_ text: String, to limit: Int) -> String {
        guard limit > 1, text.count > limit else { return text }
        var cut = String(text.prefix(limit - 1))
        if let space = cut.lastIndex(of: " ") {
            let word = cut[cut.startIndex..<space]
            // Only honour the word boundary when it does not throw away most of the snippet.
            if word.count >= (limit - 1) / 2 { cut = String(word) }
        }
        return cut.trimmingCharacters(in: .whitespaces) + "…"
    }
}
