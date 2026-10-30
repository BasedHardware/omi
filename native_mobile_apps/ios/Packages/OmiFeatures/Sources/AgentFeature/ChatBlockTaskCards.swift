import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

// MARK: - Task

/// A task the answer created or named, drawn live from the task list: tick it off here, or open it.
/// The tasks API has no read-by-id, so the card resolves against the loaded list and says so when
/// the row is not in it (Flutter `TaskCardBlock`).
struct TaskBlockCard: View {
    @Environment(TasksStore.self) private var tasks
    @Environment(\.openURL) private var openURL
    let block: ChatBlock
    let taskID: String
    @State private var isToggling = false

    var body: some View {
        if let task {
            loaded(task)
        } else if tasks.phase != .loaded {
            ChatBlockNotice(
                symbol: "checklist", label: L("chatBlockTask"), message: L("loading"),
                isLoading: true, identifier: "chat.block.task.\(block.id).loading"
            )
            .task { await tasks.load() }
        } else {
            ChatBlockNotice(
                symbol: "checklist", label: L("chatBlockTask"), message: L("chatBlockUnavailable"),
                identifier: "chat.block.task.\(block.id).unavailable"
            )
        }
    }

    private var task: ActionItem? {
        tasks.tasks.first { $0.id == taskID }
    }

    private func loaded(_ task: ActionItem) -> some View {
        ChatBlockCard(onTap: { open(task) }, content: {
            VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                ChatBlockEyebrow(symbol: "checklist", label: L("chatBlockTask"))
                HStack(spacing: DS.Spacing.sm) {
                    Button {
                        toggle(task)
                    } label: {
                        Image(systemName: task.isCompleted ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 20, weight: .regular))
                            .foregroundStyle(task.isCompleted ? DS.Palette.success : DS.Palette.inkSecondary)
                            .frame(width: 32, height: 32)
                    }
                    .buttonStyle(.plain)
                    .disabled(isToggling)
                    .accessibilityLabel(task.isCompleted ? L("markIncomplete") : L("markComplete"))
                    .accessibilityIdentifier("chat.block.task.\(block.id).toggle")
                    Text(task.description)
                        .font(DS.Typography.callout)
                        .foregroundStyle(task.isCompleted ? DS.Palette.inkSecondary : DS.Palette.ink)
                        .strikethrough(task.isCompleted, color: DS.Palette.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        })
        .accessibilityIdentifier("chat.block.task.\(block.id)")
    }

    private func toggle(_ task: ActionItem) {
        guard !isToggling else { return }
        isToggling = true
        DSHaptics.tap()
        Task {
            await tasks.setCompleted(task.id, !task.isCompleted)
            isToggling = false
        }
    }

    private func open(_ task: ActionItem) {
        openURL(DeepLink.task(id: task.id).url)
    }
}

// MARK: - Goal

/// The goal the answer moved: its current and target, and the way to its form.
struct GoalBlockCard: View {
    @Environment(GoalsStore.self) private var goals
    let block: ChatBlock
    let goalID: String
    let summary: String
    @State private var editing: Goal?
    @State private var showsGoals = false

    var body: some View {
        ChatBlockCard(onTap: resolved.map { goal in { editing = goal } }, content: {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                ChatBlockEyebrow(symbol: "flag", label: L("chatBlockGoal"))
                Text(summary.isEmpty ? L("chatBlockUnavailable") : summary)
                    .font(DS.Typography.callout)
                    .foregroundStyle(summary.isEmpty ? DS.Palette.inkSecondary : DS.Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let goal = resolved {
                    ProgressView(value: goal.progress).tint(GoalRow.tint(goal.progress))
                    Text(progress(goal))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .monospacedDigit()
                }
                ChatBlockAction(
                    title: L("chatBlockOpenInGoals"), identifier: "chat.block.goal.\(block.id).open",
                    action: { showsGoals = true }
                )
            }
        })
        .accessibilityIdentifier("chat.block.goal.\(block.id)")
        .sheet(item: $editing) { GoalFormSheet(goal: $0).presentationDetents([.medium]) }
        .sheet(isPresented: $showsGoals) { NavigationStack { GoalsScreen() } }
    }

    private var resolved: Goal? {
        goals.goals.first { $0.id == goalID }
    }

    private func progress(_ goal: Goal) -> String {
        L("nativeGoalProgress", GoalRow.number(goal.current), GoalRow.number(goal.target))
    }
}
