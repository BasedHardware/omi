import Foundation

/// Task extraction assistant that identifies tasks and action items from screen content.
/// Phase 2: sends screenshots to backend via WebSocket, receives structured task results.
actor TaskAssistant: ProactiveAssistant {
    // MARK: - ProactiveAssistant Protocol

    nonisolated let identifier = "task-extraction"
    nonisolated let displayName = "Task Extractor"

    var isEnabled: Bool {
        get async {
            await MainActor.run {
                TaskAssistantSettings.shared.isEnabled
            }
        }
    }

    // MARK: - Properties

    private let backendService: BackendProactiveService
    private var isRunning = false
    private var previousTasks: [ExtractedTask] = [] // Last 10 extracted tasks for context
    private let maxPreviousTasks = 10
    private var currentApp: String?
    private var processingTask: Task<Void, Never>?

    // MARK: - Event-Driven Trigger System
    private enum TriggerEvent {
        case contextSwitch(CapturedFrame)  // departing frame from context being left
        case timerFallback(CapturedFrame)  // latest frame after extraction interval
    }

    private let triggerStream: AsyncStream<TriggerEvent>
    private let triggerContinuation: AsyncStream<TriggerEvent>.Continuation

    /// Always holds the most recent frame for fallback timer use
    private var latestFrame: CapturedFrame?
    /// Fallback timer that fires after extractionInterval if no context switch occurs
    private var fallbackTimerTask: Task<Void, Never>?
    /// Timestamp of last context switch yield, for throttling rapid switches
    private var lastContextSwitchYieldTime: Date = .distantPast

    // MARK: - Due Date Helpers

    /// Parse an inferred deadline string into a Date, or default to end of today.
    /// Tries ISO8601, then common natural language patterns.
    private func parseDueDate(from inferredDeadline: String?) -> Date? {
        guard let deadline = inferredDeadline, !deadline.isEmpty else {
            return nil
        }
        let startOfToday = Calendar.current.startOfDay(for: Date())

        // Try ISO8601 first (e.g. "2025-10-04T14:00:00Z")
        let iso = ISO8601DateFormatter()
        if let date = iso.date(from: deadline) {
            if date < startOfToday {
                log("Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future.")
                return nil
            }
            return date
        }
        // Try common date formats
        let formats = [
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd",
            "MM/dd/yyyy",
            "MMMM d, yyyy",
            "MMM d, yyyy",
            "MMMM d",
            "MMM d"
        ]
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        for format in formats {
            formatter.dateFormat = format
            if let date = formatter.date(from: deadline) {
                if date < startOfToday {
                    log("Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future.")
                    return nil
                }
                return date
            }
        }

        // Fallback: try macOS natural language date parsing (handles "Thursday", "next week", etc.)
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.date.rawValue)
        if let match = detector?.firstMatch(in: deadline, range: NSRange(deadline.startIndex..., in: deadline)),
           let date = match.date {
            // Validate that the parsed date is not in the past
            let startOfToday = Calendar.current.startOfDay(for: Date())
            if date < startOfToday {
                log("Task: Rejected past due date '\(deadline)' → \(date). Today is \(Date()). Due dates must be today or in the future.")
                return nil
            }
            return date
        }

        log("Task: Could not parse inferred_deadline '\(deadline)', skipping deadline")
        return nil
    }

    /// Returns 11:59 PM today in the user's local timezone
    private static func endOfToday() -> Date {
        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: Date())
        return calendar.date(bySettingHour: 23, minute: 59, second: 0, of: startOfDay) ?? startOfDay
    }

    /// Get the extraction interval from settings
    private var extractionInterval: TimeInterval {
        get async {
            await MainActor.run {
                TaskAssistantSettings.shared.extractionInterval
            }
        }
    }

    /// Get the minimum confidence threshold from settings
    private var minConfidence: Double {
        get async {
            await MainActor.run {
                TaskAssistantSettings.shared.minConfidence
            }
        }
    }

    // MARK: - Initialization

    init(backendService: BackendProactiveService) {
        self.backendService = backendService

        let (stream, continuation) = AsyncStream.makeStream(of: TriggerEvent.self, bufferingPolicy: .bufferingNewest(1))
        self.triggerStream = stream
        self.triggerContinuation = continuation

        // Start processing loop + embedding index
        Task {
            await self.startProcessing()
            await self.initializeEmbeddings()
        }
    }

    // MARK: - Embedding Lifecycle

    /// Load embedding index and kick off backfill
    private func initializeEmbeddings() async {
        await EmbeddingService.shared.loadIndex()
        // Backfill in background
        Task {
            await EmbeddingService.shared.backfillIfNeeded()
        }
    }

    // MARK: - Processing

    private func startProcessing() {
        isRunning = true
        processingTask = Task {
            await processLoop()
        }
    }

    private func processLoop() async {
        log("Task assistant started (event-driven)")

        for await trigger in triggerStream {
            guard isRunning else { break }

            let (frame, triggerType): (CapturedFrame, String) = {
                switch trigger {
                case .contextSwitch(let f): return (f, "context_switch")
                case .timerFallback(let f): return (f, "timer_fallback")
                }
            }()

            log("Task: Processing \(triggerType) trigger from \(frame.appName) (window: \(frame.windowTitle ?? "nil"))")

            // Cancel fallback timer before processing
            fallbackTimerTask?.cancel()
            fallbackTimerTask = nil

            await processFrame(frame)

            // Start a new fallback timer after processing
            startFallbackTimer()
        }

        log("Task assistant stopped")
    }

    /// Start (or restart) the fallback timer that fires after extractionInterval
    private func startFallbackTimer() {
        fallbackTimerTask?.cancel()
        fallbackTimerTask = Task {
            let interval = await self.extractionInterval
            try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            guard !Task.isCancelled else { return }
            guard let frame = self.latestFrame else { return }
            log("Task: Fallback timer fired after \(Int(interval))s")
            self.triggerContinuation.yield(.timerFallback(frame))
        }
    }

    // MARK: - Test Analysis (for test runner)

    /// Run extraction via backend for test runner. Returns (result, 0) for compatibility.
    func testAnalyze(jpegData: Data, appName: String) async throws -> (TaskExtractionResult?, Int) {
        let base64 = autoreleasepool { jpegData.base64EncodedString() }
        let backendResult = try await backendService.extractTasks(
            imageBase64: base64, appName: appName, windowTitle: ""
        )
        if backendResult.tasks.isEmpty {
            return (TaskExtractionResult(hasNewTask: false, task: nil, contextSummary: "Analyzed \(appName)", currentActivity: ""), 0)
        }
        let result = parseBackendTask(backendResult.tasks[0], appName: appName)
        return (result, 0)
    }

    // MARK: - ProactiveAssistant Protocol Methods

    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        return true
    }

    func analyze(frame: CapturedFrame) async -> AssistantResult? {
        // Only analyze apps on the whitelist
        let allowed = await MainActor.run { TaskAssistantSettings.shared.isAppAllowed(frame.appName) }
        if !allowed {
            return nil
        }

        // For browser apps, also check window title against enabled heuristics
        let windowAllowed = await MainActor.run {
            TaskAssistantSettings.shared.isWindowAllowed(appName: frame.appName, windowTitle: frame.windowTitle)
        }
        if !windowAllowed {
            return nil
        }

        // Store as latest frame (used by fallback timer and context switch)
        latestFrame = frame

        // Start fallback timer if not already running
        if fallbackTimerTask == nil {
            startFallbackTimer()
        }

        return nil
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        guard let taskResult = result as? TaskExtractionResult else { return }
        await handleResultWithScreenshot(taskResult, screenshotId: nil, appName: "Unknown", sendEvent: sendEvent)
    }

    /// Handle result with screenshot ID for SQLite storage
    private func handleResultWithScreenshot(
        _ taskResult: TaskExtractionResult,
        screenshotId: Int64?,
        appName: String,
        windowTitle: String? = nil,
        sendEvent: @escaping (String, [String: Any]) -> Void
    ) async {
        // Save observation for every result (fire-and-forget)
        let observationApp = taskResult.task?.sourceApp ?? appName
        let observation = ObservationRecord(
            screenshotId: screenshotId,
            appName: observationApp,
            contextSummary: taskResult.contextSummary,
            currentActivity: taskResult.currentActivity,
            hasTask: taskResult.hasNewTask,
            taskTitle: taskResult.task?.title,
            sourceCategory: taskResult.task?.sourceCategory,
            sourceSubcategory: taskResult.task?.sourceSubcategory,
            createdAt: Date()
        )
        Task {
            do {
                try await ActionItemStorage.shared.insertObservation(observation)
            } catch {
                logError("Task: Failed to insert observation", error: error)
            }
        }

        guard taskResult.hasNewTask, let task = taskResult.task else {
            return
        }

        let threshold = await minConfidence
        let confidencePercent = Int(task.confidence * 100)

        guard task.confidence >= threshold else {
            log("Task: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(task.title)\"")
            return
        }

        log("Task: [\(confidencePercent)% conf.] \"\(task.title)\"")

        previousTasks.insert(task, at: 0)
        if previousTasks.count > maxPreviousTasks {
            previousTasks.removeLast()
        }

        // Save to staged_tasks SQLite + generate embedding
        let extractionRecord = await saveTaskToSQLite(
            task: task,
            screenshotId: screenshotId,
            contextSummary: taskResult.contextSummary,
            windowTitle: windowTitle
        )

        // Generate embedding for new staged task in background
        if let recordId = extractionRecord?.id {
            Task {
                await self.generateEmbeddingForTask(id: recordId, text: task.title)
            }
        }

        // Sync to backend (staged_tasks)
        if let backendId = await syncTaskToBackend(task: task, taskResult: taskResult, windowTitle: windowTitle) {
            if let recordId = extractionRecord?.id {
                do {
                    try await StagedTaskStorage.shared.markSynced(id: recordId, backendId: backendId)
                } catch {
                    logError("Task: Failed to update sync status", error: error)
                }
            }
        }

        await MainActor.run {
            AnalyticsManager.shared.taskExtracted(taskCount: 1)
        }

        sendEvent("taskExtracted", [
            "assistant": identifier,
            "task": task.toDictionary(),
            "contextSummary": taskResult.contextSummary
        ])
    }

    /// Generate embedding for a newly saved staged task and store it
    private func generateEmbeddingForTask(id: Int64, text: String) async {
        do {
            let embedding = try await EmbeddingService.shared.embed(text: text)
            let data = await EmbeddingService.shared.floatsToData(embedding)
            try await StagedTaskStorage.shared.updateEmbedding(id: id, embedding: data)
            await EmbeddingService.shared.addToIndex(id: id, embedding: embedding)
            log("Task: Generated embedding for staged task \(id)")
        } catch {
            logError("Task: Failed to generate embedding for staged task \(id)", error: error)
        }
    }

    /// Save extracted task to staged_tasks SQLite table
    private func saveTaskToSQLite(
        task: ExtractedTask,
        screenshotId: Int64?,
        contextSummary: String,
        windowTitle: String? = nil
    ) async -> StagedTaskRecord? {
        var metadata: [String: Any] = [
            "tags": task.tags,
            "context_summary": contextSummary,
            "source_category": task.sourceCategory,
            "source_subcategory": task.sourceSubcategory
        ]
        if let primaryTag = task.primaryTag {
            metadata["category"] = primaryTag
        }
        if let deadline = task.inferredDeadline {
            metadata["inferred_deadline"] = deadline
        }
        if let windowTitle = windowTitle {
            metadata["window_title"] = windowTitle
        }

        let metadataJson: String?
        if let data = try? JSONSerialization.data(withJSONObject: metadata),
           let json = String(data: data, encoding: .utf8) {
            metadataJson = json
        } else {
            metadataJson = nil
        }

        let tagsJson: String?
        if let data = try? JSONEncoder().encode(task.tags),
           let json = String(data: data, encoding: .utf8) {
            tagsJson = json
        } else {
            tagsJson = nil
        }

        let dueAt = parseDueDate(from: task.inferredDeadline)

        let record = StagedTaskRecord(
            backendSynced: false,
            description: task.title,
            source: "screenshot",
            priority: task.priority.rawValue,
            category: task.primaryTag,
            tagsJson: tagsJson,
            dueAt: dueAt,
            screenshotId: screenshotId,
            confidence: task.confidence,
            sourceApp: task.sourceApp,
            windowTitle: windowTitle,
            contextSummary: contextSummary,
            metadataJson: metadataJson,
            relevanceScore: task.relevanceScore,
            scoredAt: task.relevanceScore != nil ? Date() : nil
        )

        do {
            let inserted: StagedTaskRecord
            if task.relevanceScore != nil {
                inserted = try await StagedTaskStorage.shared.insertWithScoreShift(record)
            } else {
                inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(record)
            }
            log("Task: Saved to staged_tasks (id: \(inserted.id ?? -1), score: \(task.relevanceScore.map { String($0) } ?? "nil"))")
            return inserted
        } catch {
            logError("Task: Failed to save to staged_tasks", error: error)
            return nil
        }
    }

    /// Sync task to backend API, returns backend ID if successful
    private func syncTaskToBackend(task: ExtractedTask, taskResult: TaskExtractionResult, windowTitle: String? = nil) async -> String? {
        do {
            var metadata: [String: Any] = [
                "source_app": task.sourceApp,
                "confidence": task.confidence,
                "context_summary": taskResult.contextSummary,
                "current_activity": taskResult.currentActivity,
                "tags": task.tags,
                "source_category": task.sourceCategory,
                "source_subcategory": task.sourceSubcategory
            ]
            if let primaryTag = task.primaryTag {
                metadata["category"] = primaryTag
            }
            if let reasoning = task.description {
                metadata["reasoning"] = reasoning
            }
            if let deadline = task.inferredDeadline {
                metadata["inferred_deadline"] = deadline
            }
            if let windowTitle = windowTitle {
                metadata["window_title"] = windowTitle
            }

            let dueAt = parseDueDate(from: task.inferredDeadline)

            let response = try await APIClient.shared.createStagedTask(
                description: task.title,
                dueAt: dueAt,
                source: "screenshot",
                priority: task.priority.rawValue,
                category: task.primaryTag,
                metadata: metadata,
                relevanceScore: task.relevanceScore
            )

            log("Task: Synced to staged_tasks backend (id: \(response.id))")
            return response.id
        } catch {
            logError("Task: Failed to sync to backend", error: error)
            return nil
        }
    }

    /// Send a notification for the extracted task
    private func sendTaskNotification(task: ExtractedTask) async {
        let message = task.title
        await MainActor.run {
            NotificationService.shared.sendNotification(
                title: "Task",
                message: message,
                assistantId: identifier
            )
        }
    }

    func onAppSwitch(newApp: String) async {
        if newApp != currentApp {
            if let currentApp = currentApp {
                log("Task: APP SWITCH: \(currentApp) -> \(newApp)")
            } else {
                log("Task: Active app: \(newApp)")
            }
            currentApp = newApp
        }
    }

    func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
        // Use latestFrame if departing frame is unavailable or stale (from a different app due to delay periods)
        let frame: CapturedFrame? = {
            if let departing = departingFrame {
                return departing
            }
            return latestFrame
        }()

        guard let frame = frame else {
            log("Task: Context switch but no frame available")
            return
        }

        // Check frame's app is on the whitelist
        let allowed = await MainActor.run { TaskAssistantSettings.shared.isAppAllowed(frame.appName) }
        if !allowed {
            log("Task: Context switch from non-whitelisted app '\(frame.appName)', skipping")
            // Still cancel fallback timer on any context switch
            fallbackTimerTask?.cancel()
            fallbackTimerTask = nil
            return
        }

        // Check window is allowed for browser apps
        let windowAllowed = await MainActor.run {
            TaskAssistantSettings.shared.isWindowAllowed(appName: frame.appName, windowTitle: frame.windowTitle)
        }
        if !windowAllowed {
            log("Task: Context switch from filtered browser window, skipping")
            fallbackTimerTask?.cancel()
            fallbackTimerTask = nil
            return
        }

        log("Task: Context switch from \(frame.appName) (window: \(frame.windowTitle ?? "nil")) -> \(newApp)")

        // Throttle context switch yields using the analysis delay setting
        let analysisDelay = await MainActor.run { AssistantSettings.shared.analysisDelay }
        if analysisDelay > 0 {
            let elapsed = Date().timeIntervalSince(lastContextSwitchYieldTime)
            if elapsed < TimeInterval(analysisDelay) {
                log("Task: Context switch throttled (\(Int(elapsed))s < \(analysisDelay)s delay)")
                // Still cancel fallback timer so it resets
                fallbackTimerTask?.cancel()
                fallbackTimerTask = nil
                return
            }
        }

        // Cancel fallback timer — context switch replaces it
        fallbackTimerTask?.cancel()
        fallbackTimerTask = nil

        // Yield context switch trigger with the frame
        lastContextSwitchYieldTime = Date()
        triggerContinuation.yield(.contextSwitch(frame))
    }

    func clearPendingWork() async {
        fallbackTimerTask?.cancel()
        fallbackTimerTask = nil
        log("Task: Cleared fallback timer")
    }

    func stop() async {
        isRunning = false
        fallbackTimerTask?.cancel()
        fallbackTimerTask = nil
        triggerContinuation.finish()
        processingTask?.cancel()
        latestFrame = nil
    }

    // MARK: - Backend Analysis (Phase 2 thin client)

    private func processFrame(_ frame: CapturedFrame) async {
        let enabled = await isEnabled
        guard enabled else {
            log("Task: Skipping analysis (disabled)")
            return
        }

        log("Task: Analyzing frame from \(frame.appName)...")
        do {
            let base64 = autoreleasepool { frame.jpegData.base64EncodedString() }
            let backendResult = try await backendService.extractTasks(
                imageBase64: base64,
                appName: frame.appName,
                windowTitle: frame.windowTitle ?? ""
            )

            let sendEvent: (String, [String: Any]) -> Void = { type, data in
                Task { @MainActor in
                    AssistantCoordinator.shared.sendEvent(type: type, data: data)
                }
            }

            if backendResult.tasks.isEmpty {
                let result = TaskExtractionResult(
                    hasNewTask: false, task: nil,
                    contextSummary: "Analyzed \(frame.appName)",
                    currentActivity: ""
                )
                log("Task: Analysis returned no tasks")
                await handleResultWithScreenshot(result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle, sendEvent: sendEvent)
                return
            }

            log("Task: Analysis complete - \(backendResult.tasks.count) task(s)")

            for taskDict in backendResult.tasks {
                let result = parseBackendTask(taskDict, appName: frame.appName)
                await handleResultWithScreenshot(result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle, sendEvent: sendEvent)
            }
        } catch {
            logError("Task extraction error", error: error)
        }
    }

    /// Parse a raw task dict from the backend into a TaskExtractionResult.
    private func parseBackendTask(_ dict: [String: Any], appName: String) -> TaskExtractionResult {
        let title = dict["title"] as? String ?? ""
        let description = dict["description"] as? String
        let priorityStr = dict["priority"] as? String ?? "medium"
        let priority = TaskPriority(rawValue: priorityStr) ?? .medium
        let tags = (dict["tags"] as? [String]) ?? []
        let sourceApp = dict["source_app"] as? String ?? appName
        let inferredDeadline = dict["inferred_deadline"] as? String
        let confidence: Double
        if let confValue = dict["confidence"] as? Double {
            confidence = confValue
        } else if let confInt = dict["confidence"] as? Int {
            confidence = Double(confInt)
        } else {
            confidence = 0.5
        }
        let sourceCategory = dict["source_category"] as? String ?? "other"
        let sourceSubcategory = dict["source_subcategory"] as? String ?? "other"
        let relevanceScore: Int?
        if let scoreValue = dict["relevance_score"] as? Int {
            relevanceScore = scoreValue
        } else if let scoreDouble = dict["relevance_score"] as? Double {
            relevanceScore = Int(scoreDouble)
        } else {
            relevanceScore = nil
        }

        let task = ExtractedTask(
            title: title,
            description: description?.isEmpty == true ? nil : description,
            priority: priority,
            sourceApp: sourceApp,
            inferredDeadline: inferredDeadline?.isEmpty == true ? nil : inferredDeadline,
            confidence: confidence,
            tags: tags,
            sourceCategory: sourceCategory,
            sourceSubcategory: sourceSubcategory,
            relevanceScore: relevanceScore
        )

        return TaskExtractionResult(
            hasNewTask: true,
            task: task,
            contextSummary: dict["context_summary"] as? String ?? "Analyzed \(appName)",
            currentActivity: dict["current_activity"] as? String ?? ""
        )
    }

}
