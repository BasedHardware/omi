import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

/// Settings page that wraps SettingsView with proper dark theme styling for the main window
struct SettingsPage: View {
  @ObservedObject var appState: AppState
  @Binding var selectedSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingId: String?
  var chatProvider: ChatProvider? = nil

  var body: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(spacing: 0) {
          // Section header
          HStack {
            Text(selectedSection.rawValue)
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
  }
}

struct SubscriptionPlanCatalogMerger {
  static func merge(
    primary: [SubscriptionPlanOption],
    fallback: [SubscriptionPlanOption]
  ) -> [SubscriptionPlanOption] {
    var mergedById: [String: SubscriptionPlanOption] = [:]

    for plan in fallback {
      mergedById[plan.id] = plan
    }

    for plan in primary {
      if let existing = mergedById[plan.id] {
        mergedById[plan.id] = SubscriptionPlanOption(
          id: plan.id,
          title: plan.title.isEmpty ? existing.title : plan.title,
          subtitle: plan.subtitle ?? existing.subtitle,
          description: plan.description ?? existing.description,
          eyebrow: plan.eyebrow ?? existing.eyebrow,
          features: plan.features.isEmpty ? existing.features : plan.features,
          prices: mergePrices(primary: plan.prices, fallback: existing.prices)
        )
      } else {
        mergedById[plan.id] = plan
      }
    }

    return Array(mergedById.values)
  }

