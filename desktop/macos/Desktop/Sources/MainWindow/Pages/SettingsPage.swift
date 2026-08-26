import OmiTheme
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

  /// Whether the Reset Onboarding confirmation is up.
  ///
  /// It lives here rather than beside the card that raises it because a modal's dim is an overlay,
  /// and an overlay's extent is the view it is attached to. The card is a row inside this page's
  /// scroll view; attached there, the dim would darken one row and the dialog would centre on it.
  /// This is the pane — the deepest surface in the shell that is a real, laid-out rectangle rather
  /// than a scrolling column — so it is where the confirmation is mounted.
  @State private var showResetOnboardingConfirm = false

  var body: some View {
    Group {
      if let page = selectedSection.presentedPage {
        // A section that presents a whole established page mounts it directly. Not inside the
        // shared scroll view: `PermissionsPage` owns a `ScrollView` of its own, so nesting it
        // inside this page's scroller gives the pane two scrollbars. It already draws its own pane
        // heading and `SettingsGlassMetrics.pane*` padding, so the shared header is skipped too
        // rather than stacked on top of its own.
        presentedPage(page)
      } else {
        sectionScrollView
      }
    }
    // Deliberately no background: the window wears the glass, and the glass owns the ground. A fill
    // here — even a faint one — is a second ground painted over the material, which is how a
    // translucent window ends up looking opaque.
    //
    // Drawn by the shell rather than by `.alert`, which dims the *window* — and this window is a
    // transparent rectangle larger than the panels in it, so that dim was a rounded rectangle on the
    // user's wallpaper. See `ShellConfirmationDialog`.
    .shellConfirmation(
      isPresented: $showResetOnboardingConfirm,
      title: "Reset Onboarding?",
      message: "This will reset onboarding for this app build only, clear onboarding chat history, "
        + "and restart the app without affecting the other installed build.",
      confirmTitle: "Reset & Restart"
    ) {
      appState.resetOnboardingAndRestart()
    }
    // The settings section list is a sibling of this pane inside the panel, so it stays clickable
    // while the confirmation is up. Leaving on it cancels rather than stranding a destructive
    // confirmation over a page it no longer belongs to.
    .onChange(of: selectedSection) { _, _ in
      showResetOnboardingConfirm = false
    }
    .onAppear {
      AnalyticsManager.shared.settingsPageOpened()
    }
  }

  /// The established page a presenting section mounts. One `switch`, so a new presenting section
  /// cannot compile without naming the page it presents.
  @ViewBuilder
  private func presentedPage(_ page: ShellDestination) -> some View {
    switch page {
    case .permissions:
      PermissionsPage(appState: appState)
    default:
      EmptyView()
    }
  }

  private var sectionScrollView: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(spacing: 0) {
          // The pane's own heading. Open Runde at display size — the one run on this surface above
          // `Font.inkDisplayThreshold`, which is what decides the face; everything below it stays SF
          // Pro, because that is what a native macOS app sets a settings pane in.
          HStack {
            Text(selectedSection.displayTitle)
              .inkStyle(.stepHeadline, color: Ink.primary)
              .id(selectedSection)
              .transition(.opacity)
              .omiAnimation(.easeInOut(duration: 0.15), value: selectedSection)

            Spacer()
          }
          .padding(.horizontal, SettingsGlassMetrics.paneHorizontalPadding)
          .padding(.top, SettingsGlassMetrics.paneTopPadding)
          .padding(.bottom, SettingsGlassMetrics.sectionSpacing)

          SettingsContentView(
            appState: appState,
            selectedSection: $selectedSection,
            highlightedSettingId: $highlightedSettingId,
            chatProvider: chatProvider,
            showResetOnboardingConfirm: $showResetOnboardingConfirm
          )
          .padding(.horizontal, SettingsGlassMetrics.paneHorizontalPadding)
          .padding(.bottom, SettingsGlassMetrics.paneBottomPadding)

          Spacer()
        }
      }
      .onChange(of: highlightedSettingId) { _, newId in
        guard let newId = newId else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
          OmiMotion.withGated(.easeInOut(duration: 0.3)) {
            proxy.scrollTo(newId, anchor: .center)
          }
        }
      }
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
  @State var screenCaptureHealth: ScreenCaptureHealth
  @State var isToggling: Bool = false
  @State var permissionError: String?

  // Ask Omi floating bar state
  @State var showAskOmiBar: Bool = false

  // Grant for chat screenshot tools (capture_screen / get_screenshot);
  // read by ChatToolExecutor.physicalExecutionPrecondition. Default on.
  @AppStorage(DefaultsKey.chatScreenshotSharingEnabled.rawValue)
  var chatScreenshotSharingEnabled: Bool = true

  // Offline cache of the server's `meeting_note_screenshots_enabled` account setting; read
  // synchronously by MeetingNoteScreenshotsFeature.isEnabled so the feature gate never blocks on
  // the network. The account setting itself (GET/PATCH `v1/screen-frame-egress/settings`) is
  // authoritative — see `loadMeetingNoteScreenshotsSetting()` /
  // `updateMeetingNoteScreenshotsSetting(enabled:)` in SettingsContentView+Rewind.swift. Default on.
  @AppStorage(DefaultsKey.meetingNoteScreenshotsEnabled.rawValue)
  var meetingNoteScreenshotsEnabled: Bool = true

  // Guards against the read-on-appear (`loadMeetingNoteScreenshotsSetting`) reconciling
  // `meetingNoteScreenshotsEnabled` with the server's value from also being mistaken for a user
  // edit and PATCHed straight back — see the toggle's `onChange` in SettingsContentView+Rewind.swift.
  @State var isSyncingMeetingNoteScreenshotsFromServer = false

  // The sole ambient-audio preference. Runtime activity remains on AppState.
  @AppStorage(AssistantSettings.audioRecordingModeDefaultsKey) var audioRecordingModeRaw =
    AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue

  // Log export state

  // Focus Assistant states
  @State var glowOverlayEnabled: Bool
  @State var analysisDelay: Int
  @State var liveSuggestionsEnabled: Bool

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

  // Meeting summary share notification
  @State var meetingSummaryNotificationsEnabled: Bool

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

  // Tier gating (0 = show all, 1-6 = sequential tiers)
  @AppStorage("currentTierLevel") var currentTierLevel = 0

  // Advanced stats
  @State var advancedStats: UserStats?
  @State var isLoadingStats = false
  @State var chatMessageCount: Int?
  @State var isLoadingChatMessages = false
  // Persisted, because the copy beside it promises to "keep … hidden until you need them" — a
  // promise a plain `@State` breaks at the next relaunch, and re-hiding a panel every session is
  // the opposite of what the control offers.
  @AppStorage("settingsShowProfileAndStats") var showProfileAndStats = false

  // AI User Profile
  @State var aiProfileId: Int64?
  @State var aiProfileText: String?
  @State var aiProfileGeneratedAt: Date?
  @State var aiProfileDataSourcesUsed: Int = 0
  @State var isGeneratingAIProfile = false
  @State var isEditingAIProfile = false
  @State var aiProfileEditText: String = ""

  // Selected section (passed in from parent)
  @Binding var selectedSection: SettingsSection
  @Binding var highlightedSettingId: String?

  // Notification settings (from backend)
  @State var dailySummaryEnabled: Bool = true
  @State var dailySummaryHour: Int = 22
  // UI-only date for the Summary Time stepper field; the backend stores whole hours,
  // so this glides freely while only the hour component is persisted.
  @State var dailySummaryTime: Date = SettingsControlMetrics.dailySummaryDate(
    forHour: 22, referenceDate: Date())
  @State var notificationsEnabled: Bool = NotificationService.areNotificationsEnabled()
  // Start from the synchronous persisted mirror so reopening Settings never flashes
  // Balanced while the authoritative backend value is still hydrating.
  @State var notificationFrequency: Int = NotificationService.currentFrequencyLevel()

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
  // 10s, 1min, 5min, 10min, 30min, 1hr. Three rungs — 10s, 10min, 1hr — was not a ladder: the gap
  // from "ten seconds" to "ten minutes" is the whole usable range of this setting, and any value in
  // between (the default 600 aside) had no position at all, which is what made an off-list value
  // land the handle on rung 0. The endpoints are unchanged so no stored setting moves.
  //
  // There is deliberately no zero here. This slider answers "how often", and a frequency has no off
  // position — the card's own switch above it is the off switch, and it is the one that stops the
  // model calls. A `0` would also have to mean "never" to three assistant loops that read it as
  // "immediately", which is the opposite of what the number says.
  let extractionIntervalOptions: [Double] = [10.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]
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

  // Multi-chat mode setting
  @AppStorage("multiChatEnabled") var multiChatEnabled = false
  @AppStorage("conversationsCompactView") var conversationsCompactView = true
  @AppStorage("useLegacyHomeDesign") var useLegacyHomeDesign = false
  @AppStorage("useOldestHomeDesign") var useOldestHomeDesign = false
  @AppStorage("speakNotificationsAloud") var speakNotificationsAloud = false
  @AppStorage(DefaultsKey.integrationNudgesEnabled.rawValue) var integrationNudgesEnabled = true

  // AI Chat settings
  @AppStorage("chatBridgeMode") var chatBridgeMode: String = "piMono"
  @AppStorage("realtimeOmniProvider") var realtimeOmniProvider: String = RealtimeOmniProvider.auto.rawValue
  @AppStorage("askModeEnabled") var askModeEnabled = false
  @AppStorage("aiChatWorkingDirectory") var aiChatWorkingDirectory: String = ""
  @State var aiChatClaudeMdContent: String?
  @State var aiChatClaudeMdPath: String?
  @State var aiChatProjectClaudeMdContent: String?
  @State var aiChatProjectClaudeMdPath: String?
  @State var aiChatDiscoveredSkills: [(name: String, description: String, path: String)] =
    []
  @State var aiChatProjectDiscoveredSkills: [(name: String, description: String, path: String)] = []
  @State var aiChatDisabledSkills: Set<String> = []
  @State var showFileViewer = false
  @State var fileViewerContent = ""
  @State var fileViewerTitle = ""
  @State var skillSearchQuery = ""

  // Dev Mode setting
  @AppStorage("devModeEnabled") var devModeEnabled = false
  @AppStorage(BetaEnhancedDiagnosticsConfiguration.defaultsKey) var betaEnhancedDiagnosticsEnabled = true

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
    case referral = "Refer a Friend"
    case about = "About"
    /// The established page that had no door. It was only ever written by the sidebar the glass
    /// shell stopped rendering, so `PermissionsPage` kept working with nothing on screen that
    /// reached it. It is a section rather than a new pill because it was already dressed as a
    /// settings pane — it lays itself out in `SettingsGlassMetrics.pane*` padding and the settings
    /// card corner — and because the bar's gear already promises "permissions, capture, account".
    /// See `presentedPage`.
    case permissions = "Permissions"

    /// The established page this section presents *whole*, instead of a column of settings rows.
    ///
    /// This is the value `ShellDestination.unreachable()` checks, and the reason a row here is a
    /// door rather than a second version of the page (INV-NAV-1): the section mounts the same
    /// `PermissionsPage` the shell's own route does, never a trimmed copy of it. `SettingsPage`
    /// reads it to skip the shared scroll view and pane heading, which that page already carries
    /// itself.
    var presentedPage: ShellDestination? {
      switch self {
      case .permissions: return .permissions
      default: return nil
      }
    }

    /// Label shown in the settings sidebar and page header. Merged sections
    /// (Account + Plan and Usage, Notifications + Privacy) share one nav item,
    /// so both cases surface the combined title. Raw values stay untouched —
    /// they are the automation contract (`selectedSettingsSection` snapshots,
    /// `omi-ctl navigate settings <section>`, e2e flow waits).
    var displayTitle: String {
      switch self {
      case .account, .planUsage: return "Account & Plan"
      case .notifications, .privacy: return "Notifications & Privacy"
      default: return rawValue
      }
    }

    /// The sidebar nav entry that represents this section. Legacy deep-link
    /// targets (`privacy`, `planUsage`) remain routable but highlight their
    /// merged sidebar item.
    var sidebarItem: SettingsSection {
      switch self {
      case .planUsage: return .account
      case .privacy: return .notifications
      default: return self
      }
    }

    /// Resolve an automation-supplied section name tolerantly (SET-01). The raw values
    /// are Title Case with spaces ("Plan and Usage"), but `omi-ctl navigate settings
    /// <section>` sends whatever the caller typed — the documented examples are
    /// lowercase (`settings rewind`), so a strict `init(rawValue:)` never matched and
    /// navigation silently stayed on General. Accepts the exact raw value, any
    /// case/spacing/hyphen/underscore variant of it, or the Swift case name
    /// (`planUsage`, `floating_bar`, "plan-and-usage", …).
    nonisolated static func automationMatch(_ raw: String) -> SettingsSection? {
      if let exact = SettingsSection(rawValue: raw) { return exact }
      let key = normalizedAutomationKey(raw)
      guard !key.isEmpty else { return nil }
      return allCases.first { section in
        normalizedAutomationKey(section.rawValue) == key
          || normalizedAutomationKey(String(describing: section)) == key
      }
    }

    /// Lowercase and strip everything but letters/digits, so "Plan and Usage",
    /// "plan_usage", "plan-and-usage", and "planUsage" can meet in one keyspace.
    private nonisolated static func normalizedAutomationKey(_ value: String) -> String {
      String(value.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) })
        .lowercased()
    }
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
      case .insightAssistant: return ProactiveNotificationBadge.insightSystemImage
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

  /// Raised by the Reset Onboarding card here; **presented by `SettingsPage`**, which owns a surface
  /// this scrolling column does not — see the property there.
  @Binding var showResetOnboardingConfirm: Bool
  @State var showRescanFilesAlert: Bool = false
  @State var showDeleteAccountAlert: Bool = false

  // Gmail Reader states
  @State var gmailEmails: [GmailEmail] = []
  @State var isReadingGmail: Bool = false
  @State var isSavingGmailMemories: Bool = false
  @State var gmailMemoriesSaved: Int = 0
  @State var gmailReadError: String?
  @State var gmailLastFetched: Date?
  @State var gmailReadGeneration = 0
  @State var gmailAccounts: [GmailAccountOption] = []
  @State var isProbingGmailAccounts: Bool = false
  @State var showingGmailAccountPicker: Bool = false

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
  @AppStorage("dev_openrouter_api_key") var devOpenRouterKey: String = ""
  @AppStorage("dev_deepgram_api_key") var devDeepgramKey: String = ""
  @AppStorage(DefaultsKey.byokLLMProvider.rawValue) var devBYOKLLMProvider: String = ""
  @State var byokKeyStatuses: [BYOKProvider: BYOKValidator.Status] = [:]
  @State var byokActivationError: String?

  init(
    appState: AppState,
    selectedSection: Binding<SettingsSection>,
    highlightedSettingId: Binding<String?> = .constant(nil),
    chatProvider: ChatProvider? = nil,
    showResetOnboardingConfirm: Binding<Bool>
  ) {
    self.appState = appState
    self._selectedSection = selectedSection
    self._highlightedSettingId = highlightedSettingId
    self.chatProvider = chatProvider
    self._showResetOnboardingConfirm = showResetOnboardingConfirm
    let settings = AssistantSettings.shared
    _isMonitoring = State(initialValue: ProactiveAssistantsPlugin.shared.isMonitoring)
    _screenCaptureHealth = State(initialValue: ProactiveAssistantsPlugin.shared.screenCaptureHealth)
    _glowOverlayEnabled = State(initialValue: settings.glowOverlayEnabled)
    _analysisDelay = State(initialValue: settings.analysisDelay)
    _liveSuggestionsEnabled = State(initialValue: SuggestionAssistantSettings.shared.isEnabled)
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
    _meetingSummaryNotificationsEnabled = State(
      initialValue: MeetingSummaryNotificationSettings.isEnabled)
    _memoryExcludedApps = State(initialValue: MemoryAssistantSettings.shared.excludedApps)
    _vadGateEnabled = State(initialValue: settings.vadGateEnabled)
    _transcriptionLanguage = State(initialValue: settings.transcriptionLanguage)
    _transcriptionAutoDetect = State(initialValue: settings.transcriptionAutoDetect)
  }

  /// Computed status text for notifications — OS permission/banner mirror only.
  /// Product proactive enablement is owned by Notifications & Privacy.
  var notificationStatusText: String {
    SettingsControlMetrics.generalNotificationPermissionStatusText(
      hasPermission: appState.hasNotificationPermission,
      bannersDisabled: appState.isNotificationBannerDisabled)
  }

  /// Divider header used when two legacy sections are stacked on one merged
  /// settings page (visually mirrors `advancedCategoryHeader` but lives here so
  /// routing does not depend on the Sections content files).
  func mergedSectionHeader(title: String, icon: String) -> some View {
    HStack(spacing: SettingsGlassMetrics.rowContentSpacing) {
      SettingsIconTile(symbol: icon)
      Text(title)
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Spacer()
    }
    .padding(.top, SettingsGlassMetrics.sectionSpacing)
  }

  var body: some View {
    VStack(spacing: OmiSpacing.xxl) {
      // Section content
      Group {
        switch selectedSection {
        case .general:
          generalSection
        case .rewind:
          rewindSection
        case .transcription:
          transcriptionSection
        case .notifications, .privacy:
          notificationsSection
          mergedSectionHeader(title: "Privacy", icon: "lock.shield")
          privacySection
        case .account, .planUsage:
          accountSection
          mergedSectionHeader(title: "Plan and Usage", icon: "creditcard")
          planUsageSection
        case .aiChat:
          aiChatSection
        case .floatingBar:
          floatingBarSection
        case .shortcuts:
          shortcutsSection
        case .advanced:
          advancedSection
        case .referral:
          referralSection
        case .about:
          aboutSection
        case .permissions:
          // Presenting sections never reach here — `SettingsPage` mounts the whole page they
          // present before it builds this pane. Listed explicitly rather than under a `default`
          // so a new section still has to say what it renders.
          EmptyView()
        }
      }
      .id(selectedSection)
      .transition(.opacity)
      .omiAnimation(.easeInOut(duration: 0.15), value: selectedSection)
    }
    .onAppear {
      if AppBuild.isProductionBundle && selectedSection == .aiChat {
        selectedSection = .advanced
      }
      loadBackendSettings()
      loadSubscriptionInfo()
      // Sync floating bar state with persisted preference (not transient visibility)
      showAskOmiBar = FloatingControlBarManager.shared.isEnabled
      playwrightExtensionToken =
        UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
      chatProvider?.checkClaudeConnectionStatus()
      // Refresh notification permission state
      appState.checkNotificationPermission()
      screenCaptureHealth = ProactiveAssistantsPlugin.shared.screenCaptureHealth
    }
    .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) {
      notification in
      if let userInfo = notification.userInfo, let state = userInfo["isMonitoring"] as? Bool {
        isMonitoring = state
      }
      screenCaptureHealth = ProactiveAssistantsPlugin.shared.screenCaptureHealth
    }
    .onChange(of: selectedSection) { _, newValue in
      if AppBuild.isProductionBundle && newValue == .aiChat {
        selectedSection = .advanced
        return
      }
      if newValue == .planUsage || newValue == .account {
        // Plan and Usage now renders on the merged "Account & Plan" page, so
        // entering via either section id must refresh billing state.
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
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      // Refresh notification permission when app becomes active (user may have changed it in System Settings)
      appState.refreshNotificationPermissionAfterSystemSettings()
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
