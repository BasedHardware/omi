import Combine
import SwiftUI
import AppKit

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
    @ObservedObject var memoriesViewModel: MemoriesViewModel
    @ObservedObject private var deviceProvider = DeviceProvider.shared
    @Binding var selectedIndex: Int
    @State private var citedConversation: ServerConversation? = nil
    @State private var isLoadingCitation = false
    @State private var screenshotCount: Int?
    @State private var isCaptureMonitoring = false
    @State private var isTogglingCapture = false
    @State private var isTogglingListening = false
    @AppStorage("dashboardWidgetsCollapsed") private var widgetsCollapsed = false
    @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
    @AppStorage("transcriptionEnabled") private var transcriptionEnabled = true

    private var selectedApp: OmiApp? {
        guard let appId = chatProvider.selectedAppId else { return nil }
        return appProvider.chatApps.first { $0.id == appId }
    }

    private var captureStatus: HomeStatusState {
        if appState.isScreenCaptureKitBroken || appState.isScreenRecordingStale || !appState.hasScreenRecordingPermission {
            return .blocked
        }

        if screenAnalysisEnabled && isCaptureMonitoring {
            return .active
        }

        return .inactive
    }

    private var hasOmiDeviceHistory: Bool {
        deviceProvider.connectedDevice != nil || deviceProvider.pairedDevice != nil
    }

    var body: some View {
        redesignedHome
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(HomePalette.paper)
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
            syncCaptureState()
            Task { await loadScreenshotCount() }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            viewModel.refreshGoals()
            appState.checkAllPermissions()
            syncCaptureState()
            Task { await loadScreenshotCount() }
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            syncCaptureState()
        }
        .onReceive(NotificationCenter.default.publisher(for: .screenCapturePermissionLost)) { _ in
            syncCaptureState()
        }
        .onReceive(NotificationCenter.default.publisher(for: .screenCaptureKitBroken)) { _ in
            syncCaptureState()
        }
    }

    // MARK: - Redesigned Home

    private var redesignedHome: some View {
        GeometryReader { proxy in
            let panelHeight = min(max(proxy.size.height - 132, CGFloat(440)), CGFloat(640))
            let panelTop = max(CGFloat(82), (proxy.size.height - panelHeight) / 2)

            ZStack(alignment: .topTrailing) {
                HomeCanvasBackground()

                homeRoutingStage
                    .frame(maxWidth: 1120)
                    .padding(.horizontal, 34)
                    .frame(width: proxy.size.width)
                    .frame(height: panelHeight)
                    .position(x: proxy.size.width / 2, y: panelTop + panelHeight / 2)

                homeHeader
                    .padding(.horizontal, 34)
                    .padding(.top, 26)
            }
        }
    }

    private var homeHeader: some View {
        HStack {
            Spacer()
            HStack(spacing: 10) {
                HomeStatusButton(
                    title: "Capture",
                    systemImage: "viewfinder",
                    status: captureStatus,
                    isToggling: isTogglingCapture,
                    action: toggleCapture
                )

                HomeStatusButton(
                    title: "Listening",
                    systemImage: appState.isTranscribing ? "waveform.circle.fill" : "mic.circle",
                    status: appState.isTranscribing ? .active : .inactive,
                    isToggling: isTogglingListening,
                    action: toggleListening
                )

                HomeSettingsMenuButton(
                    onRefer: openReferFriend,
                    onDiscord: openDiscord,
                    onSettings: { navigate(to: .settings) }
                )
            }
        }
        .frame(height: 36)
    }

    private var homeRoutingStage: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .fill(HomePalette.panel)
                .overlay(
                    RoundedRectangle(cornerRadius: 30, style: .continuous)
                        .stroke(HomePalette.hairline.opacity(0.86), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.42), radius: 34, y: 18)

            HomeMemoryBridgeBackdrop()
                .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))

            HStack(alignment: .top, spacing: 28) {
                VStack(alignment: .leading, spacing: 12) {
                    sourceColumnHeader
                    sourceConstellation
                }
                .frame(width: 320)

                VStack(spacing: 12) {
                    centerMemoryHeader
                    homeMetricsStrip
                }
                .frame(width: 340)

                destinationStack
                    .frame(width: 300)
            }
            .frame(height: 318)
            .padding(26)
        }
    }

    private var sourceColumnHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Connect data")
                .font(.system(size: 20, weight: .medium, design: .serif))
                .foregroundStyle(HomePalette.ink)

            Text("Sources Omi learns from.")
                .scaledFont(size: 12, weight: .medium)
                .foregroundStyle(HomePalette.muted)
                .lineLimit(1)
        }
        .frame(height: 62, alignment: .bottomLeading)
    }

    private var centerMemoryHeader: some View {
        VStack(spacing: 2) {
            Text("omi.")
                .font(.system(size: 42, weight: .bold, design: .rounded))
                .foregroundStyle(HomePalette.ink)
                .lineLimit(1)
                .shadow(color: HomePalette.purple.opacity(0.42), radius: 20)

            Text("What omi knows")
                .font(.system(size: 15, weight: .medium, design: .serif))
                .foregroundStyle(HomePalette.secondary)
                .multilineTextAlignment(.center)
                .lineLimit(1)
        }
        .frame(height: 62, alignment: .bottom)
    }

    private var sourceConstellation: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                HomeSourceIconTile(title: "Gmail", brand: .gmail) {
                    openImportConnector("email")
                }

                HomeSourceIconTile(title: "Calendar", brand: .calendar) {
                    openImportConnector("calendar")
                }

                HomeSourceIconTile(title: "Files", brand: .localFiles, isConnected: true) {
                    openImportConnector("local-files")
                }
            }

            HStack(spacing: 10) {
                HomeSourceIconTile(title: "Notes", brand: .appleNotes) {
                    openImportConnector("apple-notes")
                }

                HomeSourceIconTile(
                    title: "Omi Device",
                    usesOmiDeviceImage: true,
                    isConnected: hasOmiDeviceHistory
                ) {
                    openOmiDeviceWebsite()
                }

                HomeSourceIconTile(title: "More", systemImage: "plus", isBrowse: true) {
                    openAppsPage()
                }
            }
        }
    }

    private var destinationStack: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Connect your AI")
                    .font(.system(size: 22, weight: .medium, design: .serif))
                    .foregroundStyle(HomePalette.ink)

                Text("Use Omi memory where you already work.")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundStyle(HomePalette.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(height: 62, alignment: .bottomLeading)

            HomeAIChoiceButton(title: "Claude", brand: .claude) {
                openExportDestination(.claude)
            }
            HomeAIChoiceButton(title: "ChatGPT", brand: .chatgpt) {
                openExportDestination(.chatgpt)
            }
            HomeAIChoiceButton(title: "Ask Omi", usesOmiMark: true) {
                navigate(to: .chat)
            }
            HomeAIChoiceButton(title: "More", brand: .agents) {
                openAppsPage()
            }
        }
    }

    private var homeMetricsStrip: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                HomeCenterMetricTile(
                    title: "Conversations",
                    value: formattedCount(appState.conversations.count),
                    systemImage: "text.bubble.fill",
                    action: { navigate(to: .conversations) }
                )
                HomeCenterMetricTile(
                    title: "Tasks",
                    value: formattedCount(incompleteTaskCount),
                    systemImage: "checklist",
                    action: { navigate(to: .tasks) }
                )
            }

            HStack(spacing: 8) {
                HomeCenterMetricTile(
                    title: "Memories",
                    value: formattedCount(memoriesViewModel.memories.count),
                    systemImage: "brain",
                    action: { navigate(to: .memories) }
                )
                HomeCenterMetricTile(
                    title: "Screenshots",
                    value: screenshotCount.map(formattedCount) ?? "—",
                    systemImage: "photo.on.rectangle.angled",
                    action: { navigate(to: .rewind) }
                )
            }
        }
        .frame(maxWidth: 300)
    }

    private func navigate(to item: SidebarNavItem) {
        selectedIndex = item.rawValue
        AnalyticsManager.shared.tabChanged(tabName: item.title)
    }

    private func openAppsPage() {
        navigate(to: .apps)
    }

    private func openImportConnector(_ connectorID: String) {
        navigate(to: .apps)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) {
            NotificationCenter.default.post(
                name: .desktopAutomationOpenImportRequested,
                object: nil,
                userInfo: ["connector": connectorID]
            )
        }
    }

    private func openExportDestination(_ destination: MemoryExportDestination) {
        navigate(to: .apps)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) {
            NotificationCenter.default.post(
                name: .desktopAutomationOpenExportRequested,
                object: nil,
                userInfo: ["destination": destination.rawValue]
            )
        }
    }

    private func openReferFriend() {
        if let url = URL(string: "https://affiliate.omi.me") {
            NSWorkspace.shared.open(url)
        }
    }

    private func openDiscord() {
        if let url = URL(string: "https://discord.com/invite/8MP3b9ymvx") {
            NSWorkspace.shared.open(url)
        }
    }

    private func openOmiDeviceWebsite() {
        if let url = URL(string: "https://www.omi.me") {
            NSWorkspace.shared.open(url)
        }
    }

    private func toggleListening() {
        let enabled = !appState.isTranscribing
        if enabled && !appState.hasMicrophonePermission {
            appState.requestMicrophonePermission()
            return
        }

        isTogglingListening = true
        transcriptionEnabled = enabled
        AssistantSettings.shared.transcriptionEnabled = enabled
        AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)
        NotificationCenter.default.post(
            name: .toggleTranscriptionRequested,
            object: nil,
            userInfo: ["enabled": enabled]
        )

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            isTogglingListening = false
        }
    }

    private func toggleCapture() {
        let enabled = !screenAnalysisEnabled
        isTogglingCapture = true

        if enabled {
            ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
            guard ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission else {
                screenAnalysisEnabled = false
                isCaptureMonitoring = false
                isTogglingCapture = false
                ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    ScreenCaptureService.requestAllScreenCapturePermissions()
                }
                return
            }
        }

        screenAnalysisEnabled = enabled
        AssistantSettings.shared.screenAnalysisEnabled = enabled
        AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

        if enabled {
            ProactiveAssistantsPlugin.shared.startMonitoring { success, _ in
                DispatchQueue.main.async {
                    isTogglingCapture = false
                    isCaptureMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
                    if !success {
                        screenAnalysisEnabled = false
                        AssistantSettings.shared.screenAnalysisEnabled = false
                        isCaptureMonitoring = false
                    }
                }
            }
        } else {
            ProactiveAssistantsPlugin.shared.stopMonitoring()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                isTogglingCapture = false
                isCaptureMonitoring = false
            }
        }
    }

    private func syncCaptureState() {
        ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
        screenAnalysisEnabled = AssistantSettings.shared.screenAnalysisEnabled
        isCaptureMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
    }

    private func loadScreenshotCount() async {
        let stats = await RewindIndexer.shared.getStats()
        await MainActor.run {
            screenshotCount = stats?.total
        }
    }

    private func formattedCount(_ count: Int) -> String {
        count.formatted()
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

// MARK: - Home Components

private enum HomePalette {
    static let paper = Color(red: 0.018, green: 0.019, blue: 0.021)
    static let panel = Color(red: 0.045, green: 0.046, blue: 0.052)
    static let tile = Color(red: 0.078, green: 0.078, blue: 0.088)
    static let tileHover = Color(red: 0.115, green: 0.103, blue: 0.142)
    static let ink = Color(red: 0.94, green: 0.925, blue: 0.89)
    static let secondary = Color(red: 0.78, green: 0.765, blue: 0.725)
    static let muted = Color(red: 0.49, green: 0.47, blue: 0.43)
    static let faint = Color(red: 0.36, green: 0.35, blue: 0.33)
    static let hairline = Color(red: 0.155, green: 0.155, blue: 0.172)
    static let green = Color(red: 0.17, green: 0.78, blue: 0.38)
    static let purple = Color(red: 0.48, green: 0.30, blue: 0.95)
    static let purpleSoft = Color(red: 0.28, green: 0.17, blue: 0.57)
    static let flowPink = Color(red: 1.0, green: 0.16, blue: 0.44)
}

private enum HomeRowStatus {
    case connect
    case connected
    case open
}

private enum HomeDestinationProminence {
    case primary
    case quiet
}

private struct HomeCanvasBackground: View {
    var body: some View {
        ZStack {
            HomePalette.paper

            RadialGradient(
                colors: [
                    HomePalette.purple.opacity(0.16),
                    HomePalette.purple.opacity(0.035),
                    .clear,
                ],
                center: .center,
                startRadius: 30,
                endRadius: 520
            )
            .blur(radius: 12)
        }
        .ignoresSafeArea()
    }
}

private struct HomeMemoryBridgeBackdrop: View {
    var body: some View {
        TimelineView(.animation) { timeline in
            GeometryReader { proxy in
                let width = proxy.size.width
                let height = proxy.size.height
                let progress = CGFloat(
                    timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 7.0) / 7.0)

                ZStack {
                    ForEach(0..<5, id: \.self) { index in
                        HomeFlowCloud(index: index, progress: progress, width: width, height: height)
                    }

                    ForEach(0..<14, id: \.self) { index in
                        HomeFlowParticle(index: index, progress: progress, width: width, height: height)
                    }
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct HomeFlowCloud: View {
    let index: Int
    let progress: CGFloat
    let width: CGFloat
    let height: CGFloat

    var body: some View {
        let baseX = CGFloat(0.13 + Double(index) * 0.19)
        let wave = CGFloat(sin(Double(progress) * Double.pi * 2 + Double(index) * 0.82))
        let drift = CGFloat(cos(Double(progress) * Double.pi * 2 + Double(index) * 0.55))
        let cloudWidth = width * (index == 2 ? 0.46 : 0.34)
        let cloudHeight = height * (index == 2 ? 0.42 : 0.32)
        let opacity = index == 2 ? 0.18 : 0.12

        Ellipse()
            .fill(
                RadialGradient(
                    colors: [
                        (index % 2 == 0 ? HomePalette.purple : HomePalette.flowPink).opacity(opacity),
                        HomePalette.purpleSoft.opacity(opacity * 0.58),
                        .clear,
                    ],
                    center: .center,
                    startRadius: 0,
                    endRadius: cloudWidth * 0.46
                )
            )
            .frame(width: cloudWidth, height: cloudHeight)
            .position(
                x: width * baseX + drift * width * 0.020,
                y: height * (0.47 + wave * 0.052)
            )
            .blur(radius: 36)
            .blendMode(.screen)
    }
}

private struct HomeFlowParticle: View {
    let index: Int
    let progress: CGFloat
    let width: CGFloat
    let height: CGFloat

    var body: some View {
        let base = CGFloat(index) / 14.0
        let wrapped = (base + progress).truncatingRemainder(dividingBy: 1)
        let wave = CGFloat(sin(Double(wrapped) * Double.pi * 2 + Double(index) * 0.72))
        let fade = min(max((wrapped < 0.5 ? wrapped : 1 - wrapped) * 2.4, 0), 1)
        let lane = CGFloat((index % 5) - 2) * 0.018
        let x = width * (-0.06 + wrapped * 1.12)
        let y = height * (0.49 + lane + wave * 0.052)
        let size = CGFloat(26 + (index % 4) * 9)
        let opacity = 0.04 + fade * 0.16

        Ellipse()
            .fill(
                RadialGradient(
                    colors: [
                        (index % 3 == 0 ? HomePalette.flowPink : HomePalette.purple).opacity(opacity),
                        HomePalette.purpleSoft.opacity(opacity * 0.46),
                        .clear,
                    ],
                    center: .center,
                    startRadius: 2,
                    endRadius: size
                )
            )
            .frame(width: size * 2.3, height: size * 1.12)
            .position(x: x, y: y)
            .rotationEffect(.degrees(Double(wave) * 9))
            .blur(radius: 15)
            .blendMode(.screen)
    }
}

private struct HomePrimaryRouteButton: View {
    let title: String
    let brand: ConnectorBrand
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                ConnectorBrandIcon(brand: brand, size: 20, cornerRadius: 6)

                Text(title)
                    .scaledFont(size: 13, weight: .semibold)
                    .lineLimit(1)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(minWidth: 118)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(HomePalette.green.opacity(isHovering ? 0.92 : 1))
            )
            .shadow(color: HomePalette.green.opacity(isHovering ? 0.22 : 0.12), radius: 12, y: 5)
            .contentShape(.rect(cornerRadius: 11))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("Connect \(title)")
    }
}

private struct HomeInlineAction: View {
    let title: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let action: () -> Void

    @State private var isHovering = false

    init(title: String, brand: ConnectorBrand, action: @escaping () -> Void) {
        self.title = title
        self.brand = brand
        self.systemImage = nil
        self.action = action
    }

    init(title: String, systemImage: String, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = systemImage
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                icon

                Text(title)
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .lineLimit(1)

                Image(systemName: "chevron.right")
                    .scaledFont(size: 9, weight: .bold)
                    .foregroundStyle(HomePalette.faint)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                Capsule(style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.72))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isHovering ? HomePalette.green.opacity(0.3) : HomePalette.hairline.opacity(0.42), lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }

    @ViewBuilder
    private var icon: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 18, cornerRadius: 5)
        } else if let systemImage {
            Image(systemName: systemImage)
                .scaledFont(size: 12, weight: .semibold)
                .foregroundStyle(HomePalette.secondary)
                .frame(width: 18, height: 18)
        }
    }
}

