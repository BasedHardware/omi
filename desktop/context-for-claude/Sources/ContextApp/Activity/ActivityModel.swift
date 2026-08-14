//
//  ActivityModel.swift — the captured day, as one list.
//
//  A conversation, the memories and tasks it left behind, and the frames that were on screen while
//  it happened are records of the same minute, and until now the app filed them in three places: the
//  timeline draws pixels, the search panel draws hits, the account holds the rest, and answering
//  "what was I doing at eight?" meant visiting all three and reconciling them by eye. This composes
//  them into **one reverse-chronological stream, grouped by day** — the order they actually happened
//  in, newest first.
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
/// `all` is not a fifth kind of row — it is the absence of a filter, and the merged view is the
/// whole point of the surface: one spine where a conversation, the memory it produced, the task it
/// left behind and the screen you were on sit together. `ActivityRow.kind` can therefore never hold
/// it: the composer only ever writes one of the other four into a row, and `ActivityComposer.filter`
/// treats `.all` as "match anything" rather than as a value to compare against.
enum ActivityKind: String, CaseIterable, Identifiable, Sendable {
    case all
    case conversations
    case memories
    case tasks
    case rewind

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "All"
        case .conversations: return "Conversations"
        case .memories: return "Memories"
        case .tasks: return "Tasks"
        case .rewind: return "Rewind"
        }
    }

    /// The chips, in the order they are shown — the declaration order, so there is one place the
    /// order lives rather than a list that can drift out of step with the cases.
    static let chips: [ActivityKind] = allCases
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

/// One conversation on the spine, from whichever half of the world knew about it.
///
/// **Two sources, one row shape.** The account is the one that knows what a conversation was *about*
/// — it carries the title and the emoji the mockup shows — and this Mac is the one that knows a
/// conversation happened at all when nobody is signed in. Rather than two row kinds, the difference
/// is one field (`source`) and two optionals, so the stream's ordering, attachment and counting
/// rules are written once.
struct ActivityConversation: Identifiable, Equatable, Sendable {
    /// Who told us about this conversation. It decides one thing on screen — whether the tile is the
    /// account's emoji or the speech mark — and nothing else.
    enum Source: Equatable, Sendable {
        case account
        case local
    }

    let id: String
    let source: Source
    let title: String
    /// The account's emoji. `nil` for a local session, which has no way to know one; the row draws
    /// the speech mark instead rather than inventing a glyph the account did not choose.
    let emoji: String?
    let startedAt: Date
    let duration: TimeInterval
    /// How many transcript lines this Mac heard. Zero for an account conversation, which is a
    /// summary rather than a recording — the clause is dropped rather than printed as "0".
    let segmentCount: Int
    /// What the account calls it, when it says anything. Shown under the counts.
    let overview: String?
    /// What the row was matched against before it was lowercased — the parts a typed query should
    /// reach that the title does not already carry.
    let matchable: String
    /// How many screen moments fell inside this conversation's window. Filled in by the composer,
    /// which is the only thing that knows.
    let momentCount: Int

    init(
        id: String,
        source: Source,
        title: String,
        emoji: String? = nil,
        startedAt: Date,
        duration: TimeInterval,
        segmentCount: Int = 0,
        overview: String? = nil,
        matchable: String = "",
        momentCount: Int = 0
    ) {
        self.id = id
        self.source = source
        self.title = title
        self.emoji = emoji
        self.startedAt = startedAt
        self.duration = max(0, duration)
        self.segmentCount = segmentCount
        self.overview = overview
        self.matchable = matchable
        self.momentCount = momentCount
    }

    /// One conversation as the account tells it.
    init(account: ActivityAccountConversation) {
        let started = Date(timeIntervalSince1970: account.startedAt)
        self.init(
            id: account.id,
            source: .account,
            title: account.title,
            emoji: account.emoji.isEmpty ? nil : account.emoji,
            startedAt: started,
            duration: max(0, account.finishedAt - account.startedAt),
            overview: account.overview,
            matchable: account.overview ?? "")
    }

