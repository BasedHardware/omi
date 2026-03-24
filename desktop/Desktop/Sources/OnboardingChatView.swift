import GRDB
import MarkdownUI
import SwiftUI

// MARK: - Onboarding Chat Persistence

/// Persists onboarding state across app restarts (e.g. screen recording permission requires restart).
/// Messages are stored on the backend via the normal chat save path — only the ACP session ID
/// and a mid-onboarding flag are kept in UserDefaults for restart recovery.
enum OnboardingChatPersistence {
  private static let sessionIdKey = "onboardingACPSessionId"
  private static let midOnboardingKey = "onboardingMidOnboarding"
  private static let explorationTextKey = "onboardingExplorationText"
  private static let explorationCompletedKey = "onboardingExplorationCompleted"
  private static let toolCompletedKey = "onboardingToolCompleted"
  private static let goalCompletedKey = "onboardingGoalCompleted"

  /// Save the ACP session ID for resume after restart
  static func saveSessionId(_ sessionId: String) {
    UserDefaults.standard.set(sessionId, forKey: sessionIdKey)
  }

  /// Load the saved ACP session ID
  static func loadSessionId() -> String? {
    UserDefaults.standard.string(forKey: sessionIdKey)
  }

  /// Mark that onboarding is in progress (for restart detection)
  static func saveMidOnboarding() {
    UserDefaults.standard.set(true, forKey: midOnboardingKey)
  }

  /// Whether the app was restarted mid-onboarding
  static var isMidOnboarding: Bool {
    UserDefaults.standard.bool(forKey: midOnboardingKey)
  }

  // MARK: - Exploration Persistence

  /// Save exploration state so it survives app restarts
  static func saveExplorationState(text: String, completed: Bool) {
    UserDefaults.standard.set(text, forKey: explorationTextKey)
    UserDefaults.standard.set(completed, forKey: explorationCompletedKey)
  }

  /// Load saved exploration state (returns nil if no exploration was saved)
  static func loadExplorationState() -> (text: String, completed: Bool)? {
    let text = UserDefaults.standard.string(forKey: explorationTextKey) ?? ""
    let completed = UserDefaults.standard.bool(forKey: explorationCompletedKey)
    guard !text.isEmpty || completed else { return nil }
    return (text, completed)
  }

  /// Whether exploration already completed in a prior session
  static var isExplorationCompleted: Bool {
    UserDefaults.standard.bool(forKey: explorationCompletedKey)
  }

  // MARK: - Tool Completion

  /// Mark that `complete_onboarding` tool was called (so button shows on restart)
  static func markToolCompleted() {
    UserDefaults.standard.set(true, forKey: toolCompletedKey)
  }

  /// Whether `complete_onboarding` was already called in a prior session
  static var isToolCompleted: Bool {
    UserDefaults.standard.bool(forKey: toolCompletedKey)
  }

  /// Mark that the user answered the monthly goal question
  static func markGoalCompleted() {
    UserDefaults.standard.set(true, forKey: goalCompletedKey)
  }

  /// Whether the user already answered the monthly goal question
  static var isGoalCompleted: Bool {
    UserDefaults.standard.bool(forKey: goalCompletedKey)
  }

  /// Clear all persisted onboarding data
  static func clear() {
    UserDefaults.standard.removeObject(forKey: sessionIdKey)
    UserDefaults.standard.removeObject(forKey: midOnboardingKey)
    UserDefaults.standard.removeObject(forKey: explorationTextKey)
    UserDefaults.standard.removeObject(forKey: explorationCompletedKey)
    UserDefaults.standard.removeObject(forKey: toolCompletedKey)
    UserDefaults.standard.removeObject(forKey: goalCompletedKey)
    // Clean up legacy messages key if present
    UserDefaults.standard.removeObject(forKey: "onboardingChatMessages")
  }
}

// MARK: - Onboarding Chat View

