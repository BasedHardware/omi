import SwiftUI
import Combine
import GRDB

// MARK: - UserDefaults Extension for KVO

extension UserDefaults {
    @objc dynamic var multiChatEnabled: Bool {
        return bool(forKey: "multiChatEnabled")
    }
    @objc dynamic var playwrightUseExtension: Bool {
        return bool(forKey: "playwrightUseExtension")
    }
}

// MARK: - Chat Session Model

/// A chat session that groups related messages
struct ChatSession: Identifiable, Codable, Equatable {
    let id: String
    var title: String
    var preview: String?
    let createdAt: Date
    var updatedAt: Date
    let appId: String?
    var messageCount: Int
    var starred: Bool

    enum CodingKeys: String, CodingKey {
        case id, title, preview, starred
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case appId = "app_id"
        case messageCount = "message_count"
    }

    init(id: String = UUID().uuidString, title: String = "New Chat", preview: String? = nil,
         createdAt: Date = Date(), updatedAt: Date = Date(), appId: String? = nil,
         messageCount: Int = 0, starred: Bool = false) {
        self.id = id
        self.title = title
        self.preview = preview
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.appId = appId
        self.messageCount = messageCount
        self.starred = starred
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decodeIfPresent(String.self, forKey: .title) ?? "New Chat"
        preview = try container.decodeIfPresent(String.self, forKey: .preview)
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
        appId = try container.decodeIfPresent(String.self, forKey: .appId)
        messageCount = try container.decodeIfPresent(Int.self, forKey: .messageCount) ?? 0
        starred = try container.decodeIfPresent(Bool.self, forKey: .starred) ?? false
    }
}

// MARK: - Content Block Model

/// Structured tool input for inline display
struct ToolCallInput {
    /// Short summary for inline display (e.g., file path, command)
    let summary: String
    /// Full JSON details for expanded view
    let details: String?
}

/// A block of content within an AI message (text or tool call indicator)
enum ChatContentBlock: Identifiable {
    case text(id: String, text: String)
    case toolCall(id: String, name: String, status: ToolCallStatus,
                  toolUseId: String? = nil,
                  input: ToolCallInput? = nil,
                  output: String? = nil)
    case thinking(id: String, text: String)

    var id: String {
        switch self {
        case .text(let id, _): return id
        case .toolCall(let id, _, _, _, _, _): return id
        case .thinking(let id, _): return id
        }
    }

    /// Human-friendly display name for a tool
    static func displayName(for toolName: String) -> String {
        // Strip MCP prefix (e.g., "mcp__omi-tools__execute_sql" → "execute_sql")
        let cleanName: String
        if toolName.hasPrefix("mcp__") {
            cleanName = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleanName = toolName
        }

        switch cleanName {
        case "execute_sql": return "Querying database"
        case "semantic_search": return "Searching conversations"
        case "Read": return "Reading file"
        case "Write": return "Writing file"
        case "Edit": return "Editing file"
        case "Bash": return "Running command"
        case "Grep": return "Searching code"
        case "Glob": return "Finding files"
        case "WebSearch": return "Searching the web"
        case "WebFetch": return "Fetching page"
        default: return "Using \(cleanName)"
        }
    }

    /// Extracts a short summary from tool input for inline display
    static func toolInputSummary(for toolName: String, input: [String: Any]) -> ToolCallInput? {
        let cleanName: String
        if toolName.hasPrefix("mcp__") {
            cleanName = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleanName = toolName
        }

        let summary: String?
        switch cleanName {
        case "Read":
            summary = input["file_path"] as? String
        case "Write", "Edit":
            summary = input["file_path"] as? String
        case "Bash":
            if let cmd = input["command"] as? String {
                summary = cmd.count > 80 ? String(cmd.prefix(80)) + "…" : cmd
            } else {
                summary = nil
            }
        case "Grep":
            let pattern = input["pattern"] as? String ?? ""
            let path = input["path"] as? String
            summary = path != nil ? "\(pattern) in \(path!)" : pattern
        case "Glob":
            summary = input["pattern"] as? String
        case "WebSearch":
            summary = input["query"] as? String
        case "WebFetch":
            summary = input["url"] as? String
        case "execute_sql":
            if let query = input["query"] as? String {
                summary = query.count > 100 ? String(query.prefix(100)) + "…" : query
            } else {
                summary = nil
            }
        case "semantic_search":
            summary = input["query"] as? String
        default:
            // Try common key names
            summary = (input["file_path"] ?? input["path"] ?? input["query"] ?? input["command"]) as? String
        }

        guard let summary = summary, !summary.isEmpty else { return nil }

        // Build full details JSON
        let details: String?
        if let data = try? JSONSerialization.data(withJSONObject: input, options: [.prettyPrinted, .sortedKeys]),
           let str = String(data: data, encoding: .utf8) {
            details = str
        } else {
            details = nil
        }

        return ToolCallInput(summary: summary, details: details)
    }
}

enum ToolCallStatus {
    case running
    case completed
}

// MARK: - Chat Message Model

/// A single chat message
struct ChatMessage: Identifiable {
    var id: String  // Mutable to sync with server-generated ID
    var text: String
    let createdAt: Date
    let sender: ChatSender
    var isStreaming: Bool
    /// Rating: 1 = thumbs up, -1 = thumbs down, nil = no rating
    var rating: Int?
    /// Whether the message has been synced with the backend (has valid server ID)
    var isSynced: Bool
    /// Citations extracted from the AI response
    var citations: [Citation]
    /// Structured content blocks for AI messages (text interspersed with tool calls)
    var contentBlocks: [ChatContentBlock]

    init(id: String = UUID().uuidString, text: String, createdAt: Date = Date(), sender: ChatSender, isStreaming: Bool = false, rating: Int? = nil, isSynced: Bool = false, citations: [Citation] = [], contentBlocks: [ChatContentBlock] = []) {
        self.id = id
        self.text = text
        self.createdAt = createdAt
        self.sender = sender
        self.isStreaming = isStreaming
        self.rating = rating
        self.isSynced = isSynced
        self.citations = citations
        self.contentBlocks = contentBlocks
    }
}

enum ChatSender {
    case user
    case ai
}

extension ChatMessage {
    /// Convert a backend message to a local ChatMessage
    init(from db: ChatMessageDB) {
        self.init(
            id: db.id,
            text: db.text,
            createdAt: db.createdAt,
            sender: db.sender == "human" ? .user : .ai,
            isStreaming: false,
            rating: db.rating,
            isSynced: true
        )
    }
}

// MARK: - Citation Model

/// A citation referencing a source conversation or memory
struct Citation: Identifiable {
    let id: String
    let sourceType: CitationSourceType
    let title: String
    let preview: String
    let emoji: String?
    let createdAt: Date?

    enum CitationSourceType {
        case conversation
        case memory
    }
}

// MARK: - Chat Mode

/// Controls whether the AI agent can perform write actions (Act) or is restricted to read-only (Ask)
enum ChatMode: String, CaseIterable {
    case ask
    case act
}

/// State management for chat functionality with Claude Agent SDK
/// Uses hybrid architecture: Swift → Claude Agent (via Node.js bridge) for AI, Backend for persistence + context
@MainActor
class ChatProvider: ObservableObject {
    // MARK: - Published State
    @Published var chatMode: ChatMode = .act
    @Published var draftText = ""
    @Published var messages: [ChatMessage] = []
    @Published var sessions: [ChatSession] = []
    @Published var currentSession: ChatSession?
    @Published var isLoading = false
    @Published var isLoadingSessions = true  // Start true since we load sessions on init
    @Published var isSending = false
    @Published var isStopping = false
    @Published var isClearing = false
    @Published var errorMessage: String?
    @Published var sessionsLoadError: String?
    @Published var selectedAppId: String?
    @Published var hasMoreMessages = false
    @Published var isLoadingMoreMessages = false
    @Published var showStarredOnly = false
    @Published var searchQuery = ""

    /// Triggered when a browser tool is called but the extension token isn't configured.
    /// The UI should observe this and present BrowserExtensionSetup.
    @Published var needsBrowserExtensionSetup = false

    /// Whether the user is currently viewing the default chat (syncs with Flutter app)
    @Published var isInDefaultChat = true

    /// Working directory for Claude Agent SDK file-system tools (Read, Write, Bash, etc.)
    /// Set by TaskChatCoordinator to point at the user's project directory.
    var workingDirectory: String?

    /// Override app ID for message routing (e.g. "task-chat" to isolate task messages).
    /// When set, messages are saved with this app_id so the backend routes them
    /// to the correct session instead of the default chat.
    var overrideAppId: String?

    /// Override the Claude model for this provider's queries.
    /// When set, the bridge uses this model instead of the default (Opus).
    /// e.g. "claude-sonnet-4-6" for faster floating bar responses.
    var modelOverride: String?

    /// Multi-chat mode setting - when false, only default chat is shown (syncs with Flutter)
    /// When true, user can create multiple chat sessions
    @AppStorage("multiChatEnabled") var multiChatEnabled = false

    private let claudeBridge = ClaudeAgentBridge()
    private var bridgeStarted = false

