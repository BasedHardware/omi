import Foundation
import OmiCore
import OmiNetwork

/// Home's "Needs you" (docs/CHAT-FIRST.md): at most `needsYouLimit` cards in a fixed order (the
/// day's tidy-up, Omi asks, finished runs to review, What matters now, the condensed important
/// tasks, one connection), and "Later" for everything else that wants attention some time (put
/// off tasks, overflow, Omi's running work without a card, tips). Pure, so the order is testable.
public enum HomeAttention {
    public enum Item: Identifiable, Equatable, Sendable {
        /// The daily AI tidy-up's suggestion ("Tidy up: merge 6, mark 4 done").
        case tidyUp(TaskTidyUp.Proposal)
        /// Omi is waiting on the user mid-run ("Omi asks"): first, since the run waits for it.
        case omiAsks(PendingDeviceTool)
        /// A finished run the user has not opened yet.
        case finished(AgentStore.Run)
        /// Several finished runs as one card ("Omi finished 3 tasks"); each is in Later too.
        case finishedGroup([AgentStore.Run])
        case working(AgentStore.Run)
        /// A backend recommendation ("What matters now") without a task of its own.
        case recommendation(Recommendation)
        /// A condensed task card (duplicates merged, ranked; `TaskConsolidation`).
        case task(TaskConsolidation.Card)
        /// A run Omi could not finish: the user takes it from here.
        case needsHelp(AgentStore.Run)
        case speakerPrompt(SpeakerPrompt)
        case nudge(ForYouItem)
        /// "Ask Omi with Siri", until tapped or dismissed.
        case siriTip
        /// "Connect Google Calendar?": a connection Omi works better with (calendar, mail, health),
        /// offered one at a time while the account is new.
        case connect(String)

        public var id: String {
            switch self {
            case .tidyUp: "tidyup"
            case let .omiAsks(pending): "asks.\(pending.id)"
            case let .finished(run): "finished.\(run.id)"
            case .finishedGroup: "finished"
            case let .working(run): "working.\(run.id)"
            case let .recommendation(recommendation): "recommendation.\(recommendation.id)"
            case let .task(card): "task.\(card.id)"
            case let .needsHelp(run): "help.\(run.id)"
            case let .speakerPrompt(prompt): "speaker.\(prompt.id)"
            case let .nudge(item): "nudge.\(item.id)"
            case .siriTip: "siri"
            case let .connect(id): "connect.\(id)"
            }
        }
    }

    /// Cards in "Needs you", hard.
    public static let needsYouLimit = 5
    /// Backend recommendations without a task taken at most (the rest wait for the next refresh).
    public static let maxRecommendations = 2

    public struct Input: Sendable {
        public var runs: [AgentStore.Run]
        /// Device tool calls waiting for the user (`AgentStore.pendingDeviceTools`).
        public var asks: [PendingDeviceTool]
        public var openedRunIDs: Set<String>
        public var recommendations: [Recommendation]
        /// Every task (`TasksStore.tasks`); the cards come from `TaskConsolidation`.
        public var tasks: [ActionItem]
        /// Task id → "Later" until.
        public var snoozes: [String: Date]
        /// Task id → the words it was extracted from, when its conversation is loaded.
        public var quotes: [String: String]
        /// The tidy-up's suggestion, when it has changes; its `important` list ranks tasks.
        public var tidyUp: TaskTidyUp.Proposal?
        public var speakerPrompt: SpeakerPrompt?
        public var nudges: [ForYouItem]
        public var showsSiriTip: Bool
        /// Connections to suggest, most useful first (Home shows the first).
        public var connect: [String]
        public var now: Date
        public var calendar: Calendar