private struct HomeSourceIconTile: View {
    let title: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let usesOmiDeviceImage: Bool
    let isConnected: Bool
    let isBrowse: Bool
    let action: () -> Void

    @State private var isHovering = false

    init(
        title: String,
        brand: ConnectorBrand,
        isConnected: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.brand = brand
        self.systemImage = nil
        self.usesOmiDeviceImage = false
        self.isConnected = isConnected
        self.isBrowse = false
        self.action = action
    }

    init(
        title: String,
        systemImage: String,
        isBrowse: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.brand = nil
        self.systemImage = systemImage
        self.usesOmiDeviceImage = false
        self.isConnected = false
        self.isBrowse = isBrowse
        self.action = action
    }

    init(
        title: String,
        usesOmiDeviceImage: Bool,
        isConnected: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.brand = nil
        self.systemImage = nil
        self.usesOmiDeviceImage = usesOmiDeviceImage
        self.isConnected = isConnected
        self.isBrowse = false
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 9) {
                ZStack(alignment: .topTrailing) {
                    icon

                    if isConnected {
                        Circle()
                            .fill(HomePalette.green)
                            .frame(width: 9, height: 9)
                            .overlay(Circle().stroke(HomePalette.tile, lineWidth: 2))
                            .offset(x: 2, y: -2)
                    }
                }

                HStack(spacing: 4) {
                    Text(title)
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    if isBrowse {
                        Image(systemName: "chevron.right")
                            .scaledFont(size: 8, weight: .bold)
                            .foregroundStyle(HomePalette.faint)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 92)
            .background(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(isHovering ? HomePalette.purple.opacity(0.58) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? HomePalette.purple.opacity(0.16) : .clear, radius: 14)
            .contentShape(.rect(cornerRadius: 17))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(title)
    }

    @ViewBuilder
    private var icon: some View {
        if usesOmiDeviceImage {
            HomeOmiDeviceIcon(size: 42, cornerRadius: 12)
        } else if let brand {
            ConnectorBrandIcon(brand: brand, size: 42, cornerRadius: 12)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(0.05))
                Image(systemName: systemImage)
                    .scaledFont(size: 19, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
            .frame(width: 42, height: 42)
        }
    }
}

private struct HomeOmiDeviceIcon: View {
    let size: CGFloat
    let cornerRadius: CGFloat

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(Color.white.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                )

            if let deviceImage = OmiDeviceImage.shared {
                Image(nsImage: deviceImage)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .padding(size * 0.16)
            } else {
                Image(systemName: "wave.3.right.circle.fill")
                    .scaledFont(size: size * 0.45, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
        }
        .frame(width: size, height: size)
    }
}

private struct HomeDataSourceCard: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let actionTitle: String
    let isConnected: Bool
    let action: () -> Void

    @State private var isHovering = false

    init(
        title: String,
        subtitle: String,
        brand: ConnectorBrand,
        actionTitle: String,
        isConnected: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = brand
        self.systemImage = nil
        self.actionTitle = actionTitle
        self.isConnected = isConnected
        self.action = action
    }

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        actionTitle: String,
        isConnected: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = nil
        self.systemImage = systemImage
        self.actionTitle = actionTitle
        self.isConnected = isConnected
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                icon

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .scaledFont(size: 14, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 10)

                HStack(spacing: 5) {
                    if isConnected {
                        Circle()
                            .fill(HomePalette.green)
                            .frame(width: 5, height: 5)
                    }

                    Text(actionTitle)
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundStyle(isConnected ? HomePalette.green : HomePalette.secondary)
                        .lineLimit(1)

                    if !isConnected && actionTitle == "Browse" {
                        Image(systemName: "chevron.right")
                            .scaledFont(size: 9, weight: .bold)
                            .foregroundStyle(HomePalette.faint)
                    }
                }
                .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 11)
            .frame(height: 64)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(isHovering ? HomePalette.purple.opacity(0.5) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? HomePalette.purple.opacity(0.12) : .clear, radius: 12)
            .contentShape(.rect(cornerRadius: 15))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle), \(actionTitle)")
    }

    @ViewBuilder
    private var icon: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 36, cornerRadius: 10)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.white.opacity(0.04))
                Image(systemName: systemImage)
                    .scaledFont(size: 17, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
            .frame(width: 36, height: 36)
        }
    }
}

