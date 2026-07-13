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
    @ObservedObject var homeStatusStore: HomeStatusStore = HomeStatusStore()
    @ObservedObject var appState: AppState
    @ObservedObject var appProvider: AppProvider
    @ObservedObject var chatProvider: ChatProvider
    @ObservedObject var memoriesViewModel: MemoriesViewModel
    var taskChatCoordinator: TaskChatCoordinator? = nil
    @ObservedObject private var deviceProvider = DeviceProvider.shared
    @StateObject private var intelligenceStore = DashboardIntelligenceStore()
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
    @State private var isCaptureMonitoring = false
    @State private var isTogglingCapture = false
    @State private var isTogglingListening = false
    @State private var showingAllGoals = false
    @State private var showingGoalDetail = false
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

    private static let homeStageMaxWidth: CGFloat = 1360
    private static let homeStageMinSideInset: CGFloat = 30
    private static let homeStageMaxSideInset: CGFloat = 96
    private static let homeAskBarMinWidth: CGFloat = 560
    private static let homeAskBarMaxWidth: CGFloat = 980
    private static let homeStagePanelMaxWidth: CGFloat = 1280
    private static let homeStageTopPadding: CGFloat = 74
    private static let homeStageBottomPadding: CGFloat = 26
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
            || homeStatusStore.accountHasOmiDeviceConversations
    }

    /// Real persisted import-connector state (UserDefaults-backed via ImportConnectorStatusStore).
    private func isImportConnectorConnected(_ connectorID: String) -> Bool {
        guard let connector = ImportConnector.all.first(where: { $0.id == connectorID }) else { return false }
        return homeStatusStore.connectorStatusStore.snapshot(for: connector).isConnected
    }

    private func isMCPDestinationConnected(_ destination: MemoryExportDestination) -> Bool {
        switch destination {
        case .claude, .claudeCode:
            return [.claude, .claudeCode].contains { homeStatusStore.memoryExportStatuses[$0]?.hasConnection == true }
        case .chatgpt, .codex:
            return [.chatgpt, .codex].contains { homeStatusStore.memoryExportStatuses[$0]?.hasConnection == true }
        default:
            return homeStatusStore.memoryExportStatuses[destination]?.hasConnection == true
        }
    }

    var body: some View {
        applyHomeLifecycle(to: applyHomeSheets(to: homeSurface))
    }

    private var homeSurface: some View {
        Group {
            if useLegacyHomeDesign {
                legacyHome
            } else {
                redesignedHome
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(useLegacyHomeDesign ? Color.clear : HomePalette.paper)
    }

    private func applyHomeSheets<Content: View>(to content: Content) -> some View {
        content
        .sheet(item: $citedConversation) { conversation in
            ConversationDetailView(
                conversation: conversation,
                onBack: {
                    citedConversation = nil
                }
            )
            .frame(minWidth: 500, minHeight: 500)
        }
        .sheet(isPresented: $showingAllGoals) {
            AllGoalsSheet(
                store: intelligenceStore,
                onOpenGoal: { goalID in await openGoal(goalID) },
                onDismiss: { showingAllGoals = false }
            )
        }
        .sheet(isPresented: $showingGoalDetail) {
            if let detail = intelligenceStore.selectedGoalDetail {
                CanonicalGoalDetailSheet(
                    detail: detail,
                    error: intelligenceStore.error,
                    onResumeThread: { workstreamID in
                        _ = await resumeThread(workstreamID: workstreamID, taskID: nil)
                    },
                    onStartWork: { await startWorkFromSelectedGoal() },
                    onDismiss: {
                        showingGoalDetail = false
                        intelligenceStore.clearGoalDetail()
                    }
                )
            } else {
                ProgressView().frame(width: 300, height: 180)
            }
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
                statusStore: homeStatusStore.connectorStatusStore,
                onDismiss: {
                    selectedImportConnector = nil
                }
            )
            .frame(width: 520, height: 620)
        }
        .dismissableSheet(item: legacySelectedExportDestination) { destination in
            ConnectDestinationSheet(
                destination: destination,
                statuses: $homeStatusStore.memoryExportStatuses,
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
                    VStack(spacing: OmiSpacing.md) {
                        ProgressView()
                        Text("Loading source...")
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(.white)
                    }
                    .padding(OmiSpacing.xl)
                    .background(OmiColors.backgroundSecondary)
                    .cornerRadius(OmiChrome.smallControlRadius)
                }
            }
        }
    }

    private func applyHomeLifecycle<Content: View>(to content: Content) -> some View {
        content
        .onAppear {
            if PostOnboardingPromptSuggestions.shouldShowPopup && !postOnboardingSuggestions.isEmpty {
                NotificationCenter.default.post(name: .showTryAskingPopup, object: nil)
            }
            syncCaptureState()
            reportHomeAutomationMode()
            intelligenceStore.setRecommendationActionHandler { recommendation in
                await openRecommendation(recommendation)
            }
            intelligenceStore.registerAutomationActions()
            Task { await intelligenceStore.load() }
            Task {
                if let recommendationID = ContextualTaskNavigationRouter.shared.consume() {
                    _ = await intelligenceStore.openRecommendation(id: recommendationID)
                }
            }
            Task { await homeStatusStore.refreshIfNeeded() }
        }
        .onDisappear {
            intelligenceStore.setRecommendationActionHandler(nil)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            viewModel.refreshGoals()
            Task { await intelligenceStore.load() }
            appState.checkAllPermissions()
            syncCaptureState()
            Task { await homeStatusStore.refreshIfNeeded() }
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            syncCaptureState()
        }
        .onReceive(NotificationCenter.default.publisher(for: .whatMattersNowContextDidRefresh)) { notification in
            guard let projection = notification.object as? OmiAPI.WhatMattersNowProjection else { return }
            intelligenceStore.applyContextProjection(projection)
        }
        .onReceive(NotificationCenter.default.publisher(for: .openWhatMattersNowRecommendation)) { notification in
            guard let recommendationID = notification.userInfo?[
                TaskContextualResurfacingService.recommendationIDUserInfoKey
            ] as? String else { return }
            guard ContextualTaskNavigationRouter.shared.consume(requestedID: recommendationID) != nil else { return }
            Task { _ = await intelligenceStore.openRecommendation(id: recommendationID) }
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
                sessionsLoadError: chatProvider.sessionsLoadError.map {
                    UserFacingErrorPresentation.message(from: $0, while: .chatSessions)
                },
                onRetry: { Task { await chatProvider.retryLoad() } },
                localSendToken: chatProvider.localSendToken,
                onOpenAgent: { agentID, completion in
                    FloatingControlBarManager.shared.openAgentChatFromTimeline(agentID: agentID, completion: completion)
                },
                onOpenAgentRef: { ref, completion in
                    FloatingControlBarManager.shared.openAgentChatFromTimeline(ref: ref, completion: completion)
                },
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

            dashboardChatErrorCard
                .padding(.horizontal, OmiSpacing.section)

            ChatInputView(
                onSend: { text in
                    AnalyticsManager.shared.chatMessageSent(
                        messageLength: text.count,
                        hasSelectedAppContext: selectedApp != nil,
                        source: "dashboard_chat"
                    )
                    Task { await chatProvider.sendMainDraft(text) }
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
            .padding(.horizontal, OmiSpacing.section)
            .padding(.top, OmiSpacing.md)
            .padding(.bottom, OmiSpacing.xl)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
    }

    // MARK: - Redesigned Home

    private var redesignedHome: some View {
        GeometryReader { proxy in
            let sideInset = homeStageSideInset(for: proxy.size.width)
            let panelHeight = min(max(proxy.size.height - 132, CGFloat(440)), CGFloat(640))
            let panelTop = max(CGFloat(82), (proxy.size.height - panelHeight) / 2)
            let panelWidth = homeStageContentWidth(for: proxy.size.width)

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

                homeStage(stageWidth: proxy.size.width, stageHeight: proxy.size.height)
                    .frame(width: proxy.size.width, height: proxy.size.height)
                    // The popup/sheet overlays are modal: while one is up, the
                    // stage underneath must not be reachable by VoiceOver /
                    // Full Keyboard Access.
                    .accessibilityHidden(isHomeModalPresented)

                homeHeader
                    .padding(.horizontal, sideInset)
                    .padding(.top, OmiSpacing.xxl)
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
            .omiAnimation(.easeOut(duration: 0.2), value: isShowingAppsPopup)
            .omiAnimation(.easeOut(duration: 0.2), value: homeConnectSheetIsPresented)
            .omiAnimation(Self.homeStageAnimation, value: homeMode)
        }
    }

    /// Vertical stage: mode content on top (hub metrics, inline chat, or the
    /// connect tray), the persistent ask bar anchored beneath it, and the
    /// suggested questions under the bar while the hub is showing.
    private func homeStage(stageWidth: CGFloat, stageHeight: CGFloat) -> some View {
        let askBarWidth = homeAskBarWidth(for: stageWidth)

        return Group {
            if homeMode == .hub {
                homeHubStage(askBarWidth: askBarWidth, stageHeight: stageHeight)
            } else {
                homePanelStage(stageWidth: stageWidth, askBarWidth: askBarWidth)
            }
        }
        .padding(.top, Self.homeStageTopPadding)
        .padding(.bottom, Self.homeStageBottomPadding)
    }

    /// Hub layout: the omi wordmark centered in the full screen, with the stats
    /// ribbon, ask bar, and suggestions docked as one column at the bottom.
    ///
    /// Built as a plain VStack (wordmark, flexible gap, cluster) so the two can
    /// never overlap. The wordmark's top inset is computed so it lands on the
    /// true stage center when the window is tall enough, and lifts to sit just
    /// above the cluster (with a minimum gap) when it isn't.
    private func homeHubStage(askBarWidth: CGFloat, stageHeight: CGFloat) -> some View {
        // Wordmark height and a deliberately generous estimate of the docked
        // cluster height (ribbon + gap + ask bar + gap + three suggestion rows).
        // Overestimating only lifts the wordmark slightly early; it never lets
        // the cluster clip.
        let wordmarkHeight: CGFloat = 76
        let clusterHeight: CGFloat = intelligenceStore.recommendations.isEmpty ? 390 : 570
        let minGap: CGFloat = 24
        let contentHeight = stageHeight - Self.homeStageTopPadding - Self.homeStageBottomPadding

        let trueCenterInset = (contentHeight - wordmarkHeight) / 2
        let maxInset = contentHeight - wordmarkHeight - clusterHeight - minGap
        let topInset = max(0, min(trueCenterInset, maxInset))

        return VStack(spacing: 0) {
            Spacer(minLength: 0)
                .frame(height: topInset)

            if intelligenceStore.recommendations.isEmpty {
                homeHubWordmark
                    .transition(.homeHubFade)

                // Flexible gap absorbs the remaining height, docking the cluster at
                // the bottom while keeping at least `minGap` below the wordmark.
                Spacer(minLength: minGap)
            } else {
                Spacer(minLength: 0)
            }

            VStack(spacing: 0) {
                WhatMattersNowSection(
                    store: intelligenceStore,
                    onOpen: { recommendation in await openRecommendation(recommendation) }
                )
                .frame(width: askBarWidth)
                .padding(.bottom, intelligenceStore.recommendations.isEmpty ? 0 : OmiSpacing.sm)

                dashboardIntelligenceError
                    .frame(width: askBarWidth)
                    .padding(.bottom, intelligenceStore.error == nil ? 0 : OmiSpacing.sm)

                FocusedGoalsSection(
                    store: intelligenceStore,
                    onOpenGoal: { goalID in await openGoal(goalID) },
                    onShowAll: { showingAllGoals = true }
                )
                .frame(width: askBarWidth)
                .padding(.bottom, intelligenceStore.goals.isEmpty ? 0 : OmiSpacing.sm)

                homeStatRibbon
                    .frame(width: askBarWidth)
                    .padding(.bottom, OmiSpacing.md)

                homeAskBar
                    .frame(width: askBarWidth)

                homeSuggestionList
                    .frame(width: askBarWidth)
                    .padding(.top, OmiSpacing.md)
                    .transition(.homeSuggestionsFade)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// Panel layout (chat / connect): the surface fills the height with the ask
    /// bar anchored directly beneath it.
    private func homePanelStage(stageWidth: CGFloat, askBarWidth: CGFloat) -> some View {
        VStack(spacing: 0) {
            ZStack {
                switch homeMode {
                case .chat:
                    homeChatPanel(stageWidth: stageWidth)
                        .transition(.homeDropFromTop)
                case .connect:
                    homeConnectPanel(stageWidth: stageWidth)
                        .transition(.homeDropFromTop)
                case .hub:
                    EmptyView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            homeAskBar
                .frame(width: askBarWidth)
                .padding(.top, OmiSpacing.xl)

            dashboardChatErrorCard
                .frame(width: askBarWidth)
                .padding(.top, OmiSpacing.sm)
        }
    }

    // MARK: Hub centerpiece

    private var homeHubWordmark: some View {
        Text("omi.")
            .font(.system(size: 58, weight: .bold, design: .rounded))
            .foregroundStyle(HomePalette.ink)
            .lineLimit(1)
            .shadow(color: HomePalette.jewelGlow.opacity(0.22), radius: 24)
            .frame(maxWidth: .infinity, alignment: .center)
    }

    /// Stat summary strip that docks directly above the ask bar.
    private var homeStatRibbon: some View {
        HomeStatRibbon(items: [
            HomeStatItem(
                title: "Conversations",
                value: conversationMetricValue,
                systemImage: "text.bubble.fill",
                action: { navigate(to: .conversations) }
            ),
            HomeStatItem(
                title: "Tasks",
                value: taskMetricValue,
                systemImage: "checklist",
                action: { navigate(to: .tasks) }
            ),
            HomeStatItem(
                title: "Memories",
                value: memoryMetricValue,
                systemImage: "brain",
                action: { navigate(to: .memories) }
            ),
            HomeStatItem(
                title: "Screenshots",
                value: screenshotMetricValue,
                systemImage: "photo.on.rectangle.angled",
                action: { navigate(to: .rewind) }
            ),
        ])
    }

    // MARK: Inline chat panel

    private func homeChatPanel(stageWidth: CGFloat) -> some View {
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
                sessionsLoadError: chatProvider.sessionsLoadError.map {
                    UserFacingErrorPresentation.message(from: $0, while: .chatSessions)
                },
                onRetry: { Task { await chatProvider.retryLoad() } },
                localSendToken: chatProvider.localSendToken,
                onCancelTurn: { chatProvider.stopAgent(owner: .mainChat) },
                onOpenAgent: { agentID, completion in
                    FloatingControlBarManager.shared.openAgentChatFromTimeline(agentID: agentID, completion: completion)
                },
                onOpenAgentRef: { ref, completion in
                    FloatingControlBarManager.shared.openAgentChatFromTimeline(ref: ref, completion: completion)
                },
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
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)

            dashboardChatErrorCard
                .padding(.horizontal, OmiSpacing.md)
                .padding(.bottom, OmiSpacing.sm)
        }
        // Barely-there card so the chat reads as a bounded surface while still
        // dissolving into the ambient Home canvas.
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.018),
                            Color.white.opacity(0.009),
                            Color.white.opacity(0.006),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
                .stroke(HomePalette.hairline.opacity(0.50), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.24), radius: 28, y: 8)
        .frame(width: homeStagePanelWidth(for: stageWidth))
    }

    // MARK: Connect tray

    private func homeConnectPanel(stageWidth: CGFloat) -> some View {
        // Sources feed omi; omi's memory flows out to the AI destinations —
        // the chevron between the two cards reads that direction. The tray
        // hugs its content: no scroll filler below the columns.
        HStack(alignment: .center, spacing: OmiSpacing.md) {
            homeConnectColumnCard {
                VStack(alignment: .leading, spacing: OmiSpacing.md) {
                    sourceColumnHeader
                    sourceConstellation
                }
            }

            Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.body, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
                .frame(width: 30, height: 30)
                .background(Circle().fill(HomePalette.tile))
                .overlay(Circle().stroke(HomePalette.hairline, lineWidth: 1))
                .accessibilityHidden(true)

            homeConnectColumnCard {
                destinationStack
            }
        }
        .padding(OmiSpacing.lg)
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
            .padding(OmiSpacing.md)
        }
        .shadow(color: .black.opacity(0.4), radius: 30, y: 16)
        .frame(width: homeStagePanelWidth(for: stageWidth))
    }

    private func homeConnectColumnCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(OmiSpacing.lg)
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

    @ViewBuilder
    private var dashboardChatErrorCard: some View {
        if let cardState = chatProvider.currentError {
            ChatErrorCard(
                state: cardState,
                onRecover: {
                    Task { await chatProvider.recoverFromError() }
                },
                onDismiss: {
                    chatProvider.dismissCurrentError()
                }
            )
        }
    }

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
            onActivate: { openHomeChat() }
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
        VStack(spacing: OmiSpacing.sm) {
            ForEach(homeSuggestedQuestions, id: \.self) { question in
                HomeSuggestionRow(text: question) {
                    askHomeSuggestion(question)
                }
            }
        }
    }

    private func homeStageSideInset(for stageWidth: CGFloat) -> CGFloat {
        min(Self.homeStageMaxSideInset, max(Self.homeStageMinSideInset, stageWidth * 0.06))
    }

    private func homeStageContentWidth(for stageWidth: CGFloat) -> CGFloat {
        let sideInset = homeStageSideInset(for: stageWidth)
        return min(Self.homeStageMaxWidth, max(CGFloat(0), stageWidth - (sideInset * 2)))
    }

    private func homeStagePanelWidth(for stageWidth: CGFloat) -> CGFloat {
        min(Self.homeStagePanelMaxWidth, homeStageContentWidth(for: stageWidth))
    }

    private func homeAskBarWidth(for stageWidth: CGFloat) -> CGFloat {
        let contentWidth = homeStageContentWidth(for: stageWidth)
        if homeMode != .hub {
            return min(Self.homeStagePanelMaxWidth, contentWidth)
        }

        let availableWidth = min(Self.homeAskBarMaxWidth, contentWidth)
        let text = chatProvider.draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            return min(availableWidth, Self.homeAskBarMinWidth)
        }

        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 15),
        ]
        let measuredTextWidth = (text as NSString).size(withAttributes: attributes).width
        let chromeWidth: CGFloat = 210
        return min(availableWidth, max(Self.homeAskBarMinWidth, measuredTextWidth + chromeWidth))
    }

    // MARK: Stage actions

    private func reportHomeAutomationMode() {
        guard DesktopAutomationLaunchOptions.isEnabled else { return }
        let modeLabel = useLegacyHomeDesign ? nil : homeMode.automationLabel
        _ = DesktopAutomationStateStore.shared.updateLiveFields { snapshot in
            snapshot.homeMode = modeLabel
            snapshot.updatedAt = ISO8601DateFormatter().string(from: Date())
        }
    }

    private func openHomeChat(focusInput: Bool = true) {
        guard homeMode != .chat else { return }
        OmiMotion.withGated(Self.homeStageAnimation) {
            homeMode = .chat
        }
        if focusInput {
            focusHomeAskFieldAfterStageTransition()
        }
        reportHomeAutomationMode()
    }

    private func focusHomeAskFieldAfterStageTransition() {
        Task { @MainActor in
            await Task.yield()
            homeAskFieldFocused = true
        }
    }

    private func toggleHomeConnectPanel() {
        let target: HomeStageMode = homeMode == .connect ? .hub : .connect
        if target == .connect {
            homeAskFieldFocused = false
        }
        OmiMotion.withGated(Self.homeStageAnimation) {
            homeMode = target
        }
        reportHomeAutomationMode()
    }

    private func closeHomeStagePanel() {
        homeAskFieldFocused = false
        OmiMotion.withGated(Self.homeStageAnimation) {
            homeMode = .hub
        }
        reportHomeAutomationMode()
    }

    private func sendFromHomeAskBar() {
        let draft = chatProvider.draftText
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        // Text is required — ChatProvider.sendMessage no-ops on empty text, so
        // an attachment-only "send" would silently drop the turn.
        guard !text.isEmpty else { return }
        openHomeChat(focusInput: false)
        AnalyticsManager.shared.chatMessageSent(
            messageLength: text.count,
            hasSelectedAppContext: selectedApp != nil,
            source: "home_ask_bar"
        )
        if chatProvider.isSending {
            return
        } else {
            Task { await chatProvider.sendMainDraft(draft) }
        }
    }

    private func askHomeSuggestion(_ suggestion: String) {
        openHomeChat(focusInput: false)
        AnalyticsManager.shared.chatMessageSent(
            messageLength: suggestion.count,
            hasSelectedAppContext: selectedApp != nil,
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
                    connectorStatusStore: homeStatusStore.connectorStatusStore,
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
                statusStore: homeStatusStore.connectorStatusStore,
                onDismiss: {
                    dismissHomeConnectSheet()
                }
            )
        } else if let destination = selectedExportDestination {
            ConnectDestinationSheet(
                destination: destination,
                statuses: $homeStatusStore.memoryExportStatuses,
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
        let transcriptionUnavailable = appState.transcriptionServiceError != nil

        return HStack {
            Spacer()
            HStack(spacing: OmiSpacing.sm) {
                HomeStatusButton(
                    title: "Capture",
                    systemImage: "viewfinder",
                    status: captureStatus,
                    isToggling: isTogglingCapture,
                    action: toggleCapture
                )

                HomeListeningStatusButton(
                    title: transcriptionUnavailable ? "Transcription unavailable" : "Listening",
                    systemImage: transcriptionUnavailable
                        ? "exclamationmark.triangle.fill"
                        : (appState.isTranscribing ? "waveform.circle.fill" : "mic.circle"),
                    status: transcriptionUnavailable ? .blocked : (appState.isTranscribing ? .active : .inactive),
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
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Connect data")
                .font(.system(size: 20, weight: .medium, design: .serif))
                .foregroundStyle(HomePalette.ink)

            Text("Sources Omi learns from.")
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundStyle(HomePalette.muted)
                .lineLimit(1)
        }
    }

    private var sourceConstellation: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
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
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Use omi memory anywhere")
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(HomePalette.ink)

                Text("Bring your memories to the apps you use")
                    .scaledFont(size: OmiType.caption, weight: .medium)
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
                openExportDestination(.chatgpt)
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
        formattedCount(
            homeStatusStore.conversationCount ?? appState.totalConversationsCount ?? appState.conversations.count
        )
    }

    private var taskMetricValue: String {
        formattedCount(homeStatusStore.taskCount ?? incompleteTaskCount)
    }

    private var memoryMetricValue: String {
        let count = homeStatusStore.memoryCount ?? (memoriesViewModel.totalMemoriesCount > 0
            ? memoriesViewModel.totalMemoriesCount
            : memoriesViewModel.memories.count)
        return formattedCount(count)
    }

    private var screenshotMetricValue: String {
        homeStatusStore.screenshotCount.map(formattedCount) ?? "—"
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
                ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
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

    private func formattedCount(_ count: Int) -> String {
        count.formatted()
    }

    /// Welcome message shown when there are no chat messages yet.
    /// Transparent — no card chrome — so it morphs into the dashboard background.
    private var dashboardChatWelcome: some View {
        VStack(spacing: OmiSpacing.md) {
            if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                let logoImage = NSImage(contentsOf: logoURL)
            {
                Image(nsImage: logoImage)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 40, height: 40)
            }

            Text("Ask omi anything")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Your personal AI assistant — knows you through your memories and conversations")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, OmiSpacing.page)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, OmiSpacing.section)
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

    private func openRecommendation(_ recommendation: DashboardRecommendation) async -> Bool {
        switch recommendation.destination {
        case .suggested(let candidateID):
            guard let candidate = await intelligenceStore.candidateForNavigation(candidateID: candidateID) else {
                return false
            }
            TaskNavigationRequestStore.shared.request(candidate: candidate)
            selectedIndex = 4
            return true
        case .task(let taskID, let workstreamID):
            if let workstreamID {
                return await resumeThread(workstreamID: workstreamID, taskID: taskID)
            } else {
                guard let task = await intelligenceStore.taskForNavigation(taskID: taskID) else {
                    return false
                }
                TaskNavigationRequestStore.shared.request(task: task)
                selectedIndex = 4
                return true
            }
        case .thread(let workstreamID, let taskID):
            return await resumeThread(workstreamID: workstreamID, taskID: taskID)
        case .unavailable:
            intelligenceStore.error = "This review target is no longer available."
            return false
        }
    }

    private func openGoal(_ goalID: String) async {
        await intelligenceStore.loadGoalDetail(goalID: goalID)
        guard intelligenceStore.selectedGoalDetail != nil else { return }
        showingAllGoals = false
        showingGoalDetail = true
    }

    @discardableResult
    private func resumeThread(workstreamID: String, taskID: String?) async -> Bool {
        guard let taskChatCoordinator else {
            intelligenceStore.error = "The task thread is unavailable."
            return false
        }
        if await taskChatCoordinator.openExistingThread(
            workstreamID: workstreamID,
            preferredTaskID: taskID
        ) {
            showingGoalDetail = false
            showingAllGoals = false
            selectedIndex = 4
            return true
        } else {
            intelligenceStore.error = taskChatCoordinator.errorMessage ?? "The task thread could not be opened."
            return false
        }
    }

    private func startWorkFromSelectedGoal() async {
        guard let detail = intelligenceStore.selectedGoalDetail, let taskChatCoordinator else {
            intelligenceStore.error = "The goal thread is unavailable."
            return
        }
        do {
            let receipt = try await taskChatCoordinator.resolveGoalOrigin(
                goalId: detail.goal.goalId,
                occurrenceId: "goal-detail-primary-v1",
                title: detail.goal.title,
                objective: detail.goal.desiredOutcome,
                anchorTaskDescription: "Make progress on \(detail.goal.title)"
            )
            await resumeThread(workstreamID: receipt.workstreamId, taskID: receipt.taskId)
        } catch {
            intelligenceStore.error = "Omi could not start work on this goal."
        }
    }

    // MARK: - Summary counts for collapsed bar

    private var incompleteTaskCount: Int {
        viewModel.overdueTasks.count + viewModel.todaysTasks.count + viewModel.recentTasks.count
    }

    private var activeGoalCount: Int {
        intelligenceStore.accountGeneration == nil
            ? viewModel.goals.count
            : intelligenceStore.currentGoals.count
    }

    // MARK: - Dashboard Widgets (collapsible)

    private var dashboardWidgets: some View {
        VStack(alignment: .leading, spacing: widgetsCollapsed ? 0 : OmiSpacing.xl) {
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

            WhatMattersNowSection(
                store: intelligenceStore,
                onOpen: { recommendation in await openRecommendation(recommendation) }
            )

            dashboardIntelligenceError

            FocusedGoalsSection(
                store: intelligenceStore,
                onOpenGoal: { goalID in await openGoal(goalID) },
                onShowAll: { showingAllGoals = true }
            )

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
        .padding(.horizontal, OmiSpacing.section)
        .padding(.top, widgetsCollapsed ? OmiSpacing.xl : OmiSpacing.section)
        .padding(.bottom, OmiSpacing.sm)
        .omiAnimation(.easeInOut(duration: 0.25), value: widgetsCollapsed)
    }

    @ViewBuilder
    private var dashboardIntelligenceError: some View {
        if let error = intelligenceStore.error, !error.isEmpty {
            HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.warning)
                Text(error)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textSecondary)
                Spacer(minLength: OmiSpacing.sm)
                Button("Retry") {
                    Task { await intelligenceStore.load() }
                }
                .buttonStyle(.plain)
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(0.88))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .stroke(OmiColors.border.opacity(0.7), lineWidth: 1)
            )
            .accessibilityIdentifier("dashboard-intelligence-error")
        }
    }

    private var collapsedWidgetBar: some View {
        Button(action: { widgetsCollapsed = false }) {
            HStack(spacing: OmiSpacing.lg) {
                // Tasks summary
                HStack(spacing: OmiSpacing.xs) {
                    Image(systemName: "checklist")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(incompleteTaskCount == 0
                        ? "No tasks"
                        : "\(incompleteTaskCount) task\(incompleteTaskCount == 1 ? "" : "s")")
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }

                // Subtle divider dot
                Circle()
                    .fill(OmiColors.textQuaternary)
                    .frame(width: 3, height: 3)

                // Goals summary
                HStack(spacing: OmiSpacing.xs) {
                    Image(systemName: "target")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(activeGoalCount == 0
                        ? "No goals"
                        : "\(activeGoalCount) goal\(activeGoalCount == 1 ? "" : "s")")
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }

                Spacer()

                // Expand chevron
                Image(systemName: "chevron.down")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundColor(OmiColors.textQuaternary)
            }
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.md)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
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
        Grid(horizontalSpacing: OmiSpacing.xl, verticalSpacing: OmiSpacing.xl) {
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

                if intelligenceStore.accountGeneration != nil {
                    canonicalGoalsWidget
                } else {
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
                            Task { await viewModel.updateGoalProgress(goal, currentValue: value) }
                        },
                        onDeleteGoal: { goal in
                            Task { await viewModel.deleteGoal(goal) }
                        }
                    )
                    .frame(minWidth: 0, maxWidth: .infinity)
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private var canonicalGoalsWidget: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            HStack {
                Text("Goals")
                    .scaledFont(size: OmiType.subheading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                Button("All goals") { showingAllGoals = true }
                    .buttonStyle(.plain)
                    .scaledFont(size: OmiType.micro, weight: .medium)
            }
            FocusedGoalsSection(
                store: intelligenceStore,
                onOpenGoal: { goalID in await openGoal(goalID) },
                onShowAll: { showingAllGoals = true }
            )
            if intelligenceStore.focusedGoals.isEmpty {
                Text("Keep a few outcomes in focus.")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textSecondary)
            }
            Spacer(minLength: 0)
        }
        .padding(OmiSpacing.lg)
        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.backgroundSecondary.opacity(0.65))
        )
    }

    private var collapseButton: some View {
        HStack {
            Spacer()
            Button(action: { widgetsCollapsed = true }) {
                Image(systemName: "chevron.up")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
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
    /// The Home jewel is intentionally neutral: one soft light shared only by
    /// the wordmark and focused ask bar, never by secondary cards or states.
    static let jewelGlow = OmiColors.accent
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
        VStack(spacing: OmiSpacing.sm) {
            if !attachments.isEmpty {
                AttachmentPreviewRow(
                    attachments: attachments,
                    onRemove: onAttachmentRemoved
                )
                .padding(.top, OmiSpacing.sm)
                .padding(.horizontal, OmiSpacing.md)
            }

            HStack(spacing: OmiSpacing.sm) {
                Button(action: pickFiles) {
                    Image(systemName: "paperclip")
                        .scaledFont(size: OmiType.subheading, weight: .medium)
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
                .onSubmit(handleSubmit)

                actionButton
            }
            .padding(.leading, OmiSpacing.lg)
            .padding(.trailing, OmiSpacing.sm)
            .frame(height: 58)
        }
        .background(
            RoundedRectangle(cornerRadius: 29, style: .continuous)
                .fill(HomePalette.tile.opacity(isHovering || isFocused ? 1 : 0.92))
        )
        .overlay {
            if isDropTargeted {
                RoundedRectangle(cornerRadius: 29, style: .continuous)
                    .stroke(Color.white.opacity(0.42), lineWidth: 1)
            } else {
                RoundedRectangle(cornerRadius: 29, style: .continuous)
                    .stroke(
                        isFocused
                            ? HomePalette.jewelGlow.opacity(0.18)
                            : HomePalette.hairline.opacity(0.72),
                        lineWidth: 1
                    )
                    .blur(radius: 1.8)
            }
        }
        .shadow(
            color: HomePalette.jewelGlow.opacity(isFocused ? 0.08 : 0),
            radius: isFocused ? 22 : 0,
            y: 8
        )
        .shadow(color: .black.opacity(isFocused ? 0.45 : 0.34), radius: 24, y: 10)
        .contentShape(.rect(cornerRadius: 29))
        .onTapGesture {
            onActivate()
            focus.wrappedValue = true
        }
        .onHover { isHovering = $0 }
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
        .omiAnimation(.easeOut(duration: 0.16), value: isFocused)
        .omiAnimation(.easeOut(duration: 0.16), value: canSend)
        .omiAnimation(.easeOut(duration: 0.16), value: attachments.count)
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

    private func handleSubmit() {
        if isSending {
            onStop()
        } else if canSend {
            onSend()
        }
    }

    @ViewBuilder
    private var actionButton: some View {
        switch actionMode {
        case .stop:
            stopButton
        case .send:
            sendButton
        case .connect:
            connectButton
        case .none:
            EmptyView()
        }
    }

    private var actionMode: HomeAskBarActionMode {
        if isSending { return .stop }
        if canSend { return .send }
        if isFocused { return .none }
        return .connect
    }

    private var sendButton: some View {
        Button(action: handleSubmit) {
            ZStack {
                Circle()
                    .fill(Color.white)

                Image(systemName: "arrow.up")
                    .scaledFont(size: OmiType.body, weight: .bold)
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
                        .scaledFont(size: OmiType.micro, weight: .bold)
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

private enum HomeAskBarActionMode: Equatable {
    case connect
    case send
    case stop
    case none
}

private struct HomeAskBarConnectButton: View {
    let isActive: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "link")
                    .scaledFont(size: OmiType.caption, weight: .semibold)

                Text("Connect")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
            }
            .foregroundStyle(isActive ? Color.black : HomePalette.ink)
            .padding(.horizontal, OmiSpacing.md)
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
            HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "sparkles")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(isHovering ? Color(hex: 0xE3BF63) : HomePalette.muted)

                Text(text)
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)
                    .lineLimit(1)

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: OmiType.micro, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.faint)
            }
            .padding(.horizontal, OmiSpacing.lg)
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

            // Neutral key light high behind the wordmark, with a soft ambient
            // wash so the redesigned Home stage reads against the dark canvas.
            RadialGradient(
                colors: [Color.white.opacity(0.040), .clear],
                center: UnitPoint(x: 0.5, y: 0.16),
                startRadius: 0,
                endRadius: 560
            )

            RadialGradient(
                colors: [.clear, HomePalette.paper.opacity(0.88), Color.black.opacity(0.62)],
                center: UnitPoint(x: 0.50, y: 0.48),
                startRadius: 470,
                endRadius: 900
            )

            LinearGradient(
                stops: [
                    .init(color: .clear, location: 0.50),
                    .init(color: Color.white.opacity(0.014), location: 0.90),
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
            HStack(spacing: OmiSpacing.sm) {
                ConnectorBrandIcon(brand: brand, size: 20, cornerRadius: OmiChrome.badgeRadius)

                Text(title)
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .lineLimit(1)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .frame(minWidth: 118)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .fill(HomePalette.green.opacity(isHovering ? 0.92 : 1))
            )
            .shadow(color: HomePalette.green.opacity(isHovering ? 0.22 : 0.12), radius: 12, y: 5)
            .contentShape(.rect(cornerRadius: OmiChrome.smallControlRadius))
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
            HStack(spacing: OmiSpacing.xs) {
                icon

                Text(title)
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .lineLimit(1)

                Image(systemName: "chevron.right")
                    .scaledFont(size: OmiType.micro, weight: .bold)
                    .foregroundStyle(HomePalette.faint)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
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
            ConnectorBrandIcon(brand: brand, size: 18, cornerRadius: OmiChrome.badgeRadius)
        } else if let systemImage {
            Image(systemName: systemImage)
                .scaledFont(size: OmiType.caption, weight: .semibold)
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
            VStack(spacing: OmiSpacing.sm) {
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

                HStack(spacing: OmiSpacing.xxs) {
                    Text(title)
                        .scaledFont(size: OmiType.caption, weight: .semibold)
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
                    .stroke(isHovering ? HomePalette.ink.opacity(0.26) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? .black.opacity(0.20) : .clear, radius: 14, y: 6)
            .contentShape(.rect(cornerRadius: 17))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel(title)
    }

    @ViewBuilder
    private var icon: some View {
        if usesOmiDeviceImage {
            HomeOmiDeviceIcon(size: 42, cornerRadius: OmiChrome.smallControlRadius)
        } else if let brand {
            ConnectorBrandIcon(brand: brand, size: 42, cornerRadius: OmiChrome.smallControlRadius)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
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
            HStack(spacing: OmiSpacing.md) {
                icon

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 10)

                HStack(spacing: OmiSpacing.xxs) {
                    if isConnected {
                        Circle()
                            .fill(HomePalette.green)
                            .frame(width: 5, height: 5)
                    }

                    Text(actionTitle)
                        .scaledFont(size: OmiType.caption, weight: .semibold)
                        .foregroundStyle(isConnected ? HomePalette.green : HomePalette.secondary)
                        .lineLimit(1)

                    if !isConnected && actionTitle == "Browse" {
                        Image(systemName: "chevron.right")
                            .scaledFont(size: OmiType.micro, weight: .bold)
                            .foregroundStyle(HomePalette.faint)
                    }
                }
                .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.md)
            .frame(height: 64)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(isHovering ? HomePalette.ink.opacity(0.24) : HomePalette.hairline.opacity(0.9), lineWidth: 1)
            )
            .shadow(color: isHovering ? .black.opacity(0.18) : .clear, radius: 12, y: 5)
            .contentShape(.rect(cornerRadius: 15))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(subtitle), \(actionTitle)")
    }

    @ViewBuilder
    private var icon: some View {
        if let brand {
            ConnectorBrandIcon(brand: brand, size: 36, cornerRadius: OmiChrome.smallControlRadius)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .fill(Color.white.opacity(0.04))
                Image(systemName: systemImage)
                    .scaledFont(size: OmiType.subheading, weight: .semibold)
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
            HStack(spacing: OmiSpacing.sm) {
                icon

                Text(title)
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(HomePalette.ink)
                    .lineLimit(1)

                Spacer(minLength: 8)

                if isConnected {
                    Text("Connected")
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundStyle(HomePalette.faint)
                }

                Image(systemName: "chevron.right")
                    .scaledFont(size: OmiType.micro, weight: .bold)
                    .foregroundStyle(HomePalette.faint)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.md)
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
                .scaledFont(size: OmiType.body, weight: .bold)
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
            VStack(spacing: OmiSpacing.xs) {
                ZStack(alignment: .topTrailing) {
                    ConnectorBrandIcon(brand: brand, size: 44, cornerRadius: 13)
                        .shadow(color: .black.opacity(isHovering ? 0.16 : 0.08), radius: 9, y: 4)

                    if let badge {
                        Text(badge)
                            .scaledFont(size: 8, weight: .bold)
                            .foregroundStyle(.white)
                            .padding(.horizontal, OmiSpacing.xxs)
                            .padding(.vertical, OmiSpacing.hairline)
                            .background(Capsule(style: .continuous).fill(HomePalette.green))
                            .offset(x: 8, y: -6)
                    }
                }

                Text(title)
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .lineLimit(1)
            }
            .padding(OmiSpacing.sm)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
                    .fill(isHovering ? HomePalette.panel : Color.clear)
            )
            .contentShape(.rect(cornerRadius: OmiChrome.controlRadius))
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
            HStack(spacing: OmiSpacing.sm) {
                ConnectorBrandIcon(brand: brand, size: 34, cornerRadius: 9)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: OmiType.caption, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.green : HomePalette.faint)
            }
            .padding(OmiSpacing.md)
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
            HStack(alignment: .top, spacing: OmiSpacing.md) {
                Text("Connect Omi to ChatGPT, Claude, or ask Omi directly...")
                    .scaledFont(size: OmiType.subheading, weight: .regular)
                    .foregroundStyle(HomePalette.faint)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, OmiSpacing.hairline)

                Button(action: onAskOmi) {
                    Image(systemName: "arrow.up.circle")
                        .scaledFont(size: 24, weight: .regular)
                        .foregroundStyle(HomePalette.faint)
                }
                .buttonStyle(.plain)
                .help("Ask Omi")
            }
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.top, OmiSpacing.lg)
            .padding(.bottom, OmiSpacing.xxl)

            HStack(spacing: OmiSpacing.sm) {
                Button(action: onChatGPT) {
                    HStack(spacing: OmiSpacing.sm) {
                        ConnectorBrandIcon(brand: .chatgpt, size: 22, cornerRadius: OmiChrome.badgeRadius)
                        Text("Connect ChatGPT")
                            .scaledFont(size: OmiType.body, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, OmiSpacing.sm)
                    .foregroundStyle(.white)
                    .background(
                        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                            .fill(HomePalette.green)
                    )
                }
                .buttonStyle(.plain)

                Button(action: onClaude) {
                    HStack(spacing: OmiSpacing.sm) {
                        ConnectorBrandIcon(brand: .claude, size: 22, cornerRadius: OmiChrome.badgeRadius)
                        Text("Claude")
                            .scaledFont(size: OmiType.body, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, OmiSpacing.sm)
                    .foregroundStyle(HomePalette.secondary)
                    .background(
                        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                            .fill(HomePalette.tile)
                    )
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.bottom, OmiSpacing.md)
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
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                HStack(alignment: .top) {
                    iconView
                    Spacer()
                    statusView
                }

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }
            }
            .padding(OmiSpacing.sm)
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
                    .scaledFont(size: OmiType.body, weight: .semibold)
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
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
        case .connected:
            Image(systemName: "checkmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(HomePalette.green)
        case .open:
            Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(HomePalette.secondary)
        }
    }
}

private struct HomeStatItem: Identifiable {
    let id = UUID()
    let title: String
    let value: String
    let systemImage: String
    let action: () -> Void
}

/// Slim summary strip: the four Home metrics fused into a single
/// hairline-divided bar so they read as one glanceable object instead of
/// four heavy widgets. Each cell still hovers and navigates.
private struct HomeStatRibbon: View {
    let items: [HomeStatItem]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Rectangle()
                        .fill(HomePalette.hairline.opacity(0.7))
                        .frame(width: 1)
                        .padding(.vertical, OmiSpacing.lg)
                }
                HomeStatRibbonCell(item: item)
            }
        }
        // Pin the height so the hairline dividers (greedy Rectangles) size to the
        // content instead of stretching the whole strip in taller windows.
        .frame(height: 76)
        .background(HomePalette.tile.opacity(0.88))
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
                .stroke(HomePalette.hairline.opacity(0.8), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.16), radius: 10, y: 8)
    }
}

