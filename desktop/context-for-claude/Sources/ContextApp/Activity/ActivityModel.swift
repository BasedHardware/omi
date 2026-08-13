//
//  ActivityModel.swift — the captured day, as one list.
//
//  A conversation and the frames that were on screen while it happened are records of the same
//  minute, and until now the app filed them in two places: the timeline draws pixels, the search
//  panel draws hits, and answering "what was I doing at eight?" meant visiting both and reconciling
//  them by eye. This composes them into **one reverse-chronological stream, grouped by day** — the
//  order they actually happened in, newest first.
//
//  **Conversations stay dominant and the frames stay first-class.** A run of screen moments that
//  fell inside a conversation's window renders *indented under* it, which is what keeps the
//  conversation the thing your eye lands on. It is not a child of a card, though: it is a row of the
//  same spine, so filtering to one kind is a real filter over the whole stream rather than a
//  different screen. When one kind is soloed the indent collapses and every row states its own time
//  (see `ActivityRow.isAttached` and `ActivityComposer.compose`), so the list stays a clock rather
//  than degrading into a flat list.
//
//  Everything here is a pure function of its inputs, deliberately: the composition is the part with
//  rules in it (what attaches to what, what a day header counts, where a cluster ends), and rules
//  that can only be checked by looking at a screenshot are rules that drift.
//

import ContextCore
import Foundation

// MARK: - Kind

/// The one axis the stream filters on.
///
/// `everything` is not a third kind of row — it is the absence of a filter — which is why
/// `ActivityRow.kind` can never hold it. The composer only ever writes `.conversations` or
/// `.screen` into a row, and `ActivityComposer.filter` treats `.everything` as "match anything"
/// rather than as a value to compare against.
enum ActivityKind: String, CaseIterable, Identifiable, Sendable {
    case everything
    case conversations
    case screen

    var id: String { rawValue }

    var title: String {
        switch self {
        case .everything: return "Activity"
        case .conversations: return "Conversations"
        case .screen: return "Screens"
        }
    }

    /// The chips, in the order they are shown.
    static let chips: [ActivityKind] = [.everything, .conversations, .screen]
}

// MARK: - Leaves

/// One frame that was on screen.
///
/// Deliberately not `RewindFrame`: that type carries the OCR text and the accessibility text of the
/// window it came from, and carrying those through a day of thousands of frames is the difference
/// between a scroll and a stall. This is the six columns a row needs to lay itself out and find its
/// picture, and nothing else.
struct ActivityMoment: Identifiable, Equatable, Sendable {
    let id: Int64
    let timestamp: Date
    let appName: String
    let bundleId: String?
    let windowTitle: String?
    /// Absolute path to the stored image, or nil for a frame whose picture is gone. Nil is a real
    /// and ordinary state — retention unlinks files — and the tile draws the app instead.
    let imagePath: String?

    init(
        id: Int64,
        timestamp: Date,
        appName: String,
        bundleId: String? = nil,
        windowTitle: String? = nil,
        imagePath: String? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.appName = appName
        self.bundleId = bundleId
        self.windowTitle = windowTitle
        self.imagePath = imagePath
    }

    /// The projection of a stored frame this surface actually needs.
    init(frame: RewindFrame) {
        self.init(
            id: frame.id,
            timestamp: Date(timeIntervalSince1970: frame.capturedAt),
            appName: frame.appName,
            bundleId: frame.bundleId,
            windowTitle: frame.windowTitle,
            imagePath: frame.imagePath)
    }

    /// What the caption says. The window title is the specific thing; the app is the true fallback.
    var label: String {
        guard let windowTitle, !windowTitle.isEmpty else { return appName }
        return windowTitle
    }

    /// The record `FrameLoader` decodes from, rebuilt from what the row already holds — so a strip
    /// never goes back to the database for a second row per picture. Nil when there is no picture,
    /// which is what puts the tile into its app-icon state rather than into a spinner.
    var frame: RewindFrame? {
        guard let imagePath else { return nil }
        return RewindFrame(
            id: id,
            capturedAt: timestamp.timeIntervalSince1970,
            appName: appName,
            bundleId: bundleId,
            windowTitle: windowTitle,
            imagePath: imagePath)
    }
}