private struct HomeAIChoiceButton: View {
    let title: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let usesOmiMark: Bool
    let isPrimary: Bool
    let action: () -> Void

    @State private var isHovering = false

    init(title: String, brand: ConnectorBrand, isPrimary: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = brand
        self.systemImage = nil
        self.usesOmiMark = false
        self.isPrimary = isPrimary
        self.action = action
    }

    init(title: String, systemImage: String, isPrimary: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = systemImage
        self.usesOmiMark = false
        self.isPrimary = isPrimary
        self.action = action
    }

    init(title: String, usesOmiMark: Bool, isPrimary: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = nil
        self.usesOmiMark = usesOmiMark
        self.isPrimary = isPrimary
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                icon

                Text(title)
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundStyle(HomePalette.ink)
                    .lineLimit(1)

                Spacer(minLength: 8)

                Image(systemName: "chevron.right")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundStyle(HomePalette.faint)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .frame(height: 48)
            .frame(maxWidth: .infinity)
            .background(buttonBackground)
            .overlay(buttonStroke)
            .contentShape(.rect(cornerRadius: 15))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(title)
    }

    @ViewBuilder
    private var icon: some View {
        if usesOmiMark {
            HomeOmiMarkIcon(size: 24, cornerRadius: 7)
        } else if let brand {
            ConnectorBrandIcon(brand: brand, size: 24, cornerRadius: 7)
        } else if let systemImage {
            Image(systemName: systemImage)
                .scaledFont(size: 14, weight: .bold)
                .foregroundStyle(HomePalette.purple)
                .frame(width: 24, height: 24)
        }
    }

