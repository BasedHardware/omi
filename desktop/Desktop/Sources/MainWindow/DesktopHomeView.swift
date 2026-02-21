import SwiftUI

struct DesktopHomeView: View {
    @StateObject private var appState = AppState()
    @StateObject private var viewModelContainer = ViewModelContainer()
    @ObservedObject private var authState = AuthState.shared
    @State private var selectedIndex: Int = {
        if OMIApp.launchMode == .rewind { return SidebarNavItem.rewind.rawValue }
        let tier = UserDefaults.standard.integer(forKey: "currentTierLevel")
        return SidebarNavItem.dashboard.rawValue
    }()
    @State private var isSidebarCollapsed: Bool = false
    @AppStorage("currentTierLevel") private var currentTierLevel = 0

    // Settings sidebar state
    @State private var selectedSettingsSection: SettingsContentView.SettingsSection = .general
    @State private var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection? = nil
    @State private var highlightedSettingId: String? = nil
    @State private var previousIndexBeforeSettings: Int = 0
    @State private var logoPulse = false

    // File indexing sheet for existing users
    @State private var showFileIndexingSheet = false

    /// Whether we're currently viewing the settings page
    private var isInSettings: Bool {
        selectedIndex == SidebarNavItem.settings.rawValue
    }

    var body: some View {
        Group {
            if authState.isRestoringAuth {
                // State 0: Restoring auth session - show loading
                VStack(spacing: 16) {
                    if let iconURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                       let nsImage = NSImage(contentsOf: iconURL) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 64, height: 64)
                    }
                    ProgressView()
                        .scaleEffect(0.8)
                        .tint(.white.opacity(0.6))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .onAppear {
                    log("DesktopHomeView: Showing auth loading splash")
                }
            } else if !authState.isSignedIn {
                // State 1: Not signed in - show sign in
                SignInView(authState: authState)
                    .onAppear {
                        log("DesktopHomeView: Showing SignInView (not signed in)")
                    }
            } else if !appState.hasCompletedOnboarding {
                // State 2: Signed in but onboarding not complete
                if shouldSkipOnboarding() {
                    Color.clear.onAppear {
                        log("DesktopHomeView: --skip-onboarding flag detected, skipping onboarding")
                        appState.hasCompletedOnboarding = true
                    }
                } else {
                    OnboardingView(appState: appState, chatProvider: viewModelContainer.chatProvider, onComplete: nil)
                        .onAppear {
                            log("DesktopHomeView: Showing OnboardingView (signed in, not onboarded)")
                        }
                }
            } else {
                // State 3: Signed in and onboarded - show main content
                ZStack {
                    mainContent
                        .opacity(viewModelContainer.isInitialLoadComplete ? 1 : 0)
                        .onAppear {
                            log("DesktopHomeView: Showing mainContent (signed in and onboarded)")
                            // Check all permissions on launch
                            appState.checkAllPermissions()

                            // Show file indexing sheet for existing users who haven't done it
                            if !UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing") {
                                showFileIndexingSheet = true
                            }

                            let settings = AssistantSettings.shared

                            // Auto-start transcription if enabled in settings
                            if settings.transcriptionEnabled && !appState.isTranscribing {
                                log("DesktopHomeView: Auto-starting transcription")
                                appState.startTranscription()
                            } else if !settings.transcriptionEnabled {
                                log("DesktopHomeView: Transcription disabled in settings, skipping auto-start")
                            }

                            // Start proactive assistants monitoring if enabled in settings
                            if settings.screenAnalysisEnabled {
                                ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
                                    if success {
                                        log("DesktopHomeView: Screen analysis started")
                                    } else {
                                        log("DesktopHomeView: Screen analysis failed to start: \(error ?? "unknown")")
                                        // Revert persistent setting so UI reflects actual state
                                        DispatchQueue.main.async {
                                            AssistantSettings.shared.screenAnalysisEnabled = false
                                            UserDefaults.standard.set(false, forKey: "screenAnalysisEnabled")
                                        }
                                    }
                                }
                            } else {
                                log("DesktopHomeView: Screen analysis disabled in settings, skipping auto-start")
                            }

                            // Start Crisp chat in background for notifications
                            CrispManager.shared.start()

                            // Set up floating control bar (only show if user hasn't disabled it)
                            FloatingControlBarManager.shared.setup(appState: appState, chatProvider: viewModelContainer.chatProvider)
                            if FloatingControlBarManager.shared.isEnabled {
                                FloatingControlBarManager.shared.show()
                            }

                            // Set up push-to-talk voice input
                            if let barState = FloatingControlBarManager.shared.barState {
                                PushToTalkManager.shared.setup(barState: barState)
                            }
                        }
                        .task {
                            // Trigger eager data loading when main content appears
                            // Load conversations/folders in parallel with other data
                            async let vmLoad: Void = viewModelContainer.loadAllData()
                            async let conversations: Void = appState.loadConversations()
                            async let folders: Void = appState.loadFolders()
                            _ = await (vmLoad, conversations, folders)

                            // Backend-based check: ensure user has a cloud agent VM
                            await AgentVMService.shared.ensureProvisioned()
                        }
                        // Refresh conversations when app becomes active (e.g. switching back from another app)
                        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
                            Task { await appState.refreshConversations() }
                        }
                        // Periodic refresh every 30s to pick up conversations from other devices (e.g. Omi Glass)
                        .onReceive(Timer.publish(every: 30, on: .main, in: .common).autoconnect()) { _ in
                            Task { await appState.refreshConversations() }
                        }
                        // On sign-out: reset @AppStorage-backed onboarding flag and stop transcription.
                        // hasCompletedOnboarding must be set here (in a View) because @AppStorage
                        // on ObservableObject caches internally and ignores UserDefaults.removeObject().
                        // Stopping transcription here prevents FOREIGN KEY errors from an old
                        // transcription session writing to a new user's database.
                        .onReceive(NotificationCenter.default.publisher(for: .userDidSignOut)) { _ in
                            log("DesktopHomeView: userDidSignOut — resetting hasCompletedOnboarding and stopping transcription")
                            appState.hasCompletedOnboarding = false
                            appState.stopTranscription()
                        }
                        // Periodic file re-scan (every 3 hours)
                        .task {
                            while !Task.isCancelled {
                                try? await Task.sleep(for: .seconds(3 * 60 * 60))
                                guard !Task.isCancelled else { break }
                                guard UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing") else { continue }
                                log("DesktopHomeView: Triggering background file rescan")
                                await FileIndexerService.shared.backgroundRescan()
                            }
                        }
                        .onReceive(NotificationCenter.default.publisher(for: .triggerFileIndexing)) { _ in
                            showFileIndexingSheet = true
                        }
                        .dismissableSheet(isPresented: $showFileIndexingSheet) {
                            FileIndexingView(
                                chatProvider: viewModelContainer.chatProvider,
                                onComplete: { fileCount in
                                    showFileIndexingSheet = false
                                }
                            )
                            .frame(width: 600, height: 650)
                        }

