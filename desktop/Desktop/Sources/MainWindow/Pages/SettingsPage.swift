import SwiftUI
import Sparkle
import UniformTypeIdentifiers

/// Settings page that wraps SettingsView with proper dark theme styling for the main window
struct SettingsPage: View {
    @ObservedObject var appState: AppState
    @Binding var selectedSection: SettingsContentView.SettingsSection
    @Binding var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection?
    @Binding var highlightedSettingId: String?
    var chatProvider: ChatProvider? = nil

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 0) {
                    // Section header
                    HStack {
                        Text(selectedSection == .advanced && selectedAdvancedSubsection != nil
                             ? selectedAdvancedSubsection!.rawValue
                             : selectedSection.rawValue)
                            .scaledFont(size: 28, weight: .bold)
                            .foregroundColor(OmiColors.textPrimary)
                            .id(selectedSection)
                            .transition(.opacity)
                            .animation(.easeInOut(duration: 0.15), value: selectedSection)

                        Spacer()
                    }
                    .padding(.horizontal, 32)
                    .padding(.top, 32)
                    .padding(.bottom, 24)

                    // Settings content - embedded SettingsView with dark theme override
                    SettingsContentView(
                        appState: appState,
                        selectedSection: $selectedSection,
                        selectedAdvancedSubsection: $selectedAdvancedSubsection,
                        highlightedSettingId: $highlightedSettingId,
                        chatProvider: chatProvider
                    )
                    .padding(.horizontal, 32)

                    Spacer()
                }
            }
            .onChange(of: highlightedSettingId) { _, newId in
                guard let newId = newId else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    withAnimation(.easeInOut(duration: 0.3)) {
                        proxy.scrollTo(newId, anchor: .center)
                    }
                }
            }
        }
        .background(OmiColors.backgroundSecondary.opacity(0.3))
        .onAppear {
            AnalyticsManager.shared.settingsPageOpened()
        }
        .onChange(of: selectedSection) { _, newValue in
            if newValue == .advanced && selectedAdvancedSubsection == nil {
                selectedAdvancedSubsection = .aiUserProfile
            }
        }
    }
}

/// Dark-themed settings content matching the main window style
struct SettingsContentView: View {
    // AppState for transcription control
    @ObservedObject var appState: AppState

    // ChatProvider for browser extension setup
    var chatProvider: ChatProvider? = nil

    // Updater view model
    @ObservedObject private var updaterViewModel = UpdaterViewModel.shared

    // Master monitoring state (screen analysis)
    @State private var isMonitoring: Bool
    @State private var isToggling: Bool = false
    @State private var permissionError: String?

    // Ask Omi floating bar state
    @State private var showAskOmiBar: Bool = false

    // Transcription state
    @State private var isTranscribing: Bool
    @State private var isTogglingTranscription: Bool = false
    @State private var transcriptionError: String?

    // Log export state

    // Focus Assistant states
    @State private var focusEnabled: Bool
    @State private var cooldownInterval: Int
    @State private var glowOverlayEnabled: Bool
    @State private var analysisDelay: Int
    @State private var focusNotificationsEnabled: Bool
    @State private var focusExcludedApps: Set<String>

    // Task Assistant states
    @State private var taskEnabled: Bool
    @State private var taskExtractionInterval: Double
    @State private var taskMinConfidence: Double
    @State private var taskNotificationsEnabled: Bool
    @State private var taskAllowedApps: Set<String>
    @State private var taskBrowserKeywords: [String]
    @State private var isRescoringTasks = false

    // Advice Assistant states
    @State private var adviceEnabled: Bool
    @State private var adviceExtractionInterval: Double
    @State private var adviceMinConfidence: Double
    @State private var adviceNotificationsEnabled: Bool
    @State private var adviceExcludedApps: Set<String>

    // Memory Assistant states
    @State private var memoryEnabled: Bool
    @State private var memoryExtractionInterval: Double
    @State private var memoryMinConfidence: Double
    @State private var memoryNotificationsEnabled: Bool
    @State private var memoryExcludedApps: Set<String>

    // Goals states
    @State private var goalsAutoGenerateEnabled: Bool = GoalGenerationService.shared.isAutoGenerationEnabled

    // Glow preview state
    @State private var isPreviewRunning: Bool = false

    // Tier gating (0 = show all, 1-6 = sequential tiers)
    @AppStorage("currentTierLevel") private var currentTierLevel = 0

    // Advanced stats
    @State private var advancedStats: UserStats?
    @State private var isLoadingStats = false
    @State private var chatMessageCount: Int?
    @State private var isLoadingChatMessages = false

    // AI User Profile
    @State private var aiProfileId: Int64?
    @State private var aiProfileText: String?
    @State private var aiProfileGeneratedAt: Date?
    @State private var aiProfileDataSourcesUsed: Int = 0
    @State private var isGeneratingAIProfile = false
    @State private var isEditingAIProfile = false
    @State private var aiProfileEditText: String = ""

    // Selected section (passed in from parent)
    @Binding var selectedSection: SettingsSection
    @Binding var selectedAdvancedSubsection: AdvancedSubsection?
    @Binding var highlightedSettingId: String?

    // Notification settings (from backend)
    @State private var dailySummaryEnabled: Bool = true
    @State private var dailySummaryHour: Int = 22
    @State private var notificationsEnabled: Bool = true
    @State private var notificationFrequency: Int = 3

    // Privacy settings (from backend)
    @State private var recordingPermissionEnabled: Bool = false
    @State private var privateCloudSyncEnabled: Bool = true
    @State private var isTrackingExpanded: Bool = false

    // Transcription settings (from backend)
    @State private var singleLanguageMode: Bool = false
    @State private var newVocabularyWord: String = ""
    @State private var vocabularyList: [String] = []

    // Language setting
    @State private var userLanguage: String = "en"

    // Loading states
    @State private var isLoadingSettings: Bool = false

    private let cooldownOptions = [1, 2, 5, 10, 15, 30, 60]
    private let analysisDelayOptions = [0, 10, 20, 30, 60, 300] // seconds: instant, 10s, 20s, 30s, 1 min, 5 min
    private let extractionIntervalOptions: [Double] = [10.0, 600.0, 3600.0] // 10s, 10min, 1hr
    private let hourOptions = Array(0...23)
    private let frequencyOptions = [
        (0, "Off"),
        (1, "Minimal"),
        (2, "Low"),
        (3, "Balanced"),
        (4, "High"),
        (5, "Maximum")
    ]
    // Use the full language list from AssistantSettings
    private var languageOptions: [(String, String)] {
        AssistantSettings.supportedLanguages.map { ($0.code, $0.name) }
    }

    // Language auto-detect state (from local settings)
    @State private var transcriptionAutoDetect: Bool = true
    @State private var transcriptionLanguage: String = "en"

    // Multi-chat mode setting
    @AppStorage("multiChatEnabled") private var multiChatEnabled = false
    @AppStorage("conversationsCompactView") private var conversationsCompactView = true

    // AI Chat settings
    @AppStorage("chatBridgeMode") private var chatBridgeMode: String = "agentSDK"
    @AppStorage("askModeEnabled") private var askModeEnabled = false
    @AppStorage("claudeMdEnabled") private var claudeMdEnabled = true
    @AppStorage("projectClaudeMdEnabled") private var projectClaudeMdEnabled = true
    @AppStorage("aiChatWorkingDirectory") private var aiChatWorkingDirectory: String = ""
    @State private var aiChatClaudeMdContent: String?
    @State private var aiChatClaudeMdPath: String?
    @State private var aiChatProjectClaudeMdContent: String?
    @State private var aiChatProjectClaudeMdPath: String?
    @State private var aiChatDiscoveredSkills: [(name: String, description: String, path: String)] = []
    @State private var aiChatProjectDiscoveredSkills: [(name: String, description: String, path: String)] = []
    @State private var aiChatDisabledSkills: Set<String> = []
    @State private var showFileViewer = false
    @State private var fileViewerContent = ""
    @State private var fileViewerTitle = ""
    @State private var skillSearchQuery = ""

    // Dev Mode setting
    @AppStorage("devModeEnabled") private var devModeEnabled = false

    // Browser Extension settings
    @AppStorage("playwrightUseExtension") private var playwrightUseExtension = true
    @State private var playwrightExtensionToken: String = ""
    @State private var showBrowserSetup = false

    // Launch at login manager
    @ObservedObject private var launchAtLoginManager = LaunchAtLoginManager.shared

    enum SettingsSection: String, CaseIterable {
        case general = "General"
        case device = "Device"
        case focus = "Focus"
        case rewind = "Rewind"
        case transcription = "Transcription"
        case notifications = "Notifications"
        case privacy = "Privacy"
        case account = "Account"
        case aiChat = "AI Chat"
        case advanced = "Advanced"
        case about = "About"
    }

    enum AdvancedSubsection: String, CaseIterable {
        case aiUserProfile = "AI User Profile"
        case stats = "Your Stats"
        case featureTiers = "Feature Tiers"
        case focusAssistant = "Focus Assistant"
        case taskAssistant = "Task Assistant"
        case adviceAssistant = "Advice Assistant"
        case memoryAssistant = "Memory Assistant"
        case analysisThrottle = "Analysis Throttle"
        case goals = "Goals"
        case askOmiFloatingBar = "Ask Omi Floating Bar"
        case preferences = "Preferences"
        case troubleshooting = "Troubleshooting"

        var icon: String {
            switch self {
            case .aiUserProfile: return "brain"
            case .stats: return "chart.bar"
            case .featureTiers: return "lock.shield"
            case .focusAssistant: return "eye.fill"
            case .taskAssistant: return "checklist"
            case .adviceAssistant: return "lightbulb.fill"
            case .memoryAssistant: return "brain.head.profile"
            case .analysisThrottle: return "clock.arrow.2.circlepath"
            case .goals: return "target"
            case .askOmiFloatingBar: return "sparkles"
            case .preferences: return "slider.horizontal.3"
            case .troubleshooting: return "wrench.and.screwdriver"
            }
        }
    }

    @State private var showResetOnboardingAlert: Bool = false
    @State private var showRescanFilesAlert: Bool = false

    init(
        appState: AppState,
        selectedSection: Binding<SettingsSection>,
        selectedAdvancedSubsection: Binding<AdvancedSubsection?>,
        highlightedSettingId: Binding<String?> = .constant(nil),
        chatProvider: ChatProvider? = nil
    ) {
        self.appState = appState
        self._selectedSection = selectedSection
        self._selectedAdvancedSubsection = selectedAdvancedSubsection
        self._highlightedSettingId = highlightedSettingId
        self.chatProvider = chatProvider
        let settings = AssistantSettings.shared
        _isMonitoring = State(initialValue: ProactiveAssistantsPlugin.shared.isMonitoring)
        _isTranscribing = State(initialValue: appState.isTranscribing)
        _focusEnabled = State(initialValue: FocusAssistantSettings.shared.isEnabled)
        _cooldownInterval = State(initialValue: FocusAssistantSettings.shared.cooldownInterval)
        _glowOverlayEnabled = State(initialValue: settings.glowOverlayEnabled)
        _analysisDelay = State(initialValue: settings.analysisDelay)
        _focusNotificationsEnabled = State(initialValue: FocusAssistantSettings.shared.notificationsEnabled)
        _focusExcludedApps = State(initialValue: FocusAssistantSettings.shared.excludedApps)
        _taskEnabled = State(initialValue: TaskAssistantSettings.shared.isEnabled)
        _taskExtractionInterval = State(initialValue: TaskAssistantSettings.shared.extractionInterval)
        _taskMinConfidence = State(initialValue: TaskAssistantSettings.shared.minConfidence)
        _taskNotificationsEnabled = State(initialValue: TaskAssistantSettings.shared.notificationsEnabled)
        _taskAllowedApps = State(initialValue: TaskAssistantSettings.shared.allowedApps)
        _taskBrowserKeywords = State(initialValue: TaskAssistantSettings.shared.browserKeywords)
        _adviceEnabled = State(initialValue: AdviceAssistantSettings.shared.isEnabled)
        _adviceExtractionInterval = State(initialValue: AdviceAssistantSettings.shared.extractionInterval)
        _adviceMinConfidence = State(initialValue: AdviceAssistantSettings.shared.minConfidence)
        _adviceNotificationsEnabled = State(initialValue: AdviceAssistantSettings.shared.notificationsEnabled)
        _adviceExcludedApps = State(initialValue: AdviceAssistantSettings.shared.excludedApps)
        _memoryEnabled = State(initialValue: MemoryAssistantSettings.shared.isEnabled)
        _memoryExtractionInterval = State(initialValue: MemoryAssistantSettings.shared.extractionInterval)
        _memoryMinConfidence = State(initialValue: MemoryAssistantSettings.shared.minConfidence)
        _memoryNotificationsEnabled = State(initialValue: MemoryAssistantSettings.shared.notificationsEnabled)
        _memoryExcludedApps = State(initialValue: MemoryAssistantSettings.shared.excludedApps)
    }

    /// Computed status text for notifications
    private var notificationStatusText: String {
        if !appState.hasNotificationPermission {
            return "Notifications are disabled"
        } else if appState.isNotificationBannerDisabled {
            return "Enabled but banners are off"
        } else {
            return "Proactive alerts enabled"
        }
    }

