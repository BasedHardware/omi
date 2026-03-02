import SwiftUI
import MarkdownUI
import GRDB

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

    /// Clear all persisted onboarding data
    static func clear() {
        UserDefaults.standard.removeObject(forKey: sessionIdKey)
        UserDefaults.standard.removeObject(forKey: midOnboardingKey)
        UserDefaults.standard.removeObject(forKey: explorationTextKey)
        UserDefaults.standard.removeObject(forKey: explorationCompletedKey)
        UserDefaults.standard.removeObject(forKey: toolCompletedKey)
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
    @State private var isGrantingPermission: Bool = false
    @State private var pendingPermissionType: String? = nil  // e.g. "microphone" — waiting for user to grant
    @FocusState private var isInputFocused: Bool

    // Parallel exploration state
    @State private var explorationBridge: ACPBridge?
    @State private var explorationRunning = false
    @State private var explorationCompleted = false
    @State private var explorationText = ""
    @State private var explorationTask: Task<Void, Never>?

    // Timer to periodically check permission status
    let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Setting up omi")
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

                        // Parallel exploration card (appears after scan_files)
                        if explorationRunning || (explorationCompleted && !explorationText.isEmpty) {
                            ExplorationProfileCard(
                                text: explorationText,
                                isRunning: explorationRunning,
                                isCompleted: explorationCompleted
                            )
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.leading, 44) // align with message text
                            .id("exploration-card")
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
                        if onboardingCompleted && !chatProvider.isSending && !explorationRunning {
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
                TextField(quickReplyOptions.isEmpty ? "Type your message..." : "Or type your own answer...", text: $inputText, axis: .vertical)
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

        // Wire up onboarding tools
        ChatToolExecutor.onboardingAppState = appState
        ChatToolExecutor.onCompleteOnboarding = {
            onboardingCompleted = true
        }
        ChatToolExecutor.onQuickReplyOptions = { options in
            quickReplyOptions = options
        }
        ChatToolExecutor.onKnowledgeGraphUpdated = { [weak graphViewModel] in
            guard let vm = graphViewModel else { return }
            Task { await vm.addGraphFromStorage() }
        }
        ChatToolExecutor.onScanFilesCompleted = { [weak graphViewModel] fileCount in
            guard fileCount > 0 else { return }
            startExploration(fileCount: fileCount, graphViewModel: graphViewModel)
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
                    resumeSystemPrompt = systemPrompt + "\n\n<conversation_so_far>\n" + conversationContext + "\n</conversation_so_far>\n\nThe user's app just restarted after granting a macOS permission. Continue the onboarding from where you left off — do NOT re-ask questions the user already answered above."
                }

                // Wait for bridge warmup before sending
                await bridgeWarmup

                // Resume the conversation — tell the AI the app was restarted
                await chatProvider.sendMessage(
                    "I'm back — the app just restarted after granting a permission. Let's continue where we left off.",
                    systemPromptPrefix: resumeSystemPrompt,
                    resume: savedSessionId
                )
            }
        } else {
            // Fresh start — clear stale messages, mark mid-onboarding, begin
            chatProvider.messages.removeAll()
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

    private func sendMessage() {
        guard canSend else { return }

        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        inputText = ""

        // Clear quick replies when user types their own message
        quickReplyOptions = []

        Task {
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
        quickReplyOptions = []

        if let permType = permissionType(from: option) {
            // Grant button — trigger the permission directly
            isGrantingPermission = true
            Task {
                let result = await ChatToolExecutor.execute(ToolCall(name: "request_permission", arguments: ["type": permType], thoughtSignature: nil))
                isGrantingPermission = false

                if result.contains("granted") {
                    // Granted immediately — tell the AI
                    await chatProvider.sendMessage("\(option) — done!")
                } else {
                    // Pending — wait silently for the permission check timer to detect it
                    // The onChange handlers for appState.has*Permission will send the message
                    pendingPermissionType = permType
                }
            }
        } else {
            // Regular quick reply — just send as message
            Task {
                await chatProvider.sendMessage(option)
            }
        }
    }

    private func handleOnboardingComplete() {
        log("OnboardingChatView: Completing onboarding")

        // Set flag so DesktopHomeView navigates to Chat page after transition
        UserDefaults.standard.set(true, forKey: "onboardingJustCompleted")

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

        // Create welcome task (skip if it already exists from a previous onboarding)
        Task {
            let welcomeDescription = "Run omi for two days to start receiving helpful advice"
            let alreadyExists = await ActionItemStorage.shared.actionItemExists(description: welcomeDescription)
            if !alreadyExists {
                await TasksStore.shared.createTask(
                    description: welcomeDescription,
                    dueAt: Date(),
                    priority: "low"
                )
            }
        }

        // Send welcome notification
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            NotificationService.shared.sendNotification(
                title: "You're all set!",
                message: "Just go back to your work and run me in the background. I'll start sending you useful advice during your day."
            )
        }

        // Clean up parallel exploration
        explorationTask?.cancel()
        explorationTask = nil
        if let bridge = explorationBridge {
            Task { await bridge.stop() }
        }
        explorationBridge = nil

        // Clean up onboarding state and persisted chat data
        chatProvider.isOnboarding = false
        OnboardingChatPersistence.clear()

        // Log analytics
        AnalyticsManager.shared.onboardingCompleted()

        // Notify parent
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
            log("OnboardingChat: Restoring completed exploration from saved state (\(saved.text.count) chars)")
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
        let fileCount = (try? await dbQueue.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files")
        }) ?? 0

        if fileCount > 0 {
            log("OnboardingChat: Files already indexed (\(fileCount)), starting exploration on resume")
            startExploration(fileCount: fileCount, graphViewModel: graphViewModel)
        }
    }

    private func startExploration(fileCount: Int, graphViewModel: MemoryGraphViewModel?) {
        guard !explorationRunning else { return }
        explorationRunning = true
        log("OnboardingChat: Starting parallel exploration (\(fileCount) files indexed)")
        AnalyticsManager.shared.onboardingChatToolUsed(tool: "exploration_started", properties: ["file_count": fileCount])

        explorationTask = Task {
            do {
                let bridge = ACPBridge(passApiKey: true)
                await MainActor.run { explorationBridge = bridge }
                try await bridge.start()

                let userName = AuthService.shared.displayName.isEmpty ? "User" : AuthService.shared.displayName
                let schema = await Self.loadDatabaseSchema()
                let systemPrompt = ChatPromptBuilder.buildOnboardingExploration(userName: userName, databaseSchema: schema)

                let result = try await bridge.query(
                    prompt: "Begin exploration. \(fileCount) files have been indexed in the indexed_files table.",
                    systemPrompt: systemPrompt,
                    model: "claude-opus-4-6",
                    onTextDelta: { @Sendable delta in
                        Task { @MainActor in
                            explorationText += delta
                            // Persist partial text periodically (every ~500 chars) so it survives crashes
                            if explorationText.count % 500 < delta.count {
                                OnboardingChatPersistence.saveExplorationState(text: explorationText, completed: false)
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

                log("OnboardingChat: Exploration completed (cost=$\(String(format: "%.4f", result.costUsd)), tokens=\(result.inputTokens)+\(result.outputTokens))")
                AnalyticsManager.shared.onboardingChatToolUsed(tool: "exploration_completed", properties: [
                    "cost_usd": result.costUsd,
                    "input_tokens": result.inputTokens,
                    "output_tokens": result.outputTokens
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
                let rows = try Row.fetchAll(db, sql: """
                    SELECT name, sql FROM sqlite_master
                    WHERE type='table' AND sql IS NOT NULL
                    ORDER BY name
                """)
                return rows.compactMap { row -> (name: String, sql: String)? in
                    guard let name: String = row["name"],
                          let sql: String = row["sql"] else { return nil }
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
                      let closeParen = sql.lastIndex(of: ")") else { continue }
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
                    } else { current.append(char) }
                }
                let last = current.trimmingCharacters(in: .whitespacesAndNewlines)
                if !last.isEmpty { columnDefs.append(last) }

                let columnNames = columnDefs.filter { col in
                    let upper = col.uppercased().trimmingCharacters(in: .whitespaces)
                    return !upper.hasPrefix("UNIQUE") && !upper.hasPrefix("CHECK") &&
                           !upper.hasPrefix("FOREIGN") && !upper.hasPrefix("CONSTRAINT") &&
                           !upper.hasPrefix("PRIMARY KEY")
                }.compactMap { col -> String? in
                    let colName = col.components(separatedBy: .whitespaces).first?
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
        // Messages loaded from backend have empty contentBlocks but non-empty text
        if message.contentBlocks.isEmpty {
            return !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
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
        cleanToolName == "ask_followup"
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
        case "scan_files", "start_file_scan":
            return "folder_access"
        case "request_permission":
            return input?.summary // summary contains the permission type (e.g., "microphone")
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
            return status == .running ? "Building knowledge graph..." : "Knowledge graph saved"
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
