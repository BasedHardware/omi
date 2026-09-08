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

    /// **Which of the two halves this filter is actually asking for.**
    ///
    /// The spine has two sources and the chips solo across them, so "why is this empty" has a
    /// different answer under every chip. Without these two questions the surface reported the
    /// account's silence as the reason an empty `Rewind` was empty — a confident wrong answer about
    /// the wrong machine — and promised, under a soloed `Memories`, that "screen moments from this
    /// Mac still show up here" on a list that was excluding them.
    ///
    /// Screen moments are the only local kind, so this is one case rather than a set.
    var showsLocalCapture: Bool {
        switch self {
        case .all, .rewind: return true
        case .conversations, .memories, .tasks: return false
        }
    }

    /// True when the Omi account is a source of what this filter shows. Conversations come from
    /// both halves, so only `rewind` is outside it.
    var showsAccount: Bool {
        switch self {
        case .all, .conversations, .memories, .tasks: return true
        case .rewind: return false
        }
    }
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
/// is one field (`source`) and the counts each half can state, so the stream's ordering, attachment
/// and counting rules are written once.
///
/// **The title and the emoji are the shipping app's, word for word.** `SpineConversation` in the main
/// macOS app reads `structured.title` with `"Untitled conversation"` behind it and `structured.emoji`
/// with `"💬"` behind it, and nothing else is ever put in either. This surface used to synthesise a
/// headline out of the capture session's app hint — "Arc conversation", "Warp conversation" — which
/// is not a title anybody wrote, is not what the same conversation is called anywhere else in Omi,
/// and read as the product having failed to summarise. A row that cannot be titled says so.
struct ActivityConversation: Identifiable, Equatable, Sendable {
    /// Who told us about this conversation. It decides nothing on screen; the detail sheet reads it
    /// to know which half of the world to ask for the transcript.
    enum Source: Equatable, Sendable {
        case account
        case local
    }

    /// What a conversation nobody titled is called. The shipping app's string, not a second opinion
    /// about the same absence.
    static let untitled = "Untitled conversation"

    /// The tile glyph when the account chose none. An empty emoji would render as a blank circle,
    /// and the app hint is not a glyph, so a speech mark is used — because every row here is one.
    static let defaultEmoji = "💬"