    /// One spoken session as this Mac heard it.
    ///
    /// There is no server-side title in this database — it stores speech, not summaries — so the app
    /// that was in front is the most specific true thing available, and "Conversation" is the
    /// fallback rather than an invented headline.
    ///
    /// **The window is derived from `durationSeconds`, not from `endedAt`.** A session that is still
    /// open has no `endedAt`, but it does have a last line, and `Queries.sessions` already resolves
    /// that into a duration. Reading `endedAt` directly would make a live conversation a *point* on
    /// the clock: it would attach none of the frames captured while it was happening, which is
    /// exactly the conversation a reader is most likely to be looking at.
    init(session: SessionSummary) {
        let hint = (session.appHint ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        self.init(
            id: ActivityConversation.localID(session.id),
            source: .local,
            title: hint.isEmpty ? "Conversation" : "\(hint) conversation",
            startedAt: Date(timeIntervalSince1970: session.startedAt),
            duration: session.durationSeconds,
            segmentCount: session.lineCount,
            matchable: "\(session.appHint ?? "") \(session.preview)")
    }

    /// A local session's identity in the merged stream. Prefixed so a session id and an account id
    /// can never collide on a surface that now holds both.
    static func localID(_ sessionID: Int64) -> String { "local:\(sessionID)" }

    /// The same conversation, told what the composer worked out about it.
    func counted(momentCount: Int) -> ActivityConversation {
        ActivityConversation(
            id: id, source: source, title: title, emoji: emoji, startedAt: startedAt,
            duration: duration, segmentCount: segmentCount, overview: overview,
            matchable: matchable, momentCount: momentCount)
    }

    /// The end of the conversation's window on the clock — and **the same window the frames attach
    /// inside of**.
    var finishedAt: Date { startedAt.addingTimeInterval(duration) }

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
        [title, matchable].joined(separator: " ").lowercased()
    }
}

// MARK: - Memories and tasks

/// One durable fact the account is keeping.
///
/// A projection of `ActivityAccountMemory` rather than the seam's own type, for the reason
/// `ActivityMoment` is one: the stream sorts, clusters and filters these, and every one of those is
/// a `Date` comparison against a value the seam states in epoch seconds.
struct ActivityMemory: Identifiable, Equatable, Sendable {
    let id: String
    let text: String
    let timestamp: Date

    init(id: String, text: String, timestamp: Date) {
        self.id = id
        self.text = text
        self.timestamp = timestamp
    }

    init(memory: ActivityAccountMemory) {
        self.init(
            id: memory.id, text: memory.content,
            timestamp: Date(timeIntervalSince1970: memory.at))
    }
}

/// One commitment the account extracted or the user wrote down.
///
/// **Read-only here, deliberately.** `ActivityAccountReading` has one method and it reads; a tick
/// this surface could toggle would be a write the seam does not carry, so the glyph states the
/// task's condition rather than offering to change it.
struct ActivityTask: Identifiable, Equatable, Sendable {
    let id: String
    let text: String
    let isCompleted: Bool
    let timestamp: Date

    init(id: String, text: String, isCompleted: Bool, timestamp: Date) {
        self.id = id
        self.text = text
        self.isCompleted = isCompleted
        self.timestamp = timestamp
    }

    init(task: ActivityAccountTask) {
        self.init(
            id: task.id, text: task.text, isCompleted: task.completed,
            timestamp: Date(timeIntervalSince1970: task.at))
    }
}

// MARK: - Row

/// One row of the stream.
struct ActivityRow: Identifiable, Equatable {
    enum Content: Equatable {
        case conversation(ActivityConversation)
        /// The memories of one run, together. A memory is one sentence and a row per sentence is a
        /// column of stubs; the run they came out of is the thing worth having a row for.
        case memories([ActivityMemory])
        /// The tasks of one run, on the same terms.
        case tasks([ActivityTask])
        /// The frames a strip draws, plus how many there were in the run they were taken from — a
        /// strip that silently shows 8 of 184 is a strip that lies about the day.
        case moments(shown: [ActivityMoment], total: Int)
    }