                    if !viewModelContainer.isInitialLoadComplete {
                        VStack(spacing: 24) {
                            if let iconURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                               let nsImage = NSImage(contentsOf: iconURL) {
                                Image(nsImage: nsImage)
                                    .resizable()
                                    .scaledToFit()
                                    .frame(width: 72, height: 72)
                                    .scaleEffect(logoPulse ? 1.08 : 1.0)
                                    .opacity(logoPulse ? 1.0 : 0.7)
                                    .animation(
                                        .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                                        value: logoPulse
                                    )
                                    .onAppear { logoPulse = true }
                            }

                            Text(viewModelContainer.initStatusMessage)
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textTertiary)

                            ProgressView()
                                .scaleEffect(0.8)
                                .tint(OmiColors.purplePrimary.opacity(0.6))
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(OmiColors.backgroundPrimary)
                        .transition(.opacity.animation(.easeOut(duration: 0.3)))
                    }
                }
            }
        }
        .background(OmiColors.backgroundPrimary)
        .frame(minWidth: 900, minHeight: 600)
        .preferredColorScheme(.dark)
        .tint(OmiColors.purplePrimary)
        .onAppear {
            log("DesktopHomeView: View appeared - isSignedIn=\(authState.isSignedIn), hasCompletedOnboarding=\(appState.hasCompletedOnboarding)")
            // Force dark appearance on the window
            DispatchQueue.main.async {
                for window in NSApp.windows {
                    if window.title == "Omi" {
                        window.appearance = NSAppearance(named: .darkAqua)
                    }
                }
            }
            // Redirect if current page isn't visible at current tier
            redirectIfPageHidden()
        }
        .onChange(of: currentTierLevel) { _, _ in
            redirectIfPageHidden()
        }
    }

    /// Redirect to conversations if current page isn't visible at the current tier level
    private func redirectIfPageHidden() {
        // Tier 0 or tier 6+ shows everything — no redirect needed
        guard currentTierLevel > 0 && currentTierLevel < 6 else { return }
        // Don't redirect from settings/permissions/device/help pages
        let nonMainPages: Set<Int> = [SidebarNavItem.settings.rawValue, SidebarNavItem.permissions.rawValue, SidebarNavItem.device.rawValue, SidebarNavItem.help.rawValue]
        guard !nonMainPages.contains(selectedIndex) else { return }

        var visibleRawValues: Set<Int> = [SidebarNavItem.dashboard.rawValue, SidebarNavItem.rewind.rawValue]
        if currentTierLevel >= 2 { visibleRawValues.insert(SidebarNavItem.memories.rawValue) }
        if currentTierLevel >= 3 { visibleRawValues.insert(SidebarNavItem.tasks.rawValue) }
        if currentTierLevel >= 4 { visibleRawValues.insert(SidebarNavItem.chat.rawValue) }

        if !visibleRawValues.contains(selectedIndex) {
            selectedIndex = SidebarNavItem.dashboard.rawValue
        }
    }

    /// Whether to hide the sidebar (rewind mode)
    private var hideSidebar: Bool {
        OMIApp.launchMode == .rewind
    }

    /// Update store auto-refresh based on which page is visible
    private func updateStoreActivity(for index: Int) {
        viewModelContainer.tasksStore.isActive =
            index == SidebarNavItem.dashboard.rawValue || index == SidebarNavItem.tasks.rawValue
        viewModelContainer.memoriesViewModel.isActive =
            index == SidebarNavItem.memories.rawValue
    }

    private var mainContent: some View {
        HStack(spacing: 0) {
            // Sidebar slot: settings sidebar overlays main sidebar
            // IMPORTANT: SidebarView is kept alive (but hidden) when in settings to prevent
            // EXC_BAD_ACCESS crash in SwiftUI's tooltip system. When the view is conditionally
            // removed, its .help() tooltip graph nodes get invalidated, but the macOS tooltip
            // tracking system still tries to evaluate them during window key state changes.
            ZStack {
                if !hideSidebar {
                    SidebarView(
                        selectedIndex: $selectedIndex,
                        isCollapsed: $isSidebarCollapsed,
                        appState: appState
                    )
                    .clickThrough()
                    .opacity(isInSettings ? 0 : 1)
                    .allowsHitTesting(!isInSettings)
                }

                if isInSettings {
                    SettingsSidebar(
                        selectedSection: $selectedSettingsSection,
                        selectedAdvancedSubsection: $selectedAdvancedSubsection,
                        highlightedSettingId: $highlightedSettingId,
                        onBack: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                selectedIndex = previousIndexBeforeSettings
                            }
                        }
                    )
                }
            }
            .fixedSize(horizontal: true, vertical: false)

            // Main content area with rounded container
            ZStack {
                // Content container background
                RoundedRectangle(cornerRadius: 16)
                    .fill(OmiColors.backgroundSecondary.opacity(0.4))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(OmiColors.backgroundTertiary.opacity(0.3), lineWidth: 1)
                    )
                    .shadow(color: .black.opacity(0.05), radius: 20, x: 0, y: 4)

                // Page content - switch recreates views on tab change
                // Extracted into a separate struct so that pages like TasksPage
                // are not re-rendered when AppState publishes unrelated changes.
                PageContentView(
                    selectedIndex: selectedIndex,
                    appState: appState,
                    viewModelContainer: viewModelContainer,
                    selectedSettingsSection: $selectedSettingsSection,
                    selectedAdvancedSubsection: $selectedAdvancedSubsection,
                    highlightedSettingId: $highlightedSettingId,
                    selectedTabIndex: $selectedIndex
                )
                .id(selectedIndex)
                .transition(.opacity.combined(with: .move(edge: .trailing)))
                .animation(.easeInOut(duration: 0.2), value: selectedIndex)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            }
            .padding(12)
        }
        .overlay {
            // Goal completion celebration overlay
            GoalCelebrationView()
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToRewindSettings)) { _ in
            // Set the section directly and navigate to settings
            selectedSettingsSection = .rewind
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.settings.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToDeviceSettings)) { _ in
            // Set the section directly and navigate to settings
            selectedSettingsSection = .device
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.settings.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToTaskSettings)) { _ in
            // Navigate to settings > advanced > task assistant subsection
            selectedSettingsSection = .advanced
            selectedAdvancedSubsection = .taskAssistant
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.settings.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToFloatingBarSettings)) { _ in
            selectedSettingsSection = .advanced
            selectedAdvancedSubsection = .askOmiFloatingBar
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.settings.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToAIChatSettings)) { _ in
            selectedSettingsSection = .aiChat
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.settings.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToRewind)) { _ in
            // Navigate to Rewind page (index 6) - triggered by global hotkey Cmd+Option+R
            log("DesktopHomeView: Received navigateToRewind notification, navigating to Rewind (index \(SidebarNavItem.rewind.rawValue))")
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.rewind.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToChat)) { _ in
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.chat.rawValue
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToTasks)) { _ in
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedIndex = SidebarNavItem.tasks.rawValue
            }
        }
        .onChange(of: selectedIndex) { oldValue, newValue in
            // Track the previous index when navigating to settings
            if newValue == SidebarNavItem.settings.rawValue && oldValue != SidebarNavItem.settings.rawValue {
                previousIndexBeforeSettings = oldValue
            }
            // Only auto-refresh stores when their pages are visible
            updateStoreActivity(for: newValue)
        }
        .onAppear {
            updateStoreActivity(for: selectedIndex)
        }
    }
}

