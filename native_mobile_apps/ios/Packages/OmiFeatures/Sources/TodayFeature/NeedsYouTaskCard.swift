import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// A task on Home (`TaskCardView`, docs HOME_TASK_CARD.md): its picture, the task, why now and
/// where it came from; the round button lets Omi start at once (or marks it done), swipe right
/// for "Later" (with undo). Long press for the rest, including "Not a task" (the learning signal).
extension NeedsYouSection {
    func taskCard(_ card: TaskConsolidation.Card) -> some View {
        let task = card.task
        let omiCan = agent.canTakeOver(task)
        let running = agent.runs[task.id]?.isActive == true
        let conversation = conversations.source(of: task)
        let status = running
            ? TaskCardView.Status(text: L("nativeOmiOnIt"), color: DS.Palette.agent, pulses: true)
            : TaskCardWording.status(card)
        return TaskCardView(
            visual: EntityVisual.forTask(task, source: conversation),
            fallback: EntityVisual.quiet(conversation),
            title: task.description,
            status: status,
            source: source(card),
            answer: running ? .running : omiCan ? .omiTakesOver : .markDone,
            // The task's own screen; while Omi works, the run's progress.
            onTap: { running ? onHandOver(task) : onOpenTask(task) },
            onButton: {
                if running { onHandOver(task) } else if omiCan { start(card) } else { complete(card) }
            },
            onLater: card.snoozedUntil == nil && !running ? { swipedLater(card) } : nil
        )
        .contextMenu { taskMenu(card, omiCan: omiCan) }
        .accessibilityIdentifier("forYou.task.\(task.id)")
    }

    @ViewBuilder
    private func taskMenu(_ card: TaskConsolidation.Card, omiCan: Bool) -> some View {
        Button { complete(card) } label: { Label(L("nativeMarkDone"), systemImage: "checkmark.circle") }
        if omiCan {
            Button { takeOver(card) } label: { Label(L("nativeOmiTakesOver"), systemImage: "sparkles") }
        }
        if card.snoozedUntil == nil {
            Button { later(card) } label: { Label(L("nativeForYouLater"), systemImage: "clock") }
        } else {
            Button { withAnimation(DS.Motion.standard) { tasks.unsnooze(card.group.ids) } } label: {
                Label(L("nativeForYouBackToNeedsYou"), systemImage: "arrow.uturn.up")
            }
        }
        if let id = conversationID(card) {
            Button { onOpenConversation(id) } label: { Label(L("openConversation"), systemImage: "text.bubble") }
        }
        Divider()
        Button(role: .destructive) { notTask(card) } label: { Label(L("nativeNotATask"), systemImage: "xmark.circle") }
    }

    /// "Pricing sync · Wed", or "Pricing sync +1" for a card merged from two conversations.
    private func source(_ card: TaskConsolidation.Card) -> String? {
        let ids = card.group.conversationIDs
        let sources = card.group.all.compactMap { conversations.source(of: $0) }
        let first = ids.lazy.compactMap { id in sources.first { $0.id == id } }.first
        if let first, ids.count > 1 { return "\(first.displayTitle) +\(ids.count - 1)" }
        if let first {
            return "\(first.displayTitle) · \(first.createdAt.formatted(.dateTime.weekday(.abbreviated)))"
        }
        return card.recommendation.flatMap(TaskCardWording.origin)
    }

    private func conversationID(_ card: TaskConsolidation.Card) -> String? {
        card.group.conversationIDs.first
    }

    /// "Omi takes over" from the menu: the hand-over sheet, to read what Omi will do first.
    private func takeOver(_ card: TaskConsolidation.Card) {
        if agent.runs[card.task.id]?.isActive != true {
            hold(card)
            if let recommendation = card.recommendation { decide(recommendation, .doNow) }
        }
        onHandOver(card.task)
    }

    /// The magic button: Omi starts right away, the same start as the hand-over sheet's; the card
    /// stays (spinning) until the run's own card replaces it.
    func start(_ card: TaskConsolidation.Card) {
        DSHaptics.success()
        hold(card)
        let task = card.task
        let title = conversations.source(of: task)?.title
        Task {
            if let recommendation = card.recommendation { await agent.decide(recommendation, .doNow) }
        }
        Task { await agent.takeOver(task, conversationTitle: title) }
    }

