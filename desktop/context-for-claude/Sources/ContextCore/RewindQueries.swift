import Foundation
import GRDB

/// The reads that need the picture, and the only place `frames.imagePath` is selected.
///
/// `Queries` deliberately never returns an image path: every one of its results is destined for a
/// language model over MCP, and a filesystem path is neither answerable nor safe to hand over. The
/// consumers that need the pixels get their own entry points here rather than a flag threaded
/// through the MCP shapes.
///
/// There are two of them, and the distinction the rule turns on is *path versus pixels*, not
/// *local versus model*. The Rewind timeline draws the file directly. The `look` tool decodes it
/// and sends the image itself, which is why it may read from here — what it must never do, and
/// what a path on a `Hit` would let it do by accident, is hand Claude a string only this Mac can
/// resolve.
///
/// **Whole days are read at once, and nothing is sampled.** A day of capture is ~1,500 rows and a
/// `RewindFrame` is a handful of pointers, so the entire day fits in memory with room to spare; the
/// window then owns a complete, sorted array it can binary-search by timestamp. The alternative —
/// selecting every Nth row to bound the count — is what makes a timeline time-blind: it hands the
/// UI an array whose index is the only thing it can map a pixel to, so a three-hour gap and a
/// three-second one occupy the same width and "scroll left to go back in time" stops being true.
/// The sort order here (`capturedAt ASC`) is what a time-linear track needs, and
/// `idx_frames_capturedAt` already serves it as an ordered index scan rather than a sort.
public enum RewindQueries {

    /// What an unnamed app is called on the timeline.
    ///
    /// `frames.appName` is nullable in the schema even though capture has always populated it
    /// (`ScreenWatcher` falls back to the bundle id and then to a literal). A timeline that
    /// force-unwrapped it would be one schema-legal row away from taking the window down, and a
    /// timeline that dropped those rows would silently lose time from the day — so they are named
    /// and kept.
    public static let unknownApp = "Unknown"

    /// Every frame in `[since, until]` that has an image on disk, oldest first.
    ///
    /// `imagePath IS NOT NULL` is a `WHERE` clause rather than a filter applied afterwards because
    /// a frame with no image cannot be shown: 8.7% of the rows on this machine (275 of 3,149) are
    /// image-less — the dedupe gate stored the app/title transition without paying for a picture, or
    /// the encode failed. Those rows are real history and `Queries.activity` still counts them
    /// towards the day's shape; they simply are not scrubbable, so the frame array excludes them
    /// while the segment track does not. That asymmetry is deliberate and is why the two are
    /// computed separately.
    public static func frames(_ store: ContextStore, since: Double, until: Double) throws -> [RewindFrame] {
        try store.read { db in
            try Row.fetchAll(
                db,
                sql: """
                    SELECT id, capturedAt, appName, bundleId, windowTitle, ocrText, imagePath
                    FROM frames
                    WHERE capturedAt >= ? AND capturedAt <= ? AND imagePath IS NOT NULL
                    ORDER BY capturedAt ASC, id ASC
                    """,
                arguments: [since, until]
            ).compactMap(RewindFrame.init)
        }
    }

    /// How many showable frames sit in `[since, until]`.
    ///
    /// Counted in SQL rather than as `frames(...).count` so a caller deciding whether a day is worth
    /// opening does not pay to materialise it. The predicate is character-for-character the one in
    /// `frames(_:since:until:)`; a count that disagreed with the array it describes would be worse
    /// than no count, because the window sizes its track from it.
    public static func frameCount(_ store: ContextStore, since: Double, until: Double) throws -> Int {
        try store.read { db in
            try Int.fetchOne(
                db,
                sql: """
                    SELECT COUNT(*) FROM frames
                    WHERE capturedAt >= ? AND capturedAt <= ? AND imagePath IS NOT NULL
                    """,
                arguments: [since, until]
            ) ?? 0
        }
    }