    var body: some View {
        VStack(spacing: 24) {
            // Section content
            Group {
                switch selectedSection {
                case .general:
                    generalSection
                case .device:
                    DeviceSettingsPage()
                case .focus:
                    FocusPage()
                case .rewind:
                    rewindSection
                case .transcription:
                    transcriptionSection
                case .notifications:
                    notificationsSection
                case .privacy:
                    privacySection
                case .account:
                    accountSection
                case .aiChat:
                    aiChatSection
                case .advanced:
                    advancedSection
                case .about:
                    aboutSection
                }
            }
            .id(selectedSection)
            .transition(.opacity)
            .animation(.easeInOut(duration: 0.15), value: selectedSection)
        }
        .onAppear {
            loadBackendSettings()
            // Sync transcription state with appState
            isTranscribing = appState.isTranscribing
            // Sync floating bar state
            showAskOmiBar = FloatingControlBarManager.shared.isVisible
            // Refresh notification permission state
            appState.checkNotificationPermission()
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { notification in
            if let userInfo = notification.userInfo, let state = userInfo["isMonitoring"] as? Bool {
                isMonitoring = state
            }
        }
        .onChange(of: appState.isTranscribing) { _, newValue in
            isTranscribing = newValue
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToTaskSettings)) { _ in
            selectedSection = .advanced
            selectedAdvancedSubsection = .taskAssistant
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToFloatingBarSettings)) { _ in
            selectedSection = .advanced
            selectedAdvancedSubsection = .askOmiFloatingBar
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Refresh notification permission when app becomes active (user may have changed it in System Settings)
            appState.checkNotificationPermission()
        }
    }

    // MARK: - General Section

    private var generalSection: some View {
        VStack(spacing: 20) {
            // Rewind toggle (controls both screen + audio)
            settingsCard(settingId: "general.rewind") {
                HStack(spacing: 16) {
                    Circle()
                        .fill((isMonitoring || isTranscribing) ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
                        .frame(width: 12, height: 12)
                        .shadow(color: (isMonitoring || isTranscribing) ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Rewind")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(permissionError ?? transcriptionError ?? ((isMonitoring || isTranscribing) ? "Screen capture and audio are active" : "Screen capture and audio are paused"))
                            .scaledFont(size: 13)
                            .foregroundColor((permissionError ?? transcriptionError) != nil ? OmiColors.warning : OmiColors.textTertiary)
                    }

                    Spacer()

                    if isToggling || isTogglingTranscription {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Toggle("", isOn: Binding(
                            get: { isMonitoring || isTranscribing },
                            set: { newValue in
                                isMonitoring = newValue
                                isTranscribing = newValue
                                toggleMonitoring(enabled: newValue)
                                toggleTranscription(enabled: newValue)
                            }
                        ))
                            .toggleStyle(.switch)
                            .labelsHidden()
                    }
                }
            }

            // Notifications toggle
            settingsCard(settingId: "general.notifications") {
                VStack(spacing: 12) {
                    HStack(spacing: 16) {
                        Circle()
                            .fill(appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                                  ? OmiColors.success
                                  : (appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.textTertiary.opacity(0.3)))
                            .frame(width: 12, height: 12)
                            .shadow(color: appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                                    ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Notifications")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text(notificationStatusText)
                                .scaledFont(size: 13)
                                .foregroundColor(appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.textTertiary)
                        }

                        Spacer()

                        if appState.hasNotificationPermission && !appState.isNotificationBannerDisabled {
                            // Show enabled badge
                            Text("Enabled")
                                .scaledFont(size: 12, weight: .medium)
                                .foregroundColor(.green)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(
                                    Capsule()
                                        .fill(Color.green.opacity(0.15))
                                )
                        } else {
                            // Show button to enable or fix
                            Button(action: {
                                if appState.isNotificationBannerDisabled {
                                    // Banners off — user needs to change style in System Settings
                                    appState.openNotificationPreferences()
                                } else {
                                    // Auth not granted — try lsregister repair first
                                    AnalyticsManager.shared.notificationRepairTriggered(
                                        reason: "settings_fix_button",
                                        previousStatus: "not_authorized",
                                        currentStatus: "not_authorized"
                                    )
                                    appState.repairNotificationAndFallback()
                                }
                            }) {
                                Text(appState.isNotificationBannerDisabled ? "Fix" : "Enable")
                                    .scaledFont(size: 12, weight: .semibold)
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.purplePrimary)
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    // Warning when banners are disabled
                    if appState.isNotificationBannerDisabled {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.warning)

                            Text("Banners disabled - you won't see visual alerts. Set style to \"Banners\" in System Settings.")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.warning)

                            Spacer()
                        }
                        .padding(10)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.warning.opacity(0.1))
                        )
                    }
                }
            }

            // Ask Omi floating bar toggle
            settingsCard(settingId: "general.askomi") {
                HStack(spacing: 16) {
                    Circle()
                        .fill(showAskOmiBar ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
                        .frame(width: 12, height: 12)
                        .shadow(color: showAskOmiBar ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Ask Omi")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(showAskOmiBar ? "Floating bar is visible (⌘\\)" : "Floating bar is hidden (⌘\\)")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Toggle("", isOn: $showAskOmiBar)
                        .toggleStyle(.switch)
                        .labelsHidden()
                        .onChange(of: showAskOmiBar) { _, newValue in
                            if newValue {
                                FloatingControlBarManager.shared.show()
                            } else {
                                FloatingControlBarManager.shared.hide()
                            }
                        }
                }
            }

            // Font Size
            settingsCard(settingId: "general.fontsize") {
                VStack(spacing: 12) {
                    HStack(spacing: 16) {
                        Image(systemName: "textformat.size")
                            .scaledFont(size: 16, weight: .medium)
                            .foregroundColor(OmiColors.purplePrimary)
                            .frame(width: 12)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Font Size")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Scale: \(Int(fontScaleSettings.scale * 100))%")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        if fontScaleSettings.scale != 1.0 {
                            Button("Reset") {
                                fontScaleSettings.resetToDefault()
                            }
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.purplePrimary)
                            .buttonStyle(.plain)
                        }
                    }

                    HStack(spacing: 12) {
                        Text("A")
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)

                        Slider(value: $fontScaleSettings.scale, in: 0.5...2.0, step: 0.05)
                            .tint(OmiColors.purplePrimary)

                        Text("A")
                            .scaledFont(size: 18, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Text("The quick brown fox jumps over the lazy dog")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 4)

                    // Keyboard shortcuts for font size
                    VStack(spacing: 6) {
                        fontShortcutRow(label: "Increase font size", keys: "\u{2318}+")
                        fontShortcutRow(label: "Decrease font size", keys: "\u{2318}\u{2212}")
                        fontShortcutRow(label: "Reset font size", keys: "\u{2318}0")
                    }
                    .padding(.top, 4)

                    HStack {
                        Spacer()
                        Button(action: {
                            resetWindowToDefaultSize()
                        }) {
                            HStack(spacing: 6) {
                                Image(systemName: "arrow.uturn.backward")
                                    .scaledFont(size: 11)
                                Text("Reset Window Size")
                                    .scaledFont(size: 12, weight: .medium)
                            }
                            .foregroundColor(OmiColors.textSecondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(OmiColors.backgroundTertiary)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

        }
    }

    // MARK: - Rewind Section

    @ObservedObject private var fontScaleSettings = FontScaleSettings.shared
    @ObservedObject private var rewindSettings = RewindSettings.shared

    @State private var rewindStats: (total: Int, indexed: Int, storageSize: Int64)? = nil

    private var rewindSection: some View {
        VStack(spacing: 20) {
            // Storage Stats
            settingsCard(settingId: "rewind.storage") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "internaldrive.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Storage")
                                .scaledFont(size: 15, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            if let stats = rewindStats {
                                Text("\(stats.total) frames • \(RewindStorage.formatBytes(stats.storageSize))")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textTertiary)
                            } else {
                                Text("Loading...")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }

                        Spacer()
                    }
                }
            }
            .task {
                rewindStats = await RewindIndexer.shared.getStats()
            }

            // Excluded Apps
            settingsCard(settingId: "rewind.excludedapps") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "eye.slash.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Excluded Apps")
                                .scaledFont(size: 15, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Screen capture is paused when these apps are active")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        Button("Reset to Defaults") {
                            rewindSettings.resetToDefaults()
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // List of excluded apps
                    if rewindSettings.excludedApps.isEmpty {
                        HStack {
                            Spacer()
                            VStack(spacing: 8) {
                                Image(systemName: "checkmark.shield")
                                    .scaledFont(size: 24)
                                    .foregroundColor(OmiColors.textTertiary)
                                Text("No apps excluded")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            .padding(.vertical, 16)
                            Spacer()
                        }
                    } else {
                        LazyVStack(spacing: 8) {
                            ForEach(Array(rewindSettings.excludedApps).sorted(), id: \.self) { appName in
                                ExcludedAppRow(
                                    appName: appName,
                                    onRemove: {
                                        rewindSettings.includeApp(appName)
                                    }
                                )
                            }
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Add app section
                    AddExcludedAppView(
                        onAdd: { appName in
                            rewindSettings.excludeApp(appName)
                        },
                        excludedApps: rewindSettings.excludedApps
                    )
                }
            }

            // Battery Settings
            settingsCard(settingId: "rewind.battery") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "battery.75percent")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Battery Optimization")
                                .scaledFont(size: 15, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Pause text recognition on battery to save energy. OCR runs automatically when plugged back in.")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        Toggle("", isOn: $rewindSettings.pauseOCROnBattery)
                            .toggleStyle(.switch)
                            .labelsHidden()
                    }
                }
            }

            // Retention Settings
            settingsCard(settingId: "rewind.retention") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "clock.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Data Retention")
                                .scaledFont(size: 15, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("How long to keep screen recordings")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        Picker("", selection: $rewindSettings.retentionDays) {
                            Text("3 days").tag(3)
                            Text("7 days").tag(7)
                            Text("14 days").tag(14)
                            Text("30 days").tag(30)
                        }
                        .pickerStyle(.menu)
                        .frame(width: 110)
                    }
                }
            }
        }
    }

    // MARK: - Transcription Section

    private var transcriptionSection: some View {
        VStack(spacing: 20) {
            // Language Mode
            settingsCard(settingId: "transcription.languagemode") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "globe")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Language Mode")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()
                    }

                    // Auto-Detect option
                    Button(action: {
                        transcriptionAutoDetect = true
                        AssistantSettings.shared.transcriptionAutoDetect = true
                        updateTranscriptionPreferences(singleLanguageMode: false)
                        restartTranscriptionIfNeeded()
                    }) {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: transcriptionAutoDetect ? "checkmark.circle.fill" : "circle")
                                .scaledFont(size: 20)
                                .foregroundColor(transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

                            VStack(alignment: .leading, spacing: 6) {
                                Text("Auto-Detect (Multi-Language)")
                                    .scaledFont(size: 14, weight: .medium)
                                    .foregroundColor(OmiColors.textPrimary)

                                Text("Automatically detects and transcribes:")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)

                                // List of supported languages
                                Text("English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }

                            Spacer()
                        }
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.1) : Color.clear)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary, lineWidth: 1)
                                )
                        )
                    }
                    .buttonStyle(.plain)

                    // Single Language option
                    Button(action: {
                        transcriptionAutoDetect = false
                        AssistantSettings.shared.transcriptionAutoDetect = false
                        updateTranscriptionPreferences(singleLanguageMode: true)
                        restartTranscriptionIfNeeded()
                    }) {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: !transcriptionAutoDetect ? "checkmark.circle.fill" : "circle")
                                .scaledFont(size: 20)
                                .foregroundColor(!transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

                            VStack(alignment: .leading, spacing: 6) {
                                Text("Single Language (Better Accuracy)")
                                    .scaledFont(size: 14, weight: .medium)
                                    .foregroundColor(OmiColors.textPrimary)

                                Text("Best for speaking in one specific language")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)

                                // Language picker (only shown when single language is selected)
                                if !transcriptionAutoDetect {
                                    HStack {
                                        Text("Language:")
                                            .scaledFont(size: 12)
                                            .foregroundColor(OmiColors.textTertiary)

                                        Picker("", selection: $transcriptionLanguage) {
                                            ForEach(languageOptions, id: \.0) { option in
                                                Text(option.1).tag(option.0)
                                            }
                                        }
                                        .pickerStyle(.menu)
                                        .frame(width: 180)
                                        .onChange(of: transcriptionLanguage) { _, newValue in
                                            AssistantSettings.shared.transcriptionLanguage = newValue
                                            updateLanguage(newValue)
                                            restartTranscriptionIfNeeded()
                                        }
                                    }
                                    .padding(.top, 4)
                                }
                            }

                            Spacer()
                        }
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(!transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.1) : Color.clear)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(!transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary, lineWidth: 1)
                                )
                        )
                    }
                    .buttonStyle(.plain)

                    // Info about language support
                    HStack(spacing: 8) {
                        Image(systemName: "info.circle")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Single language mode supports 42 languages including Ukrainian, Russian, and more.")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }

            // Custom Vocabulary
            settingsCard(settingId: "transcription.vocabulary") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "text.book.closed")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Custom Vocabulary")
                                .scaledFont(size: 15, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Improve recognition of names, brands, and technical terms")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        if !vocabularyList.isEmpty {
                            Text("\(vocabularyList.count) terms")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }

                    // Current vocabulary display with removable tags
                    if !vocabularyList.isEmpty {
                        FlowLayout(spacing: 6) {
                            ForEach(vocabularyList, id: \.self) { term in
                                HStack(spacing: 4) {
                                    Text(term)
                                        .scaledFont(size: 12)
                                        .foregroundColor(OmiColors.textSecondary)

                                    Button(action: {
                                        removeVocabularyWord(term)
                                    }) {
                                        Image(systemName: "xmark")
                                            .scaledFont(size: 9, weight: .medium)
                                            .foregroundColor(OmiColors.textTertiary)
                                    }
                                    .buttonStyle(.plain)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(OmiColors.backgroundQuaternary)
                                )
                            }
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Add new word input
                    HStack(spacing: 8) {
                        TextField("Add a word...", text: $newVocabularyWord)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit {
                                addVocabularyWord()
                            }

                        Button(action: {
                            addVocabularyWord()
                        }) {
                            Image(systemName: "plus.circle.fill")
                                .scaledFont(size: 20)
                                .foregroundColor(newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty ? OmiColors.textTertiary : OmiColors.purplePrimary)
                        }
                        .buttonStyle(.plain)
                        .disabled(newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty)
                    }

                    Text("Press Enter or click + to add • Click × to remove")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }
        }
    }

    /// Add a word to the vocabulary
    private func addVocabularyWord() {
        let word = newVocabularyWord.trimmingCharacters(in: .whitespaces)
        guard !word.isEmpty else { return }

        // Don't add duplicates (case-insensitive check)
        guard !vocabularyList.contains(where: { $0.lowercased() == word.lowercased() }) else {
            newVocabularyWord = ""
            return
        }

        vocabularyList.append(word)
        newVocabularyWord = ""
        saveVocabulary()
    }

    /// Remove a word from the vocabulary
    private func removeVocabularyWord(_ word: String) {
        vocabularyList.removeAll { $0 == word }
        saveVocabulary()
    }

    /// Save vocabulary to local settings and backend
    private func saveVocabulary() {
        // Save to local settings
        AssistantSettings.shared.transcriptionVocabulary = vocabularyList

        // Sync to backend
        updateTranscriptionPreferences(vocabulary: vocabularyList.joined(separator: ", "))
    }

    /// Restart transcription if currently running to apply new settings
    private func restartTranscriptionIfNeeded() {
        guard appState.isTranscribing else { return }

        // Stop and restart to apply new language settings
        appState.stopTranscription()

        // Wait a moment for cleanup, then restart
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            self.appState.startTranscription()
        }
    }

    // MARK: - Notifications Section

    private var notificationsSection: some View {
        VStack(spacing: 20) {
            // Notifications
            settingsCard(settingId: "notifications.settings") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "bell.badge.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Notifications")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $notificationsEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: notificationsEnabled) { _, newValue in
                                updateNotificationSettings(enabled: newValue)
                            }
                    }

                    Text("Control how often you receive notifications")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if notificationsEnabled {
                        Divider()
                            .background(OmiColors.backgroundQuaternary)

                        settingRow(title: "Frequency", subtitle: "How often to receive notifications", settingId: "notifications.frequency") {
                            Picker("", selection: $notificationFrequency) {
                                ForEach(frequencyOptions, id: \.0) { option in
                                    Text(option.1).tag(option.0)
                                }
                            }
                            .pickerStyle(.menu)
                            .frame(width: 120)
                            .onChange(of: notificationFrequency) { _, newValue in
                                updateNotificationSettings(frequency: newValue)
                            }
                        }

                        settingRow(title: "Focus Notifications", subtitle: "Show notification on focus changes", settingId: "notifications.focus") {
                            Toggle("", isOn: $focusNotificationsEnabled)
                                .toggleStyle(.switch)
                                .labelsHidden()
                                .onChange(of: focusNotificationsEnabled) { _, newValue in
                                    FocusAssistantSettings.shared.notificationsEnabled = newValue
                                    SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(focus: FocusSettingsResponse(notificationsEnabled: newValue)))
                                }
                        }

                        settingRow(title: "Task Notifications", subtitle: "Show notification when a task is extracted", settingId: "notifications.task") {
                            Toggle("", isOn: $taskNotificationsEnabled)
                                .toggleStyle(.switch)
                                .labelsHidden()
                                .onChange(of: taskNotificationsEnabled) { _, newValue in
                                    TaskAssistantSettings.shared.notificationsEnabled = newValue
                                    SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(task: TaskSettingsResponse(notificationsEnabled: newValue)))
                                }
                        }

                        settingRow(title: "Advice Notifications", subtitle: "Show notification when advice is generated", settingId: "notifications.advice") {
                            Toggle("", isOn: $adviceNotificationsEnabled)
                                .toggleStyle(.switch)
                                .labelsHidden()
                                .onChange(of: adviceNotificationsEnabled) { _, newValue in
                                    AdviceAssistantSettings.shared.notificationsEnabled = newValue
                                    SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(advice: AdviceSettingsResponse(notificationsEnabled: newValue)))
                                }
                        }

                        settingRow(title: "Memory Notifications", subtitle: "Show notification when a memory is extracted", settingId: "notifications.memory") {
                            Toggle("", isOn: $memoryNotificationsEnabled)
                                .toggleStyle(.switch)
                                .labelsHidden()
                                .onChange(of: memoryNotificationsEnabled) { _, newValue in
                                    MemoryAssistantSettings.shared.notificationsEnabled = newValue
                                    SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(memory: MemorySettingsResponse(notificationsEnabled: newValue)))
                                }
                        }
                    }
                }
            }

            // Daily Summary
            settingsCard(settingId: "notifications.dailysummary") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "text.badge.checkmark")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Daily Summary")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $dailySummaryEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: dailySummaryEnabled) { _, newValue in
                                updateDailySummarySettings(enabled: newValue)
                            }
                    }

                    Text("Receive a daily summary of your conversations and activities")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if dailySummaryEnabled {
                        Divider()
                            .background(OmiColors.backgroundQuaternary)

                        settingRow(title: "Summary Time", subtitle: "When to send your daily summary", settingId: "notifications.summarytime") {
                            Picker("", selection: $dailySummaryHour) {
                                ForEach(hourOptions, id: \.self) { hour in
                                    Text(formatHour(hour)).tag(hour)
                                }
                            }
                            .pickerStyle(.menu)
                            .frame(width: 100)
                            .onChange(of: dailySummaryHour) { _, newValue in
                                updateDailySummarySettings(hour: newValue)
                            }
                        }
                    }
                }
            }

        }
    }

    // MARK: - Privacy Section

    private var privacySection: some View {
        VStack(spacing: 16) {
            // Data Controls
            settingsCard(settingId: "privacy.storerecordings") {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Image(systemName: "mic.fill")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.purplePrimary)
                            .frame(width: 20)

                        Text("Store Recordings")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $recordingPermissionEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .controlSize(.small)
                            .onChange(of: recordingPermissionEnabled) { _, newValue in
                                updateRecordingPermission(newValue)
                            }
                    }
                    .padding(.bottom, 4)

                    Text("Allow Omi to store audio recordings of your conversations")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.leading, 34)

                    Divider()
                        .padding(.vertical, 12)

                    HStack {
                        Image(systemName: "cloud.fill")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.purplePrimary)
                            .frame(width: 20)

                        Text("Private Cloud Sync")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $privateCloudSyncEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .controlSize(.small)
                            .onChange(of: privateCloudSyncEnabled) { _, newValue in
                                updatePrivateCloudSync(newValue)
                            }
                    }
                    .padding(.bottom, 4)

                    Text("Sync your data securely to your private cloud storage")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.leading, 34)
                }
            }

            // Encryption
            settingsCard(settingId: "privacy.encryption") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 10) {
                        Image(systemName: "shield.lefthalf.filled")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.purplePrimary)
                            .frame(width: 20)

                        Text("Encryption")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                    }

                    HStack(spacing: 10) {
                        Image(systemName: "checkmark.circle.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(.green)
                            .frame(width: 20)

                        Text("Server-side encryption")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textSecondary)

                        Text("Active")
                            .scaledFont(size: 10, weight: .semibold)
                            .foregroundColor(.green)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.green.opacity(0.15))
                            .cornerRadius(3)
                    }
                    .padding(.leading, 14)

                    HStack(spacing: 10) {
                        Image(systemName: "lock.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 20)

                        Text("End-to-end encryption")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Coming Soon")
                            .scaledFont(size: 10, weight: .semibold)
                            .foregroundColor(OmiColors.textTertiary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(OmiColors.backgroundQuaternary.opacity(0.5))
                            .cornerRadius(3)
                    }
                    .padding(.leading, 14)

                    Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.leading, 34)
                }
            }

            // What We Track
            settingsCard(settingId: "privacy.tracking") {
                VStack(alignment: .leading, spacing: 0) {
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            isTrackingExpanded.toggle()
                        }
                    }) {
                        HStack(spacing: 10) {
                            Image(systemName: "list.bullet")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.purplePrimary)
                                .frame(width: 20)

                            Text("What We Track")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Spacer()

                            Image(systemName: "chevron.right")
                                .scaledFont(size: 11, weight: .semibold)
                                .foregroundColor(OmiColors.textTertiary)
                                .rotationEffect(.degrees(isTrackingExpanded ? 90 : 0))
                        }
                    }
                    .buttonStyle(.plain)

                    if isTrackingExpanded {
                        VStack(alignment: .leading, spacing: 6) {
                            trackingItem("Onboarding steps completed")
                            trackingItem("Settings changes")
                            trackingItem("App installations and usage")
                            trackingItem("Device connection status")
                            trackingItem("Transcript processing events")
                            trackingItem("Conversation creation and updates")
                            trackingItem("Memory extraction events")
                            trackingItem("Chat interactions")
                            trackingItem("Speech profile creation")
                            trackingItem("Focus session events")
                            trackingItem("App open/close events")
                        }
                        .padding(.top, 10)
                        .padding(.leading, 34)
                        .transition(.opacity)
                    }
                }
            }

            // Privacy Guarantees
            settingsCard(settingId: "privacy.privacy") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        Image(systemName: "hand.raised.fill")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.purplePrimary)
                            .frame(width: 20)

                        Text("Privacy Guarantees")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        privacyBullet("Anonymous tracking with randomly generated IDs")
                        privacyBullet("No personal info stored in analytics")
                        privacyBullet("Data is never sold or shared with third parties")
                        privacyBullet("Opt out of tracking at any time")
                    }
                    .padding(.leading, 34)
                }
            }
        }
    }

    // MARK: - Account Section

    private var accountSection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "account.account") {
                HStack(spacing: 16) {
                    Image(systemName: "person.circle.fill")
                        .scaledFont(size: 40)
                        .foregroundColor(OmiColors.textTertiary)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(AuthService.shared.displayName.isEmpty ? "User" : AuthService.shared.displayName)
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        if let email = AuthState.shared.userEmail {
                            Text(email)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }

                    Spacer()

                    Button("Sign Out") {
                        appState.stopTranscription()
                        ProactiveAssistantsPlugin.shared.stopMonitoring()
                        try? AuthService.shared.signOut()
                    }
                    .buttonStyle(.bordered)
                }
            }