    private var buttonBackground: some View {
        RoundedRectangle(cornerRadius: 15, style: .continuous)
            .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
    }

    private var buttonStroke: some View {
        RoundedRectangle(cornerRadius: 15, style: .continuous)
            .stroke(
                HomePalette.hairline.opacity(isHovering ? 1 : 0.9),
                lineWidth: 1
            )
    }
}

private struct HomeOmiMarkIcon: View {
    let size: CGFloat
    let cornerRadius: CGFloat

    private static let markImage: NSImage? = {
        guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(Color.white.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                )

            if let image = Self.markImage {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .padding(size * 0.18)
            } else {
                OmiDotRing()
                    .frame(width: size * 0.58, height: size * 0.58)
            }
        }
        .frame(width: size, height: size)
    }
}

private struct OmiDotRing: View {
    var body: some View {
        ZStack {
            ForEach(0..<8, id: \.self) { index in
                Circle()
                    .fill(HomePalette.ink)
                    .frame(width: 3.5, height: 3.5)
                    .offset(y: -6)
                    .rotationEffect(.degrees(Double(index) * 45))
            }
        }
    }
}

private struct HomeOrbitButton: View {
    let title: String
    let brand: ConnectorBrand
    let badge: String?
    let action: () -> Void

    @State private var isHovering = false