struct OnboardingChatView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var graphViewModel: MemoryGraphViewModel?
  var onComplete: () -> Void
  var onSkip: () -> Void

  @State private var inputText: String = ""
  @State private var hasStarted: Bool = false
  @State private var onboardingCompleted: Bool = false
  @State private var quickReplyOptions: [String] = []
  @State private var quickReplyQuestion: String = ""
  @State private var isTaskSelectionFollowup: Bool = false
  @State private var awaitingGoalInput: Bool = false
  @State private var awaitingDailyTaskInput: Bool = false
  @State private var createdGoalTitles: Set<String> = []
  @State private var createdTaskTitles: Set<String> = []
  @State private var isGrantingPermission: Bool = false
  @State private var pendingPermissionType: String? = nil  // e.g. "microphone" — waiting for user to grant
  @FocusState private var isInputFocused: Bool

  // Parallel exploration state
  @State private var explorationBridge: ACPBridge?
  @State private var explorationRunning = false
  @State private var explorationCompleted = false
  @State private var explorationText = ""
  @State private var explorationTask: Task<Void, Never>?

  // Gmail reading state (runs alongside exploration during onboarding)
  @State private var gmailReadingRunning = false
  @State private var gmailReadingCompleted = false
  @State private var gmailReadingText = ""
  @State private var gmailReadingTask: Task<Void, Never>?

  // Calendar reading state (runs alongside exploration during onboarding)
  @State private var calendarReadingRunning = false
  @State private var calendarReadingCompleted = false
  @State private var calendarReadingText = ""
  @State private var calendarReadingTask: Task<Void, Never>?

  @State private var showSkipConfirmation = false
  @State private var recoveredOnboardingFallbackTask: Task<Void, Never>?

  // Permission help notification state — shows a floating bar hint if user struggles
  @State private var permissionHelpShown: Set<String> = []
  @State private var permissionHelpTimer: DispatchWorkItem? = nil

  // Timer to periodically check permission status
  let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        if let logoImage = whiteTemplateLogoImage() {
          Image(nsImage: logoImage)
            .resizable()
            .renderingMode(.template)
            .foregroundColor(.white)
            .scaledToFit()
            .frame(width: 52, height: 18)
            .accessibilityLabel("omi")
        } else {
          Text("omi")
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(.white)
        }

        Spacer()

        Button(action: { showSkipConfirmation = true }) {
          Text("Skip")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .alert("Are you sure?", isPresented: $showSkipConfirmation) {
          Button("Skip anyway", role: .destructive) { onSkip() }
          Button("Continue setup", role: .cancel) {}
        } message: {
          Text("Omi won't be useful for you if it doesn't know enough about you.")
        }
      }
      .padding(.horizontal, 24)
      .padding(.vertical, 16)

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Chat messages
      ScrollViewReader { proxy in
        ScrollView {
          VStack(spacing: 16) {
            ForEach(chatProvider.messages) { message in
              OnboardingChatBubble(
                message: message,
                hidePermissionImages: !quickReplyOptions.isEmpty || pendingPermissionType != nil
                  || awaitingGoalInput
              )
              .id(message.id)
            }

            // Parallel exploration card (appears after scan_files)
            if !shouldHideExplorationCard
              && (explorationRunning || (explorationCompleted && !explorationText.isEmpty))
            {
              ExplorationProfileCard(
                text: explorationText,
                isRunning: explorationRunning,
                isCompleted: explorationCompleted
              )
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.leading, 44)  // align with message text
              .id("exploration-card")
            }

            // Gmail insights card (appears alongside exploration)
            if !shouldHideExplorationCard
              && (gmailReadingRunning || (gmailReadingCompleted && !gmailReadingText.isEmpty))
            {
              GmailInsightsCard(
                text: gmailReadingText,
                isRunning: gmailReadingRunning,
                isCompleted: gmailReadingCompleted
              )
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.leading, 44)
              .id("gmail-card")
            }

            // Calendar insights card (appears alongside exploration)
            if !shouldHideExplorationCard
              && (calendarReadingRunning
                || (calendarReadingCompleted && !calendarReadingText.isEmpty))
            {
              CalendarInsightsCard(
                text: calendarReadingText,
                isRunning: calendarReadingRunning,
                isCompleted: calendarReadingCompleted
              )
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.leading, 44)
              .id("calendar-card")
            }

            // Typing indicator (floating, no avatar)
            if chatProvider.isSending {
              TypingIndicator()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 44)  // align with message text (32px avatar + 12px spacing)
                .id("typing")
            }

            // Quick reply buttons
            if !quickReplyOptions.isEmpty && !chatProvider.isSending {
              if !quickReplyQuestion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(quickReplyQuestion)
                  .font(.system(size: 14, weight: .medium))
                  .foregroundColor(OmiColors.textPrimary)
                  .frame(maxWidth: .infinity, alignment: .leading)
                  .padding(.leading, 44)
              }

              // Show permission media for permission-related quick replies, including
              // post-request follow-ups like "Done with Screen Recording?"
              if let permType = permissionType(for: quickReplyQuestion, options: quickReplyOptions)
              {
                OnboardingPermissionImage(permissionType: permType)
                  .frame(maxWidth: .infinity, alignment: .leading)
                  .padding(.leading, 44)
              }

              HStack(spacing: 8) {
                ForEach(quickReplyOptions, id: \.self) { option in
                  Button(action: {
                    handleQuickReply(option)
                  }) {
                    Text(option)
                      .font(.system(size: 13, weight: .medium))
                      .foregroundColor(isGrantButton(option) ? .white : OmiColors.purplePrimary)
                      .padding(.horizontal, 16)
                      .padding(.vertical, 8)
                      .background(
                        isGrantButton(option)
                          ? OmiColors.purplePrimary
                          : OmiColors.purplePrimary.opacity(0.1)
                      )
                      .cornerRadius(20)
                      .overlay(
                        RoundedRectangle(cornerRadius: 20)
                          .stroke(OmiColors.purplePrimary.opacity(0.3), lineWidth: 1)
                      )
                  }
                  .buttonStyle(.plain)
                  .disabled(isGrantingPermission)
                }
              }
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.leading, 44)  // align with message text
              .id("quick-replies")
            }

            // Retry "Open System Settings" button — shown when a permission grant
            // is pending but System Settings didn't open (or user closed it)
            if let pending = pendingPermissionType,
              quickReplyOptions.isEmpty && !chatProvider.isSending
            {
              let isStillPending: Bool = {
                switch pending {
                case "screen_recording": return !appState.hasScreenRecordingPermission
                case "microphone": return !appState.hasMicrophonePermission
                case "notifications": return !appState.hasNotificationPermission
                case "accessibility": return !appState.hasAccessibilityPermission
                case "automation": return !appState.hasAutomationPermission
                case "full_disk_access": return !appState.hasFullDiskAccess
                default: return false
                }
              }()
              if isStillPending {
                OnboardingPermissionImage(permissionType: pending)
                  .frame(maxWidth: .infinity, alignment: .leading)
                  .padding(.leading, 44)

                Button(action: {
                  openSettingsForPermission(pending)
                }) {
                  HStack(spacing: 6) {
                    Image(systemName: "gear")
                      .font(.system(size: 12))
                    Text("Open \(permissionLabel(pending)) Settings")
                      .font(.system(size: 13, weight: .medium))
                  }
                  .foregroundColor(.white)
                  .padding(.horizontal, 16)
                  .padding(.vertical, 8)
                  .background(OmiColors.purplePrimary)
                  .cornerRadius(20)
                }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 44)
              }
            }

            // "Continue" button — shown only after AI calls complete_onboarding
            // and no pending questions or permissions remain.
            if onboardingCompleted && !chatProvider.isSending && quickReplyOptions.isEmpty
              && pendingPermissionType == nil
            {
              Button(action: {
                handleOnboardingComplete()
              }) {
                Text("Continue")
                  .font(.system(size: 15, weight: .semibold))
                  .foregroundColor(.white)
                  .frame(maxWidth: 220)
                  .padding(.vertical, 12)
                  .background(OmiColors.purplePrimary)
                  .cornerRadius(12)
              }
              .buttonStyle(.plain)
              .padding(.top, 12)
            }

            // Extra spacing so quick replies / buttons don't sit against the input field
            Spacer().frame(height: 20)
          }
          .padding(20)

          // Invisible anchor at the very bottom — always scroll to this
          // (same pattern as ChatMessagesView)
          Color.clear
            .frame(height: 1)
            .id("bottom-anchor")
        }
        .onChange(of: chatProvider.messages.count) { _, _ in
          scrollToBottom(proxy: proxy)
        }
        .onChange(of: chatProvider.messages.last?.text) { _, _ in
          scrollToBottom(proxy: proxy)
        }
        .onChange(of: chatProvider.messages.last?.contentBlocks.count) { _, _ in
          // Multiple scroll attempts: first for the text/indicator layout,
          // second for images/GIFs that load asynchronously and add height
          scrollToBottom(proxy: proxy, delay: 0.15)
          scrollToBottom(proxy: proxy, delay: 0.6)
        }
        .onChange(of: chatProvider.isSending) { _, _ in
          scrollToBottom(proxy: proxy)
        }
        .onChange(of: quickReplyOptions) { _, _ in
          scrollToBottom(proxy: proxy, delay: 0.1)
        }
        .onChange(of: explorationRunning) { _, running in
          if running {
            scrollToBottom(proxy: proxy, delay: 0.2)
          }
        }
        .onChange(of: explorationCompleted) { _, completed in
          if completed {
            scrollToBottom(proxy: proxy, delay: 0.2)
          }
        }
      }

      // Input area
      HStack(spacing: 12) {
        TextField(
          quickReplyOptions.isEmpty ? "Type your message..." : "Or type your own answer...",
          text: $inputText, axis: .vertical
        )
        .textFieldStyle(.plain)
        .font(.system(size: 14))
        .foregroundColor(OmiColors.textPrimary)
        .focused($isInputFocused)
        .padding(12)
        .lineLimit(1...3)
        .onSubmit {
          sendMessage()
        }
        .frame(maxWidth: .infinity)
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(20)

        if chatProvider.isSending
          && inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        {
          // Stop button when AI is responding and input is empty
          Button(action: stopAgent) {
            Image(systemName: chatProvider.isStopping ? "ellipsis.circle" : "stop.circle.fill")
              .font(.system(size: 32))
              .foregroundColor(OmiColors.purplePrimary)
          }
          .buttonStyle(.plain)
          .disabled(chatProvider.isStopping)
        } else {
          Button(action: sendMessage) {
            Image(systemName: "arrow.up.circle.fill")
              .font(.system(size: 32))
              .foregroundColor(canSend ? OmiColors.purplePrimary : OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .disabled(!canSend)
        }
      }
      .padding(.horizontal, 20)
      .padding(.vertical, 16)
    }
    .onAppear {
      startChat()
    }
    .onReceive(permissionCheckTimer) { _ in
      appState.checkNotificationPermission()
      appState.checkScreenRecordingPermission()
      appState.checkMicrophonePermission()
      appState.checkAccessibilityPermission()
      appState.checkAutomationPermission()
      appState.checkFullDiskAccess()
    }
    // When a pending permission is granted, bring app to front and notify the AI
    .onChange(of: appState.hasScreenRecordingPermission) { _, granted in
      if granted { handlePermissionGranted("screen_recording", label: "Screen Recording") }
    }
    .onChange(of: appState.hasMicrophonePermission) { _, granted in
      if granted { handlePermissionGranted("microphone", label: "Microphone") }
    }
    .onChange(of: appState.hasNotificationPermission) { _, granted in
      if granted { handlePermissionGranted("notifications", label: "Notifications") }
    }
    .onChange(of: appState.hasAccessibilityPermission) { _, granted in
      if granted { handlePermissionGranted("accessibility", label: "Accessibility") }
    }
    .onChange(of: appState.hasAutomationPermission) { _, granted in
      if granted { handlePermissionGranted("automation", label: "Automation") }
    }
    .onChange(of: appState.hasFullDiskAccess) { _, granted in
      if granted { handlePermissionGranted("full_disk_access", label: "Full Disk Access") }
    }
    .onChange(of: chatProvider.isSending) { _, isSending in
      if isSending {
        cancelRecoveredOnboardingFallback()
      } else {
        scheduleRecoveredOnboardingFallback()
      }
    }
    .onChange(of: quickReplyOptions) { _, newOptions in
      scheduleRecoveredOnboardingFallback()
      // Detect permission-related quick replies (e.g. "Done!" after FDA request, or "Grant Mic")
      // and start the help timer even when pendingPermissionType isn't set
      if !newOptions.isEmpty,
        let detectedPerm = permissionType(for: quickReplyQuestion, options: newOptions)
      {
        schedulePermissionHelpTimer(for: detectedPerm)
      }
    }
    .onChange(of: pendingPermissionType) { _, newValue in
      scheduleRecoveredOnboardingFallback()
      schedulePermissionHelpTimer(for: newValue)
    }
    .onChange(of: explorationRunning) { _, _ in
      scheduleRecoveredOnboardingFallback()
    }
    .onChange(of: explorationCompleted) { _, _ in
      scheduleRecoveredOnboardingFallback()
    }
  }

  @ViewBuilder
  private var omiAvatar: some View {
    if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
      let logoImage = NSImage(contentsOf: logoURL)
    {
      Image(nsImage: logoImage)
        .resizable()
        .scaledToFit()
        .frame(width: 20, height: 20)
        .frame(width: 32, height: 32)
        .background(OmiColors.backgroundTertiary)
        .clipShape(Circle())
    }
  }

  /// Human-readable label for a permission type
  private func permissionLabel(_ type: String) -> String {
    switch type {
    case "screen_recording": return "Screen Recording"
    case "microphone": return "Microphone"
    case "accessibility": return "Accessibility"
    case "automation": return "Automation"
    case "notifications": return "Notification"
    case "full_disk_access": return "Full Disk Access"
    default: return "System"
    }
  }

  /// Open System Settings to the correct pane for a permission type
  private func openSettingsForPermission(_ type: String) {
    let urlString: String? = {
      switch type {
      case "screen_recording":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
      case "microphone":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
      case "accessibility":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
      case "automation":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
      case "notifications":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_Notifications"
      case "full_disk_access":
        return "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
      default:
        return nil
      }
    }()
    if let urlString, let url = URL(string: urlString) {
      NSWorkspace.shared.open(url)
    }
  }

  /// Called when a permission is detected as granted (by the 1s timer)
  private func handlePermissionGranted(_ type: String, label: String) {
    bringToFront()
    // If this was the permission we were waiting for, notify the AI
    if pendingPermissionType == type {
      pendingPermissionType = nil
      Task {
        await chatProvider.sendMessage("Grant \(label) — done!")
      }
    }
  }

  private var canSend: Bool {
    !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !chatProvider.isSending
  }

  // MARK: - Scroll

  private func scrollToBottom(proxy: ScrollViewProxy, delay: TimeInterval = 0) {
    if delay > 0 {
      DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
        withAnimation { proxy.scrollTo("bottom-anchor", anchor: .bottom) }
      }
    } else {
      withAnimation { proxy.scrollTo("bottom-anchor", anchor: .bottom) }
    }
  }

  // MARK: - Actions

  private func startChat() {
    guard !hasStarted else { return }
    hasStarted = true
    isInputFocused = true

    // Set up floating bar so permission help notifications can be shown
    FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
    FloatingControlBarManager.shared.showTemporarily()

    // Wire up onboarding tools
    ChatToolExecutor.onboardingAppState = appState
    ChatToolExecutor.onCompleteOnboarding = {
      onboardingCompleted = true
    }
    ChatToolExecutor.onQuickReplyOptions = { options in
      quickReplyOptions = options
      if options.isEmpty {
        quickReplyQuestion = ""
        isTaskSelectionFollowup = false
      }
      let hasTypedOption = options.contains(where: { isTypeYourOwnOption($0) })
      awaitingGoalInput = hasTypedOption && isGoalPriorityQuestion(quickReplyQuestion)
      isTaskSelectionFollowup = shouldTreatAsTaskSelection(
        question: quickReplyQuestion, options: options)
      awaitingDailyTaskInput = hasTypedOption && isTaskSelectionFollowup
    }
    ChatToolExecutor.onQuickReplyQuestion = { question in
      quickReplyQuestion = question
      awaitingGoalInput = isGoalPriorityQuestion(question)
      isTaskSelectionFollowup = shouldTreatAsTaskSelection(
        question: question, options: quickReplyOptions)
      awaitingDailyTaskInput =
        isTaskSelectionFollowup && quickReplyOptions.contains(where: { isTypeYourOwnOption($0) })
    }
    ChatToolExecutor.onKnowledgeGraphUpdated = { [weak graphViewModel] in
      guard let vm = graphViewModel else { return }
      Task { await vm.addGraphFromStorage() }
    }
    ChatToolExecutor.onPermissionPending = { permType in
      pendingPermissionType = permType
      log("OnboardingChat: Permission pending from tool executor: \(permType)")
    }
    ChatToolExecutor.onScanFilesCompleted = { [weak graphViewModel] fileCount in
      guard fileCount > 0 else { return }
      startExploration(fileCount: fileCount, graphViewModel: graphViewModel)
      startGmailReading()
      startCalendarReading()
    }

    // Build onboarding system prompt
    let userName = AuthService.shared.displayName.isEmpty ? "there" : AuthService.shared.displayName
    let givenName = AuthService.shared.givenName.isEmpty ? userName : AuthService.shared.givenName
    let email = AuthState.shared.userEmail ?? ""

    let systemPrompt = ChatPromptBuilder.buildOnboardingChat(
      userName: userName,
      givenName: givenName,
      email: email
    )

    // Mark as onboarding so ACP session ID gets persisted for restart recovery
    chatProvider.isOnboarding = true

    // Check if we're resuming after a mid-onboarding restart (e.g. screen recording permission)
    if OnboardingChatPersistence.isMidOnboarding {
      let savedSessionId = OnboardingChatPersistence.loadSessionId()
      log("OnboardingChatView: Resuming mid-onboarding, ACP session: \(savedSessionId ?? "none")")

      // If complete_onboarding was already called before restart, show the button immediately
      if OnboardingChatPersistence.isToolCompleted {
        log("OnboardingChatView: complete_onboarding was called before restart, showing button")
        onboardingCompleted = true
      }

      Task {
        // Start bridge eagerly so it's ready by the time we need to send
        async let bridgeWarmup: () = chatProvider.warmupBridge()

        // Load previous messages from backend (same default chat, sessionId=nil)
        await chatProvider.loadDefaultChatMessages()

        // Restore the knowledge graph from local storage (saved before restart)
        if let vm = graphViewModel {
          await vm.addGraphFromStorage()
        }

        // If files are already indexed from prior run, kick off exploration immediately
        await checkAndStartExploration(graphViewModel: graphViewModel)

        // Build a conversation summary so the AI has context even if session/resume fails
        let conversationContext = buildConversationContext(from: chatProvider.messages)
        let resumeSystemPrompt: String
        if conversationContext.isEmpty {
          resumeSystemPrompt = systemPrompt
        } else {
          resumeSystemPrompt =
            systemPrompt + "\n\n<conversation_so_far>\n" + conversationContext
            + "\n</conversation_so_far>\n\nThe user's app just restarted after granting a macOS permission. Continue the onboarding from where you left off — do NOT re-ask questions the user already answered above."
        }

        // Wait for bridge warmup before sending
        await bridgeWarmup

        // Resume the conversation — tell the AI the app was restarted
        let resumeMessage: String
        if OnboardingChatPersistence.isGoalCompleted {
          resumeMessage = "I'm back — the app just restarted after granting a permission. Let's continue where we left off."
        } else {
          resumeMessage = "I'm back — the app just restarted after granting a permission. I haven't set my monthly goal yet — can you help me pick one?"
        }
        await chatProvider.sendMessage(
          resumeMessage,
          systemPromptPrefix: resumeSystemPrompt,
          resume: savedSessionId
        )

        await MainActor.run {
          scheduleRecoveredOnboardingFallback()
        }
      }
    } else if chatProvider.messages.isEmpty {
      // Fresh start — clear stale messages, mark mid-onboarding, begin
      OnboardingChatPersistence.saveMidOnboarding()

      Task {
        await chatProvider.sendMessage(
          "Hi, I just installed omi!",
          systemPromptPrefix: systemPrompt
        )
      }
    }
  }

  private func stopAgent() {
    chatProvider.stopAgent()
  }

  private func cancelRecoveredOnboardingFallback() {
    recoveredOnboardingFallbackTask?.cancel()
    recoveredOnboardingFallbackTask = nil
  }

  private func scheduleRecoveredOnboardingFallback() {
    cancelRecoveredOnboardingFallback()

    guard OnboardingChatPersistence.isMidOnboarding,
      !OnboardingChatPersistence.isToolCompleted,
      !onboardingCompleted
    else { return }

    recoveredOnboardingFallbackTask = Task {
      try? await Task.sleep(for: .seconds(2))
      guard !Task.isCancelled else { return }

      let shouldUnlockContinue = await shouldAutoCompleteRecoveredOnboarding()
      guard shouldUnlockContinue else { return }

      await MainActor.run {
        guard OnboardingChatPersistence.isMidOnboarding,
          !OnboardingChatPersistence.isToolCompleted,
          !onboardingCompleted,
          pendingPermissionType == nil,
          quickReplyOptions.isEmpty,
          !chatProvider.isSending
        else { return }

        log("OnboardingChatView: Auto-unlocking Continue after recovered onboarding went idle")
        onboardingCompleted = true
      }
    }
  }

  private func shouldAutoCompleteRecoveredOnboarding() async -> Bool {
    guard OnboardingChatPersistence.isMidOnboarding,
      !OnboardingChatPersistence.isToolCompleted,
      !onboardingCompleted,
      pendingPermissionType == nil,
      quickReplyOptions.isEmpty,
      !chatProvider.isSending
    else { return false }

    if explorationRunning || explorationCompleted
      || OnboardingChatPersistence.isExplorationCompleted
    {
      return true
    }

    return await FileIndexerService.shared.getIndexedFileCount() > 0
  }

  private func sendMessage() {
    guard canSend else { return }

    let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
    inputText = ""

    // Clear quick replies and unblock any pending ask_followup
    quickReplyOptions = []
    quickReplyQuestion = ""
    isTaskSelectionFollowup = false
    ChatToolExecutor.resumeFollowup(with: text)

    Task {
      if awaitingGoalInput {
        await maybeCreateGoal(from: text, source: "typed")
      }
      if awaitingDailyTaskInput {
        await maybeCreateTask(from: text, source: "typed")
        awaitingDailyTaskInput = false
      }
      await chatProvider.sendMessage(text)
    }
  }

  /// Whether a quick reply option is a "Grant" permission button
  private func isGrantButton(_ option: String) -> Bool {
    option.hasPrefix("Grant ")
  }

  /// Extract permission type from a "Grant [Permission]" button label
  private func permissionType(from option: String) -> String? {
    guard isGrantButton(option) else { return nil }
    let name = String(option.dropFirst("Grant ".count)).lowercased()
    return permissionType(matching: name)
  }

  private func permissionType(for question: String, options: [String]) -> String? {
    if let grantOption = options.first(where: { isGrantButton($0) }),
      let permType = permissionType(from: grantOption)
    {
      return permType
    }

    return permissionType(matching: question.lowercased())
  }

  private func permissionType(matching text: String) -> String? {
    let mapping: [(needle: String, permission: String)] = [
      ("screen recording", "screen_recording"),
      ("full disk access", "full_disk_access"),
      ("disk access", "full_disk_access"),
      ("microphone", "microphone"),
      ("mic", "microphone"),
      ("notifications", "notifications"),
      ("accessibility", "accessibility"),
      ("automation", "automation"),
    ]

    return mapping.first(where: { text.contains($0.needle) })?.permission
  }

  /// Handle quick reply button tap — triggers permission if applicable, then sends as user message
  private func handleQuickReply(_ option: String) {
    let wasTaskSelectionFollowup = isTaskSelectionFollowup
    quickReplyOptions = []
    quickReplyQuestion = ""
    isTaskSelectionFollowup = false

    if let permType = permissionType(from: option) {
      // Grant button — trigger the permission directly
      isGrantingPermission = true
      Task {
        let result = await ChatToolExecutor.execute(
          ToolCall(name: "request_permission", arguments: ["type": permType], thoughtSignature: nil)
        )
        isGrantingPermission = false

        if result.contains("granted") {
          // Granted immediately — tell the AI
          await chatProvider.sendMessage("\(option) — done!")
        } else if result.contains("move omi to /Applications first") {
          await chatProvider.sendMessage(
            "Move omi to Applications, reopen it, then tap Grant Notifications again.")
        } else {
          // Pending — wait silently for the permission check timer to detect it
          // The onChange handlers for appState.has*Permission will send the message
          pendingPermissionType = permType
        }
      }
    } else {
      // Regular quick reply — resume the blocked ask_followup tool, then send as message
      let shouldCreateFromSelection = awaitingGoalInput && !isTypeYourOwnOption(option)
      if shouldCreateFromSelection {
        awaitingGoalInput = false
      } else if isTypeYourOwnOption(option) {
        awaitingGoalInput = true
      }
      let shouldCreateTaskFromSelection = wasTaskSelectionFollowup && !isTypeYourOwnOption(option)
      if shouldCreateTaskFromSelection {
        awaitingDailyTaskInput = false
      } else if isTypeYourOwnOption(option) && wasTaskSelectionFollowup {
        awaitingDailyTaskInput = true
      }
      ChatToolExecutor.resumeFollowup(with: option)
      Task {
        if shouldCreateFromSelection {
          await maybeCreateGoal(from: option, source: "selected")
        }
        if shouldCreateTaskFromSelection {
          await maybeCreateTask(from: option, source: "selected")
        }
        await chatProvider.sendMessage(option)
      }
    }
  }

  private var shouldHideExplorationCard: Bool {
    !quickReplyOptions.isEmpty || pendingPermissionType != nil || awaitingGoalInput
      || awaitingDailyTaskInput
  }

  private func whiteTemplateLogoImage() -> NSImage? {
    guard
      let logoURL = Bundle.resourceBundle.url(forResource: "omi_text_logo", withExtension: "png"),
      let loadedLogoImage = NSImage(contentsOf: logoURL)
    else {
      return nil
    }
    let logoImage = loadedLogoImage.copy() as? NSImage ?? loadedLogoImage
    logoImage.isTemplate = true
    return logoImage
  }

  private func isGoalPriorityQuestion(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("top one goal")
      || lower.contains("top goal")
      || lower.contains("#1 goal")
      || lower.contains("number 1 goal")
      || lower.contains("goal this month")
      || lower.contains("what's your #1 goal")
      || lower.contains("top priority")
      || lower.contains("priority right now")
  }

  private func isDailyTaskQuestion(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("goal for today")
      || lower.contains("tasks for today")
      || lower.contains("task for today")
      || lower.contains("daily goal")
      || lower.contains("today's top task")
      || lower.contains("today top task")
      || lower.contains("daily reminder task")
      || lower.contains("tasks that could help")
      || lower.contains("could help today")
      || lower.contains("what do you want to get done")
      || lower.contains("today's priority")
      || lower.contains("today priority")
      || (lower.contains("set that as") && lower.contains("task"))
  }

  private func isLikelyTaskOption(_ text: String) -> Bool {
    let lower = text.lowercased()
    if isTypeYourOwnOption(text) || lower == "skip" || lower == "why?" || isGrantButton(text) {
      return false
    }
    let taskVerbs = [
      "record", "publish", "ship", "launch", "write", "fix", "review", "design", "test", "send",
      "post", "call", "build", "finish",
    ]
    if taskVerbs.contains(where: { lower.hasPrefix($0 + " ") || lower.contains(" " + $0 + " ") }) {
      return true
    }
    return lower.contains("today")
      || lower.contains("task")
      || lower.contains("goal")
      || lower.contains("per day")
      || lower.contains("daily")
  }

  private func shouldTreatAsTaskSelection(question: String, options: [String]) -> Bool {
    if isDailyTaskQuestion(question) {
      return true
    }
    guard !options.isEmpty else { return false }
    let nonPermission = options.filter { !isGrantButton($0) }
    let likelyTaskOptions = nonPermission.filter { isLikelyTaskOption($0) }
    // Require at least one actionable option and a typed option to avoid false positives
    return !likelyTaskOptions.isEmpty && options.contains(where: { isTypeYourOwnOption($0) })
  }

  private func isTypeYourOwnOption(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("type my own")
      || lower.contains("i'll type my own")
      || lower.contains("i’ll type my own")
      || lower.contains("i'll type it")
      || lower.contains("i’ll type it")
      || lower.contains("type it")
  }

  private func normalizedGoalTitle(_ text: String) -> String {
    text
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: "\n", with: " ")
  }

  private func heuristicGoalTitle(_ text: String) -> String {
    var cleaned = normalizedGoalTitle(text)
    let lower = cleaned.lowercased()
    let prefixes = [
      "my goal is ",
      "goal is ",
      "my goal: ",
      "goal: ",
      "i want to ",
      "i wanna ",
      "i need to ",
      "i will ",
      "i'm going to ",
    ]
    for prefix in prefixes where lower.hasPrefix(prefix) {
      cleaned = String(cleaned.dropFirst(prefix.count))
      break
    }
    return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func fallbackGoalConfig(from title: String) -> (
    goalType: GoalType, targetValue: Double, unit: String?
  ) {
    let lower = title.lowercased()
    let pattern =
      #"\b(\d+(?:\.\d+)?)\s*(k|m|b)?\s*(users?|customers?|clients?|sales?|revenue|downloads?)?\b"#
    if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
      let match = regex.firstMatch(in: lower, range: NSRange(lower.startIndex..., in: lower))
    {
      let numberRange = match.range(at: 1)
      let suffixRange = match.range(at: 2)
      let unitRange = match.range(at: 3)
      if let numberSwiftRange = Range(numberRange, in: lower),
        let baseNumber = Double(lower[numberSwiftRange])
      {
        var multiplier = 1.0
        if let suffixSwiftRange = Range(suffixRange, in: lower) {
          switch lower[suffixSwiftRange] {
          case "k": multiplier = 1_000
          case "m": multiplier = 1_000_000
          case "b": multiplier = 1_000_000_000
          default: break
          }
        }
        let unit: String? = Range(unitRange, in: lower).map { String(lower[$0]) }
        return (.numeric, max(baseNumber * multiplier, 1), unit)
      }
    }

    return (.boolean, 1, nil)
  }

  private func shouldSkipGoalCreation(_ title: String) -> Bool {
    if title.isEmpty {
      return true
    }
    let lower = title.lowercased()
    if lower == "skip" || lower == "done" || lower.contains("type my own") {
      return true
    }
    return false
  }

  private func normalizedTaskTitle(_ text: String) -> String {
    text
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: "\n", with: " ")
  }

  private func cleanedTaskTitle(_ text: String) -> String {
    var cleaned = normalizedTaskTitle(text)
    let lower = cleaned.lowercased()
    let removablePrefixes = [
      "my task is ",
      "task: ",
      "i will ",
      "i'll ",
      "i need to ",
      "today i need to ",
    ]
    for prefix in removablePrefixes where lower.hasPrefix(prefix) {
      cleaned = String(cleaned.dropFirst(prefix.count))
      break
    }

    cleaned = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.hasSuffix(".") {
      cleaned.removeLast()
    }
    return cleaned
  }

  private func shouldSkipTaskCreation(_ title: String) -> Bool {
    if title.isEmpty {
      return true
    }
    let lower = title.lowercased()
    if lower == "skip" || lower == "done" || lower.contains("i'll type")
      || lower.contains("i’ll type")
    {
      return true
    }
    return false
  }

  private func isDailyTask(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("daily")
      || lower.contains("per day")
      || lower.contains("every day")
      || lower.contains("2-videos-per-day")
      || lower.contains("videos per day")
  }

  private func maybeCreateTask(from rawText: String, source: String) async {
    let title = cleanedTaskTitle(rawText)
    guard !shouldSkipTaskCreation(title) else { return }

    let dedupeKey = title.lowercased()
    guard !createdTaskTitles.contains(dedupeKey) else { return }

    let createdTask: TaskActionItem?
    if isDailyTask(rawText) {
      createdTask = await TasksStore.shared.createDailyRecurringTask(
        description: title,
        priority: "medium",
        tags: ["onboarding"]
      )
    } else {
      let dueToday = Calendar.current.startOfDay(for: Date())
      createdTask = await TasksStore.shared.createTask(
        description: title,
        dueAt: dueToday,
        priority: "medium",
        tags: ["onboarding"]
      )
    }

    if createdTask != nil {
      createdTaskTitles.insert(dedupeKey)
      log("OnboardingChat: Created task from onboarding input (\(source)): \(title)")
    } else {
      log("OnboardingChat: Failed to create task from onboarding input (\(source)): \(title)")
    }
  }

  private func maybeCreateGoal(from rawText: String, source: String) async {
    let rawTitle = normalizedGoalTitle(rawText)
    guard !shouldSkipGoalCreation(rawTitle) else { return }

    let aiNormalized = await GoalsAIService.shared.normalizeOnboardingGoalInput(rawTitle)
    let title = aiNormalized?.title ?? heuristicGoalTitle(rawTitle)
    guard !shouldSkipGoalCreation(title) else { return }

    let config: (goalType: GoalType, targetValue: Double, unit: String?) =
      aiNormalized.map { (goalType: $0.goalType, targetValue: $0.targetValue, unit: $0.unit) }
      ?? fallbackGoalConfig(from: title)
    let dedupeKey = title.lowercased()
    guard !createdGoalTitles.contains(dedupeKey) else { return }

    do {
      let goal = try await APIClient.shared.createGoal(
        title: title,
        description: "Added from onboarding",
        goalType: config.goalType,
        targetValue: config.targetValue,
        currentValue: 0,
        unit: config.unit,
        source: "onboarding_\(source)"
      )
      _ = try? await GoalStorage.shared.syncServerGoal(goal)
      createdGoalTitles.insert(dedupeKey)
      awaitingGoalInput = false
      OnboardingChatPersistence.markGoalCompleted()
      log(
        "OnboardingChat: Created goal from onboarding input: \(title) (\(config.goalType.rawValue), target: \(config.targetValue))"
      )
    } catch {
      logError("OnboardingChat: Failed to create goal from onboarding input", error: error)
    }
  }

  // MARK: - Permission Help Notification

  /// Schedule (or cancel) the 15-second help timer when a permission is being requested.
  private func schedulePermissionHelpTimer(for permissionType: String?) {
    // Always cancel any existing timer first
    permissionHelpTimer?.cancel()
    permissionHelpTimer = nil

    guard let permType = permissionType else { return }
    // Only fire once per permission type
    guard !permissionHelpShown.contains(permType) else { return }

    let workItem = DispatchWorkItem { [permType] in
      // Check permission is still pending — either via pendingPermissionType
      // or via a permission-related question still showing (e.g. FDA "Done!" buttons)
      let stillPending =
        pendingPermissionType == permType
        || (!quickReplyOptions.isEmpty
          && self.permissionType(for: quickReplyQuestion, options: quickReplyOptions) == permType)
      guard stillPending else { return }
      showPermissionHelpNotification(for: permType)
    }
    permissionHelpTimer = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 15, execute: workItem)
    log("OnboardingChat: Started 15s permission help timer for \(permType)")
  }

  /// Take a screenshot, send it to Gemini for analysis, and show the result in the floating bar.
  private func showPermissionHelpNotification(for permType: String) {
    // Mark as shown immediately so we don't fire again
    permissionHelpShown.insert(permType)
    log("OnboardingChat: Permission help timer fired for \(permType), capturing screenshot")

    Task {
      let helpMessage = await generatePermissionHelp(for: permType)
      await MainActor.run {
        let permLabel = permissionDisplayName(permType)
        FloatingControlBarManager.shared.showNotification(
          title: "Need help with \(permLabel)?",
          message: helpMessage,
          assistantId: "onboarding",
          sound: .none
        )
      }
    }
  }

  /// Capture a screenshot and ask Gemini how to grant the permission. Falls back to a static message.
  private func generatePermissionHelp(for permType: String) async -> String {
    let permLabel = permissionDisplayName(permType)
    let fallback =
      "Open System Settings \u{2192} Privacy & Security \u{2192} \(permLabel) and toggle Omi on."

    // Capture screenshot
    guard let screenshotURL = ScreenCaptureManager.captureScreen() else {
      log("OnboardingChat: Screenshot capture failed for permission help, using fallback")
      return fallback
    }

    // Load image data
    guard let imageData = try? Data(contentsOf: screenshotURL) else {
      log("OnboardingChat: Failed to load screenshot data for permission help, using fallback")
      return fallback
    }

    // Send to Gemini
    do {
      let gemini = try GeminiClient()
      let prompt =
        "The user needs to grant \(permLabel) permission to the Omi app. Look at the screenshot. Tell them exactly where to click in ONE short sentence, max 15 words."
      let systemPrompt = "You are a concise macOS setup helper. Give only the essential click instruction, nothing else."

      let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
        type: "object",
        properties: [
          "help_text": .init(type: "string", description: "1-2 sentence help text for the user")
        ],
        required: ["help_text"]
      )

      let responseJSON = try await gemini.sendRequest(
        prompt: prompt,
        imageData: imageData,
        systemPrompt: systemPrompt,
        responseSchema: responseSchema
      )

      // Parse the JSON response
      if let data = responseJSON.data(using: .utf8),
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let helpText = json["help_text"] as? String,
        !helpText.isEmpty
      {
        log("OnboardingChat: Gemini permission help response: \(helpText)")
        // Clean up screenshot file
        try? FileManager.default.removeItem(at: screenshotURL)
        return helpText
      }

      log("OnboardingChat: Gemini response didn't contain valid help_text, using fallback")
      try? FileManager.default.removeItem(at: screenshotURL)
      return fallback
    } catch {
      log("OnboardingChat: Gemini request failed for permission help: \(error.localizedDescription), using fallback")
      try? FileManager.default.removeItem(at: screenshotURL)
      return fallback
    }
  }

  /// Human-readable permission name for display
  private func permissionDisplayName(_ permType: String) -> String {
    switch permType {
    case "screen_recording": return "Screen Recording"
    case "microphone": return "Microphone"
    case "notifications": return "Notifications"
    case "accessibility": return "Accessibility"
    case "automation": return "Automation"
    case "full_disk_access": return "Full Disk Access"
    default: return permType
    }
  }

  private func handleOnboardingComplete() {
    log("OnboardingChatView: Chat step complete, advancing to next onboarding step")

    // Clean up permission help timer
    permissionHelpTimer?.cancel()
    permissionHelpTimer = nil

    // Clean up parallel exploration
    explorationTask?.cancel()
    explorationTask = nil
    if let bridge = explorationBridge {
      Task { await bridge.stop() }
    }
    explorationBridge = nil

    // Clean up Gmail reading
    gmailReadingTask?.cancel()
    gmailReadingTask = nil

    // Clean up Calendar reading
    calendarReadingTask?.cancel()
    calendarReadingTask = nil

    // Notify parent to advance to next step
    onComplete()
  }

  /// Build a compact summary of the conversation so far for inclusion in the system prompt.
  /// This ensures the AI has context even if ACP session/resume fails and a fresh session starts.
  private func buildConversationContext(from messages: [ChatMessage]) -> String {
    guard !messages.isEmpty else { return "" }

    var lines: [String] = []
    for message in messages {
      let role = message.sender == .user ? "User" : "Assistant"
      let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty else { continue }
      // Truncate very long messages to keep the context compact
      let truncated = text.count > 500 ? String(text.prefix(500)) + "..." : text
      lines.append("\(role): \(truncated)")
    }
    return lines.joined(separator: "\n")
  }

  // MARK: - Parallel Exploration

  /// Check if files are already indexed and start/restore exploration (for resume path)
  private func checkAndStartExploration(graphViewModel: MemoryGraphViewModel?) async {
    guard !explorationRunning && !explorationCompleted else { return }

    // If exploration already completed in a prior session, restore from saved state
    if let saved = OnboardingChatPersistence.loadExplorationState(), saved.completed {
      log(
        "OnboardingChat: Restoring completed exploration from saved state (\(saved.text.count) chars)"
      )
      explorationText = saved.text
      explorationCompleted = true
      // Re-inject the discovery card (UI state was lost on restart)
      if !saved.text.isEmpty {
        await injectExplorationDiscoveryCard()
      }
      return
    }

    // Otherwise check if files are indexed and run exploration fresh
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return }
    let fileCount =
      (try? await dbQueue.read { db in
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files")
      }) ?? 0

    if fileCount > 0 {
      log("OnboardingChat: Files already indexed (\(fileCount)), starting exploration on resume")
      startExploration(fileCount: fileCount, graphViewModel: graphViewModel)
      startGmailReading()
      startCalendarReading()
    }
  }

  private func startExploration(fileCount: Int, graphViewModel: MemoryGraphViewModel?) {
    guard !explorationRunning else { return }
    explorationRunning = true
    log("OnboardingChat: Starting parallel exploration (\(fileCount) files indexed)")
    AnalyticsManager.shared.onboardingChatToolUsed(
      tool: "exploration_started", properties: ["file_count": fileCount])

    explorationTask = Task {
      do {
        let bridge = ACPBridge(passApiKey: true)
        await MainActor.run { explorationBridge = bridge }
        try await bridge.start()

        let userName =
          AuthService.shared.displayName.isEmpty ? "User" : AuthService.shared.displayName
        let schema = await Self.loadDatabaseSchema()
        let systemPrompt = ChatPromptBuilder.buildOnboardingExploration(
          userName: userName, databaseSchema: schema)

        let result = try await bridge.query(
          prompt:
            "Begin exploration. \(fileCount) files have been indexed in the indexed_files table.",
          systemPrompt: systemPrompt,
          model: "claude-opus-4-6",
          onTextDelta: { @Sendable delta in
            Task { @MainActor in
              explorationText += delta
              // Persist partial text periodically (every ~500 chars) so it survives crashes
              if explorationText.count % 500 < delta.count {
                OnboardingChatPersistence.saveExplorationState(
                  text: explorationText, completed: false)
              }
            }
          },
          onToolCall: { @Sendable _, name, input in
            let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
            let result = await ChatToolExecutor.execute(toolCall)
            log("OnboardingChat: Exploration tool \(name) executed")
            return result
          },
          onToolActivity: { @Sendable name, status, _, _ in
            log("OnboardingChat: Exploration tool \(name) \(status)")
          }
        )

        log(
          "OnboardingChat: Exploration completed (cost=$\(String(format: "%.4f", result.costUsd)), tokens=\(result.inputTokens)+\(result.outputTokens))"
        )
        AnalyticsManager.shared.onboardingChatToolUsed(
          tool: "exploration_completed",
          properties: [
            "cost_usd": result.costUsd,
            "input_tokens": result.inputTokens,
            "output_tokens": result.outputTokens,
          ])

        let finalText = await MainActor.run {
          explorationCompleted = true
          explorationRunning = false
          return explorationText
        }

        // Persist so it survives app restarts
        OnboardingChatPersistence.saveExplorationState(text: finalText, completed: true)

        // Append to user profile and inject discovery card
        await appendExplorationToProfile()
        await injectExplorationDiscoveryCard()

        await bridge.stop()
        await MainActor.run { explorationBridge = nil }
      } catch {
        log("OnboardingChat: Exploration failed (non-fatal): \(error.localizedDescription)")
        if let bridge = await MainActor.run(body: { explorationBridge }) {
          await bridge.stop()
        }
        await MainActor.run {
          explorationRunning = false
          explorationBridge = nil
        }
      }
    }
  }

  /// Load a compact database schema string from sqlite_master for the exploration prompt.
  /// This gives the AI the actual table/column names so it doesn't hallucinate them.
  private static func loadDatabaseSchema() async -> String {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return ""
    }

    do {
      let tables = try await dbQueue.read { db -> [(name: String, sql: String)] in
        let rows = try Row.fetchAll(
          db,
          sql: """
                SELECT name, sql FROM sqlite_master
                WHERE type='table' AND sql IS NOT NULL
                ORDER BY name
            """)
        return rows.compactMap { row -> (name: String, sql: String)? in
          guard let name: String = row["name"],
            let sql: String = row["sql"]
          else { return nil }
          return (name: name, sql: sql)
        }
      }

      var lines: [String] = ["**Database schema (omi.db):**", ""]
      for (name, sql) in tables {
        if ChatPrompts.excludedTables.contains(name) { continue }
        if ChatPrompts.excludedTablePrefixes.contains(where: { name.hasPrefix($0) }) { continue }
        if name.contains("_fts") { continue }

        // Extract column names from CREATE TABLE DDL
        guard let openParen = sql.firstIndex(of: "("),
          let closeParen = sql.lastIndex(of: ")")
        else { continue }
        let body = String(sql[sql.index(after: openParen)..<closeParen])
        var columnDefs: [String] = []
        var current = ""
        var depth = 0
        for char in body {
          if char == "(" { depth += 1 } else if char == ")" { depth -= 1 }
          if char == "," && depth == 0 {
            let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { columnDefs.append(trimmed) }
            current = ""
          } else {
            current.append(char)
          }
        }
        let last = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if !last.isEmpty { columnDefs.append(last) }

        let columnNames = columnDefs.filter { col in
          let upper = col.uppercased().trimmingCharacters(in: .whitespaces)
          return !upper.hasPrefix("UNIQUE") && !upper.hasPrefix("CHECK")
            && !upper.hasPrefix("FOREIGN") && !upper.hasPrefix("CONSTRAINT")
            && !upper.hasPrefix("PRIMARY KEY")
        }.compactMap { col -> String? in
          let colName =
            col.components(separatedBy: .whitespaces).first?
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'`")) ?? ""
          return ChatPrompts.excludedColumns.contains(colName) || colName.isEmpty ? nil : colName
        }
        guard !columnNames.isEmpty else { continue }

        let annotation = ChatPrompts.tableAnnotations[name] ?? ""
        let header = annotation.isEmpty ? name : "\(name) — \(annotation)"
        lines.append(header)
        lines.append("  \(columnNames.joined(separator: ", "))")
        lines.append("")
      }
      lines.append(ChatPrompts.schemaFooter)
      return lines.joined(separator: "\n")
    } catch {
      logError("Failed to load schema for exploration", error: error)
      return ""
    }
  }

  /// Append the exploration text to the user's AI profile
  private func appendExplorationToProfile() async {
    let text = await MainActor.run { explorationText }
    guard !text.isEmpty else {
      log("OnboardingChat: No exploration text to append to profile")
      return
    }

    let service = AIUserProfileService.shared
    let existingProfile = await service.getLatestProfile()

    if let existing = existingProfile, let profileId = existing.id {
      let updated = existing.profileText + "\n\n--- File Exploration Insights ---\n" + text
      let success = await service.updateProfileText(id: profileId, newText: updated)
      log("OnboardingChat: Appended exploration to AI profile (success=\(success))")
    } else {
      log("OnboardingChat: No existing AI profile, triggering generation")
      _ = try? await service.generateProfile()
    }
  }

  /// Inject a discovery card into the onboarding chat with the exploration profile
  private func injectExplorationDiscoveryCard() async {
    let text = await MainActor.run { explorationText }
    guard !text.isEmpty else { return }

    let summary = text.count > 120 ? String(text.prefix(120)) + "..." : text

    await MainActor.run {
      chatProvider.appendDiscoveryCard(
        title: "Your Digital Profile",
        summary: summary,
        fullText: text
      )
    }
  }

  private func bringToFront() {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
      NSApp.activate()
      for window in NSApp.windows {
        if window.title.hasPrefix("Omi") {
          window.makeKeyAndOrderFront(nil)
          window.orderFrontRegardless()
        }
      }
    }
  }

  // MARK: - Gmail Reading (Parallel Onboarding Task)

  private func startGmailReading() {
    guard !gmailReadingRunning && !gmailReadingCompleted else { return }
    gmailReadingRunning = true
    log("OnboardingChat: Starting Gmail reading in background")

    gmailReadingTask = Task {
      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(
          maxResults: 50, query: "newer_than:30d"
        )
        guard !emails.isEmpty else {
          log("OnboardingChat: No Gmail emails found, skipping synthesis")
          await MainActor.run {
            gmailReadingRunning = false
            gmailReadingCompleted = true
          }
          return
        }
        log("OnboardingChat: Fetched \(emails.count) Gmail emails, starting synthesis")

        await MainActor.run {
          gmailReadingText = "Analyzing \(emails.count) emails..."
        }

        let result = await GmailReaderService.shared.synthesizeFromEmails(emails: emails)

        let summaryText =
          result.profileSummary.isEmpty
          ? "Created \(result.memories) memories and \(result.tasks) tasks from your emails."
          : result.profileSummary

        await MainActor.run {
          gmailReadingText = summaryText
          gmailReadingCompleted = true
          gmailReadingRunning = false
          ChatToolExecutor.emailInsightsText = summaryText
        }

        log(
          "OnboardingChat: Gmail synthesis complete — \(result.memories) memories, \(result.tasks) tasks"
        )

        // Append Gmail insights to AI profile
        let text = await MainActor.run { gmailReadingText }
        if !text.isEmpty {
          let service = AIUserProfileService.shared
          let existingProfile = await service.getLatestProfile()
          if let existing = existingProfile, let profileId = existing.id {
            let updated = existing.profileText + "\n\n--- Gmail Insights ---\n" + text
            let success = await service.updateProfileText(id: profileId, newText: updated)
            log("OnboardingChat: Appended Gmail insights to AI profile (success=\(success))")
          }
        }

      } catch {
        log("OnboardingChat: Gmail reading failed (non-fatal): \(error.localizedDescription)")
        await MainActor.run {
          gmailReadingRunning = false
        }
      }
    }
  }

  // MARK: - Calendar Reading (Parallel Onboarding Task)

  private func startCalendarReading() {
    guard !calendarReadingRunning && !calendarReadingCompleted else { return }
    calendarReadingRunning = true
    log("OnboardingChat: Starting Calendar reading in background")

    calendarReadingTask = Task {
      do {
        let events = try await CalendarReaderService.shared.readEvents(
          daysBack: 90, daysForward: 14, maxResults: 200
        )
        guard !events.isEmpty else {
          log("OnboardingChat: No calendar events found, skipping synthesis")
          await MainActor.run {
            calendarReadingRunning = false
            calendarReadingCompleted = true
          }
          return
        }
        log("OnboardingChat: Fetched \(events.count) calendar events, starting synthesis")

        await MainActor.run {
          calendarReadingText = "Analyzing \(events.count) calendar events..."
        }

        let result = await CalendarReaderService.shared.synthesizeFromEvents(events: events)

        let summaryText =
          result.profileSummary.isEmpty
          ? "Created \(result.memories) memories and \(result.tasks) tasks from your calendar."
          : result.profileSummary

        await MainActor.run {
          calendarReadingText = summaryText
          calendarReadingCompleted = true
          calendarReadingRunning = false
          ChatToolExecutor.calendarInsightsText = summaryText
        }

        log(
          "OnboardingChat: Calendar synthesis complete — \(result.memories) memories, \(result.tasks) tasks"
        )

        // Append Calendar insights to AI profile
        let text = await MainActor.run { calendarReadingText }
        if !text.isEmpty {
          let service = AIUserProfileService.shared
          let existingProfile = await service.getLatestProfile()
          if let existing = existingProfile, let profileId = existing.id {
            let updated = existing.profileText + "\n\n--- Calendar Insights ---\n" + text
            let success = await service.updateProfileText(id: profileId, newText: updated)
            log("OnboardingChat: Appended Calendar insights to AI profile (success=\(success))")
          }
        }

      } catch {
        log("OnboardingChat: Calendar reading failed (non-fatal): \(error.localizedDescription)")
        await MainActor.run {
          calendarReadingRunning = false
        }
      }
    }
  }
}