private struct HomeStatRibbonCell: View {
    let item: HomeStatItem

    @State private var isHovering = false

    var body: some View {
        Button(action: item.action) {
            VStack(spacing: OmiSpacing.xxs) {
                HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.xs) {
                    Image(systemName: item.systemImage)
                        .scaledFont(size: OmiType.caption, weight: .semibold)
                        .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)

                    Text(item.value)
                        .font(.system(size: 22, weight: .medium, design: .serif))
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                }

                Text(item.title)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundStyle(isHovering ? HomePalette.secondary : HomePalette.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, OmiSpacing.md)
            .padding(.horizontal, OmiSpacing.sm)
            .background(isHovering ? HomePalette.tileHover : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(item.title), \(item.value)")
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
            HStack(spacing: OmiSpacing.md) {
                ZStack {
                    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                        .fill(Color.white.opacity(0.055))

                    Image(systemName: systemImage)
                        .scaledFont(size: OmiType.subheading, weight: .semibold)
                        .foregroundStyle(HomePalette.ink)
                }
                .frame(width: 42, height: 42)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(value)
                        .font(.system(size: 21, weight: .medium, design: .serif))
                        .foregroundStyle(HomePalette.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    Text(title)
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: OmiType.micro, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.faint)
            }
            .padding(.horizontal, OmiSpacing.md)
            .frame(height: 76)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(isHovering ? HomePalette.ink.opacity(0.26) : HomePalette.hairline.opacity(0.86), lineWidth: 1)
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
            HStack(spacing: OmiSpacing.xs) {
                Image(systemName: systemImage)
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)

                Text(value)
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(HomePalette.ink)

                Text(title)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundStyle(HomePalette.muted)
                    .lineLimit(1)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
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
            .padding(OmiSpacing.lg)
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
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(eyebrow.uppercased())
                .scaledFont(size: OmiType.micro, weight: .bold)
                .foregroundStyle(HomePalette.green)

            Text(title)
                .scaledFont(size: OmiType.heading, weight: .semibold)
                .foregroundStyle(HomePalette.ink)
                .lineLimit(1)

            Text(subtitle)
                .scaledFont(size: OmiType.caption)
                .foregroundStyle(HomePalette.muted)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(2)
        }
    }
}

