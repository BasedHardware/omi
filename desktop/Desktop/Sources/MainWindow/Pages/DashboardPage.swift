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
        async let tasksTask: Void = tasksStore.loadTasksIfNeeded()  // Don't re-fetch if ViewModelContainer already loaded
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
                unit: unit,
                source: "user"
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

    func updateGoal(_ goal: Goal, title: String, currentValue: Double, targetValue: Double) async {
        log("Goals: Updating goal '\(goal.title)' -> title='\(title)', current=\(currentValue), target=\(targetValue)")

        do {
            let updated = try await APIClient.shared.updateGoal(
                goalId: goal.id,
                title: title,
                currentValue: currentValue,
                targetValue: targetValue
            )

            _ = try? await GoalStorage.shared.syncServerGoal(updated)
            goals = try await GoalStorage.shared.getLocalGoals()
            log("Goals: Updated goal '\(updated.title)' confirmed by API")
        } catch {
            logError("Failed to update goal", error: error)
            goals = (try? await GoalStorage.shared.getLocalGoals()) ?? goals
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
    @ObservedObject var appProvider: AppProvider
    @ObservedObject var chatProvider: ChatProvider
    @Binding var selectedIndex: Int
    @State private var citedConversation: ServerConversation? = nil
    @State private var isLoadingCitation = false
    @AppStorage("dashboardWidgetsCollapsed") private var widgetsCollapsed = false

    private var selectedApp: OmiApp? {
        guard let appId = chatProvider.selectedAppId else { return nil }
        return appProvider.chatApps.first { $0.id == appId }
    }

    var body: some View {
        VStack(spacing: 0) {
            dashboardWidgets

            // Chat messages — fills remaining vertical space, scrolls internally,
            // morphs into the dashboard background (no card chrome).
            // A bottom gradient mask softens messages into the background near
            // the input field so they fade out instead of clipping abruptly.
            ChatMessagesView(
                messages: chatProvider.messages,
                isSending: chatProvider.isSending,
                hasMoreMessages: chatProvider.hasMoreMessages,
                isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
                isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions)
                    && !chatProvider.isClearing,
                app: selectedApp,
                onLoadMore: { await chatProvider.loadMoreMessages() },
                onRate: { messageId, rating in
                    Task { await chatProvider.rateMessage(messageId, rating: rating) }
                },
                onCitationTap: { citation in
                    handleCitationTap(citation)
                },
                sessionsLoadError: chatProvider.sessionsLoadError,
                onRetry: { Task { await chatProvider.retryLoad() } },
                welcomeContent: { dashboardChatWelcome }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .mask(
                LinearGradient(
                    stops: [
                        .init(color: .clear, location: 0.0),
                        .init(color: .black, location: 0.08),
                        .init(color: .black, location: 0.92),
                        .init(color: .clear, location: 1.0),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )

            ChatInputView(
                onSend: { text in
                    AnalyticsManager.shared.chatMessageSent(
                        messageLength: text.count, hasContext: selectedApp != nil, source: "dashboard_chat")
                    Task { await chatProvider.sendMessage(text) }
                },
                onFollowUp: { text in
                    Task { await chatProvider.sendFollowUp(text) }
                },
                onStop: {
                    chatProvider.stopAgent()
                },
                isSending: chatProvider.isSending,
                isStopping: chatProvider.isStopping,
                placeholder: "Ask omi anything",
                mode: $chatProvider.chatMode,
                inputText: $chatProvider.draftText
            )
            .padding(.horizontal, 30)
            .padding(.top, 12)
            .padding(.bottom, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .sheet(item: $citedConversation) { conversation in
            ConversationDetailView(
                conversation: conversation,
                onBack: {
                    citedConversation = nil
                }
            )
            .frame(minWidth: 500, minHeight: 500)
        }
        .overlay {
            if isLoadingCitation {
                ZStack {
                    Color.black.opacity(0.3)
                    VStack(spacing: 12) {
                        ProgressView()
                        Text("Loading source...")
                            .scaledFont(size: 13)
                            .foregroundColor(.white)
                    }
                    .padding(20)
                    .background(OmiColors.backgroundSecondary)
                    .cornerRadius(12)
                }
            }
        }
        .onAppear {
            if PostOnboardingPromptSuggestions.shouldShowPopup && !postOnboardingSuggestions.isEmpty {
                NotificationCenter.default.post(name: .showTryAskingPopup, object: nil)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            viewModel.refreshGoals()
        }
    }

    /// Welcome message shown when there are no chat messages yet.
    /// Transparent — no card chrome — so it morphs into the dashboard background.
    private var dashboardChatWelcome: some View {
        VStack(spacing: 12) {
            if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                let logoImage = NSImage(contentsOf: logoURL)
            {
                Image(nsImage: logoImage)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 40, height: 40)
            }

            Text("Ask omi anything")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Your personal AI assistant — knows you through your memories and conversations")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    /// Handle tapping on a citation card — opens the cited conversation in a sheet.
    private func handleCitationTap(_ citation: Citation) {
        guard citation.sourceType == .conversation else {
            log("Citation tapped: \(citation.title) (memory - no detail view)")
            return
        }

        isLoadingCitation = true

        Task {
            do {
                let conversation = try await APIClient.shared.getConversation(id: citation.id)
                await MainActor.run {
                    citedConversation = conversation
                    isLoadingCitation = false
                }
            } catch {
                logError("Failed to fetch cited conversation", error: error)
                await MainActor.run {
                    isLoadingCitation = false
                }
            }
        }
    }

    // MARK: - Summary counts for collapsed bar

    private var incompleteTaskCount: Int {
        viewModel.overdueTasks.count + viewModel.todaysTasks.count + viewModel.recentTasks.count
    }

    private var activeGoalCount: Int {
        viewModel.goals.count
    }

    // MARK: - Dashboard Widgets (collapsible)

    private var dashboardWidgets: some View {
        VStack(alignment: .leading, spacing: widgetsCollapsed ? 0 : 20) {
            if shouldShowSuggestionBanner {
                PromptSuggestionBanner(
                    suggestions: postOnboardingSuggestions,
                    onOpen: {
                        dismissSuggestionBanner()
                        NotificationCenter.default.post(name: .showTryAskingPopup, object: nil)
                    },
                    onAsk: handleSuggestedPrompt,
                    onDismiss: dismissSuggestionBanner
                )
            }

            if widgetsCollapsed {
                // Collapsed: slim summary bar
                collapsedWidgetBar
            } else {
                // Expanded: full Tasks + Goals cards
                expandedWidgets

                // Collapse button centered below widgets
                collapseButton
            }
        }
        .padding(.horizontal, 30)
        .padding(.top, widgetsCollapsed ? 20 : 32)
        .padding(.bottom, 8)
        .animation(.easeInOut(duration: 0.25), value: widgetsCollapsed)
    }

    private var collapsedWidgetBar: some View {
        Button(action: { widgetsCollapsed = false }) {
            HStack(spacing: 16) {
                // Tasks summary
                HStack(spacing: 6) {
                    Image(systemName: "checklist")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(incompleteTaskCount == 0
                        ? "No tasks"
                        : "\(incompleteTaskCount) task\(incompleteTaskCount == 1 ? "" : "s")")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }

                // Subtle divider dot
                Circle()
                    .fill(OmiColors.textQuaternary)
                    .frame(width: 3, height: 3)

                // Goals summary
                HStack(spacing: 6) {
                    Image(systemName: "target")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(activeGoalCount == 0
                        ? "No goals"
                        : "\(activeGoalCount) goal\(activeGoalCount == 1 ? "" : "s")")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }

                Spacer()

                // Expand chevron
                Image(systemName: "chevron.down")
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundColor(OmiColors.textQuaternary)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(OmiColors.border.opacity(0.12), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private var expandedWidgets: some View {
        // fixedSize(vertical:) constrains the Grid to its row's intrinsic
        // height so Tasks/Goals stop competing with ChatMessagesView for
        // vertical space; each cell still fills the row, so the two cards
        // remain visually equal-height (matching the taller intrinsic).
        Grid(horizontalSpacing: 20, verticalSpacing: 20) {
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
                    onUpdateGoal: { goal, title, current, target in
                        Task {
                            await viewModel.updateGoal(
                                goal,
                                title: title,
                                currentValue: current,
                                targetValue: target
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
        .fixedSize(horizontal: false, vertical: true)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private var collapseButton: some View {
        HStack {
            Spacer()
            Button(action: { widgetsCollapsed = true }) {
                Image(systemName: "chevron.up")
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundColor(OmiColors.textQuaternary)
                    .frame(width: 48, height: 20)
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }

    private var postOnboardingSuggestions: [String] {
        PostOnboardingPromptSuggestions.suggestions()
    }

    private var shouldShowSuggestionBanner: Bool {
        !postOnboardingSuggestions.isEmpty && !PostOnboardingPromptSuggestions.isDismissed
    }

    private func dismissSuggestionBanner() {
        PostOnboardingPromptSuggestions.shouldShowPopup = false
        PostOnboardingPromptSuggestions.isDismissed = true
    }

    private func handleSuggestedPrompt(_ suggestion: String) {
        PostOnboardingPromptSuggestions.shouldShowPopup = false
        FloatingControlBarManager.shared.openAIInputWithQuery(suggestion)
    }

}

#Preview {
    DashboardPage(
        viewModel: DashboardViewModel(),
        appState: AppState(),
        appProvider: AppProvider(),
        chatProvider: ChatProvider(),
        selectedIndex: .constant(0)
    )
    .frame(width: 800, height: 600)
    .background(OmiColors.backgroundPrimary)
}