// MARK: - Gmail Insights Card

struct GmailInsightsCard: View {
  let text: String
  let isRunning: Bool
  let isCompleted: Bool

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: {
        guard !text.isEmpty else { return }
        withAnimation(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: 8) {
          if isRunning {
            ProgressView()
              .controlSize(.mini)
          } else {
            Image(systemName: "envelope.open.fill")
              .font(.system(size: 12))
              .foregroundColor(OmiColors.purplePrimary)
          }

          VStack(alignment: .leading, spacing: 2) {
            Text(isRunning ? "Reading your emails..." : "Email Insights")
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)

            if !text.isEmpty {
              Text(String(text.prefix(100)).replacingOccurrences(of: "\n", with: " "))
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(2)
            }
          }

          Spacer(minLength: 4)

          if !text.isEmpty {
            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
              .font(.system(size: 10))
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
      .buttonStyle(.plain)

      if isExpanded && !text.isEmpty {
        Divider()
          .padding(.horizontal, 10)

        ScrollView {
          Markdown(text)
            .markdownTheme(.aiMessage())
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
        }
        .frame(maxHeight: 300)
      }
    }
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(12)
    .overlay(
      RoundedRectangle(cornerRadius: 12)
        .stroke(OmiColors.purplePrimary.opacity(0.2), lineWidth: 1)
    )
  }
}

