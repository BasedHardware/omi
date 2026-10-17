import Foundation
import OmiCore

/// Home's tasks, condensed (docs/CHAT-FIRST.md): only what is the user's to do, the same task
/// heard in several conversations as one card, ranked, and only the ones that matter now. Pure
/// rules on the client; the daily AI tidy-up (`TaskTidyUp`) proposes the rest. English and German.
public enum TaskConsolidation {
    /// One card's tasks: the one kept and the duplicates merged into it.
    public struct Group: Identifiable, Equatable, Sendable {
        public let task: ActionItem
        public let duplicates: [ActionItem]

        public var id: String { task.id }
        public var all: [ActionItem] { [task] + duplicates }
        public var ids: [String] { all.map(\.id) }

        /// Distinct source conversations, the kept task's first ("From 2 conversations").
        public var conversationIDs: [String] {
            var seen = Set<String>()
            return all.compactMap(\.conversationID).filter { seen.insert($0).inserted }
        }

        /// The earliest due date among the merged tasks that the backend is reasonably sure of.
        public var dueAt: Date? {
            all.filter { ($0.dueConfidence ?? 1) >= TaskConsolidation.minimumDueConfidence }.compactMap(\.dueAt).min()
        }

        public var priority: ActionItem.Priority? {
            all.contains { $0.priority == .high } ? .high : task.priority
        }

        public init(task: ActionItem, duplicates: [ActionItem] = []) {
            self.task = task
            self.duplicates = duplicates
        }
    }

    /// One "Needs you" task card.
    public struct Card: Identifiable, Equatable, Sendable {
        public enum Kicker: Equatable, Sendable {
            case overdue, dueToday
            /// Due tomorrow or the day after.
            case dueSoon(Date)
            /// Someone waits on the user (blocked, a reply owed).
            case waiting
            /// Omi or the backend picked it (`What matters now`, the tidy-up's important list).
            case suggestion
        }

        public let group: Group
        public let kicker: Kicker
        /// The backend's "What matters now" pick for this task, when there is one.
        public let recommendation: Recommendation?
        /// "Later" was tapped: hidden from Needs you until then.
        public let snoozedUntil: Date?

        public var task: ActionItem { group.task }
        public var id: String { group.id }

        public init(group: Group, kicker: Kicker, recommendation: Recommendation? = nil, snoozedUntil: Date? = nil) {
            self.group = group
            self.kicker = kicker
            self.recommendation = recommendation
            self.snoozedUntil = snoozedUntil
        }
    }

    /// What ranks a task besides its own fields.
    public struct Signals: Sendable {
        /// Tasks the backend's "What matters now" or the tidy-up marked important.
        public var picks: Set<String>
        /// Tasks someone waits on (a recommendation that says so).
        public var waiting: Set<String>
        /// Tasks Omi already works on (any run, a workstream): their run shows instead.
        public var handled: Set<String>
        /// Tasks Omi is running right now from their card: the card stays (in place, "Omi is on
        /// it") although a refresh gives the task a workstream mid-run.
        public var running: Set<String>
        /// Task id → "Later" until.
        public var snoozes: [String: Date]
        /// Task id → the words it was extracted from (`ConversationsStore.quote`), when loaded.
        public var quotes: [String: String]
        public var now: Date
        public var calendar: Calendar

        public init(
            picks: Set<String> = [], waiting: Set<String> = [], handled: Set<String> = [], running: Set<String> = [],
            snoozes: [String: Date] = [:], quotes: [String: String] = [:], now: Date = .now, calendar: Calendar = .current
        ) {
            self.picks = picks
            self.waiting = waiting
            self.handled = handled
            self.running = running
            self.snoozes = snoozes
            self.quotes = quotes
            self.now = now
            self.calendar = calendar
        }
    }

    /// Below this the backend guessed the due date; it does not make a task urgent.
    public static let minimumDueConfidence = 0.4
    /// Token overlap from which two tasks with the same verb are one.
    public static let duplicateThreshold = 0.6

    // MARK: Cards

