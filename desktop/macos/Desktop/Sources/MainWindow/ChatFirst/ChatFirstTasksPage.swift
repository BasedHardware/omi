import Foundation
import SwiftUI
import OmiTheme

/// The two deliberate scheduling groups in the cohort Tasks page. This folds
/// the legacy page's Tomorrow, Later, and no-deadline buckets into a single
/// quiet Later section while preserving its rule that overdue work is Today.
enum ChatFirstTaskScheduleGroup: String, CaseIterable, Hashable, Sendable {
  case today
  case later

  var title: String {
    switch self {
    case .today: return "Today"
    case .later: return "Later"
    }
  }
}

struct ChatFirstTaskBadges: Equatable, Sendable {
  let goalID: String?
  let captureID: String?
}

struct ChatFirstTaskGoalGroup: Identifiable {
  let goalID: String?
  let tasks: [TaskActionItem]

  var id: String { goalID.map { "goal:\($0)" } ?? "other" }
}

/// Pure presentation policy for T10. Keeping date grouping, badge derivation,
/// and the visible-focus predicate separate from the view makes the page
/// replay-safe and keeps tests independent from SwiftUI layout timing.
enum ChatFirstTaskPagePolicy {
  static func scheduleGroup(
    for task: TaskActionItem,
    now: Date = Date(),
    calendar: Calendar = .current
  ) -> ChatFirstTaskScheduleGroup {
    let startOfToday = calendar.startOfDay(for: now)
    let startOfTomorrow = calendar.date(byAdding: .day, value: 1, to: startOfToday) ?? now
    // Matches `TasksViewModel.categoryFor`: every task due before tomorrow —
    // including overdue work — belongs in Today. No-date work is Later.
    return (task.dueAt ?? .distantFuture) < startOfTomorrow ? .today : .later
  }

  static func suggestedDueDate(
    for group: ChatFirstTaskScheduleGroup,
    now: Date = Date(),
    calendar: Calendar = .current
  ) -> Date {
    let startOfToday = calendar.startOfDay(for: now)
    switch group {
    case .today:
      return calendar.date(bySettingHour: 23, minute: 59, second: 0, of: now) ?? now
    case .later:
      // This is the legacy page's Later move/create scheduling value.
      return calendar.date(byAdding: .day, value: 7, to: startOfToday) ?? now
    }
  }

  static func badges(for task: TaskActionItem) -> ChatFirstTaskBadges {
    ChatFirstTaskBadges(
      goalID: normalizedID(task.goalId),
      captureID: ChatFirstCaptureLinkPolicy.captureID(for: task)
    )
  }

  static func groupedByGoal(_ tasks: [TaskActionItem]) -> [ChatFirstTaskGoalGroup] {
    let ordered = tasks.sorted(by: taskSort)
    var orderedKeys: [String] = []
    var grouped: [String: [TaskActionItem]] = [:]
    var goalIDs: [String: String] = [:]

    for task in ordered {
      let goalID = normalizedID(task.goalId)
      let key = goalID.map { "goal:\($0)" } ?? "other"
      if grouped[key] == nil {
        orderedKeys.append(key)
        if let goalID { goalIDs[key] = goalID }
      }
      grouped[key, default: []].append(task)
    }

    return orderedKeys.compactMap { key in
      guard let tasks = grouped[key] else { return nil }
      return ChatFirstTaskGoalGroup(goalID: goalIDs[key], tasks: tasks)
    }
  }

  static func focusToAcknowledge(
    pendingFocus: ChatFirstPendingFocus?,
    visibleTaskID: String
  ) -> ChatFirstPendingFocus? {
    guard case .task(let pendingID) = pendingFocus, pendingID == visibleTaskID else { return nil }
    return pendingFocus
  }

  static func goalFocusToAcknowledge(
    pendingFocus: ChatFirstPendingFocus?,
    visibleGoalID: String
  ) -> ChatFirstPendingFocus? {
    guard case .goal(let pendingID) = pendingFocus, pendingID == visibleGoalID else { return nil }
    return pendingFocus
  }

  static func goalFocusAnchor(_ goalID: String) -> String {
    "chat-first-tasks-goal-focus:\(goalID)"
  }

  private static func normalizedID(_ id: String?) -> String? {
    guard let id else { return nil }
    let normalized = id.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }

  private static func taskSort(_ lhs: TaskActionItem, _ rhs: TaskActionItem) -> Bool {
    if lhs.completed != rhs.completed { return !lhs.completed }
    let lhsDue = lhs.dueAt ?? .distantFuture
    let rhsDue = rhs.dueAt ?? .distantFuture
    if lhsDue != rhsDue { return lhsDue < rhsDue }
    return lhs.createdAt > rhs.createdAt
  }
}