    /// Showable frames matching `query`, newest first, with how many there were in total.
    ///
    /// Lives here and not in `Queries` for the reason stated at the top of this file: this is the one
    /// module allowed to select `frames.imagePath`, because the search *surface* draws pictures where
    /// every `Queries` result is destined for a language model over MCP and must never carry a
    /// filesystem path. A second imagePath-selecting site elsewhere is how a path reaches a tool
    /// result by accident.
    ///
    /// An empty or unindexable query is not an error and does not return nothing: it returns the
    /// newest captures, which is what a search surface with nothing typed into it should be showing.
    /// The FTS path unions the OCR index and the accessibility-tree index exactly as
    /// `Queries.recall` does — the two see different halves of the same window and fail in opposite
    /// directions, so a frame matched by either is a frame the user saw.
    ///
    /// `total` is counted in SQL rather than taken as `frames.count`, because the two answer
    /// different questions: the array is the page the grid can draw, and the count is what the panel
    /// says out loud. A surface that reports its page size as the total tells the user there were 60
    /// results when there were 600.
    public static func search(
        _ store: ContextStore,
        matching query: String,
        since: Double? = nil,
        until: Double? = nil,
        limit: Int = 60
    ) throws -> (frames: [RewindFrame], total: Int) {
        guard limit > 0 else { return ([], 0) }

        var conditions = ["f.imagePath IS NOT NULL"]
        var scope: [(any DatabaseValueConvertible)?] = []
        var source = "frames f"

        if let match = Queries.ftsExpression(for: query) {
            source = """
                (SELECT rowid AS rid FROM frames_fts WHERE frames_fts MATCH ?
                 UNION SELECT rowid AS rid FROM frames_ax_fts WHERE frames_ax_fts MATCH ?) m
                JOIN frames f ON f.rowid = m.rid
                """
            scope += [match, match]
        }
        if let since {
            conditions.append("f.capturedAt >= ?")
            scope.append(since)
        }
        if let until {
            conditions.append("f.capturedAt <= ?")
            scope.append(until)
        }
        let where_ = conditions.joined(separator: " AND ")

        return try store.read { db in
            let total = try Int.fetchOne(
                db,
                sql: "SELECT COUNT(*) FROM \(source) WHERE \(where_)",
                arguments: StatementArguments(scope)) ?? 0
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT f.id AS id, f.capturedAt AS capturedAt, f.appName AS appName,
                           f.bundleId AS bundleId, f.windowTitle AS windowTitle, f.imagePath AS imagePath
                    FROM \(source)
                    WHERE \(where_)
                    ORDER BY f.capturedAt DESC, f.id DESC
                    LIMIT ?
                    """,
                arguments: StatementArguments(scope + [limit]))
            return (rows.compactMap(RewindFrame.init), total)
        }
    }

    /// The newest showable frames at or before `instant`, newest first, optionally one app only.
    ///
    /// The read behind the `look` tool: "show me the screen" is a lookup backwards from a moment,
    /// never a scan forwards, because the newest frame at or before *now* is the closest thing to
    /// what is on the display this second. A frame *after* `instant` is deliberately unreachable —
    /// answering "what did it look like at 2pm" with a 2:40pm picture is not a slightly stale
    /// answer, it is a different question.
    ///
    /// `app` matches the display name or the bundle id, case-insensitively and by prefix, so
    /// `"Xcode"`, `"xcode"` and `"com.apple.dt.Xcode"` all find the same frames. Callers pass what
    /// a person would type.
    ///
    /// Lives in this file for the reason stated at the top of it: this is still the only module
    /// that selects `frames.imagePath`. What the `look` tool does with the path is convert the file
    /// into pixels — the path itself never reaches a tool result.
    public static func newestFrames(
        _ store: ContextStore,
        at instant: Double,
        app: String? = nil,
        limit: Int = 1
    ) throws -> [RewindFrame] {
        guard limit > 0 else { return [] }

        var conditions = ["imagePath IS NOT NULL", "capturedAt <= ?"]
        var scope: [(any DatabaseValueConvertible)?] = [instant]
        if let app, !app.trimmingCharacters(in: .whitespaces).isEmpty {
            conditions.append("(appName LIKE ? OR bundleId LIKE ?)")
            let prefix = app.trimmingCharacters(in: .whitespaces) + "%"
            scope += [prefix, prefix]
        }

        return try store.read { db in
            try Row.fetchAll(
                db,
                sql: """
                    SELECT id, capturedAt, appName, bundleId, windowTitle, ocrText, axText, imagePath
                    FROM frames
                    WHERE \(conditions.joined(separator: " AND "))
                    ORDER BY capturedAt DESC, id DESC
                    LIMIT ?
                    """,
                arguments: StatementArguments(scope + [limit])
            ).compactMap(RewindFrame.init)
        }
    }

    /// The span the timeline may travel over, or nil when nothing showable was ever captured.
    ///
    /// Bounded to frames that have an image, for the same reason `frames` is: a date picker that
    /// offered a day whose every row is image-less would open on an empty window.
    ///
    /// **Two statements, not one, and that is the whole cost of this query.** SQLite answers a bare
    /// `MIN(x)` or `MAX(x)` over an indexed column by seeking to one end of the index and stopping;
    /// it cannot do that for both at once, because one walk cannot end at both ends — asking for the
    /// pair in a single `SELECT` plans as a full scan of every showable row instead. Measured
    /// against a synthetic year of capture (547,500 frames): 581 ms as one statement with no index,
    /// 34.7 ms as one statement over `idx_frames_showable`, and 0.0 ms as this pair over the same
    /// index. It is worth the extra line here because `RewindModel.loadInitial` calls this on the
    /// main actor before the timeline can draw anything.
    ///
    /// Both reads share one connection, so they see one snapshot: a frame captured between them
    /// cannot make `newest` older than `oldest`.
    public static func coverage(_ store: ContextStore) throws -> ClosedRange<Double>? {
        try store.read { db in
            guard
                let oldest = try Double.fetchOne(
                    db, sql: "SELECT MIN(capturedAt) FROM frames WHERE imagePath IS NOT NULL"),
                let newest = try Double.fetchOne(
                    db, sql: "SELECT MAX(capturedAt) FROM frames WHERE imagePath IS NOT NULL")
            else { return nil }
            return oldest...max(oldest, newest)
        }
    }

    /// Which way a seek runs from an instant.
    public enum Seek: Sendable {
        case forward
        case backward
    }

    /// The showable capture nearest `instant` on one side of it, or nil when that side holds none.
    ///
    /// **Strictly** after — or strictly before — `instant`, never at it. The timeline seeks from a
    /// day's own boundary, and a capture sitting exactly on that boundary belongs to the day being
    /// left rather than to the one being looked for; an inclusive seek would answer "the previous
    /// day" with the day you are already on.
    ///
    /// This is what lets the window step over the days that hold nothing. `coverage` says the record
    /// runs from the first of the month to the fourteenth; it does not say that eight of those days
    /// are empty, and a "previous day" control that walked back one calendar day at a time would make
    /// the user press it eight times through eight blank screens to reach the day before. One seek
    /// lands on the next day that has something on it.
    ///
    /// **One indexed seek, not a scan.** `idx_frames_capturedAt` serves the range and the order at
    /// once, so the plan is `SEARCH frames USING INDEX idx_frames_capturedAt (capturedAt>?)` with no
    /// sort step: SQLite walks outward from the boundary and stops at the first row that has an
    /// image. That is why the direction is baked into the SQL rather than fetched and filtered in
    /// Swift — the point of the query is that it reads a handful of rows and not a day of them.
    public static func nearestCapture(
        _ store: ContextStore,
        from instant: Double,
        direction: Seek
    ) throws -> Double? {
        let forward = direction == .forward
        return try store.read { db in
            try Double.fetchOne(
                db,
                sql: """
                    SELECT capturedAt FROM frames
                    WHERE capturedAt \(forward ? ">" : "<") ? AND imagePath IS NOT NULL
                    ORDER BY capturedAt \(forward ? "ASC" : "DESC")
                    LIMIT 1
                    """,
                arguments: [instant])
        }
    }

    /// The newest bundle identifier seen for each app name.
    ///
    /// Icons resolve from a bundle id (`NSWorkspace.urlForApplication(withBundleIdentifier:)`), but
    /// `frames.bundleId` only exists from the migration that added it forward — every row captured
    /// before it is NULL and always will be. Rather than probe the filesystem for those, the app
    /// name is looked up here against any *later* row that did record an id: one frame of Cursor
    /// captured today teaches the whole back catalogue of Cursor frames what Cursor's bundle id is.
    /// The name-based fallback stays for apps that have not been seen since, which is the only case
    /// left.
    ///
    /// `MAX(id)` picks the newest sighting, which matters when an app is replaced by a rebuilt one
    /// under a new identifier — the current id is the one that resolves today.
    public static func bundleIdsByApp(_ store: ContextStore) throws -> [String: String] {
        try store.read { db in
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT appName, bundleId FROM frames
                    WHERE bundleId IS NOT NULL AND TRIM(bundleId) <> ''
                      AND appName IS NOT NULL AND TRIM(appName) <> ''
                      AND id IN (SELECT MAX(id) FROM frames
                                 WHERE bundleId IS NOT NULL AND TRIM(bundleId) <> ''
                                 GROUP BY appName)
                    """)
            return rows.reduce(into: [String: String]()) { map, row in
                guard let app: String = row["appName"], let bundle: String = row["bundleId"] else { return }
                map[app] = bundle
            }
        }
    }
}