private struct HomeBridgeChevron: View {
    var body: some View {
        VStack(spacing: OmiSpacing.sm) {
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
                .scaledFont(size: OmiType.subheading, weight: .bold)
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
            HStack(spacing: OmiSpacing.sm) {
                rowIcon

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                statusView
            }
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.sm)
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
            ConnectorBrandIcon(brand: brand, size: 32, cornerRadius: OmiChrome.elementRadius)
        } else if let systemImage {
            ZStack {
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
                    .fill(OmiColors.backgroundPrimary.opacity(0.78))
                Image(systemName: systemImage)
                    .scaledFont(size: OmiType.body, weight: .semibold)
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
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(OmiColors.success)
        case .connected:
            Image(systemName: "checkmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(OmiColors.success)
        case .open:
            Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.caption, weight: .bold)
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
            HStack(spacing: OmiSpacing.sm) {
                rowIcon

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(prominence == .primary ? HomePalette.ink : HomePalette.secondary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption)
                        .foregroundStyle(HomePalette.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: OmiType.caption, weight: .bold)
                    .foregroundStyle(isHovering ? HomePalette.green : HomePalette.faint)
            }
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.sm)
            .background(rowBackground)
            .overlay(rowStroke)
            .contentShape(.rect(cornerRadius: OmiChrome.chipRadius))
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
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
            }
            .frame(width: 34, height: 34)
        }
    }

    private var rowBackground: some View {
        RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
            .fill(
                prominence == .primary
                    ? HomePalette.green.opacity(isHovering ? 0.20 : 0.12)
                    : (isHovering ? HomePalette.tileHover : HomePalette.tile)
            )
    }

    private var rowStroke: some View {
        RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
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
            VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                HStack {
                    Image(systemName: systemImage)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(accent)

                    Spacer()

                    Image(systemName: "arrow.up.right")
                        .scaledFont(size: OmiType.micro, weight: .bold)
                        .foregroundStyle(isHovering ? accent : OmiColors.textQuaternary)
                }

                Text(value)
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundStyle(OmiColors.textPrimary)
                    .lineLimit(1)

                Text(title)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundStyle(OmiColors.textTertiary)
                    .lineLimit(1)
            }
            .padding(OmiSpacing.md)
            .frame(minHeight: 86, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
                    .fill(Color.white.opacity(isHovering ? 0.08 : 0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
                    .stroke(isHovering ? accent.opacity(0.34) : Color.white.opacity(0.07), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: OmiChrome.controlRadius))
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
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(title)
                .scaledFont(size: OmiType.heading, weight: .semibold)
                .foregroundStyle(OmiColors.textPrimary)

            Text(subtitle)
                .scaledFont(size: OmiType.caption)
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
            HStack(spacing: OmiSpacing.sm) {
                ZStack {
                    if isToggling {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.55)
                    } else {
                        Image(systemName: systemImage)
                            .scaledFont(size: OmiType.body, weight: .semibold)
                    }
                }
                .frame(width: 18, height: 18)

                Text(title)
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .lineLimit(1)
            }
            .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
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
                HStack(spacing: OmiSpacing.sm) {
                    ZStack {
                        if isToggling {
                            ProgressView()
                                .controlSize(.small)
                                .scaleEffect(0.55)
                        } else {
                            Image(systemName: systemImage)
                                .scaledFont(size: OmiType.body, weight: .semibold)
                        }
                    }
                    .frame(width: 18, height: 18)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(title)
                            .scaledFont(size: OmiType.caption, weight: .semibold)
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
                .padding(.leading, OmiSpacing.md)
                .padding(.trailing, OmiSpacing.sm)
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
                        .scaledFont(size: OmiType.caption, weight: .semibold)
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
        .omiAnimation(.easeInOut(duration: 0.14), value: isHovering)
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
                .scaledFont(size: OmiType.body, weight: .semibold)
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
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)
            }
            .frame(width: 34, height: 34)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .popover(isPresented: $isPresented, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                popoverButton(title: "Refer a Friend", systemImage: "gift.fill") {
                    isPresented = false
                    onRefer()
                }

                popoverButton(title: "Discord", systemImage: "message.fill") {
                    isPresented = false
                    onDiscord()
                }

                Divider()
                    .padding(.vertical, OmiSpacing.hairline)

                popoverButton(title: "Settings", systemImage: "gearshape.fill") {
                    isPresented = false
                    onSettings()
                }
            }
            .padding(OmiSpacing.sm)
            .frame(width: 190)
            .background(HomePalette.panel)
        }
        .help("Settings")
        .accessibilityLabel("Settings menu")
    }

    private func popoverButton(title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: OmiSpacing.sm) {
                Image(systemName: systemImage)
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .frame(width: 18)

                Text(title)
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundStyle(HomePalette.ink)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .contentShape(.rect(cornerRadius: OmiChrome.elementRadius))
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
            HStack(spacing: OmiSpacing.md) {
                ConnectorBrandIcon(brand: brand, size: 36, cornerRadius: 9)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(subtitle)
                        .scaledFont(size: OmiType.caption)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 10)

                if let status {
                    HStack(spacing: OmiSpacing.xxs) {
                        Image(systemName: "checkmark")
                            .scaledFont(size: OmiType.micro, weight: .bold)
                        Text(status)
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                    }
                    .foregroundStyle(OmiColors.success)
                    .lineLimit(1)
                } else {
                    HStack(spacing: OmiSpacing.xxs) {
                        Image(systemName: "plus")
                            .scaledFont(size: OmiType.micro, weight: .bold)
                        Text(actionTitle)
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                    }
                    .foregroundStyle(OmiColors.success)
                    .lineLimit(1)
                }
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .frame(minHeight: 56)
            .background(cardBackground)
            .overlay(cardStroke)
            .contentShape(.rect(cornerRadius: OmiChrome.smallControlRadius))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityLabel("\(title), \(status ?? actionTitle)")
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
            .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.94 : 0.72))
    }

    private var cardStroke: some View {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
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
            HStack(spacing: OmiSpacing.md) {
                ZStack {
                    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                        .fill(OmiColors.backgroundPrimary)
                        .overlay(
                            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                                .stroke(OmiColors.border.opacity(0.55), lineWidth: 1)
                        )

                    Image(systemName: "square.grid.2x2.fill")
                        .scaledFont(size: OmiType.subheading, weight: .semibold)
                        .foregroundStyle(OmiColors.textSecondary)
                }
                .frame(width: 36, height: 36)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text("Connect more")
                        .scaledFont(size: OmiType.body, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)

                    Text("Browse all apps")
                        .scaledFont(size: OmiType.caption)
                        .foregroundStyle(OmiColors.textTertiary)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(OmiColors.success)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .frame(minHeight: 56)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.94 : 0.72))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                    .stroke(
                        isHovering ? OmiColors.success.opacity(0.32) : OmiColors.border.opacity(0.42),
                        lineWidth: 1
                    )
            )
            .contentShape(.rect(cornerRadius: OmiChrome.smallControlRadius))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