    // MARK: - Dual Bridge (Mode A: Agent SDK, Mode B: ACP)
    private let acpBridge = ACPBridge()
    private var acpBridgeStarted = false

    enum BridgeMode: String {
        case agentSDK = "agentSDK"
        case claudeCode = "claudeCode"
    }
    @AppStorage("chatBridgeMode") var bridgeMode: String = BridgeMode.agentSDK.rawValue

    /// Whether the ACP bridge requires authentication (shown as sheet in UI)
    @Published var isClaudeAuthRequired = false
    /// Auth methods returned by ACP bridge
    @Published var claudeAuthMethods: [[String: Any]] = []

    private let messagesPageSize = 50
    private var multiChatObserver: AnyCancellable?
    private var playwrightExtensionObserver: AnyCancellable?

    // MARK: - Cross-Platform Message Polling
    /// Polls for new messages from other platforms (mobile) every 15 seconds.
    /// Similar to TasksStore's 30-second polling pattern.
    private var messagePollTimer: AnyCancellable?
    private static let messagePollInterval: TimeInterval = 15.0

    // MARK: - Streaming Buffer
    /// Accumulates text deltas during streaming and flushes them to the published
    /// messages array at most once per ~100ms, reducing SwiftUI re-render frequency.
    private var streamingTextBuffer: String = ""
    private var streamingThinkingBuffer: String = ""
    private var streamingBufferMessageId: String?
    private var streamingFlushWorkItem: DispatchWorkItem?
    private let streamingFlushInterval: TimeInterval = 0.1

    // MARK: - Filtered Sessions
    var filteredSessions: [ChatSession] {
        // Filter out "empty" sessions (only AI greeting, no user messages)
        // These have messageCount <= 1 and default "New Chat" title
        // Always keep the currently selected session visible
        let nonEmptySessions = sessions.filter { session in
            // Always show the current session (so user can continue working)
            if session.id == currentSession?.id { return true }
            // Keep sessions that have user messages (more than just AI greeting)
            // or have been renamed (user intentionally kept them)
            return session.messageCount > 1 || session.title != "New Chat"
        }

        guard !searchQuery.isEmpty else { return nonEmptySessions }
        let query = searchQuery.lowercased()
        return nonEmptySessions.filter { session in
            session.title.lowercased().contains(query) ||
            (session.preview?.lowercased().contains(query) ?? false)
        }
    }

    // MARK: - Cached Context for Prompts
    private var cachedMemories: [ServerMemory] = []
    private var memoriesLoaded = false
    private var cachedGoals: [Goal] = []
    private var goalsLoaded = false
    private var cachedTasks: [TaskActionItem] = []
    private var tasksLoaded = false
    private var cachedAIProfile: String = ""
    private var aiProfileLoaded = false
    private var cachedDatabaseSchema: String = ""
    private var schemaLoaded = false

    // MARK: - CLAUDE.md & Skills (Global)
    @Published var claudeMdContent: String?
    @Published var claudeMdPath: String?
    @Published var discoveredSkills: [(name: String, description: String, path: String)] = []
    @AppStorage("claudeMdEnabled") var claudeMdEnabled = true
    @AppStorage("disabledSkillsJSON") private var disabledSkillsJSON: String = ""

    // MARK: - Project-level CLAUDE.md & Skills
    @AppStorage("aiChatWorkingDirectory") var aiChatWorkingDirectory: String = ""
    @Published var projectClaudeMdContent: String?
    @Published var projectClaudeMdPath: String?
    @Published var projectDiscoveredSkills: [(name: String, description: String, path: String)] = []
    @AppStorage("projectClaudeMdEnabled") var projectClaudeMdEnabled = true

    // MARK: - Dev Mode
    @AppStorage("devModeEnabled") var devModeEnabled = false
    private var devModeContext: String?

    // MARK: - Current Session ID
    var currentSessionId: String? {
        currentSession?.id
    }

    // MARK: - Current Model
    var currentModel: String {
        "Claude"
    }

    // MARK: - System Prompt
    // Prompts are defined in ChatPrompts.swift (converted from Python backend)