    /// The tasks that matter now, ranked (`active`), and the ones the user put off (`snoozed`,
    /// soonest back first). `recommendations` with a task become that task's card.
    public static func cards(
        _ tasks: [ActionItem], recommendations: [Recommendation] = [], signals: Signals
    ) -> (active: [Card], snoozed: [Card]) {
        // A request the user made of someone else (an assistant, a colleague) stays in All tasks.
        let own = tasks.filter { isCandidate($0) && !isRequestToSomeoneElse($0.description, quote: signals.quotes[$0.id]) }
        let groups = groups(own).filter { group in
            !group.all.contains { task in
                signals.handled.contains(task.id) || (task.workstreamID != nil && !signals.running.contains(task.id))
            }
        }
        var byTask: [String: Recommendation] = [:]
        for recommendation in recommendations {
            if let id = recommendation.taskID, byTask[id] == nil { byTask[id] = recommendation }
        }
        var active: [(card: Card, key: RankKey)] = []
        var snoozed: [Card] = []
        for group in groups {
            let recommendation = group.ids.lazy.compactMap { byTask[$0] }.first
            let key = rankKey(group, recommended: recommendation != nil, signals: signals)
            let until = group.ids.compactMap { signals.snoozes[$0] }.filter { $0 > signals.now }.max()
            if let until {
                snoozed.append(Card(group: group, kicker: key.kicker, recommendation: recommendation, snoozedUntil: until))
            } else if key.isImportant {
                active.append((Card(group: group, kicker: key.kicker, recommendation: recommendation), key))
            }
        }
        let ranked = active.sorted { $0.key < $1.key }.map(\.card)
        // The backend's own picks lead (Home: Omi asks, finished runs, What matters now, then tasks).
        let picked = ranked.filter { $0.recommendation != nil }
        let comingBack = snoozed.sorted { ($0.snoozedUntil ?? .distantFuture) < ($1.snoozedUntil ?? .distantFuture) }
        return (picked + ranked.filter { $0.recommendation == nil }, comingBack)
    }

    // MARK: Hiding

    /// Something for the user to do: open, theirs, and a real task rather than a stray phrase.
    public static func isCandidate(_ task: ActionItem) -> Bool {
        guard task.isOpen, task.owner != .other else { return false }
        if TakeOverEligibility.looksLikeSomeoneElses(task.description) { return false }
        return !isFragment(task.description)
    }

    /// Clearly not actionable: one word, a few letters, filler from speech ("um", "yeah so"), a
    /// sentence cut off mid-way.
    public static func isFragment(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let words = words(trimmed)
        guard words.count >= 2, trimmed.filter(\.isLetter).count >= 6 else { return true }
        if fillers.contains(words[0]) { return true }
        return trimmed.hasSuffix("...") || trimmed.hasSuffix("…")
    }

    /// Said to someone else in the second person ("Kannst du dir mal das Transkript ziehen …",
    /// "Could you send me the deck"): the other person's job, often an assistant on a laptop.
    /// Unless the user said it about himself ("can you remind me", "ich muss …").
    public static func isRequestToSomeoneElse(_ text: String, quote: String?) -> Bool {
        let spoken = " " + words([quote ?? "", text].joined(separator: " ")).joined(separator: " ") + " "
        guard requestPhrases.contains(where: { spoken.contains(" \($0) ") }) else { return false }
        return !selfPhrases.contains { spoken.contains(" \($0) ") }
    }

    /// The due date that makes a task urgent: none when the backend guessed it (low confidence) or
    /// filled in the end of the day it was heard ("23:59" on its creation day) with no time said.
    public static func deadline(_ task: ActionItem, quote: String?, calendar: Calendar) -> Date? {
        guard let due = task.dueAt, (task.dueConfidence ?? 1) >= minimumDueConfidence else { return nil }
        let time = calendar.dateComponents([.hour, .minute], from: due)
        let endOfDay = time.hour == 23 && time.minute == 59
        guard endOfDay, let created = task.createdAt, calendar.isDate(due, inSameDayAs: created) else { return due }
        let spoken = " " + words([quote ?? "", task.description].joined(separator: " ")).joined(separator: " ") + " "
        return timePhrases.contains { spoken.contains(" \($0) ") } ? due : nil
    }