//            settingsCard {
//                HStack(spacing: 16) {
//                    Image(systemName: "bolt.fill")
//                        .scaledFont(size: 16)
//                        .foregroundColor(.yellow)
//
//                    VStack(alignment: .leading, spacing: 4) {
//                        Text("Upgrade to Pro")
//                            .scaledFont(size: 15, weight: .medium)
//                            .foregroundColor(OmiColors.textPrimary)
//
//                        Text("Unlock all features and unlimited usage")
//                            .scaledFont(size: 13)
//                            .foregroundColor(OmiColors.textTertiary)
//                    }
//
//                    Spacer()
//
//                    Button("Upgrade") {
//                        if let url = URL(string: "https://omi.me/pricing") {
//                            NSWorkspace.shared.open(url)
//                        }
//                    }
//                    .buttonStyle(.borderedProminent)
//                    .tint(OmiColors.purplePrimary)
//                }
//            }
        }
    }

    // MARK: - AI Chat Section

    private var aiChatSection: some View {
        VStack(spacing: 20) {
            // AI Provider card
            settingsCard(settingId: "aichat.provider") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "cpu")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("AI Provider")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Picker("", selection: $chatBridgeMode) {
                            Text("Omi AI (Free)").tag("agentSDK")
                            Text("Your Claude Account").tag("claudeCode")
                        }
                        .pickerStyle(.menu)
                        .frame(width: 200)
                        .onChange(of: chatBridgeMode) { _, newMode in
                            if let mode = ChatProvider.BridgeMode(rawValue: newMode) {
                                Task {
                                    await chatProvider?.switchBridgeMode(to: mode)
                                }
                            }
                        }
                    }

                    Text(chatBridgeMode == "claudeCode"
                         ? "Using your Claude Pro/Max subscription. You'll be prompted to sign in with your Claude account."
                         : "Using Omi's AI — free for all users.")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            // Ask Mode card
            settingsCard(settingId: "aichat.askmode") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Ask Mode")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $askModeEnabled)
                            .toggleStyle(.switch)
                            .controlSize(.small)
                            .labelsHidden()
                    }

                    Text("When enabled, shows an Ask/Act toggle in the chat. Ask mode restricts the AI to read-only actions. When disabled, the AI always runs in Act mode.")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            // Workspace card
            settingsCard(settingId: "aichat.workspace") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "folder")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Workspace")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Button("Browse...") {
                            let panel = NSOpenPanel()
                            panel.canChooseFiles = false
                            panel.canChooseDirectories = true
                            panel.allowsMultipleSelection = false
                            panel.message = "Select a project directory"
                            if panel.runModal() == .OK, let url = panel.url {
                                aiChatWorkingDirectory = url.path
                                refreshAIChatConfig()
                                // Update ChatProvider
                                chatProvider?.aiChatWorkingDirectory = url.path
                                Task { await chatProvider?.discoverClaudeConfig() }
                                if chatProvider?.workingDirectory == nil {
                                    chatProvider?.workingDirectory = url.path
                                }
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)

                        if !aiChatWorkingDirectory.isEmpty {
                            Button("Clear") {
                                aiChatWorkingDirectory = ""
                                refreshAIChatConfig()
                                chatProvider?.aiChatWorkingDirectory = ""
                                Task { await chatProvider?.discoverClaudeConfig() }
                                chatProvider?.workingDirectory = nil
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }

                    if !aiChatWorkingDirectory.isEmpty {
                        Text(aiChatWorkingDirectory)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                            .truncationMode(.middle)

                        Text("Project-level CLAUDE.md and skills will be discovered from this directory")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    } else {
                        Text("No workspace set. Set a project directory to discover project-level CLAUDE.md and skills.")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }

            // CLAUDE.md card
            settingsCard(settingId: "aichat.claudemd") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "doc.text")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("CLAUDE.md")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()
                    }

                    // Global CLAUDE.md
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Global")
                                .scaledFont(size: 11, weight: .medium)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(OmiColors.backgroundPrimary.opacity(0.5))
                                )

                            Spacer()

                            if aiChatClaudeMdContent != nil {
                                Button("View") {
                                    fileViewerTitle = "Global CLAUDE.md"
                                    fileViewerContent = aiChatClaudeMdContent ?? ""
                                    showFileViewer = true
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)

                                Toggle("", isOn: $claudeMdEnabled)
                                    .toggleStyle(.switch)
                                    .controlSize(.small)
                                    .labelsHidden()
                            }
                        }

                        if let path = aiChatClaudeMdPath, let content = aiChatClaudeMdContent {
                            let sizeKB = Double(content.utf8.count) / 1024.0
                            Text("\(path) (\(String(format: "%.1f", sizeKB)) KB)")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        } else {
                            Text("No CLAUDE.md found at ~/.claude/CLAUDE.md")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }

                    // Project CLAUDE.md (only show if workspace is set)
                    if !aiChatWorkingDirectory.isEmpty {
                        Divider().opacity(0.3)

                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("Project")
                                    .scaledFont(size: 11, weight: .medium)
                                    .foregroundColor(OmiColors.purplePrimary)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(
                                        RoundedRectangle(cornerRadius: 4)
                                            .fill(OmiColors.purplePrimary.opacity(0.1))
                                    )

                                Spacer()

                                if aiChatProjectClaudeMdContent != nil {
                                    Button("View") {
                                        fileViewerTitle = "Project CLAUDE.md"
                                        fileViewerContent = aiChatProjectClaudeMdContent ?? ""
                                        showFileViewer = true
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)

                                    Toggle("", isOn: $projectClaudeMdEnabled)
                                        .toggleStyle(.switch)
                                        .controlSize(.small)
                                        .labelsHidden()
                                }
                            }

                            if let path = aiChatProjectClaudeMdPath, let content = aiChatProjectClaudeMdContent {
                                let sizeKB = Double(content.utf8.count) / 1024.0
                                Text("\(path) (\(String(format: "%.1f", sizeKB)) KB)")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            } else {
                                Text("No CLAUDE.md found at \(aiChatWorkingDirectory)/CLAUDE.md")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }
                    }
                }
            }

            // Skills card
            settingsCard(settingId: "aichat.skills") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "sparkles")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        if aiChatProjectDiscoveredSkills.isEmpty {
                            Text("Skills (\(aiChatDiscoveredSkills.count) discovered)")
                                .scaledFont(size: 15, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)
                        } else {
                            Text("Skills (\(aiChatDiscoveredSkills.count) global + \(aiChatProjectDiscoveredSkills.count) project)")
                                .scaledFont(size: 15, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)
                        }

                        Spacer()

                        Button(action: { refreshAIChatConfig() }) {
                            Image(systemName: "arrow.clockwise")
                                .scaledFont(size: 13)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    let allSkills: [(skill: (name: String, description: String, path: String), origin: String)] =
                        aiChatDiscoveredSkills.map { ($0, "Global") } +
                        aiChatProjectDiscoveredSkills.map { ($0, "Project") }

                    if allSkills.isEmpty {
                        Text("No skills found in ~/.claude/skills/")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    } else {
                        Text("Skill descriptions are included in the AI chat system prompt")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        // Search field
                        HStack(spacing: 8) {
                            Image(systemName: "magnifyingglass")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)

                            TextField("Search skills...", text: $skillSearchQuery)
                                .textFieldStyle(.plain)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textPrimary)

                            if !skillSearchQuery.isEmpty {
                                Button(action: { skillSearchQuery = "" }) {
                                    Image(systemName: "xmark.circle.fill")
                                        .scaledFont(size: 12)
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundPrimary.opacity(0.5))
                        )

                        ScrollView {
                            let filteredSkills = allSkills.enumerated().filter { _, item in
                                skillSearchQuery.isEmpty ||
                                item.skill.name.localizedCaseInsensitiveContains(skillSearchQuery) ||
                                item.skill.description.localizedCaseInsensitiveContains(skillSearchQuery)
                            }

                            VStack(spacing: 0) {
                                ForEach(Array(filteredSkills.enumerated()), id: \.offset) { filteredIndex, item in
                                    let skill = item.element.skill
                                    let origin = item.element.origin
                                    HStack(spacing: 10) {
                                        Toggle("", isOn: Binding(
                                            get: { !aiChatDisabledSkills.contains(skill.name) },
                                            set: { enabled in
                                                if enabled {
                                                    aiChatDisabledSkills.remove(skill.name)
                                                } else {
                                                    aiChatDisabledSkills.insert(skill.name)
                                                }
                                                saveDisabledSkills()
                                            }
                                        ))
                                        .toggleStyle(.checkbox)
                                        .labelsHidden()

                                        VStack(alignment: .leading, spacing: 2) {
                                            HStack(spacing: 6) {
                                                Text(skill.name)
                                                    .scaledFont(size: 13, weight: .medium)
                                                    .foregroundColor(OmiColors.textPrimary)

                                                Text(origin)
                                                    .scaledFont(size: 9, weight: .medium)
                                                    .foregroundColor(origin == "Project" ? OmiColors.purplePrimary : OmiColors.textTertiary)
                                                    .padding(.horizontal, 4)
                                                    .padding(.vertical, 1)
                                                    .background(
                                                        RoundedRectangle(cornerRadius: 3)
                                                            .fill(origin == "Project" ? OmiColors.purplePrimary.opacity(0.1) : OmiColors.backgroundPrimary.opacity(0.5))
                                                    )
                                            }

                                            if !skill.description.isEmpty {
                                                Text(skill.description)
                                                    .scaledFont(size: 11)
                                                    .foregroundColor(OmiColors.textTertiary)
                                                    .lineLimit(1)
                                                    .truncationMode(.tail)
                                            }
                                        }

                                        Spacer()

                                        Button("View") {
                                            fileViewerTitle = "\(skill.name)/SKILL.md"
                                            fileViewerContent = (try? String(contentsOfFile: skill.path, encoding: .utf8)) ?? "Unable to read file"
                                            showFileViewer = true
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.mini)
                                    }
                                    .padding(.vertical, 6)
                                    .padding(.horizontal, 4)

                                    if filteredIndex < filteredSkills.count - 1 {
                                        Divider()
                                            .opacity(0.3)
                                    }
                                }
                            }
                        }
                        .frame(maxHeight: 300)
                    }
                }
            }

            // Browser Extension card
            settingsCard(settingId: "aichat.browserextension") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "globe")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Browser Extension")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        if !playwrightExtensionToken.isEmpty {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(Color.green)
                                    .frame(width: 6, height: 6)
                                Text("Connected")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }

                        Toggle("", isOn: $playwrightUseExtension)
                            .toggleStyle(.switch)
                            .controlSize(.small)
                            .labelsHidden()
                            .onChange(of: playwrightUseExtension) { _, _ in
                            }
                    }

                    Text("Lets the AI use your Chrome browser with all your logged-in sessions.")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)

                    if playwrightUseExtension {
                        if playwrightExtensionToken.isEmpty {
                            // No token — show "Set Up" button
                            Button(action: {
                                showBrowserSetup = true
                            }) {
                                HStack(spacing: 6) {
                                    Image(systemName: "wrench.and.screwdriver")
                                        .scaledFont(size: 12)
                                    Text("Set Up")
                                        .scaledFont(size: 13, weight: .medium)
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                        } else {
                            // Token is set — show compact view
                            HStack(spacing: 8) {
                                Text("Token")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)

                                Text(String(playwrightExtensionToken.prefix(8)) + "...")
                                    .scaledFont(size: 12, weight: .medium)
                                    .foregroundColor(OmiColors.textPrimary)
                                    .font(.system(.body, design: .monospaced))

                                Spacer()

                                Button(action: {
                                    showBrowserSetup = true
                                }) {
                                    HStack(spacing: 4) {
                                        Image(systemName: "arrow.clockwise")
                                            .scaledFont(size: 11)
                                        Text("Reconfigure")
                                            .scaledFont(size: 12)
                                    }
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)

                                Button(action: {
                                    playwrightExtensionToken = ""
                                    UserDefaults.standard.set("", forKey: "playwrightExtensionToken")
                                }) {
                                    HStack(spacing: 4) {
                                        Image(systemName: "xmark")
                                            .scaledFont(size: 11)
                                        Text("Reset")
                                            .scaledFont(size: 12)
                                    }
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }
                        }
                    }
                }
            }

            // Dev Mode card
            settingsCard(settingId: "aichat.devmode") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "hammer")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.textTertiary)

                        Text("Dev Mode")
                            .scaledFont(size: 15, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $devModeEnabled)
                            .toggleStyle(.switch)
                            .controlSize(.small)
                            .labelsHidden()
                    }

                    Text("Let the AI modify the app's source code, rebuild it, and add custom features.")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)

                    if devModeEnabled {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 6) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                                    .scaledFont(size: 12)
                                Text("AI can modify UI, add features, create custom SQLite tables")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                            }
                            HStack(spacing: 6) {
                                Image(systemName: "lock.fill")
                                    .foregroundColor(.orange)
                                    .scaledFont(size: 12)
                                Text("Backend API, auth, and sync logic are read-only")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                            }
                        }
                    }
                }
            }
        }
        .onAppear {
            refreshAIChatConfig()
            playwrightExtensionToken = UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        }
        .sheet(isPresented: $showFileViewer) {
            fileViewerSheet
        }
        .sheet(isPresented: $showBrowserSetup) {
            BrowserExtensionSetup(
                onComplete: {
                    showBrowserSetup = false
                    playwrightExtensionToken = UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
                },
                onDismiss: {
                    showBrowserSetup = false
                    playwrightExtensionToken = UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
                },
                chatProvider: chatProvider
            )
            .fixedSize()
        }
    }

    private var fileViewerSheet: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text(fileViewerTitle)
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: { showFileViewer = false }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(16)

            Divider().opacity(0.3)

            // Content
            ScrollView {
                Text(fileViewerContent)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(OmiColors.textSecondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
        }
        .frame(width: 600, height: 500)
        .background(OmiColors.backgroundSecondary)
    }

    private func refreshAIChatConfig() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let claudeDir = "\(home)/.claude"

        // Discover global CLAUDE.md
        let mdPath = "\(claudeDir)/CLAUDE.md"
        if FileManager.default.fileExists(atPath: mdPath),
           let content = try? String(contentsOfFile: mdPath, encoding: .utf8) {
            aiChatClaudeMdContent = content
            aiChatClaudeMdPath = mdPath
        } else {
            aiChatClaudeMdContent = nil
            aiChatClaudeMdPath = nil
        }

        // Discover global skills
        var skills: [(name: String, description: String, path: String)] = []
        let skillsDir = "\(claudeDir)/skills"
        if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: skillsDir) {
            for dir in skillDirs.sorted() {
                let skillPath = "\(skillsDir)/\(dir)/SKILL.md"
                if FileManager.default.fileExists(atPath: skillPath),
                   let content = try? String(contentsOfFile: skillPath, encoding: .utf8) {
                    let desc = extractSkillDescription(from: content)
                    skills.append((name: dir, description: desc, path: skillPath))
                }
            }
        }
        aiChatDiscoveredSkills = skills

        // Discover project-level config from workspace directory
        let workspace = aiChatWorkingDirectory
        if !workspace.isEmpty, FileManager.default.fileExists(atPath: workspace) {
            // Project CLAUDE.md
            let projectMdPath = "\(workspace)/CLAUDE.md"
            if FileManager.default.fileExists(atPath: projectMdPath),
               let content = try? String(contentsOfFile: projectMdPath, encoding: .utf8) {
                aiChatProjectClaudeMdContent = content
                aiChatProjectClaudeMdPath = projectMdPath
            } else {
                aiChatProjectClaudeMdContent = nil
                aiChatProjectClaudeMdPath = nil
            }

            // Project skills
            var projectSkills: [(name: String, description: String, path: String)] = []
            let projectSkillsDir = "\(workspace)/.claude/skills"
            if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: projectSkillsDir) {
                for dir in skillDirs.sorted() {
                    let skillPath = "\(projectSkillsDir)/\(dir)/SKILL.md"
                    if FileManager.default.fileExists(atPath: skillPath),
                       let content = try? String(contentsOfFile: skillPath, encoding: .utf8) {
                        let desc = extractSkillDescription(from: content)
                        projectSkills.append((name: dir, description: desc, path: skillPath))
                    }
                }
            }
            aiChatProjectDiscoveredSkills = projectSkills
        } else {
            aiChatProjectClaudeMdContent = nil
            aiChatProjectClaudeMdPath = nil
            aiChatProjectDiscoveredSkills = []
        }

        // Load enabled skills from UserDefaults
        loadDisabledSkills()
    }

    private func extractSkillDescription(from content: String) -> String {
        guard content.hasPrefix("---") else {
            let lines = content.components(separatedBy: "\n")
            return lines.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })?.trimmingCharacters(in: .whitespaces) ?? ""
        }
        let lines = content.components(separatedBy: "\n")
        for line in lines.dropFirst() {
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("---") { break }
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("description:") {
                var value = String(line.trimmingCharacters(in: .whitespaces).dropFirst("description:".count))
                value = value.trimmingCharacters(in: .whitespaces)
                if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                   (value.hasPrefix("'") && value.hasSuffix("'")) {
                    value = String(value.dropFirst().dropLast())
                }
                return value
            }
        }
        return ""
    }

    private func loadDisabledSkills() {
        let json = UserDefaults.standard.string(forKey: "disabledSkillsJSON") ?? ""
        guard let data = json.data(using: .utf8),
              let names = try? JSONDecoder().decode([String].self, from: data) else {
            aiChatDisabledSkills = [] // Default: nothing disabled = all enabled
            return
        }
        aiChatDisabledSkills = Set(names)
    }

    private func saveDisabledSkills() {
        if let data = try? JSONEncoder().encode(Array(aiChatDisabledSkills)),
           let json = String(data: data, encoding: .utf8) {
            UserDefaults.standard.set(json, forKey: "disabledSkillsJSON")
        }
    }

    // MARK: - About Section

    // MARK: - Advanced Section

    struct UserStats {
        let conversations: Int
        let appsInstalled: Int
        let screenshotsTotal: Int
        let focusSessions: Int
        let tasksTodo: Int
        let tasksDone: Int
        let tasksDeleted: Int
        let goalsCount: Int
        let memoriesTotal: Int
    }

    private var advancedSection: some View {
        Group {
            switch selectedAdvancedSubsection {
            case .aiUserProfile, .none:
                aiUserProfileSubsection
            case .stats:
                statsSubsection
            case .featureTiers:
                featureTiersSubsection
            case .focusAssistant:
                focusAssistantSubsection
            case .taskAssistant:
                taskAssistantSubsection
            case .adviceAssistant:
                adviceAssistantSubsection
            case .memoryAssistant:
                memoryAssistantSubsection
            case .analysisThrottle:
                analysisThrottleSubsection
            case .goals:
                goalsSubsection
            case .askOmiFloatingBar:
                askOmiFloatingBarSubsection
            case .preferences:
                preferencesSubsection
            case .troubleshooting:
                troubleshootingSubsection
            }
        }
    }

    // MARK: - Advanced Subsections

    private var aiUserProfileSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.aiuserprofile") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 10) {
                        Image(systemName: "brain")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("AI User Profile")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        if isGeneratingAIProfile {
                            ProgressView()
                                .controlSize(.small)
                        } else {
                            Button(action: {
                                regenerateAIProfile()
                            }) {
                                Text(aiProfileText == nil ? "Generate Now" : "Regenerate")
                                    .scaledFont(size: 12)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    if let text = aiProfileText {
                        if isEditingAIProfile {
                            TextEditor(text: $aiProfileEditText)
                                .scaledFont(size: 13, design: .monospaced)
                                .foregroundColor(OmiColors.textSecondary)
                                .scrollContentBackground(.hidden)
                                .frame(maxHeight: 200)

                            HStack {
                                Button("Cancel") {
                                    isEditingAIProfile = false
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)

                                Button("Save") {
                                    if let id = aiProfileId {
                                        Task {
                                            let success = await AIUserProfileService.shared.updateProfileText(
                                                id: id, newText: aiProfileEditText
                                            )
                                            if success {
                                                aiProfileText = aiProfileEditText
                                            }
                                            isEditingAIProfile = false
                                        }
                                    }
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.small)

                                Spacer()
                            }
                        } else {
                            ScrollView {
                                Text(text)
                                    .scaledFont(size: 13, design: .monospaced)
                                    .foregroundColor(OmiColors.textSecondary)
                                    .textSelection(.enabled)
                                    .if_available_writingToolsNone()
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(maxHeight: 200)

                            HStack {
                                if let date = aiProfileGeneratedAt {
                                    Text("Last updated: \(date.formatted(.relative(presentation: .named)))")
                                        .scaledFont(size: 12)
                                        .foregroundColor(OmiColors.textTertiary)
                                }

                                Spacer()

                                if aiProfileDataSourcesUsed > 0 {
                                    Text("Data sources: \(aiProfileDataSourcesUsed) items")
                                        .scaledFont(size: 12)
                                        .foregroundColor(OmiColors.textTertiary)
                                }

                                Button(action: {
                                    aiProfileEditText = text
                                    isEditingAIProfile = true
                                }) {
                                    Image(systemName: "pencil")
                                        .scaledFont(size: 11)
                                }
                                .buttonStyle(.borderless)
                                .help("Edit profile")

                                Button(action: {
                                    deleteCurrentAIProfile()
                                }) {
                                    Image(systemName: "trash")
                                        .scaledFont(size: 11)
                                        .foregroundColor(.red.opacity(0.7))
                                }
                                .buttonStyle(.borderless)
                                .help("Delete this profile")
                            }
                        }
                    } else if !isGeneratingAIProfile {
                        Text("Your AI user profile will be generated automatically on next launch, or click \"Generate Now\" to create it now.")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    } else {
                        HStack {
                            Spacer()
                            VStack(spacing: 8) {
                                ProgressView()
                                Text("Generating profile...")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            Spacer()
                        }
                        .padding(.vertical, 20)
                    }
                }
            }
        }
        .task {
            // Try loading immediately (covers all restarts after first generation)
            if let profile = await AIUserProfileService.shared.getLatestProfile() {
                aiProfileId = profile.id
                aiProfileText = profile.profileText
                aiProfileGeneratedAt = profile.generatedAt
                aiProfileDataSourcesUsed = profile.dataSourcesUsed
                return
            }
            // No profile yet — first-ever generation may be in progress, poll briefly
            for _ in 0..<6 {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if let profile = await AIUserProfileService.shared.getLatestProfile() {
                    aiProfileId = profile.id
                    aiProfileText = profile.profileText
                    aiProfileGeneratedAt = profile.generatedAt
                    aiProfileDataSourcesUsed = profile.dataSourcesUsed
                    return
                }
            }
        }
    }

    private var statsSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.stats") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 10) {
                        Image(systemName: "chart.bar")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Your Stats")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    if let stats = advancedStats {
                        statRow(label: "Conversations", value: stats.conversations)
                        statRow(label: "Apps Installed", value: stats.appsInstalled)
                        if isLoadingChatMessages {
                            HStack {
                                Text("AI Chat Messages")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Spacer()
                                ProgressView()
                                    .controlSize(.mini)
                            }
                        } else if let count = chatMessageCount {
                            statRow(label: "AI Chat Messages", value: count)
                        }
                        statRow(label: "Screenshots", value: stats.screenshotsTotal)
                        statRow(label: "Focus Sessions", value: stats.focusSessions)
                        statRow(label: "Tasks (To Do)", value: stats.tasksTodo)
                        statRow(label: "Tasks (Done)", value: stats.tasksDone)
                        statRow(label: "Tasks (Removed)", value: stats.tasksDeleted)
                        statRow(label: "Goals", value: stats.goalsCount)
                        statRow(label: "Memories", value: stats.memoriesTotal)
                    } else if isLoadingStats {
                        statRowLoading(label: "Conversations")
                        statRowLoading(label: "Apps Installed")
                        statRowLoading(label: "AI Chat Messages")
                        statRowLoading(label: "Screenshots")
                        statRowLoading(label: "Focus Sessions")
                        statRowLoading(label: "Tasks (To Do)")
                        statRowLoading(label: "Tasks (Done)")
                        statRowLoading(label: "Tasks (Removed)")
                        statRowLoading(label: "Goals")
                        statRowLoading(label: "Memories")
                    } else {
                        Text("Unable to load stats")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }
        }
        .task {
            await loadAdvancedStats()
        }
        .task {
            await loadChatMessageCount()
        }
    }

    private var featureTiersSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.featuretiers") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 10) {
                        Image(systemName: "lock.shield")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Feature Tiers")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Tier picker — radio-style selector
                    VStack(alignment: .leading, spacing: 6) {
                        tierPickerRow(tier: 0, label: "Show All Features", subtitle: "Unlock everything")
                        tierPickerRow(tier: 1, label: "Tier 1", subtitle: "Conversations + Rewind")
                        tierPickerRow(tier: 2, label: "Tier 2", subtitle: "+ Memories (100 memories)")
                        tierPickerRow(tier: 3, label: "Tier 3", subtitle: "+ Tasks (100 tasks)")
                        tierPickerRow(tier: 4, label: "Tier 4", subtitle: "+ AI Chat (100 conversations)")
                        tierPickerRow(tier: 5, label: "Tier 5", subtitle: "+ Dashboard (200 convos + 2K screenshots)")
                        tierPickerRow(tier: 6, label: "Tier 6", subtitle: "+ Apps (300 conversations)")
                    }

                    if currentTierLevel > 0 {
                        Divider()
                            .background(OmiColors.backgroundQuaternary)

                        Text("Progress")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(OmiColors.textSecondary)

                        // Tier 1 — always unlocked
                        tierFeatureRow(
                            tier: 1, name: "Conversations + Rewind",
                            requirement: "Always unlocked",
                            progress: nil, unlocked: true
                        )

                        // Tier 2 — 100 memories
                        tierFeatureRow(
                            tier: 2, name: "Memories",
                            requirement: "100 memories",
                            progress: advancedStats.map { "\($0.memoriesTotal) / 100" },
                            unlocked: currentTierLevel >= 2
                        )

                        // Tier 3 — 100 tasks
                        tierFeatureRow(
                            tier: 3, name: "Tasks",
                            requirement: "100 tasks (todo + done)",
                            progress: advancedStats.map { "\($0.tasksTodo + $0.tasksDone) / 100" },
                            unlocked: currentTierLevel >= 3
                        )

                        // Tier 4 — 100 conversations
                        tierFeatureRow(
                            tier: 4, name: "AI Chat",
                            requirement: "100 conversations",
                            progress: advancedStats.map { "\($0.conversations) / 100" },
                            unlocked: currentTierLevel >= 4
                        )

                        // Tier 5 — 200 conversations + 2,000 screenshots
                        tierFeatureRow(
                            tier: 5, name: "Dashboard",
                            requirement: "200 conversations + 2K screenshots",
                            progress: advancedStats.map { "\($0.conversations) / 200 convos, \($0.screenshotsTotal) / 2,000 screenshots" },
                            unlocked: currentTierLevel >= 5
                        )

                        // Tier 6 — 300 conversations
                        tierFeatureRow(
                            tier: 6, name: "Apps",
                            requirement: "300 conversations",
                            progress: advancedStats.map { "\($0.conversations) / 300" },
                            unlocked: currentTierLevel >= 6
                        )
                    }
                }
            }
        }
    }

    private var focusAssistantSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.focusassistant") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "eye.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Focus Assistant")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $focusEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: focusEnabled) { _, newValue in
                                FocusAssistantSettings.shared.isEnabled = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(focus: FocusSettingsResponse(enabled: newValue)))
                            }
                    }

                    Text("Detect distractions and help you stay focused")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if focusEnabled {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    settingRow(title: "Visual Glow Effect", subtitle: "Show colored border when focus changes", settingId: "advanced.focusassistant.glow") {
                        Toggle("", isOn: $glowOverlayEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .disabled(isPreviewRunning)
                            .onChange(of: glowOverlayEnabled) { _, newValue in
                                AssistantSettings.shared.glowOverlayEnabled = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(shared: SharedAssistantSettingsResponse(glowOverlayEnabled: newValue)))
                                if newValue {
                                    startGlowPreview()
                                }
                            }
                    }

                    settingRow(title: "Focus Cooldown", subtitle: "Minimum time between distraction alerts", settingId: "advanced.focusassistant.cooldown") {
                        Picker("", selection: $cooldownInterval) {
                            ForEach(cooldownOptions, id: \.self) { minutes in
                                Text(formatMinutes(minutes)).tag(minutes)
                            }
                        }
                        .pickerStyle(.menu)
                        .frame(width: 120)
                        .onChange(of: cooldownInterval) { _, newValue in
                            FocusAssistantSettings.shared.cooldownInterval = newValue
                            SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(focus: FocusSettingsResponse(cooldownInterval: newValue)))
                        }
                    }

                    settingRow(title: "Focus Analysis Prompt", subtitle: "Customize AI instructions for focus analysis", settingId: "advanced.focusassistant.prompt") {
                        Button(action: {
                            PromptEditorWindow.show()
                        }) {
                            HStack(spacing: 4) {
                                Text("Edit")
                                    .scaledFont(size: 12)
                                Image(systemName: "arrow.up.right.square")
                                    .scaledFont(size: 11)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Excluded Apps for Focus Analysis
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Excluded Apps")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("Focus coaching won't trigger for these apps")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        // Built-in system exclusions (non-removable)
                        DisclosureGroup {
                            LazyVStack(spacing: 4) {
                                ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) { appName in
                                    HStack(spacing: 12) {
                                        AppIconView(appName: appName, size: 20)

                                        Text(appName)
                                            .scaledFont(size: 13)
                                            .foregroundColor(OmiColors.textTertiary)

                                        Spacer()
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 4)
                                }
                            }
                        } label: {
                            Text("System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .tint(OmiColors.textTertiary)

                        if !focusExcludedApps.isEmpty {
                            LazyVStack(spacing: 8) {
                                ForEach(Array(focusExcludedApps).sorted(), id: \.self) { appName in
                                    ExcludedAppRow(
                                        appName: appName,
                                        onRemove: {
                                            FocusAssistantSettings.shared.includeApp(appName)
                                            focusExcludedApps = FocusAssistantSettings.shared.excludedApps
                                        }
                                    )
                                }
                            }
                        }

                        AddExcludedAppView(
                            onAdd: { appName in
                                FocusAssistantSettings.shared.excludeApp(appName)
                                focusExcludedApps = FocusAssistantSettings.shared.excludedApps
                            },
                            excludedApps: focusExcludedApps
                        )
                    }
                    } // end if focusEnabled
                }
            }
        }
    }

    private var taskAssistantSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.taskassistant") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "checklist")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Task Assistant")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $taskEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: taskEnabled) { _, newValue in
                                TaskAssistantSettings.shared.isEnabled = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(task: TaskSettingsResponse(enabled: newValue)))
                            }
                    }

                    Text("Extract tasks and action items from your screen")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if taskEnabled {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Extraction Interval Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Extraction Interval")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("How often to scan for new tasks")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text(formatExtractionInterval(taskExtractionInterval))
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 80, alignment: .trailing)
                        }

                        Slider(value: Binding(
                            get: { Double(taskIntervalSliderIndex) },
                            set: { taskExtractionInterval = extractionIntervalOptions[Int($0)] }
                        ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: taskExtractionInterval) { _, newValue in
                                TaskAssistantSettings.shared.extractionInterval = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(task: TaskSettingsResponse(extractionInterval: newValue)))
                            }
                    }

                    // Minimum Confidence Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Minimum Confidence")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Only show tasks above this confidence level")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text("\(Int(taskMinConfidence * 100))%")
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 40, alignment: .trailing)
                        }

                        Slider(value: $taskMinConfidence, in: 0.3...0.9, step: 0.1)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: taskMinConfidence) { _, newValue in
                                TaskAssistantSettings.shared.minConfidence = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(task: TaskSettingsResponse(minConfidence: newValue)))
                            }
                    }

                    settingRow(title: "Task Extraction Prompt", subtitle: "Customize AI instructions for task extraction", settingId: "advanced.taskassistant.prompt") {
                        HStack(spacing: 8) {
                            Button(action: {
                                TaskTestRunnerWindow.show()
                            }) {
                                HStack(spacing: 4) {
                                    Image(systemName: "play.circle")
                                        .scaledFont(size: 11)
                                    Text("Test Run")
                                        .scaledFont(size: 12)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)

                            Button(action: {
                                TaskPromptEditorWindow.show()
                            }) {
                                HStack(spacing: 4) {
                                    Text("Edit")
                                        .scaledFont(size: 12)
                                    Image(systemName: "arrow.up.right.square")
                                        .scaledFont(size: 11)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Allowed Apps for Task Extraction (Whitelist)
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Allowed Apps")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("Tasks will only be extracted from these apps. Browsers are also filtered by keywords below.")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        // Editable list of all allowed apps
                        LazyVStack(spacing: 4) {
                            ForEach(Array(taskAllowedApps).sorted(), id: \.self) { appName in
                                HStack(spacing: 12) {
                                    AppIconView(appName: appName, size: 20)

                                    Text(appName)
                                        .scaledFont(size: 13)
                                        .foregroundColor(OmiColors.textPrimary)

                                    if TaskAssistantSettings.isBrowser(appName) {
                                        Text("browser")
                                            .scaledFont(size: 10)
                                            .foregroundColor(OmiColors.purplePrimary)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(OmiColors.purplePrimary.opacity(0.15))
                                            .cornerRadius(4)
                                    }

                                    Spacer()

                                    Button {
                                        TaskAssistantSettings.shared.disallowApp(appName)
                                        taskAllowedApps = TaskAssistantSettings.shared.allowedApps
                                    } label: {
                                        Image(systemName: "xmark.circle.fill")
                                            .scaledFont(size: 14)
                                            .foregroundColor(OmiColors.textTertiary)
                                    }
                                    .buttonStyle(.plain)
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 4)
                            }
                        }

                        AddAllowedAppView(
                            onAdd: { appName in
                                TaskAssistantSettings.shared.allowApp(appName)
                                taskAllowedApps = TaskAssistantSettings.shared.allowedApps
                            },
                            allowedApps: taskAllowedApps
                        )
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Browser Window Keywords
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Browser Window Keywords")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("For browser apps, only analyze windows whose title contains one of these keywords.")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        // Keyword chips (filterable, deletable)
                        BrowserKeywordListView(
                            keywords: $taskBrowserKeywords,
                            onAdd: { keyword in
                                TaskAssistantSettings.shared.addBrowserKeyword(keyword)
                                taskBrowserKeywords = TaskAssistantSettings.shared.browserKeywords
                            },
                            onRemove: { keyword in
                                TaskAssistantSettings.shared.removeBrowserKeyword(keyword)
                                taskBrowserKeywords = TaskAssistantSettings.shared.browserKeywords
                            }
                        )
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Task Prioritization Re-score
                    settingRow(title: "Task Prioritization", subtitle: "Re-score all tasks by relevance to your profile and goals", settingId: "advanced.taskassistant.prioritization") {
                        if isRescoringTasks {
                            ProgressView()
                                .controlSize(.small)
                        } else {
                            Button(action: {
                                isRescoringTasks = true
                                Task {
                                    await TaskPrioritizationService.shared.forceFullRescore()
                                    await MainActor.run { isRescoringTasks = false }
                                }
                            }) {
                                HStack(spacing: 4) {
                                    Image(systemName: "arrow.trianglehead.counterclockwise")
                                        .scaledFont(size: 11)
                                    Text("Re-score")
                                        .scaledFont(size: 12)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }
                    } // end if taskEnabled
                }
            }


            // Task Agent Settings (merged into Task Assistant subsection)
            settingsCard(settingId: "advanced.taskassistant.agent") {
                TaskAgentSettingsView()
            }
        }
    }

    private var adviceAssistantSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.adviceassistant") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "lightbulb.fill")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Advice Assistant")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $adviceEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: adviceEnabled) { _, newValue in
                                AdviceAssistantSettings.shared.isEnabled = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(advice: AdviceSettingsResponse(enabled: newValue)))
                            }
                    }

                    Text("Get proactive tips and suggestions")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if adviceEnabled {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Frequency Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Frequency")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("How often to check for advice opportunities")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text(formatExtractionInterval(adviceExtractionInterval))
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 80, alignment: .trailing)
                        }

                        Slider(value: Binding(
                            get: { Double(adviceIntervalSliderIndex) },
                            set: { adviceExtractionInterval = extractionIntervalOptions[Int($0)] }
                        ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: adviceExtractionInterval) { _, newValue in
                                AdviceAssistantSettings.shared.extractionInterval = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(advice: AdviceSettingsResponse(extractionInterval: newValue)))
                            }
                    }

                    // Minimum Confidence Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Minimum Confidence")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Only show advice above this confidence level")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text("\(Int(adviceMinConfidence * 100))%")
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 40, alignment: .trailing)
                        }

                        Slider(value: $adviceMinConfidence, in: 0.5...0.95, step: 0.05)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: adviceMinConfidence) { _, newValue in
                                AdviceAssistantSettings.shared.minConfidence = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(advice: AdviceSettingsResponse(minConfidence: newValue)))
                            }
                    }

                    settingRow(title: "Advice Prompt", subtitle: "Customize AI instructions for advice", settingId: "advanced.adviceassistant.prompt") {
                        Button(action: {
                            AdvicePromptEditorWindow.show()
                        }) {
                            HStack(spacing: 4) {
                                Text("Edit")
                                    .scaledFont(size: 12)
                                Image(systemName: "arrow.up.right.square")
                                    .scaledFont(size: 11)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Excluded Apps for Advice
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Excluded Apps")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("Advice won't be generated from these apps")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        // Built-in system exclusions (non-removable, shared with Task Extractor)
                        DisclosureGroup {
                            LazyVStack(spacing: 4) {
                                ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) { appName in
                                    HStack(spacing: 12) {
                                        AppIconView(appName: appName, size: 20)

                                        Text(appName)
                                            .scaledFont(size: 13)
                                            .foregroundColor(OmiColors.textTertiary)

                                        Spacer()
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 4)
                                }
                            }
                        } label: {
                            Text("System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .tint(OmiColors.textTertiary)

                        if !adviceExcludedApps.isEmpty {
                            LazyVStack(spacing: 8) {
                                ForEach(Array(adviceExcludedApps).sorted(), id: \.self) { appName in
                                    ExcludedAppRow(
                                        appName: appName,
                                        onRemove: {
                                            AdviceAssistantSettings.shared.includeApp(appName)
                                            adviceExcludedApps = AdviceAssistantSettings.shared.excludedApps
                                        }
                                    )
                                }
                            }
                        }

                        AddExcludedAppView(
                            onAdd: { appName in
                                AdviceAssistantSettings.shared.excludeApp(appName)
                                adviceExcludedApps = AdviceAssistantSettings.shared.excludedApps
                            },
                            excludedApps: adviceExcludedApps
                        )
                    }
                    } // end if adviceEnabled
                }
            }
        }
    }

    private var memoryAssistantSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.memoryassistant") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "brain.head.profile")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Memory Assistant")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Toggle("", isOn: $memoryEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: memoryEnabled) { _, newValue in
                                MemoryAssistantSettings.shared.isEnabled = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(memory: MemorySettingsResponse(enabled: newValue)))
                            }
                    }

                    Text("Extract facts and wisdom from your screen")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if memoryEnabled {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Extraction Interval Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Extraction Interval")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("How often to scan for new memories")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text(formatExtractionInterval(memoryExtractionInterval))
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 80, alignment: .trailing)
                        }

                        Slider(value: Binding(
                            get: { Double(memoryIntervalSliderIndex) },
                            set: { memoryExtractionInterval = extractionIntervalOptions[Int($0)] }
                        ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: memoryExtractionInterval) { _, newValue in
                                MemoryAssistantSettings.shared.extractionInterval = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(memory: MemorySettingsResponse(extractionInterval: newValue)))
                            }
                    }

                    // Minimum Confidence Slider
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Minimum Confidence")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Only save memories above this confidence level")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                            }

                            Spacer()

                            Text("\(Int(memoryMinConfidence * 100))%")
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                                .frame(width: 40, alignment: .trailing)
                        }

                        Slider(value: $memoryMinConfidence, in: 0.5...0.95, step: 0.05)
                            .tint(OmiColors.purplePrimary)
                            .onChange(of: memoryMinConfidence) { _, newValue in
                                MemoryAssistantSettings.shared.minConfidence = newValue
                                SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(memory: MemorySettingsResponse(minConfidence: newValue)))
                            }
                    }

                    settingRow(title: "Memory Extraction Prompt", subtitle: "Customize AI instructions for memory extraction", settingId: "advanced.memoryassistant.prompt") {
                        Button(action: {
                            MemoryPromptEditorWindow.show()
                        }) {
                            HStack(spacing: 4) {
                                Text("Edit")
                                    .scaledFont(size: 12)
                                Image(systemName: "arrow.up.right.square")
                                    .scaledFont(size: 11)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Excluded Apps for Memory Extraction
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Excluded Apps")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("Memories won't be extracted from these apps")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        // Built-in system exclusions (non-removable, shared across assistants)
                        DisclosureGroup {
                            LazyVStack(spacing: 4) {
                                ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) { appName in
                                    HStack(spacing: 12) {
                                        AppIconView(appName: appName, size: 20)

                                        Text(appName)
                                            .scaledFont(size: 13)
                                            .foregroundColor(OmiColors.textTertiary)

                                        Spacer()
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 4)
                                }
                            }
                        } label: {
                            Text("System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .tint(OmiColors.textTertiary)

                        if !memoryExcludedApps.isEmpty {
                            LazyVStack(spacing: 8) {
                                ForEach(Array(memoryExcludedApps).sorted(), id: \.self) { appName in
                                    ExcludedAppRow(
                                        appName: appName,
                                        onRemove: {
                                            MemoryAssistantSettings.shared.includeApp(appName)
                                            memoryExcludedApps = MemoryAssistantSettings.shared.excludedApps
                                        }
                                    )
                                }
                            }
                        }

                        AddExcludedAppView(
                            onAdd: { appName in
                                MemoryAssistantSettings.shared.excludeApp(appName)
                                memoryExcludedApps = MemoryAssistantSettings.shared.excludedApps
                            },
                            excludedApps: memoryExcludedApps
                        )
                    }
                    } // end if memoryEnabled
                }
            }
        }
    }

    private var analysisThrottleSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.analysisthrottle") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Analysis Throttle")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                            Text("Wait before analyzing after switching apps")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()

                        Text(formatAnalysisDelay(analysisDelay))
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .frame(width: 80, alignment: .trailing)
                    }

                    Slider(value: Binding(
                        get: { Double(analysisDelaySliderIndex) },
                        set: { analysisDelay = analysisDelayOptions[Int($0)] }
                    ), in: 0...Double(analysisDelayOptions.count - 1), step: 1)
                        .tint(OmiColors.purplePrimary)
                        .onChange(of: analysisDelay) { _, newValue in
                            AssistantSettings.shared.analysisDelay = newValue
                            SettingsSyncManager.shared.pushPartialUpdate(AssistantSettingsResponse(shared: SharedAssistantSettingsResponse(analysisDelay: newValue)))
                        }
                }
            }
        }
    }

    private var goalsSubsection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "advanced.goals") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "target")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Goals")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()
                    }

                    Text("Track personal goals with AI-powered progress detection from your conversations")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    settingRow(title: "Auto-Generate Goals", subtitle: "Automatically suggest new goals daily based on your conversations and tasks", settingId: "advanced.goals.autogenerate") {
                        Toggle("", isOn: $goalsAutoGenerateEnabled)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: goalsAutoGenerateEnabled) { _, newValue in
                                GoalGenerationService.shared.isAutoGenerationEnabled = newValue
                            }
                    }
                }
            }
        }
    }

    private var askOmiFloatingBarSubsection: some View {
        VStack(spacing: 20) {
            ShortcutsSettingsSection(highlightedSettingId: $highlightedSettingId)
        }
    }

    private var preferencesSubsection: some View {
        VStack(spacing: 20) {
            // Multiple Chat Sessions toggle
            settingsCard(settingId: "advanced.preferences.multichat") {
                HStack(spacing: 16) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Multiple Chat Sessions")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(multiChatEnabled
                             ? "Create separate chat threads"
                             : "Single chat synced with mobile app")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Toggle("", isOn: $multiChatEnabled)
                        .toggleStyle(.switch)
                        .labelsHidden()
                }
            }

            // Conversation View toggle
            settingsCard(settingId: "advanced.preferences.compact") {
                HStack(spacing: 16) {
                    Image(systemName: conversationsCompactView ? "list.bullet" : "list.bullet.rectangle")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Compact Conversations")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(conversationsCompactView
                             ? "Showing compact conversation list"
                             : "Showing expanded conversation list")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Toggle("", isOn: $conversationsCompactView)
                        .toggleStyle(.switch)
                        .labelsHidden()
                }
            }

            // Launch at Login toggle
            settingsCard(settingId: "advanced.preferences.launchatlogin") {
                HStack(spacing: 16) {
                    Image(systemName: "power")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Launch at Login")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(launchAtLoginManager.statusDescription)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Toggle("", isOn: Binding(
                        get: { launchAtLoginManager.isEnabled },
                        set: { newValue in
                            if launchAtLoginManager.setEnabled(newValue) {
                                AnalyticsManager.shared.launchAtLoginChanged(enabled: newValue, source: "user")
                            }
                        }
                    ))
                        .toggleStyle(.switch)
                        .labelsHidden()
                }
            }
        }
    }

    private var troubleshootingSubsection: some View {
        VStack(spacing: 20) {
            // Report Issue
            settingsCard(settingId: "advanced.troubleshooting.reportissue") {
                HStack(spacing: 16) {
                    Image(systemName: "exclamationmark.bubble")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Report Issue")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text("Send app logs and report a problem")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Button(action: {
                        FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
                    }) {
                        Text("Report")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(.white)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(OmiColors.purplePrimary)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }

            // Rescan Files
            settingsCard(settingId: "advanced.troubleshooting.rescanfiles") {
                HStack(spacing: 16) {
                    Image(systemName: "folder.badge.gearshape")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Rescan Files")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text("Re-index your files and update your AI profile")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Button(action: { showRescanFilesAlert = true }) {
                        Text("Rescan")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(.white)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(OmiColors.purplePrimary)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .alert("Rescan Files?", isPresented: $showRescanFilesAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Rescan") {
                    UserDefaults.standard.set(false, forKey: "hasCompletedFileIndexing")
                    NotificationCenter.default.post(name: .triggerFileIndexing, object: nil)
                }
            } message: {
                Text("This will re-scan your files and update your AI profile with the latest information about your projects and interests.")
            }

            // Reset Onboarding
            settingsCard(settingId: "advanced.troubleshooting.resetonboarding") {
                HStack(spacing: 16) {
                    Image(systemName: "arrow.counterclockwise")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Reset Onboarding")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text("Restart setup wizard and reset permissions")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Button(action: { showResetOnboardingAlert = true }) {
                        Text("Reset")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(.black)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(.white)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .alert("Reset Onboarding?", isPresented: $showResetOnboardingAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Reset & Restart", role: .destructive) {
                    appState.resetOnboardingAndRestart()
                }
            } message: {
                Text("This will reset all permissions and restart the app. You'll need to grant permissions again during setup.")
            }
        }
    }

    private func tierPickerRow(tier: Int, label: String, subtitle: String) -> some View {
        let isSelected = currentTierLevel == tier
        return Button(action: {
            TierManager.shared.userDidSetTier(tier)
        }) {
            HStack(spacing: 10) {
                Image(systemName: isSelected ? "largecircle.fill.circle" : "circle")
                    .scaledFont(size: 16)
                    .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textTertiary)

                VStack(alignment: .leading, spacing: 1) {
                    Text(label)
                        .scaledFont(size: 14, weight: isSelected ? .medium : .regular)
                        .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

                    Text(subtitle)
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.1) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }

    private func tierFeatureRow(tier: Int, name: String, requirement: String, progress: String?, unlocked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Tier \(tier)")
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundColor(unlocked ? OmiColors.purplePrimary : OmiColors.textTertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(
                        RoundedRectangle(cornerRadius: 4)
                            .fill(unlocked ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundTertiary)
                    )

                Text(name)
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(unlocked ? OmiColors.textPrimary : OmiColors.textTertiary)

                Spacer()

                if unlocked {
                    Image(systemName: "checkmark.circle.fill")
                        .scaledFont(size: 14)
                        .foregroundColor(.green)
                } else {
                    Image(systemName: "lock.fill")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            HStack(spacing: 8) {
                Text(requirement)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)

                if let progress = progress, !unlocked {
                    Text("(\(progress))")
                        .scaledMonospacedDigitFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func statRow(label: String, value: Int) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textSecondary)

            Spacer()

            Text(formatNumber(value))
                .scaledMonospacedDigitFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
        }
    }

    private func statRowLoading(label: String) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textSecondary)

            Spacer()

            ProgressView()
                .controlSize(.mini)
        }
    }

    private func formatNumber(_ n: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: n)) ?? "\(n)"
    }

    private func loadAdvancedStats() async {
        isLoadingStats = true
        defer { isLoadingStats = false }

        do {
            async let conversationsCount = APIClient.shared.getConversationsCount()
            async let installedApps = APIClient.shared.searchApps(installedOnly: true)
            async let focusCount = ProactiveStorage.shared.getTotalFocusSessionCount()
            async let filterCounts = ActionItemStorage.shared.getFilterCounts()
            async let goals = APIClient.shared.getGoals()
            async let memoryStats = MemoryStorage.shared.getStats()

            let cc = try await conversationsCount
            let ia = try await installedApps
            let fc = try await focusCount
            let filters = try await filterCounts
            let g = try await goals
            let ms = try await memoryStats

            let screenshotCount: Int
            do {
                screenshotCount = try await RewindDatabase.shared.getScreenshotCount()
            } catch {
                screenshotCount = 0
            }

            advancedStats = UserStats(
                conversations: cc,
                appsInstalled: ia.count,
                screenshotsTotal: screenshotCount,
                focusSessions: fc,
                tasksTodo: filters.todo,
                tasksDone: filters.done,
                tasksDeleted: filters.deleted,
                goalsCount: g.count,
                memoriesTotal: ms.total
            )
        } catch {
            print("SETTINGS: Failed to load advanced stats: \(error)")
        }
    }

    private func loadChatMessageCount() async {
        isLoadingChatMessages = true
        defer { isLoadingChatMessages = false }

        do {
            chatMessageCount = try await APIClient.shared.getChatMessageCount()
        } catch {
            chatMessageCount = 0
        }
    }

    // MARK: - About Section

    private var aboutSection: some View {
        VStack(spacing: 20) {
            settingsCard(settingId: "about.version") {
                VStack(spacing: 16) {
                    // App info
                    HStack(spacing: 16) {
                        if let logoImage = NSImage(contentsOf: Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png")!) {
                            Image(nsImage: logoImage)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 48, height: 48)
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Omi")
                                .scaledFont(size: 18, weight: .bold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Version \(updaterViewModel.currentVersion) (\(updaterViewModel.buildNumber))")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                                .onTapGesture {
                                    // Hidden: Option+click to enable staging channel
                                    if NSEvent.modifierFlags.contains(.option) {
                                        UserDefaults.standard.set("staging", forKey: "update_channel")
                                        updaterViewModel.updateChannel = .beta // closest visible option
                                        logSync("Settings: Staging channel enabled via hidden gesture")
                                    }
                                }
                        }

                        Spacer()
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    // Links
                    linkRow(title: "Visit Website", url: "https://omi.me")
                    linkRow(title: "Help Center", url: "https://help.omi.me")
                    Button(action: {
                        selectedSection = .privacy
                    }) {
                        HStack {
                            Text("Privacy Policy")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)

                            Spacer()

                            Image(systemName: "arrow.right")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }
                    .buttonStyle(.plain)
                    linkRow(title: "Terms of Service", url: "https://omi.me/terms")
                }
            }

            // Software Updates
            settingsCard(settingId: "about.updates") {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .scaledFont(size: 16)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("Software Updates")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Button("Check Now") {
                            updaterViewModel.checkForUpdates()
                        }
                        .buttonStyle(.bordered)
                        .disabled(!updaterViewModel.canCheckForUpdates)
                    }

                    if let lastCheck = updaterViewModel.lastUpdateCheckDate {
                        Text("Last checked: \(lastCheck, style: .relative) ago")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    settingRow(title: "Automatic Updates", subtitle: "Check for updates automatically in the background", settingId: "about.autoupdates") {
                        Toggle("", isOn: $updaterViewModel.automaticallyChecksForUpdates)
                            .toggleStyle(.switch)
                            .labelsHidden()
                    }

                    if updaterViewModel.automaticallyChecksForUpdates {
                        settingRow(title: "Auto-Install Updates", subtitle: "Automatically download and install updates when available", settingId: "about.autoinstall") {
                            Toggle("", isOn: $updaterViewModel.automaticallyDownloadsUpdates)
                                .toggleStyle(.switch)
                                .labelsHidden()
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    settingRow(title: "Update Channel", subtitle: updaterViewModel.updateChannel.description, settingId: "about.channel") {
                        Picker("", selection: $updaterViewModel.updateChannel) {
                            ForEach(UpdateChannel.allCases, id: \.self) { channel in
                                Text(channel.displayName).tag(channel)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()
                        .frame(width: 100)
                    }
                }
            }

            settingsCard(settingId: "about.reportissue") {
                HStack(spacing: 16) {
                    Image(systemName: "exclamationmark.bubble.fill")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.purplePrimary)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Report an Issue")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Text("Help us improve Omi")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Button("Report") {
                        FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    // MARK: - Helper Views

    private func fontShortcutRow(label: String, keys: String) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            Spacer()
            Text(keys)
                .scaledMonospacedFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(OmiColors.backgroundTertiary.opacity(0.8))
                .cornerRadius(5)
        }
    }

    private func settingsCard<Content: View>(settingId: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        let card = content()
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
                    )
            )
        return Group {
            if let settingId = settingId {
                card.modifier(SettingHighlightModifier(settingId: settingId, highlightedSettingId: $highlightedSettingId))
            } else {
                card
            }
        }
    }

    private func settingRow<Content: View>(title: String, subtitle: String, settingId: String? = nil, @ViewBuilder control: () -> Content) -> some View {
        let row = HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                Text(subtitle)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            control()
        }
        return Group {
            if let settingId = settingId {
                row.modifier(SettingHighlightModifier(settingId: settingId, highlightedSettingId: $highlightedSettingId))
            } else {
                row
            }
        }
    }

    private func linkRow(title: String, url: String) -> some View {
        Button(action: {
            if let url = URL(string: url) {
                NSWorkspace.shared.open(url)
            }
        }) {
            HStack {
                Text(title)
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .buttonStyle(.plain)
    }

    private func trackingItem(_ text: String) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(OmiColors.textTertiary.opacity(0.5))
                .frame(width: 4, height: 4)

            Text(text)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func privacyBullet(_ text: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark")
                .scaledFont(size: 9, weight: .bold)
                .foregroundColor(.green)

            Text(text)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
        }
    }

    // MARK: - Language Helpers

    /// Whether the selected language supports auto-detect mode
    private var autoDetectSupported: Bool {
        AssistantSettings.supportsAutoDetect(transcriptionLanguage)
    }

    /// Subtitle text for auto-detect toggle
    private var autoDetectSubtitle: String {
        if autoDetectSupported {
            return "Automatically detect spoken language"
        } else {
            return "Not available for \(languageName(for: transcriptionLanguage))"
        }
    }

    /// Get display name for a language code
    private func languageName(for code: String) -> String {
        AssistantSettings.supportedLanguages.first { $0.code == code }?.name ?? code
    }

    // MARK: - Slider Index Helpers

    private var analysisDelaySliderIndex: Int {
        analysisDelayOptions.firstIndex(of: analysisDelay) ?? 0
    }

    private var taskIntervalSliderIndex: Int {
        extractionIntervalOptions.firstIndex(of: taskExtractionInterval) ?? 0
    }

    private var adviceIntervalSliderIndex: Int {
        extractionIntervalOptions.firstIndex(of: adviceExtractionInterval) ?? 0
    }

    private var memoryIntervalSliderIndex: Int {
        extractionIntervalOptions.firstIndex(of: memoryExtractionInterval) ?? 0
    }

    // MARK: - Helpers

    private func toggleMonitoring(enabled: Bool) {
        if enabled && !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
            permissionError = "Screen recording permission required"
            isMonitoring = false
            ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
            return
        }

        permissionError = nil
        isToggling = true

        // Track setting change
        AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

        if enabled {
            ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
                DispatchQueue.main.async {
                    isToggling = false
                    if !success {
                        permissionError = error ?? "Failed to start monitoring"
                        isMonitoring = false
                    }
                }
            }
        } else {
            ProactiveAssistantsPlugin.shared.stopMonitoring()
            isToggling = false
        }

        // Persist the setting
        AssistantSettings.shared.screenAnalysisEnabled = enabled
    }

    private func toggleTranscription(enabled: Bool) {
        // Check microphone permission
        if enabled && !appState.hasMicrophonePermission {
            transcriptionError = "Microphone permission required"
            isTranscribing = false
            return
        }

        transcriptionError = nil
        isTogglingTranscription = true

        // Track setting change
        AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)

        if enabled {
            appState.startTranscription()
            isTogglingTranscription = false
            isTranscribing = true
        } else {
            appState.stopTranscription()
            isTogglingTranscription = false
            isTranscribing = false
        }

        // Persist the setting
        AssistantSettings.shared.transcriptionEnabled = enabled
    }


    private func startGlowPreview() {
        isPreviewRunning = true

        // Show the demo window and get its frame
        let demoWindow = GlowDemoWindow.show()
        let windowFrame = demoWindow.frame

        // Phase 1: Show focused (green) glow after a small delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            GlowDemoWindow.setPhase(.focused)
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .focused, isPreview: true)
        }

        // Phase 2: Show distracted (red) glow
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.3) {
            GlowDemoWindow.setPhase(.distracted)
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .distracted, isPreview: true)
        }

        // End preview and close demo window
        DispatchQueue.main.asyncAfter(deadline: .now() + 7.0) {
            GlowDemoWindow.close()
            isPreviewRunning = false
        }
    }

    private func deleteCurrentAIProfile() {
        guard let id = aiProfileId else { return }
        Task {
            let previous = await AIUserProfileService.shared.deleteProfile(id: id)
            await MainActor.run {
                if let previous {
                    aiProfileId = previous.id
                    aiProfileText = previous.profileText
                    aiProfileGeneratedAt = previous.generatedAt
                    aiProfileDataSourcesUsed = previous.dataSourcesUsed
                } else {
                    aiProfileId = nil
                    aiProfileText = nil
                    aiProfileGeneratedAt = nil
                    aiProfileDataSourcesUsed = 0
                }
            }
        }
    }

    private func regenerateAIProfile() {
        isGeneratingAIProfile = true
        Task {
            do {
                let result = try await AIUserProfileService.shared.generateProfile()
                await MainActor.run {
                    aiProfileId = result.id
                    aiProfileText = result.profileText
                    aiProfileGeneratedAt = result.generatedAt
                    aiProfileDataSourcesUsed = result.dataSourcesUsed
                    isGeneratingAIProfile = false
                }
            } catch {
                log("Settings: AI profile generation failed: \(error.localizedDescription)")
                await MainActor.run {
                    isGeneratingAIProfile = false
                }
            }
        }
    }

    private func formatMinutes(_ minutes: Int) -> String {
        if minutes == 1 {
            return "1 minute"
        } else if minutes < 60 {
            return "\(minutes) minutes"
        } else {
            return "1 hour"
        }
    }

    private func formatAnalysisDelay(_ seconds: Int) -> String {
        if seconds == 0 {
            return "Instant"
        } else if seconds < 60 {
            return "\(seconds) seconds"
        } else if seconds == 60 {
            return "1 minute"
        } else {
            return "\(seconds / 60) minutes"
        }
    }

    private func formatExtractionInterval(_ seconds: Double) -> String {
        if seconds < 60 {
            return "\(Int(seconds)) seconds"
        } else if seconds < 3600 {
            let minutes = Int(seconds / 60)
            return minutes == 1 ? "1 minute" : "\(minutes) minutes"
        } else {
            let hours = Int(seconds / 3600)
            return hours == 1 ? "1 hour" : "\(hours) hours"
        }
    }

    private func formatHour(_ hour: Int) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:00 a"
        var components = DateComponents()
        components.hour = hour
        if let date = Calendar.current.date(from: components) {
            return formatter.string(from: date)
        }
        return "\(hour):00"
    }

    // MARK: - Backend Settings

    private func loadBackendSettings() {
        guard !isLoadingSettings else { return }
        isLoadingSettings = true

        // Load local transcription settings first (these are used immediately)
        transcriptionLanguage = AssistantSettings.shared.transcriptionLanguage
        transcriptionAutoDetect = AssistantSettings.shared.transcriptionAutoDetect
        vocabularyList = AssistantSettings.shared.transcriptionVocabulary

        Task {
            do {
                // Load all settings in parallel
                async let dailySummaryTask = APIClient.shared.getDailySummarySettings()
                async let notificationsTask = APIClient.shared.getNotificationSettings()
                async let languageTask = APIClient.shared.getUserLanguage()
                async let recordingTask = APIClient.shared.getRecordingPermission()
                async let cloudSyncTask = APIClient.shared.getPrivateCloudSync()
                async let transcriptionTask = APIClient.shared.getTranscriptionPreferences()

                // Sync assistant settings from server in parallel
                async let assistantSyncTask: () = SettingsSyncManager.shared.syncFromServer()

                let (dailySummary, notifications, language, recording, cloudSync, transcription, _) = try await (
                    dailySummaryTask,
                    notificationsTask,
                    languageTask,
                    recordingTask,
                    cloudSyncTask,
                    transcriptionTask,
                    assistantSyncTask
                )

                await MainActor.run {
                    dailySummaryEnabled = dailySummary.enabled
                    dailySummaryHour = dailySummary.hour
                    notificationsEnabled = notifications.enabled
                    notificationFrequency = notifications.frequency
                    userLanguage = language.language
                    recordingPermissionEnabled = recording.enabled
                    privateCloudSyncEnabled = cloudSync.enabled
                    singleLanguageMode = transcription.singleLanguageMode
                    vocabularyList = transcription.vocabulary
                    // Sync backend vocabulary to local settings
                    AssistantSettings.shared.transcriptionVocabulary = transcription.vocabulary

                    // Sync backend language to local if different (backend is source of truth for language)
                    if !language.language.isEmpty && language.language != transcriptionLanguage {
                        transcriptionLanguage = language.language
                        AssistantSettings.shared.transcriptionLanguage = language.language
                    }

                    // Sync single language mode from backend (inverted to auto-detect)
                    // Only update if we got a valid response and it differs
                    let backendAutoDetect = !transcription.singleLanguageMode
                    if backendAutoDetect != transcriptionAutoDetect {
                        transcriptionAutoDetect = backendAutoDetect
                        AssistantSettings.shared.transcriptionAutoDetect = backendAutoDetect
                    }

                    isLoadingSettings = false
                }
            } catch {
                logError("Failed to load backend settings", error: error)
                await MainActor.run {
                    isLoadingSettings = false
                }
            }
        }
    }

    private func updateDailySummarySettings(enabled: Bool? = nil, hour: Int? = nil) {
        Task {
            do {
                let _ = try await APIClient.shared.updateDailySummarySettings(enabled: enabled, hour: hour)
            } catch {
                logError("Failed to update daily summary settings", error: error)
            }
        }
    }

    private func updateNotificationSettings(enabled: Bool? = nil, frequency: Int? = nil) {
        Task {
            do {
                let _ = try await APIClient.shared.updateNotificationSettings(enabled: enabled, frequency: frequency)
            } catch {
                logError("Failed to update notification settings", error: error)
            }
        }
    }

    private func updateLanguage(_ language: String) {
        Task {
            // Track language change
            AnalyticsManager.shared.languageChanged(language: language)
            do {
                let _ = try await APIClient.shared.updateUserLanguage(language)
            } catch {
                logError("Failed to update language", error: error)
            }
        }
    }

    private func updateRecordingPermission(_ enabled: Bool) {
        Task {
            do {
                try await APIClient.shared.setRecordingPermission(enabled: enabled)
            } catch {
                logError("Failed to update recording permission", error: error)
            }
        }
    }

    private func updatePrivateCloudSync(_ enabled: Bool) {
        Task {
            do {
                try await APIClient.shared.setPrivateCloudSync(enabled: enabled)
            } catch {
                logError("Failed to update private cloud sync", error: error)
            }
        }
    }

    private func updateTranscriptionPreferences(singleLanguageMode: Bool? = nil, vocabulary: String? = nil) {
        Task {
            do {
                var vocabArray: [String]? = nil
                if let vocab = vocabulary {
                    vocabArray = vocab.split(separator: ",")
                        .map { $0.trimmingCharacters(in: .whitespaces) }
                        .filter { !$0.isEmpty }
                }
                let _ = try await APIClient.shared.updateTranscriptionPreferences(
                    singleLanguageMode: singleLanguageMode,
                    vocabulary: vocabArray
                )
            } catch {
                logError("Failed to update transcription preferences", error: error)
            }
        }
    }
}

