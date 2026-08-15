import Foundation
import OmiTheme
import SwiftUI

/// Universal canonical Goals destination. The page owns no copied goal or
/// task state: it renders the shared projection and delegates task mutation to
/// `TasksStore` after that store hydrates the canonical task ID.
@MainActor
struct ChatFirstGoalsPage: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  @ObservedObject var goalsStore: CanonicalGoalsStore
  @ObservedObject var tasksStore: TasksStore
  let chatProvider: ChatProvider
  let automationRuntime: ChatFirstAutomationRuntime?

  @State private var resolvingTaskIDs = Set<String>()

  private var pendingGoalID: String? {
    guard case .goal(let id) = navigation.pendingFocus else { return nil }
    return id
  }

  private var displayedDetail: OmiAPI.GoalDetailProjection? {
    guard let detail = goalsStore.selectedGoalDetail else { return nil }
    if let pendingGoalID { return detail.goal.goalId == pendingGoalID ? detail : nil }
    return detail.goal.goalId == goalsStore.primaryFocusedGoal?.goalId ? detail : nil
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header

      Group {
        switch goalsStore.availability {
        case .unavailable(let message):
          unavailableState(message)
        case .inactive, .loading:
          if goalsStore.activeGoals.isEmpty {
            ProgressView("Loading goals")
              .frame(maxWidth: .infinity, maxHeight: .infinity)
          } else {
            goalContent
          }
        default:
          if !ChatFirstGoalPresentationPolicy.shouldShowGoalContent(
            activeGoalCount: goalsStore.activeGoals.count,
            displayedGoalID: displayedDetail?.goal.goalId
          ) {
            emptyState
          } else {
            goalContent
          }
        }
      }
    }
    .onAppear {
      Task { await refreshProjectionAndDetail() }
      registerAutomationActions()
    }
    .onDisappear { automationRuntime?.unregisterGoalsPage() }
    .onChange(of: navigation.pendingFocus) { _, _ in
      Task { await loadDetailForCurrentFocus() }
    }
    .accessibilityIdentifier("chat-first-goals-page")
  }

  private var header: some View {
    HStack(alignment: .firstTextBaseline) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Goals")
          .scaledFont(size: OmiType.title, weight: .bold)
          .foregroundStyle(Ink.primary)
        Text("Keep the work that matters in view.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
      }
      Spacer()
      Button {
        Task { await refreshProjectionAndDetail() }
      } label: {
        Image(systemName: "arrow.clockwise")
          .scaledFont(size: OmiType.body, weight: .medium)
      }
      .buttonStyle(.plain)
      .disabled(goalsStore.isLoading)
      .accessibilityLabel("Refresh goals")
      .accessibilityIdentifier("chat-first-goals-refresh")
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.xl)
  }

  private var goalContent: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        if let detail = displayedDetail {
          ChatFirstFocusedGoalSection(
            detail: detail,
            isResolvingTask: { resolvingTaskIDs.contains($0) },
            onToggleTask: toggleTask,
            onViewTasks: {
              navigation.open(focus: .goal(id: detail.goal.goalId), destination: .tasks)
            },
            onContinueInChat: { navigation.discuss(.goal(id: detail.goal.goalId), using: chatProvider) },
            onVisible: acknowledgeVisibleGoal
          )
          .id(detail.goal.goalId)
        } else if goalsStore.primaryFocusedGoal != nil || pendingGoalID != nil {
          ProgressView("Loading goal")
            .frame(maxWidth: .infinity)
        }

        if !goalsStore.otherActiveGoals.isEmpty {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Other active goals")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundStyle(Ink.primary)

            ForEach(goalsStore.otherActiveGoals, id: \.goalId) { goal in
              ChatFirstGoalRow(
                goal: goal,
                isSettingFocus: goalsStore.focusMutationGoalID == goal.goalId,
                onDiscuss: { navigation.discuss(.goal(id: goal.goalId), using: chatProvider) },
                onSetFocus: { setFocus(goalID: goal.goalId) }
              )
            }
          }
        }

        if let error = goalsStore.error, displayedDetail != nil {
          Text(error)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
            .accessibilityIdentifier("chat-first-goals-inline-error")
        }
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.bottom, OmiSpacing.xxl)
    }
  }

  private var emptyState: some View {
    ContentUnavailableView {
      Label("No active goals", systemImage: "target")
    } description: {
      Text("Omi can help you turn what matters into a clear goal.")
    } actions: {
      Button("Talk to Omi about a goal") {
        navigation.discuss(.goals, using: chatProvider)
      }
      .accessibilityIdentifier("chat-first-goals-empty-discuss")
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func unavailableState(_ message: String) -> some View {
    ContentUnavailableView {
      Label("Goals are unavailable", systemImage: "exclamationmark.triangle")
    } description: {
      Text(message)
    } actions: {
      Button("Refresh") {
        Task { await refreshProjectionAndDetail() }
      }
      .accessibilityIdentifier("chat-first-goals-unavailable-refresh")
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func refreshProjectionAndDetail() async {
    await goalsStore.load()
    await loadDetailForCurrentFocus()
  }

  private func loadDetailForCurrentFocus() async {
    let goalID = pendingGoalID ?? goalsStore.primaryFocusedGoal?.goalId
    guard let goalID else { return }
    _ = await goalsStore.loadDetail(goalID: goalID)
  }

  private func acknowledgeVisibleGoal(_ goalID: String) {
    guard
      let focus = ChatFirstGoalDetailPolicy.focusToAcknowledge(
        pendingFocus: navigation.pendingFocus,
        visibleGoalID: goalID
      )
    else { return }
    _ = navigation.acknowledgeFocus(focus)
  }

  private func setFocus(goalID: String) {
    Task { @MainActor in
      guard await goalsStore.setAsFocus(goalID: goalID) else { return }
      _ = await goalsStore.loadDetail(goalID: goalID)
    }
  }

  private func toggleTask(_ taskID: String) {
    guard !resolvingTaskIDs.contains(taskID) else { return }
    resolvingTaskIDs.insert(taskID)
    Task { @MainActor in
      defer { resolvingTaskIDs.remove(taskID) }
      guard let task = await tasksStore.resolveCanonicalTask(id: taskID) else { return }
      await tasksStore.toggleTask(task)
      if let goalID = displayedDetail?.goal.goalId {
        _ = await goalsStore.loadDetail(goalID: goalID)
      }
    }
  }

  private func registerAutomationActions() {
    automationRuntime?.registerGoalsPage(
      setFocus: { [goalsStore] in
        guard let goalID = goalsStore.otherActiveGoals.first?.goalId else { return false }
        guard await goalsStore.setAsFocus(goalID: goalID) else { return false }
        return await goalsStore.loadDetail(goalID: goalID) != nil
      },
      openRelatedTasks: { [navigation, goalsStore] in
        guard let goalID = goalsStore.selectedGoalDetail?.goal.goalId else { return false }
        navigation.open(focus: .goal(id: goalID), destination: .tasks)
        return true
      }
    )
  }
}

private struct ChatFirstFocusedGoalSection: View {
  let detail: OmiAPI.GoalDetailProjection
  let isResolvingTask: (String) -> Bool
  let onToggleTask: (String) -> Void
  let onViewTasks: () -> Void
  let onContinueInChat: () -> Void
  let onVisible: (String) -> Void

  private var completedCount: Int { ChatFirstGoalDetailPolicy.completedTaskCount(in: detail) }
  private var nextTasks: [OmiAPI.ActionItemResponse] {
    detail.tasks.filter { !$0.completed }.prefix(3).map { $0 }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        Image(systemName: "target")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(Ink.secondary)
          .frame(width: 28, height: 28)
          .glassCard(cornerRadius: OmiChrome.chipRadius)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Focused goal")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.secondary)
          Text(detail.goal.title)
            .scaledFont(size: OmiType.subheading, weight: .bold)
            .foregroundStyle(Ink.primary)
          Text(detail.goal.desiredOutcome)
            .scaledFont(size: OmiType.body)
            .foregroundStyle(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      if let whyItMatters = detail.goal.whyItMatters, !whyItMatters.isEmpty {
        Text(whyItMatters)
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        HStack {
          Text("Progress")
          Spacer()
          Text("\(completedCount) of \(detail.tasks.count) tasks")
        }
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(Ink.secondary)
        ProgressView(value: Double(completedCount), total: Double(max(1, detail.tasks.count)))
          .tint(Ink.listeningGreen)
      }

      if !nextTasks.isEmpty {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text("Next up")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.secondary)
          ForEach(nextTasks, id: \.id) { task in
            ChatFirstGoalTaskRow(
              task: task,
              isResolving: isResolvingTask(task.id),
              onToggle: { onToggleTask(task.id) }
            )
          }
        }
      }

      HStack(spacing: OmiSpacing.lg) {
        Button("View related tasks", action: onViewTasks)
          .buttonStyle(.plain)
          .foregroundStyle(Ink.secondary)
          .accessibilityIdentifier("chat-first-goal-\(detail.goal.goalId)-tasks")
        Button("Continue in Chat", action: onContinueInChat)
          .buttonStyle(.plain)
          .foregroundStyle(Ink.secondary)
          .accessibilityIdentifier("chat-first-goal-\(detail.goal.goalId)-discuss")
      }
      .scaledFont(size: OmiType.caption, weight: .semibold)
    }
    .padding(OmiSpacing.xl)
    .frame(maxWidth: 680, alignment: .leading)
    // The focused goal is the emphasised card on the page; no drop shadow, because
    // the panel already carries the one ambient shadow in this system.
    .glassCard(emphasized: true)
    .onAppear { onVisible(detail.goal.goalId) }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("chat-first-goal-focused-\(detail.goal.goalId)")
  }
}

private struct ChatFirstGoalTaskRow: View {
  let task: OmiAPI.ActionItemResponse
  let isResolving: Bool
  let onToggle: () -> Void

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Button(action: onToggle) {
        Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundStyle(task.completed ? Ink.listeningGreen : Ink.secondary)
      }
      .buttonStyle(.plain)
      .disabled(isResolving)
      .accessibilityLabel(
        task.completed ? "Mark \(task.description_) incomplete" : "Mark \(task.description_) complete"
      )
      .accessibilityIdentifier("chat-first-goal-task-\(task.id)-toggle")

      Text(task.description_)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(task.completed ? Ink.secondary : Ink.primary)
        .strikethrough(task.completed, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
      if isResolving {
        ProgressView()
          .controlSize(.small)
      }
    }
    .accessibilityIdentifier("chat-first-goal-task-\(task.id)")
  }
}