// MARK: - Calendar Insights Card

struct CalendarInsightsCard: View {
  let text: String
  let isRunning: Bool
  let isCompleted: Bool

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: {
        guard !text.isEmpty else { return }
        withAnimation(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: 8) {
          if isRunning {
            ProgressView()
              .controlSize(.mini)
          } else {
            Image(systemName: "calendar.badge.checkmark")
              .font(.system(size: 12))
              .foregroundColor(OmiColors.purplePrimary)
          }

          VStack(alignment: .leading, spacing: 2) {
            Text(isRunning ? "Reading your calendar..." : "Calendar Insights")
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)

            if !text.isEmpty {
              Text(String(text.prefix(100)).replacingOccurrences(of: "\n", with: " "))
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(2)
            }
          }

          Spacer(minLength: 4)

          if !text.isEmpty {
            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
              .font(.system(size: 10))
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
      .buttonStyle(.plain)

      if isExpanded && !text.isEmpty {
        Divider()
          .padding(.horizontal, 10)

        ScrollView {
          Markdown(text)
            .markdownTheme(.aiMessage())
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
        }
        .frame(maxHeight: 300)
      }
    }
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(12)
    .overlay(
      RoundedRectangle(cornerRadius: 12)
        .stroke(OmiColors.purplePrimary.opacity(0.2), lineWidth: 1)
    )
  }
}