    init(title: String, brand: ConnectorBrand, badge: String? = nil, action: @escaping () -> Void) {
        self.title = title
        self.brand = brand
        self.badge = badge
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                ZStack(alignment: .topTrailing) {
                    ConnectorBrandIcon(brand: brand, size: 44, cornerRadius: 13)
                        .shadow(color: .black.opacity(isHovering ? 0.16 : 0.08), radius: 9, y: 4)

                    if let badge {
                        Text(badge)
                            .scaledFont(size: 8, weight: .bold)
                            .foregroundStyle(.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(Capsule(style: .continuous).fill(HomePalette.green))
                            .offset(x: 8, y: -6)
                    }
                }

                Text(title)
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .lineLimit(1)
            }
            .padding(8)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(isHovering ? HomePalette.panel : Color.clear)
            )
            .contentShape(.rect(cornerRadius: 16))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(title)
    }
}

private struct HomeDestinationCapsule: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                ConnectorBrandIcon(brand: brand, size: 34, cornerRadius: 9)

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 11, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.green : HomePalette.faint)
            }
            .padding(11)
            .background(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.82))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(isHovering ? HomePalette.green.opacity(0.32) : HomePalette.hairline.opacity(0.45), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 15))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle)")
    }
}

private struct HomeCommandCard: View {
    let onChatGPT: () -> Void
    let onClaude: () -> Void
    let onAskOmi: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                Text("Connect Omi to ChatGPT, Claude, or ask Omi directly...")
                    .scaledFont(size: 15, weight: .regular)
                    .foregroundStyle(HomePalette.faint)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 2)

                Button(action: onAskOmi) {
                    Image(systemName: "arrow.up.circle")
                        .scaledFont(size: 24, weight: .regular)
                        .foregroundStyle(HomePalette.faint)
                }
                .buttonStyle(.plain)
                .help("Ask Omi")
            }
            .padding(.horizontal, 18)
            .padding(.top, 18)
            .padding(.bottom, 24)

            HStack(spacing: 9) {
                Button(action: onChatGPT) {
                    HStack(spacing: 8) {
                        ConnectorBrandIcon(brand: .chatgpt, size: 22, cornerRadius: 6)
                        Text("Connect ChatGPT")
                            .scaledFont(size: 13, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .foregroundStyle(.white)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(HomePalette.green)
                    )
                }
                .buttonStyle(.plain)

                Button(action: onClaude) {
                    HStack(spacing: 8) {
                        ConnectorBrandIcon(brand: .claude, size: 22, cornerRadius: 6)
                        Text("Claude")
                            .scaledFont(size: 13, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .foregroundStyle(HomePalette.secondary)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(HomePalette.tile)
                    )
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
        }
        .background(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .fill(HomePalette.panel)
                .shadow(color: .black.opacity(0.10), radius: 16, y: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(HomePalette.hairline.opacity(0.72), lineWidth: 1)
        )
        .frame(maxWidth: 720)
    }
}

private struct HomeSourceTile: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let status: HomeRowStatus
    let action: () -> Void

    @State private var isHovering = false

    init(
        title: String,
        subtitle: String,
        brand: ConnectorBrand,
        status: HomeRowStatus = .connect,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = brand
        self.systemImage = nil
        self.status = status
        self.action = action
    }

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        status: HomeRowStatus = .connect,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = nil
        self.systemImage = systemImage
        self.status = status
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top) {
                    iconView
                    Spacer()
                    statusView
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 11)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }
            }
            .padding(10)
            .frame(minHeight: 78, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(isHovering ? HomePalette.green.opacity(0.4) : HomePalette.hairline.opacity(0.3), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 9))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle)")
    }

    @ViewBuilder
    private var iconView: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 28, cornerRadius: 7)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(HomePalette.panel)
                Image(systemName: systemImage)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
            .frame(width: 28, height: 28)
        }
    }

    @ViewBuilder
    private var statusView: some View {
        switch status {
        case .connect:
            Image(systemName: "plus")
                .scaledFont(size: 11, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
        case .connected:
            Image(systemName: "checkmark")
                .scaledFont(size: 11, weight: .bold)
                .foregroundStyle(HomePalette.green)
        case .open:
            Image(systemName: "chevron.right")
                .scaledFont(size: 11, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
        }
    }
}

private struct HomeCenterMetricTile: View {
    let title: String
    let value: String
    let systemImage: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Image(systemName: systemImage)
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)

                    Spacer(minLength: 8)

                    Image(systemName: "arrow.up.right")
                        .scaledFont(size: 9, weight: .bold)
                        .foregroundStyle(isHovering ? HomePalette.flowPink : HomePalette.faint)
                }

                Text(value)
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(HomePalette.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)

                Text(title)
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundStyle(HomePalette.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.82)
            }
            .padding(10)
            .frame(width: 146, height: 82, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.92))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(isHovering ? HomePalette.flowPink.opacity(0.5) : HomePalette.hairline.opacity(0.82), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 15))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(value)")
    }
}

