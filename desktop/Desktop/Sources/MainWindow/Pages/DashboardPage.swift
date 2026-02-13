import SwiftUI
import Combine

// MARK: - Dashboard View Model

@MainActor
class DashboardViewModel: ObservableObject {
    // Observe the shared TasksStore
    private let tasksStore = TasksStore.shared

    @Published var scoreResponse: ScoreResponse?
    @Published var goals: [Goal] = []
    @Published var isLoading = false
    @Published var error: String?

    private var cancellables = Set<AnyCancellable>()
    private var lastGoalRefreshTime: Date = .distantPast

    // Computed properties that delegate to TasksStore
    var overdueTasks: [TaskActionItem] { tasksStore.overdueTasks }
    var todaysTasks: [TaskActionItem] { tasksStore.todaysTasks }
    var recentTasks: [TaskActionItem] { tasksStore.tasksWithoutDueDate }

    init() {
        // Forward TasksStore changes to trigger view updates
        tasksStore.objectWillChange
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        // Load goals from local SQLite for instant display
        loadGoalsFromLocal()

        // Refresh goals when one is auto-created
        NotificationCenter.default.publisher(for: .goalAutoCreated)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { [weak self] in
                    await self?.loadGoals()
                }
            }
            .store(in: &cancellables)
    }

    func loadDashboardData() async {
        isLoading = true
        error = nil

        // Load all data in parallel
        async let scoreTask: Void = loadScores()
        async let tasksTask: Void = tasksStore.loadTasks()  // Use shared store
        async let goalsTask: Void = loadGoals()

        let _ = await (scoreTask, tasksTask, goalsTask)

        isLoading = false
    }

    private func loadScores() async {
        do {
            scoreResponse = try await APIClient.shared.getScores()
        } catch {
            logError("Failed to load scores", error: error)
        }
    }

    private func loadGoals() async {
        // 1. Show local data first (already loaded in init)
        // 2. Fetch from API
        do {
            let apiGoals = try await APIClient.shared.getGoals()
            // 3. Sync to SQLite
            try await GoalStorage.shared.syncServerGoals(apiGoals)
            // 4. Reload from SQLite (source of truth)
            goals = try await GoalStorage.shared.getLocalGoals()
            lastGoalRefreshTime = Date()
        } catch {
            logError("Failed to load goals", error: error)
        }
    }

    /// Refresh goals with 30-second debounce (for app lifecycle events)
    func refreshGoals() {
        let now = Date()
        guard now.timeIntervalSince(lastGoalRefreshTime) > 30 else { return }
        Task {
            await loadGoals()
        }
    }

    // MARK: - Local Goals Storage

    private func loadGoalsFromLocal() {
        Task {
            do {
                goals = try await GoalStorage.shared.getLocalGoals()
            } catch {
                logError("Failed to load goals from local storage", error: error)
            }
        }
    }

    func toggleTaskCompletion(_ task: TaskActionItem) async {
        // Delegate to shared store - it handles the update
        await tasksStore.toggleTask(task)
        // Reload scores after task completion change
        await loadScores()
    }

    func createGoal(title: String, goalType: GoalType, targetValue: Double, unit: String?) async {
        do {
            let goal = try await APIClient.shared.createGoal(
                title: title,
                goalType: goalType,
                targetValue: targetValue,
                unit: unit
            )
            _ = try? await GoalStorage.shared.syncServerGoal(goal)
            goals = try await GoalStorage.shared.getLocalGoals()
        } catch {
            logError("Failed to create goal", error: error)
        }
    }

    func updateGoalProgress(_ goal: Goal, currentValue: Double) async {
        log("Goals: Updating '\(goal.title)' progress to \(currentValue)")

        // Optimistically update local SQLite
        if let index = goals.firstIndex(where: { $0.id == goal.id }) {
            goals[index].currentValue = currentValue
        }
        try? await GoalStorage.shared.updateProgress(backendId: goal.id, currentValue: currentValue)

        do {
            let updated = try await APIClient.shared.updateGoalProgress(
                goalId: goal.id,
                currentValue: currentValue
            )

            // Sync API response to SQLite
            _ = try? await GoalStorage.shared.syncServerGoal(updated)

            // Check if the backend auto-completed this goal
            if updated.completedAt != nil {
                log("Goals: '\(goal.title)' COMPLETED! Triggering celebration.")
                goals = try await GoalStorage.shared.getLocalGoals()
                NotificationCenter.default.post(name: .goalCompleted, object: updated)
                return
            }

            goals = try await GoalStorage.shared.getLocalGoals()
            log("Goals: Updated '\(goal.title)' progress confirmed by API")
        } catch {
            logError("Failed to update goal progress", error: error)
        }
    }

    func deleteGoal(_ goal: Goal) async {
        do {
            // Soft-delete locally first for instant UI update
            try? await GoalStorage.shared.softDelete(backendId: goal.id)
            goals = try await GoalStorage.shared.getLocalGoals()
            // Then delete on backend
            try await APIClient.shared.deleteGoal(id: goal.id)
        } catch {
            logError("Failed to delete goal", error: error)
        }
    }
}