    let id: String
    let source: Source
    let title: String
    /// Always something drawable: the account's emoji when it chose one, `defaultEmoji` when it did
    /// not and for every local session, which has no way to know one.
    let emoji: String
    let startedAt: Date
    let duration: TimeInterval
    /// How many transcript lines this Mac heard. Zero for an account conversation, which is a
    /// summary rather than a recording — the clause is dropped rather than printed as "0".
    let segmentCount: Int
    /// What the account calls it, when it says anything.
    ///
    /// **It is search material, not row copy** — `searchText` is the only thing that reads it here,
    /// exactly as `SpineConversation.searchText` is the only thing that reads `structured.overview`
    /// in the shipping app. A row states what the conversation *was*; a paragraph about what it was
    /// about belongs on the conversation itself.
    let overview: String?
    /// What the row was matched against before it was lowercased — the parts a typed query should
    /// reach that the title does not already carry.
    let matchable: String
    /// How many memories the account extracted from this conversation, and how many screen moments
    /// fell inside its window. Both are filled in by the composer, which is the only thing that
    /// knows, and both are dropped from the subtitle when they are zero.
    let memoryCount: Int
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
        memoryCount: Int = 0,
        momentCount: Int = 0
    ) {
        self.id = id
        self.source = source
        // The two fallbacks are applied here rather than at each call site, so there is one answer
        // in the product to "what is a conversation called when nothing named it".
        let trimmedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        self.title = trimmedTitle.isEmpty ? Self.untitled : trimmedTitle
        let trimmedEmoji = (emoji ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        self.emoji = trimmedEmoji.isEmpty ? Self.defaultEmoji : trimmedEmoji
        self.startedAt = startedAt
        self.duration = max(0, duration)
        self.segmentCount = segmentCount
        self.overview = overview
        self.matchable = matchable
        self.memoryCount = memoryCount
        self.momentCount = momentCount
    }

    /// One conversation as the account tells it.
    init(account: ActivityAccountConversation) {
        let started = Date(timeIntervalSince1970: account.startedAt)
        self.init(
            id: account.id,
            source: .account,
            title: account.title,
            emoji: account.emoji,
            startedAt: started,
            duration: max(0, account.finishedAt - account.startedAt),
            overview: account.overview,
            matchable: account.overview ?? "")
    }

    /// One spoken session as this Mac heard it, and **the one row shape the shipping app has no
    /// counterpart for.**
    ///
    /// The spine in the main app composes from the account alone, so every row it draws has a title.
    /// This app hears speech without an account: a session nobody is going to upload — because
    /// nobody is signed in, because Airgap Mode is on, because the queue had nothing uploadable in
    /// it — is still a real thing that happened on this Mac, and dropping it would make that user's
    /// day claim they had not spoken. So it gets a row, and the row is the plainest possible thing:
    /// the same `untitled` string the account's own untitled conversations get, with the spoken-line
    /// count under it as the one thing this half of the world actually knows. Nothing is
    /// synthesised — `context.db` stores speech, not summaries, and the app the sound came through
    /// is not a title.
    ///
    /// **A session that is merely *waiting* to be uploaded never reaches this initialiser.** It has
    /// no title for the same reason as the rest, but the reason is temporary and the string is not:
    /// see `ActivityComposer.merge`, which leaves it out of the stream until the account has titled
    /// it, rather than drawing "Untitled conversation" over a conversation that simply has not been
    /// uploaded yet.
    ///
    /// **The window is derived from `durationSeconds`, not from `endedAt`.** A session that is still
    /// open has no `endedAt`, but it does have a last line, and `Queries.sessions` already resolves
    /// that into a duration. Reading `endedAt` directly would make a live conversation a *point* on
    /// the clock: it would attach none of the frames captured while it was happening, which is
    /// exactly the conversation a reader is most likely to be looking at.
    init(session: SessionSummary) {
        self.init(
            id: ActivityConversation.localID(session.id),
            source: .local,
            title: ActivityConversation.untitled,
            startedAt: Date(timeIntervalSince1970: session.startedAt),
            duration: session.durationSeconds,
            segmentCount: session.lineCount,
            matchable: "\(session.appHint ?? "") \(session.preview)")
    }

    /// A local session's identity in the merged stream. Prefixed so a session id and an account id
    /// can never collide on a surface that now holds both.
    static func localID(_ sessionID: Int64) -> String { "local:\(sessionID)" }

    /// The same conversation, told what the composer worked out about it.
    func counted(memoryCount: Int = 0, momentCount: Int = 0) -> ActivityConversation {
        ActivityConversation(
            id: id, source: source, title: title, emoji: emoji, startedAt: startedAt,
            duration: duration, segmentCount: segmentCount, overview: overview,
            matchable: matchable, memoryCount: memoryCount, momentCount: momentCount)
    }

    /// The end of the conversation's window on the clock — and **the same window the frames attach
    /// inside of**.
    var finishedAt: Date { startedAt.addingTimeInterval(duration) }

    /// "8m 9s · 2 memories · 6 screen moments" — the shipping app's clause set, in its order, and
    /// each clause is dropped when its count is zero rather than shown as "0 memories", which reads
    /// as a defect rather than as an absence. With every clause gone the line falls back to the
    /// time, so a row is never blank.
    ///
    /// **Two clauses of the main app's are missing and only one of them is a choice.** Its
    /// `N tasks` cannot be stated here: `ActivityAccountTask` carries no conversation id, so no task
    /// on this surface is ever attributed to a conversation (see `ActivityComposer.composeDay`) and
    /// the count could only ever be zero. `N spoken lines` is the other direction — it is the one
    /// thing a local-only row knows about itself, and it stands in the slot the main app gives to
    /// tasks. An account row has no transcript of its own, so it never prints it.
    var subtitle: String {
        var parts: [String] = []
        if duration >= 1 { parts.append(ActivityFormat.duration(duration)) }
        if memoryCount > 0 {
            parts.append(ActivityFormat.plural(memoryCount, "memory", "memories"))
        }
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
    /// The conversation this fact came out of, when the account named one — and the only thing that
    /// can attach a memory to a row, because a timestamp cannot. See `ActivityAccountMemory`.
    let conversationID: String?

    init(id: String, text: String, timestamp: Date, conversationID: String? = nil) {
        self.id = id
        self.text = text
        self.timestamp = timestamp
        self.conversationID = conversationID
    }

    init(memory: ActivityAccountMemory) {
        self.init(
            id: memory.id, text: memory.content,
            timestamp: Date(timeIntervalSince1970: memory.at),
            conversationID: memory.conversationID)
    }
}

/// A memory's text, split where it repeats.
///
/// Memories are generated, and generated copy runs to a template: four in a row arrive as "Focused on
/// Omi App: …", "Focused on Omi: …", "Focused on Omi App: …", "Focused on Omi Memories: …". Set as
/// one sentence in the largest reading role this surface owns, the half that is the *same* every time
/// is the loudest thing on it, and the half that is actually this memory is what the eye gets to
/// last.
///
/// So the repeated half is presented as a quiet label over the sentence rather than as its opening
/// words. **Nothing is hidden and nothing is truncated:** `label` and `body` together are the whole
/// text less the colon that already separated them, and a memory with no such prefix keeps its
/// sentence whole and has no label at all.
struct ActivityMemoryCopy: Equatable, Sendable {
    /// The words before the colon, or nil when the text is a plain sentence.
    let label: String?
    /// The rest of it — and the whole of it when there is no label.
    let body: String
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
    ///
    /// **A strip's `total` is the count of real frames it stands for, not the tiles it drew** — see
    /// `ActivityComposer.momentRow`, which scales the sample back up. Before it did, this sum was
    /// denominated in *sampled* frames while `thingCount` above was denominated in real ones, and
    /// the corner compared the two: soloing `Rewind` over 2,845 captures that the chip excluded
    /// none of read "51 results · of 2,954 in everything Omi has kept". Observed in the render
    /// harness; the two halves of that sentence must always count the same unit.
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

    /// The longest prefix that still reads as a category rather than as the first clause of a
    /// sentence. Past this, splitting stops being a label and becomes a fold through the middle of
    /// the copy.
    static let maximumMemoryLabelCharacters = 48

    /// Splits a memory into its repeated category and the sentence that is actually about this
    /// memory.
    ///
    /// Deliberately conservative — a memory that is merely *a sentence containing a colon* keeps its
    /// sentence. Three things have to be true before the split happens, and each of them is a real
    /// memory this would otherwise mangle:
    ///
    /// - **A space after the colon.** `12:56` and `https://omi.me` both carry one and neither is a
    ///   category; a separator between a label and a sentence is always followed by a space.
    /// - **No sentence punctuation in the prefix.** "He asked Dr. Kim: …" is a sentence with a quote
    ///   in it, not a labelled one.
    /// - **A prefix under `maximumMemoryLabelCharacters`, and a body left over.** A long prefix is a
    ///   clause, and a memory that is *only* a prefix has nothing to be a label for.
    static func memoryCopy(_ text: String) -> ActivityMemoryCopy {
        let whole = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let colon = whole.firstIndex(of: ":") else {
            return ActivityMemoryCopy(label: nil, body: whole)
        }
        let label = whole[whole.startIndex..<colon].trimmingCharacters(in: .whitespacesAndNewlines)
        let rest = whole[whole.index(after: colon)...]
        let body = rest.trimmingCharacters(in: .whitespacesAndNewlines)
        guard rest.first?.isWhitespace == true,
            !label.isEmpty,
            !body.isEmpty,
            label.count <= maximumMemoryLabelCharacters,
            !label.contains(where: { ".?!".contains($0) })
        else {
            return ActivityMemoryCopy(label: nil, body: whole)
        }
        return ActivityMemoryCopy(label: label, body: body)
    }

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

    /// …and what it counts when the account did not answer.
    ///
    /// **The wide sentence is a claim, and while the account is silent it is false.** Three of the
    /// five kinds on this surface live in the account, so a signed-out, rate-limited or airgapped
    /// Mac is showing *half* the corpus — and the empty copy that would have said so is only ever
    /// reached when the stream is completely empty. On any Mac with screen capture on it never
    /// appears, so the panel quietly presented one half of the record under a line promising the
    /// whole of it. Naming the narrower scope is the smallest true thing this corner can say.
    static let localScope = "what this Mac has kept"

    /// Which of the two the corner is entitled to name. A reason is only ever recorded after a read
    /// really came back unreachable, so this cannot flicker to the narrow claim during the opening
    /// moments when nothing has answered yet.
    ///
    /// **It stays correct when `ActivityLocalMemories` fills the memory column from the Omi app's
    /// own database**, and that is not a coincidence — those rows are kept on this Mac, in
    /// `~/Library/Application Support/Omi`, exactly as the screen capture is. "What this Mac has
    /// kept" is the true description of both halves, so a surface reading its memories locally needs
    /// no third sentence here.
    static func scope(accountUnreachable reason: ActivityAccountUnreachableReason?) -> String {
        reason == nil ? scope : localScope
    }

    /// **The unit this corner is denominated in, and it is deliberately not "moments".**
    ///
    /// The number is `ActivityDay.thingCount` summed — screen moments *plus* conversations,
    /// memories and tasks — and this line said "moments", the word the day header a hundred points
    /// below it uses for screen frames alone. The render harness caught the two side by side:
    /// `1,213 moments in everything Omi has kept` over `TODAY · 1,204 moments · 3 conversations ·
    /// 3 memories · 3 tasks`. One word, two counts, one screen. "Things" is the only noun true of
    /// all four kinds, and it is the word the model itself uses (`thingCount`).
    static func unit(_ count: Int) -> String { count == 1 ? "thing" : "things" }

    /// - Parameter isSettled: whether `total` is a finished count. The day walk fills older days in
    ///   behind an already-readable list, so the number climbs under the reader — it says so instead
    ///   of presenting a moving figure as a settled one.
    /// - Parameter scope: what the number is a count *of* — see `scope(accountUnreachable:)`.
    static func sentence(
        matching: Int, total: Int, isFiltering: Bool, isSettled: Bool, scope: String = scope
    ) -> String {
        guard isFiltering else {
            guard isSettled else { return "\(number(total)) so far · still counting \(scope)" }
            return "\(number(total)) \(unit(total)) in \(scope)"
        }
        return "\(number(matching)) result\(matching == 1 ? "" : "s") · of \(number(total)) in \(scope)"
    }

    /// What the corner says before anything has been counted. Not a confident zero: nothing has been
    /// read yet, and a zero is a claim about the machine.
    static let counting = "Counting what you've captured…"

    /// …and what it says once the count *has* finished and the answer really is nothing.
    ///
    /// **`corpusTotal` is nil for both, which is how this corner got stuck.** An empty stream leaves
    /// it nil forever, so on a Mac that has genuinely captured nothing the corner went on saying
    /// "Counting what you've captured…" for the rest of the session — directly opposite a body
    /// reading "Nothing captured in this window yet." One surface, two contradictory claims about
    /// the same read, side by side in the render harness. `corpusSettled` is what tells them apart.
    static let nothingYet = "Nothing captured yet"

    /// Grouped digits, because the count is routinely five figures and an ungrouped one is unreadable
    /// at a glance — which is the only way this line is ever read.
    static func number(_ value: Int) -> String { ActivityFormat.number(value) }
}