private struct HomeMemoryMetricCard: View {
    let title: String
    let value: String
    let systemImage: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color.white.opacity(0.055))

                    Image(systemName: systemImage)
                        .scaledFont(size: 15, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                }
                .frame(width: 42, height: 42)

                VStack(alignment: .leading, spacing: 2) {
                    Text(value)
                        .font(.system(size: 21, weight: .medium, design: .serif))
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    Text(title)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.purple : HomePalette.faint)
            }
            .padding(.horizontal, 14)
            .frame(height: 76)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(isHovering ? HomePalette.purple.opacity(0.56) : HomePalette.hairline.opacity(0.86), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 17))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(value)")
    }
}

private struct HomeMetricPill: View {
    let title: String
    let value: String
    let systemImage: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: systemImage)
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)

                Text(value)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(HomePalette.ink)

                Text(title)
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundStyle(HomePalette.muted)
                    .lineLimit(1)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
            .background(
                Capsule(style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.panel)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isHovering ? HomePalette.green.opacity(0.34) : HomePalette.hairline.opacity(0.64), lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(value)")
    }
}

private struct HomeGlassPanel<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(HomePalette.panel)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(HomePalette.hairline.opacity(0.8), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.08), radius: 14, y: 6)
    }
}

private struct HomeStageHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(eyebrow.uppercased())
                .scaledFont(size: 10, weight: .bold)
                .foregroundStyle(HomePalette.green)

            Text(title)
                .scaledFont(size: 18, weight: .semibold)
                .foregroundStyle(HomePalette.ink)
                .lineLimit(1)

            Text(subtitle)
                .scaledFont(size: 12)
                .foregroundStyle(HomePalette.muted)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(2)
        }
    }
}

private struct HomeBridgeChevron: View {
    var body: some View {
        VStack(spacing: 8) {
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, OmiColors.border.opacity(0.65), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 1, height: 150)

            Image(systemName: "chevron.right")
                .scaledFont(size: 16, weight: .bold)
                .foregroundStyle(OmiColors.textTertiary)
        }
        .frame(width: 22)
        .accessibilityHidden(true)
    }
}

private struct HomeSourceRow: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let status: HomeRowStatus
    let action: () -> Void

    @State private var isHovering = false

    init(
        title: String,
        subtitle: String,
        brand: ConnectorBrand,
        status: HomeRowStatus = .connect,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = brand
        self.systemImage = nil
        self.status = status
        self.action = action
    }

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        status: HomeRowStatus = .connect,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = nil
        self.systemImage = systemImage
        self.status = status
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                rowIcon

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 11)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                statusView
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(isHovering ? Color.white.opacity(0.08) : Color.white.opacity(0.035))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(isHovering ? OmiColors.success.opacity(0.28) : Color.white.opacity(0.06), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 13))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle)")
    }

    @ViewBuilder
    private var rowIcon: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 32, cornerRadius: 8)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(OmiColors.backgroundPrimary.opacity(0.78))
                Image(systemName: systemImage)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(OmiColors.textSecondary)
            }
            .frame(width: 32, height: 32)
        }
    }

    @ViewBuilder
    private var statusView: some View {
        switch status {
        case .connect:
            Image(systemName: "plus")
                .scaledFont(size: 12, weight: .bold)
                .foregroundStyle(OmiColors.success)
        case .connected:
            Image(systemName: "checkmark")
                .scaledFont(size: 12, weight: .bold)
                .foregroundStyle(OmiColors.success)
        case .open:
            Image(systemName: "chevron.right")
                .scaledFont(size: 12, weight: .bold)
                .foregroundStyle(OmiColors.success)
        }
    }
}

