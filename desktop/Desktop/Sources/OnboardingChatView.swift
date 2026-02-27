import SwiftUI
import MarkdownUI

// MARK: - Onboarding Chat View

struct OnboardingChatView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @State private var inputText: String = ""
    @State private var hasStarted: Bool = false
    @State private var showCompleteButton: Bool = false
    @State private var onboardingCompleted: Bool = false
    @FocusState private var isInputFocused: Bool

    // Timer to periodically check permission status
    let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()
    // Safety timeout timer (3 minutes)
    let safetyTimer = Timer.publish(every: 180.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Setting up Omi")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
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
                            OnboardingChatBubble(message: message)
                                .id(message.id)
                        }

                        // Typing indicator (floating, no avatar)
                        if chatProvider.isSending {
                            TypingIndicator()
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.leading, 44) // align with message text (32px avatar + 12px spacing)
                                .id("typing")
                        }

                        // "Continue to App" button — shown after AI calls complete_onboarding
                        if onboardingCompleted && !chatProvider.isSending {
                            Button(action: {
                                handleOnboardingComplete()
                            }) {
                                Text("Continue to App")
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

                        // Safety timeout button — fallback if AI never calls complete_onboarding
                        if showCompleteButton && !onboardingCompleted && !chatProvider.isSending {
                            Button(action: {
                                handleOnboardingComplete()
                            }) {
                                Text("Complete Setup")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 24)
                                    .padding(.vertical, 10)
                                    .background(OmiColors.purplePrimary)
                                    .cornerRadius(12)
                            }
                            .buttonStyle(.plain)
                            .padding(.top, 8)
                        }
                    }
                    .padding(20)
                }
                .onChange(of: chatProvider.messages.count) { _, _ in
                    if let lastMessage = chatProvider.messages.last {
                        withAnimation {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
                .onChange(of: chatProvider.isSending) { _, sending in
                    if sending {
                        withAnimation {
                            proxy.scrollTo("typing", anchor: .bottom)
                        }
                    }
                }
            }

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Input area
            HStack(spacing: 12) {
                TextField("Type your message...", text: $inputText, axis: .vertical)
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

                if chatProvider.isSending && inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
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
        }
        .onReceive(safetyTimer) { _ in
            if !showCompleteButton {
                showCompleteButton = true
            }
        }
        // Bring app to front when permissions are granted
        .onChange(of: appState.hasScreenRecordingPermission) { _, granted in
            if granted { bringToFront() }
        }
        .onChange(of: appState.hasMicrophonePermission) { _, granted in
            if granted { bringToFront() }
        }
        .onChange(of: appState.hasNotificationPermission) { _, granted in
            if granted { bringToFront() }
        }
        .onChange(of: appState.hasAccessibilityPermission) { _, granted in
            if granted { bringToFront() }
        }
        .onChange(of: appState.hasAutomationPermission) { _, granted in
            if granted { bringToFront() }
        }
    }

    @ViewBuilder
    private var omiAvatar: some View {
        if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
           let logoImage = NSImage(contentsOf: logoURL) {
            Image(nsImage: logoImage)
                .resizable()
                .scaledToFit()
                .frame(width: 20, height: 20)
                .frame(width: 32, height: 32)
                .background(OmiColors.backgroundTertiary)
                .clipShape(Circle())
        }
    }

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !chatProvider.isSending
    }

    // MARK: - Actions

    private func startChat() {
        guard !hasStarted else { return }
        hasStarted = true
        isInputFocused = true

        // Clear any existing messages so onboarding starts fresh
        chatProvider.messages.removeAll()

        // Wire up onboarding tools
        ChatToolExecutor.onboardingAppState = appState
        ChatToolExecutor.onCompleteOnboarding = {
            onboardingCompleted = true
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

        // Set onboarding session key so messages go to a dedicated session
        chatProvider.onboardingSessionKey = "onboarding"

        // Send initial user message — the system prompt tells AI how to respond
        Task {
            await chatProvider.sendMessage(
                "Hi, I just installed Omi!",
                systemPromptPrefix: systemPrompt,
                sessionKey: "onboarding"
            )
        }
    }

    private func stopAgent() {
        chatProvider.stopAgent()
    }

    private func sendMessage() {
        guard canSend else { return }

        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        inputText = ""

        Task {
            await chatProvider.sendMessage(text, sessionKey: "onboarding")
        }
    }

    private func handleOnboardingComplete() {
        log("OnboardingChatView: Completing onboarding")

        // Mark onboarding as done
        appState.hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")

        // Start cloud agent VM pipeline
        Task {
            await AgentVMService.shared.startPipeline()
        }

        // Enable launch at login
        if LaunchAtLoginManager.shared.setEnabled(true) {
            AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "onboarding")
        }

        // Start proactive monitoring
        ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }

        // Start transcription if microphone is available
        appState.startTranscription()

        // Create welcome task
        Task {
            await TasksStore.shared.createTask(
                description: "Run Omi for two days to start receiving helpful advice",
                dueAt: Date(),
                priority: "low"
            )
        }

        // Send welcome notification
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            NotificationService.shared.sendNotification(
                title: "You're all set!",
                message: "Just go back to your work and run me in the background. I'll start sending you useful advice during your day."
            )
        }

        // Clean up onboarding session key
        chatProvider.onboardingSessionKey = nil

        // Log analytics
        AnalyticsManager.shared.onboardingCompleted()

        // Notify parent
        onComplete()
    }

    private func bringToFront() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            NSApp.activate(ignoringOtherApps: true)
            for window in NSApp.windows {
                if window.title.hasPrefix("Omi") {
                    window.makeKeyAndOrderFront(nil)
                    window.orderFrontRegardless()
                }
            }
        }
    }
}