/// One spoken session, plus the count the row states about it.
///
/// Wraps `SessionSummary` rather than restating it: the summary is what `Queries.sessions` already
/// returns and what every other reader of this database sees, and a second shape for the same
/// session is a second place for "how long was it" to be answered differently.
struct ActivityConversation: Identifiable, Equatable, Sendable {
    let session: SessionSummary
    /// How many screen moments fell inside this conversation's window. Filled in by the composer,
    /// which is the only thing that knows.
    let momentCount: Int

    init(session: SessionSummary, momentCount: Int = 0) {
        self.session = session
        self.momentCount = momentCount
    }

    var id: Int64 { session.id }

    var startedAt: Date { Date(timeIntervalSince1970: session.startedAt) }

    /// The end of the conversation's window on the clock — and **the same window the day header's
    /// duration states**, which is why it is derived from `durationSeconds` rather than from
    /// `endedAt`.
    ///
    /// A session that is still open has no `endedAt`, but it does have a last line, and
    /// `Queries.sessions` already resolves that into `durationSeconds`. Reading `endedAt` directly
    /// would make a live conversation a *point* on the clock: it would attach none of the frames
    /// captured while it was happening, which is exactly the conversation a reader is most likely
    /// to be looking at.
    var finishedAt: Date { startedAt.addingTimeInterval(duration) }

    var duration: TimeInterval { max(0, session.durationSeconds) }

    /// How many transcript lines it produced.
    var segmentCount: Int { session.lineCount }

    /// What the row is called. There is no server-side title here — this database stores speech,
    /// not summaries — so the app that was in front is the most specific true thing available, and
    /// "Conversation" is the fallback rather than an invented headline.
    var title: String {
        let hint = (session.appHint ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return hint.isEmpty ? "Conversation" : "\(hint) conversation"
    }

    /// "8m 9s · 42 spoken lines · 6 screen moments" — and each clause is dropped when its count is
    /// zero rather than shown as "0 spoken lines", which reads as a defect rather than as an
    /// absence. With every clause gone the line falls back to the time, so a row is never blank.
    var subtitle: String {
        var parts: [String] = []
        if duration >= 1 { parts.append(ActivityFormat.duration(duration)) }
        if segmentCount > 0 {
            parts.append(ActivityFormat.plural(segmentCount, "spoken line", "spoken lines"))
        }
        if momentCount > 0 {
            parts.append(ActivityFormat.plural(momentCount, "screen moment", "screen moments"))
        }
        if parts.isEmpty { parts.append(ActivityFormat.time(startedAt)) }
        return parts.joined(separator: " · ")
    }

    /// What a typed query is matched against. Pre-lowercased, because the filter runs on every
    /// keystroke and folding a thousand rows per keystroke is work the composer already did once.
    var searchText: String {
        [title, session.appHint ?? "", session.preview]
            .joined(separator: " ")
            .lowercased()
    }
}

// MARK: - Row

/// One row of the stream.
struct ActivityRow: Identifiable, Equatable {
    enum Content: Equatable {
        case conversation(ActivityConversation)
        /// The frames a strip draws, plus how many there were in the run they were taken from — a
        /// strip that silently shows 8 of 184 is a strip that lies about the day.
        case moments(shown: [ActivityMoment], total: Int)
    }

    /// Derived from the record ids underneath it, so a repeated record is a repeated row rather
    /// than a duplicate SwiftUI identity. See `ActivityComposer.compose`.
    let id: String
    /// Where this row sits on the clock. The only thing the stream is ordered by.
    let anchor: Date
    /// Never `.everything`: a row is one kind of thing.
    let kind: ActivityKind
    /// True when this row was produced by the conversation directly above it. Indented while the
    /// whole stream is shown; flattened — and given its own timestamp — the moment one kind is
    /// soloed.
    let isAttached: Bool
    let content: Content

    /// What a typed query is matched against, already lowercased.
    let searchText: String
}

// MARK: - Day

/// One day of the stream, with the header that counts it.
struct ActivityDay: Identifiable, Equatable {
    /// The local start of the day. Stable across recompositions, which is what keeps the sticky
    /// header from being rebuilt on every scroll.
    let id: Date
    let title: String
    /// **The counts are of the whole day, never of what survived a filter.** `ActivityComposer`
    /// carries them through `filter` untouched, so a narrowed stream still says how big the day
    /// really was — a header that shrank with the filter would leave nothing on screen able to say
    /// what was being hidden.
    let momentCount: Int
    let conversationCount: Int
    let rows: [ActivityRow]