    /// Derived from the record ids underneath it, so a repeated record is a repeated row rather
    /// than a duplicate SwiftUI identity. See `ActivityComposer.compose`.
    let id: String
    /// Where this row sits on the clock. The only thing the stream is ordered by.
    let anchor: Date
    /// Never `.all`: a row is one kind of thing.
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
    let memoryCount: Int
    let taskCount: Int
    let rows: [ActivityRow]

    init(
        id: Date,
        title: String,
        momentCount: Int = 0,
        conversationCount: Int = 0,
        memoryCount: Int = 0,
        taskCount: Int = 0,
        rows: [ActivityRow]
    ) {
        self.id = id
        self.title = title
        self.momentCount = momentCount
        self.conversationCount = conversationCount
        self.memoryCount = memoryCount
        self.taskCount = taskCount
        self.rows = rows
    }

    /// "1,204 moments · 4 conversations · 3 memories". Zero clauses are dropped for the same reason
    /// as on a row.
    ///
    /// **This line is the whole of a collapsed day.** With the rows folded away it is the only
    /// thing saying what is behind the header, so it names every kind the day holds.
    var subtitle: String {
        var parts: [String] = []
        if momentCount > 0 { parts.append(ActivityFormat.plural(momentCount, "moment", "moments")) }
        if conversationCount > 0 {
            parts.append(ActivityFormat.plural(conversationCount, "conversation", "conversations"))
        }
        if memoryCount > 0 {
            parts.append(ActivityFormat.plural(memoryCount, "memory", "memories"))
        }
        if taskCount > 0 { parts.append(ActivityFormat.plural(taskCount, "task", "tasks")) }
        return parts.joined(separator: " · ")
    }

    /// How many *things* this day holds, counted from the header rather than from the rows — the
    /// unit the corpus line at the top of the panel is denominated in. See `matchCount` for why the
    /// two are different sums.
    var thingCount: Int { momentCount + conversationCount + memoryCount + taskCount }

    /// How many *things* this day is showing, which is not the same as how many rows it drew: one
    /// strip can stand for a hundred and eighty-four frames. The count the surface says out loud is
    /// a fraction of the corpus, so it has to count the corpus's units rather than the stream's.
    var matchCount: Int {
        rows.reduce(0) { total, row in
            switch row.content {
            case .conversation: return total + 1
            case .memories(let memories): return total + memories.count
            case .tasks(let tasks): return total + tasks.count
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

// MARK: - The corpus line

/// The one sentence in the panel header's trailing corner.
///
/// It has two jobs and they are not the same sentence: at rest it says how much this Mac and the
/// account are holding between them, and under a filter it says how much of that survived. Collapsing
/// them into one string is how a surface ends up claiming "0 moments captured" the moment somebody
/// types a letter.
///
/// **Every branch names its scope, because there is a second counter on this surface.** The hour rail
/// on the left counts *one day* of screen capture; this corner counts everything. A large `0` beside
/// `798 so far · still counting` is unreadable unless each says which it is about, and giving the two
/// different *nouns* is not enough — the missing words are "today" and "everything". The rail says its
/// own half.
enum ActivityCount {
    /// **The scope this corner counts, in the app's own words.** One constant rather than three
    /// literals, so the branches cannot end up describing three different corpora.
    static let scope = "everything Omi has kept"

    /// - Parameter isSettled: whether `total` is a finished count. The day walk fills older days in
    ///   behind an already-readable list, so the number climbs under the reader — it says so instead
    ///   of presenting a moving figure as a settled one.
    static func sentence(matching: Int, total: Int, isFiltering: Bool, isSettled: Bool) -> String {
        guard isFiltering else {
            guard isSettled else { return "\(number(total)) so far · still counting \(scope)" }
            return "\(number(total)) moment\(total == 1 ? "" : "s") in \(scope)"
        }
        return "\(number(matching)) result\(matching == 1 ? "" : "s") · of \(number(total)) in \(scope)"
    }

    /// What the corner says before anything has been counted. Not a confident zero: nothing has been
    /// read yet, and a zero is a claim about the machine.
    static let counting = "Counting what you've captured…"

    /// Grouped digits, because the count is routinely five figures and an ungrouped one is unreadable
    /// at a glance — which is the only way this line is ever read.
    static func number(_ value: Int) -> String { ActivityFormat.number(value) }
}