/// Cohort-only lightweight checklist. It reads and mutates the one shared
/// TasksStore; legacy TasksPage continues to own the legacy-shell UI unchanged.
@MainActor
struct ChatFirstTasksPage: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  @ObservedObject var tasksStore: TasksStore
  let chatProvider: ChatProvider

  @State private var addDrafts: [ChatFirstTaskScheduleGroup: String] = [:]
  @State private var addingGroups: Set<ChatFirstTaskScheduleGroup> = []
  @State private var highlightedTaskID: String?

  init(
    navigation: ChatFirstShellNavigation,
    tasksStore: TasksStore,
    chatProvider: ChatProvider
  ) {
    self.navigation = navigation
    self.tasksStore = tasksStore
    self.chatProvider = chatProvider
  }

  private var visibleTasks: [TaskActionItem] {
    tasksStore.tasks.filter { $0.deleted != true }
  }

  private var todayTasks: [TaskActionItem] {
    visibleTasks.filter { ChatFirstTaskPagePolicy.scheduleGroup(for: $0) == .today }
  }

  private var laterTasks: [TaskActionItem] {
    visibleTasks.filter { ChatFirstTaskPagePolicy.scheduleGroup(for: $0) == .later }
  }

  private var pendingTaskID: String? {
    guard case .task(let id) = navigation.pendingFocus else { return nil }
    return id
  }

  private var pendingGoalID: String? {
    guard case .goal(let id) = navigation.pendingFocus else { return nil }
    return id
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header

      if let error = tasksStore.error, visibleTasks.isEmpty {
        unavailableState(error)
      } else if tasksStore.isLoading && visibleTasks.isEmpty {
        ProgressView("Loading tasks")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if visibleTasks.isEmpty {
        emptyState
      } else {
        taskList
      }
    }
    .background(OmiColors.backgroundPrimary)
    .onAppear {
      tasksStore.isActive = true
      Task { await tasksStore.loadTasksIfNeeded() }
    }
    .onDisappear {
      tasksStore.isActive = false
    }
    .accessibilityIdentifier("chat-first-tasks-page")
  }

  private var header: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(alignment: .firstTextBaseline) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Tasks")
            .scaledFont(size: OmiType.title, weight: .bold)
            .foregroundStyle(OmiColors.textPrimary)
          Text("A quiet checklist for what is next.")
            .scaledFont(size: OmiType.body)
            .foregroundStyle(OmiColors.textSecondary)
        }
        Spacer()
        Button {
          Task { await tasksStore.loadTasks() }
        } label: {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: OmiType.body, weight: .medium)
        }
        .buttonStyle(.plain)
        .disabled(tasksStore.isLoading)
        .accessibilityLabel("Refresh tasks")
        .accessibilityIdentifier("chat-first-tasks-refresh")
      }

      Button("Ask Omi about these tasks") {
        navigation.discuss(.tasks, using: chatProvider)
      }
      .buttonStyle(.plain)
      .foregroundStyle(OmiColors.textSecondary)
      .accessibilityIdentifier("chat-first-tasks-discuss")

      if let error = tasksStore.error, !visibleTasks.isEmpty {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "exclamationmark.triangle")
            .accessibilityHidden(true)
          Text("Some task changes could not be confirmed. Refresh to reconcile.")
        }
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(OmiColors.textSecondary)
        .padding(.top, OmiSpacing.xs)
      }
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.xl)
  }

  private var taskList: some View {
    ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          scheduleSection(.today, tasks: todayTasks)
          scheduleSection(.later, tasks: laterTasks)
        }
        .padding(.horizontal, OmiSpacing.xxl)
        .padding(.bottom, OmiSpacing.xxl)
      }
      .onAppear { scrollPendingFocusIntoView(proxy) }
      .onChange(of: navigation.pendingFocus) { _, _ in scrollPendingFocusIntoView(proxy) }
      .onChange(of: visibleTasks.map(\.id)) { _ in scrollPendingFocusIntoView(proxy) }
    }
  }

  @ViewBuilder
  private func scheduleSection(_ group: ChatFirstTaskScheduleGroup, tasks: [TaskActionItem]) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text(group.title)
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundStyle(OmiColors.textPrimary)

      ForEach(ChatFirstTaskPagePolicy.groupedByGoal(tasks)) { goalGroup in
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          if let goalID = goalGroup.goalID {
            ChatFirstDestinationBadge(
              title: "Goal",
              systemImage: "target",
              accessibilityID: "chat-first-tasks-goal-\(goalID)"
            ) {
              navigation.open(focus: .goal(id: goalID))
            }
            .padding(.bottom, OmiSpacing.xxs)
          }

          ForEach(goalGroup.tasks) { task in
            ChatFirstTaskRow(
              task: task,
              scheduleGroup: group,
              tasksStore: tasksStore,
              navigation: navigation,
              isHighlighted: highlightedTaskID == task.id,
              onVisible: { taskID in acknowledgeVisibleTaskIfNeeded(taskID) }
            )
            .id(task.id)
          }
        }
        .id(goalGroup.goalID.map(ChatFirstTaskPagePolicy.goalFocusAnchor) ?? goalGroup.id)
        .onAppear {
          guard let goalID = goalGroup.goalID else { return }
          acknowledgeVisibleGoalIfNeeded(goalID)
        }
      }

      ChatFirstTaskAddRow(
        group: group,
        draft: Binding(
          get: { addDrafts[group, default: ""] },
          set: { addDrafts[group] = $0 }
        ),
        isAdding: addingGroups.contains(group),
        onSubmit: { createTask(in: group) }
      )
    }
    .accessibilityIdentifier("chat-first-tasks-section-\(group.rawValue)")
  }

  private var emptyState: some View {
    ContentUnavailableView {
      Label("No tasks yet", systemImage: "checklist")
    } description: {
      Text("Talk to Omi when you are ready to make a plan.")
    } actions: {
      Button("Talk to Omi") {
        navigation.discuss(.tasks, using: chatProvider)
      }
      .accessibilityIdentifier("chat-first-tasks-empty-discuss")
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func unavailableState(_ error: String) -> some View {
    ContentUnavailableView {
      Label("Tasks are unavailable", systemImage: "exclamationmark.triangle")
    } description: {
      Text(error)
    } actions: {
      Button("Refresh") {
        Task { await tasksStore.loadTasks() }
      }
      .accessibilityIdentifier("chat-first-tasks-unavailable-refresh")
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func createTask(in group: ChatFirstTaskScheduleGroup) {
    guard !addingGroups.contains(group) else { return }
    let description = addDrafts[group, default: ""].trimmingCharacters(in: .whitespacesAndNewlines)
    guard !description.isEmpty else { return }

    addingGroups.insert(group)
    Task { @MainActor in
      _ = await tasksStore.createTask(
        description: description,
        dueAt: ChatFirstTaskPagePolicy.suggestedDueDate(for: group),
        priority: nil
      )
      addDrafts[group] = ""
      addingGroups.remove(group)
    }
  }

  private func scrollPendingFocusIntoView(_ proxy: ScrollViewProxy) {
    if let taskID = pendingTaskID,
      visibleTasks.contains(where: { $0.id == taskID })
    {
      withAnimation(OmiMotion.gated(.easeOut(duration: 0.18))) {
        proxy.scrollTo(taskID, anchor: .center)
      }
      return
    }

    guard let goalID = pendingGoalID,
      visibleTasks.contains(where: { $0.goalId == goalID })
    else { return }
    withAnimation(OmiMotion.gated(.easeOut(duration: 0.18))) {
      proxy.scrollTo(ChatFirstTaskPagePolicy.goalFocusAnchor(goalID), anchor: .center)
    }
  }

  private func acknowledgeVisibleTaskIfNeeded(_ taskID: String) {
    guard let focus = ChatFirstTaskPagePolicy.focusToAcknowledge(
      pendingFocus: navigation.pendingFocus,
      visibleTaskID: taskID
    ), navigation.acknowledgeFocus(focus)
    else { return }

    highlightedTaskID = taskID
    Task { @MainActor in
      try? await Task.sleep(nanoseconds: 900_000_000)
      guard !Task.isCancelled, highlightedTaskID == taskID else { return }
      highlightedTaskID = nil
    }
  }

  private func acknowledgeVisibleGoalIfNeeded(_ goalID: String) {
    guard let focus = ChatFirstTaskPagePolicy.goalFocusToAcknowledge(
      pendingFocus: navigation.pendingFocus,
      visibleGoalID: goalID
    ) else { return }
    _ = navigation.acknowledgeFocus(focus)
  }
}

private struct ChatFirstTaskRow: View {
  let task: TaskActionItem
  let scheduleGroup: ChatFirstTaskScheduleGroup
  @ObservedObject var tasksStore: TasksStore
  let navigation: ChatFirstShellNavigation
  let isHighlighted: Bool
  let onVisible: (String) -> Void

  @State private var isToggling = false
  @State private var isSaving = false
  @State private var isEditing = false
  @State private var titleDraft = ""
  @FocusState private var titleIsFocused: Bool

  private var badges: ChatFirstTaskBadges { ChatFirstTaskPagePolicy.badges(for: task) }
  private var moveTarget: ChatFirstTaskScheduleGroup {
    scheduleGroup == .today ? .later : .today
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Button {
        toggle()
      } label: {
        Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundStyle(task.completed ? OmiColors.success : OmiColors.textTertiary)
          .frame(width: 24, height: 24)
      }
      .buttonStyle(.plain)
      .disabled(isToggling)
      .accessibilityLabel(task.completed ? "Mark \(task.description) incomplete" : "Mark \(task.description) complete")
      .accessibilityIdentifier("chat-first-tasks-toggle-\(task.id)")

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        if isEditing {
          TextField("Task", text: $titleDraft)
            .textFieldStyle(.plain)
            .scaledFont(size: OmiType.body, weight: .medium)
            .focused($titleIsFocused)
            .onSubmit { rename() }
            .onExitCommand { cancelRename() }
            .accessibilityLabel("Rename \(task.description)")
            .accessibilityIdentifier("chat-first-tasks-rename-\(task.id)")
            .onAppear {
              titleDraft = task.description
              titleIsFocused = true
            }
        } else {
          Button {
            titleDraft = task.description
            isEditing = true
          } label: {
            Text(task.description)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundStyle(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
              .strikethrough(task.completed, color: OmiColors.textTertiary)
              .multilineTextAlignment(.leading)
              .fixedSize(horizontal: false, vertical: true)
          }
          .buttonStyle(.plain)
          .disabled(isSaving)
          .onKeyPress(.return) { _ in
            titleDraft = task.description
            isEditing = true
            return .handled
          }
          .accessibilityLabel("Rename \(task.description)")
          .accessibilityIdentifier("chat-first-tasks-title-\(task.id)")
        }

        HStack(spacing: OmiSpacing.sm) {
          if let captureID = badges.captureID {
            ChatFirstDestinationBadge(
              title: "Capture",
              systemImage: "waveform",
              accessibilityID: "chat-first-tasks-capture-\(task.id)-\(captureID)"
            ) {
              navigation.open(focus: .capture(id: captureID, momentTs: nil))
            }
          }

          Button("Move to \(moveTarget.title)") {
            move()
          }
          .buttonStyle(.plain)
          .foregroundStyle(OmiColors.textSecondary)
          .disabled(isSaving)
          .accessibilityIdentifier("chat-first-tasks-move-\(task.id)-\(moveTarget.rawValue)")
        }
        .scaledFont(size: OmiType.caption)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(isHighlighted ? OmiColors.backgroundTertiary : Color.clear)
    )
    .onAppear { onVisible(task.id) }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("chat-first-tasks-row-\(task.id)")
  }

  private func toggle() {
    guard !isToggling else { return }
    isToggling = true
    Task { @MainActor in
      await tasksStore.toggleTask(task)
      isToggling = false
    }
  }

  private func rename() {
    let description = titleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !description.isEmpty else {
      cancelRename()
      return
    }
    guard description != task.description else {
      cancelRename()
      return
    }
    isEditing = false
    isSaving = true
    Task { @MainActor in
      _ = await tasksStore.updateTask(
        task,
        description: description,
        remoteFailureBehavior: .rollbackForChatFirst
      )
      isSaving = false
    }
  }

  private func cancelRename() {
    titleDraft = task.description
    titleIsFocused = false
    isEditing = false
  }

  private func move() {
    guard !isSaving else { return }
    isSaving = true
    Task { @MainActor in
      _ = await tasksStore.updateTask(
        task,
        dueAt: ChatFirstTaskPagePolicy.suggestedDueDate(for: moveTarget),
        remoteFailureBehavior: .rollbackForChatFirst
      )
      isSaving = false
    }
  }
}

private struct ChatFirstTaskAddRow: View {
  let group: ChatFirstTaskScheduleGroup
  @Binding var draft: String
  let isAdding: Bool
  let onSubmit: () -> Void

  @FocusState private var isFocused: Bool

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "plus")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(OmiColors.textTertiary)
        .frame(width: 24, height: 24)
        .accessibilityHidden(true)
      TextField("Add a task", text: $draft)
        .textFieldStyle(.plain)
        .focused($isFocused)
        .onSubmit(onSubmit)
        .accessibilityLabel("Add \(group.title) task")
        .accessibilityIdentifier("chat-first-tasks-add-\(group.rawValue)")
      if !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        Button("Add", action: onSubmit)
          .buttonStyle(.plain)
          .foregroundStyle(OmiColors.textSecondary)
          .disabled(isAdding)
          .accessibilityIdentifier("chat-first-tasks-add-submit-\(group.rawValue)")
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .stroke(OmiColors.border.opacity(0.45), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
    )
  }
}