// MARK: - Onboarding Chat Bubble

struct OnboardingChatBubble: View {
  let message: ChatMessage
  var hidePermissionImages: Bool = false

  /// Whether this AI message has any visible content (non-empty text or visible tool calls)
  private var hasVisibleContent: Bool {
    if message.sender != .ai { return true }
    // Messages loaded from backend have empty contentBlocks but non-empty text
    if message.contentBlocks.isEmpty {
      return !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    return message.contentBlocks.contains { block in
      switch block {
      case .toolCall(_, let name, _, _, _, _):
        return name != "ask_followup"  // ask_followup renders its own UI separately
      case .text(_, let text):
        return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      case .thinking:
        return false
      case .discoveryCard:
        return true
      }
    }
  }

  var body: some View {
    if hasVisibleContent {
      HStack(alignment: .top, spacing: 12) {
        if message.sender == .ai {
          // Omi logo
          if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
            let logoImage = NSImage(contentsOf: logoURL)
          {
            Image(nsImage: logoImage)
              .resizable()
              .scaledToFit()
              .frame(width: 20, height: 20)
              .frame(width: 32, height: 32)
              .background(OmiColors.backgroundTertiary)
              .clipShape(Circle())
          }
        }

        VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 4) {
          if message.sender == .ai {
            if message.contentBlocks.isEmpty {
              // Fallback for messages loaded from backend (no contentBlocks, only flat text)
              if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Markdown(message.text)
                  .markdownTheme(.aiMessage())
                  .textSelection(.enabled)
                  .padding(.horizontal, 14)
                  .padding(.vertical, 10)
                  .background(OmiColors.backgroundSecondary)
                  .cornerRadius(18)
              }
            } else {
              // Use the full message text (which streams continuously) for a single bubble.
              // contentBlocks splits text around tool calls, but message.text is uninterrupted.
              let allText = message.text.trimmingCharacters(in: .whitespacesAndNewlines)

              if !allText.isEmpty {
                Markdown(allText)
                  .markdownTheme(.aiMessage())
                  .textSelection(.enabled)
                  .padding(.horizontal, 14)
                  .padding(.vertical, 10)
                  .background(OmiColors.backgroundSecondary)
                  .cornerRadius(18)
              }

              ForEach(message.contentBlocks) { block in
                switch block {
                case .toolCall(_, let name, let status, _, let input, _):
                  let indicator = OnboardingToolIndicator(
                    toolName: name,
                    status: status,
                    input: input,
                    hidePermissionImage: hidePermissionImages
                  )
                  if !indicator.isHidden {
                    indicator
                  }
                case .discoveryCard(_, let title, let summary, let fullText):
                  DiscoveryCard(title: title, summary: summary, fullText: fullText)
                default:
                  EmptyView()
                }
              }
            }
          } else {
            if !message.text.isEmpty {
              Markdown(message.text)
                .markdownTheme(.userMessage())
                .textSelection(.enabled)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(OmiColors.purplePrimary)
                .cornerRadius(18)
            }
          }
        }

        if message.sender == .user {
          // User avatar
          Image(systemName: "person.fill")
            .font(.system(size: 14))
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 32, height: 32)
            .background(OmiColors.backgroundTertiary)
            .clipShape(Circle())
        }
      }
      .frame(maxWidth: .infinity, alignment: message.sender == .user ? .trailing : .leading)
    }
  }

}

