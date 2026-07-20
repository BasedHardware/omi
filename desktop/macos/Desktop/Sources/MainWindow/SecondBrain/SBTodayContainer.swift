import OmiTheme
import SwiftUI

/// Adapter: reads the real stores (AppState, TasksStore, DashboardViewModel,
/// AssistantSettings, AuthService) and projects them into `SBTodayData` for the
/// presentational `SBTodayPage`. No business logic here beyond store calls.
struct SBTodayContainer: View {
  @ObservedObject var appState: AppState
  @ObservedObject var dashboardViewModel: DashboardViewModel
  @ObservedObject private var tasks = TasksStore.shared

  var onOpenConversation: (String) -> Void
  var onNavigate: (Int) -> Void
  var onAsk: (String) -> Void

  @State private var screenOn = AssistantSettings.shared.screenAnalysisEnabled

  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "h:mm a"
    return f
  }()

  var body: some View {
    SBTodayPage(
      data: buildData(),
      onToggleListening: { appState.toggleTranscription() },
      onToggleScreen: {
        let next = !AssistantSettings.shared.screenAnalysisEnabled
        AssistantSettings.shared.screenAnalysisEnabled = next
        screenOn = next
      },
      onAsk: onAsk,
      onViewAllFollowUps: { onNavigate(SidebarNavItem.tasks.rawValue) },
      onStartRecording: { if !appState.isTranscribing { appState.toggleTranscription() } }
    )
    .task { await tasks.loadDashboardTasks() }
    .onAppear { screenOn = AssistantSettings.shared.screenAnalysisEnabled }
    .onReceive(NotificationCenter.default.publisher(for: .assistantSettingsDidChange)) { _ in
      screenOn = AssistantSettings.shared.screenAnalysisEnabled
    }
  }

  private func buildData() -> SBTodayData {
    let name = normalizedName(AuthService.shared.displayName)
    let listening = appState.isTranscribing

    // Follow-ups: overdue first, then today's, then undated — real incomplete tasks.
    let followUpTasks = (tasks.overdueTasks + tasks.todaysTasks + tasks.tasksWithoutDueDate)
      .filter { !$0.completed }
    var seen = Set<String>()
    let dedupedFollowUps = followUpTasks.filter { seen.insert($0.id).inserted }

    let followUps = dedupedFollowUps.prefix(3).map { task in
      SBFollowUpRow(
        id: task.id,
        label: task.description,
        sub: followUpSub(task),
        // Task export integrations don't exist yet — completing is the real action.
        cta: "Done",
        run: { Task { await tasks.toggleTask(task) } }
      )
    }

    // Today's conversations.
    let cal = Calendar.current
    let todays = appState.conversations.filter { cal.isDateInToday($0.createdAt) }
    let live = todays.first { $0.status == .inProgress }
    let convRows =
      todays
      .filter { $0.status != .inProgress }
      .prefix(6)
      .map { convo in
        SBTodayItem(
          id: convo.id,
          title: convo.title,
          meta: conversationMeta(convo),
          time: Self.timeFormatter.string(from: convo.createdAt),
          onOpen: { onOpenConversation(convo.id) }
        )
      }

    // Classify against the data this view actually loads (dashboard slices), not
    // incompleteTasks (which only the Tasks page loads) — else seasoned users flash fresh.
    let isFresh = appState.conversations.isEmpty && dedupedFollowUps.isEmpty

    return SBTodayData(
      name: name,
      isFreshUser: isFresh,
      isListening: listening,
      screenOn: screenOn,
      followUps: Array(followUps),
      followUpTotal: dedupedFollowUps.count,
      liveConversationTitle: listening ? (live?.title ?? "Recording") : nil,
      conversations: Array(convRows),
      upcoming: [],
      focusToday: nil,
      suggestedQuestions: suggestedQuestions(isFresh: isFresh)
    )
  }

  private func normalizedName(_ raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed.components(separatedBy: " ").first
  }

  private func followUpSub(_ task: TaskActionItem) -> String {
    if let due = task.dueAt {
      return "Due " + Self.relativeDue(due)
    }
    return task.sourceLabel
  }

  private static func relativeDue(_ date: Date) -> String {
    let cal = Calendar.current
    if cal.isDateInToday(date) { return "today" }
    if cal.isDateInTomorrow(date) { return "tomorrow" }
    let f = DateFormatter()
    f.dateFormat = "EEE"
    return f.string(from: date)
  }

  private func conversationMeta(_ convo: ServerConversation) -> String {
    let count = convo.structured.actionItems.count
    if count > 0 { return count == 1 ? "1 task" : "\(count) tasks" }
    return convo.structured.category.capitalized
  }

  private func suggestedQuestions(isFresh: Bool) -> [String] {
    let all = [
      "What does my day look like?",
      "What did I promise people?",
      "What was I working on yesterday?",
    ]
    return isFresh ? Array(all.prefix(1)) : all
  }
}
