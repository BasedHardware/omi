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
  @StateObject var viewModel = SettingsViewModel()

  // Updater view model
  @ObservedObject var updaterViewModel = UpdaterViewModel.shared
  @ObservedObject var shortcutSettings = ShortcutSettings.shared

  // Master monitoring state (screen analysis)
  @State var isMonitoring: Bool
  @State var isToggling: Bool = false
  @State var permissionError: String?

  // Ask Omi floating bar state
  @State var showAskOmiBar: Bool = false

  // Transcription state
  @State var isTranscribing: Bool
  @State var isTogglingTranscription: Bool = false
  @State var transcriptionError: String?

  // Log export state

  // Focus Assistant states
  @State var focusEnabled: Bool
  @State var cooldownInterval: Int
  @State var glowOverlayEnabled: Bool
  @State var analysisDelay: Int
  @State var focusNotificationsEnabled: Bool
  @State var focusExcludedApps: Set<String>

  // Task Assistant states
  @State var taskEnabled: Bool
  @State var taskChatAgentEnabled: Bool
  @State var taskAgentWorkingDirectory: String
  @State var taskExtractionInterval: Double
  @State var taskMinConfidence: Double
  @State var taskNotificationsEnabled: Bool
  @State var taskAllowedApps: Set<String>
  @State var taskBrowserKeywords: [String]
  @State var isRescoringTasks = false

  // Advice Assistant states
  @State var insightEnabled: Bool
  @State var insightExtractionInterval: Double
  @State var insightMinConfidence: Double
  @State var insightNotificationsEnabled: Bool
  @State var insightExcludedApps: Set<String>

  // Memory Assistant states
  @State var memoryEnabled: Bool
  @State var memoryExtractionInterval: Double
  @State var memoryMinConfidence: Double
  @State var memoryNotificationsEnabled: Bool
  @State var memoryExcludedApps: Set<String>

  // Goals states
  @State var goalsAutoGenerateEnabled: Bool = GoalGenerationService.shared
    .isAutoGenerationEnabled

  // Glow preview state
  @State var isPreviewRunning: Bool = false

  // Downgrade confirmation alert
  @State var showDowngradeAlert = false

  // Tier gating (0 = show all, 1-6 = sequential tiers)
  @AppStorage("currentTierLevel") var currentTierLevel = 0

  // Advanced stats
  @State var advancedStats: UserStats?
  @State var isLoadingStats = false
  @State var chatMessageCount: Int?
  @State var isLoadingChatMessages = false
  @State var showProfileAndStats = false

  // AI User Profile
  @State var aiProfileId: Int64?
  @State var aiProfileText: String?
  @State var aiProfileGeneratedAt: Date?
  @State var aiProfileDataSourcesUsed: Int = 0
  @State var isGeneratingAIProfile = false
  @State var isEditingAIProfile = false
  @State var aiProfileEditText: String = ""

  // Writing Voice (messaging Tone & Style guide — backend-generated on message sync)
  @State var toneGuideText: String?
  @State var toneGuideGeneratedAt: Date?
  @State var toneGuideSampleCount: Int = 0
  @State var isGeneratingToneGuide = false

  // Selected section (passed in from parent)
  @Binding var selectedSection: SettingsSection
  @Binding var highlightedSettingId: String?

  // Notification settings (from backend)
  @State var dailySummaryEnabled: Bool = true
  @State var dailySummaryHour: Int = 22
  @State var notificationsEnabled: Bool = true
  @State var notificationFrequency: Int = 3

  // Privacy settings (from backend)
  @State var recordingPermissionEnabled: Bool = false
  @State var privateCloudSyncEnabled: Bool = true
  @State var isTrackingExpanded: Bool = false

  // Transcription settings (from backend)
  @State var singleLanguageMode: Bool = false
  @State var newVocabularyWord: String = ""
  @State var vocabularyList: [String] = []

  // Language setting
  @State var userLanguage: String = "en"

  // Loading states
  @State var userSubscription: UserSubscriptionResponse?
  @State var chatUsageQuota: APIClient.ChatUsageQuota?
  @State var isLoadingChatUsage: Bool = false
  @State var overageInfo: OverageInfoResponse?
  @State var isLoadingOverage: Bool = false
  @State var planUsageDetailsRequestID: Int = 0
  @State var showOverageExplainer: Bool = false
  @State var fallbackPlanCatalog: [SubscriptionPlanOption] = []
  @State var activeCheckoutPriceId: String?
  @State var selectedPlanIdForCheckout: String?
  @State var upgradePromotionCode: String = ""
  @State var isPromoCodeExpanded: Bool = false
  @State var isOpeningCustomerPortal: Bool = false
  @State var activeBillingWebFlow: BillingWebFlow?
  @State var pendingSubscriptionPriceId: String?
  @State var pendingCheckoutSessionId: String?

  var isLoadingSettings: Bool {
    get { viewModel.isLoadingBackendSettings }
    nonmutating set { viewModel.isLoadingBackendSettings = newValue }
  }

  var isLoadingSubscription: Bool {
    get { viewModel.isLoadingSubscription }
    nonmutating set { viewModel.isLoadingSubscription = newValue }
  }

  var subscriptionError: String? {
    get { viewModel.subscriptionError }
    nonmutating set { viewModel.subscriptionError = newValue }
  }

  let cooldownOptions = [1, 2, 5, 10, 15, 30, 60]
  let analysisDelayOptions = [0, 10, 20, 30, 60, 300]  // seconds: instant, 10s, 20s, 30s, 1 min, 5 min
  let extractionIntervalOptions: [Double] = [10.0, 600.0, 3600.0]  // 10s, 10min, 1hr
  let hourOptions = Array(0...23)
  let frequencyOptions = [
    (0, "Off"),
    (1, "Minimal"),
    (2, "Low"),
    (3, "Balanced"),
    (4, "High"),
    (5, "Maximum"),
  ]
  // Use the full language list from AssistantSettings
  var languageOptions: [(String, String)] {
    AssistantSettings.supportedLanguages.map { ($0.code, $0.name) }
  }

  // Language auto-detect state (from local settings)
  @State var transcriptionAutoDetect: Bool = true
  @State var transcriptionLanguage: String = "en"
  @State var vadGateEnabled: Bool = false
  @State var systemAudioCaptureMode: AssistantSettings.SystemAudioCaptureMode = .always

  // Multi-chat mode setting
  @AppStorage("multiChatEnabled") var multiChatEnabled = false
  @AppStorage("conversationsCompactView") var conversationsCompactView = true
  @AppStorage("useLegacyHomeDesign") var useLegacyHomeDesign = false

  // AI Chat settings
  @AppStorage("chatBridgeMode") var chatBridgeMode: String = "piMono"
  @AppStorage("realtimeOmniProvider") var realtimeOmniProvider: String = RealtimeOmniProvider.auto.rawValue
  @AppStorage("askModeEnabled") var askModeEnabled = false
  @AppStorage("claudeMdEnabled") var claudeMdEnabled = true
  @AppStorage("projectClaudeMdEnabled") var projectClaudeMdEnabled = true
  @AppStorage("aiChatWorkingDirectory") var aiChatWorkingDirectory: String = ""
  @State var aiChatClaudeMdContent: String?
  @State var aiChatClaudeMdPath: String?
  @State var aiChatProjectClaudeMdContent: String?
  @State var aiChatProjectClaudeMdPath: String?
  @State var aiChatDiscoveredSkills: [(name: String, description: String, path: String)] =
    []
  @State var aiChatProjectDiscoveredSkills:
    [(name: String, description: String, path: String)] = []
  @State var aiChatDisabledSkills: Set<String> = []
  @State var showFileViewer = false
  @State var fileViewerContent = ""
  @State var fileViewerTitle = ""
  @State var skillSearchQuery = ""

  // Dev Mode setting
  @AppStorage("devModeEnabled") var devModeEnabled = false

  // Browser Extension settings
  @AppStorage("playwrightUseExtension") var playwrightUseExtension = true
  @State var playwrightExtensionToken: String = ""
  @State var showBrowserSetup = false

  // Launch at login manager
  @ObservedObject var launchAtLoginManager = LaunchAtLoginManager.shared

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
    case writingVoice = "Writing Voice"
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
      case .writingVoice: return "text.bubble"
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

  @State var showResetOnboardingAlert: Bool = false
  @State var showRescanFilesAlert: Bool = false
  @State var showDeleteAccountAlert: Bool = false

  // Gmail Reader states
  @State var gmailEmails: [GmailEmail] = []
  @State var isReadingGmail: Bool = false
  @State var isSavingGmailMemories: Bool = false
  @State var gmailMemoriesSaved: Int = 0
  @State var gmailReadError: String?
  @State var gmailLastFetched: Date?

  // Calendar Sync states
  @State var calendarEvents: [CalendarEvent] = []
  @State var isReadingCalendar: Bool = false
  @State var calendarMemoriesCreated: Int = 0
  @State var calendarTasksCreated: Int = 0
  @State var calendarSyncError: String?
  @State var calendarLastSynced: Date?

  @State var isDeletingAccount: Bool = false
  @State var deleteAccountError: String?

  // Developer API Key overrides — also double as BYOK free-plan credentials
  // when all four (Gemini, Anthropic, OpenAI, Deepgram) are provided.
  @AppStorage("dev_gemini_api_key") var devGeminiKey: String = ""
  @AppStorage("dev_anthropic_api_key") var devAnthropicKey: String = ""
  @AppStorage("dev_openai_api_key") var devOpenAIKey: String = ""
  @AppStorage("dev_deepgram_api_key") var devDeepgramKey: String = ""
  @State var byokKeyStatuses: [BYOKProvider: BYOKValidator.Status] = [:]
  @State var byokActivationError: String?

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
    _systemAudioCaptureMode = State(initialValue: settings.systemAudioCaptureMode)
  }

  /// Computed status text for notifications
  var notificationStatusText: String {
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
        // Refetch everything for the CURRENT account. Without the trial + limiter
        // refresh, switching accounts leaves the previous user's "Trial Ended" /
        // over-limit state painted here (trialMetadata + serverQuota aren't reset
        // per-account on a section switch).
        loadSubscriptionInfo()
        AppState.current?.fetchTrialMetadata()
        Task { await FloatingBarUsageLimiter.shared.fetchPlan() }
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


  @ObservedObject var fontScaleSettings = FontScaleSettings.shared
  @ObservedObject var rewindSettings = RewindSettings.shared
  @State var rewindStats: (total: Int, indexed: Int, storageSize: Int64)? = nil
}