// MARK: - Tool Activity Indicator

struct OnboardingToolIndicator: View {
  let toolName: String
  let status: ToolCallStatus
  var input: ToolCallInput? = nil
  var hidePermissionImage: Bool = false

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 6) {
        if status == .running {
          ProgressView()
            .controlSize(.mini)
        } else {
          Image(systemName: "checkmark.circle.fill")
            .font(.system(size: 10))
            .foregroundColor(.green)
        }

        Text(displayText)
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }

      // Show permission guide image automatically for scan_files and request_permission
      if !hidePermissionImage, let permImage = permissionImageType {
        OnboardingPermissionImage(permissionType: permImage)
      }
    }
    .padding(.vertical, 2)
  }

  /// Whether this tool should be hidden from the UI (e.g. ask_followup renders its own UI)
  var isHidden: Bool {
    cleanToolName == "ask_followup"
      || cleanToolName == "save_knowledge_graph"
  }

  /// Strip MCP prefix from tool name (e.g. "mcp__omi-tools__scan_files" → "scan_files")
  private var cleanToolName: String {
    if toolName.hasPrefix("mcp__") {
      return String(toolName.split(separator: "__").last ?? Substring(toolName))
    }
    return toolName
  }

  /// Determines which permission image to show based on the tool name and input
  private var permissionImageType: String? {
    switch cleanToolName {
    case "request_permission":
      return input?.summary  // summary contains the permission type (e.g., "microphone")
    default:
      return nil
    }
  }

  private var displayText: String {
    switch cleanToolName {
    case "scan_files", "start_file_scan":
      return status == .running ? "Scanning your files..." : "Files scanned"
    case "check_permission_status":
      return status == .running ? "Checking permissions..." : "Permissions checked"
    case "request_permission":
      return status == .running ? "Requesting permission..." : "Permission requested"
    case "set_user_preferences":
      return status == .running ? "Saving preferences..." : "Preferences saved"
    case "complete_onboarding":
      return status == .running ? "Finishing setup..." : "Setup complete"
    case "save_knowledge_graph":
      return status == .running ? "Updating your profile..." : "Profile updated"
    default:
      if toolName == "WebSearch" || toolName.contains("search") || toolName.contains("web") {
        return status == .running ? "Learning more about you..." : "Learned more about you"
      }
      if toolName.hasPrefix("WebFetch:") || toolName == "WebFetch" {
        return status == .running ? "Reading context..." : "Context updated"
      }
      return status == .running ? "Working..." : "Done"
    }
  }
}