// MARK: - Dashboard Page

struct DashboardPage: View {
    @ObservedObject var viewModel: DashboardViewModel
    @ObservedObject var appState: AppState
    @Binding var selectedIndex: Int

    var body: some View {
        VStack(spacing: 0) {
            // Dashboard widgets (scrollable, compact)
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Header
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Dashboard")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(OmiColors.textPrimary)

                            Text(formattedDate)
                                .font(.system(size: 14))
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        if viewModel.isLoading {
                            ProgressView()
                                .scaleEffect(0.8)
                        }

                        Button(action: {
                            Task {
                                await viewModel.loadDashboardData()
                            }
                        }) {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 14))
                                .foregroundColor(OmiColors.textSecondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 24)

                // 4 Widgets in 2x2 grid
                Grid(horizontalSpacing: 16, verticalSpacing: 16) {
                    // Top row: Score + Focus
                    GridRow {
                        ScoreWidget(scoreResponse: viewModel.scoreResponse)
                            .frame(minWidth: 0, maxWidth: .infinity)

                        FocusSummaryWidget(
                            todayStats: FocusStorage.shared.todayStats,
                            totalStats: FocusStorage.shared.allTimeStats
                        )
                        .frame(minWidth: 0, maxWidth: .infinity)
                    }

                    // Bottom row: Tasks + Goals
                    GridRow {
                        TasksWidget(
                            overdueTasks: viewModel.overdueTasks,
                            todaysTasks: viewModel.todaysTasks,
                            recentTasks: viewModel.recentTasks,
                            onToggleCompletion: { task in
                                Task {
                                    await viewModel.toggleTaskCompletion(task)
                                }
                            }
                        )
                        .frame(minWidth: 0, maxWidth: .infinity)

                        GoalsWidget(
                            goals: viewModel.goals,
                            onCreateGoal: { title, current, target in
                                Task {
                                    await viewModel.createGoal(
                                        title: title,
                                        goalType: .numeric,
                                        targetValue: target,
                                        unit: nil
                                    )
                                }
                            },
                            onUpdateProgress: { goal, value in
                                Task {
                                    await viewModel.updateGoalProgress(goal, currentValue: value)
                                }
                            },
                            onDeleteGoal: { goal in
                                Task {
                                    await viewModel.deleteGoal(goal)
                                }
                            }
                        )
                        .frame(minWidth: 0, maxWidth: .infinity)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 16)

                }
            }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
                viewModel.refreshGoals()
            }

            // Conversations section fills remaining space
            ConversationsPage(appState: appState)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
    }

    private var formattedDate: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d"
        return formatter.string(from: Date())
    }
}

#Preview {
    DashboardPage(viewModel: DashboardViewModel(), appState: AppState(), selectedIndex: .constant(0))
        .frame(width: 800, height: 600)
        .background(OmiColors.backgroundPrimary)
}
