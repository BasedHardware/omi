import Combine
import SwiftUI
import AppKit
import UniformTypeIdentifiers
import OmiTheme

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
        async let tasksTask: Void = tasksStore.refreshDashboardTasksFromServer()
        async let goalsTask: Void = loadGoals()

        let _ = await (scoreTask, tasksTask, goalsTask)

        isLoading = false
    }

    func loadCachedDashboardData() async {
        await loadGoalsFromLocalSnapshot()
    }

    func resetSessionState() {
        scoreResponse = nil
        goals = []
        isLoading = false
        error = nil
        lastGoalRefreshTime = .distantPast
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
            await loadGoalsFromLocalSnapshot()
        }
    }

    private func loadGoalsFromLocalSnapshot() async {
        do {
            goals = try await GoalStorage.shared.getLocalGoals()
        } catch {
            logError("Failed to load goals from local storage", error: error)
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
    @StateObject private var importConnectorStatusStore = ImportConnectorStatusStore()
    @Binding var selectedIndex: Int
    @State private var citedConversation: ServerConversation? = nil
    @State private var selectedCatalogApp: OmiApp?
    @State private var selectedImportConnector: ImportConnector?
    @State private var selectedExportDestination: MemoryExportDestination?
    @State private var isShowingAppsPopup = false
    @State private var appsPopupAcceptsInput = false
    @State private var homeConnectSheetAcceptsInput = false
    @State private var appsPopupInitialSection: AppsCatalogInitialSection = .imports
    @State private var appsPopupPresentationID = UUID()
    @State private var isLoadingCitation = false
    @State private var screenshotCount: Int?
    // True totals for the "What omi knows" tiles. Without these the tiles showed
    // only the loaded page (~50 conversations, ~100 memories), badly undercounting.
    @State private var conversationCount: Int?
    @State private var memoryCount: Int?
    @State private var taskCount: Int?
    // Wearable used on this account (any friend/omi-sourced conversation).
    // Seeded from UserDefaults so the badge is instant on later launches.
    @State private var accountHasOmiDeviceConversations = UserDefaults.standard.bool(
        forKey: DashboardPage.omiDeviceHistoryDefaultsKey)
    @State private var memoryExportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]
    @State private var lastHomeStatusRefreshAt = Date.distantPast
    @State private var isCaptureMonitoring = false
    @State private var isTogglingCapture = false
    @State private var isTogglingListening = false
    @AppStorage("dashboardWidgetsCollapsed") private var widgetsCollapsed = false
    @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
    @AppStorage("transcriptionEnabled") private var transcriptionEnabled = true
    @AppStorage("systemAudioCaptureMode") private var systemAudioCaptureModeRaw =
        AssistantSettings.SystemAudioCaptureMode.onlyDuringMeetings.rawValue
    @AppStorage("useLegacyHomeDesign") private var useLegacyHomeDesign = false
    @State private var homeMode: HomeStageMode = .hub
    @FocusState private var homeAskFieldFocused: Bool

    private var selectedApp: OmiApp? {
        guard let appId = chatProvider.selectedAppId else { return nil }
        return appProvider.chatApps.first { $0.id == appId }
    }

    private var captureStatus: HomeStatusState {
        if appState.isScreenCaptureKitBroken || appState.isScreenRecordingStale || !appState.hasScreenRecordingPermission {
            return .blocked
        }

        if isCaptureLive {
            return .active
        }

        return .inactive
    }

    private var isCaptureLive: Bool {
        isCaptureMonitoring || ProactiveAssistantsPlugin.shared.isMonitoring
    }

    private var listeningCaptureMode: AssistantSettings.SystemAudioCaptureMode {
        AssistantSettings.SystemAudioCaptureMode(rawValue: systemAudioCaptureModeRaw) ?? .onlyDuringMeetings
    }

    private var listeningModeTitle: String {
        switch listeningCaptureMode {
        case .always:
            return "Always"
        case .onlyDuringMeetings:
            return appState.isAwaitingMeeting ? "Meetings only" : "In meeting"
        case .never:
            return "Mic only"
        }
    }

    private static let omiDeviceHistoryDefaultsKey = "home-omi-device-account-history"
    private static let homeStageMaxWidth: CGFloat = 1120
    private static let homeStageHorizontalPadding: CGFloat = 34
    private static let homeAskBarMaxWidth: CGFloat = 640
    private static let homeStagePanelMaxWidth: CGFloat = 780
    private static let homeStageAnimation = Animation.spring(response: 0.46, dampingFraction: 0.86)
    private static let appsPopupMaxWidth: CGFloat = 1040
    private static let appsPopupMaxHeight: CGFloat = 600
    private static let appsPopupMinWidth: CGFloat = 360
    private static let appsPopupMinHeight: CGFloat = 360
    private static let appsPopupHorizontalMargin: CGFloat = 48
    private static let appsPopupVerticalMargin: CGFloat = 32
    private static let appsPopupCornerRadius: CGFloat = 22
    private static let homeConnectSheetHorizontalMargin: CGFloat = 56
    private static let homeConnectSheetVerticalMargin: CGFloat = 44
    private static let homeConnectSheetMinWidth: CGFloat = 360
    private static let homeConnectSheetMinHeight: CGFloat = 360
    private static let homeConnectSheetCornerRadius: CGFloat = 24
    private static let appDetailSheetPreferredSize = CGSize(width: 500, height: 600)
    private static let importConnectorSheetPreferredSize = CGSize(width: 520, height: 500)
    private static let exportDestinationSheetPreferredSize = CGSize(width: 520, height: 560)

    private var homeConnectSheetIsPresented: Bool {
        selectedCatalogApp != nil || selectedImportConnector != nil || selectedExportDestination != nil
    }

    private var isHomeModalPresented: Bool {
        isShowingAppsPopup || homeConnectSheetIsPresented
    }

    private var legacySelectedCatalogApp: Binding<OmiApp?> {
        Binding(
            get: { useLegacyHomeDesign ? selectedCatalogApp : nil },
            set: { selectedCatalogApp = $0 }
        )
    }

    private var legacySelectedImportConnector: Binding<ImportConnector?> {
        Binding(
            get: { useLegacyHomeDesign ? selectedImportConnector : nil },
            set: { selectedImportConnector = $0 }
        )
    }

    private var legacySelectedExportDestination: Binding<MemoryExportDestination?> {
        Binding(
            get: { useLegacyHomeDesign ? selectedExportDestination : nil },
            set: { selectedExportDestination = $0 }
        )
    }

    private var hasOmiDeviceHistory: Bool {
        deviceProvider.connectedDevice != nil || deviceProvider.pairedDevice != nil
            || accountHasOmiDeviceConversations
    }

    /// Real persisted import-connector state (UserDefaults-backed via ImportConnectorStatusStore).
    private func isImportConnectorConnected(_ connectorID: String) -> Bool {
        guard let connector = ImportConnector.all.first(where: { $0.id == connectorID }) else { return false }
        return importConnectorStatusStore.snapshot(for: connector).isConnected
    }

    private func isMCPDestinationConnected(_ destination: MemoryExportDestination) -> Bool {
        switch destination {
        case .claude, .claudeCode:
            return [.claude, .claudeCode].contains { memoryExportStatuses[$0]?.hasConnection == true }
        case .chatgpt, .codex:
            return [.chatgpt, .codex].contains { memoryExportStatuses[$0]?.hasConnection == true }
        default:
            return memoryExportStatuses[destination]?.hasConnection == true
        }
    }

    var body: some View {
        Group {
            if useLegacyHomeDesign {
                legacyHome
            } else {
                redesignedHome
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(useLegacyHomeDesign ? Color.clear : HomePalette.paper)
        .sheet(item: $citedConversation) { conversation in
            ConversationDetailView(
                conversation: conversation,
                onBack: {
                    citedConversation = nil
                }
            )
            .frame(minWidth: 500, minHeight: 500)
        }
        .dismissableSheet(item: legacySelectedCatalogApp) { app in
            AppDetailSheet(app: app, appProvider: appProvider, onDismiss: { selectedCatalogApp = nil })
                .frame(width: 500, height: 650)
                .onAppear {
                    AnalyticsManager.shared.appDetailViewed(appId: app.id, appName: app.name)
                }
        }
        .dismissableSheet(item: legacySelectedImportConnector) { connector in
            ImportConnectorSheet(
                connector: connector,
                appState: appState,
                statusStore: importConnectorStatusStore,
                onDismiss: {
                    selectedImportConnector = nil
                }
            )
            .frame(width: 520, height: 620)
        }
        .dismissableSheet(item: legacySelectedExportDestination) { destination in
            ConnectDestinationSheet(
                destination: destination,
                statuses: $memoryExportStatuses,
                onDismiss: {
                    selectedExportDestination = nil
                }
            )
            .frame(width: 520, height: 620)
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
            reportHomeAutomationMode()
            Task { await refreshHomeStatusData(force: true) }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            viewModel.refreshGoals()
            appState.checkAllPermissions()
            syncCaptureState()
            Task { await refreshHomeStatusData(force: false) }
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
        // Clicking into the ask bar reveals the inline chat; the same is true
        // when focus lands there via keyboard (Tab / Full Keyboard Access).
        .onChange(of: homeAskFieldFocused) { _, focused in
            if focused && !useLegacyHomeDesign && homeMode != .chat {
                openHomeChat()
            }
        }
        // Automation-bridge entry points (home_open_chat / home_connect_toggle /
        // home_close_panel / home_ask) — they call the exact functions the
        // on-screen controls call.
        .onReceive(NotificationCenter.default.publisher(for: .homeStageOpenChat)) { _ in
            guard !useLegacyHomeDesign else { return }
            openHomeChat()
        }
        .onReceive(NotificationCenter.default.publisher(for: .homeStageToggleConnect)) { _ in
            guard !useLegacyHomeDesign else { return }
            toggleHomeConnectPanel()
        }
        .onReceive(NotificationCenter.default.publisher(for: .homeStageClose)) { _ in
            guard !useLegacyHomeDesign else { return }
            closeHomeStagePanel()
        }
        .onReceive(NotificationCenter.default.publisher(for: .homeStageAsk)) { note in
            guard !useLegacyHomeDesign,
                  let query = note.userInfo?["query"] as? String else { return }
            askHomeSuggestion(query)
        }
        .onReceive(NotificationCenter.default.publisher(for: .homeStageAttach)) { note in
            guard !useLegacyHomeDesign,
                  let path = note.userInfo?["path"] as? String else { return }
            // Same wiring the ask bar's paperclip/drag-drop runs after the
            // OS hands back file URLs.
            if let attachment = ChatAttachment.from(url: URL(fileURLWithPath: path)) {
                chatProvider.addAttachments([attachment])
            }
        }
    }

    private var legacyHome: some View {
        VStack(spacing: 0) {
            dashboardWidgets

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
                localSendToken: chatProvider.localSendToken,
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
                        messageLength: text.count,
                        hasContext: selectedApp != nil,
                        source: "dashboard_chat"
                    )
                    Task { await chatProvider.sendMessage(text) }
                },
                onFollowUp: { text in
                    Task { await chatProvider.sendFollowUp(text) }
                },
                onStop: {
                    chatProvider.stopAgent(owner: .mainChat)
                },
                isSending: chatProvider.isSending,
                isStopping: chatProvider.isStopping,
                placeholder: "Ask omi anything",
                mode: $chatProvider.chatMode,
                inputText: $chatProvider.draftText,
                attachments: $chatProvider.pendingAttachments,
                onAttachmentsAdded: { urls in
                    let toAdd = urls.compactMap { ChatAttachment.from(url: $0) }
                    chatProvider.addAttachments(toAdd)
                },
                onAttachmentRemoved: { id in
                    chatProvider.removePendingAttachment(id: id)
                }
            )
            .padding(.horizontal, 30)
            .padding(.top, 12)
            .padding(.bottom, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
    }

    // MARK: - Redesigned Home

    private var redesignedHome: some View {
        GeometryReader { proxy in
            let panelHeight = min(max(proxy.size.height - 132, CGFloat(440)), CGFloat(640))
            let panelTop = max(CGFloat(82), (proxy.size.height - panelHeight) / 2)
            let panelWidth = min(
                Self.homeStageMaxWidth,
                max(CGFloat(0), proxy.size.width - (Self.homeStageHorizontalPadding * 2))
            )

            ZStack(alignment: .topTrailing) {
                HomeCanvasBackground()

                // Clicking anywhere outside the chat / connect panel collapses
                // back to the hub (panels and the ask bar consume their own
                // clicks above this catcher).
                if homeMode != .hub {
                    Color.black.opacity(0.001)
                        .ignoresSafeArea()
                        .contentShape(Rectangle())
                        .onTapGesture {
                            closeHomeStagePanel()
                        }
                }

                homeStage
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    // The popup/sheet overlays are modal: while one is up, the
                    // stage underneath must not be reachable by VoiceOver /
                    // Full Keyboard Access.
                    .accessibilityHidden(isHomeModalPresented)

                homeHeader
                    .padding(.horizontal, Self.homeStageHorizontalPadding)
                    .padding(.top, 26)
                    .accessibilityHidden(isHomeModalPresented)

                appsPopupOverlay(
                    contentWidth: proxy.size.width,
                    panelWidth: panelWidth,
                    panelHeight: panelHeight,
                    panelTop: panelTop
                )

                homeConnectSheetOverlay(
                    contentWidth: proxy.size.width,
                    panelWidth: panelWidth,
                    panelHeight: panelHeight,
                    panelTop: panelTop
                )

                // Esc collapses the inline chat / connect tray back to the hub —
                // but only while no modal overlay owns the key.
                if homeMode != .hub && !isHomeModalPresented {
                    OverlayModalEscapeCatcher {
                        closeHomeStagePanel()
                    }
                }
            }
            .animation(.easeOut(duration: 0.2), value: isShowingAppsPopup)
            .animation(.easeOut(duration: 0.2), value: homeConnectSheetIsPresented)
            .animation(Self.homeStageAnimation, value: homeMode)
        }
    }

    /// Vertical stage: mode content on top (hub metrics, inline chat, or the
    /// connect tray), the persistent ask bar anchored beneath it, and the
    /// suggested questions under the bar while the hub is showing.
    private var homeStage: some View {
        VStack(spacing: 0) {
            // Constant container alignment — each mode positions itself inside
            // the flexible area. Animating the container's own alignment made
            // the hub snap instead of gliding when the chat opened.
            ZStack {
                switch homeMode {
                case .hub:
                    VStack(spacing: 0) {
                        Spacer(minLength: 0)
                        homeHubCenterpiece
                    }
                    .transition(.homeHubFade)
                case .chat:
                    homeChatPanel
                        .transition(.homeDropFromTop)
                case .connect:
                    homeConnectPanel
                        .transition(.homeDropFromTop)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            homeAskBar
                .frame(maxWidth: Self.homeAskBarMaxWidth)
                .padding(.horizontal, Self.homeStageHorizontalPadding)
                .padding(.top, 22)

            if homeMode == .hub {
                homeSuggestionList
                    .frame(maxWidth: Self.homeAskBarMaxWidth)
                    .padding(.horizontal, Self.homeStageHorizontalPadding)
                    .padding(.top, 12)
                    .transition(.homeSuggestionsFade)
            }

            // Lifts the hub cluster toward the optical center; collapses while
            // a panel is up so the ask bar anchors at the bottom.
            Spacer(minLength: 0)
                .frame(height: homeMode == .hub ? 64 : 0)
        }
        .padding(.top, 74)
        .padding(.bottom, 26)
    }

    // MARK: Hub centerpiece

    private var homeHubCenterpiece: some View {
        VStack(spacing: 22) {
            Text("omi.")
                .font(.system(size: 52, weight: .bold, design: .rounded))
                .foregroundStyle(HomePalette.ink)
                .lineLimit(1)
                .shadow(color: HomePalette.glow.opacity(0.45), radius: 24)

            VStack(spacing: 8) {
                HStack(spacing: 8) {
                    HomeCenterMetricTile(
                        title: "Conversations",
                        value: conversationMetricValue,
                        systemImage: "text.bubble.fill",
                        action: { navigate(to: .conversations) }
                    )
                    HomeCenterMetricTile(
                        title: "Tasks",
                        value: taskMetricValue,
                        systemImage: "checklist",
                        action: { navigate(to: .tasks) }
                    )
                }

                HStack(spacing: 8) {
                    HomeCenterMetricTile(
                        title: "Memories",
                        value: memoryMetricValue,
                        systemImage: "brain",
                        action: { navigate(to: .memories) }
                    )
                    HomeCenterMetricTile(
                        title: "Screenshots",
                        value: screenshotMetricValue,
                        systemImage: "photo.on.rectangle.angled",
                        action: { navigate(to: .rewind) }
                    )
                }
            }
            .frame(width: 304)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: Inline chat panel

    private var homeChatPanel: some View {
        VStack(spacing: 0) {
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
                localSendToken: chatProvider.localSendToken,
                onCancelTurn: { chatProvider.stopAgent(owner: .mainChat) },
                welcomeContent: { dashboardChatWelcome }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .mask(
                LinearGradient(
                    stops: [
                        .init(color: .clear, location: 0.0),
                        .init(color: .black, location: 0.05),
                        .init(color: .black, location: 0.97),
                        .init(color: .clear, location: 1.0),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
        }
        // Barely-there card so the chat reads as a bounded surface — making it
        // obvious the canvas around it is clickable (and closes the chat).
        // The stroke is a soft gradient that dissolves toward the bottom.
        .background(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .fill(Color.white.opacity(0.012))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [
                            HomePalette.hairline.opacity(0.45),
                            HomePalette.hairline.opacity(0.10),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        )
        .frame(maxWidth: Self.homeStagePanelMaxWidth)
        .padding(.horizontal, Self.homeStageHorizontalPadding)
    }

    // MARK: Connect tray

    private var homeConnectPanel: some View {
        // Sources feed omi; omi's memory flows out to the AI destinations —
        // the chevron between the two cards reads that direction. The tray
        // hugs its content: no scroll filler below the columns.
        HStack(alignment: .center, spacing: 12) {
            homeConnectColumnCard {
                VStack(alignment: .leading, spacing: 12) {
                    sourceColumnHeader
                    sourceConstellation
                }
            }

            Image(systemName: "chevron.right")
                .scaledFont(size: 13, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
                .frame(width: 30, height: 30)
                .background(Circle().fill(HomePalette.tile))
                .overlay(Circle().stroke(HomePalette.hairline, lineWidth: 1))
                .accessibilityHidden(true)

            homeConnectColumnCard {
                destinationStack
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(HomePalette.panel.opacity(0.94))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(HomePalette.hairline.opacity(0.9), lineWidth: 1)
        )
        .overlay(alignment: .topTrailing) {
            HomeIconActionButton(title: "Close connect", systemImage: "xmark") {
                closeHomeStagePanel()
            }
            .padding(14)
        }
        .shadow(color: .black.opacity(0.4), radius: 30, y: 16)
        .frame(maxWidth: Self.homeStagePanelMaxWidth)
        .padding(.horizontal, Self.homeStageHorizontalPadding)
    }

    private func homeConnectColumnCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(Color.white.opacity(0.025))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(HomePalette.hairline.opacity(0.55), lineWidth: 1)
            )
    }

    // MARK: Ask bar + suggestions

    private var homeAskBar: some View {
        HomeAskBar(
            text: $chatProvider.draftText,
            isSending: chatProvider.isSending,
            isStopping: chatProvider.isStopping,
            isConnectActive: homeMode == .connect,
            focus: $homeAskFieldFocused,
            attachments: $chatProvider.pendingAttachments,
            onAttachmentsAdded: { urls in
                let toAdd = urls.compactMap { ChatAttachment.from(url: $0) }
                chatProvider.addAttachments(toAdd)
            },
            onAttachmentRemoved: { id in
                chatProvider.removePendingAttachment(id: id)
            },
            onSend: sendFromHomeAskBar,
            onStop: { chatProvider.stopAgent(owner: .mainChat) },
            onConnect: toggleHomeConnectPanel,
            onActivate: openHomeChat
        )
    }

    private var homeSuggestedQuestions: [String] {
        let saved = PostOnboardingPromptSuggestions.suggestions()
        let fallback = [
            "What should I focus on today to achieve my goals?",
            "What did I spend my time on this week?",
            "What's the highest-leverage thing I can do next?",
        ]
        return Array((saved.isEmpty ? fallback : saved).prefix(3))
    }

    private var homeSuggestionList: some View {
        VStack(spacing: 8) {
            ForEach(homeSuggestedQuestions, id: \.self) { question in
                HomeSuggestionRow(text: question) {
                    askHomeSuggestion(question)
                }
            }
        }
    }

    // MARK: Stage actions

    private func reportHomeAutomationMode() {
        guard DesktopAutomationLaunchOptions.isEnabled else { return }
        let modeLabel = useLegacyHomeDesign ? nil : homeMode.automationLabel
        DesktopAutomationStateStore.shared.updateLiveFields { snapshot in
            snapshot.homeMode = modeLabel
            snapshot.updatedAt = ISO8601DateFormatter().string(from: Date())
        }
    }

    private func openHomeChat() {
        guard homeMode != .chat else { return }
        withAnimation(Self.homeStageAnimation) {
            homeMode = .chat
        }
        reportHomeAutomationMode()
    }

    private func toggleHomeConnectPanel() {
        let target: HomeStageMode = homeMode == .connect ? .hub : .connect
        if target == .connect {
            homeAskFieldFocused = false
        }
        withAnimation(Self.homeStageAnimation) {
            homeMode = target
        }
        reportHomeAutomationMode()
    }

    private func closeHomeStagePanel() {
        homeAskFieldFocused = false
        withAnimation(Self.homeStageAnimation) {
            homeMode = .hub
        }
        reportHomeAutomationMode()
    }

    private func sendFromHomeAskBar() {
        let text = chatProvider.draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        // Text is required — ChatProvider.sendMessage no-ops on empty text, so
        // an attachment-only "send" would silently drop the turn.
        guard !text.isEmpty else { return }
        chatProvider.draftText = ""
        openHomeChat()
        AnalyticsManager.shared.chatMessageSent(
            messageLength: text.count,
            hasContext: selectedApp != nil,
            source: "home_ask_bar"
        )
        if chatProvider.isSending {
            Task { await chatProvider.sendFollowUp(text) }
        } else {
            Task { await chatProvider.sendMessage(text) }
        }
    }

    private func askHomeSuggestion(_ suggestion: String) {
        openHomeChat()
        AnalyticsManager.shared.chatMessageSent(
            messageLength: suggestion.count,
            hasContext: selectedApp != nil,
            source: "home_suggested_question"
        )
        Task { await chatProvider.sendMessage(suggestion) }
    }

    @ViewBuilder
    private func appsPopupOverlay(
        contentWidth: CGFloat,
        panelWidth: CGFloat,
        panelHeight: CGFloat,
        panelTop: CGFloat
    ) -> some View {
        ZStack {
            if isShowingAppsPopup {
                Color.black.opacity(0.16)
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture {
                        dismissAppsPopup()
                    }
                    .transition(.opacity)
                    .zIndex(2)

                let popupSize = appsPopupSize(panelWidth: panelWidth, panelHeight: panelHeight)

                AppsPage(
                    appProvider: appProvider,
                    appState: appState,
                    initialSection: appsPopupInitialSection,
                    onDismiss: {
                        dismissAppsPopup()
                    },
                    onSelectApp: { app in
                        openAppFromAppsPopup(app)
                    },
                    onSelectConnector: { connector in
                        openImportConnectorFromAppsPopup(connector)
                    },
                    onSelectDestination: { destination in
                        openExportDestinationFromAppsPopup(destination)
                    }
                )
                .id(appsPopupPresentationID)
                .frame(width: popupSize.width, height: popupSize.height)
                .background(OmiColors.backgroundPrimary)
                .clipShape(RoundedRectangle(cornerRadius: Self.appsPopupCornerRadius, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: Self.appsPopupCornerRadius, style: .continuous)
                        .stroke(HomePalette.hairline.opacity(0.9), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.38), radius: 26, y: 14)
                .position(x: contentWidth / 2, y: panelTop + panelHeight / 2)
                .transition(.scale(scale: 0.95).combined(with: .opacity))
                .accessibilityAddTraits(.isModal)
                .zIndex(3)

                // Only the topmost modal owns Esc; the connect sheet takes over
                // while it is presented (including the brief crossfade overlap).
                if appsPopupAcceptsInput && !homeConnectSheetIsPresented {
                    OverlayModalEscapeCatcher {
                        dismissAppsPopup()
                    }
                    .zIndex(3)
                }
            }
        }
        .allowsHitTesting(appsPopupAcceptsInput && !homeConnectSheetIsPresented)
        .zIndex(2)
    }

    @ViewBuilder
    private func homeConnectSheetOverlay(
        contentWidth: CGFloat,
        panelWidth: CGFloat,
        panelHeight: CGFloat,
        panelTop: CGFloat
    ) -> some View {
        ZStack {
            if homeConnectSheetIsPresented {
                Color.black.opacity(0.22)
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture {
                        dismissHomeConnectSheet()
                    }
                    .transition(.opacity)
                    .zIndex(4)

                let sheetSize = homeConnectSheetSize(panelWidth: panelWidth, panelHeight: panelHeight)

                homeConnectSheetContent()
                    .frame(width: sheetSize.width, height: sheetSize.height)
                    .background(OmiColors.backgroundPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: Self.homeConnectSheetCornerRadius, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: Self.homeConnectSheetCornerRadius, style: .continuous)
                            .stroke(HomePalette.hairline.opacity(0.92), lineWidth: 1)
                    )
                    .shadow(color: .black.opacity(0.42), radius: 30, y: 16)
                    .position(x: contentWidth / 2, y: panelTop + panelHeight / 2)
                    .transition(.scale(scale: 0.96).combined(with: .opacity))
                    .accessibilityAddTraits(.isModal)
                    .zIndex(5)

                if homeConnectSheetAcceptsInput {
                    OverlayModalEscapeCatcher {
                        dismissHomeConnectSheet()
                    }
                    .zIndex(5)
                }
            }
        }
        .allowsHitTesting(homeConnectSheetAcceptsInput)
        .zIndex(4)
    }

    private func homeConnectSheetSize(panelWidth: CGFloat, panelHeight: CGFloat) -> CGSize {
        let preferred = homeConnectSheetPreferredSize
        return CGSize(
            width: min(
                preferred.width,
                max(Self.homeConnectSheetMinWidth, panelWidth - (Self.homeConnectSheetHorizontalMargin * 2))
            ),
            height: min(
                preferred.height,
                max(Self.homeConnectSheetMinHeight, panelHeight - (Self.homeConnectSheetVerticalMargin * 2))
            )
        )
    }

    private var homeConnectSheetPreferredSize: CGSize {
        if selectedCatalogApp != nil {
            return Self.appDetailSheetPreferredSize
        }
        if selectedImportConnector != nil {
            return Self.importConnectorSheetPreferredSize
        }
        return Self.exportDestinationSheetPreferredSize
    }

    @ViewBuilder
    private func homeConnectSheetContent() -> some View {
        if let app = selectedCatalogApp {
            AppDetailSheet(app: app, appProvider: appProvider, onDismiss: { dismissHomeConnectSheet() })
                .onAppear {
                    AnalyticsManager.shared.appDetailViewed(appId: app.id, appName: app.name)
                }
        } else if let connector = selectedImportConnector {
            ImportConnectorSheet(
                connector: connector,
                appState: appState,
                statusStore: importConnectorStatusStore,
                onDismiss: {
                    dismissHomeConnectSheet()
                }
            )
        } else if let destination = selectedExportDestination {
            ConnectDestinationSheet(
                destination: destination,
                statuses: $memoryExportStatuses,
                onDismiss: {
                    dismissHomeConnectSheet()
                }
            )
        }
    }

    private func appsPopupSize(panelWidth: CGFloat, panelHeight: CGFloat) -> CGSize {
        CGSize(
            width: min(
                Self.appsPopupMaxWidth,
                max(Self.appsPopupMinWidth, panelWidth - (Self.appsPopupHorizontalMargin * 2))
            ),
            height: min(
                Self.appsPopupMaxHeight,
                max(Self.appsPopupMinHeight, panelHeight - (Self.appsPopupVerticalMargin * 2))
            )
        )
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

                HomeListeningStatusButton(
                    title: "Listening",
                    systemImage: appState.isTranscribing ? "waveform.circle.fill" : "mic.circle",
                    status: appState.isTranscribing ? .active : .inactive,
                    modeTitle: listeningModeTitle,
                    isMeetingsOnly: listeningCaptureMode == .onlyDuringMeetings,
                    isToggling: isTogglingListening,
                    action: toggleListening,
                    modeAction: toggleListeningMode
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
    }

    private var sourceConstellation: some View {
        VStack(alignment: .leading, spacing: 12) {
            HomeAIChoiceButton(title: "Gmail", brand: .gmail, isConnected: isImportConnectorConnected("email")) {
                openImportConnector("email")
            }
            HomeAIChoiceButton(title: "Calendar", brand: .calendar, isConnected: isImportConnectorConnected("calendar")) {
                openImportConnector("calendar")
            }
            HomeAIChoiceButton(title: "Files", brand: .localFiles, isConnected: isImportConnectorConnected("local-files")) {
                openImportConnector("local-files")
            }
            HomeAIChoiceButton(title: "Notes", brand: .appleNotes, isConnected: isImportConnectorConnected("apple-notes")) {
                openImportConnector("apple-notes")
            }
            HomeAIChoiceButton(title: "Omi Device", usesOmiMark: true, isConnected: hasOmiDeviceHistory) {
                openOmiDeviceWebsite()
            }
            HomeAIChoiceButton(title: "More", systemImage: "plus") {
                openAppsPopup(initialSection: .imports)
            }
        }
    }

    private var destinationStack: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Use omi memory anywhere")
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(HomePalette.ink)

                Text("Bring your memories to the apps you use")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundStyle(HomePalette.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HomeAIChoiceButton(title: "Ask Omi", usesOmiMark: true) {
                openHomeChat()
            }
            HomeAIChoiceButton(title: "Claude / Claude Code", brand: .claude, isConnected: isMCPDestinationConnected(.claude)) {
                openExportDestination(.claudeCode)
            }
            HomeAIChoiceButton(title: "ChatGPT / Codex", brand: .chatgpt, isConnected: isMCPDestinationConnected(.chatgpt)) {
                openExportDestination(.codex)
            }
            HomeAIChoiceButton(title: "OpenClaw", brand: .openclaw, isConnected: isMCPDestinationConnected(.openclaw)) {
                openExportDestination(.openclaw)
            }
            HomeAIChoiceButton(title: "Hermes", brand: .hermes, isConnected: isMCPDestinationConnected(.hermes)) {
                openExportDestination(.hermes)
            }
            HomeAIChoiceButton(title: "More", systemImage: "plus") {
                openAppsPopup(initialSection: .exports)
            }
        }
    }

    private var conversationMetricValue: String {
        formattedCount(conversationCount ?? appState.totalConversationsCount ?? appState.conversations.count)
    }

    private var taskMetricValue: String {
        formattedCount(taskCount ?? incompleteTaskCount)
    }

    private var memoryMetricValue: String {
        let count = memoryCount ?? (memoriesViewModel.totalMemoriesCount > 0
            ? memoriesViewModel.totalMemoriesCount
            : memoriesViewModel.memories.count)
        return formattedCount(count)
    }

    private var screenshotMetricValue: String {
        screenshotCount.map(formattedCount) ?? "—"
    }

    private func navigate(to item: SidebarNavItem) {
        selectedIndex = item.rawValue
        AnalyticsManager.shared.tabChanged(tabName: item.title)
    }

    private func openAppsPopup(initialSection: AppsCatalogInitialSection) {
        // Filters left behind by earlier catalog visits (a category, a search,
        // "Installed") would otherwise replace the Imports/Exports sections
        // this popup exists to show.
        appProvider.clearFilters()
        appsPopupInitialSection = initialSection
        appsPopupPresentationID = UUID()
        appsPopupAcceptsInput = true
        isShowingAppsPopup = true
    }

    private func dismissAppsPopup() {
        appsPopupAcceptsInput = false
        isShowingAppsPopup = false
    }

    private func openAppFromAppsPopup(_ app: OmiApp) {
        dismissAppsPopup()
        presentCatalogApp(app)
    }

    private func openImportConnectorFromAppsPopup(_ connector: ImportConnector) {
        dismissAppsPopup()
        presentImportConnector(connector)
    }

    private func openExportDestinationFromAppsPopup(_ destination: MemoryExportDestination) {
        dismissAppsPopup()
        presentExportDestination(destination)
    }

    private func openImportConnector(_ connectorID: String) {
        if let connector = ImportConnector.all.first(where: { $0.id == connectorID }) {
            presentImportConnector(connector)
        }
    }

    private func openExportDestination(_ destination: MemoryExportDestination) {
        presentExportDestination(destination)
    }

    private func presentCatalogApp(_ app: OmiApp) {
        homeConnectSheetAcceptsInput = true
        selectedImportConnector = nil
        selectedExportDestination = nil
        selectedCatalogApp = app
    }

    private func presentImportConnector(_ connector: ImportConnector) {
        homeConnectSheetAcceptsInput = true
        selectedCatalogApp = nil
        selectedExportDestination = nil
        selectedImportConnector = connector
    }

    private func presentExportDestination(_ destination: MemoryExportDestination) {
        homeConnectSheetAcceptsInput = true
        selectedCatalogApp = nil
        selectedImportConnector = nil
        selectedExportDestination = destination
    }

    private func dismissHomeConnectSheet() {
        homeConnectSheetAcceptsInput = false
        selectedCatalogApp = nil
        selectedImportConnector = nil
        selectedExportDestination = nil
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

    private func toggleListeningMode() {
        let nextMode: AssistantSettings.SystemAudioCaptureMode =
            listeningCaptureMode == .onlyDuringMeetings ? .always : .onlyDuringMeetings
        systemAudioCaptureModeRaw = nextMode.rawValue
        AssistantSettings.shared.systemAudioCaptureMode = nextMode
        AnalyticsManager.shared.settingToggled(
            setting: "meetings_only_listening",
            enabled: nextMode == .onlyDuringMeetings
        )
    }

    private func toggleCapture() {
        syncCaptureState()
        let enabled = !isCaptureLive
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

    /// Refreshes Home-only status tiles and connector rows. Forced loads run
    /// when the Home view is recreated; activation-triggered loads share the
    /// app-wide cooldown so Cmd-Tab bursts do not rescan configs or hit count
    /// endpoints repeatedly while Home is still mounted.
    private func refreshHomeStatusData(force: Bool) async {
        let shouldRefresh = await MainActor.run {
            let now = Date()
            if !force,
               !PollingConfig.shouldAllowActivationRefresh(
                   now: now,
                   lastRefresh: lastHomeStatusRefreshAt
               ) {
                return false
            }
            lastHomeStatusRefreshAt = now
            return true
        }
        guard shouldRefresh else { return }

        async let importConnectorStatuses: Void = importConnectorStatusStore.refresh()
        async let screenshots: Void = loadScreenshotCount()
        async let knowledgeCounts: Void = loadKnowledgeCounts()
        async let exportStatuses: Void = loadMemoryExportStatuses()
        _ = await (importConnectorStatuses, screenshots, knowledgeCounts, exportStatuses)
    }

    private func loadMemoryExportStatuses() async {
        let statuses = await MemoryExportService.shared.allStatuses()
        await MainActor.run {
            memoryExportStatuses = statuses
        }
    }

    /// Load the true totals behind the "What omi knows" tiles. Conversations come
    /// from the server count endpoint (not stored locally); memories and tasks are
    /// counted from the synced local DB — the same totals the detail pages show.
    private func loadKnowledgeCounts() async {
        async let convos = try? APIClient.shared.getConversationsCount(includeDiscarded: false)
        async let mems = try? MemoryStorage.shared.getLocalMemoriesCount()
        // Open tasks only (matches the "Tasks" label and the old tile's intent —
        // the old value just under-counted, capping each bucket at a 7-day window).
        async let tasks = try? ActionItemStorage.shared.getLocalActionItemsCount(completed: false)
        let shouldLoadDeviceHistory = await MainActor.run { !accountHasOmiDeviceConversations }
        async let deviceHistory = shouldLoadDeviceHistory ? loadOmiDeviceHistory() : nil
        let (c, m, t, d) = await (convos, mems, tasks, deviceHistory)
        await MainActor.run {
            if let c { conversationCount = c }
            if let m { memoryCount = m }
            if let t { taskCount = t }
            // Sticky: device history never un-happens; keep the badge across
            // launches and network failures once observed.
            if d == true {
                accountHasOmiDeviceConversations = true
                UserDefaults.standard.set(true, forKey: Self.omiDeviceHistoryDefaultsKey)
            }
        }
    }

    private func loadOmiDeviceHistory() async -> Bool? {
        try? await APIClient.shared.hasOmiDeviceConversations()
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
    // Home ambient glow is PURPLE per Nik's explicit, repeated preference — the rose/red
    // variant (0.95,0.33,0.45) was disliked. The purple VALUE lives on `.glow` on purpose:
    // earlier purple fixes kept getting reverted by "HomePalette.purple → .glow" merge
    // cleanups (e.g. 317424f57), so we put the purple on the name those reverts converge to.
    // Do NOT change this back to red/rose.
    static let glow = Color(red: 0.48, green: 0.30, blue: 0.95)      // purple
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

private enum HomeStageMode: Equatable {
    case hub
    case chat
    case connect

    var automationLabel: String {
        switch self {
        case .hub: return "hub"
        case .chat: return "chat"
        case .connect: return "connect"
        }
    }
}

/// Shared "drop from the top" motion for stage panels: a short slide with a
/// slight top-anchored scale and fade — deliberate, not a full-height fly-in.
private struct HomeStageDropModifier: ViewModifier {
    let offsetY: CGFloat
    let scale: CGFloat
    let opacity: Double

    func body(content: Content) -> some View {
        content
            .offset(y: offsetY)
            .scaleEffect(scale, anchor: .top)
            .opacity(opacity)
    }
}

extension AnyTransition {
    fileprivate static var homeDropFromTop: AnyTransition {
        .modifier(
            active: HomeStageDropModifier(offsetY: -46, scale: 0.97, opacity: 0),
            identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
        )
    }

    fileprivate static var homeHubFade: AnyTransition {
        .modifier(
            active: HomeStageDropModifier(offsetY: 14, scale: 1, opacity: 0),
            identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
        )
    }

    fileprivate static var homeSuggestionsFade: AnyTransition {
        .modifier(
            active: HomeStageDropModifier(offsetY: 10, scale: 1, opacity: 0),
            identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
        )
    }
}

/// The persistent home ask bar: a pill-shaped chat input with attachments
/// (paperclip + drag-drop, same limits as the chat page), a send/stop action,
/// and the Connect toggle living inside the pill.
private struct HomeAskBar: View {
    @Binding var text: String
    let isSending: Bool
    let isStopping: Bool
    let isConnectActive: Bool
    var focus: FocusState<Bool>.Binding
    @Binding var attachments: [ChatAttachment]
    let onAttachmentsAdded: ([URL]) -> Void
    let onAttachmentRemoved: (String) -> Void
    let onSend: () -> Void
    let onStop: () -> Void
    let onConnect: () -> Void
    let onActivate: () -> Void

    @State private var isHovering = false
    @State private var isDropTargeted = false

    private var hasText: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Requires text: ChatProvider.sendMessage drops empty-text sends, so
    /// presenting attachment-only as sendable would silently do nothing.
    /// Staged files ride along with the typed message instead.
    private var canSend: Bool {
        hasText
    }

    private var isFocused: Bool { focus.wrappedValue }

    var body: some View {
        VStack(spacing: 8) {
            if !attachments.isEmpty {
                AttachmentPreviewRow(
                    attachments: attachments,
                    onRemove: onAttachmentRemoved
                )
                .padding(.top, 10)
                .padding(.horizontal, 12)
            }

            HStack(spacing: 10) {
                Button(action: pickFiles) {
                    Image(systemName: "paperclip")
                        .scaledFont(size: 15, weight: .medium)
                        .foregroundStyle(isFocused ? HomePalette.secondary : HomePalette.muted)
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(attachments.count >= kMaxChatAttachments)
                .help("Attach files")

                TextField(
                    "",
                    text: $text,
                    prompt: Text("Ask omi anything").foregroundColor(HomePalette.muted)
                )
                .textFieldStyle(.plain)
                .font(.system(size: 15))
                .foregroundStyle(HomePalette.ink)
                .focused(focus)
                .onSubmit(onSend)

                if isSending && !hasText {
                    stopButton
                } else if canSend {
                    sendButton
                }

                connectButton
            }
            .padding(.leading, 16)
            .padding(.trailing, 8)
            .frame(height: 58)
        }
        .background(
            RoundedRectangle(cornerRadius: 29, style: .continuous)
                .fill(HomePalette.tile.opacity(isHovering || isFocused ? 1 : 0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 29, style: .continuous)
                .stroke(
                    isDropTargeted
                        ? Color.white.opacity(0.55)
                        : (isFocused
                            ? Color.white.opacity(0.30)
                            : HomePalette.hairline.opacity(isHovering ? 1 : 0.9)),
                    lineWidth: 1
                )
        )
        .shadow(color: .black.opacity(isFocused ? 0.45 : 0.34), radius: 24, y: 10)
        .contentShape(.rect(cornerRadius: 29))
        .onTapGesture {
            onActivate()
            focus.wrappedValue = true
        }
        .onHover { isHovering = $0 }
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
        .animation(.easeOut(duration: 0.16), value: isFocused)
        .animation(.easeOut(duration: 0.16), value: canSend)
        .animation(.easeOut(duration: 0.16), value: attachments.count)
    }

    private func pickFiles() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [
            .image, .jpeg, .png, .gif, .heic, .heif, .webP, .tiff, .bmp,
            .pdf, .plainText, .json, .commaSeparatedText, .html,
            .text, .content,
        ]
        if panel.runModal() == .OK {
            let remaining = max(0, kMaxChatAttachments - attachments.count)
            let urls = Array(panel.urls.prefix(remaining))
            if !urls.isEmpty {
                onAttachmentsAdded(urls)
            }
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        ChatAttachmentDropHandler.collectURLs(from: providers) { [attachments] urls in
            guard !urls.isEmpty else { return }
            let remaining = max(0, kMaxChatAttachments - attachments.count)
            let allowed = Array(urls.prefix(remaining))
            if !allowed.isEmpty {
                onAttachmentsAdded(allowed)
            }
        }
    }

    private var sendButton: some View {
        Button(action: onSend) {
            ZStack {
                Circle()
                    .fill(Color.white)

                Image(systemName: "arrow.up")
                    .scaledFont(size: 13, weight: .bold)
                    .foregroundStyle(Color.black)
            }
            .frame(width: 34, height: 34)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .help("Send")
        .accessibilityLabel("Send message")
    }

    private var stopButton: some View {
        Button(action: onStop) {
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.14))

                if isStopping {
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.6)
                } else {
                    Image(systemName: "square.fill")
                        .scaledFont(size: 10, weight: .bold)
                        .foregroundStyle(HomePalette.ink)
                }
            }
            .frame(width: 34, height: 34)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(isStopping)
        .help("Stop")
        .accessibilityLabel("Stop response")
    }

    private var connectButton: some View {
        HomeAskBarConnectButton(isActive: isConnectActive, action: onConnect)
    }
}

private struct HomeAskBarConnectButton: View {
    let isActive: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "link")
                    .scaledFont(size: 11, weight: .semibold)

                Text("Connect")
                    .scaledFont(size: 12, weight: .semibold)
            }
            .foregroundStyle(isActive ? Color.black : HomePalette.ink)
            .padding(.horizontal, 13)
            .frame(height: 34)
            .background(
                Capsule(style: .continuous)
                    .fill(isActive ? Color.white : Color.white.opacity(isHovering ? 0.14 : 0.07))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isActive ? Color.clear : HomePalette.hairline, lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help("Connect data & use omi anywhere")
        .accessibilityLabel(isActive ? "Close connect" : "Connect")
    }
}

private struct HomeSuggestionRow: View {
    let text: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: "sparkles")
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundStyle(isHovering ? Color(hex: 0xE3BF63) : HomePalette.muted)

                Text(text)
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)
                    .lineLimit(1)

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 10, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.faint)
            }
            .padding(.horizontal, 16)
            .frame(height: 42)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 21, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.55))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 21, style: .continuous)
                    .stroke(HomePalette.hairline.opacity(isHovering ? 1 : 0.55), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: 21))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(text)
    }
}

private struct HomeCanvasBackground: View {
    var body: some View {
        ZStack {
            HomePalette.paper

            // One barely-there key light high behind the wordmark, and a faint
            // horizon lift near the ask bar. Deliberately subtle — the old
            // mid-screen glow blobs read as splotches on large displays.
            RadialGradient(
                colors: [Color.white.opacity(0.045), .clear],
                center: UnitPoint(x: 0.5, y: 0.16),
                startRadius: 0,
                endRadius: 560
            )

            RadialGradient(
                colors: [HomePalette.glow.opacity(0.05), .clear],
                center: UnitPoint(x: 0.5, y: 0.20),
                startRadius: 0,
                endRadius: 720
            )

            LinearGradient(
                stops: [
                    .init(color: .clear, location: 0.62),
                    .init(color: Color.white.opacity(0.02), location: 0.86),
                    .init(color: .clear, location: 1.0),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
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
                    .stroke(isHovering ? HomePalette.glow.opacity(0.58) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? HomePalette.glow.opacity(0.16) : .clear, radius: 14)
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
                    .stroke(isHovering ? HomePalette.glow.opacity(0.5) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? HomePalette.glow.opacity(0.12) : .clear, radius: 12)
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
    let isConnected: Bool
    let action: () -> Void

    @State private var isHovering = false

    init(title: String, brand: ConnectorBrand, isPrimary: Bool = false, isConnected: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = brand
        self.systemImage = nil
        self.usesOmiMark = false
        self.isPrimary = isPrimary
        self.isConnected = isConnected
        self.action = action
    }

    init(title: String, systemImage: String, isPrimary: Bool = false, isConnected: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = systemImage
        self.usesOmiMark = false
        self.isPrimary = isPrimary
        self.isConnected = isConnected
        self.action = action
    }

    init(title: String, usesOmiMark: Bool, isPrimary: Bool = false, isConnected: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.brand = nil
        self.systemImage = nil
        self.usesOmiMark = usesOmiMark
        self.isPrimary = isPrimary
        self.isConnected = isConnected
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

                if isConnected {
                    Text("Connected")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundStyle(HomePalette.faint)
                }

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
                .foregroundStyle(HomePalette.ink)
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
                        .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.faint)
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
            .frame(maxWidth: .infinity, minHeight: 82, maxHeight: 82, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.92))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(isHovering ? HomePalette.hairline : HomePalette.hairline.opacity(0.82), lineWidth: 1)
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
                    .foregroundStyle(isHovering ? HomePalette.glow : HomePalette.faint)
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
                    .stroke(isHovering ? HomePalette.glow.opacity(0.56) : HomePalette.hairline.opacity(0.86), lineWidth: 1)
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
            }
            .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(height: 34)
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

private struct HomeListeningStatusButton: View {
    let title: String
    let systemImage: String
    let status: HomeStatusState
    let modeTitle: String
    let isMeetingsOnly: Bool
    let isToggling: Bool
    let action: () -> Void
    let modeAction: () -> Void

    // Single pill-level hover flag so moving between the title and the mode
    // toggle never flickers the revealed controls.
    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 0) {
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

                    VStack(alignment: .leading, spacing: 1) {
                        Text(title)
                            .scaledFont(size: 12, weight: .semibold)
                            .lineLimit(1)

                        // Mode ("Always" / "In meeting" / …) is revealed only on
                        // hover to keep the resting pill clean.
                        if isHovering {
                            Text(modeTitle)
                                .scaledFont(size: 8, weight: .medium)
                                .foregroundStyle(status.isActive ? HomePalette.secondary : HomePalette.muted)
                                .lineLimit(1)
                                .transition(.opacity)
                        }
                    }
                }
                .padding(.leading, 12)
                .padding(.trailing, 8)
                .frame(height: 34)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .help("Listening: \(status.text), \(modeTitle)")
            .accessibilityLabel("Listening \(status.text), \(modeTitle)")

            // Divider + mode toggle are revealed only on hover to keep the
            // resting pill compact.
            if isHovering {
                Rectangle()
                    .fill(HomePalette.hairline.opacity(0.65))
                    .frame(width: 1, height: 18)
                    .transition(.opacity)

                Button(action: modeAction) {
                    Image(systemName: isMeetingsOnly ? "person.2.fill" : "person.fill")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundStyle(modeIconColor)
                        .frame(width: 30, height: 34)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(isMeetingsOnly ? "Switch to always listening" : "Switch to meetings only")
                .accessibilityLabel(isMeetingsOnly ? "Switch Listening to Always" : "Switch Listening to Meetings Only")
                .transition(.opacity)
            }
        }
        .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
        .background(
            Capsule(style: .continuous)
                .fill(statusFill)
        )
        .overlay(
            Capsule(style: .continuous)
                .stroke(statusStroke, lineWidth: 1)
        )
        .contentShape(Capsule())
        .frame(height: 34)
        .onHover { isHovering = $0 }
        .animation(.easeInOut(duration: 0.14), value: isHovering)
    }

    private var modeIconColor: Color {
        status.isActive ? HomePalette.green : HomePalette.muted
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

#if canImport(PreviewsMacros)
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
#endif