    // MARK: Duplicates

    /// Tasks merged where they say the same thing: same verb and at least `duplicateThreshold`
    /// token overlap (Jaccard). The kept task is the most useful one: due date, high priority,
    /// then the first heard. Order follows the input.
    public static func groups(_ tasks: [ActionItem]) -> [Group] {
        var buckets: [[ActionItem]] = []
        var signatures: [Signature] = []
        for task in tasks {
            let signature = Signature(task.description)
            if let index = signatures.firstIndex(where: { $0.matches(signature) }) {
                buckets[index].append(task)
            } else {
                buckets.append([task])
                signatures.append(signature)
            }
        }
        return buckets.map { members in
            let kept = members.min(by: keepsBefore) ?? members[0]
            return Group(task: kept, duplicates: members.filter { $0.id != kept.id })
        }
    }

    public static func isDuplicate(_ lhs: String, _ rhs: String) -> Bool {
        Signature(lhs).matches(Signature(rhs))
    }

    /// Token Jaccard similarity of two task texts (stop words dropped, light stemming).
    public static func similarity(_ lhs: String, _ rhs: String) -> Double {
        Signature(lhs).similarity(Signature(rhs))
    }

    private static func keepsBefore(_ lhs: ActionItem, _ rhs: ActionItem) -> Bool {
        if (lhs.dueAt == nil) != (rhs.dueAt == nil) { return lhs.dueAt != nil }
        if (lhs.priority == .high) != (rhs.priority == .high) { return lhs.priority == .high }
        let (left, right) = (lhs.createdAt ?? .distantFuture, rhs.createdAt ?? .distantFuture)
        return left != right ? left < right : lhs.id < rhs.id
    }

    struct Signature {
        let verb: String
        let tokens: Set<String>

        init(_ text: String) {
            let all = TaskConsolidation.words(text)
            // "Leo unblocks the firmware release": the verb is the second word.
            let verbIndex = TakeOverEligibility.looksLikeSomeoneElses(text) && all.count > 1 ? 1 : 0
            verb = all.indices.contains(verbIndex) ? TaskConsolidation.stem(all[verbIndex]) : ""
            tokens = Set(all.filter { !TaskConsolidation.stopWords.contains($0) }.map(TaskConsolidation.stem))
        }

        func similarity(_ other: Signature) -> Double {
            let union = tokens.union(other.tokens)
            guard !union.isEmpty else { return 0 }
            return Double(tokens.intersection(other.tokens).count) / Double(union.count)
        }

        func matches(_ other: Signature) -> Bool {
            !verb.isEmpty && verb == other.verb && similarity(other) >= TaskConsolidation.duplicateThreshold
        }
    }

    // MARK: Ranking

    /// Lexicographic: overdue, someone waits, picked, due within two days, high priority, Omi
    /// can do it, then the newest.
    struct RankKey: Comparable {
        let overdue: Bool, waiting: Bool, picked: Bool, dueSoon: Bool, high: Bool, omiCan: Bool
        let created: Date
        let kicker: Card.Kicker
        let dueToday: Bool

        var isImportant: Bool { overdue || dueToday || dueSoon || waiting || picked || high }

        private var flags: [Int] { [overdue, waiting, picked, dueToday || dueSoon, high, omiCan].map { $0 ? 0 : 1 } }

        static func < (lhs: RankKey, rhs: RankKey) -> Bool {
            if lhs.flags != rhs.flags { return lhs.flags.lexicographicallyPrecedes(rhs.flags) }
            return lhs.created > rhs.created
        }

        static func == (lhs: RankKey, rhs: RankKey) -> Bool {
            lhs.flags == rhs.flags && lhs.created == rhs.created
        }
    }