  private static func mergePrices(
    primary: [SubscriptionPriceOption],
    fallback: [SubscriptionPriceOption]
  ) -> [SubscriptionPriceOption] {
    var mergedById: [String: SubscriptionPriceOption] = [:]

    for price in fallback {
      mergedById[price.id] = price
    }

    for price in primary {
      mergedById[price.id] = price
    }

    return Array(mergedById.values).sorted { lhs, rhs in
      if lhs.title != rhs.title {
        return lhs.title < rhs.title
      }
      return lhs.id < rhs.id
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
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

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
  @State private var taskChatAgentEnabled: Bool
  @State private var taskAgentWorkingDirectory: String
  @State private var taskExtractionInterval: Double
  @State private var taskMinConfidence: Double
  @State private var taskNotificationsEnabled: Bool
  @State private var taskAllowedApps: Set<String>
  @State private var taskBrowserKeywords: [String]
  @State private var isRescoringTasks = false

  // Advice Assistant states
  @State private var insightEnabled: Bool
  @State private var insightExtractionInterval: Double
  @State private var insightMinConfidence: Double
  @State private var insightNotificationsEnabled: Bool
  @State private var insightExcludedApps: Set<String>

  // Memory Assistant states
  @State private var memoryEnabled: Bool
  @State private var memoryExtractionInterval: Double
  @State private var memoryMinConfidence: Double
  @State private var memoryNotificationsEnabled: Bool
  @State private var memoryExcludedApps: Set<String>

  // Goals states
  @State private var goalsAutoGenerateEnabled: Bool = GoalGenerationService.shared
    .isAutoGenerationEnabled

  // Glow preview state
  @State private var isPreviewRunning: Bool = false

  // Downgrade confirmation alert
  @State private var showDowngradeAlert = false

  // Tier gating (0 = show all, 1-6 = sequential tiers)
  @AppStorage("currentTierLevel") private var currentTierLevel = 0

  // Advanced stats
  @State private var advancedStats: UserStats?
  @State private var isLoadingStats = false
  @State private var chatMessageCount: Int?
  @State private var isLoadingChatMessages = false
  @State private var showProfileAndStats = false

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
  @State private var userSubscription: UserSubscriptionResponse?
  @State private var isLoadingSubscription: Bool = false
  @State private var subscriptionError: String?
  @State private var chatUsageQuota: APIClient.ChatUsageQuota?
  @State private var isLoadingChatUsage: Bool = false
  @State private var overageInfo: OverageInfoResponse?
  @State private var isLoadingOverage: Bool = false
  @State private var showOverageExplainer: Bool = false
  @State private var fallbackPlanCatalog: [SubscriptionPlanOption] = []
  @State private var activeCheckoutPriceId: String?
  @State private var selectedPlanIdForCheckout: String?
  @State private var isOpeningCustomerPortal: Bool = false
  @State private var activeBillingWebFlow: BillingWebFlow?
  @State private var pendingSubscriptionPriceId: String?
  @State private var pendingCheckoutSessionId: String?

  private let cooldownOptions = [1, 2, 5, 10, 15, 30, 60]
  private let analysisDelayOptions = [0, 10, 20, 30, 60, 300]  // seconds: instant, 10s, 20s, 30s, 1 min, 5 min
  private let extractionIntervalOptions: [Double] = [10.0, 600.0, 3600.0]  // 10s, 10min, 1hr
  private let hourOptions = Array(0...23)
  private let frequencyOptions = [
    (0, "Off"),
    (1, "Minimal"),
    (2, "Low"),
    (3, "Balanced"),
    (4, "High"),
    (5, "Maximum"),
  ]
  // Use the full language list from AssistantSettings
  private var languageOptions: [(String, String)] {
    AssistantSettings.supportedLanguages.map { ($0.code, $0.name) }
  }

  // Language auto-detect state (from local settings)
  @State private var transcriptionAutoDetect: Bool = true
  @State private var transcriptionLanguage: String = "en"
  @State private var vadGateEnabled: Bool = false

  // Multi-chat mode setting
  @AppStorage("multiChatEnabled") private var multiChatEnabled = false
  @AppStorage("conversationsCompactView") private var conversationsCompactView = true

  // AI Chat settings
  @AppStorage("chatBridgeMode") private var chatBridgeMode: String = "piMono"
  @AppStorage("askModeEnabled") private var askModeEnabled = false
  @AppStorage("claudeMdEnabled") private var claudeMdEnabled = true
  @AppStorage("projectClaudeMdEnabled") private var projectClaudeMdEnabled = true
  @AppStorage("aiChatWorkingDirectory") private var aiChatWorkingDirectory: String = ""
  @State private var aiChatClaudeMdContent: String?
  @State private var aiChatClaudeMdPath: String?
  @State private var aiChatProjectClaudeMdContent: String?
  @State private var aiChatProjectClaudeMdPath: String?
  @State private var aiChatDiscoveredSkills: [(name: String, description: String, path: String)] =
    []
  @State private var aiChatProjectDiscoveredSkills:
    [(name: String, description: String, path: String)] = []
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
    case rewind = "Rewind"
    case transcription = "Transcription"
    case notifications = "Notifications"
    case privacy = "Privacy"
    case account = "Account"
    case planUsage = "Plan and Usage"
    case aiChat = "AI Chat"
    case floatingBar = "Floating Bar"
    case shortcuts = "Shortcuts"
    case advanced = "Advanced"
    case about = "About"
  }

  enum AdvancedSubsection: String, CaseIterable {
    case resetOnboarding = "Reset Onboarding"
    case aiUserProfile = "AI User Profile"
    case stats = "Your Stats"
    case focusAssistant = "Focus Assistant"
    case taskAssistant = "Task Assistant"
    case insightAssistant = "Insight Assistant"
    case memoryAssistant = "Memory Assistant"
    case analysisThrottle = "Analysis Throttle"
    case goals = "Goals"
    case preferences = "Preferences"
    case troubleshooting = "Troubleshooting"
    case gmailReader = "Gmail Reader"
    case calendarSync = "Calendar Sync"
    case developerKeys = "Developer API Keys"

    var icon: String {
      switch self {
      case .resetOnboarding: return "arrow.counterclockwise"
      case .aiUserProfile: return "brain"
      case .stats: return "chart.bar"
      case .focusAssistant: return "eye.fill"
      case .taskAssistant: return "checklist"
      case .insightAssistant: return "lightbulb.fill"
      case .memoryAssistant: return "brain.head.profile"
      case .analysisThrottle: return "clock.arrow.2.circlepath"
      case .goals: return "target"
      case .preferences: return "slider.horizontal.3"
      case .troubleshooting: return "wrench.and.screwdriver"
      case .gmailReader: return "envelope.fill"
      case .calendarSync: return "calendar"
      case .developerKeys: return "key"
      }
    }
  }

  @State private var showResetOnboardingAlert: Bool = false
  @State private var showRescanFilesAlert: Bool = false
  @State private var showDeleteAccountAlert: Bool = false

  // Gmail Reader states
  @State private var gmailEmails: [GmailEmail] = []
  @State private var isReadingGmail: Bool = false
  @State private var isSavingGmailMemories: Bool = false
  @State private var gmailMemoriesSaved: Int = 0
  @State private var gmailReadError: String?
  @State private var gmailLastFetched: Date?

  // Calendar Sync states
  @State private var calendarEvents: [CalendarEvent] = []
  @State private var isReadingCalendar: Bool = false
  @State private var calendarMemoriesCreated: Int = 0
  @State private var calendarTasksCreated: Int = 0
  @State private var calendarSyncError: String?
  @State private var calendarLastSynced: Date?

  @State private var isDeletingAccount: Bool = false
  @State private var deleteAccountError: String?

  // Developer API Key overrides — also double as BYOK free-plan credentials
  // when all four (Gemini, Anthropic, OpenAI, Deepgram) are provided.
  @AppStorage("dev_gemini_api_key") private var devGeminiKey: String = ""
  @AppStorage("dev_anthropic_api_key") private var devAnthropicKey: String = ""
  @AppStorage("dev_openai_api_key") private var devOpenAIKey: String = ""
  @AppStorage("dev_deepgram_api_key") private var devDeepgramKey: String = ""
  @State private var byokKeyStatuses: [BYOKProvider: BYOKValidator.Status] = [:]
  @State private var byokActivationError: String?

  init(
    appState: AppState,
    selectedSection: Binding<SettingsSection>,
    highlightedSettingId: Binding<String?> = .constant(nil),
    chatProvider: ChatProvider? = nil
  ) {
    self.appState = appState
    self._selectedSection = selectedSection
    self._highlightedSettingId = highlightedSettingId
    self.chatProvider = chatProvider
    let settings = AssistantSettings.shared
    _isMonitoring = State(initialValue: ProactiveAssistantsPlugin.shared.isMonitoring)
    _isTranscribing = State(initialValue: appState.isTranscribing)
    _focusEnabled = State(initialValue: FocusAssistantSettings.shared.isEnabled)
    _cooldownInterval = State(initialValue: FocusAssistantSettings.shared.cooldownInterval)
    _glowOverlayEnabled = State(initialValue: settings.glowOverlayEnabled)
    _analysisDelay = State(initialValue: settings.analysisDelay)
    _focusNotificationsEnabled = State(
      initialValue: FocusAssistantSettings.shared.notificationsEnabled)
    _focusExcludedApps = State(initialValue: FocusAssistantSettings.shared.excludedApps)
    _taskEnabled = State(initialValue: TaskAssistantSettings.shared.isEnabled)
    _taskChatAgentEnabled = State(initialValue: TaskAgentSettings.shared.isChatEnabled)
    _taskAgentWorkingDirectory = State(initialValue: TaskAgentSettings.shared.workingDirectory)
    _taskExtractionInterval = State(initialValue: TaskAssistantSettings.shared.extractionInterval)
    _taskMinConfidence = State(initialValue: TaskAssistantSettings.shared.minConfidence)
    _taskNotificationsEnabled = State(
      initialValue: TaskAssistantSettings.shared.notificationsEnabled)
    _taskAllowedApps = State(initialValue: TaskAssistantSettings.shared.allowedApps)
    _taskBrowserKeywords = State(initialValue: TaskAssistantSettings.shared.browserKeywords)
    _insightEnabled = State(initialValue: InsightAssistantSettings.shared.isEnabled)
    _insightExtractionInterval = State(
      initialValue: InsightAssistantSettings.shared.extractionInterval)
    _insightMinConfidence = State(initialValue: InsightAssistantSettings.shared.minConfidence)
    _insightNotificationsEnabled = State(
      initialValue: InsightAssistantSettings.shared.notificationsEnabled)
    _insightExcludedApps = State(initialValue: InsightAssistantSettings.shared.excludedApps)
    _memoryEnabled = State(initialValue: MemoryAssistantSettings.shared.isEnabled)
    _memoryExtractionInterval = State(
      initialValue: MemoryAssistantSettings.shared.extractionInterval)
    _memoryMinConfidence = State(initialValue: MemoryAssistantSettings.shared.minConfidence)
    _memoryNotificationsEnabled = State(
      initialValue: MemoryAssistantSettings.shared.notificationsEnabled)
    _memoryExcludedApps = State(initialValue: MemoryAssistantSettings.shared.excludedApps)
    _vadGateEnabled = State(initialValue: settings.vadGateEnabled)
    _transcriptionLanguage = State(initialValue: settings.transcriptionLanguage)
    _transcriptionAutoDetect = State(initialValue: settings.transcriptionAutoDetect)
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
        case .planUsage:
          planUsageSection
        case .aiChat:
          aiChatSection
        case .floatingBar:
          floatingBarSection
        case .shortcuts:
          shortcutsSection
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
      if selectedSection == .aiChat {
        selectedSection = .advanced
      }
      loadBackendSettings()
      loadSubscriptionInfo()
      // Sync transcription state with appState
      isTranscribing = appState.isTranscribing
      // Sync floating bar state with persisted preference (not transient visibility)
      showAskOmiBar = FloatingControlBarManager.shared.isEnabled
      playwrightExtensionToken =
        UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
      chatProvider?.checkClaudeConnectionStatus()
      // Refresh notification permission state
      appState.checkNotificationPermission()
    }
    .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) {
      notification in
      if let userInfo = notification.userInfo, let state = userInfo["isMonitoring"] as? Bool {
        isMonitoring = state
      }
    }
    .onChange(of: appState.isTranscribing) { _, newValue in
      isTranscribing = newValue
    }
    .onChange(of: selectedSection) { _, newValue in
      if newValue == .aiChat {
        selectedSection = .advanced
        return
      }
      if newValue == .planUsage {
        loadSubscriptionInfo()
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .navigateToTaskSettings)) { _ in
      selectedSection = .advanced
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
        highlightedSettingId = "advanced.taskassistant"
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .navigateToFloatingBarSettings)) { _ in
      selectedSection = .floatingBar
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification))
    { _ in
      // Refresh notification permission when app becomes active (user may have changed it in System Settings)
      appState.checkNotificationPermission()
    }
    .sheet(item: $activeBillingWebFlow) { flow in
      BillingWebFlowSheet(flow: flow) { outcome in
        activeBillingWebFlow = nil
        handleBillingFlowCompletion(outcome)
      }
    }
    .sheet(isPresented: $showBrowserSetup) {
      BrowserExtensionSetup(
        onComplete: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        },
        onDismiss: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        },
        chatProvider: chatProvider
      )
      .fixedSize()
    }
  }

  // MARK: - General Section

  private var generalSection: some View {
    VStack(spacing: 20) {
      // Screen Capture toggle
      settingsCard(settingId: "general.screencapture") {
        HStack(spacing: 16) {
          Circle()
            .fill(isMonitoring ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
            .frame(width: 12, height: 12)
            .shadow(color: isMonitoring ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

          Image(systemName: "rectangle.dashed.badge.record")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.purplePrimary)

          VStack(alignment: .leading, spacing: 4) {
            Text("Screen Capture")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              permissionError
                ?? (isMonitoring ? "Capturing screen content" : "Screen capture is paused")
            )
            .scaledFont(size: 13)
            .foregroundColor(permissionError != nil ? OmiColors.warning : OmiColors.textTertiary)
          }

          Spacer()

          if isToggling {
            ProgressView()
              .scaleEffect(0.8)
          } else {
            Toggle(
              "",
              isOn: Binding(
                get: { isMonitoring },
                set: { newValue in
                  isMonitoring = newValue
                  toggleMonitoring(enabled: newValue)
                }
              )
            )
            .toggleStyle(.switch)
            .labelsHidden()
          }
        }
      }

      // Audio Recording toggle
      settingsCard(settingId: "general.audiorecording") {
        HStack(spacing: 16) {
          Circle()
            .fill(isTranscribing ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
            .frame(width: 12, height: 12)
            .shadow(color: isTranscribing ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

          Image(systemName: "mic.fill")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.purplePrimary)

          VStack(alignment: .leading, spacing: 4) {
            Text("Audio Recording")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(
              transcriptionError
                ?? (isTranscribing
                  ? "Recording and transcribing audio" : "Audio recording is paused")
            )
            .scaledFont(size: 13)
            .foregroundColor(transcriptionError != nil ? OmiColors.warning : OmiColors.textTertiary)
          }

          Spacer()

          if isTogglingTranscription {
            ProgressView()
              .scaleEffect(0.8)
          } else {
            Toggle(
              "",
              isOn: Binding(
                get: { isTranscribing },
                set: { newValue in
                  isTranscribing = newValue
                  toggleTranscription(enabled: newValue)
                }
              )
            )
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
              .fill(
                appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                  ? OmiColors.success
                  : (appState.isNotificationBannerDisabled
                    ? OmiColors.warning : OmiColors.textTertiary.opacity(0.3))
              )
              .frame(width: 12, height: 12)
              .shadow(
                color: appState.hasNotificationPermission && !appState.isNotificationBannerDisabled
                  ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

            VStack(alignment: .leading, spacing: 4) {
              Text("Notifications")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(notificationStatusText)
                .scaledFont(size: 13)
                .foregroundColor(
                  appState.isNotificationBannerDisabled ? OmiColors.warning : OmiColors.textTertiary
                )
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
                      .fill(
                        appState.isNotificationBannerDisabled
                          ? OmiColors.warning : OmiColors.purplePrimary)
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

              Text(
                "Banners disabled - you won't see visual alerts. Set style to \"Banners\" in System Settings."
              )
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

              Text(
                "Pause text recognition on battery to save energy. OCR runs automatically when plugged back in."
              )
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
                .foregroundColor(
                  transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

              VStack(alignment: .leading, spacing: 6) {
                Text("Auto-Detect (Multi-Language)")
                  .scaledFont(size: 14, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)

                Text("Automatically detects and transcribes:")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)

                // List of supported languages
                Text(
                  "English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch"
                )
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
                    .stroke(
                      transcriptionAutoDetect
                        ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary,
                      lineWidth: 1)
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
                .foregroundColor(
                  !transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

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
                      let supportsMulti = AssistantSettings.supportsAutoDetect(newValue)
                      transcriptionAutoDetect = supportsMulti
                      AssistantSettings.shared.transcriptionAutoDetect = supportsMulti
                      updateTranscriptionPreferences(singleLanguageMode: !supportsMulti)
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
                    .stroke(
                      !transcriptionAutoDetect
                        ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary,
                      lineWidth: 1)
                )
            )
          }
          .buttonStyle(.plain)

          // Info about language support
          HStack(spacing: 8) {
            Image(systemName: "info.circle")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)

            Text(
              "Single language mode supports 42 languages including Ukrainian, Russian, and more."
            )
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
                .foregroundColor(
                  newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty
                    ? OmiColors.textTertiary : OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
            .disabled(newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty)
          }

          Text("Press Enter or click + to add • Click × to remove")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      // Local VAD Gate
      settingsCard(settingId: "transcription.vadgate") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "waveform.badge.minus")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Local VAD Gate")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text(
                "Uses on-device voice activity detection to skip silence, reducing Deepgram API usage. May save ~40% on transcription costs."
              )
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Toggle("", isOn: $vadGateEnabled)
              .toggleStyle(.switch)
              .onChange(of: vadGateEnabled) { _, newValue in
                AssistantSettings.shared.vadGateEnabled = newValue
                restartTranscriptionIfNeeded()
              }
          }
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

            settingRow(
              title: "Frequency", subtitle: "How often to receive notifications",
              settingId: "notifications.frequency"
            ) {
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

            settingRow(
              title: "Focus Notifications", subtitle: "Show notification on focus changes",
              settingId: "notifications.focus"
            ) {
              Toggle("", isOn: $focusNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: focusNotificationsEnabled) { _, newValue in
                  FocusAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      focus: FocusSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Task Notifications", subtitle: "Show notification when a task is extracted",
              settingId: "notifications.task"
            ) {
              Toggle("", isOn: $taskNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: taskNotificationsEnabled) { _, newValue in
                  TaskAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      task: TaskSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Insight Notifications",
              subtitle: "Show notification when an insight is generated",
              settingId: "notifications.insight"
            ) {
              Toggle("", isOn: $insightNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: insightNotificationsEnabled) { _, newValue in
                  InsightAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      insight: InsightSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Memory Notifications",
              subtitle: "Show notification when a memory is extracted",
              settingId: "notifications.memory"
            ) {
              Toggle("", isOn: $memoryNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: memoryNotificationsEnabled) { _, newValue in
                  MemoryAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      memory: MemorySettingsResponse(notificationsEnabled: newValue)))
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

            settingRow(
              title: "Summary Time", subtitle: "When to send your daily summary",
              settingId: "notifications.summarytime"
            ) {
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
    VStack(spacing: 20) {
      // Data Controls
      settingsCard(settingId: "privacy.storerecordings") {
        VStack(alignment: .leading, spacing: 16) {
          Text("Data Controls")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          privacyToggleRow(
            icon: "mic.fill",
            title: "Store Recordings",
            subtitle: "Allow omi to store audio recordings of your conversations",
            isOn: $recordingPermissionEnabled
          ) { newValue in
            updateRecordingPermission(newValue)
          }

          Divider()

          privacyToggleRow(
            icon: "cloud.fill",
            title: "Private Cloud Sync",
            subtitle: "Sync your data securely to your private cloud storage",
            isOn: $privateCloudSyncEnabled
          ) { newValue in
            updatePrivateCloudSync(newValue)
          }
        }
      }

      // Encryption
      settingsCard(settingId: "privacy.encryption") {
        VStack(alignment: .leading, spacing: 14) {
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
              .frame(width: 20, alignment: .leading)

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

          Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      // What We Track
      settingsCard(settingId: "privacy.tracking") {
        VStack(alignment: .leading, spacing: 12) {
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
        }
      }
    }
  }

  // MARK: - Account Section

  private var accountSection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "account.account") {
        VStack(alignment: .leading, spacing: 14) {
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
            .disabled(isDeletingAccount)
          }

          Divider()
            .overlay(OmiColors.backgroundQuaternary)

          HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
              Text("Delete Account & Data")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.error)

              Text(
                "Permanently deletes server data, clears local data for this account, resets onboarding, and signs you out."
              )
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Button(action: {
              AnalyticsManager.shared.deleteAccountClicked()
              showDeleteAccountAlert = true
            }) {
              if isDeletingAccount {
                ProgressView()
                  .controlSize(.small)
              } else {
                Text("Delete")
                  .scaledFont(size: 13, weight: .semibold)
              }
            }
            .buttonStyle(.borderedProminent)
            .tint(OmiColors.error)
            .disabled(isDeletingAccount)
          }

          if let deleteAccountError {
            Text(deleteAccountError)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
          }
        }
      }
      .alert("Delete Account and Data?", isPresented: $showDeleteAccountAlert) {
        Button("Cancel", role: .cancel) {
          AnalyticsManager.shared.deleteAccountCancelled()
        }
        Button("Delete Permanently", role: .destructive) {
          deleteAccountAndData()
        }
      } message: {
        Text(
          "This cannot be undone. Your account, chat history, and all server data will be permanently deleted. Local data for this account will be cleared and you'll return to onboarding."
        )
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

  // MARK: - Plan and Usage Section

  private var planUsageSection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "planusage.current") {
        VStack(alignment: .leading, spacing: 14) {
          HStack(spacing: 16) {
            Image(systemName: "creditcard.fill")
              .scaledFont(size: 28)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text(currentPlanTitle)
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(currentPlanSubtitle)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if isLoadingSubscription {
              ProgressView()
                .controlSize(.small)
            } else if hasPaidSubscription {
              Button(action: openCustomerPortal) {
                if isOpeningCustomerPortal {
                  ProgressView()
                    .controlSize(.small)
                } else {
                  Text("Manage")
                    .scaledFont(size: 13, weight: .semibold)
                }
              }
              .buttonStyle(.bordered)
              .disabled(isOpeningCustomerPortal)
            } else {
              Button("Refresh") {
                loadSubscriptionInfo()
              }
              .buttonStyle(.bordered)
              .disabled(isLoadingSubscription)
            }
          }

          if let periodText = currentPlanPeriodText {
            Divider()
              .overlay(OmiColors.backgroundQuaternary)

            Text(periodText)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textSecondary)
          }

          if let error = subscriptionError {
            Text(error)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
          }
        }
      }

      if let subscription = userSubscription?.subscription,
        subscription.deprecated == true
      {
        settingsCard(settingId: "planusage.deprecation") {
          VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
              Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(OmiColors.warning)
                .scaledFont(size: 16)
              Text("Plan Retiring")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
            }

            Text(
              subscription.deprecationMessage
                ?? "Your Unlimited plan is being retired. Try the new Operator plan — same great features at $49/mo."
            )
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)

            Button(action: {
              selectedPlanIdForCheckout = "operator"
            }) {
              Text("Try Operator")
                .scaledFont(size: 13, weight: .semibold)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .buttonStyle(.borderedProminent)
            .tint(OmiColors.success)
          }
        }
      }

      if shouldShowPlanPurchaseOptions {
        settingsCard(settingId: "planusage.purchase") {
          VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
              Text("Choose a plan")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text("Pick one plan first. Billing options appear only after the card is selected.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }

            ScrollView(.horizontal, showsIndicators: false) {
              HStack(alignment: .top, spacing: 14) {
                ForEach(subscriptionPlansForDisplay) { plan in
                  subscriptionPlanCard(plan)
                    .frame(minWidth: 220)
                }
              }
            }
          }
        }
      }

      chatUsageQuotaCard

      overageCard

      byokPromoCard
    }
    .sheet(isPresented: $showOverageExplainer) {
      overageExplainerSheet
    }
  }

  @ViewBuilder
  private var overageCard: some View {
    if let info = overageInfo, info.isOveragePlan {
      settingsCard(settingId: "planusage.overage") {
        VStack(alignment: .leading, spacing: 10) {
          HStack(spacing: 10) {
            Image(systemName: info.excessQuestions > 0
              ? "dollarsign.circle.fill"
              : "checkmark.circle.fill")
              .scaledFont(size: 18)
              .foregroundColor(info.excessQuestions > 0
                ? OmiColors.warning
                : OmiColors.success)
            Text(info.excessQuestions > 0
              ? "Usage-based overage"
              : "No overage yet this cycle")
              .scaledFont(size: 14, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Spacer()
            if info.excessQuestions > 0 {
              Text(String(format: "$%.2f", info.overageUsd))
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.warning)
                .monospacedDigit()
            }
          }

          if info.excessQuestions > 0 {
            Text(
              "You've gone \(info.excessQuestions) question\(info.excessQuestions == 1 ? "" : "s") past your plan's \(info.includedQuestions ?? 0) included. We'll bill the overage at end of your cycle."
            )
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
          } else {
            Text(
              "Go over your \(info.includedQuestions ?? 0) included questions and we'll charge real provider cost + \(Int(info.markupPercent))%. No hard cutoff."
            )
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
          }

          Button(action: { showOverageExplainer = true }) {
            HStack(spacing: 4) {
              Text(info.explainerTitle)
                .scaledFont(size: 12, weight: .medium)
              Image(systemName: "info.circle")
                .scaledFont(size: 11)
            }
            .foregroundColor(OmiColors.purplePrimary)
          }
          .buttonStyle(.plain)
        }
      }
    } else if isLoadingOverage && overageInfo == nil {
      // silent while loading — nothing to show
      EmptyView()
    }
  }

  private var overageExplainerSheet: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        HStack {
          Text(overageInfo?.explainerTitle ?? "How overage billing works")
            .scaledFont(size: 18, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Spacer()
          Button(action: { showOverageExplainer = false }) {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: 20)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        Text(overageInfo?.explainerBody ?? "")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
          .fixedSize(horizontal: false, vertical: true)

        if let info = overageInfo, info.isOveragePlan {
          Divider().overlay(OmiColors.backgroundQuaternary)
          VStack(alignment: .leading, spacing: 8) {
            Text("Your current cycle")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            overageExplainerRow("Questions used", value: "\(info.usedQuestions)")
            overageExplainerRow("Included in plan", value: "\(info.includedQuestions ?? 0)")
            overageExplainerRow("Over the limit", value: "\(info.excessQuestions)")
            overageExplainerRow(
              "Real provider cost",
              value: String(format: "$%.2f", info.realCostUsd)
            )
            overageExplainerRow(
              "Markup",
              value: String(format: "%.0f%%", info.markupPercent)
            )
            overageExplainerRow(
              "Overage to bill",
              value: String(format: "$%.2f", info.overageUsd),
              emphasized: true
            )
          }
        }
      }
      .padding(24)
    }
    .frame(minWidth: 440, minHeight: 360)
  }

  private func overageExplainerRow(_ label: String, value: String, emphasized: Bool = false) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
      Spacer()
      Text(value)
        .scaledFont(size: 12, weight: emphasized ? .semibold : .regular)
        .foregroundColor(emphasized ? OmiColors.warning : OmiColors.textSecondary)
        .monospacedDigit()
    }
  }

  @ViewBuilder
  private var byokPromoCard: some View {
    settingsCard(settingId: "planusage.byok") {
      VStack(alignment: .leading, spacing: 12) {
        HStack(spacing: 12) {
          Image(systemName: "key.fill")
            .scaledFont(size: 20)
            .foregroundColor(OmiColors.purplePrimary)
          VStack(alignment: .leading, spacing: 2) {
            Text(APIKeyService.isByokActive ? "Free plan active" : "Use Omi free forever")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text(
              APIKeyService.isByokActive
                ? "You're using your own OpenAI, Anthropic, Gemini, and Deepgram keys. No subscription."
                : "Provide your own OpenAI, Anthropic, Gemini, and Deepgram keys to skip the subscription entirely."
            )
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
        }

        Button(action: openBYOKSettings) {
          Text(APIKeyService.isByokActive ? "Manage your keys" : "Switch to your own keys")
            .scaledFont(size: 13, weight: .semibold)
        }
        .buttonStyle(.bordered)
      }
    }
  }

  private func openBYOKSettings() {
    selectedSection = .advanced
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
      highlightedSettingId = "advanced.devkeys.info"
    }
  }

  // MARK: - Chat Usage Quota Card

  @ViewBuilder
  private var chatUsageQuotaCard: some View {
    if let quota = chatUsageQuota {
      settingsCard(settingId: "planusage.current") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Text("Usage this month")
              .scaledFont(size: 14, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Spacer()
            Text(chatUsageQuotaValueText(quota))
              .scaledFont(size: 13, weight: .medium)
              .foregroundColor(chatUsageBarColor(quota))
              .monospacedDigit()
          }

          ProgressView(value: min(quota.percent / 100.0, 1.0))
            .progressViewStyle(LinearProgressViewStyle(tint: chatUsageBarColor(quota)))
            .frame(height: 6)

          HStack {
            Text(chatUsageQuotaDescription(quota))
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
            Spacer()
            if let resetText = chatUsageQuotaResetText(quota) {
              Text(resetText)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if !quota.allowed {
            // Neo / overage-enabled plans keep working past the cap (extra
            // usage accrues as overage). Show a softer message on those plans;
            // only show the hard "upgrade" copy on Free and other hard-capped
            // plans.
            if let info = overageInfo, info.isOveragePlan {
              Text("You're past your included limit — extra usage is billed as overage at end of cycle.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.warning)
            } else {
              Text("You've reached this month's limit. Upgrade your plan or wait until the next reset.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.warning)
            }
          } else if quota.percent >= 80.0 {
            Text("You're close to your monthly limit.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
          }
        }
      }
    } else if isLoadingChatUsage {
      settingsCard(settingId: "planusage.current") {
        HStack {
          ProgressView().controlSize(.small)
          Text("Loading usage…")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
    }
  }

  private func chatUsageQuotaValueText(_ q: APIClient.ChatUsageQuota) -> String {
    if q.unit == "cost_usd" {
      let limit = q.limit.map { String(format: "$%.0f", $0) } ?? "—"
      return String(format: "$%.2f / %@", q.used, limit)
    }
    let used = Int(q.used)
    let limit = q.limit.map { "\(Int($0))" } ?? "∞"
    return "\(used) / \(limit)"
  }

  private func chatUsageQuotaDescription(_ q: APIClient.ChatUsageQuota) -> String {
    if q.unit == "cost_usd" {
      return "Chat spend on \(q.plan) plan"
    }
    return "Chat questions on \(q.plan) plan"
  }

  private func chatUsageQuotaResetText(_ q: APIClient.ChatUsageQuota) -> String? {
    guard let resetAt = q.resetAt else { return nil }
    let resetDate = Date(timeIntervalSince1970: TimeInterval(resetAt))
    let now = Date()
    let days = max(0, Int(resetDate.timeIntervalSince(now) / 86400))
    if days <= 0 {
      return "Resets today"
    }
    if days == 1 {
      return "Resets tomorrow"
    }
    return "Resets in \(days) days"
  }

  private func chatUsageBarColor(_ q: APIClient.ChatUsageQuota) -> Color {
    if !q.allowed || q.percent >= 100.0 { return OmiColors.warning }
    if q.percent >= 80.0 { return OmiColors.warning }
    return OmiColors.purplePrimary
  }

  // MARK: - AI Chat Section

  private var floatingBarSection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "floatingbar.show") {
        HStack(spacing: 16) {
          Circle()
            .fill(showAskOmiBar ? OmiColors.success : OmiColors.textTertiary.opacity(0.3))
            .frame(width: 12, height: 12)
            .shadow(color: showAskOmiBar ? OmiColors.success.opacity(0.5) : .clear, radius: 6)

          Text("Show floating bar")
            .scaledFont(size: 16, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

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

      settingsCard(settingId: "floatingbar.background") {
        VStack(alignment: .leading, spacing: 16) {
          Text("Background Style")
            .scaledFont(size: 16, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          HStack(spacing: 16) {
            Text("Transparent")
              .scaledFont(size: 13, weight: shortcutSettings.solidBackground ? .regular : .semibold)
              .foregroundColor(
                shortcutSettings.solidBackground ? OmiColors.textTertiary : OmiColors.textPrimary)

            Toggle("", isOn: $shortcutSettings.solidBackground)
              .toggleStyle(.switch)
              .tint(OmiColors.purplePrimary)
              .labelsHidden()

            Text("Solid Dark")
              .scaledFont(size: 13, weight: shortcutSettings.solidBackground ? .semibold : .regular)
              .foregroundColor(
                shortcutSettings.solidBackground ? OmiColors.textPrimary : OmiColors.textTertiary)

            Spacer()
          }
        }
      }

      settingsCard(settingId: "floatingbar.draggable") {
        HStack(spacing: 16) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Draggable Floating Bar")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Allow repositioning the floating bar by dragging it.")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: $shortcutSettings.draggableBarEnabled)
            .toggleStyle(.switch)
            .tint(OmiColors.purplePrimary)
        }
      }

      settingsCard(settingId: "floatingbar.voiceanswers") {
        HStack(spacing: 16) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Voice Questions")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Speak answers aloud when you ask with push to talk.")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: floatingBarVoiceAnswersBinding)
            .toggleStyle(.switch)
            .tint(OmiColors.purplePrimary)
        }
      }

      settingsCard(settingId: "floatingbar.typedvoiceanswers") {
        HStack(spacing: 16) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Typed Questions")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Speak answers aloud when you submit a typed question from the floating bar.")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Toggle("", isOn: floatingBarTypedVoiceAnswersBinding)
            .toggleStyle(.switch)
            .tint(OmiColors.purplePrimary)
        }
      }

      voicePicker(settingId: "floatingbar.voice")
        .opacity(shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled ? 1 : 0.55)
        .disabled(!shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled)

      voiceSpeedSlider(settingId: "floatingbar.voicespeed")
        .opacity(shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled ? 1 : 0.55)
        .disabled(!shortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled)
    }
  }

  private func voicePicker(settingId: String) -> some View {
    settingsCard(settingId: settingId) {
      HStack(spacing: 16) {
        VStack(alignment: .leading, spacing: 4) {
          Text("Voice")
            .scaledFont(size: 16, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(
            ShortcutSettings.voiceOption(for: shortcutSettings.selectedVoiceID).description
          )
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
        }
        Spacer()
        Picker("", selection: $shortcutSettings.selectedVoiceID) {
          Section("Female") {
            ForEach(ShortcutSettings.availableVoices.filter { $0.gender == .female }) { voice in
              Text(voice.name).tag(voice.id)
            }
          }
          Section("Male") {
            ForEach(ShortcutSettings.availableVoices.filter { $0.gender == .male }) { voice in
              Text(voice.name).tag(voice.id)
            }
          }
        }
        .pickerStyle(.menu)
        .labelsHidden()
        .frame(width: 180)
        .tint(OmiColors.purplePrimary)
      }
    }
  }

  private var shortcutsSection: some View {
    ShortcutsSettingsSection(highlightedSettingId: $highlightedSettingId)
  }

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
              ForEach(AIProvider.all) { provider in
                Text(provider.displayName).tag(provider.bridgeModeRawValue)
              }
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

          if let provider = AIProvider.from(bridgeMode: chatBridgeMode) {
            if let url = provider.attributionURL {
              Link(destination: url) {
                Text("\(provider.tagline) · \(url.host ?? "")")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }
            } else {
              Text(provider.tagline)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if chatBridgeMode == "claudeCode" && chatProvider?.isClaudeConnected == true {
            Divider()

            HStack {
              Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .scaledFont(size: 12)
              Text("Connected to Claude")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)

              Spacer()

              Button("Disconnect") {
                Task {
                  await chatProvider?.disconnectClaude()
                }
              }
              .buttonStyle(.plain)
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(.red)
            }
          }
        }
      }
      .onAppear {
        chatProvider?.checkClaudeConnectionStatus()
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

          Text(
            "When enabled, shows an Ask/Act toggle in the chat. Ask mode restricts the AI to read-only actions. When disabled, the AI always runs in Act mode."
          )
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
            Text(
              "No workspace set. Set a project directory to discover project-level CLAUDE.md and skills."
            )
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
              Text(
                "Skills (\(aiChatDiscoveredSkills.count) global + \(aiChatProjectDiscoveredSkills.count) project)"
              )
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

          let allSkills:
            [(skill: (name: String, description: String, path: String), origin: String)] =
              aiChatDiscoveredSkills.map { ($0, "Global") }
              + aiChatProjectDiscoveredSkills.map { ($0, "Project") }

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
                skillSearchQuery.isEmpty
                  || item.skill.name.localizedCaseInsensitiveContains(skillSearchQuery)
                  || item.skill.description.localizedCaseInsensitiveContains(skillSearchQuery)
              }

              VStack(spacing: 0) {
                ForEach(Array(filteredSkills.enumerated()), id: \.offset) { filteredIndex, item in
                  let skill = item.element.skill
                  let origin = item.element.origin
                  HStack(spacing: 10) {
                    Toggle(
                      "",
                      isOn: Binding(
                        get: { !aiChatDisabledSkills.contains(skill.name) },
                        set: { enabled in
                          if enabled {
                            aiChatDisabledSkills.remove(skill.name)
                          } else {
                            aiChatDisabledSkills.insert(skill.name)
                          }
                          saveDisabledSkills()
                        }
                      )
                    )
                    .toggleStyle(.checkbox)
                    .labelsHidden()

                    VStack(alignment: .leading, spacing: 2) {
                      HStack(spacing: 6) {
                        Text(skill.name)
                          .scaledFont(size: 13, weight: .medium)
                          .foregroundColor(OmiColors.textPrimary)

                        Text(origin)
                          .scaledFont(size: 9, weight: .medium)
                          .foregroundColor(
                            origin == "Project" ? OmiColors.purplePrimary : OmiColors.textTertiary
                          )
                          .padding(.horizontal, 4)
                          .padding(.vertical, 1)
                          .background(
                            RoundedRectangle(cornerRadius: 3)
                              .fill(
                                origin == "Project"
                                  ? OmiColors.purplePrimary.opacity(0.1)
                                  : OmiColors.backgroundPrimary.opacity(0.5))
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
                      fileViewerContent =
                        (try? String(contentsOfFile: skill.path, encoding: .utf8))
                        ?? "Unable to read file"
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
              .onChange(of: devModeEnabled) { _, newValue in
                AnalyticsManager.shared.settingToggled(setting: "dev_mode", enabled: newValue)
              }
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
      playwrightExtensionToken =
        UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
    }
    .sheet(isPresented: $showFileViewer) {
      fileViewerSheet
    }
    .sheet(isPresented: $showBrowserSetup) {
      BrowserExtensionSetup(
        onComplete: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
        },
        onDismiss: {
          showBrowserSetup = false
          playwrightExtensionToken =
            UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
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
    // Pull skill and CLAUDE.md data directly from ChatProvider (already discovered at startup).
    // Fall back to reading from disk only when ChatProvider is unavailable.
    if let provider = chatProvider {
      aiChatClaudeMdContent = provider.claudeMdContent
      aiChatClaudeMdPath = provider.claudeMdPath
      aiChatDiscoveredSkills = provider.discoveredSkills
      aiChatProjectClaudeMdContent = provider.projectClaudeMdContent
      aiChatProjectClaudeMdPath = provider.projectClaudeMdPath
      aiChatProjectDiscoveredSkills = provider.projectDiscoveredSkills
      loadDisabledSkills()
      return
    }

    // Fallback: read from disk (used when Settings is shown before ChatProvider initializes)
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let claudeDir = "\(home)/.claude"

    let mdPath = "\(claudeDir)/CLAUDE.md"
    if FileManager.default.fileExists(atPath: mdPath),
      let content = try? String(contentsOfFile: mdPath, encoding: .utf8)
    {
      aiChatClaudeMdContent = content
      aiChatClaudeMdPath = mdPath
    } else {
      aiChatClaudeMdContent = nil
      aiChatClaudeMdPath = nil
    }

    var skills: [(name: String, description: String, path: String)] = []
    let skillsDir = "\(claudeDir)/skills"
    if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: skillsDir) {
      for dir in skillDirs.sorted() {
        let skillPath = "\(skillsDir)/\(dir)/SKILL.md"
        if FileManager.default.fileExists(atPath: skillPath),
          let content = try? String(contentsOfFile: skillPath, encoding: .utf8)
        {
          let desc = ChatProvider.extractSkillDescription(from: content)
          skills.append((name: dir, description: desc, path: skillPath))
        }
      }
    }
    aiChatDiscoveredSkills = skills

    let workspace = aiChatWorkingDirectory
    if !workspace.isEmpty, FileManager.default.fileExists(atPath: workspace) {
      let projectMdPath = "\(workspace)/CLAUDE.md"
      if FileManager.default.fileExists(atPath: projectMdPath),
        let content = try? String(contentsOfFile: projectMdPath, encoding: .utf8)
      {
        aiChatProjectClaudeMdContent = content
        aiChatProjectClaudeMdPath = projectMdPath
      } else {
        aiChatProjectClaudeMdContent = nil
        aiChatProjectClaudeMdPath = nil
      }

      var projectSkills: [(name: String, description: String, path: String)] = []
      let projectSkillsDir = "\(workspace)/.claude/skills"
      if let skillDirs = try? FileManager.default.contentsOfDirectory(atPath: projectSkillsDir) {
        for dir in skillDirs.sorted() {
          let skillPath = "\(projectSkillsDir)/\(dir)/SKILL.md"
          if FileManager.default.fileExists(atPath: skillPath),
            let content = try? String(contentsOfFile: skillPath, encoding: .utf8)
          {
            let desc = ChatProvider.extractSkillDescription(from: content)
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

    loadDisabledSkills()
  }

  private func loadDisabledSkills() {
    let json = UserDefaults.standard.string(forKey: "disabledSkillsJSON") ?? ""
    guard let data = json.data(using: .utf8),
      let names = try? JSONDecoder().decode([String].self, from: data)
    else {
      aiChatDisabledSkills = []  // Default: nothing disabled = all enabled
      return
    }
    aiChatDisabledSkills = Set(names)
  }

  private func saveDisabledSkills() {
    if let data = try? JSONEncoder().encode(Array(aiChatDisabledSkills)),
      let json = String(data: data, encoding: .utf8)
    {
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

  private func advancedCategoryHeader(title: String, icon: String) -> some View {
    HStack(spacing: 10) {
      Image(systemName: icon)
        .scaledFont(size: 16)
        .foregroundColor(OmiColors.purplePrimary)
      Text(title)
        .scaledFont(size: 18, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Spacer()
    }
    .padding(.top, 16)
  }

  private var advancedSection: some View {
    VStack(spacing: 24) {
      advancedCategoryHeader(title: "AI Setup", icon: "cpu")
      aiSetupSubsection
      advancedCategoryHeader(title: "Profile & Stats", icon: "brain")
      profileAndStatsSubsection
      advancedCategoryHeader(title: "Reset Onboarding", icon: "arrow.counterclockwise")
      resetOnboardingSubsection
      advancedCategoryHeader(title: "Goals", icon: "target")
      goalsSubsection
      advancedCategoryHeader(title: "Preferences", icon: "slider.horizontal.3")
      preferencesSubsection
      advancedCategoryHeader(title: "Troubleshooting", icon: "wrench.and.screwdriver")
      troubleshootingSubsection
      advancedCategoryHeader(title: "Developer API Keys", icon: "key")
      developerKeysSubsection

      advancedCategoryHeader(title: "Dev Tools", icon: "hammer")
      devToolsSubsection
    }
  }

  // MARK: - Dev Tools Subsection

  private var devToolsSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.devtools.chatlab") {
        HStack(spacing: 12) {
          Image(systemName: "flask.fill")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.purplePrimary)
          VStack(alignment: .leading, spacing: 4) {
            Text("Chat Prompt Lab")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Iterate on chat system prompts with real questions, AI grading, and production ratings")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Button("Open") {
            ChatLabWindowManager.shared.openWindow(chatProvider: chatProvider)
          }
          .buttonStyle(.plain)
          .padding(.horizontal, 14)
          .padding(.vertical, 6)
          .background(OmiColors.purplePrimary)
          .foregroundColor(.white)
          .clipShape(RoundedRectangle(cornerRadius: 8))
        }
      }
    }
  }

  // MARK: - Advanced Subsections

  private var aiSetupSubsection: some View {
    VStack(spacing: 20) {
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
              ForEach(AIProvider.all) { provider in
                Text(provider.displayName).tag(provider.bridgeModeRawValue)
              }
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

          if let provider = AIProvider.from(bridgeMode: chatBridgeMode) {
            if let url = provider.attributionURL {
              Link(destination: url) {
                Text("\(provider.tagline) · \(url.host ?? "")")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }
            } else {
              Text(provider.tagline)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if chatBridgeMode == "claudeCode" && chatProvider?.isClaudeConnected == true {
            Divider()

            HStack {
              Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .scaledFont(size: 12)
              Text("Connected to Claude")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)

              Spacer()

              Button("Disconnect") {
                Task {
                  await chatProvider?.disconnectClaude()
                }
              }
              .buttonStyle(.plain)
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(.red)
            }
          }
        }
      }

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
          } else {
            Text("No workspace set. Choose a project directory for desktop chat context.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }

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
          }

          Text("Lets the AI use your Chrome browser with all your logged-in sessions.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)

          if playwrightUseExtension {
            if playwrightExtensionToken.isEmpty {
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
              .onChange(of: devModeEnabled) { _, newValue in
                AnalyticsManager.shared.settingToggled(setting: "dev_mode", enabled: newValue)
              }
          }

          Text("Let the AI modify the app's source code, rebuild it, and add custom features.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
    }
  }

  private var profileAndStatsSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.profileandstats") {
        VStack(alignment: .leading, spacing: 12) {
          HStack(spacing: 12) {
            Image(systemName: showProfileAndStats ? "eye.slash" : "eye")
              .scaledFont(size: 15)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Profile and Stats")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
              Text("Keep the generated profile and usage stats hidden until you need them.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Button(showProfileAndStats ? "Hide" : "Show") {
              withAnimation(.easeInOut(duration: 0.2)) {
                showProfileAndStats.toggle()
              }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
          }
        }
      }

      if showProfileAndStats {
        aiUserProfileSubsection
        statsSubsection
      }
    }
  }

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
            Text(
              "Your AI user profile will be generated automatically on next launch, or click \"Generate Now\" to create it now."
            )
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
            tierPickerRow(
              tier: 5, label: "Tier 5", subtitle: "+ Home (200 convos + 2K screenshots)")
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
              tier: 5, name: "Home",
              requirement: "200 conversations + 2K screenshots",
              progress: advancedStats.map {
                "\($0.conversations) / 200 convos, \($0.screenshotsTotal) / 2,000 screenshots"
              },
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
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(focus: FocusSettingsResponse(enabled: newValue)))
              }
          }

          Text("Detect distractions and help you stay focused")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          if focusEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            settingRow(
              title: "Visual Glow Effect", subtitle: "Show colored border when focus changes",
              settingId: "advanced.focusassistant.glow"
            ) {
              Toggle("", isOn: $glowOverlayEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .disabled(isPreviewRunning)
                .onChange(of: glowOverlayEnabled) { _, newValue in
                  AssistantSettings.shared.glowOverlayEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      shared: SharedAssistantSettingsResponse(glowOverlayEnabled: newValue)))
                  if newValue {
                    startGlowPreview()
                  }
                }
            }

            settingRow(
              title: "Focus Cooldown", subtitle: "Minimum time between distraction alerts",
              settingId: "advanced.focusassistant.cooldown"
            ) {
              Picker("", selection: $cooldownInterval) {
                ForEach(cooldownOptions, id: \.self) { minutes in
                  Text(formatMinutes(minutes)).tag(minutes)
                }
              }
              .pickerStyle(.menu)
              .frame(width: 120)
              .onChange(of: cooldownInterval) { _, newValue in
                FocusAssistantSettings.shared.cooldownInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    focus: FocusSettingsResponse(cooldownInterval: newValue)))
              }
            }

            settingRow(
              title: "Focus Analysis Prompt",
              subtitle: "Customize AI instructions for focus analysis",
              settingId: "advanced.focusassistant.prompt"
            ) {
              HStack(spacing: 8) {
                Button(action: {
                  FocusTestRunnerWindow.show()
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
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
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
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
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
          }  // end if focusEnabled
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
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(task: TaskSettingsResponse(enabled: newValue)))
              }
          }

          Text("Extract tasks and action items from your screen")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          if taskEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Task Agent (chat / investigate) toggle
            HStack {
              VStack(alignment: .leading, spacing: 2) {
                Text("Task Agent")
                  .scaledFont(size: 14)
                  .foregroundColor(OmiColors.textSecondary)
                Text("Investigate button and sidebar chat for tasks")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }

              Spacer()

              Toggle("", isOn: $taskChatAgentEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: taskChatAgentEnabled) { _, newValue in
                  TaskAgentSettings.shared.isChatEnabled = newValue
                }
            }

            // Working Directory (shared by chat agent and terminal agent)
            HStack(spacing: 8) {
              VStack(alignment: .leading, spacing: 2) {
                Text("Working Directory")
                  .scaledFont(size: 14)
                  .foregroundColor(OmiColors.textSecondary)
                Text(
                  taskAgentWorkingDirectory.isEmpty
                    ? "Not set — chat agent defaults to ~" : taskAgentWorkingDirectory
                )
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
                .truncationMode(.middle)
              }

              Spacer()

              Button("Browse...") {
                let panel = NSOpenPanel()
                panel.canChooseFiles = false
                panel.canChooseDirectories = true
                panel.allowsMultipleSelection = false
                panel.canCreateDirectories = true
                if !taskAgentWorkingDirectory.isEmpty {
                  panel.directoryURL = URL(fileURLWithPath: taskAgentWorkingDirectory)
                }
                if panel.runModal() == .OK, let url = panel.url {
                  taskAgentWorkingDirectory = url.path
                  TaskAgentSettings.shared.workingDirectory = url.path
                }
              }
              .scaledFont(size: 13)

              if !taskAgentWorkingDirectory.isEmpty {
                Button("Clear") {
                  taskAgentWorkingDirectory = ""
                  TaskAgentSettings.shared.workingDirectory = ""
                }
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
              }
            }

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

              Slider(
                value: Binding(
                  get: { Double(taskIntervalSliderIndex) },
                  set: { taskExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.purplePrimary)
              .onChange(of: taskExtractionInterval) { _, newValue in
                TaskAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    task: TaskSettingsResponse(extractionInterval: newValue)))
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
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(task: TaskSettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Task Extraction Prompt",
              subtitle: "Customize AI instructions for task extraction",
              settingId: "advanced.taskassistant.prompt"
            ) {
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
                Text(
                  "Tasks will only be extracted from these apps. Browsers are also filtered by keywords below."
                )
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
                Text(
                  "For browser apps, only analyze windows whose title contains one of these keywords."
                )
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
            settingRow(
              title: "Task Prioritization",
              subtitle: "Re-score all tasks by relevance to your profile and goals",
              settingId: "advanced.taskassistant.prioritization"
            ) {
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
          }  // end if taskEnabled
        }
      }

      // Task Agent Settings (merged into Task Assistant subsection)
      settingsCard(settingId: "advanced.taskassistant.agent") {
        TaskAgentSettingsView()
      }
    }
  }

  private var insightAssistantSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.insightassistant") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "lightbulb.fill")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Insight Assistant")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $insightEnabled)
              .toggleStyle(.switch)
              .labelsHidden()
              .onChange(of: insightEnabled) { _, newValue in
                InsightAssistantSettings.shared.isEnabled = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(insight: InsightSettingsResponse(enabled: newValue)))
              }
          }

          Text("Get proactive insights and suggestions")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          if insightEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            // Frequency Slider
            VStack(alignment: .leading, spacing: 8) {
              HStack {
                VStack(alignment: .leading, spacing: 2) {
                  Text("Frequency")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("How often to check for insight opportunities")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text(formatExtractionInterval(insightExtractionInterval))
                  .scaledFont(size: 13, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 80, alignment: .trailing)
              }

              Slider(
                value: Binding(
                  get: { Double(insightIntervalSliderIndex) },
                  set: { insightExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.purplePrimary)
              .onChange(of: insightExtractionInterval) { _, newValue in
                InsightAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    insight: InsightSettingsResponse(extractionInterval: newValue)))
              }
            }

            // Minimum Confidence Slider
            VStack(alignment: .leading, spacing: 8) {
              HStack {
                VStack(alignment: .leading, spacing: 2) {
                  Text("Minimum Confidence")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                  Text("Only show insights above this confidence level")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                Text("\(Int(insightMinConfidence * 100))%")
                  .scaledFont(size: 13, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 40, alignment: .trailing)
              }

              Slider(value: $insightMinConfidence, in: 0.5...0.95, step: 0.05)
                .tint(OmiColors.purplePrimary)
                .onChange(of: insightMinConfidence) { _, newValue in
                  InsightAssistantSettings.shared.minConfidence = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      insight: InsightSettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Insight Prompt", subtitle: "Customize AI instructions for insights",
              settingId: "advanced.insightassistant.prompt"
            ) {
              HStack(spacing: 8) {
                Button(action: {
                  InsightTestRunnerWindow.show()
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
                  InsightPromptEditorWindow.show()
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
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
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
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
              }
              .tint(OmiColors.textTertiary)

              if !insightExcludedApps.isEmpty {
                LazyVStack(spacing: 8) {
                  ForEach(Array(insightExcludedApps).sorted(), id: \.self) { appName in
                    ExcludedAppRow(
                      appName: appName,
                      onRemove: {
                        InsightAssistantSettings.shared.includeApp(appName)
                        insightExcludedApps = InsightAssistantSettings.shared.excludedApps
                      }
                    )
                  }
                }
              }

              AddExcludedAppView(
                onAdd: { appName in
                  InsightAssistantSettings.shared.excludeApp(appName)
                  insightExcludedApps = InsightAssistantSettings.shared.excludedApps
                },
                excludedApps: insightExcludedApps
              )
            }
          }  // end if insightEnabled
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
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(memory: MemorySettingsResponse(enabled: newValue)))
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

              Slider(
                value: Binding(
                  get: { Double(memoryIntervalSliderIndex) },
                  set: { memoryExtractionInterval = extractionIntervalOptions[Int($0)] }
                ), in: 0...Double(extractionIntervalOptions.count - 1), step: 1
              )
              .tint(OmiColors.purplePrimary)
              .onChange(of: memoryExtractionInterval) { _, newValue in
                MemoryAssistantSettings.shared.extractionInterval = newValue
                SettingsSyncManager.shared.pushPartialUpdate(
                  AssistantSettingsResponse(
                    memory: MemorySettingsResponse(extractionInterval: newValue)))
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
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      memory: MemorySettingsResponse(minConfidence: newValue)))
                }
            }

            settingRow(
              title: "Memory Extraction Prompt",
              subtitle: "Customize AI instructions for memory extraction",
              settingId: "advanced.memoryassistant.prompt"
            ) {
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
                  ForEach(Array(TaskAssistantSettings.builtInExcludedApps).sorted(), id: \.self) {
                    appName in
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
                Text(
                  "System apps always excluded (\(TaskAssistantSettings.builtInExcludedApps.count))"
                )
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
          }  // end if memoryEnabled
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

          Slider(
            value: Binding(
              get: { Double(analysisDelaySliderIndex) },
              set: { analysisDelay = analysisDelayOptions[Int($0)] }
            ), in: 0...Double(analysisDelayOptions.count - 1), step: 1
          )
          .tint(OmiColors.purplePrimary)
          .onChange(of: analysisDelay) { _, newValue in
            AssistantSettings.shared.analysisDelay = newValue
            SettingsSyncManager.shared.pushPartialUpdate(
              AssistantSettingsResponse(
                shared: SharedAssistantSettingsResponse(analysisDelay: newValue)))
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

          settingRow(
            title: "Auto-Generate Goals",
            subtitle: "Automatically suggest new goals daily based on your conversations and tasks",
            settingId: "advanced.goals.autogenerate"
          ) {
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

            Text(
              multiChatEnabled
                ? "Create separate chat threads"
                : "Single chat synced with mobile app"
            )
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Toggle("", isOn: $multiChatEnabled)
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

          Toggle(
            "",
            isOn: Binding(
              get: { launchAtLoginManager.isEnabled },
              set: { newValue in
                if launchAtLoginManager.setEnabled(newValue) {
                  AnalyticsManager.shared.launchAtLoginChanged(enabled: newValue, source: "user")
                }
              }
            )
          )
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
        Button("Cancel", role: .cancel) {}
        Button("Rescan") {
          NotificationCenter.default.post(name: .triggerFileIndexing, object: nil)
        }
      } message: {
        Text(
          "This will re-scan your files and update your AI profile with the latest information about your projects and interests."
        )
      }

    }
  }

  // MARK: - Reset Onboarding Subsection

  private var resetOnboardingSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.resetonboarding") {
        HStack(spacing: 16) {
          Image(systemName: "arrow.counterclockwise")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: 4) {
            Text("Reset Onboarding")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Restart setup wizard for this app build only")
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
        Button("Cancel", role: .cancel) {}
        Button("Reset & Restart", role: .destructive) {
          appState.resetOnboardingAndRestart()
        }
      } message: {
        Text(
          "This will reset onboarding for this app build only, clear onboarding chat history, and restart the app without affecting the other installed build."
        )
      }
    }
  }

  // MARK: - Gmail Reader Subsection

  private var gmailReaderSubsection: some View {
    VStack(spacing: 20) {
      // Read Gmail button
      settingsCard(settingId: "advanced.gmail.read") {
        HStack(spacing: 16) {
          Image(systemName: "envelope.badge")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: 4) {
            Text("Read Gmail")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            if let lastFetched = gmailLastFetched {
              Text("Last read \(lastFetched, formatter: relativeDateFormatter)")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            } else {
              Text("Reads recent emails using browser cookies — no OAuth needed")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          Spacer()

          Button(action: {
            Task { await readGmail() }
          }) {
            if isReadingGmail {
              ProgressView()
                .scaleEffect(0.7)
                .frame(width: 60, height: 22)
            } else {
              Text("Read Gmail")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(
                  RoundedRectangle(cornerRadius: 6)
                    .fill(OmiColors.purplePrimary)
                )
            }
          }
          .buttonStyle(.plain)
          .disabled(isReadingGmail)
        }
      }

      // Error card
      if let error = gmailReadError {
        settingsCard(settingId: "advanced.gmail.error") {
          HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
              .foregroundColor(.orange)
            Text(error)
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
              .lineLimit(3)
            Spacer()
          }
        }
      }

      // Memory save status
      if gmailMemoriesSaved > 0 {
        settingsCard(settingId: "advanced.gmail.saved") {
          HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
              .foregroundColor(.green)
            Text("\(gmailMemoriesSaved) emails saved as memories")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
            Spacer()
          }
        }
      }

      // Email list
      if !gmailEmails.isEmpty {
        VStack(spacing: 8) {
          ForEach(gmailEmails.prefix(20)) { email in
            settingsCard(settingId: "advanced.gmail.email.\(email.id)") {
              VStack(alignment: .leading, spacing: 4) {
                Text(email.subject)
                  .scaledFont(size: 14, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)
                  .lineLimit(1)

                Text(email.from)
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textSecondary)
                  .lineLimit(1)

                if !email.snippet.isEmpty {
                  Text(email.snippet)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .lineLimit(2)
                }
              }
            }
          }
        }
      }
    }
  }

  private func readGmail() async {
    isReadingGmail = true
    gmailReadError = nil
    gmailMemoriesSaved = 0

    do {
      let emails = try await GmailReaderService.shared.readRecentEmails(maxResults: 50)
      gmailEmails = emails
      gmailLastFetched = Date()

      if !emails.isEmpty {
        isSavingGmailMemories = true
        let result = await GmailReaderService.shared.saveAsMemories(emails: emails)
        gmailMemoriesSaved = result.saved
        isSavingGmailMemories = false
      }
    } catch {
      gmailReadError = error.localizedDescription
    }

    isReadingGmail = false
  }

  // MARK: - Calendar Sync Subsection

  private var calendarSyncSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.calendar.sync") {
        HStack(spacing: 16) {
          Image(systemName: "calendar.badge.clock")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)
          VStack(alignment: .leading, spacing: 4) {
            Text("Sync Calendar")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            if let lastSynced = calendarLastSynced {
              Text("Last synced \(lastSynced, formatter: relativeDateFormatter)")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            } else {
              Text("Reads Google Calendar using browser cookies — no OAuth needed")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }
          }
          Spacer()
          Button(action: { Task { await syncCalendar() } }) {
            if isReadingCalendar {
              ProgressView().scaleEffect(0.7).frame(width: 80, height: 22)
            } else {
              Text("Sync Calendar")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 6).fill(OmiColors.purplePrimary))
            }
          }
          .buttonStyle(.plain)
          .disabled(isReadingCalendar)
          .accessibilityIdentifier("syncCalendarButton")
        }
      }
      if let error = calendarSyncError {
        settingsCard(settingId: "advanced.calendar.error") {
          HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.orange)
            Text(error).scaledFont(size: 13).foregroundColor(OmiColors.textSecondary).lineLimit(3)
            Spacer()
          }
        }
      }
      if calendarMemoriesCreated > 0 || calendarTasksCreated > 0 {
        settingsCard(settingId: "advanced.calendar.saved") {
          HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
            Text(
              "\(calendarMemoriesCreated) memories and \(calendarTasksCreated) tasks created from \(calendarEvents.count) events"
            )
            .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
            Spacer()
          }
        }
      }
      if !calendarEvents.isEmpty {
        VStack(spacing: 8) {
          ForEach(calendarEvents.prefix(15)) { event in
            settingsCard(settingId: "advanced.calendar.event.\(event.id)") {
              VStack(alignment: .leading, spacing: 4) {
                Text(event.summary).scaledFont(size: 14, weight: .medium).foregroundColor(
                  OmiColors.textPrimary
                ).lineLimit(1)
                Text(event.startTime).scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
                  .lineLimit(1)
                if !event.attendees.isEmpty {
                  Text("With: \(event.attendees.prefix(3).joined(separator: ", "))").scaledFont(
                    size: 12
                  ).foregroundColor(OmiColors.textTertiary).lineLimit(1)
                }
              }
            }
          }
        }
      }
    }
  }

  private func syncCalendar() async {
    isReadingCalendar = true
    calendarSyncError = nil
    calendarMemoriesCreated = 0
    calendarTasksCreated = 0
    do {
      let events = try await CalendarReaderService.shared.readEvents(daysBack: 30, daysForward: 14)
      calendarEvents = events
      calendarLastSynced = Date()
      if !events.isEmpty {
        let result = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
        calendarMemoriesCreated = result.memories
        calendarTasksCreated = result.tasks
      }
    } catch {
      calendarSyncError = error.localizedDescription
    }
    isReadingCalendar = false
  }

  private var relativeDateFormatter: DateFormatter {
    let formatter = DateFormatter()
    formatter.doesRelativeDateFormatting = true
    formatter.dateStyle = .short
    formatter.timeStyle = .short
    return formatter
  }

  // MARK: - Developer API Keys Subsection

  private var developerKeysSubsection: some View {
    VStack(spacing: 20) {
      byokStatusBanner

      developerKeyField(
        provider: .openai,
        title: "OpenAI API Key",
        subtitle: "For GPT calls.",
        settingId: "advanced.devkeys.openai",
        value: $devOpenAIKey
      )

      developerKeyField(
        provider: .anthropic,
        title: "Anthropic API Key",
        subtitle: "For chat (Claude).",
        settingId: "advanced.devkeys.anthropic",
        value: $devAnthropicKey
      )

      developerKeyField(
        provider: .gemini,
        title: "Gemini API Key",
        subtitle: "For proactive AI (memory, tasks, insights, focus).",
        settingId: "advanced.devkeys.gemini",
        value: $devGeminiKey
      )

      developerKeyField(
        provider: .deepgram,
        title: "Deepgram API Key",
        subtitle: "For live transcription.",
        settingId: "advanced.devkeys.deepgram",
        value: $devDeepgramKey
      )

      if let byokActivationError {
        settingsCard(settingId: "advanced.devkeys.error") {
          HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
              .foregroundColor(OmiColors.warning)
            Text(byokActivationError)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
          }
        }
      }

      if hasAnyBYOKKey {
        settingsCard(settingId: "advanced.devkeys.clear") {
          HStack {
            Spacer()
            Button(action: clearAllBYOKKeys) {
              Text("Clear All Custom Keys")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.red)
            }
            .buttonStyle(.plain)
            Spacer()
          }
        }
      }
    }
    .onChange(of: devOpenAIKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devAnthropicKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devGeminiKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devDeepgramKey) { _, _ in refreshBYOKActivation() }
  }

  private var hasAnyBYOKKey: Bool {
    !devOpenAIKey.isEmpty || !devAnthropicKey.isEmpty || !devGeminiKey.isEmpty
      || !devDeepgramKey.isEmpty
  }

  private var hasAllBYOKKeys: Bool {
    !devOpenAIKey.isEmpty && !devAnthropicKey.isEmpty && !devGeminiKey.isEmpty
      && !devDeepgramKey.isEmpty
  }

  @ViewBuilder
  private var byokStatusBanner: some View {
    settingsCard(settingId: "advanced.devkeys.info") {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: hasAllBYOKKeys ? "checkmark.seal.fill" : "key.fill")
          .foregroundColor(hasAllBYOKKeys ? OmiColors.success : OmiColors.textTertiary)
        VStack(alignment: .leading, spacing: 4) {
          Text(hasAllBYOKKeys ? "Free plan active" : "Use Omi free forever")
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(
            hasAllBYOKKeys
              ? "You're paying your own providers. Omi skips the subscription charge. Keys stay on this Mac."
              : "Provide all four keys (OpenAI, Anthropic, Gemini, Deepgram) to switch to the free plan. Keys stay on this Mac — we never store them on our servers."
          )
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        }
        Spacer()
      }
    }
  }

  private func clearAllBYOKKeys() {
    devOpenAIKey = ""
    devAnthropicKey = ""
    devGeminiKey = ""
    devDeepgramKey = ""
    Task {
      try? await APIClient.shared.deactivateBYOK()
    }
  }

  private func refreshBYOKActivation() {
    Task {
      if APIKeyService.isByokActive {
        // Validate before flipping the backend flag — otherwise we'd put the
        // user on the free plan with dead keys and every chat would 401.
        let snapshot = APIKeyService.byokSnapshot.reduce(into: [BYOKProvider: String]()) {
          acc, entry in acc[entry.key] = entry.value.key
        }
        let results = await BYOKValidator.validateAll(snapshot)
        let allOk = results.allSatisfy {
          if case .ok = $0.value { return true }
          return false
        }
        if allOk {
          let fingerprints = APIKeyService.byokSnapshot.reduce(into: [String: String]()) {
            acc, entry in acc[entry.key.rawValue] = entry.value.fingerprint
          }
          try? await APIClient.shared.activateBYOK(fingerprints: fingerprints)
          await FloatingBarUsageLimiter.shared.fetchPlan()
          await MainActor.run {
            byokKeyStatuses = results
            byokActivationError = nil
          }
        } else {
          let failed = results.filter {
            if case .ok = $0.value { return false }
            return true
          }
          let names = failed.keys.map(\.displayName).sorted().joined(separator: ", ")
          try? await APIClient.shared.deactivateBYOK()
          await FloatingBarUsageLimiter.shared.fetchPlan()
          await MainActor.run {
            byokKeyStatuses = results
            byokActivationError =
              "Rejected by provider: \(names). Free plan stays off until all 4 keys authenticate."
          }
        }
      } else {
        try? await APIClient.shared.deactivateBYOK()
        await FloatingBarUsageLimiter.shared.fetchPlan()
        await MainActor.run {
          byokKeyStatuses = [:]
          byokActivationError = nil
        }
      }
      await MainActor.run { loadSubscriptionInfo() }
    }
  }

  private func developerKeyField(
    provider: BYOKProvider? = nil,
    title: String, subtitle: String, settingId: String, value: Binding<String>
  ) -> some View {
    settingsCard(settingId: settingId) {
      VStack(alignment: .leading, spacing: 8) {
        HStack {
          Text(title)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
          Spacer()
          if let provider, let status = byokKeyStatuses[provider] {
            byokStatusBadge(status)
          }
        }
        Text(subtitle)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        SecureField("Leave blank for default", text: value)
          .textFieldStyle(.roundedBorder)
          .scaledFont(size: 13)
        if let provider, case .failed(let msg) = byokKeyStatuses[provider] ?? .notChecked {
          Text(msg)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.warning)
        }
      }
    }
  }

  @ViewBuilder
  private func byokStatusBadge(_ status: BYOKValidator.Status) -> some View {
    switch status {
    case .notChecked:
      EmptyView()
    case .checking:
      HStack(spacing: 4) {
        ProgressView().controlSize(.mini)
        Text("Checking…").scaledFont(size: 11).foregroundColor(OmiColors.textTertiary)
      }
    case .ok:
      Text("Valid").scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.success)
    case .failed:
      Text("Invalid").scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.warning)
    }
  }

  private var floatingBarVoiceAnswersBinding: Binding<Bool> {
    Binding(
      get: { shortcutSettings.floatingBarVoiceAnswersEnabled },
      set: { newValue in
        shortcutSettings.floatingBarVoiceAnswersEnabled = newValue
        SettingsSyncManager.shared.pushPartialUpdate(
          AssistantSettingsResponse(
            floatingBar: FloatingBarSettingsResponse(voiceAnswersEnabled: newValue)
          )
        )
      }
    )
  }

  private var floatingBarTypedVoiceAnswersBinding: Binding<Bool> {
    Binding(
      get: { shortcutSettings.floatingBarTypedQuestionVoiceAnswersEnabled },
      set: { newValue in
        shortcutSettings.floatingBarTypedQuestionVoiceAnswersEnabled = newValue
      }
    )
  }

  private func voiceSpeedSlider(settingId: String) -> some View {
    let steps = ShortcutSettings.voiceSpeedSteps
    let currentSpeed = shortcutSettings.voicePlaybackSpeed
    let currentIndex =
      steps.enumerated().min(by: { abs($0.element - currentSpeed) < abs($1.element - currentSpeed) }
      )?.offset ?? 3

    return settingsCard(settingId: settingId) {
      VStack(spacing: 16) {
        HStack {
          VStack(alignment: .leading, spacing: 2) {
            Text(ShortcutSettings.voiceSpeedLabel(for: currentSpeed))
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Voice playback speed")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Text("\(String(format: "%.1f", currentSpeed))×")
            .font(.system(size: 22, weight: .bold, design: .rounded))
            .foregroundColor(OmiColors.purplePrimary)
            .frame(width: 52, height: 52)
            .background(
              RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(OmiColors.purplePrimary.opacity(0.15))
            )
        }

        VStack(spacing: 6) {
          // Stepped slider
          GeometryReader { geo in
            let trackWidth = geo.size.width
            let segmentCount = CGFloat(steps.count - 1)

            ZStack(alignment: .leading) {
              // Track background
              RoundedRectangle(cornerRadius: 4)
                .fill(OmiColors.backgroundQuaternary)
                .frame(height: 6)

              // Filled track
              RoundedRectangle(cornerRadius: 4)
                .fill(OmiColors.purplePrimary)
                .frame(width: trackWidth * CGFloat(currentIndex) / segmentCount, height: 6)

              // Step dots
              ForEach(0..<steps.count, id: \.self) { i in
                Circle()
                  .fill(
                    i <= currentIndex ? OmiColors.purplePrimary : OmiColors.backgroundQuaternary
                  )
                  .frame(width: 8, height: 8)
                  .position(
                    x: trackWidth * CGFloat(i) / segmentCount,
                    y: 3
                  )
              }

              // Thumb
              Circle()
                .fill(Color.white)
                .frame(width: 22, height: 22)
                .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                .position(
                  x: trackWidth * CGFloat(currentIndex) / segmentCount,
                  y: 3
                )
                .gesture(
                  DragGesture(minimumDistance: 0)
                    .onChanged { value in
                      let fraction = max(0, min(1, value.location.x / trackWidth))
                      let nearestIndex = Int(round(fraction * segmentCount))
                      let clamped = max(0, min(steps.count - 1, nearestIndex))
                      shortcutSettings.voicePlaybackSpeed = steps[clamped]
                    }
                )
            }
          }
          .frame(height: 22)

          HStack {
            Text("Slow")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
            Spacer()
            Text("Max")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
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

  private func tierFeatureRow(
    tier: Int, name: String, requirement: String, progress: String?, unlocked: Bool
  ) -> some View {
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
            if let logoURL = Bundle.resourceBundle.url(
              forResource: "herologo", withExtension: "png"),
              let logoImage = NSImage(contentsOf: logoURL)
            {
              Image(nsImage: logoImage)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 48, height: 48)
            }

            VStack(alignment: .leading, spacing: 4) {
              HStack(spacing: 6) {
                Text("omi")
                  .scaledFont(size: 18, weight: .bold)
                  .foregroundColor(OmiColors.textPrimary)

                if !updaterViewModel.activeChannelLabel.isEmpty {
                  Text("(\(updaterViewModel.activeChannelLabel))")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(OmiColors.purplePrimary)
                }
              }

              Text("Version \(updaterViewModel.currentVersion) (\(updaterViewModel.buildNumber))")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
                .textSelection(.enabled)
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
            .help(
              updaterViewModel.canCheckForUpdates
                ? "Check for app updates" : "Already checking for updates…")
          }

          if let lastCheck = updaterViewModel.lastUpdateCheckDate {
            Text("Last checked: \(lastCheck, style: .relative) ago")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          settingRow(
            title: "Automatic Updates",
            subtitle: "Check for updates automatically in the background",
            settingId: "about.autoupdates"
          ) {
            Toggle("", isOn: $updaterViewModel.automaticallyChecksForUpdates)
              .toggleStyle(.switch)
              .labelsHidden()
              .disabled(updaterViewModel.usesManagedUpdatePolicy || AnalyticsManager.isDevBuild)
          }

          if updaterViewModel.automaticallyChecksForUpdates {
            settingRow(
              title: "Auto-Install Updates",
              subtitle: "Automatically download and install updates when available",
              settingId: "about.autoinstall"
            ) {
              Toggle("", isOn: $updaterViewModel.automaticallyDownloadsUpdates)
                .toggleStyle(.switch)
                .labelsHidden()
                .disabled(updaterViewModel.usesManagedUpdatePolicy || AnalyticsManager.isDevBuild)
            }
          }

          if updaterViewModel.usesManagedUpdatePolicy {
            Text("Release builds always auto-check and auto-install updates in the background.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          } else if AnalyticsManager.isDevBuild {
            Text(
              "Development builds keep automatic installation disabled to avoid replacing the local app."
            )
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          settingRow(
            title: "Update Channel", subtitle: updaterViewModel.updateChannel.description,
            settingId: "about.channel"
          ) {
            Picker(
              "",
              selection: Binding(
                get: { updaterViewModel.updateChannel },
                set: { newChannel in
                  // Switching beta → stable with a newer build: confirm first
                  if updaterViewModel.updateChannel == .beta && newChannel == .stable
                    && updaterViewModel.isDowngradeToStable
                  {
                    showDowngradeAlert = true
                  } else {
                    updaterViewModel.updateChannel = newChannel
                  }
                }
              )
            ) {
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
      .alert("Switch to Stable Channel?", isPresented: $showDowngradeAlert) {
        Button("Stay on Beta", role: .cancel) {}
        Button("Switch to Stable") {
          updaterViewModel.updateChannel = .stable
          if let url = URL(string: "https://macos.omi.me") {
            NSWorkspace.shared.open(url)
          }
        }
      } message: {
        let stableVersion = updaterViewModel.latestStableVersionString ?? "an older version"
        Text(
          "You're on a newer beta build (\(updaterViewModel.currentVersion)). The latest stable release is \(stableVersion).\n\nSwitching to Stable means you won't receive new updates until a stable release surpasses your current version. You can also download the stable version now."
        )
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

            Text("Help us improve omi")
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

  private func settingsCard<Content: View>(
    settingId: String? = nil, @ViewBuilder content: () -> Content
  ) -> some View {
    let card = content()
      .frame(maxWidth: .infinity, alignment: .leading)
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
        card.modifier(
          SettingHighlightModifier(
            settingId: settingId, highlightedSettingId: $highlightedSettingId))
      } else {
        card
      }
    }
  }

  private func settingRow<Content: View>(
    title: String, subtitle: String, settingId: String? = nil, @ViewBuilder control: () -> Content
  ) -> some View {
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
        row.modifier(
          SettingHighlightModifier(
            settingId: settingId, highlightedSettingId: $highlightedSettingId))
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

  private func privacyToggleRow(
    icon: String,
    title: String,
    subtitle: String,
    isOn: Binding<Bool>,
    onChange: @escaping (Bool) -> Void
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: icon)
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.purplePrimary)
          .frame(width: 20, alignment: .leading)

        VStack(alignment: .leading, spacing: 4) {
          Text(title)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text(subtitle)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 12)

        Toggle("", isOn: isOn)
          .toggleStyle(.switch)
          .labelsHidden()
          .controlSize(.small)
          .onChange(of: isOn.wrappedValue) { _, newValue in
            onChange(newValue)
          }
      }
    }
  }

  private var hasPaidSubscription: Bool {
    guard let subscription = userSubscription?.subscription else { return false }
    return subscription.plan != .basic && subscription.status == .active
  }

  private var shouldShowPlanPurchaseOptions: Bool {
    !subscriptionPlansForDisplay.isEmpty
  }

  private var subscriptionPlansForDisplay: [SubscriptionPlanOption] {
    // Operator (mass-market, green) on the left, Architect (premium, purple)
    // on the right. Hide the user's current plan — they already see it above.
    // Neo ($20) | Operator ($49) | Architect ($200) — cheapest to premium
    let order = ["unlimited": 0, "operator": 1, "architect": 2]
    return mergedPlanCatalog
      .filter { !isCurrentSubscriptionPlan($0) }
      .sorted { lhs, rhs in
        let lhsOrder = order[lhs.id, default: Int.max]
        let rhsOrder = order[rhs.id, default: Int.max]
        if lhsOrder != rhsOrder {
          return lhsOrder < rhsOrder
        }
        return lhs.title < rhs.title
      }
  }

  private var currentPlanTitle: String {
    guard let subscription = userSubscription?.subscription else {
      return isLoadingSubscription ? "Loading plan..." : "Free"
    }
    // BYOK users: the backend returns plan=unlimited to turn off metering
    // but that's an implementation detail — to the user, they're on the
    // free plan because they pay the providers directly, not Omi.
    if subscription.features.contains("byok") {
      return "Free (BYOK)"
    }
    switch subscription.plan {
    case .basic:
      return "Free"
    case .unlimited:
      // Backend serializes Operator subscribers as plan="unlimited" for
      // backward compat with old mobile builds that don't know the
      // `operator` enum. Distinguish by matching current_price_id against
      // an Operator-titled plan in the catalog.
      if isCurrentSubscriptionOperator() {
        return "Operator"
      }
      return "Neo"
    case .architect, .pro:
      return "Architect"
    case .operator:
      return "Operator"
    }
  }

  /// Returns true when the user's current Stripe price maps to a plan the
  /// backend is calling "Operator". Protects against the wire-level
  /// Operator→Unlimited remapping in `/v1/users/me/subscription`.
  private func isCurrentSubscriptionOperator() -> Bool {
    guard let subscription = userSubscription?.subscription,
          let currentPriceId = subscription.currentPriceId
    else { return false }
    for plan in subscriptionPlansForDisplay {
      guard plan.title == "Operator" else { continue }
      if plan.prices.contains(where: { $0.id == currentPriceId }) {
        return true
      }
    }
    return false
  }

  private var currentPlanSubtitle: String {
    if isLoadingSubscription {
      return "Fetching subscription details from omi."
    }
    if let detail = currentPlanBillingDetail {
      return detail
    }
    if hasPaidSubscription {
      return "Your paid plan is active."
    }
    return "You are currently on the free tier."
  }

  private var currentPlanBillingDetail: String? {
    guard hasPaidSubscription,
      let subscription = userSubscription?.subscription,
      let currentPriceId = subscription.currentPriceId
    else {
      return nil
    }

    for plan in subscriptionPlansForDisplay {
      if let price = plan.prices.first(where: { $0.id == currentPriceId }) {
        return "\(plan.title) \(price.title) • \(price.priceString)"
      }
    }

    return nil
  }

  private var currentPlanPeriodText: String? {
    guard let subscription = userSubscription?.subscription else { return nil }
    guard hasPaidSubscription, let periodEnd = subscription.currentPeriodEnd else { return nil }
    let date = Date(timeIntervalSince1970: TimeInterval(periodEnd))
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    let prefix = subscription.cancelAtPeriodEnd ? "Access ends" : "Renews"
    return "\(prefix) on \(formatter.string(from: date))"
  }

  private func planSubtitle(for planId: String) -> String? {
    switch planId {
    case "unlimited":
      return "200 questions per month"
    case "operator":
      return "500 questions per month"
    case "architect":
      return "Power-user AI — thousands of chats + agentic automations"
    default:
      return nil
    }
  }

  private func planAccentColor(for planId: String) -> Color {
    // Architect is the premium/purple tier; Operator + legacy Unlimited
    // are the mass-market green tier.
    planId == "architect" ? OmiColors.purplePrimary : OmiColors.success
  }

  private func planSummaryText(for plan: SubscriptionPlanOption) -> String {
    preferredStartingPrice(for: plan)?.priceString ?? ""
  }

  private func preferredStartingPrice(for plan: SubscriptionPlanOption) -> SubscriptionPriceOption?
  {
    let prices = sortedPrices(for: plan)
    if let monthly = prices.first(where: { price in
      let title = price.title.lowercased()
      return title.contains("month")
    }) {
      return monthly
    }
    return prices.first
  }

  private func planEyebrow(for planId: String) -> String {
    switch planId {
    case "unlimited":
      return "Starter"
    case "operator":
      return "Most popular"
    case "architect":
      return "Automation + coding"
    default:
      return "Plan"
    }
  }

  private func planDescription(for planId: String) -> String {
    switch planId {
    case "unlimited":
      return "100 chat questions per month. Shared with mobile and web."
    case "operator":
      return "500 chat questions per month. Shared with mobile and web."
    case "architect":
      return "Power-user AI for heavy agentic workflows and vibe coding."
    default:
      return ""
    }
  }

  private func sortedPrices(for plan: SubscriptionPlanOption) -> [SubscriptionPriceOption] {
    plan.prices.sorted { lhs, rhs in
      let lhsIsMonthly = lhs.title.lowercased().contains("month")
      let rhsIsMonthly = rhs.title.lowercased().contains("month")
      if lhsIsMonthly != rhsIsMonthly {
        return lhsIsMonthly && !rhsIsMonthly
      }
      return lhs.title < rhs.title
    }
  }

  private func isCurrentSubscriptionPlan(_ plan: SubscriptionPlanOption) -> Bool {
    guard hasPaidSubscription, let currentPlan = userSubscription?.subscription.plan else {
      return false
    }
    return currentPlan.rawValue == plan.id
  }

  private var mergedPlanCatalog: [SubscriptionPlanOption] {
    mergePlanCatalog(primary: userSubscription?.availablePlans ?? [], fallback: fallbackPlanCatalog)
  }

  private func mergePlanCatalog(
    primary: [SubscriptionPlanOption],
    fallback: [SubscriptionPlanOption]
  ) -> [SubscriptionPlanOption] {
    SubscriptionPlanCatalogMerger.merge(primary: primary, fallback: fallback)
  }

  private func fallbackFeatures(for planId: String) -> [String] {
    switch planId {
    case "architect":
      return [
        "Automations and vibe coding",
        "Unlimited listening, memories, and insights",
        "Priority desktop AI features",
        "~$400 of monthly AI compute included (fair-use cap)",
      ]
    case "operator":
      return [
        "500 chat questions per month",
        "Unlimited listening and transcription",
        "Unlimited memories and insights",
        "Shared with mobile and web",
      ]
    case "unlimited":
      return [
        "200 chat questions per month",
        "Unlimited listening and transcription",
        "Unlimited memories and insights",
        "Shared with mobile and web",
      ]
    default:
      return []
    }
  }

  private func normalizedPlanId(from title: String) -> String? {
    let normalized = title.lowercased()
    // Match the three plan families by title keyword. Neo is the post-rename
    // display name for the legacy "unlimited" plan and still maps to that id
    // because Stripe/backend PlanType enum is unchanged.
    if normalized.contains("unlimited") || normalized.contains("neo") {
      return "unlimited"
    }
    if normalized.contains("operator") {
      return "operator"
    }
    if normalized.contains("architect") || normalized.contains("pro") {
      return "architect"
    }
    return nil
  }

  private func planCatalog(from prices: [AvailablePlanPriceOption]) -> [SubscriptionPlanOption] {
    let groupedPrices = Dictionary(grouping: prices) { price in
      normalizedPlanId(from: price.title) ?? "unknown"
    }

    return groupedPrices.compactMap { planId, options in
      guard planId != "unknown" else { return nil }

      let title: String
      switch planId {
      case "unlimited":
        title = "Neo"
      case "operator":
        title = "Operator"
      case "architect":
        title = "Architect"
      default:
        title = options.first?.title ?? "Plan"
      }

      let mappedPrices = options.map { option in
        SubscriptionPriceOption(
          id: option.id,
          title: option.interval.lowercased().contains("year") ? "Annual" : "Monthly",
          description: option.description,
          priceString: option.priceString
        )
      }

      return SubscriptionPlanOption(
        id: planId,
        title: title,
        features: fallbackFeatures(for: planId),
        prices: mappedPrices
      )
    }
  }

  @ViewBuilder
  private func subscriptionPlanCard(_ plan: SubscriptionPlanOption) -> some View {
    let isSelected = selectedPlanIdForCheckout == plan.id
    let accent = planAccentColor(for: plan.id)
    let isCurrentPlan = isCurrentSubscriptionPlan(plan)
    let isArchitectUser =
      userSubscription?.subscription.plan == .architect
      || userSubscription?.subscription.plan == .pro
    let isDowngrade = isArchitectUser && plan.id == "unlimited"
    let canPurchase = !isCurrentPlan && !isDowngrade

    VStack(alignment: .leading, spacing: 16) {
      HStack(alignment: .top, spacing: 12) {
        VStack(alignment: .leading, spacing: 6) {
          Text((plan.eyebrow ?? planEyebrow(for: plan.id)).uppercased())
            .scaledFont(size: 10, weight: .bold)
            .foregroundColor(accent)
            .tracking(0.8)

          Text(plan.title)
            .scaledFont(size: 18, weight: .bold)
            .foregroundColor(OmiColors.textPrimary)

          if let subtitle = plan.subtitle ?? planSubtitle(for: plan.id) {
            Text(subtitle)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }

        Spacer()

        VStack(alignment: .trailing, spacing: 2) {
          Text(planSummaryText(for: plan))
            .scaledFont(size: 17, weight: .bold)
            .foregroundColor(isSelected ? accent : OmiColors.textPrimary)
            .lineLimit(1)
            .minimumScaleFactor(0.72)

          Text("starting price")
            .scaledFont(size: 10, weight: .medium)
            .foregroundColor(isSelected ? accent.opacity(0.8) : OmiColors.textTertiary)
        }
        .fixedSize(horizontal: true, vertical: false)
      }

      Text(plan.description ?? planDescription(for: plan.id))
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textSecondary)

      VStack(alignment: .leading, spacing: 8) {
        ForEach(plan.features.prefix(4), id: \.self) { feature in
          HStack(spacing: 8) {
            ZStack {
              Circle()
                .fill(accent.opacity(0.16))
                .frame(width: 18, height: 18)
              Image(systemName: "checkmark")
                .scaledFont(size: 9, weight: .bold)
                .foregroundColor(accent)
            }
            Text(feature)
              .scaledFont(size: 13, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
          }
        }
      }

      if isSelected && canPurchase {
        Divider()
          .overlay(OmiColors.backgroundQuaternary)

        VStack(alignment: .leading, spacing: 10) {
          Text("Choose billing")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)

          HStack(spacing: 10) {
            ForEach(sortedPrices(for: plan)) { price in
              Button(action: {
                startCheckout(for: price.id)
              }) {
                Group {
                  if activeCheckoutPriceId == price.id {
                    ProgressView()
                      .controlSize(.small)
                      .frame(maxWidth: .infinity)
                  } else {
                    VStack(spacing: 3) {
                      Text(price.title)
                        .scaledFont(size: 12, weight: .bold)
                      Text(price.priceString)
                        .scaledFont(size: 11)
                        .foregroundColor(Color.white.opacity(0.92))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                  }
                }
                .padding(.vertical, 10)
              }
              .buttonStyle(.borderedProminent)
              .tint(accent)
              .disabled(activeCheckoutPriceId != nil)
            }
          }
        }
      } else if isCurrentPlan {
        HStack {
          Text("Current Plan")
            .scaledFont(size: 12, weight: .bold)
          Spacer()
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 12)
        }
        .foregroundColor(accent)
        .padding(.vertical, 10)
      } else {
        Button(action: {
          selectedPlanIdForCheckout = plan.id
        }) {
          HStack {
            Text("Select \(plan.title)")
              .scaledFont(size: 12, weight: .bold)
            Spacer()
            Image(systemName: "arrow.right")
              .scaledFont(size: 11, weight: .bold)
          }
          .padding(.vertical, 10)
        }
        .buttonStyle(.borderedProminent)
        .tint(accent)
      }
    }
    .padding(20)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 18)
        .fill(isSelected ? accent.opacity(0.12) : OmiColors.backgroundPrimary.opacity(0.68))
        .overlay(
          RoundedRectangle(cornerRadius: 18)
            .stroke(
              isSelected ? accent.opacity(0.85) : OmiColors.backgroundQuaternary,
              lineWidth: isSelected ? 1.5 : 1)
        )
    )
    .contentShape(RoundedRectangle(cornerRadius: 18))
    .onTapGesture {
      guard canPurchase else { return }
      selectedPlanIdForCheckout = plan.id
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

  private var insightIntervalSliderIndex: Int {
    extractionIntervalOptions.firstIndex(of: insightExtractionInterval) ?? 0
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
    vadGateEnabled = AssistantSettings.shared.vadGateEnabled

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

        let (dailySummary, notifications, language, recording, cloudSync, transcription, _) = try
          await (
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

  private func loadSubscriptionInfo() {
    guard !isLoadingSubscription else { return }
    isLoadingSubscription = true
    subscriptionError = nil

    Task {
      do {
        let subscription = try await APIClient.shared.getUserSubscription()
        let availablePlans = try? await APIClient.shared.getAvailablePlans()
        await MainActor.run {
          userSubscription = subscription
          subscriptionError = nil
          fallbackPlanCatalog = availablePlans.map { planCatalog(from: $0.plans) } ?? []
          if let selectedPlanIdForCheckout,
            subscription.subscription.plan.rawValue == selectedPlanIdForCheckout
          {
            self.selectedPlanIdForCheckout = nil
          }
          isLoadingSubscription = false
        }
      } catch {
        logError("Failed to load subscription", error: error)
        await MainActor.run {
          subscriptionError = "Failed to load plan information."
          isLoadingSubscription = false
        }
      }
    }
    loadChatUsageQuota()
    loadOverageInfo()
  }

  private func loadChatUsageQuota() {
    guard !isLoadingChatUsage else { return }
    isLoadingChatUsage = true
    Task {
      let quota = await APIClient.shared.fetchChatUsageQuota()
      await MainActor.run {
        chatUsageQuota = quota
        isLoadingChatUsage = false
      }
    }
  }

  private func loadOverageInfo() {
    guard !isLoadingOverage else { return }
    isLoadingOverage = true
    Task {
      do {
        let info = try await APIClient.shared.getOverageInfo()
        await MainActor.run {
          overageInfo = info
          isLoadingOverage = false
        }
      } catch {
        logError("Failed to load overage info", error: error)
        await MainActor.run {
          isLoadingOverage = false
        }
      }
    }
  }

  private func startCheckout(for priceId: String) {
    guard activeCheckoutPriceId == nil else { return }
    activeCheckoutPriceId = priceId
    pendingSubscriptionPriceId = priceId
    subscriptionError = nil

    // If user already has an active paid subscription (not canceled), use upgrade endpoint
    // to schedule the plan change at end of billing period (no double-charging)
    if hasPaidSubscription,
       let subscription = userSubscription?.subscription,
       !subscription.cancelAtPeriodEnd
    {
      Task {
        do {
          _ = try await APIClient.shared.upgradeSubscription(priceId: priceId)
          await MainActor.run {
            activeCheckoutPriceId = nil
            pendingSubscriptionPriceId = nil
            subscriptionError = nil
            loadSubscriptionInfo()
          }
        } catch {
          logError("Failed to schedule plan change", error: error)
          await MainActor.run {
            activeCheckoutPriceId = nil
            pendingSubscriptionPriceId = nil
            subscriptionError = "Failed to schedule plan change."
          }
        }
      }
      return
    }

    Task {
      do {
        let response = try await APIClient.shared.createCheckoutSession(priceId: priceId)
        let apiBaseURL = await APIClient.shared.baseURL
        await MainActor.run {
          activeCheckoutPriceId = nil
          pendingCheckoutSessionId = response.sessionId
        }

        if response.status == "reactivated" {
          await MainActor.run {
            subscriptionError = nil
            pendingSubscriptionPriceId = nil
            pendingCheckoutSessionId = nil
            loadSubscriptionInfo()
          }
        } else if let urlString = response.url, let url = URL(string: urlString) {
          let normalizedBaseURL = apiBaseURL.hasSuffix("/") ? apiBaseURL : apiBaseURL + "/"
          await MainActor.run {
            activeBillingWebFlow = BillingWebFlow(
              title: "Complete Your Upgrade",
              url: url,
              completionURLs: [
                normalizedBaseURL + "v1/payments/success",
                normalizedBaseURL + "v1/payments/cancel",
              ]
            )
          }
        } else {
          await MainActor.run {
            subscriptionError = response.message ?? "Could not start checkout."
          }
        }
      } catch {
        logError("Failed to create checkout session", error: error)
        await MainActor.run {
          activeCheckoutPriceId = nil
          pendingSubscriptionPriceId = nil
          pendingCheckoutSessionId = nil
          subscriptionError = "Failed to open checkout."
        }
      }
    }
  }

  private func openCustomerPortal() {
    guard !isOpeningCustomerPortal else { return }
    isOpeningCustomerPortal = true
    subscriptionError = nil

    Task {
      do {
        let response = try await APIClient.shared.createCustomerPortalSession()
        await MainActor.run {
          isOpeningCustomerPortal = false
        }

        if let url = URL(string: response.url) {
          await MainActor.run {
            openURLInDefaultBrowser(url)
            subscriptionError = "Billing portal opened in your browser."
          }
        } else {
          await MainActor.run {
            subscriptionError = "Could not open billing portal."
          }
        }
      } catch {
        logError("Failed to open customer portal", error: error)
        await MainActor.run {
          isOpeningCustomerPortal = false
          subscriptionError = "Failed to open billing portal."
        }
      }
    }
  }

  private func handleBillingFlowCompletion(_ outcome: BillingWebFlowOutcome) {
    switch outcome {
    case .completed:
      Task {
        await completeLocalTestSubscriptionIfNeeded()
        await MainActor.run {
          pollForUpdatedSubscription()
        }
      }
    case .cancelled, .dismissed:
      pendingSubscriptionPriceId = nil
      pendingCheckoutSessionId = nil
      loadSubscriptionInfo()
    }
  }

  private func pollForUpdatedSubscription() {
    let expectedPriceId = pendingSubscriptionPriceId

    Task {
      for attempt in 0..<8 {
        do {
          let subscription = try await APIClient.shared.getUserSubscription()
          let matchedPrice =
            expectedPriceId == nil || subscription.subscription.currentPriceId == expectedPriceId
          let hasPaidPlan =
            subscription.subscription.plan != .basic && subscription.subscription.status == .active

          if matchedPrice && hasPaidPlan {
            await FloatingBarUsageLimiter.shared.fetchPlan()
            await MainActor.run {
              userSubscription = subscription
              subscriptionError = nil
              pendingSubscriptionPriceId = nil
              pendingCheckoutSessionId = nil
            }
            return
          }

          if attempt == 7 {
            await MainActor.run {
              userSubscription = subscription
              subscriptionError =
                "Payment completed, but plan refresh is still catching up. Please try reloading this page in a moment."
              pendingSubscriptionPriceId = nil
              pendingCheckoutSessionId = nil
            }
            return
          }

          try await Task.sleep(nanoseconds: 1_000_000_000)
        } catch {
          if attempt == 7 {
            await MainActor.run {
              subscriptionError = "Payment completed, but subscription refresh failed."
              pendingSubscriptionPriceId = nil
              pendingCheckoutSessionId = nil
            }
            return
          }

          try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
      }
    }
  }

  private func completeLocalTestSubscriptionIfNeeded() async {
    guard let expectedPriceId = pendingSubscriptionPriceId else { return }
    let checkoutSessionId = pendingCheckoutSessionId
    let pythonBaseURL = await APIClient.shared.baseURL
    let rustBaseURL = await APIClient.shared.rustBackendURL

    if let checkoutSessionId, isLocalURL(pythonBaseURL) {
      guard
        let encodedSessionId = checkoutSessionId.addingPercentEncoding(
          withAllowedCharacters: .urlQueryAllowed),
        let url = URL(string: "\(pythonBaseURL)v1/payments/success?session_id=\(encodedSessionId)")
      else {
        return
      }

      do {
        _ = try await URLSession.shared.data(from: url)
      } catch {
        logError("Failed to complete local python test subscription", error: error)
      }
      return
    }

    guard isLocalURL(rustBaseURL) else { return }

    guard
      let encodedPriceId = expectedPriceId.addingPercentEncoding(
        withAllowedCharacters: .urlQueryAllowed)
    else {
      return
    }

    var urlString = "\(rustBaseURL)test/complete-subscription?price_id=\(encodedPriceId)"
    if let checkoutSessionId,
      let encodedSessionId = checkoutSessionId.addingPercentEncoding(
        withAllowedCharacters: .urlQueryAllowed)
    {
      urlString += "&session_id=\(encodedSessionId)"
    }

    guard let url = URL(string: urlString) else { return }

    do {
      _ = try await URLSession.shared.data(from: url)
    } catch {
      logError("Failed to complete local test subscription", error: error)
    }
  }

  private func isLocalURL(_ url: String) -> Bool {
    url.hasPrefix("http://127.0.0.1:") || url.hasPrefix("http://localhost:")
  }

  private func openURLInDefaultBrowser(_ url: URL) {
    if let appURL = NSWorkspace.shared.urlForApplication(toOpen: url) {
      let configuration = NSWorkspace.OpenConfiguration()
      configuration.activates = true
      NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: configuration) {
        _, error in
        if let error {
          NSLog(
            "OMI SETTINGS: Failed to open browser URL %@: %@", url.absoluteString,
            error.localizedDescription)
          NSWorkspace.shared.open(url)
        }
      }
      return
    }

    NSWorkspace.shared.open(url)
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
        let _ = try await APIClient.shared.updateNotificationSettings(
          enabled: enabled, frequency: frequency)
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

  private func updateTranscriptionPreferences(
    singleLanguageMode: Bool? = nil, vocabulary: String? = nil
  ) {
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

  private func deleteAccountAndData() {
    guard !isDeletingAccount else { return }

    deleteAccountError = nil
    isDeletingAccount = true
    AnalyticsManager.shared.deleteAccountConfirmed()

    Task {
      do {
        try await APIClient.shared.deleteAccount()
        await MainActor.run {
          appState.stopTranscription()
          ProactiveAssistantsPlugin.shared.stopMonitoring()
          do {
            try AuthService.shared.signOut()
            isDeletingAccount = false
          } catch {
            deleteAccountError =
              "Account deleted, but sign out failed: \(error.localizedDescription)"
            isDeletingAccount = false
          }
        }
      } catch {
        await MainActor.run {
          deleteAccountError = "Failed to delete account: \(error.localizedDescription)"
          isDeletingAccount = false
        }
      }
    }
  }

}

private struct BillingWebFlow: Identifiable {
  let id = UUID()
  let title: String
  let url: URL
  let completionURLs: [String]
}

private enum BillingWebFlowOutcome {
  case completed
  case cancelled
  case dismissed
}

private struct BillingWebFlowSheet: View {
  let flow: BillingWebFlow
  let onComplete: (BillingWebFlowOutcome) -> Void

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Text(flow.title)
          .scaledFont(size: 18, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button("Close") {
          onComplete(.dismissed)
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
      }
      .padding(.horizontal, 20)
      .padding(.vertical, 16)
      .background(OmiColors.backgroundTertiary)

      Divider()

      BillingWebView(flow: flow, onComplete: onComplete)
        .frame(minWidth: 860, minHeight: 680)
    }
    .background(OmiColors.backgroundPrimary)
  }
}

private struct BillingWebView: NSViewRepresentable {
  let flow: BillingWebFlow
  let onComplete: (BillingWebFlowOutcome) -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(flow: flow, onComplete: onComplete)
  }

  func makeNSView(context: Context) -> WKWebView {
    let configuration = WKWebViewConfiguration()
    configuration.defaultWebpagePreferences.allowsContentJavaScript = true

    let webView = WKWebView(frame: .zero, configuration: configuration)
    webView.navigationDelegate = context.coordinator
    webView.uiDelegate = context.coordinator
    webView.setValue(false, forKey: "drawsBackground")
    webView.load(URLRequest(url: flow.url))
    return webView
  }

  func updateNSView(_ nsView: WKWebView, context: Context) {}

  final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
    private let flow: BillingWebFlow
    private let onComplete: (BillingWebFlowOutcome) -> Void
    private var completionHandled = false

    init(flow: BillingWebFlow, onComplete: @escaping (BillingWebFlowOutcome) -> Void) {
      self.flow = flow
      self.onComplete = onComplete
    }

    func webView(
      _ webView: WKWebView,
      decidePolicyFor navigationAction: WKNavigationAction,
      decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
      guard let url = navigationAction.request.url?.absoluteString else {
        decisionHandler(.allow)
        return
      }

      if let matchedCompletionURL = flow.completionURLs.first(where: { url.hasPrefix($0) }) {
        if matchedCompletionURL.hasSuffix("/cancel") {
          finish(.cancelled)
        } else {
          finish(.completed)
        }
        decisionHandler(.cancel)
        return
      }

      decisionHandler(.allow)
    }

    func webView(
      _ webView: WKWebView,
      createWebViewWith configuration: WKWebViewConfiguration,
      for navigationAction: WKNavigationAction,
      windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
      if navigationAction.targetFrame == nil, let requestURL = navigationAction.request.url {
        webView.load(URLRequest(url: requestURL))
      }
      return nil
    }

    private func finish(_ outcome: BillingWebFlowOutcome) {
      guard !completionHandled else { return }
      completionHandled = true
      DispatchQueue.main.async {
        self.onComplete(outcome)
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
            ForEach(
              runningApps.filter {
                !excludedApps.contains($0)
                  && !TaskAssistantSettings.builtInExcludedApps.contains($0)
              }, id: \.self
            ) { appName in
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
            ForEach(
              runningApps.filter {
                !allowedApps.contains($0) && !TaskAssistantSettings.defaultAllowedApps.contains($0)
              }, id: \.self
            ) { appName in
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
          .fill(
            isHovered ? OmiColors.backgroundQuaternary : OmiColors.backgroundTertiary.opacity(0.5))
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
    highlightedSettingId: .constant(nil)
  )
}
