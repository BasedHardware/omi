import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Needs you: the long-press menus, feedback to the backend and the small helpers the cards share.
extension NeedsYouSection {
    @ViewBuilder
    func menu(for item: HomeAttention.Item) -> some View {
        switch item {
        case .speakerPrompt:
            Button { Task { await voices.dismissPrompts() } } label: { Label(L("dismiss"), systemImage: "xmark") }
        case let .nudge(nudge):
            Button { send(.helpful, nudge) } label: {
                Label(
                    L("helpful"),
                    systemImage: nudge.feedback == ForYouItem.Feedback.helpful.rawValue ? "hand.thumbsup.fill" : "hand.thumbsup"
                )
            }
            Button { send(.notHelpful, nudge) } label: {
                Label(
                    L("notHelpful"),
                    systemImage: nudge.feedback == ForYouItem.Feedback.notHelpful.rawValue ? "hand.thumbsdown.fill" : "hand.thumbsdown"
                )
            }
            Divider()
            Button { send(.dismissed, nudge) } label: { Label(L("dismiss"), systemImage: "xmark") }
            Button(role: .destructive) { send(.stopThese, nudge) } label: { Label(L("stopThese"), systemImage: "bell.slash") }
        case .siriTip:
            Button { siriTipDismissed = true } label: { Label(L("dismiss"), systemImage: "xmark") }
        case let .recommendation(recommendation):
            Button { decide(recommendation, .alreadyHandled) } label: {
                Label(L("nativeForYouAlreadyHandled"), systemImage: "checkmark.seal")
            }
            Button { decide(recommendation, .later) } label: { Label(L("nativeForYouLater"), systemImage: "clock") }
            Divider()
            Button { decide(recommendation, .dismiss) } label: { Label(L("notNow"), systemImage: "xmark") }
        default:
            EmptyView()
        }
    }

    func appeared(_ item: HomeAttention.Item) async {
        switch item {
        case let .nudge(nudge): forYou?.markShown(nudge)
        // The card is the prompt on screen: starts the backend's daily cooldown.
        case .speakerPrompt: await voices.promptsShown()
        default: break
        }
    }

    func task(_ id: String) -> ActionItem? {
        tasks.tasks.first { $0.id == id }
    }

    /// A suggestion without a task: the backend's reason when specific, then where it comes from.
    func contextLines(for item: HomeAttention.Item, content: ForYouRow.Content) -> (subtitle: String, source: String?) {
        guard case let .recommendation(recommendation) = item else { return (content.subtitle, nil) }
        let source = TaskCardWording.origin(recommendation)
        if let reason = recommendation.specificWhyNow { return (reason, source) }
        return (source ?? "", nil)
    }

    func send(_ feedback: ForYouItem.Feedback, _ nudge: ForYouItem) {
        DSHaptics.selection()
        Task { await forYou?.send(feedback, for: nudge) }
    }

    func open(_ nudge: ForYouItem) {
        Task { await forYou?.send(.opened, for: nudge) }
        switch nudge.target {
        case let .conversation(id): onOpenConversation(id)
        // A task opens the conversation it came from.
        case let .task(id): if let source = task(id)?.conversationID { onOpenConversation(source) }
        case nil: break
        }
    }

    func decide(_ recommendation: Recommendation, _ decision: Recommendation.Decision) {
        DSHaptics.selection()
        Task { await agent.decide(recommendation, decision) }
    }

    func resume(_ task: ActionItem) {
        DSHaptics.tap(.medium)
        Task { await agent.resume(task, conversationTitle: conversations.source(of: task)?.title) }
    }

    /// `-omiHomeStartFirst YES`: the first task card Omi can take over gets its magic button
    /// pressed, to see the running state without a tap.
    func debugStartFirstCard() async {
        #if DEBUG
            guard DebugLaunch.flag("omiHomeStartFirst") else { return }
            for _ in 0 ..< 60 {
                let cards = HomeAttention.inbox(input).needsYou.compactMap { item -> TaskConsolidation.Card? in
                    if case let .task(card) = item, agent.canTakeOver(card.task) { card } else { nil }
                }
                if let card = cards.first {
                    start(card)
                    return
                }
                try? await Task.sleep(for: .milliseconds(250))
            }
        #endif
    }
}