// MARK: - Excluded App Row

struct ExcludedAppRow: View {
    let appName: String
    let onRemove: () -> Void

    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 12) {
            AppIconView(appName: appName, size: 24)

            Text(appName)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .scaledFont(size: 16)
                    .foregroundColor(isHovered ? OmiColors.error : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isHovered ? OmiColors.backgroundQuaternary.opacity(0.5) : Color.clear)
        )
        .onHover { hovering in
            isHovered = hovering
        }
    }
}

// MARK: - Add Excluded App View

struct AddExcludedAppView: View {
    let onAdd: (String) -> Void
    let excludedApps: Set<String>

    @State private var newAppName: String = ""
    @State private var showingSuggestions = false
    @State private var runningApps: [String] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Add App to Exclusion List")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            HStack(spacing: 8) {
                TextField("App name (e.g., Passwords)", text: $newAppName)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit {
                        addApp()
                    }

                Button("Add") {
                    addApp()
                }
                .buttonStyle(.bordered)
                .disabled(newAppName.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            // Running apps suggestions
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Currently Running Apps")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)

                    Spacer()

                    Button {
                        refreshRunningApps()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(runningApps.filter { !excludedApps.contains($0) && !TaskAssistantSettings.builtInExcludedApps.contains($0) }, id: \.self) { appName in
                            RunningAppChip(appName: appName) {
                                onAdd(appName)
                            }
                        }
                    }
                }
            }
            .padding(.top, 4)
        }
        .onAppear {
            refreshRunningApps()
        }
    }

    private func addApp() {
        let trimmed = newAppName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        onAdd(trimmed)
        newAppName = ""
    }

    private func refreshRunningApps() {
        let apps = NSWorkspace.shared.runningApplications
            .compactMap { $0.localizedName }
            .filter { !$0.isEmpty }
            .sorted()

        // Remove duplicates while preserving order
        var seen = Set<String>()
        runningApps = apps.filter { seen.insert($0).inserted }
    }
}