// MARK: - Permission Guide Image

struct OnboardingPermissionImage: View {
  let permissionType: String

  private var resourceInfo: (name: String, ext: String)? {
    switch permissionType {
    case "microphone":
      return ("microphone-settings", "png")
    case "notifications":
      return ("enable_notifications", "gif")
    case "accessibility":
      return ("accessibility_permission", "gif")
    case "screen_recording":
      return ("permissions", "gif")
    case "folder_access":
      return ("folder_access", "png")
    case "full_disk_access":
      return ("full_disk_access", "png")
    default:
      return nil
    }
  }

  var body: some View {
    if let info = resourceInfo {
      if info.ext == "gif" {
        AnimatedGIFView(gifName: info.name)
          .frame(maxWidth: 320, maxHeight: 200)
          .cornerRadius(12)
          .overlay(
            RoundedRectangle(cornerRadius: 12)
              .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
          )
      } else if let url = Bundle.resourceBundle.url(
        forResource: info.name, withExtension: info.ext),
        let nsImage = NSImage(contentsOf: url)
      {
        Image(nsImage: nsImage)
          .resizable()
          .scaledToFit()
          .frame(maxWidth: 320, maxHeight: 200)
          .cornerRadius(12)
          .overlay(
            RoundedRectangle(cornerRadius: 12)
              .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
          )
      }
    }
  }
}