        public init(
            runs: [AgentStore.Run] = [], asks: [PendingDeviceTool] = [], openedRunIDs: Set<String> = [],
            recommendations: [Recommendation] = [], tasks: [ActionItem] = [], snoozes: [String: Date] = [:],
            quotes: [String: String] = [:], tidyUp: TaskTidyUp.Proposal? = nil, speakerPrompt: SpeakerPrompt? = nil,
            nudges: [ForYouItem] = [],
            showsSiriTip: Bool = false, connect: [String] = [], now: Date = .now, calendar: Calendar = .current
        ) {
            self.runs = runs
            self.asks = asks
            self.openedRunIDs = openedRunIDs
            self.recommendations = recommendations
            self.tasks = tasks
            self.snoozes = snoozes
            self.quotes = quotes
            self.tidyUp = tidyUp
            self.speakerPrompt = speakerPrompt
            self.nudges = nudges
            self.showsSiriTip = showsSiriTip
            self.connect = connect
            self.now = now
            self.calendar = calendar
        }
    }

    public struct Inbox: Equatable, Sendable {
        public var needsYou: [Item]
        public var later: [Item]

        public var isEmpty: Bool { needsYou.isEmpty && later.isEmpty }
    }

    public static func inbox(_ input: Input) -> Inbox {
        let runs = input.runs.sorted { $0.startedAt > $1.startedAt }
        var ranked: [Item] = []
        if let tidyUp = input.tidyUp, !tidyUp.isEmpty { ranked.append(.tidyUp(tidyUp)) }
        ranked += input.asks.map(Item.omiAsks)

        // Finished runs to review: two or more fold into one card, each one waits in Later.
        let finished = runs.filter { run in
            if case .done = run.state { !input.openedRunIDs.contains(run.id) } else { false }
        }
        var later: [Item] = []
        if finished.count > 1 {
            ranked.append(.finishedGroup(finished))
            later += finished.map(Item.finished)
        } else {
            ranked += finished.map(Item.finished)
        }
        for run in runs {
            if case .failed = run.state { ranked.append(.needsHelp(run)) }
        }

        // What matters now, then the condensed tasks (a recommendation with a task is that task's card).
        // A task Omi is running keeps its card (and the recommendation Home held for it, so its
        // rank holds) until the run ends; then its run card takes over.
        let running = Set(input.runs.filter(\.isActive).map(\.id))
        let runIDs = Set(input.runs.map(\.id)).subtracting(running)
        let taskIDs = Set(input.tasks.map(\.id))
        let recommendations = input.recommendations.filter { $0.taskID.map { !runIDs.contains($0) } ?? true }
        let cards = TaskConsolidation.cards(
            input.tasks, recommendations: recommendations.filter { $0.taskID.map(taskIDs.contains) ?? false },
            signals: TaskConsolidation.Signals(
                picks: Set(input.tidyUp?.important ?? []),
                waiting: Set(recommendations.filter { $0.origin == .waitingOnYou }.compactMap(\.taskID)),
                handled: runIDs, running: running, snoozes: input.snoozes, quotes: input.quotes, now: input.now,
                calendar: input.calendar
            )
        )
        let carded = Set((cards.active + cards.snoozed).flatMap(\.group.ids))
        let picks = cards.active.filter { $0.recommendation != nil }
        ranked += picks.map(Item.task)
        // A recommendation whose task is not loaded (or has none) stays a suggestion of its own.
        ranked += recommendations.filter { $0.taskID.map { !taskIDs.contains($0) } ?? true }
            .prefix(maxRecommendations).map(Item.recommendation)
        ranked += cards.active.filter { $0.recommendation == nil }.map(Item.task)
        if let first = input.connect.first { ranked.append(.connect(first)) }

        let needsYou = Array(ranked.prefix(needsYouLimit))
        later = Array(ranked.dropFirst(needsYouLimit)) + cards.snoozed.map(Item.task) + later
        // A run that waits on the user shows as its question, not as "working" too; one whose task
        // has a card shows on that card.
        let asking = Set(input.asks.map(\.taskID))
        later += runs.filter { $0.isActive && !asking.contains($0.id) && !carded.contains($0.id) }.map(Item.working)
        if let prompt = input.speakerPrompt { later.append(.speakerPrompt(prompt)) }
        later += input.nudges.map(Item.nudge)
        if input.showsSiriTip { later.append(.siriTip) }
        return Inbox(needsYou: needsYou, later: later)
    }
}