    init() {
        log("ChatProvider initialized, will start Claude bridge on first use")

        // Observe changes to multiChatEnabled setting
        multiChatObserver = UserDefaults.standard.publisher(for: \.multiChatEnabled)
            .dropFirst() // Skip initial value
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.reinitialize()
                }
            }

        // Poll for new messages from other platforms (mobile) every 15 seconds
        messagePollTimer = Timer.publish(every: Self.messagePollInterval, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.pollForNewMessages()
                }
            }

        // Observe changes to Playwright extension mode setting — restart bridge to pick up new env vars
        playwrightExtensionObserver = UserDefaults.standard.publisher(for: \.playwrightUseExtension)
            .dropFirst()
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { @MainActor in
                    guard let self = self else { return }
                    guard !self.isSending else {
                        log("ChatProvider: Skipping bridge restart — query in progress")
                        return
                    }
                    if self.isACPMode {
                        guard self.acpBridgeStarted else { return }
                        log("ChatProvider: Playwright extension setting changed, restarting ACP bridge")
                        self.acpBridgeStarted = false
                        do {
                            try await self.acpBridge.restart()
                            self.acpBridgeStarted = true
                            log("ChatProvider: ACP bridge restarted with new Playwright settings")
                        } catch {
                            logError("Failed to restart ACP bridge after Playwright setting change", error: error)
                        }
                    } else {
                        guard self.bridgeStarted else { return }
                        log("ChatProvider: Playwright extension setting changed, restarting bridge")
                        self.bridgeStarted = false
                        do {
                            try await self.claudeBridge.restart()
                            self.bridgeStarted = true
                            log("ChatProvider: Bridge restarted with new Playwright settings")
                        } catch {
                            logError("Failed to restart bridge after Playwright setting change", error: error)
                        }
                    }
                }
            }
    }

    /// Pre-start the active bridge so the first query doesn't wait for process launch
    func warmupBridge() async {
        _ = await ensureBridgeStarted()
    }

    /// Test that the Playwright Chrome extension is connected and working.
    /// Ensures the bridge is started (restarting if needed to pick up new token),
    /// then sends a lightweight test query that triggers a browser_snapshot tool call.
    func testPlaywrightConnection() async throws -> Bool {
        // Only use agent-bridge for Playwright testing (Mode A always has our API key)
        bridgeStarted = false
        do {
            try await claudeBridge.restart()
            bridgeStarted = true
        } catch {
            // If restart fails, try a fresh start
            try await claudeBridge.start()
            bridgeStarted = true
        }
        return try await claudeBridge.testPlaywrightConnection()
    }

    /// Whether we're currently in ACP (Mode B) mode
    private var isACPMode: Bool {
        bridgeMode == BridgeMode.claudeCode.rawValue
    }

    /// Ensure the active bridge is started (restarts if the process died)
    private func ensureBridgeStarted() async -> Bool {
        if isACPMode {
            // Mode B: ACP bridge
            if acpBridgeStarted {
                let alive = await acpBridge.isAlive
                if !alive {
                    log("ChatProvider: ACP bridge process died, will restart")
                    acpBridgeStarted = false
                }
            }
            guard !acpBridgeStarted else { return true }
            do {
                try await acpBridge.start()
                acpBridgeStarted = true
                log("ChatProvider: ACP bridge started successfully")
                // Pre-warm an ACP session in background so first query is faster
                await acpBridge.warmupSession(cwd: workingDirectory, models: ["claude-opus-4-6", "claude-sonnet-4-6"])
                return true
            } catch {
                logError("Failed to start ACP bridge", error: error)
                errorMessage = "AI not available: \(error.localizedDescription)"
                return false
            }
        } else {
            // Mode A: Agent SDK bridge (existing)
            if bridgeStarted {
                let alive = await claudeBridge.isAlive
                if !alive {
                    log("ChatProvider: Bridge process died, will restart")
                    bridgeStarted = false
                }
            }
            guard !bridgeStarted else { return true }
            do {
                try await claudeBridge.start()
                bridgeStarted = true
                log("ChatProvider: Claude bridge started successfully")
                return true
            } catch {
                logError("Failed to start Claude bridge", error: error)
                errorMessage = "AI not available: \(error.localizedDescription)"
                return false
            }
        }
    }

    /// Switch between bridge modes (Agent SDK vs Claude Code ACP)
    func switchBridgeMode(to mode: BridgeMode) async {
        guard mode.rawValue != bridgeMode else { return }
        log("ChatProvider: Switching bridge mode from \(bridgeMode) to \(mode.rawValue)")

        // Stop the current bridge
        if isACPMode {
            await acpBridge.stop()
            acpBridgeStarted = false
        } else {
            await claudeBridge.stop()
            bridgeStarted = false
        }

        // Switch mode
        bridgeMode = mode.rawValue

        // Warm up the new bridge
        _ = await ensureBridgeStarted()
    }

    /// Start Claude OAuth authentication (Mode B)
    func startClaudeAuth() {
        guard isACPMode else { return }
        Task {
            // Pick the first available auth method (usually "agent_auth")
            let methodId = (claudeAuthMethods.first?["id"] as? String) ?? "auth-0"
            await acpBridge.authenticate(methodId: methodId)
        }
    }

    // MARK: - Session Management

    /// Fetch all chat sessions for the current app (retries up to 3 times on failure)
    func fetchSessions() async {
        isLoadingSessions = true
        defer { isLoadingSessions = false }

        let maxAttempts = 3
        let delays: [UInt64] = [1_000_000_000, 2_000_000_000] // 1s, 2s
        var lastError: Error?

        for attempt in 1...maxAttempts {
            do {
                sessions = try await APIClient.shared.getChatSessions(
                    appId: selectedAppId,
                    starred: showStarredOnly ? true : nil
                )
                log("ChatProvider loaded \(sessions.count) sessions (starred filter: \(showStarredOnly))")
                sessionsLoadError = nil

                // If we have sessions and no current session, select the most recent
                if currentSession == nil, let mostRecent = sessions.first {
                    await selectSession(mostRecent)
                }
                return
            } catch {
                lastError = error
                logError("Failed to load chat sessions (attempt \(attempt)/\(maxAttempts))", error: error)
                if attempt < maxAttempts {
                    try? await Task.sleep(nanoseconds: delays[attempt - 1])
                }
            }
        }

        sessions = []
        sessionsLoadError = lastError?.localizedDescription ?? "Unknown error"
    }

    /// Toggle the starred filter and reload sessions
    func toggleStarredFilter() async {
        showStarredOnly.toggle()
        log("Toggled starred filter: \(showStarredOnly)")
        AnalyticsManager.shared.chatStarredFilterToggled(enabled: showStarredOnly)
        await fetchSessions()
    }

    /// Create a new chat session
    /// - Parameters:
    ///   - title: Optional session title
    ///   - skipGreeting: Skip the initial AI greeting message
    ///   - appId: Override app ID (e.g. "task-chat" to isolate task sessions from default chat)
    func createNewSession(title: String? = nil, skipGreeting: Bool = false, appId: String? = nil) async -> ChatSession? {
        do {
            let session = try await APIClient.shared.createChatSession(title: title, appId: appId ?? selectedAppId)
            sessions.insert(session, at: 0)
            currentSession = session
            isInDefaultChat = false
            messages = []
            hasMoreMessages = false
            log("Created new chat session: \(session.id)")
            AnalyticsManager.shared.chatSessionCreated()

            // Generate initial greeting message (skip for task chats that send their own context)
            if !skipGreeting {
                await fetchInitialMessage(for: session)
            }

            return session
        } catch {
            logError("Failed to create chat session", error: error)
            errorMessage = "Failed to create new chat"
            return nil
        }
    }

    /// Fetch and display an initial greeting message for a new session
    private func fetchInitialMessage(for session: ChatSession) async {
        do {
            let response = try await APIClient.shared.getInitialMessage(
                sessionId: session.id,
                appId: selectedAppId
            )

            // Add the AI greeting to messages (already has server ID)
            let greetingMessage = ChatMessage(
                id: response.messageId,
                text: response.message,
                createdAt: Date(),
                sender: .ai,
                isStreaming: false,
                rating: nil,
                isSynced: true
            )
            messages.append(greetingMessage)

            // Update session preview
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index].preview = response.message
            }

            // Track analytics
            AnalyticsManager.shared.initialMessageGenerated(hasApp: selectedAppId != nil)

            log("Added initial greeting message for session \(session.id)")
        } catch {
            // Non-fatal: session still works without greeting
            logError("Failed to fetch initial message", error: error)
        }
    }

    /// Select a session and load its messages
    func selectSession(_ session: ChatSession, force: Bool = false) async {
        guard force || currentSession?.id != session.id || isInDefaultChat else { return }

        currentSession = session
        isInDefaultChat = false
        isLoading = true
        errorMessage = nil
        hasMoreMessages = false

        do {
            let persistedMessages = try await APIClient.shared.getMessages(
                sessionId: session.id,
                limit: messagesPageSize
            )
            messages = persistedMessages.map(ChatMessage.init(from:))
                .sorted(by: { $0.createdAt < $1.createdAt })
            // If we got a full page, there might be more messages
            hasMoreMessages = persistedMessages.count == messagesPageSize
            log("ChatProvider loaded \(messages.count) messages for session \(session.id), hasMore: \(hasMoreMessages)")
        } catch {
            logError("Failed to load messages for session", error: error)
            messages = []
        }

        isLoading = false
    }

    /// Load more (older) messages for the current session
    func loadMoreMessages() async {
        guard hasMoreMessages,
              !isLoadingMoreMessages else { return }

        isLoadingMoreMessages = true

        do {
            let offset = messages.count
            let olderMessages: [ChatMessageDB]
            if let sessionId = currentSessionId {
                olderMessages = try await APIClient.shared.getMessages(
                    sessionId: sessionId,
                    limit: messagesPageSize,
                    offset: offset
                )
            } else {
                olderMessages = try await APIClient.shared.getMessages(
                    appId: selectedAppId,
                    limit: messagesPageSize,
                    offset: offset
                )
            }

            let newMessages = olderMessages.map(ChatMessage.init(from:))

            // Append older messages and re-sort to ensure correct chronological order
            messages.append(contentsOf: newMessages)
            messages.sort(by: { $0.createdAt < $1.createdAt })

            // Check if there are more
            hasMoreMessages = olderMessages.count == messagesPageSize
            log("Loaded \(newMessages.count) more messages, total: \(messages.count), hasMore: \(hasMoreMessages)")
        } catch {
            logError("Failed to load more messages", error: error)
        }

        isLoadingMoreMessages = false
    }

    /// Track which sessions are currently being deleted
    @Published var deletingSessionIds: Set<String> = []

    /// Delete a chat session
    func deleteSession(_ session: ChatSession) async {
        deletingSessionIds.insert(session.id)
        do {
            try await APIClient.shared.deleteChatSession(sessionId: session.id)
            deletingSessionIds.remove(session.id)
            sessions.removeAll { $0.id == session.id }

            // If deleted the current session, select another or clear
            if currentSession?.id == session.id {
                if let nextSession = sessions.first {
                    await selectSession(nextSession)
                } else {
                    currentSession = nil
                    messages = []
                }
            }

            log("Deleted chat session: \(session.id)")
            AnalyticsManager.shared.chatSessionDeleted()
        } catch {
            deletingSessionIds.remove(session.id)
            logError("Failed to delete chat session", error: error)
            errorMessage = "Failed to delete chat"
        }
    }

    /// Toggle starred status for a session
    func toggleStarred(_ session: ChatSession) async {
        do {
            let updated = try await APIClient.shared.updateChatSession(
                sessionId: session.id,
                starred: !session.starred
            )

            // Update in sessions list
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index] = updated
            }

            // Update current session if it's the same
            if currentSession?.id == session.id {
                currentSession = updated
            }

            log("Toggled starred for session \(session.id): \(updated.starred)")
        } catch {
            logError("Failed to toggle starred", error: error)
        }
    }

    /// Update session title (user-initiated rename)
    func updateSessionTitle(_ session: ChatSession, title: String) async {
        do {
            let updated = try await APIClient.shared.updateChatSession(
                sessionId: session.id,
                title: title
            )

            // Update in sessions list
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index] = updated
            }

            // Update current session if it's the same
            if currentSession?.id == session.id {
                currentSession = updated
            }

            log("Updated title for session \(session.id): \(title)")
            AnalyticsManager.shared.sessionRenamed()
        } catch {
            logError("Failed to update session title", error: error)
        }
    }

    // MARK: - Load Context (Memories)

    /// Loads user memories from local SQLite for use in prompts
    private func loadMemoriesIfNeeded() async {
        guard !memoriesLoaded else { return }

        do {
            cachedMemories = try await MemoryStorage.shared.getLocalMemories(limit: 50)
            memoriesLoaded = true
            log("ChatProvider loaded \(cachedMemories.count) memories from local DB")
        } catch {
            logError("Failed to load memories from local DB", error: error)
            // Continue without memories - non-critical
        }
    }

    /// Formats cached memories into a string for the prompt
    private func formatMemoriesSection() -> String {
        guard !cachedMemories.isEmpty else { return "" }

        let userName = AuthService.shared.displayName.isEmpty ? "the user" : AuthService.shared.givenName

        var lines: [String] = ["<user_facts>", "Facts about \(userName):"]
        for memory in cachedMemories.prefix(30) {  // Limit to 30 most relevant
            lines.append("- \(memory.content)")
        }
        lines.append("</user_facts>")

        return lines.joined(separator: "\n")
    }

    // MARK: - Load Goals

    /// Loads user goals from local SQLite for use in prompts
    private func loadGoalsIfNeeded() async {
        guard !goalsLoaded else { return }

        do {
            cachedGoals = try await GoalStorage.shared.getLocalGoals(activeOnly: false)
            goalsLoaded = true
            log("ChatProvider loaded \(cachedGoals.count) goals from local DB")
        } catch {
            logError("Failed to load goals for chat context", error: error)
        }
    }

    /// Formats goals into a prompt section
    private func formatGoalSection() -> String {
        let activeGoals = cachedGoals.filter { $0.isActive }
        guard !activeGoals.isEmpty else { return "" }

        var lines: [String] = ["\n<user_goals>"]
        for goal in activeGoals {
            var line = "- \(goal.title)"
            if let desc = goal.description, !desc.isEmpty {
                line += ": \(desc)"
            }
            if goal.goalType != .boolean {
                line += " (progress: \(Int(goal.currentValue))/\(Int(goal.targetValue))"
                if let unit = goal.unit, !unit.isEmpty { line += " \(unit)" }
                line += ")"
            }
            lines.append(line)
        }
        lines.append("</user_goals>")
        return lines.joined(separator: "\n")
    }

    // MARK: - Load Tasks

    /// Fetches the latest 20 active tasks from local database for context
    private func loadTasksIfNeeded() async {
        guard !tasksLoaded else { return }

        do {
            cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: 20,
                completed: false
            )
            tasksLoaded = true
            log("ChatProvider loaded \(cachedTasks.count) tasks for context")
        } catch {
            logError("Failed to load tasks for chat context", error: error)
            tasksLoaded = true
        }
    }

    /// Formats cached tasks into a prompt section
    private func formatTasksSection() -> String {
        guard !cachedTasks.isEmpty else { return "" }

        var lines: [String] = ["\n<user_tasks>", "Current tasks:"]
        for task in cachedTasks {
            var line = "- \(task.description)"
            if let priority = task.priority {
                line += " [priority: \(priority)]"
            }
            if let dueAt = task.dueAt {
                let formatter = DateFormatter()
                formatter.dateStyle = .short
                formatter.timeStyle = .short
                line += " [due: \(formatter.string(from: dueAt))]"
            }
            if let category = task.category {
                line += " [category: \(category)]"
            }
            lines.append(line)
        }
        lines.append("</user_tasks>")
        return lines.joined(separator: "\n")
    }

    // MARK: - Load AI User Profile

    /// Fetches the latest AI-generated user profile from local database
    private func loadAIProfileIfNeeded() async {
        guard !aiProfileLoaded else { return }

        if let profile = await AIUserProfileService.shared.getLatestProfile() {
            cachedAIProfile = profile.profileText
            log("ChatProvider loaded AI profile (generated \(profile.generatedAt))")
        }
        aiProfileLoaded = true
    }

    /// Formats AI profile into a prompt section
    private func formatAIProfileSection() -> String {
        guard !cachedAIProfile.isEmpty else { return "" }
        return "\n<ai_user_profile>\n\(cachedAIProfile)\n</ai_user_profile>"
    }

    // MARK: - Load Database Schema

    /// Queries sqlite_master to build an up-to-date schema description for the prompt
    private func loadSchemaIfNeeded() async {
        guard !schemaLoaded else { return }

        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            log("ChatProvider: database not available for schema introspection")
            schemaLoaded = true
            return
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

            cachedDatabaseSchema = formatSchema(tables: tables)
            schemaLoaded = true
            log("ChatProvider loaded schema for \(tables.count) tables")
        } catch {
            logError("Failed to load database schema", error: error)
            schemaLoaded = true
        }
    }

    /// Formats raw DDL into a compact, LLM-friendly schema block
    private func formatSchema(tables: [(name: String, sql: String)]) -> String {
        var lines: [String] = ["**Database schema (omi.db):**", ""]

        for (name, sql) in tables {
            // Skip internal/FTS tables
            if ChatPrompts.excludedTables.contains(name) { continue }
            if ChatPrompts.excludedTablePrefixes.contains(where: { name.hasPrefix($0) }) { continue }

            // Extract columns from CREATE TABLE statement
            let columns = extractColumns(from: sql)
            guard !columns.isEmpty else { continue }

            // Table header with annotation
            let annotation = ChatPrompts.tableAnnotations[name] ?? ""
            let header = annotation.isEmpty ? name : "\(name) — \(annotation)"
            lines.append(header)

            // Columns as compact one-liner
            lines.append("  \(columns.joined(separator: ", "))")
            lines.append("")
        }

        // Append FTS table note
        lines.append(ChatPrompts.schemaFooter)

        return lines.joined(separator: "\n")
    }

    /// Extracts column definitions from a CREATE TABLE SQL statement
    /// Produces compact representations like: "id INTEGER PRIMARY KEY", "name TEXT NOT NULL"
    private func extractColumns(from sql: String) -> [String] {
        // Find content between first ( and last )
        guard let openParen = sql.firstIndex(of: "("),
              let closeParen = sql.lastIndex(of: ")") else { return [] }

        let body = String(sql[sql.index(after: openParen)..<closeParen])

        // Split by commas, but respect parentheses (for REFERENCES(...) etc.)
        var columns: [String] = []
        var current = ""
        var depth = 0
        for char in body {
            if char == "(" { depth += 1 }
            else if char == ")" { depth -= 1 }

            if char == "," && depth == 0 {
                let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { columns.append(trimmed) }
                current = ""
            } else {
                current.append(char)
            }
        }
        let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { columns.append(trimmed) }

        // Filter out table constraints (UNIQUE, CHECK, FOREIGN KEY, etc.) — keep only column defs
        return columns.filter { col in
            let upper = col.uppercased().trimmingCharacters(in: .whitespaces)
            return !upper.hasPrefix("UNIQUE") && !upper.hasPrefix("CHECK") &&
                   !upper.hasPrefix("FOREIGN") && !upper.hasPrefix("CONSTRAINT") &&
                   !upper.hasPrefix("PRIMARY KEY")
        }.map { col in
            // Normalize whitespace
            col.components(separatedBy: .whitespacesAndNewlines)
                .filter { !$0.isEmpty }
                .joined(separator: " ")
        }
    }

    // MARK: - Build System Prompt with Variables

    /// Builds the system prompt with dynamic template variables
    private func buildSystemPrompt(contextString: String) -> String {
        // Get user name from AuthService
        let userName = AuthService.shared.displayName.isEmpty ? "there" : AuthService.shared.givenName

        // Use the context string from backend (includes memories + conversations)
        // Fall back to just memories if context is empty
        let contextSection = contextString.isEmpty ? formatMemoriesSection() : contextString

        // Build individual sections
        let goalSection = formatGoalSection()
        let tasksSection = formatTasksSection()
        let aiProfileSection = formatAIProfileSection()
        let historyMessages = messages.filter { !$0.text.isEmpty && !$0.isStreaming }
        let historyCount = min(historyMessages.count, 20)

        // Build base prompt with goals, AI profile, and dynamic schema
        var prompt = ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: contextSection,
            goalSection: goalSection,
            tasksSection: tasksSection,
            aiProfileSection: aiProfileSection,
            databaseSchema: cachedDatabaseSchema
        )

        // Append conversation history from Firestore (source of truth for cross-platform sync)
        let history = buildConversationHistory()
        if !history.isEmpty {
            prompt += "\n\n<conversation_history>\n\(history)\n</conversation_history>"
        }

        // Append global CLAUDE.md instructions if enabled
        if claudeMdEnabled, let claudeMd = claudeMdContent {
            prompt += "\n\n<claude_md>\n\(claudeMd)\n</claude_md>"
        }

        // Append project CLAUDE.md instructions if enabled
        if projectClaudeMdEnabled, let projectClaudeMd = projectClaudeMdContent {
            prompt += "\n\n<project_claude_md>\n\(projectClaudeMd)\n</project_claude_md>"
        }

        // Append enabled skills as available context (global + project)
        // Exclude dev-mode from the regular skills list — it has its own dedicated section
        let enabledSkillNames = getEnabledSkillNames()
        if !enabledSkillNames.isEmpty {
            let allSkills = discoveredSkills + projectDiscoveredSkills
            let skillDescriptions = allSkills
                .filter { enabledSkillNames.contains($0.name) && $0.name != "dev-mode" }
                .map { "- \($0.name): \($0.description)" }
                .joined(separator: "\n")
            if !skillDescriptions.isEmpty {
                prompt += "\n\n<available_skills>\n\(skillDescriptions)\n</available_skills>"
            }
        }

        // Append dev mode context if enabled (full skill content, not just description)
        if devModeEnabled, let devMode = devModeContext {
            let workspaceDir = aiChatWorkingDirectory.isEmpty ? "not set" : aiChatWorkingDirectory
            prompt += "\n\n<dev_mode>\nDev Mode is ENABLED. The user has opted in to app customization.\nWorkspace: \(workspaceDir)\n\n\(devMode)\n</dev_mode>"
        }

        // Log prompt context summary
        let activeGoalCount = cachedGoals.filter { $0.isActive }.count
        log("ChatProvider: prompt built — schema: \(!cachedDatabaseSchema.isEmpty ? "yes" : "no"), goals: \(activeGoalCount), tasks: \(cachedTasks.count), ai_profile: \(!cachedAIProfile.isEmpty ? "yes" : "no"), memories: \(cachedMemories.count), history: \(historyCount) msgs, claude_md: \(claudeMdEnabled && claudeMdContent != nil ? "yes" : "no"), project_claude_md: \(projectClaudeMdEnabled && projectClaudeMdContent != nil ? "yes" : "no"), skills: \(enabledSkillNames.count), dev_mode: \(devModeEnabled && devModeContext != nil ? "yes" : "no"), prompt_length: \(prompt.count) chars")

        return prompt
    }

    /// Build system prompt for task chat sessions.
    /// Same as buildSystemPrompt but **omits** conversation_history section
    /// (the Claude SDK handles history via `resume: sessionId`).
    func buildTaskChatSystemPrompt() -> String {
        let userName = AuthService.shared.displayName.isEmpty ? "there" : AuthService.shared.givenName
        let contextSection = formatMemoriesSection()
        let goalSection = formatGoalSection()
        let tasksSection = formatTasksSection()
        let aiProfileSection = formatAIProfileSection()

        var prompt = ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: contextSection,
            goalSection: goalSection,
            tasksSection: tasksSection,
            aiProfileSection: aiProfileSection,
            databaseSchema: cachedDatabaseSchema
        )

        // NO conversation_history — SDK handles this via resume

        if claudeMdEnabled, let claudeMd = claudeMdContent {
            prompt += "\n\n<claude_md>\n\(claudeMd)\n</claude_md>"
        }
        if projectClaudeMdEnabled, let projectClaudeMd = projectClaudeMdContent {
            prompt += "\n\n<project_claude_md>\n\(projectClaudeMd)\n</project_claude_md>"
        }

        let enabledSkillNames = getEnabledSkillNames()
        if !enabledSkillNames.isEmpty {
            let allSkills = discoveredSkills + projectDiscoveredSkills
            let skillDescriptions = allSkills
                .filter { enabledSkillNames.contains($0.name) && $0.name != "dev-mode" }
                .map { "- \($0.name): \($0.description)" }
                .joined(separator: "\n")
            if !skillDescriptions.isEmpty {
                prompt += "\n\n<available_skills>\n\(skillDescriptions)\n</available_skills>"
            }
        }

        // Append dev mode context if enabled (full skill content, not just description)
        if devModeEnabled, let devMode = devModeContext {
            let workspaceDir = aiChatWorkingDirectory.isEmpty ? "not set" : aiChatWorkingDirectory
            prompt += "\n\n<dev_mode>\nDev Mode is ENABLED. The user has opted in to app customization.\nWorkspace: \(workspaceDir)\n\n\(devMode)\n</dev_mode>"
        }

        log("ChatProvider: task chat prompt built — prompt_length: \(prompt.count) chars")
        return prompt
    }

    /// Builds system prompt using cached memories only (for simple messages)
    private func buildSystemPromptSimple() -> String {
        let userName = AuthService.shared.displayName.isEmpty ? "there" : AuthService.shared.givenName
        let memoriesSection = formatMemoriesSection()

        return ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: memoriesSection
        )
    }

    /// Build conversation history from messages (loaded from Firestore)
    /// This ensures cross-platform sync: messages from mobile appear in context
    private func buildConversationHistory() -> String {
        // Take recent messages, excluding the current user message (last one) and any empty streaming placeholders
        let historyMessages = messages.filter { msg in
            !msg.text.isEmpty && !msg.isStreaming
        }

        // Skip if no history
        guard !historyMessages.isEmpty else { return "" }

        // Limit to last 20 messages to avoid excessive prompt size
        let recent = historyMessages.suffix(20)

        return recent.map { msg in
            let role = msg.sender == .user ? "human" : "assistant"
            return "\(role): \(msg.text)"
        }.joined(separator: "\n")
    }

    /// Initialize chat: fetch sessions and load messages
    func initialize() async {
        if multiChatEnabled {
            // Multi-chat mode: load sessions, default to default chat
            await fetchSessions()
            // Start in default chat mode
            await switchToDefaultChat()
        } else {
            // Single chat mode: just load default chat messages (syncs with Flutter)
            isLoadingSessions = false
            await loadDefaultChatMessages()
        }
        await loadMemoriesIfNeeded()
        await loadGoalsIfNeeded()
        await loadTasksIfNeeded()
        await loadAIProfileIfNeeded()
        await loadSchemaIfNeeded()
        discoverClaudeConfig()

        // Set working directory for Claude Agent SDK if workspace is configured
        if workingDirectory == nil, !aiChatWorkingDirectory.isEmpty {
            workingDirectory = aiChatWorkingDirectory
        }
    }

    /// Reinitialize after settings change
    func reinitialize() async {
        sessions = []
        messages = []
        currentSession = nil
        isInDefaultChat = true
        await initialize()
    }

    /// Retry loading after a failure — clears error state and re-runs initialize
    func retryLoad() async {
        sessionsLoadError = nil
        await initialize()
    }

    // MARK: - CLAUDE.md & Skills Discovery

    /// Discover ~/.claude/CLAUDE.md, skills from ~/.claude/skills/, and project-level equivalents
    func discoverClaudeConfig() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let claudeDir = "\(home)/.claude"

        // Discover global CLAUDE.md
        let mdPath = "\(claudeDir)/CLAUDE.md"
        if FileManager.default.fileExists(atPath: mdPath),
           let content = try? String(contentsOfFile: mdPath, encoding: .utf8) {
            claudeMdContent = content
            claudeMdPath = mdPath
        } else {
            claudeMdContent = nil
            claudeMdPath = nil
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
        discoveredSkills = skills

        // Discover project-level config from workspace directory
        let workspace = aiChatWorkingDirectory
        if !workspace.isEmpty, FileManager.default.fileExists(atPath: workspace) {
            // Project CLAUDE.md at <workspace>/CLAUDE.md
            let projectMdPath = "\(workspace)/CLAUDE.md"
            if FileManager.default.fileExists(atPath: projectMdPath),
               let content = try? String(contentsOfFile: projectMdPath, encoding: .utf8) {
                projectClaudeMdContent = content
                projectClaudeMdPath = projectMdPath
            } else {
                projectClaudeMdContent = nil
                projectClaudeMdPath = nil
            }

            // Project skills at <workspace>/.claude/skills/
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
            projectDiscoveredSkills = projectSkills
        } else {
            projectClaudeMdContent = nil
            projectClaudeMdPath = nil
            projectDiscoveredSkills = []
        }

        // Load dev-mode skill content (full SKILL.md, not just description)
        let devModeSkillPath = "\(skillsDir)/dev-mode/SKILL.md"
        if FileManager.default.fileExists(atPath: devModeSkillPath),
           let content = try? String(contentsOfFile: devModeSkillPath, encoding: .utf8) {
            // Strip YAML frontmatter, keep the markdown body
            var body = content
            if body.hasPrefix("---") {
                let lines = body.components(separatedBy: "\n")
                if let endIdx = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("---") }) {
                    body = lines[(endIdx + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            devModeContext = body
        } else {
            // Also check project skills directory
            let projectDevModePath = "\(workspace)/.claude/skills/dev-mode/SKILL.md"
            if !workspace.isEmpty, FileManager.default.fileExists(atPath: projectDevModePath),
               let content = try? String(contentsOfFile: projectDevModePath, encoding: .utf8) {
                var body = content
                if body.hasPrefix("---") {
                    let lines = body.components(separatedBy: "\n")
                    if let endIdx = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("---") }) {
                        body = lines[(endIdx + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                }
                devModeContext = body
            } else {
                devModeContext = nil
            }
        }

        log("ChatProvider: discovered global CLAUDE.md=\(claudeMdContent != nil), global skills=\(skills.count), project CLAUDE.md=\(projectClaudeMdContent != nil), project skills=\(projectDiscoveredSkills.count), dev_mode_skill=\(devModeContext != nil)")
    }

    /// Extract description from YAML frontmatter in SKILL.md
    private func extractSkillDescription(from content: String) -> String {
        guard content.hasPrefix("---") else {
            // No frontmatter — use first non-empty line as description
            let lines = content.components(separatedBy: "\n")
            return lines.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })?.trimmingCharacters(in: .whitespaces) ?? ""
        }
        let lines = content.components(separatedBy: "\n")
        for line in lines.dropFirst() {
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("---") { break }
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("description:") {
                var value = String(line.trimmingCharacters(in: .whitespaces).dropFirst("description:".count))
                value = value.trimmingCharacters(in: .whitespaces)
                // Remove surrounding quotes if present
                if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                   (value.hasPrefix("'") && value.hasSuffix("'")) {
                    value = String(value.dropFirst().dropLast())
                }
                return value
            }
        }
        return ""
    }

    /// Get the set of enabled skill names (all skills minus explicitly disabled ones)
    func getEnabledSkillNames() -> Set<String> {
        let allSkillNames = Set(discoveredSkills.map { $0.name } + projectDiscoveredSkills.map { $0.name })
        let disabled = getDisabledSkillNames()
        return allSkillNames.subtracting(disabled)
    }

    /// Get the set of explicitly disabled skill names from UserDefaults
    func getDisabledSkillNames() -> Set<String> {
        guard let data = disabledSkillsJSON.data(using: .utf8),
              let names = try? JSONDecoder().decode([String].self, from: data) else {
            return [] // Default: nothing disabled = all enabled
        }
        return Set(names)
    }

    /// Save the set of disabled skill names to UserDefaults
    func setDisabledSkillNames(_ names: Set<String>) {
        if let data = try? JSONEncoder().encode(Array(names)),
           let json = String(data: data, encoding: .utf8) {
            disabledSkillsJSON = json
        }
    }

    /// Switch to the default chat (messages without session_id, syncs with Flutter app)
    func switchToDefaultChat() async {
        currentSession = nil
        isInDefaultChat = true
        await loadDefaultChatMessages()
        log("Switched to default chat")
    }

    /// Load messages for the default chat (no session filter - compatible with Flutter)
    /// Retries up to 3 times on failure.
    private func loadDefaultChatMessages() async {
        isLoading = true
        errorMessage = nil
        hasMoreMessages = false

        let maxAttempts = 3
        let delays: [UInt64] = [1_000_000_000, 2_000_000_000] // 1s, 2s
        var lastError: Error?

        for attempt in 1...maxAttempts {
            do {
                let persistedMessages = try await APIClient.shared.getMessages(
                    appId: selectedAppId,
                    limit: messagesPageSize
                )
                messages = persistedMessages.map(ChatMessage.init(from:))
                    .sorted(by: { $0.createdAt < $1.createdAt })
                hasMoreMessages = persistedMessages.count == messagesPageSize
                sessionsLoadError = nil
                log("ChatProvider loaded \(messages.count) default chat messages, hasMore: \(hasMoreMessages)")
                isLoading = false
                return
            } catch {
                lastError = error
                logError("Failed to load default chat messages (attempt \(attempt)/\(maxAttempts))", error: error)
                if attempt < maxAttempts {
                    try? await Task.sleep(nanoseconds: delays[attempt - 1])
                }
            }
        }

        messages = []
        sessionsLoadError = lastError?.localizedDescription ?? "Unknown error"
        isLoading = false
    }

    // MARK: - Cross-Platform Message Polling

    /// Poll for new messages from other platforms (e.g. mobile).
    /// Merges new messages into the existing array without disrupting the UI.
    private func pollForNewMessages() async {
        // Skip if we're in the middle of sending, loading, or streaming
        guard !isSending, !isLoading, !isLoadingSessions else { return }
        // Skip if messages haven't been loaded yet (initial load not done)
        guard !messages.isEmpty || sessionsLoadError != nil else { return }
        // Skip if there's an active streaming message
        guard !messages.contains(where: { $0.isStreaming }) else { return }

        do {
            let persistedMessages: [ChatMessageDB]

            if let session = currentSession {
                // Multi-chat: fetch for current session
                persistedMessages = try await APIClient.shared.getMessages(
                    sessionId: session.id,
                    limit: messagesPageSize
                )
            } else {
                // Default chat
                persistedMessages = try await APIClient.shared.getMessages(
                    appId: selectedAppId,
                    limit: messagesPageSize
                )
            }

            let existingIds = Set(messages.map(\.id))
            let newMessages = persistedMessages
                .filter { !existingIds.contains($0.id) }
                .map(ChatMessage.init(from:))

            if !newMessages.isEmpty {
                log("ChatProvider poll: found \(newMessages.count) new message(s) from other platforms")
                messages.append(contentsOf: newMessages)
                messages.sort(by: { $0.createdAt < $1.createdAt })
            }
        } catch {
            // Silent failure — polling errors shouldn't disrupt the user
            logError("ChatProvider poll failed", error: error)
        }
    }

    // MARK: - Stop / Follow-Up

    /// Text of a follow-up queued while the current query is being interrupted.
    /// Checked at the end of `sendMessage` — if set, a new query is chained automatically.
    private var pendingFollowUpText: String?

    /// Stop the running agent, keeping partial response
    func stopAgent() {
        guard isSending else { return }
        isStopping = true
        Task {
            if isACPMode {
                await acpBridge.interrupt()
            } else {
                await claudeBridge.interrupt()
            }
        }
        // Result flows back normally through the bridge with partial text
    }

    /// Send a follow-up message while the agent is still running.
    /// Interrupts the current query and chains a new one with full context.
    func sendFollowUp(_ text: String) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty, isSending else { return }

        // Add as user message in UI
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            text: trimmedText,
            sender: .user
        )
        messages.append(userMessage)

        // Persist to backend and sync server ID back to prevent poll duplicates
        let capturedSessionId = isInDefaultChat ? nil : currentSessionId
        let capturedAppId = overrideAppId ?? selectedAppId
        let localId = userMessage.id
        Task { [weak self] in
            do {
                let response = try await APIClient.shared.saveMessage(
                    text: trimmedText,
                    sender: "human",
                    appId: capturedAppId,
                    sessionId: capturedSessionId
                )
                await MainActor.run {
                    if let index = self?.messages.firstIndex(where: { $0.id == localId }) {
                        self?.messages[index].id = response.id
                        self?.messages[index].isSynced = true
                    }
                }
                log("Saved follow-up message to backend: \(response.id)")
            } catch {
                logError("Failed to persist follow-up message", error: error)
            }
        }

        // Queue the follow-up and interrupt the current query.
        // When sendMessage finishes (due to the interrupt), it checks
        // pendingFollowUpText and chains a new full query automatically.
        pendingFollowUpText = trimmedText
        if isACPMode {
            await acpBridge.interrupt()
        } else {
            await claudeBridge.interrupt()
        }
        log("ChatProvider: follow-up queued, interrupt sent")
    }

    // MARK: - Send Message

    /// Send a message and get AI response via Claude Agent SDK bridge
    /// Persists both user and AI messages to backend
    /// - Parameters:
    ///   - text: The message text
    ///   - model: Optional model override for this query (e.g. "claude-sonnet-4-6" for floating bar)
    func sendMessage(_ text: String, model: String? = nil, isFollowUp: Bool = false) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Guard against concurrent sendMessage calls.
        // The bridge uses a single message continuation, so concurrent queries
        // would cause responses to be consumed by the wrong caller.
        guard !isSending else {
            log("ChatProvider: sendMessage called while already sending, ignoring")
            return
        }

        // Ensure bridge is running
        guard await ensureBridgeStarted() else {
            errorMessage = "AI not available"
            return
        }

        // Determine session ID based on mode
        // In default chat mode (isInDefaultChat=true): no session ID (compatible with Flutter)
        // In session mode: require session ID
        var sessionId: String? = nil
        if !isInDefaultChat {
            // Session mode - require a session
            if currentSession == nil {
                _ = await createNewSession()
            }
            guard let sid = currentSessionId else {
                errorMessage = "Failed to create chat session"
                return
            }
            sessionId = sid
        }

        isSending = true
        errorMessage = nil

        // Save user message to backend and add to UI
        // (skip for follow-ups — sendFollowUp already did both)
        let userMessageId = UUID().uuidString
        let isFirstMessage = messages.isEmpty
        let capturedSessionId = sessionId
        let capturedAppId = overrideAppId ?? selectedAppId
        if !isFollowUp {
            Task { [weak self] in
                do {
                    let response = try await APIClient.shared.saveMessage(
                        text: trimmedText,
                        sender: "human",
                        appId: capturedAppId,
                        sessionId: capturedSessionId
                    )
                    // Sync local message ID with server ID
                    await MainActor.run {
                        if let index = self?.messages.firstIndex(where: { $0.id == userMessageId }) {
                            self?.messages[index].id = response.id
                            self?.messages[index].isSynced = true
                        }
                    }
                    log("Saved user message to backend: \(response.id)")
                } catch {
                    logError("Failed to persist user message", error: error)
                    // Non-critical - continue with chat
                }
            }

            let userMessage = ChatMessage(
                id: userMessageId,
                text: trimmedText,
                sender: .user
            )
            messages.append(userMessage)
        }

        // Create placeholder AI message
        let aiMessageId = UUID().uuidString
        let aiMessage = ChatMessage(
            id: aiMessageId,
            text: "",
            sender: .ai,
            isStreaming: true
        )
        messages.append(aiMessage)

        // Analytics: track timing and tool usage
        let queryStartTime = Date()
        var toolNames: [String] = []
        var toolStartTimes: [String: Date] = [:]

        do {
            // Build system prompt with locally cached memories (no backend Gemini call)
            let systemPrompt = buildSystemPrompt(contextString: formatMemoriesSection())

            // Query the active bridge with streaming
            // Each query is standalone — conversation history is in the system prompt
            // This ensures cross-platform sync (mobile messages appear in context)

            // Shared callbacks for both bridges
            let textDeltaHandler: ClaudeAgentBridge.TextDeltaHandler = { [weak self] delta in
                Task { @MainActor [weak self] in
                    self?.appendToMessage(id: aiMessageId, text: delta)
                }
            }
            let toolCallHandler: ClaudeAgentBridge.ToolCallHandler = { callId, name, input in
                let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
                let result = await ChatToolExecutor.execute(toolCall)
                log("OMI tool \(name) executed for callId=\(callId)")
                return result
            }
            let toolActivityHandler: ClaudeAgentBridge.ToolActivityHandler = { [weak self] name, status, toolUseId, input in
                Task { @MainActor [weak self] in
                    self?.addToolActivity(
                        messageId: aiMessageId,
                        toolName: name,
                        status: status == "started" ? .running : .completed,
                        toolUseId: toolUseId,
                        input: input
                    )
                    if status == "started" {
                        toolNames.append(name)
                        toolStartTimes[name] = Date()
                        if (name.contains("browser") || name.contains("playwright")) {
                            let token = UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
                            if token.isEmpty {
                                log("ChatProvider: Browser tool \(name) called without extension token — aborting query and prompting setup")
                                self?.needsBrowserExtensionSetup = true
                                self?.stopAgent()
                            }
                        }
                    } else if status == "completed", let startTime = toolStartTimes.removeValue(forKey: name) {
                        let durationMs = Int(Date().timeIntervalSince(startTime) * 1000)
                        AnalyticsManager.shared.chatToolCallCompleted(toolName: name, durationMs: durationMs)
                    }
                }
            }
            let thinkingDeltaHandler: ClaudeAgentBridge.ThinkingDeltaHandler = { [weak self] text in
                Task { @MainActor [weak self] in
                    self?.appendThinking(messageId: aiMessageId, text: text)
                }
            }
            let toolResultDisplayHandler: ClaudeAgentBridge.ToolResultDisplayHandler = { [weak self] toolUseId, name, output in
                Task { @MainActor [weak self] in
                    self?.addToolResult(messageId: aiMessageId, toolUseId: toolUseId, name: name, output: output)
                }
            }

            let queryResult: ClaudeAgentBridge.QueryResult
            if isACPMode {
                let acpResult = try await acpBridge.query(
                    prompt: trimmedText,
                    systemPrompt: systemPrompt,
                    cwd: workingDirectory,
                    mode: chatMode.rawValue,
                    model: model ?? modelOverride,
                    onTextDelta: textDeltaHandler,
                    onToolCall: toolCallHandler,
                    onToolActivity: toolActivityHandler,
                    onThinkingDelta: thinkingDeltaHandler,
                    onToolResultDisplay: toolResultDisplayHandler,
                    onAuthRequired: { [weak self] methods in
                        Task { @MainActor [weak self] in
                            self?.claudeAuthMethods = methods
                            self?.isClaudeAuthRequired = true
                        }
                    },
                    onAuthSuccess: { [weak self] in
                        Task { @MainActor [weak self] in
                            self?.isClaudeAuthRequired = false
                        }
                    }
                )
                queryResult = ClaudeAgentBridge.QueryResult(text: acpResult.text, costUsd: acpResult.costUsd, sessionId: "")
            } else {
                queryResult = try await claudeBridge.query(
                    prompt: trimmedText,
                    systemPrompt: systemPrompt,
                    cwd: workingDirectory,
                    mode: chatMode.rawValue,
                    model: model ?? modelOverride,
                    onTextDelta: textDeltaHandler,
                    onToolCall: toolCallHandler,
                    onToolActivity: toolActivityHandler,
                    onThinkingDelta: thinkingDeltaHandler,
                    onToolResultDisplay: toolResultDisplayHandler
                )
            }

            // Flush any remaining buffered streaming text before finalizing
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            // Determine the final text to display and save
            let messageText: String
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                // Message still in memory — update it in-place
                messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                messages[index].text = messageText
                messages[index].isStreaming = false
                completeRemainingToolCalls(messageId: aiMessageId)
            } else {
                // Message no longer in memory (user switched away from this session).
                messageText = queryResult.text
                log("Chat response arrived after session switch")
            }

            // Always save AI response to backend with the captured session ID.
            // Even if the user switched to a different task, this response belongs
            // to the original session (concurrent queries are prevented by the
            // isSending guard, so the response is always correct for its session).
            let textToSave = queryResult.text.isEmpty ? messageText : queryResult.text
            if !textToSave.isEmpty {
                do {
                    let toolMetadata = serializeToolCallMetadata(messageId: aiMessageId)
                    let response = try await APIClient.shared.saveMessage(
                        text: textToSave,
                        sender: "ai",
                        appId: capturedAppId,
                        sessionId: capturedSessionId,
                        metadata: toolMetadata
                    )
                    if let syncIndex = messages.firstIndex(where: { $0.id == aiMessageId }) {
                        messages[syncIndex].id = response.id
                        messages[syncIndex].isSynced = true
                    }
                    log("Saved and synced AI response: \(response.id) (session=\(capturedSessionId ?? "nil"), tool_calls=\(toolMetadata != nil ? "yes" : "none"))")
                } catch {
                    logError("Failed to persist AI response", error: error)
                }
            }

            // Auto-generate title after first exchange (user message + AI response)
            if isFirstMessage, let sid = capturedSessionId {
                await generateSessionTitle(sessionId: sid)
            }

            log("Chat response complete")

            // Analytics: track query completion
            let durationMs = Int(Date().timeIntervalSince(queryStartTime) * 1000)
            let responseLength = messages.first(where: { $0.id == aiMessageId })?.text.count ?? 0
            AnalyticsManager.shared.chatAgentQueryCompleted(
                durationMs: durationMs,
                toolCallCount: toolNames.count,
                toolNames: toolNames,
                costUsd: queryResult.costUsd,
                messageLength: responseLength
            )

            // Fire-and-forget: check if user's message mentions goal progress
            let chatText = trimmedText
            Task.detached(priority: .background) {
                await GoalsAIService.shared.extractProgressFromAllGoals(text: chatText)
            }
        } catch {
            // On timeout, cancel the stuck ACP session so it's not left dangling
            if let bridgeError = error as? BridgeError, case .timeout = bridgeError, isACPMode {
                log("ChatProvider: ACP query timed out, sending interrupt to cancel stuck session")
                await acpBridge.interrupt()
            }

            // Flush any remaining buffered streaming text before handling the error
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            // Only remove the AI message if it's still empty (no streamed text yet).
            // If text was already streamed and visible, keep it and just stop streaming.
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                if messages[index].text.isEmpty && messages[index].contentBlocks.isEmpty {
                    messages.remove(at: index)
                } else {
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(messageId: aiMessageId)
                    log("Bridge error after partial response — keeping \(messages[index].text.count) chars of streamed text")
                    // Still try to persist the partial response
                    let partialText = messages[index].text
                    let partialToolMetadata = self.serializeToolCallMetadata(messageId: aiMessageId)
                    Task { [weak self] in
                        do {
                            let response = try await APIClient.shared.saveMessage(
                                text: partialText,
                                sender: "ai",
                                appId: capturedAppId,
                                sessionId: capturedSessionId,
                                metadata: partialToolMetadata
                            )
                            await MainActor.run {
                                if let syncIndex = self?.messages.firstIndex(where: { $0.id == aiMessageId }) {
                                    self?.messages[syncIndex].id = response.id
                                    self?.messages[syncIndex].isSynced = true
                                }
                            }
                            log("Saved partial AI response to backend: \(response.id)")
                        } catch {
                            logError("Failed to persist partial AI response", error: error)
                        }
                    }
                }
            }

            logError("Failed to get AI response", error: error)
            AnalyticsManager.shared.chatAgentError(error: error.localizedDescription)

            // Show error to user (unless they intentionally stopped)
            if let bridgeError = error as? BridgeError, case .stopped = bridgeError {
                // User stopped — no error to show
            } else {
                errorMessage = error.localizedDescription
            }
        }

        isSending = false
        isStopping = false

        // If a follow-up was queued while we were running, chain it as a new full query
        if let followUp = pendingFollowUpText {
            pendingFollowUpText = nil
            log("ChatProvider: chaining follow-up query")
            await sendMessage(followUp, isFollowUp: true)
        }
    }

    /// Generate a title for the session using LLM
    private func generateSessionTitle(sessionId: String) async {
        // Need at least 2 messages (user + AI) for meaningful title
        guard messages.count >= 2 else {
            log("Not enough messages for title generation")
            return
        }

        // Convert messages to the format expected by the API
        let messageTuples: [(text: String, sender: String)] = messages.map { msg in
            (text: msg.text, sender: msg.sender == .user ? "human" : "ai")
        }

        do {
            let response = try await APIClient.shared.generateSessionTitle(
                sessionId: sessionId,
                messages: messageTuples
            )

            // Update session in list
            if let index = sessions.firstIndex(where: { $0.id == sessionId }) {
                sessions[index].title = response.title
            }

            // Update current session
            if currentSession?.id == sessionId {
                currentSession?.title = response.title
            }

            log("Generated session title: \(response.title)")
            AnalyticsManager.shared.sessionTitleGenerated()
        } catch {
            logError("Failed to generate session title", error: error)
            // Non-fatal - session continues with default title
        }
    }

    /// Update message text (replaces entire text)
    private func updateMessage(id: String, text: String) {
        if let index = messages.firstIndex(where: { $0.id == id }) {
            messages[index].text = text
        }
    }

    /// Append text to a streaming message via a buffer that flushes at ~100ms intervals.
    /// This reduces SwiftUI re-renders from once-per-token to ~10 times/second.
    private func appendToMessage(id: String, text: String) {
        streamingBufferMessageId = id
        streamingTextBuffer += text

        // Schedule a flush if one isn't already pending
        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    /// Flush accumulated text and thinking deltas to the published messages array.
    private func flushStreamingBuffer() {
        streamingFlushWorkItem = nil

        guard let id = streamingBufferMessageId,
              let index = messages.firstIndex(where: { $0.id == id }) else {
            streamingTextBuffer = ""
            streamingThinkingBuffer = ""
            return
        }

        // Flush text buffer
        if !streamingTextBuffer.isEmpty {
            let buffered = streamingTextBuffer
            streamingTextBuffer = ""

            messages[index].text += buffered

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .text(let blockId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                messages[index].contentBlocks[lastBlockIndex] = .text(id: blockId, text: existing + buffered)
            } else {
                messages[index].contentBlocks.append(.text(id: UUID().uuidString, text: buffered))
            }
        }

        // Flush thinking buffer
        if !streamingThinkingBuffer.isEmpty {
            let buffered = streamingThinkingBuffer
            streamingThinkingBuffer = ""

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .thinking(let thinkId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                messages[index].contentBlocks[lastBlockIndex] = .thinking(id: thinkId, text: existing + buffered)
            } else {
                messages[index].contentBlocks.append(.thinking(id: UUID().uuidString, text: buffered))
            }
        }
    }

    /// Add a tool call indicator to a streaming message
    private func addToolActivity(messageId: String, toolName: String, status: ToolCallStatus, toolUseId: String? = nil, input: [String: Any]? = nil) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }

        let toolInput = input.flatMap { ChatContentBlock.toolInputSummary(for: toolName, input: $0) }

        if status == .running {
            // If we have a toolUseId and input, try to update an existing running block (input arrived after start)
            if let toolUseId = toolUseId, toolInput != nil {
                for i in stride(from: messages[index].contentBlocks.count - 1, through: 0, by: -1) {
                    if case .toolCall(let id, let name, let st, let existingTuid, _, let output) = messages[index].contentBlocks[i],
                       (existingTuid == toolUseId || (existingTuid == nil && name == toolName && st == .running)) {
                        messages[index].contentBlocks[i] = .toolCall(
                            id: id, name: name, status: st,
                            toolUseId: toolUseId, input: toolInput, output: output
                        )
                        return
                    }
                }
            }
            // No existing block to update — create a new one
            messages[index].contentBlocks.append(
                .toolCall(id: UUID().uuidString, name: toolName, status: .running,
                          toolUseId: toolUseId, input: toolInput)
            )
        } else {
            // Mark as completed — find by toolUseId first, fall back to name
            for i in stride(from: messages[index].contentBlocks.count - 1, through: 0, by: -1) {
                if case .toolCall(let id, let name, .running, let existingTuid, let existingInput, let output) = messages[index].contentBlocks[i] {
                    let matches = (toolUseId != nil && existingTuid == toolUseId) || (toolUseId == nil && name == toolName)
                    if matches {
                        messages[index].contentBlocks[i] = .toolCall(
                            id: id, name: name, status: .completed,
                            toolUseId: toolUseId ?? existingTuid,
                            input: toolInput ?? existingInput,
                            output: output
                        )
                        break
                    }
                }
            }
        }
    }

    /// Add tool result output to an existing tool call block
    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }

        for i in messages[index].contentBlocks.indices {
            if case .toolCall(let id, let blockName, let status, let tuid, let input, _) = messages[index].contentBlocks[i],
               (tuid == toolUseId || (tuid == nil && blockName == name)) {
                messages[index].contentBlocks[i] = .toolCall(
                    id: id, name: blockName, status: status,
                    toolUseId: toolUseId, input: input, output: output
                )
                return
            }
        }
    }

    /// Append thinking text to the streaming message via the shared buffer.
    private func appendThinking(messageId: String, text: String) {
        streamingBufferMessageId = messageId
        streamingThinkingBuffer += text

        // Schedule a flush if one isn't already pending
        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    /// Mark any remaining `.running` tool call blocks as `.completed` in a message.
    /// Called when a query finishes (success or interrupt) so spinners don't spin forever.
    private func completeRemainingToolCalls(messageId: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        for i in messages[index].contentBlocks.indices {
            if case .toolCall(let id, let name, .running, let toolUseId, let input, let output) = messages[index].contentBlocks[i] {
                messages[index].contentBlocks[i] = .toolCall(
                    id: id, name: name, status: .completed,
                    toolUseId: toolUseId, input: input, output: output
                )
            }
        }
    }

    /// Serialize tool calls from a message's contentBlocks into a JSON metadata string.
    /// Returns nil if there are no tool calls.
    private func serializeToolCallMetadata(messageId: String) -> String? {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }

        var toolCalls: [[String: Any]] = []
        for block in messages[index].contentBlocks {
            if case .toolCall(_, let name, _, let toolUseId, let input, let output) = block {
                var call: [String: Any] = ["name": name]
                if let toolUseId = toolUseId { call["tool_use_id"] = toolUseId }
                if let input = input {
                    call["input_summary"] = input.summary
                    if let details = input.details { call["input"] = details }
                }
                if let output = output {
                    // Truncate large outputs to keep metadata reasonable
                    call["output"] = output.count > 500 ? String(output.prefix(500)) + "… (truncated)" : output
                }
                toolCalls.append(call)
            }
        }

        guard !toolCalls.isEmpty else { return nil }

        let metadata: [String: Any] = ["tool_calls": toolCalls]
        guard let data = try? JSONSerialization.data(withJSONObject: metadata),
              let json = String(data: data, encoding: .utf8) else { return nil }
        return json
    }

    // MARK: - Message Rating

    /// Rate a message (thumbs up/down)
    /// - Parameters:
    ///   - messageId: The message ID to rate
    ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
    func rateMessage(_ messageId: String, rating: Int?) async {
        // Update local state immediately for responsive UI
        if let index = messages.firstIndex(where: { $0.id == messageId }) {
            messages[index].rating = rating
        }

        // Persist to backend
        do {
            try await APIClient.shared.rateMessage(messageId: messageId, rating: rating)
            log("Rated message \(messageId) with rating: \(String(describing: rating))")

            // Track analytics
            if let rating = rating {
                AnalyticsManager.shared.messageRated(rating: rating)
            }
        } catch {
            logError("Failed to rate message", error: error)
            // Revert local state on failure
            if let index = messages.firstIndex(where: { $0.id == messageId }) {
                messages[index].rating = nil
            }
        }
    }

    // MARK: - Clear Chat

    /// Clear current session messages (delete and create new)
    func clearChat() async {
        isClearing = true
        defer { isClearing = false }

        if isInDefaultChat {
            // Default chat mode: clear UI immediately, delete in background
            messages = []
            log("Cleared default chat messages")
            Task {
                do {
                    _ = try await APIClient.shared.deleteMessages(appId: selectedAppId)
                } catch {
                    logError("Failed to clear default chat messages", error: error)
                }
            }
        } else {
            // Session mode: clear UI immediately, delete old session in background, create new
            let sessionToDelete = currentSession

            // Immediately clear UI state
            if let session = sessionToDelete {
                sessions.removeAll { $0.id == session.id }
            }
            currentSession = nil
            messages = []

            // Delete old session in background (don't await — backend is slow)
            if let session = sessionToDelete {
                Task {
                    do {
                        try await APIClient.shared.deleteChatSession(sessionId: session.id)
                        log("Background deleted chat session: \(session.id)")
                    } catch {
                        logError("Failed to background delete chat session", error: error)
                    }
                }
            }

            // Create a fresh session immediately
            _ = await createNewSession()
        }

        log("Chat cleared")
        AnalyticsManager.shared.chatCleared()
    }

    // MARK: - App Selection

    /// Select a chat app and load its sessions
    func selectApp(_ appId: String?) async {
        guard selectedAppId != appId else { return }
        selectedAppId = appId
        currentSession = nil
        messages = []
        sessions = []
        errorMessage = nil
        isInDefaultChat = true

        if multiChatEnabled {
            // Multi-chat mode: load sessions, then switch to default chat
            await fetchSessions()
            await switchToDefaultChat()
        } else {
            // Single chat mode: just load default chat messages
            await loadDefaultChatMessages()
        }
    }

    // MARK: - Session Grouping Helpers

    /// Group sessions by date for sidebar display (uses filteredSessions for search)
    var groupedSessions: [(String, [ChatSession])] {
        let calendar = Calendar.current
        let now = Date()

        var today: [ChatSession] = []
        var yesterday: [ChatSession] = []
        var thisWeek: [ChatSession] = []
        var older: [ChatSession] = []

        for session in filteredSessions {
            if calendar.isDateInToday(session.updatedAt) {
                today.append(session)
            } else if calendar.isDateInYesterday(session.updatedAt) {
                yesterday.append(session)
            } else if let weekAgo = calendar.date(byAdding: .day, value: -7, to: now),
                      session.updatedAt > weekAgo {
                thisWeek.append(session)
            } else {
                older.append(session)
            }
        }

        var groups: [(String, [ChatSession])] = []
        if !today.isEmpty { groups.append(("Today", today)) }
        if !yesterday.isEmpty { groups.append(("Yesterday", yesterday)) }
        if !thisWeek.isEmpty { groups.append(("This Week", thisWeek)) }
        if !older.isEmpty { groups.append(("Older", older)) }

        return groups
    }
}