    /// "1,204 moments · 4 conversations". Zero clauses are dropped for the same reason as on a row.
    ///
    /// **This line is the whole of a collapsed day.** With the rows folded away it is the only
    /// thing saying what is behind the header, so it names every kind the day holds.
    var subtitle: String {
        var parts: [String] = []
        if momentCount > 0 { parts.append(ActivityFormat.plural(momentCount, "moment", "moments")) }
        if conversationCount > 0 {
            parts.append(ActivityFormat.plural(conversationCount, "conversation", "conversations"))
        }
        return parts.joined(separator: " · ")
    }

    /// How many *things* this day is showing, which is not the same as how many rows it drew: one
    /// strip can stand for a hundred and eighty-four frames. The count the surface says out loud is
    /// a fraction of the corpus, so it has to count the corpus's units rather than the stream's.
    var matchCount: Int {
        rows.reduce(0) { total, row in
            switch row.content {
            case .conversation: return total + 1
            case .moments(_, let count): return total + count
            }
        }
    }
}

// MARK: - Folded days

/// Which days are folded shut, as a value.
///
/// **Keyed by the day's own identity, never by its position.** The stream fills older days in as
/// they are read, so a set keyed by index folds a *different* day the moment one lands — the day
/// you collapsed reopens and the one above it closes, which reads as the list rearranging itself.
///
/// **Session-only, deliberately.** A day found silently collapsed on the next launch is
/// indistinguishable from a day whose capture failed, and this surface is the one place a user
/// checks whether anything was recorded at all. Folding is a thing you do while reading, not a
/// preference.
struct ActivityDayCollapse: Equatable {
    private var folded: Set<Date> = []

    init() {}

    var isEmpty: Bool { folded.isEmpty }

    func contains(_ dayID: Date) -> Bool { folded.contains(dayID) }

    mutating func toggle(_ dayID: Date) {
        if folded.contains(dayID) {
            folded.remove(dayID)
        } else {
            folded.insert(dayID)
        }
    }
}

// MARK: - Screen moments, per day

/// What the stream knows about one day of screen capture.
///
/// The exact `total` and the exact `hourCounts` come from every frame in the day; `sampled` is the
/// handful the strips can actually draw. Keeping the count separate from the sample is what lets a
/// header say 1,204 while a strip shows eight of them.
struct ActivityDayScreen: Equatable, Sendable {
    var total: Int = 0
    /// 24 entries, indexed by *local* hour.
    var hourCounts: [Int] = Array(repeating: 0, count: 24)
    var sampled: [ActivityMoment] = []

    static let empty = ActivityDayScreen()
}

// MARK: - Formatting

/// Every string this surface shows, in one place, so the phrasing is a test rather than a
/// screenshot.
enum ActivityFormat {
    static func plural(_ count: Int, _ singular: String, _ plural: String) -> String {
        "\(number(count)) \(count == 1 ? singular : plural)"
    }

    static func number(_ value: Int) -> String {
        numberFormatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    /// "8m 9s", "1h 04m", "42s".
    static func duration(_ seconds: TimeInterval) -> String {
        let total = Int(seconds.rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 { return String(format: "%dh %02dm", hours, minutes) }
        if minutes > 0 { return "\(minutes)m \(secs)s" }
        return "\(secs)s"
    }

    static func time(_ date: Date) -> String { timeFormatter.string(from: date) }

    /// "Wednesday 6 August" — and "Today" / "Yesterday" for the two days a date is the wrong answer
    /// for, because nobody reads their own morning as a date.
    static func day(_ date: Date, calendar: Calendar = .current, now: Date = Date()) -> String {
        if calendar.isDate(date, inSameDayAs: now) { return "Today" }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: now)),
            calendar.isDate(date, inSameDayAs: yesterday)
        {
            return "Yesterday"
        }
        let formatter =
            calendar.isDate(date, equalTo: now, toGranularity: .year) ? dayFormatter : dayYearFormatter
        return formatter.string(from: date)
    }

    /// The hour a rail label states: "6 AM", "12 PM".
    static func hourLabel(_ hour: Int) -> String {
        switch hour {
        case 0: return "12 AM"
        case 12: return "12 PM"
        case ..<12: return "\(hour) AM"
        default: return "\(hour - 12) PM"
        }
    }

    private static let numberFormatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter
    }()

    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter
    }()

    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE d MMMM"
        return formatter
    }()

    private static let dayYearFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE d MMMM yyyy"
        return formatter
    }()
}