// MARK: - Exploration Profile Card

/// Shows streaming exploration progress during onboarding, then becomes a collapsible profile card
struct ExplorationProfileCard: View {
  let text: String
  let isRunning: Bool
  let isCompleted: Bool

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header
      Button(action: {
        guard !text.isEmpty else { return }
        withAnimation(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: 8) {
          if isRunning {
            ProgressView()
              .controlSize(.mini)
          } else {
            Image(systemName: "doc.text.magnifyingglass")
              .font(.system(size: 12))
              .foregroundColor(OmiColors.purplePrimary)
          }

          VStack(alignment: .leading, spacing: 2) {
            Text(isRunning ? "Learning about you..." : "Your Digital Profile")
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)

            if !text.isEmpty {
              Text(String(text.prefix(100)).replacingOccurrences(of: "\n", with: " "))
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(2)
            }
          }

          Spacer(minLength: 4)

          if !text.isEmpty {
            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
              .font(.system(size: 10))
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded && !text.isEmpty {
        Divider()
          .padding(.horizontal, 10)

        ScrollView {
          Markdown(text)
            .markdownTheme(.aiMessage())
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
        }
        .frame(maxHeight: 300)
      }
    }
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(12)
    .overlay(
      RoundedRectangle(cornerRadius: 12)
        .stroke(OmiColors.purplePrimary.opacity(0.2), lineWidth: 1)
    )
  }
}