// MARK: - Add Allowed App View (Whitelist)

struct AddAllowedAppView: View {
    let onAdd: (String) -> Void
    let allowedApps: Set<String>

    @State private var newAppName: String = ""
    @State private var runningApps: [String] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Add App to Allowed List")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            HStack(spacing: 8) {
                TextField("App name (e.g., Mail)", text: $newAppName)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit {
                        addApp()
                    }

                Button("Add") {
                    addApp()
                }
                .buttonStyle(.bordered)
                .disabled(newAppName.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            // Running apps suggestions
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Currently Running Apps")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)

                    Spacer()

                    Button {
                        refreshRunningApps()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(runningApps.filter { !allowedApps.contains($0) && !TaskAssistantSettings.defaultAllowedApps.contains($0) }, id: \.self) { appName in
                            RunningAppChip(appName: appName) {
                                onAdd(appName)
                            }
                        }
                    }
                }
            }
            .padding(.top, 4)
        }
        .onAppear {
            refreshRunningApps()
        }
    }

    private func addApp() {
        let trimmed = newAppName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        onAdd(trimmed)
        newAppName = ""
    }

    private func refreshRunningApps() {
        let apps = NSWorkspace.shared.runningApplications
            .compactMap { $0.localizedName }
            .filter { !$0.isEmpty }
            .sorted()

        // Remove duplicates while preserving order
        var seen = Set<String>()
        runningApps = apps.filter { seen.insert($0).inserted }
    }
}