    /// `doNow` drops the card's recommendation; Home feeds it back while the run is on, so the
    /// card keeps its place.
    private func hold(_ card: TaskConsolidation.Card) {
        if let recommendation = card.recommendation { heldRecommendations[card.task.id] = recommendation }
    }

    private func complete(_ card: TaskConsolidation.Card) {
        DSHaptics.success()
        if let recommendation = card.recommendation { decide(recommendation, .complete) }
        Task { await tasks.complete(card.group.ids) }
    }

    /// Off Home until tomorrow; the due date stays as it is.
    private func later(_ card: TaskConsolidation.Card) {
        DSHaptics.selection()
        if let recommendation = card.recommendation { decide(recommendation, .later) }
        withAnimation(DS.Motion.standard) { tasks.snooze(card.group.ids) }
    }

    /// The swipe: as "Later", with "Moved to Later · Undo" at the bottom.
    private func swipedLater(_ card: TaskConsolidation.Card) {
        later(card)
        withAnimation(DS.Motion.standard) { laterUndo = LaterUndo(ids: card.group.ids) }
    }

    /// Cancelled on the backend: it disappears, and Omi learns this was no task.
    private func notTask(_ card: TaskConsolidation.Card) {
        DSHaptics.selection()
        if let recommendation = card.recommendation { decide(recommendation, .dismiss) }
        Task { await tasks.markNotTask(card.group.ids) }
    }
}

/// The words on a task card.
enum TaskCardWording {
    @MainActor
    static func status(_ card: TaskConsolidation.Card) -> TaskCardView.Status {
        if card.snoozedUntil != nil {
            return TaskCardView.Status(text: L("nativeForYouLater"), color: DS.Palette.inkSecondary)
        }
        switch card.kicker {
        case .overdue:
            return TaskCardView.Status(text: L("nativeOverdue"), color: DS.Palette.live)
        case .dueToday:
            return TaskCardView.Status(text: L("nativeForYouDueToday"), color: DS.Palette.warning)
        case let .dueSoon(date):
            return TaskCardView.Status(text: L("nativeForYouDueOn", day(date)), color: DS.Palette.inkSecondary)
        case .waiting:
            return TaskCardView.Status(text: L("nativeForYouSomeoneWaits"), color: DS.Palette.warning)
        case .suggestion:
            return TaskCardView.Status(text: L("nativeForYouSuggestion"), color: DS.Palette.agent)
        }
    }

    /// "tomorrow" or "Sat" after "Due".
    private static func day(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(date, inSameDayAs: tomorrow) {
            return L("nativeTomorrow").lowercased()
        }
        return date.formatted(.dateTime.weekday(.abbreviated))
    }

    /// Where a backend suggestion comes from when no conversation says it.
    @MainActor
    static func origin(_ recommendation: Recommendation) -> String? {
        var parts: [String] = []
        switch recommendation.origin {
        case .addedByYou: parts.append(L("nativeForYouAddedByYou"))
        case .waitingOnYou: parts.append(L("nativeForYouWaitingOnYou"))
        case let .text(text): parts.append(text)
        case nil: break
        }
        if let goal = recommendation.distinctGoalLabel { parts.append(goal) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// A card swiped to Later, while its undo is offered.
struct LaterUndo: Equatable {
    let id = UUID()
    let ids: [String]
}

/// "Moved to Later · Undo" after a swipe to Later, for a few seconds.
struct LaterUndoToast: View {
    @Environment(TasksStore.self) private var tasks
    @Binding var undo: LaterUndo?

    var body: some View {
        Group {
            if let current = undo {
                OmiToast(text: L("nativeMovedToLater"), systemImage: "clock", actionTitle: L("undo")) {
                    DSHaptics.tap()
                    withAnimation(DS.Motion.standard) {
                        tasks.unsnooze(current.ids)
                        undo = nil
                    }
                }
                .id(current.id)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .task(id: current.id) {
                    try? await Task.sleep(for: .seconds(4))
                    if undo == current { withAnimation(DS.Motion.standard) { undo = nil } }
                }
            }
        }
        .animation(DS.Motion.standard, value: undo)
    }
}
