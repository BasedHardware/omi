import Foundation
import OmiCore
import OmiNetwork

/// Where tapping a Home card goes. Every card goes somewhere (no dead taps): a task opens its
/// detail, a run its progress or result, a suggestion its task or conversation (or the chat,
/// asked about it), the tidy-up its review. The card's pills keep their own actions.
public enum HomeTapTargets {
    public enum Target: Equatable, Sendable {
        /// Omi's run on this task (progress, question, result).
        case run(String)
        /// Unfolds Later (several finished runs).
        case later
        case speakerPrompt
        case siriTip
        case conversation(String)
        /// The task's detail sheet.
        case task(String)
        /// The Chat tab with this question in the composer.
        case ask(String)
        case tidyUp
        /// The connect flow for this integration.
        case connect(String)
    }

    public static func target(_ item: HomeAttention.Item) -> Target {
        switch item {
        case .tidyUp: .tidyUp
        case let .omiAsks(pending): .run(pending.taskID)
        case let .finished(run), let .working(run), let .needsHelp(run): .run(run.id)
        case .finishedGroup: .later
        case let .recommendation(recommendation): target(recommendation)
        case let .task(card): .task(card.task.id)
        case .speakerPrompt: .speakerPrompt
        case let .nudge(nudge):
            switch nudge.target {
            case let .conversation(id): .conversation(id)
            case let .task(id): .task(id)
            case nil: .ask(nudge.title)
            }
        case .siriTip: .siriTip
        case let .connect(id): .connect(id)
        }
    }

    private static func target(_ recommendation: Recommendation) -> Target {
        if let task = recommendation.taskID { return .task(task) }
        if let conversation = recommendation.conversationIDs.first { return .conversation(conversation) }
        return .ask(recommendation.action.isEmpty ? recommendation.headline : recommendation.action)
    }
}
