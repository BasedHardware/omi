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
    private var frameQueue: [CapturedFrame] = []
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

        while isRunning {
            if let frame = frameQueue.first {
                frameQueue.removeFirst()
                // Fire off analysis in background (don't wait) - like Python version
                let task = Task {
                    await self.processFrame(frame)
                }
                pendingTasks.insert(task)
                // Clean up completed tasks periodically
                pendingTasks = pendingTasks.filter { !$0.isCancelled }
            } else {
                try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
            }
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
        // Smart filtering: Skip analysis if user is focused on the same context
        if shouldSkipAnalysis(for: frame) {
            return nil
        }

        // Update last analyzed context IMMEDIATELY when queuing (not after API response)
        // This prevents multiple frames from being queued for the same context change
        lastAnalyzedApp = frame.appName
        lastAnalyzedWindowTitle = frame.windowTitle

        // Submit frame to internal queue for processing
        frameQueue.append(frame)
        log("Focus: Queued frame \(frame.frameNumber) for analysis: App=\(frame.appName), Window=\(frame.windowTitle ?? "unknown")")

        // Return nil since we process asynchronously
        return nil
    }

    /// Determines if we should skip analysis for this frame
    /// Returns true if:
    /// - User is focused on the same app AND same window title
    /// - OR we're in cooldown period after distraction (unless context changed)
    private func shouldSkipAnalysis(for frame: CapturedFrame) -> Bool {
        // Always analyze if we don't have a status yet
        guard lastStatus != nil else {
            return false
        }

        // Check if context changed (app or window title different from last analysis)
        let contextChanged = frame.appName != lastAnalyzedApp || frame.windowTitle != lastAnalyzedWindowTitle

        // Check 1: Context switch - ALWAYS analyze (bypass cooldown)
        if contextChanged {
            // Clear cooldown on context switch since user changed context
            if analysisCooldownEndTime != nil {
                log("Focus: Context switch detected, clearing cooldown - will analyze")
                analysisCooldownEndTime = nil
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

    func clearPendingWork() async {
        let count = frameQueue.count
        frameQueue.removeAll()
        // Cancel pending analysis tasks since those frames are now stale
        for task in pendingTasks {
            task.cancel()
        }
        pendingTasks.removeAll()
        if count > 0 {
            log("Focus: Cleared \(count) pending frames from queue")
        }
    }

    func stop() async {
        isRunning = false
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
        analysisCooldownEndTime = nil
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
        do {
            guard let analysis = try await analyzeScreenshot(jpegData: frame.jpegData) else {
                return
            }

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

            // Track state transition
            let justBecameFocused = lastStatus == .distracted && analysis.status == .focused
            lastStatus = analysis.status

            if analysis.status == .distracted {
                // Send distraction notification with cooldown
                if let message = analysis.message {
                    let fullMessage = "\(analysis.appOrSite) - \(message)"
                    log("ALERT: \(message)")

                    // Send notification and trigger red glow only if notification was actually sent
                    let notificationSent = NotificationService.shared.sendNotification(
                        title: "Focus Alert",
                        message: fullMessage,
                        applyCooldown: true
                    )

                    if notificationSent {
                        // Trigger red glow via callback (runs on MainActor in plugin)
                        onDistraction?()

                        // Start analysis cooldown (same as notification cooldown)
                        // This prevents continuous API calls while user is distracted
                        let cooldownSeconds = await MainActor.run {
                            AssistantSettings.shared.cooldownIntervalSeconds
                        }
                        analysisCooldownEndTime = Date().addingTimeInterval(cooldownSeconds)
                        log("Focus: Started \(Int(cooldownSeconds))s analysis cooldown")
                    }

                    // Still call the callback for Flutter event streaming
                    onAlert(fullMessage)
                }
            } else if justBecameFocused {
                // Only notify once when transitioning TO focused state
                // Trigger the glow effect
                onRefocus?()

                if let message = analysis.message {
                    log("Back on track: \(message)")
                    NotificationService.shared.sendNotification(
                        title: "OMI - Focus",
                        message: message,
                        applyCooldown: false
                    )
                }
            }
        } catch {
            log("Frame \(frame.frameNumber) error: \(error)")
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
            log("Focus analysis error: \(error)")
            return nil
        }
    }
}

// MARK: - Backward Compatibility

/// Alias for backward compatibility
typealias GeminiService = FocusAssistant