private struct HomeDestinationRow: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let prominence: HomeDestinationProminence
    let action: () -> Void

    @State private var isHovering = false

    init(
        title: String,
        subtitle: String,
        brand: ConnectorBrand,
        prominence: HomeDestinationProminence = .primary,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = brand
        self.systemImage = nil
        self.prominence = prominence
        self.action = action
    }

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        prominence: HomeDestinationProminence = .primary,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.subtitle = subtitle
        self.brand = nil
        self.systemImage = systemImage
        self.prominence = prominence
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                rowIcon

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundStyle(prominence == .primary ? HomePalette.ink : HomePalette.secondary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 11)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 11, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.green : HomePalette.faint)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 10)
            .background(rowBackground)
            .overlay(rowStroke)
            .contentShape(.rect(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle)")
    }

    @ViewBuilder
    private var rowIcon: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 34, cornerRadius: 9)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(HomePalette.tile)
                Image(systemName: systemImage)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
            .frame(width: 34, height: 34)
        }
    }

    private var rowBackground: some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(
                prominence == .primary
                    ? HomePalette.green.opacity(isHovering ? 0.20 : 0.12)
                    : (isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
    }

    private var rowStroke: some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(
                prominence == .primary
                    ? HomePalette.green.opacity(isHovering ? 0.42 : 0.24)
                    : HomePalette.hairline.opacity(isHovering ? 0.7 : 0.4),
                lineWidth: 1
            )
    }
}

private struct HomeMetricTile: View {
    let title: String
    let value: String
    let systemImage: String
    let accent: Color
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 7) {
                HStack {
                    Image(systemName: systemImage)
                        .scaledFont(size: 13, weight: .semibold)
                        .foregroundStyle(accent)

                    Spacer()

                    Image(systemName: "arrow.up.right")
                        .scaledFont(size: 10, weight: .bold)
                        .foregroundStyle(isHovering ? accent : OmiColors.textQuaternary)
                }

                Text(value)
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundStyle(OmiColors.textPrimary)
                    .lineLimit(1)

                Text(title)
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundStyle(OmiColors.textTertiary)
                    .lineLimit(1)
            }
            .padding(11)
            .frame(minHeight: 86, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.white.opacity(isHovering ? 0.08 : 0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(isHovering ? accent.opacity(0.34) : Color.white.opacity(0.07), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 16))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(value)")
    }
}

private struct HomeSectionHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .scaledFont(size: 20, weight: .semibold)
                .foregroundStyle(OmiColors.textPrimary)

            Text(subtitle)
                .scaledFont(size: 12)
                .foregroundStyle(OmiColors.textTertiary)
        }
    }
}

private enum HomeStatusState {
    case active
    case inactive
    case blocked

    var indicator: Color {
        switch self {
        case .active:
            return HomePalette.green
        case .inactive:
            return HomePalette.faint
        case .blocked:
            return Color(red: 1.0, green: 0.24, blue: 0.30)
        }
    }

    var text: String {
        switch self {
        case .active:
            return "On"
        case .inactive:
            return "Off"
        case .blocked:
            return "Blocked"
        }
    }

    var isActive: Bool {
        if case .active = self { return true }
        return false
    }

    var isBlocked: Bool {
        if case .blocked = self { return true }
        return false
    }
}

private struct HomeStatusButton: View {
    let title: String
    let systemImage: String
    let status: HomeStatusState
    let isToggling: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                ZStack {
                    if isToggling {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.55)
                    } else {
                        Image(systemName: systemImage)
                            .scaledFont(size: 13, weight: .semibold)
                    }
                }
                .frame(width: 18, height: 18)

                Text(title)
                    .scaledFont(size: 12, weight: .semibold)
                    .lineLimit(1)

                Circle()
                    .fill(status.indicator)
                    .frame(width: 6, height: 6)
            }
            .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                Capsule(style: .continuous)
                    .fill(statusFill)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(statusStroke, lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(isToggling)
        .onHover { isHovering = $0 }
        .help("\(title): \(status.text)")
        .accessibilityLabel("\(title) \(status.text)")
    }

    private var statusFill: Color {
        if status.isActive {
            return HomePalette.green.opacity(isHovering ? 0.20 : 0.12)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.16 : 0.10)
        }
        return isHovering ? HomePalette.tileHover : HomePalette.panel
    }

    private var statusStroke: Color {
        if status.isActive {
            return HomePalette.green.opacity(0.38)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.54 : 0.38)
        }
        return HomePalette.hairline.opacity(isHovering ? 0.8 : 0.58)
    }
}

private struct HomeIconActionButton: View {
    let title: String
    let systemImage: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .scaledFont(size: 14, weight: .semibold)
                .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.muted)
                .frame(width: 34, height: 34)
                .background(
                    Circle()
                        .fill(isHovering ? HomePalette.tileHover : HomePalette.panel)
                )
                .overlay(
                    Circle()
                        .stroke(HomePalette.hairline.opacity(isHovering ? 0.8 : 0.58), lineWidth: 1)
                )
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help(title)
        .accessibilityLabel(title)
    }
}

private struct HomeSettingsMenuButton: View {
    let onRefer: () -> Void
    let onDiscord: () -> Void
    let onSettings: () -> Void

