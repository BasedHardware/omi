import Foundation

/// Focus monitoring assistant that detects when users are distracted
actor FocusAssistant: ProactiveAssistant {
    // MARK: - ProactiveAssistant Protocol

    nonisolated let identifier = "focus"
    nonisolated let displayName = "Focus Monitor"

    var isEnabled: Bool {
        get async {
            await MainActor.run {
                FocusAssistantSettings.shared.isEnabled
            }
        }
    }

    // MARK: - Properties

    private let geminiClient: GeminiClient
    private let onAlert: (String) -> Void
    private let onStatusChange: ((FocusStatus) -> Void)?
    private let onRefocus: (() -> Void)?
    private let onDistraction: (() -> Void)?

    private var isRunning = false
    private let frameStream: AsyncStream<CapturedFrame>
    private let frameContinuation: AsyncStream<CapturedFrame>.Continuation
    private var analysisHistory: [ScreenAnalysis] = []
    private let maxHistorySize = 10
    private var lastStatus: FocusStatus?
    private var lastProcessedFrameNum = 0
    private var processingTask: Task<Void, Never>?
    private var pendingTasks: Set<Task<Void, Never>> = []
    private var currentApp: String?

    // MARK: - Smart Analysis Filtering
    // Skip analysis when user is focused on the same context (app + window title)
    // Also skip during cooldown period after distraction (unless context changes)
    private var lastAnalyzedApp: String?
    private var lastAnalyzedWindowTitle: String?
    private var analysisCooldownEndTime: Date?

    // MARK: - Notification Deduplication
    // Track the last state we notified about to prevent duplicate notifications
    // from parallel frame analysis (only notify on state change)
    private var lastNotifiedState: FocusStatus?

    // MARK: - Error Backoff
    // Prevents infinite retry loops when Gemini consistently rejects content (e.g. safety filter)
    private var consecutiveErrorCount = 0
    private var errorBackoffEndTime: Date?

    /// Get the current system prompt from settings (accessed on MainActor for thread safety)
    private var systemPrompt: String {
        get async {
            await MainActor.run {
                FocusAssistantSettings.shared.analysisPrompt
            }
        }
    }

    // MARK: - Initialization

    init(
        apiKey: String? = nil,
        onAlert: @escaping (String) -> Void = { _ in },
        onStatusChange: ((FocusStatus) -> Void)? = nil,
        onRefocus: (() -> Void)? = nil,
        onDistraction: (() -> Void)? = nil
    ) throws {
        self.geminiClient = try GeminiClient(apiKey: apiKey)
        self.onAlert = onAlert
        self.onStatusChange = onStatusChange
        self.onRefocus = onRefocus
        self.onDistraction = onDistraction

        let (stream, continuation) = AsyncStream.makeStream(of: CapturedFrame.self)
        self.frameStream = stream
        self.frameContinuation = continuation

        // Start processing loop in a task
        Task {
            await self.startProcessing()
        }
    }

    // MARK: - Processing

    private func startProcessing() {
        isRunning = true
        processingTask = Task {
            await processFrameLoop()
        }
    }

    private func processFrameLoop() async {
        log("Focus assistant started (parallel mode)")

        for await frame in frameStream {
            guard isRunning else { break }
            // Fire off analysis in background (don't wait) - like Python version
            let task = Task {
                await self.processFrame(frame)
            }
            pendingTasks.insert(task)
        }

        // Wait for pending tasks on shutdown
        for task in pendingTasks {
            _ = await task.result
        }

        log("Focus assistant stopped")
    }

    // MARK: - ProactiveAssistant Protocol Methods

    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        // Focus assistant analyzes every frame
        return true
    }

    func analyze(frame: CapturedFrame) async -> AssistantResult? {
        // Skip apps excluded from focus analysis
        let excluded = await MainActor.run { FocusAssistantSettings.shared.isAppExcluded(frame.appName) }
        if excluded {
            log("Focus: Skipping excluded app '\(frame.appName)'")
            return nil
        }

        // Smart filtering: Skip analysis if user is focused on the same context
        if shouldSkipAnalysis(for: frame) {
            return nil
        }

        // Update last analyzed context IMMEDIATELY when queuing (not after API response)
        // This prevents multiple frames from being queued for the same context change
        lastAnalyzedApp = frame.appName
        lastAnalyzedWindowTitle = frame.windowTitle

        // Submit frame to stream for processing
        frameContinuation.yield(frame)
        log("Focus: Analyzing frame \(frame.frameNumber): App=\(frame.appName), Window=\(frame.windowTitle ?? "unknown")")

        // Return nil since we process asynchronously
        return nil
    }

    /// Determines if we should skip analysis for this frame
    /// Returns true if:
    /// - User is focused on the same app AND same window title
    /// - OR we're in cooldown period after distraction (unless context changed)
    /// - OR we're in error backoff period
    private func shouldSkipAnalysis(for frame: CapturedFrame) -> Bool {
        // Check error backoff FIRST (before the lastStatus guard)
        // This prevents infinite retry loops when lastStatus is nil due to repeated errors
        if let backoffEnd = errorBackoffEndTime {
            if Date() < backoffEnd {
                return true
            } else {
                // Backoff expired, allow retry
                errorBackoffEndTime = nil
                log("Focus: Error backoff expired, allowing retry")
            }
        }

        // Always analyze if we don't have a status yet
        guard lastStatus != nil else {
            return false
        }

        // Check if context changed (app or window title different from last analysis)
        // Compare normalized titles so spinner/timer updates don't trigger re-analysis
        let contextChanged = ContextDetection.didContextChange(
            fromApp: lastAnalyzedApp,
            fromWindowTitle: lastAnalyzedWindowTitle,
            toApp: frame.appName,
            toWindowTitle: frame.windowTitle
        )

        // Check 1: Context switch - ALWAYS analyze (bypass cooldown)
        if contextChanged {
            // Clear cooldown on context switch since user changed context
            if analysisCooldownEndTime != nil {
                log("Focus: Context switch detected, clearing cooldown - will analyze")
                analysisCooldownEndTime = nil
                // Clear cooldown in UI
                Task { @MainActor in
                    FocusStorage.shared.updateCooldownEndTime(nil)
                }
            } else {
                log("Focus: Context changed (app: \(lastAnalyzedApp ?? "nil") → \(frame.appName), window: \(lastAnalyzedWindowTitle ?? "nil") → \(frame.windowTitle ?? "nil")) - will analyze")
            }
            return false
        }

        // Check 2: Are we in cooldown period after distraction?
        if let cooldownEnd = analysisCooldownEndTime {
            if Date() < cooldownEnd {
                // Still in cooldown and no context switch - skip analysis
                return true
            } else {
                // Cooldown expired, clear it
                analysisCooldownEndTime = nil
                log("Focus: Cooldown ended, resuming analysis")
                // Clear cooldown in UI
                Task { @MainActor in
                    FocusStorage.shared.updateCooldownEndTime(nil)
                }
            }
        }

        // Check 3: User is focused on the same context - skip analysis
        if lastStatus == .focused {
            // User is focused on the same context - no need to re-analyze
            return true
        }

        // Default: analyze (status is distracted or unknown edge case)
        return false
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        // Results are handled internally in processFrame
    }

    func onAppSwitch(newApp: String) async {
        if newApp != currentApp {
            if let currentApp = currentApp {
                log("Focus: APP SWITCH: \(currentApp) -> \(newApp)")
            } else {
                log("Focus: Active app: \(newApp)")
            }
            currentApp = newApp
        }
    }

    var needsFrameDuringDelay: Bool {
        lastNotifiedState == .distracted
    }

    func clearPendingWork() async {
        // Cancel pending analysis tasks since those frames are now stale
        let count = pendingTasks.count
        for task in pendingTasks {
            task.cancel()
        }
        pendingTasks.removeAll()
        if count > 0 {
            log("Focus: Cancelled \(count) pending analysis tasks")
        }
    }

    func stop() async {
        isRunning = false
        frameContinuation.finish()
        processingTask?.cancel()
        // Cancel all pending analysis tasks
        for task in pendingTasks {
            task.cancel()
        }
        pendingTasks.removeAll()

        // Reset tracking state
        lastAnalyzedApp = nil
        lastAnalyzedWindowTitle = nil
        lastStatus = nil
        lastNotifiedState = nil
        analysisCooldownEndTime = nil
        consecutiveErrorCount = 0
        errorBackoffEndTime = nil

        // Clear cooldown in UI
        await MainActor.run {
            FocusStorage.shared.updateCooldownEndTime(nil)
        }
    }

    // MARK: - Legacy API (for backward compatibility)

    nonisolated func submitFrame(jpegData: Data, appName: String) {
        Task {
            let frame = CapturedFrame(
                jpegData: jpegData,
                appName: appName,
                frameNumber: await getNextFrameNumber()
            )
            _ = await analyze(frame: frame)
        }
    }

    private var frameCounter = 0

    private func getNextFrameNumber() -> Int {
        frameCounter += 1
        return frameCounter
    }

    nonisolated func onAppSwitchLegacy(newApp: String) {
        Task {
            await onAppSwitch(newApp: newApp)
        }
    }

    nonisolated func clearQueue() {
        Task {
            await clearPendingWork()
        }
    }

    // MARK: - Analysis

    private func formatHistory() -> String {
        guard !analysisHistory.isEmpty else { return "" }

        var lines = ["Recent activity (oldest to newest):"]
        for (i, past) in analysisHistory.enumerated() {
            lines.append("\(i + 1). [\(past.status.rawValue)] \(past.appOrSite): \(past.description)")
            if let message = past.message {
                lines.append("   Message: \(message)")
            }
        }
        return lines.joined(separator: "\n")
    }

    private func processFrame(_ frame: CapturedFrame) async {
        guard await isEnabled else { return }
        do {
            guard let analysis = try await analyzeScreenshot(jpegData: frame.jpegData) else {
                return
            }

            // Success — reset error backoff
            consecutiveErrorCount = 0
            errorBackoffEndTime = nil

            // Skip stale frames - a newer frame was processed while we were waiting for API
            guard frame.frameNumber > lastProcessedFrameNum else {
                log("[Frame \(frame.frameNumber)] Skipped (stale - frame \(lastProcessedFrameNum) already processed)")
                return
            }
            lastProcessedFrameNum = frame.frameNumber

            // Note: lastAnalyzedApp/lastAnalyzedWindowTitle are updated in analyze() when queuing,
            // not here, to prevent multiple frames being queued for the same context change

            // Add to history
            analysisHistory.append(analysis)
            if analysisHistory.count > maxHistorySize {
                analysisHistory.removeFirst()
            }

            log("[Frame \(frame.frameNumber)] [\(analysis.status.rawValue.uppercased())] \(analysis.appOrSite): \(analysis.description)")

            // Update status
            onStatusChange?(analysis.status)
            lastStatus = analysis.status

            // Only act on STATE CHANGE to prevent duplicates from parallel frames
            // e.g., if 3 frames all return "distracted", only the first one triggers
            if analysis.status == .distracted && lastNotifiedState != .distracted {
                // Transitioning to distracted state
                // Update notified state BEFORE other actions to prevent race with parallel frames
                lastNotifiedState = .distracted

                // Track distraction detected (use frame.windowTitle which has the actual window title)
                await MainActor.run {
                    AnalyticsManager.shared.distractionDetected(app: analysis.appOrSite, windowTitle: frame.windowTitle)
                }

                // Save to SQLite and sync to backend
                await saveFocusSessionToSQLite(analysis: analysis, screenshotId: frame.screenshotId, windowTitle: frame.windowTitle)

                // Update FocusStorage UI state (sessions list, currentStatus, currentApp)
                Task { @MainActor in
                    FocusStorage.shared.addSession(from: analysis)
                }

                // Trigger red glow via callback (runs on MainActor in plugin)
                onDistraction?()

                // Start analysis cooldown to prevent continuous API calls while distracted
                let cooldownSeconds = await MainActor.run {
                    FocusAssistantSettings.shared.cooldownIntervalSeconds
                }
                analysisCooldownEndTime = Date().addingTimeInterval(cooldownSeconds)
                log("Focus: Started \(Int(cooldownSeconds))s analysis cooldown")

                // Expose cooldown end time to UI
                let cooldownEndTime = analysisCooldownEndTime
                await MainActor.run {
                    FocusStorage.shared.updateCooldownEndTime(cooldownEndTime)
                }

                if let message = analysis.message {
                    let fullMessage = "\(analysis.appOrSite) - \(message)"
                    log("ALERT: \(message)")

                    let notificationsEnabled = await MainActor.run {
                        FocusAssistantSettings.shared.notificationsEnabled
                    }

                    await MainActor.run {
                        // Track focus alert shown
                        AnalyticsManager.shared.focusAlertShown(app: analysis.appOrSite)

                        if notificationsEnabled {
                            NotificationService.shared.sendNotification(
                                title: "Focus",
                                message: fullMessage,
                                assistantId: identifier,
                                sound: .focusLost
                            )
                        }
                    }

                    // Call the callback for Flutter event streaming
                    onAlert(fullMessage)
                }
            } else if analysis.status == .focused && lastNotifiedState != .focused {
                // Transitioning to focused state (from distracted OR initial nil state)
                let wasDistracted = lastNotifiedState == .distracted
                lastNotifiedState = .focused

                // Save to SQLite and sync to backend
                await saveFocusSessionToSQLite(analysis: analysis, screenshotId: frame.screenshotId, windowTitle: frame.windowTitle)

                // Update FocusStorage UI state (sessions list, currentStatus, currentApp)
                Task { @MainActor in
                    FocusStorage.shared.addSession(from: analysis)
                }

                // Only trigger glow and notification when returning FROM distracted
                if wasDistracted {
                    // Track focus restored
                    await MainActor.run {
                        AnalyticsManager.shared.focusRestored(app: analysis.appOrSite)
                    }

                    // Trigger the glow effect
                    onRefocus?()

                    if let message = analysis.message {
                        log("Back on track: \(message)")
                        let notificationsEnabled = await MainActor.run {
                            FocusAssistantSettings.shared.notificationsEnabled
                        }
                        if notificationsEnabled {
                            await MainActor.run {
                                NotificationService.shared.sendNotification(
                                    title: "Focus",
                                    message: message,
                                    assistantId: identifier,
                                    sound: .focusRegained
                                )
                            }
                        }
                    }
                }
            }
        } catch {
            consecutiveErrorCount += 1
            let backoffSeconds = min(5.0 * pow(2.0, Double(consecutiveErrorCount - 1)), 300.0) // 5s, 10s, 20s, 40s... cap 5min
            errorBackoffEndTime = Date().addingTimeInterval(backoffSeconds)
            logError("Frame \(frame.frameNumber) error (consecutive: \(consecutiveErrorCount), backoff: \(Int(backoffSeconds))s)", error: error)
        }
    }

    private func analyzeScreenshot(jpegData: Data) async throws -> ScreenAnalysis? {
        // Build prompt with history context
        let historyText = formatHistory()
        let prompt = historyText.isEmpty ? "Analyze this screenshot:" : "\(historyText)\n\nNow analyze this new screenshot:"

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema
        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "status": .init(type: "string", enum: ["focused", "distracted"], description: "Whether the user is focused or distracted"),
                "app_or_site": .init(type: "string", enum: nil, description: "The app or website visible"),
                "description": .init(type: "string", enum: nil, description: "Brief description of what's on screen"),
                "message": .init(type: "string", enum: nil, description: "Coaching message")
            ],
            required: ["status", "app_or_site", "description"]
        )

        do {
            let responseText = try await geminiClient.sendRequest(
                prompt: prompt,
                imageData: jpegData,
                systemPrompt: currentSystemPrompt,
                responseSchema: responseSchema
            )

            return try JSONDecoder().decode(ScreenAnalysis.self, from: Data(responseText.utf8))
        } catch {
            logError("Focus analysis error", error: error)
            return nil
        }
    }

    // MARK: - Storage

    /// Save focus session to SQLite (both tables) and sync to backend
    private func saveFocusSessionToSQLite(analysis: ScreenAnalysis, screenshotId: Int64?, windowTitle: String? = nil) async {
        // Save to focus_sessions table (for detailed tracking)
        let focusRecord = FocusSessionRecord(
            screenshotId: screenshotId,
            status: analysis.status.rawValue,
            appOrSite: analysis.appOrSite,
            windowTitle: windowTitle,
            description: analysis.description,
            message: analysis.message
        )

        var focusSessionId: Int64?
        do {
            let inserted = try await ProactiveStorage.shared.insertFocusSession(focusRecord)
            focusSessionId = inserted.id
            log("Focus: Saved to focus_sessions (id: \(inserted.id ?? -1), status: \(analysis.status.rawValue))")
        } catch {
            logError("Focus: Failed to save to focus_sessions", error: error)
        }

        // Save to unified memories table (for search/filter)
        let memoryId = await saveFocusToMemoriesTable(analysis: analysis, screenshotId: screenshotId, windowTitle: windowTitle)

        // Sync to backend once and update both tables with backendId
        if let backendId = await syncFocusSessionToBackend(analysis: analysis, windowTitle: windowTitle) {
            // Update focus_sessions table
            if let recordId = focusSessionId {
                do {
                    try await ProactiveStorage.shared.updateFocusSessionSyncStatus(
                        id: recordId,
                        backendId: backendId,
                        synced: true
                    )
                } catch {
                    logError("Focus: Failed to update focus_sessions sync status", error: error)
                }
            }

            // Update memories table
            if let memId = memoryId {
                do {
                    try await MemoryStorage.shared.markSynced(id: memId, backendId: backendId)
                } catch {
                    logError("Focus: Failed to update memories sync status", error: error)
                }
            }
        }
    }

    /// Save focus event to unified memories table for search/filter
    /// Returns the inserted memory ID if successful
    private func saveFocusToMemoriesTable(analysis: ScreenAnalysis, screenshotId: Int64?, windowTitle: String? = nil) async -> Int64? {
        // Build content for the memory
        let statusText = analysis.status == .focused ? "Focused" : "Distracted"
        let content = "\(statusText) on \(analysis.appOrSite): \(analysis.description)"

        // Build tags: ["focus", "focused"/"distracted", "app:{appName}"]
        let statusTag = analysis.status == .focused ? "focused" : "distracted"
        let appTag = "app:\(analysis.appOrSite)"
        var tags = ["focus", statusTag, appTag]

        // Add message indicator if present
        if let message = analysis.message, !message.isEmpty {
            tags.append("has-message")
        }

        // Encode tags as JSON
        let tagsJson: String?
        if let data = try? JSONEncoder().encode(tags),
           let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        } else {
            tagsJson = nil
        }

        let memoryRecord = MemoryRecord(
            backendSynced: false,
            content: content,
            category: "system",
            tagsJson: tagsJson,
            source: "desktop",
            screenshotId: screenshotId,
            sourceApp: analysis.appOrSite,
            windowTitle: windowTitle,
            contextSummary: analysis.description
        )

        do {
            let insertedMemory = try await MemoryStorage.shared.insertLocalMemory(memoryRecord)
            log("Focus: Saved to memories (id: \(insertedMemory.id ?? -1)) with tags \(tags)")
            return insertedMemory.id
        } catch {
            logError("Focus: Failed to save to memories table", error: error)
            return nil
        }
    }

    /// Sync focus session to backend as a memory with focus tags, returns backend ID if successful
    private func syncFocusSessionToBackend(analysis: ScreenAnalysis, windowTitle: String? = nil) async -> String? {
        do {
            // Build content for the memory
            let statusText = analysis.status == .focused ? "Focused" : "Distracted"
            let content = "\(statusText) on \(analysis.appOrSite): \(analysis.description)"

            // Build tags: ["focus", "focused"/"distracted", "app:{appName}"]
            let statusTag = analysis.status == .focused ? "focused" : "distracted"
            let appTag = "app:\(analysis.appOrSite)"
            var tags = ["focus", statusTag, appTag]

            // Add message indicator if present
            if let message = analysis.message, !message.isEmpty {
                tags.append("has-message")
            }

            let response = try await APIClient.shared.createMemory(
                content: content,
                visibility: "private",
                category: .system,
                tags: tags,
                source: "desktop",
                windowTitle: windowTitle
            )

            log("Focus: Synced as memory to backend (id: \(response.id))")
            return response.id
        } catch {
            logError("Focus: Failed to sync to backend", error: error)
            return nil
        }
    }
}

// MARK: - Backward Compatibility

/// Alias for backward compatibility
typealias GeminiService = FocusAssistant
