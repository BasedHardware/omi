import Foundation
import GRDB

/// The reads the Rewind timeline window performs, and the only place `frames.imagePath` is
/// selected.
///
/// `Queries` deliberately never returns an image path: every one of its results is destined for a
/// language model over MCP, and a filesystem path is neither answerable nor safe to hand over. The
/// timeline is the one consumer that needs the pixels, so it gets its own entry point rather than a
/// flag threaded through the MCP shapes.
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

    /// The span the timeline may travel over, or nil when nothing showable was ever captured.
    ///
    /// Bounded to frames that have an image, for the same reason `frames` is: a date picker that
    /// offered a day whose every row is image-less would open on an empty window.
    public static func coverage(_ store: ContextStore) throws -> ClosedRange<Double>? {
        try store.read { db in
            let row = try Row.fetchOne(
                db,
                sql: """
                    SELECT MIN(capturedAt) AS oldest, MAX(capturedAt) AS newest
                    FROM frames WHERE imagePath IS NOT NULL
                    """)
            guard let row, let oldest: Double = row["oldest"], let newest: Double = row["newest"] else {
                return nil
            }
            return oldest...max(oldest, newest)
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
        imagePath: String
    ) {
        self.id = id
        self.capturedAt = capturedAt
        let trimmed = appName.trimmingCharacters(in: .whitespacesAndNewlines)
        self.appName = trimmed.isEmpty ? RewindQueries.unknownApp : trimmed
        self.bundleId = RewindFrame.nonEmpty(bundleId)
        self.windowTitle = RewindFrame.nonEmpty(windowTitle)
        self.ocrText = ocrText
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