/// One scrubbable frame: when it was captured, what owned the screen, and where its picture is.
///
/// Distinct from `Frame` (the write shape) and from `Hit` (the MCP wire shape) because it is the
/// only one of the three that carries a filesystem path, and keeping that in its own type is what
/// stops a path reaching a tool result by being a field on a struct someone already returns.
public struct RewindFrame: Sendable, Equatable, Identifiable {
    public let id: Int64
    /// Unix epoch seconds. The track maps pixels to this, never to an array index.
    public let capturedAt: Double
    /// Never empty — `RewindQueries.unknownApp` stands in for a null or blank column.
    public let appName: String
    /// The owning application's bundle identifier, or nil for any row captured before the column
    /// existed. Nil means "not recorded", never "no bundle".
    public let bundleId: String?
    public let windowTitle: String?
    public let ocrText: String?
    /// The focused window's accessibility text, as `Frame.axText` holds it.
    ///
    /// Carried here because the two text columns fail in opposite directions and the `look` tool
    /// reads both: OCR sees everything drawn and guesses at it, accessibility is exact and covers
    /// only what the app chose to expose. It is also half of the redaction evidence — a credential
    /// `Redaction.scrub` caught may have been caught in either column, and the picture must be
    /// withheld if it was caught in *either*.
    public let axText: String?
    /// Absolute path to the stored HEIC. Non-optional by construction: a row without one is not a
    /// `RewindFrame`, so no display path has to defend against a missing picture.
    public let imagePath: String