private struct ChatFirstGoalRow: View {
  let goal: OmiAPI.GoalResponse
  let isSettingFocus: Bool
  let onDiscuss: () -> Void
  let onSetFocus: () -> Void

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: goal.status == .focused ? "target" : "circle")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.secondary)
        .frame(width: 22, height: 22)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(goal.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundStyle(Ink.primary)
        Text(goal.desiredOutcome)
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
          .lineLimit(2)
        Text(ChatFirstGoalProgressPolicy.summary(for: goal))
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(Ink.secondary)
      }
      Spacer(minLength: OmiSpacing.md)
      VStack(alignment: .trailing, spacing: OmiSpacing.sm) {
        Button("Discuss", action: onDiscuss)
          .buttonStyle(.plain)
          .foregroundStyle(Ink.secondary)
          .accessibilityIdentifier("chat-first-goal-\(goal.goalId)-discuss")
        Button {
          onSetFocus()
        } label: {
          HStack(spacing: OmiSpacing.xxs) {
            if isSettingFocus { ProgressView().controlSize(.small) }
            Text("Set as focus")
          }
        }
        .buttonStyle(.plain)
        .foregroundStyle(Ink.secondary)
        .disabled(isSettingFocus)
        .accessibilityIdentifier("chat-first-goal-\(goal.goalId)-set-focus")
      }
      .scaledFont(size: OmiType.caption, weight: .medium)
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: 680, alignment: .leading)
    .glassCard(cornerRadius: PageGlass.rowRadius)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("chat-first-goal-row-\(goal.goalId)")
  }
}

/// Canonical goals use a generic numeric projection. The list must therefore
/// show progress from that projection rather than inventing a task count or
/// consulting the legacy goal store.
enum ChatFirstGoalProgressPolicy {
  static func summary(for goal: OmiAPI.GoalResponse) -> String {
    let unit = goal.unit.map { " \($0)" } ?? ""
    return "Progress: \(formatted(goal.currentValue)) of \(formatted(goal.targetValue))\(unit)"
  }

  private static func formatted(_ value: Double) -> String {
    if value.rounded() == value { return String(Int(value)) }
    return String(format: "%.1f", value)
  }
}

enum ChatFirstGoalPresentationPolicy {
  static func shouldShowGoalContent(activeGoalCount: Int, displayedGoalID: String?) -> Bool {
    activeGoalCount > 0 || displayedGoalID != nil
  }
}