    @State private var isHovering = false
    @State private var isPresented = false

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            ZStack {
                Circle()
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.86))
                    .overlay(
                        Circle()
                            .stroke(HomePalette.hairline.opacity(isHovering ? 0.9 : 0.68), lineWidth: 1)
                    )

                Image(systemName: "gearshape.fill")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)
            }
            .frame(width: 34, height: 34)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .popover(isPresented: $isPresented, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: 4) {
                popoverButton(title: "Refer a Friend", systemImage: "gift.fill") {
                    isPresented = false
                    onRefer()
                }

                popoverButton(title: "Discord", systemImage: "message.fill") {
                    isPresented = false
                    onDiscord()
                }

                Divider()
                    .padding(.vertical, 3)

                popoverButton(title: "Settings", systemImage: "gearshape.fill") {
                    isPresented = false
                    onSettings()
                }
            }
            .padding(8)
            .frame(width: 190)
            .background(HomePalette.panel)
        }
        .help("Settings")
        .accessibilityLabel("Settings menu")
    }

    private func popoverButton(title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .frame(width: 18)

                Text(title)
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundStyle(HomePalette.ink)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .contentShape(.rect(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }
}

private struct HomeConnectorCard: View {
    let title: String
    let subtitle: String
    let brand: ConnectorBrand
    let actionTitle: String
    let status: String?
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ConnectorBrandIcon(brand: brand, size: 36, cornerRadius: 9)

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .scaledFont(size: 14, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: 12)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 10)

                if let status {
                    HStack(spacing: 5) {
                        Image(systemName: "checkmark")
                            .scaledFont(size: 10, weight: .bold)
                        Text(status)
                            .scaledFont(size: 12, weight: .semibold)
                    }
                    .foregroundStyle(OmiColors.success)
                    .lineLimit(1)
                } else {
                    HStack(spacing: 5) {
                        Image(systemName: "plus")
                            .scaledFont(size: 10, weight: .bold)
                        Text(actionTitle)
                            .scaledFont(size: 12, weight: .semibold)
                    }
                    .foregroundStyle(OmiColors.success)
                    .lineLimit(1)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(minHeight: 56)
            .background(cardBackground)
            .overlay(cardStroke)
            .contentShape(.rect(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(status ?? actionTitle)")
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.94 : 0.72))
    }

    private var cardStroke: some View {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
            .stroke(
                isHovering ? OmiColors.success.opacity(0.32) : OmiColors.border.opacity(0.42),
                lineWidth: 1
            )
    }
}

private struct HomeMoreAppsCard: View {
    let action: () -> Void
    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(OmiColors.backgroundPrimary)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(OmiColors.border.opacity(0.55), lineWidth: 1)
                        )

                    Image(systemName: "square.grid.2x2.fill")
                        .scaledFont(size: 15, weight: .semibold)
                        .foregroundStyle(OmiColors.textSecondary)
                }
                .frame(width: 36, height: 36)

                VStack(alignment: .leading, spacing: 3) {
                    Text("Connect more")
                        .scaledFont(size: 14, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)

                    Text("Browse all apps")
                        .scaledFont(size: 12)
                        .foregroundStyle(OmiColors.textTertiary)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundStyle(OmiColors.success)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(minHeight: 56)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.94 : 0.72))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(
                        isHovering ? OmiColors.success.opacity(0.32) : OmiColors.border.opacity(0.42),
                        lineWidth: 1
                    )
            )
            .contentShape(.rect(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

private struct HomeFlowArrow: View {
    var body: some View {
        VStack(spacing: 5) {
            Rectangle()
                .fill(OmiColors.border.opacity(0.75))
                .frame(width: 1, height: 14)

            Image(systemName: "chevron.down")
                .scaledFont(size: 12, weight: .semibold)
                .foregroundStyle(OmiColors.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }
}

private struct HomeMetricCard: View {
    let title: String
    let value: String
    let subtitle: String
    let systemImage: String
    let accent: Color
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(accent.opacity(0.16))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(accent.opacity(0.28), lineWidth: 1)
                        )

                    Image(systemName: systemImage)
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundStyle(accent)
                }
                .frame(width: 38, height: 38)

                VStack(alignment: .leading, spacing: 3) {
                    Text(value)
                        .scaledFont(size: 20, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(title)
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundStyle(isHovering ? accent : OmiColors.textQuaternary)
            }
            .padding(12)
            .frame(minHeight: 64)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.96 : 0.78))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(isHovering ? accent.opacity(0.34) : OmiColors.border.opacity(0.44), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(value), \(subtitle)")
    }
}

private struct HomeAIButton: View {
    let title: String
    let brand: ConnectorBrand?
    let systemImage: String?
    let action: () -> Void

    @State private var isHovering = false

    init(title: String, brand: ConnectorBrand, action: @escaping () -> Void) {
        self.title = title
        self.brand = brand
        self.systemImage = nil
        self.action = action
    }

    init(title: String, systemImage: String, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = systemImage
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let brand {
                    ConnectorBrandIcon(brand: brand, size: 26, cornerRadius: 7)
                } else if let systemImage {
                    ZStack {
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .fill(OmiColors.backgroundTertiary)
                        Image(systemName: systemImage)
                            .scaledFont(size: 12, weight: .semibold)
                            .foregroundStyle(OmiColors.textSecondary)
                    }
                    .frame(width: 26, height: 26)
                }

                Text(title)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(OmiColors.textSecondary)
                    .lineLimit(1)

                Image(systemName: "chevron.right")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundStyle(isHovering ? OmiColors.success : OmiColors.textQuaternary)
            }
            .padding(.leading, 9)
            .padding(.trailing, 12)
            .padding(.vertical, 7)
            .background(
                Capsule(style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.96 : 0.76))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isHovering ? OmiColors.success.opacity(0.32) : OmiColors.border.opacity(0.42), lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(title)
    }
}

#Preview {
    DashboardPage(
        viewModel: DashboardViewModel(),
        appState: AppState(),
        appProvider: AppProvider(),
        chatProvider: ChatProvider(),
        memoriesViewModel: MemoriesViewModel(),
        selectedIndex: .constant(0)
    )
    .frame(width: 800, height: 600)
    .background(OmiColors.backgroundPrimary)
}