    static func rankKey(_ group: Group, recommended: Bool, signals: Signals) -> RankKey {
        let calendar = signals.calendar
        let today = calendar.startOfDay(for: signals.now)
        let due = group.all.compactMap { deadline($0, quote: signals.quotes[$0.id], calendar: calendar) }.min()
        let overdue = due.map { $0 < today } ?? false
        let dueToday = due.map { calendar.isDate($0, inSameDayAs: signals.now) } ?? false
        let soonLimit = calendar.date(byAdding: .day, value: 3, to: today) ?? today
        let dueSoon = !overdue && !dueToday && (due.map { $0 < soonLimit } ?? false)
        let waiting = group.ids.contains { signals.waiting.contains($0) } || group.all.contains { someoneWaits($0.description) }
        let picked = recommended || group.ids.contains { signals.picks.contains($0) }
        let kicker: Card.Kicker = if overdue {
            .overdue
        } else if dueToday {
            .dueToday
        } else if waiting {
            .waiting
        } else if dueSoon, let due {
            .dueSoon(due)
        } else {
            .suggestion
        }
        return RankKey(
            overdue: overdue, waiting: waiting, picked: picked, dueSoon: dueSoon, high: group.priority == .high,
            omiCan: TakeOverEligibility.canTakeOver(group.task),
            created: group.all.compactMap(\.createdAt).max() ?? .distantPast, kicker: kicker, dueToday: dueToday
        )
    }

    /// The task itself says someone is waiting ("Reply to Anna", "Leo is blocked on …").
    static func someoneWaits(_ text: String) -> Bool {
        let text = " " + words(text).joined(separator: " ") + " "
        return waitingPhrases.contains { text.contains(" \($0) ") }
    }

    // MARK: Words

    static func words(_ text: String) -> [String] {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .replacingOccurrences(of: "e-mail", with: "email")
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
    }

    /// Plural and conjugation endings, so "unblocks" meets "unblock" and "schicke" meets "schick".
    static func stem(_ word: String) -> String {
        var word = word
        if word.count > 5, word.hasSuffix("en") {
            word.removeLast(2)
        } else if word.count > 3, word.hasSuffix("s"), !word.hasSuffix("ss") {
            word.removeLast()
        }
        if word.count > 4, word.hasSuffix("e") { word.removeLast() }
        return word
    }

    static let stopWords: Set<String> = [
        "the", "a", "an", "to", "for", "of", "and", "or", "with", "on", "in", "at", "by", "from", "my", "our", "your",
        "his", "her", "their", "this", "that", "it", "is", "be", "about", "up", "out", "some", "all",
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "und", "oder", "mit", "fur",
        "zu", "zum", "zur", "an", "am", "auf", "im", "von", "vom", "bei", "mein", "meine", "meinen", "dein", "deine",
    ]

    /// Speech filler a real task never starts with.
    static let fillers: Set<String> = [
        "um", "uh", "uhm", "hmm", "yeah", "yep", "okay", "ok", "and", "but", "because", "so",
        "ahm", "ah", "ja", "und", "aber", "weil", "oder", "naja",
    ]

    /// A request to the listener (folded: "könntest" is "konntest").
    static let requestPhrases: [String] = [
        "can you", "could you", "would you", "will you", "can u", "please",
        "kannst du", "kannst dir", "kannst mir", "konntest du", "wurdest du",
        "konnen sie", "konnten sie", "wurden sie", "bitte",
    ]

    /// The user speaking about himself: still his own task.
    static let selfPhrases: [String] = [
        "remind me", "i need to", "i have to", "i should", "i must", "i will", "i ll", "i want to", "i m going to",
        "erinnere mich", "erinner mich", "ich muss", "ich sollte", "ich will", "ich werde", "ich mochte", "ich mach",
    ]

    /// A time of day said out loud, which makes "by the end of today" a real deadline.
    static let timePhrases: [String] = [
        "today", "tonight", "this evening", "end of day", "eod", "midnight", "right now", "asap",
        "heute", "heute abend", "heute nacht", "noch heute", "bis heute", "mitternacht", "tagesende", "sofort", "jetzt",
    ]

    static let waitingPhrases: [String] = [
        "waiting", "waits", "waiting on", "blocked", "blocking", "reply to", "respond to", "get back to", "owe",
        "wartet", "warten", "blockiert", "antworte", "zuruckmelden", "melde dich",
    ]
}