/// Isolated page content switch — does NOT observe AppState or ViewModelContainer
/// as @ObservedObject, so pages like TasksPage won't re-render when unrelated
/// AppState properties (conversations, permissions, etc.) change.
private struct PageContentView: View {
    let selectedIndex: Int
    let appState: AppState
    let viewModelContainer: ViewModelContainer
    @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
    @Binding var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection?
    @Binding var highlightedSettingId: String?
    @Binding var selectedTabIndex: Int

    var body: some View {
        let _ = log("RENDER: PageContentView body evaluated (index=\(selectedIndex))")
        Group {
            switch selectedIndex {
            case 0:
                DashboardPage(viewModel: viewModelContainer.dashboardViewModel, appState: appState, selectedIndex: $selectedTabIndex)
            case 1:
                DashboardPage(viewModel: viewModelContainer.dashboardViewModel, appState: appState, selectedIndex: $selectedTabIndex)
            case 2:
                ChatPage(appProvider: viewModelContainer.appProvider, chatProvider: viewModelContainer.chatProvider)
            case 3:
                MemoriesPage(viewModel: viewModelContainer.memoriesViewModel)
            case 4:
                TasksPage(viewModel: viewModelContainer.tasksViewModel, chatProvider: viewModelContainer.chatProvider)
            case 5:
                FocusPage()
            case 6:
                AdvicePage()
            case 7:
                RewindPage(appState: appState)
            case 8:
                AppsPage(appProvider: viewModelContainer.appProvider)
            case 9:
                SettingsPage(
                    appState: appState,
                    selectedSection: $selectedSettingsSection,
                    selectedAdvancedSubsection: $selectedAdvancedSubsection,
                    highlightedSettingId: $highlightedSettingId,
                    chatProvider: viewModelContainer.chatProvider
                )
            case 10:
                PermissionsPage(appState: appState)
            case 11:
                DeviceSettingsPage()
            case 12:
                HelpPage()
            default:
                DashboardPage(viewModel: viewModelContainer.dashboardViewModel, appState: appState, selectedIndex: $selectedTabIndex)
            }
        }
    }
}

#Preview {
    DesktopHomeView()
}