// MARK: - Onboarding Chat Bubble

struct OnboardingChatBubble: View {
    let message: ChatMessage

    /// Whether this AI message has any visible content (non-empty text or tool calls)
    private var hasVisibleContent: Bool {
        if message.sender != .ai { return true }
        return message.contentBlocks.contains { block in
            switch block {
            case .toolCall:
                return true
            case .text(_, let text):
                return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            case .thinking:
                return false
            }
        }
    }

    var body: some View {
        if hasVisibleContent {
            HStack(alignment: .top, spacing: 12) {
                if message.sender == .ai {
                    // Omi logo
                    if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                       let logoImage = NSImage(contentsOf: logoURL) {
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
                        // Render content blocks in order — interleaving tool indicators with text
                        ForEach(message.contentBlocks) { block in
                            switch block {
                            case .toolCall(_, let name, let status, _, _, _):
                                OnboardingToolIndicator(toolName: name, status: status)
                            case .text(_, let text):
                                if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                    Markdown(text)
                                        .markdownTheme(.aiMessage())
                                        .textSelection(.enabled)
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 10)
                                        .background(OmiColors.backgroundSecondary)
                                        .cornerRadius(18)
                                }
                            case .thinking:
                                EmptyView()
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

    var body: some View {
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
        .padding(.vertical, 2)
    }

    private var displayText: String {
        switch toolName {
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
        default:
            if toolName.hasPrefix("WebSearch:") {
                let query = String(toolName.dropFirst("WebSearch: ".count)).trimmingCharacters(in: CharacterSet(charactersIn: "\""))
                return status == .running ? "Searching: \(query)" : "Searched: \(query)"
            }
            if toolName == "WebSearch" || toolName.contains("search") || toolName.contains("web") {
                return status == .running ? "Searching the web..." : "Web search complete"
            }
            if toolName.hasPrefix("WebFetch:") || toolName == "WebFetch" {
                return status == .running ? "Reading webpage..." : "Webpage read"
            }
            return status == .running ? "Working..." : "Done"
        }
    }
}
