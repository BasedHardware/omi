import SwiftUI
import MarkdownUI

// MARK: - Onboarding Chat Persistence

/// Persists onboarding chat messages across app restarts (e.g. screen recording permission requires restart).
/// Stores messages as JSON in UserDefaults alongside the ACP session ID for conversation resumption.
enum OnboardingChatPersistence {
    private static let messagesKey = "onboardingChatMessages"
    private static let sessionIdKey = "onboardingACPSessionId"

    /// Save messages to UserDefaults
    static func saveMessages(_ messages: [ChatMessage]) {
        var encoded: [[String: Any]] = []
        for msg in messages {
            var dict: [String: Any] = [
                "id": msg.id,
                "text": msg.text,
                "sender": msg.sender == .user ? "user" : "ai",
                "createdAt": msg.createdAt.timeIntervalSince1970,
            ]
            // Serialize content blocks for AI messages
            if msg.sender == .ai && !msg.contentBlocks.isEmpty {
                var blocks: [[String: Any]] = []
                for block in msg.contentBlocks {
                    switch block {
                    case .text(let id, let text):
                        blocks.append(["type": "text", "id": id, "text": text])
                    case .toolCall(let id, let name, let status, _, let input, _):
                        var b: [String: Any] = [
                            "type": "toolCall", "id": id, "name": name,
                            "status": status == .completed ? "completed" : "running",
                        ]
                        if let input { b["inputSummary"] = input.summary }
                        blocks.append(b)
                    case .thinking:
                        break // Skip thinking blocks
                    case .discoveryCard(let id, let title, let summary, let fullText):
                        blocks.append(["type": "discoveryCard", "id": id, "title": title, "summary": summary, "fullText": fullText])
                    }
                }
                dict["contentBlocks"] = blocks
            }
            encoded.append(dict)
        }
        if let data = try? JSONSerialization.data(withJSONObject: encoded) {
            UserDefaults.standard.set(data, forKey: messagesKey)
        }
    }

    /// Restore messages from UserDefaults
    static func loadMessages() -> [ChatMessage]? {
        guard let data = UserDefaults.standard.data(forKey: messagesKey),
              let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
              !array.isEmpty else { return nil }

        var messages: [ChatMessage] = []
        for dict in array {
            guard let id = dict["id"] as? String,
                  let text = dict["text"] as? String,
                  let senderStr = dict["sender"] as? String,
                  let timestamp = dict["createdAt"] as? TimeInterval else { continue }

            let sender: ChatSender = senderStr == "user" ? .user : .ai
            var contentBlocks: [ChatContentBlock] = []

            if let blocks = dict["contentBlocks"] as? [[String: Any]] {
                for block in blocks {
                    guard let type = block["type"] as? String,
                          let blockId = block["id"] as? String else { continue }
                    switch type {
                    case "text":
                        contentBlocks.append(.text(id: blockId, text: block["text"] as? String ?? ""))
                    case "toolCall":
                        let name = block["name"] as? String ?? ""
                        let status: ToolCallStatus = (block["status"] as? String) == "running" ? .running : .completed
                        let input: ToolCallInput? = (block["inputSummary"] as? String).map { ToolCallInput(summary: $0, details: nil) }
                        contentBlocks.append(.toolCall(id: blockId, name: name, status: status, input: input))
                    case "discoveryCard":
                        contentBlocks.append(.discoveryCard(
                            id: blockId,
                            title: block["title"] as? String ?? "",
                            summary: block["summary"] as? String ?? "",
                            fullText: block["fullText"] as? String ?? ""
                        ))
                    default:
                        break
                    }
                }
            }

            messages.append(ChatMessage(
                id: id, text: text,
                createdAt: Date(timeIntervalSince1970: timestamp),
                sender: sender, isStreaming: false,
                contentBlocks: contentBlocks
            ))
        }
        return messages.isEmpty ? nil : messages
    }

    /// Save the ACP session ID for resume after restart
    static func saveSessionId(_ sessionId: String) {
        UserDefaults.standard.set(sessionId, forKey: sessionIdKey)
    }

    /// Load the saved ACP session ID
    static func loadSessionId() -> String? {
        UserDefaults.standard.string(forKey: sessionIdKey)
    }

    /// Clear all persisted onboarding chat data
    static func clear() {
        UserDefaults.standard.removeObject(forKey: messagesKey)
        UserDefaults.standard.removeObject(forKey: sessionIdKey)
    }