private struct HomeFlowArrow: View {
    var body: some View {
        VStack(spacing: OmiSpacing.xxs) {
            Rectangle()
                .fill(OmiColors.border.opacity(0.75))
                .frame(width: 1, height: 14)

            Image(systemName: "chevron.down")
                .scaledFont(size: OmiType.caption, weight: .semibold)
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
            HStack(spacing: OmiSpacing.md) {
                ZStack {
                    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                        .fill(accent.opacity(0.16))
                        .overlay(
                            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                                .stroke(accent.opacity(0.28), lineWidth: 1)
                        )

                    Image(systemName: systemImage)
                        .scaledFont(size: OmiType.subheading, weight: .semibold)
                        .foregroundStyle(accent)
                }
                .frame(width: 38, height: 38)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    Text(value)
                        .scaledFont(size: OmiType.heading, weight: .semibold)
                        .foregroundStyle(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text(title)
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundStyle(OmiColors.textTertiary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: OmiType.caption, weight: .semibold)
                    .foregroundStyle(isHovering ? accent : OmiColors.textQuaternary)
            }
            .padding(OmiSpacing.md)
            .frame(minHeight: 64)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                    .fill(OmiColors.backgroundSecondary.opacity(isHovering ? 0.96 : 0.78))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                    .stroke(isHovering ? accent.opacity(0.34) : OmiColors.border.opacity(0.44), lineWidth: 1)
            )
            .contentShape(.rect(cornerRadius: OmiChrome.chipRadius))
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
            HStack(spacing: OmiSpacing.sm) {
                if let brand {
                    ConnectorBrandIcon(brand: brand, size: 26, cornerRadius: 7)
                } else if let systemImage {
                    ZStack {
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .fill(OmiColors.backgroundTertiary)
                        Image(systemName: systemImage)
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                            .foregroundStyle(OmiColors.textSecondary)
                    }
                    .frame(width: 26, height: 26)
                }

                Text(title)
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundStyle(OmiColors.textSecondary)
                    .lineLimit(1)

                Image(systemName: "chevron.right")
                    .scaledFont(size: OmiType.micro, weight: .bold)
                    .foregroundStyle(isHovering ? OmiColors.success : OmiColors.textQuaternary)
            }
            .padding(.leading, OmiSpacing.sm)
            .padding(.trailing, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xs)
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