// MARK: - Browser Keyword List View

struct BrowserKeywordListView: View {
    @Binding var keywords: [String]
    let onAdd: (String) -> Void
    let onRemove: (String) -> Void

    @State private var newKeyword: String = ""
    @State private var filterText: String = ""

    private var filteredKeywords: [String] {
        if filterText.isEmpty {
            return keywords
        }
        return keywords.filter { $0.lowercased().contains(filterText.lowercased()) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Filter field
            HStack(spacing: 8) {
                Image(systemName: "line.3.horizontal.decrease")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
                TextField("Filter keywords...", text: $filterText)
                    .textFieldStyle(.plain)
                    .scaledFont(size: 12)
                if !filterText.isEmpty {
                    Button {
                        filterText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(6)

            // Keyword chips in a wrapping flow layout
            ScrollView {
                FlowLayout(spacing: 6) {
                    ForEach(filteredKeywords, id: \.self) { keyword in
                        HStack(spacing: 4) {
                            Text(keyword)
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textPrimary)
                            Button {
                                onRemove(keyword)
                            } label: {
                                Image(systemName: "xmark")
                                    .scaledFont(size: 8, weight: .bold)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(OmiColors.backgroundTertiary)
                        .cornerRadius(6)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: 150)

            // Add new keyword
            HStack(spacing: 8) {
                TextField("Add keyword...", text: $newKeyword)
                    .textFieldStyle(.roundedBorder)
                    .scaledFont(size: 12)
                    .onSubmit { addKeyword() }

                Button("Add") { addKeyword() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(newKeyword.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            Text("\(keywords.count) keywords")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func addKeyword() {
        let trimmed = newKeyword.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        onAdd(trimmed)
        newKeyword = ""
    }
}


// MARK: - Running App Chip

struct RunningAppChip: View {
    let appName: String
    let onTap: () -> Void

    @State private var isHovered = false

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 6) {
                AppIconView(appName: appName, size: 16)

                Text(appName)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)

                Image(systemName: "plus.circle.fill")
                    .scaledFont(size: 12)
                    .foregroundColor(isHovered ? OmiColors.purplePrimary : OmiColors.textTertiary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isHovered ? OmiColors.backgroundQuaternary : OmiColors.backgroundTertiary.opacity(0.5))
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovered = hovering
        }
    }
}

#Preview {
    SettingsPage(
        appState: AppState(),
        selectedSection: .constant(.advanced),
        selectedAdvancedSubsection: .constant(.aiUserProfile),
        highlightedSettingId: .constant(nil)
    )
}