    /// Whether there are persisted messages (i.e. app was restarted mid-onboarding)
    static var hasSavedMessages: Bool {
        UserDefaults.standard.data(forKey: messagesKey) != nil
    }
}

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
    @State private var quickReplyOptions: [String] = []
    @State private var isGrantingPermission: Bool = false
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

                        // Quick reply buttons
                        if !quickReplyOptions.isEmpty && !chatProvider.isSending {
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
                            .padding(.leading, 44) // align with message text
                            .id("quick-replies")
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
                    } else {
                        // Persist messages when AI response completes (for restart recovery)
                        OnboardingChatPersistence.saveMessages(chatProvider.messages)

                        if !quickReplyOptions.isEmpty {
                            withAnimation {
                                proxy.scrollTo("quick-replies", anchor: .bottom)
                            }
                        }
                    }
                }
                .onChange(of: quickReplyOptions) { _, options in
                    if !options.isEmpty {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            withAnimation {
                                proxy.scrollTo("quick-replies", anchor: .bottom)
                            }
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

        // Wire up onboarding tools
        ChatToolExecutor.onboardingAppState = appState
        ChatToolExecutor.onCompleteOnboarding = {
            onboardingCompleted = true
        }
        ChatToolExecutor.onQuickReplyOptions = { options in
            quickReplyOptions = options
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

        // Check for persisted messages from a previous session (e.g. app restart after screen recording)
        if let savedMessages = OnboardingChatPersistence.loadMessages() {
            log("OnboardingChatView: Restoring \(savedMessages.count) messages from previous session")
            chatProvider.messages = savedMessages

            // Resume the conversation — tell the AI the app was restarted
            Task {
                await chatProvider.sendMessage(
                    "I'm back — the app just restarted after granting a permission. Let's continue where we left off.",
                    systemPromptPrefix: systemPrompt,
                    sessionKey: "onboarding"
                )
            }
        } else {
            // Fresh start — clear messages and begin onboarding
            chatProvider.messages.removeAll()

            Task {
                await chatProvider.sendMessage(
                    "Hi, I just installed Omi!",
                    systemPromptPrefix: systemPrompt,
                    sessionKey: "onboarding"
                )
            }
        }
    }

    private func stopAgent() {
        chatProvider.stopAgent()
    }

    private func sendMessage() {
        guard canSend else { return }

        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        inputText = ""

        // Clear quick replies when user types their own message
        quickReplyOptions = []

        Task {
            await chatProvider.sendMessage(text, sessionKey: "onboarding")
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
        let mapping: [String: String] = [
            "microphone": "microphone",
            "mic": "microphone",
            "notifications": "notifications",
            "accessibility": "accessibility",
            "automation": "automation",
            "screen recording": "screen_recording",
        ]
        return mapping[name]
    }

    /// Handle quick reply button tap — triggers permission if applicable, then sends as user message
    private func handleQuickReply(_ option: String) {
        let options = quickReplyOptions
        quickReplyOptions = []

        if let permType = permissionType(from: option) {
            // Grant button — trigger the permission directly
            isGrantingPermission = true
            Task {
                let result = await ChatToolExecutor.execute(ToolCall(name: "request_permission", arguments: ["type": permType], thoughtSignature: nil))
                isGrantingPermission = false
                // Send the result as a user message so the AI knows what happened
                let replyText = result.contains("granted") ? "\(option) — done!" : "\(option) — \(result)"
                await chatProvider.sendMessage(replyText, sessionKey: "onboarding")
            }
        } else {
            // Regular quick reply — just send as message
            Task {
                await chatProvider.sendMessage(option, sessionKey: "onboarding")
            }
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

        // Clean up onboarding session key and persisted chat data
        chatProvider.onboardingSessionKey = nil
        OnboardingChatPersistence.clear()

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

    /// Whether this AI message has any visible content (non-empty text or visible tool calls)
    private var hasVisibleContent: Bool {
        if message.sender != .ai { return true }
        return message.contentBlocks.contains { block in
            switch block {
            case .toolCall(_, let name, _, _, _, _):
                return name != "ask_followup" // ask_followup renders its own UI separately
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
                            case .toolCall(_, let name, let status, _, let input, _):
                                let indicator = OnboardingToolIndicator(toolName: name, status: status, input: input)
                                if !indicator.isHidden {
                                    indicator
                                }
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
                            case .discoveryCard(_, let title, let summary, let fullText):
                                DiscoveryCard(title: title, summary: summary, fullText: fullText)
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
            if let permImage = permissionImageType {
                OnboardingPermissionImage(permissionType: permImage)
            }
        }
        .padding(.vertical, 2)
    }

    /// Whether this tool should be hidden from the UI (e.g. ask_followup renders its own UI)
    var isHidden: Bool {
        toolName == "ask_followup"
    }

    /// Determines which permission image to show based on the tool name and input
    private var permissionImageType: String? {
        switch toolName {
        case "scan_files", "start_file_scan":
            return "folder_access"
        case "request_permission":
            return input?.summary // summary contains the permission type (e.g., "microphone")
        default:
            return nil
        }
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
            } else if let url = Bundle.resourceBundle.url(forResource: info.name, withExtension: info.ext),
                      let nsImage = NSImage(contentsOf: url) {
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