    public init(
        id: Int64,
        capturedAt: Double,
        appName: String,
        bundleId: String? = nil,
        windowTitle: String? = nil,
        ocrText: String? = nil,
        axText: String? = nil,
        imagePath: String
    ) {
        self.id = id
        self.capturedAt = capturedAt
        let trimmed = appName.trimmingCharacters(in: .whitespacesAndNewlines)
        self.appName = trimmed.isEmpty ? RewindQueries.unknownApp : trimmed
        self.bundleId = RewindFrame.nonEmpty(bundleId)
        self.windowTitle = RewindFrame.nonEmpty(windowTitle)
        self.ocrText = ocrText
        self.axText = axText
        self.imagePath = imagePath
    }

    /// Nil for a row the query cannot honour — no id, or no image path. Returning nil rather than
    /// substituting a placeholder keeps `imagePath` a promise the type actually keeps.
    init?(_ row: Row) {
        guard let id: Int64 = row["id"], let path: String = row["imagePath"], !path.isEmpty else {
            return nil
        }
        let at: Double? = row["capturedAt"]
        let app: String? = row["appName"]
        self.init(
            id: id,
            capturedAt: at ?? 0,
            appName: app ?? RewindQueries.unknownApp,
            bundleId: row["bundleId"],
            windowTitle: row["windowTitle"],
            ocrText: row["ocrText"],
            // Absent from the timeline's own SELECT, and `Row` returns nil rather than throwing for
            // a column that was not fetched — so a query that does not need the accessibility text
            // does not pay to read it, and one that does gets it by naming it.
            axText: row["axText"],
            imagePath: path)
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
        else { return nil }
        return trimmed
    }
}

// MARK: - Time-linear lookup

extension Array where Element == RewindFrame {
    /// The frame nearest `instant`, by binary search over `capturedAt`.
    ///
    /// The whole reason the array is sorted and complete. A track that maps a pixel to a *time* has
    /// to turn that time back into a frame, and doing it by scanning would cost the length of the
    /// day on every pointer move during a drag. Nearest rather than floor: scrubbing into a gap
    /// should show the closest thing that was captured, not nothing.
    ///
    /// Requires ascending `capturedAt`, which `RewindQueries.frames` guarantees.
    public func nearestIndex(to instant: Double) -> Int? {
        guard !isEmpty else { return nil }
        var low = 0
        var high = count - 1
        while low < high {
            let mid = low + (high - low) / 2
            if self[mid].capturedAt < instant {
                low = mid + 1
            } else {
                high = mid
            }
        }
        // `low` is the first frame at or after `instant`; its predecessor may still be nearer.
        guard low > 0 else { return low }
        let after = self[low].capturedAt - instant
        let before = instant - self[low - 1].capturedAt
        return before <= after ? low - 1 : low
    }
}
