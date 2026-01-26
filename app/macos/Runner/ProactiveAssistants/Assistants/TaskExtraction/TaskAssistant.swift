import Foundation

/// Task extraction assistant that identifies tasks and action items from screen content
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

    private let geminiClient: GeminiClient
    private var isRunning = false
    private var lastAnalysisTime: Date = .distantPast
    private var previousTasks: [ExtractedTask] = [] // Last 10 extracted tasks for context
    private let maxPreviousTasks = 10
    private var currentApp: String?
    private var pendingFrame: CapturedFrame?
    private var processingTask: Task<Void, Never>?

    /// Get the current system prompt from settings (accessed on MainActor for thread safety)
    private var systemPrompt: String {
        get async {
            await MainActor.run {
                TaskAssistantSettings.shared.analysisPrompt
            }
        }
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

    init(apiKey: String? = nil) throws {
        // Use Gemini 3 Pro for better task extraction quality
        self.geminiClient = try GeminiClient(apiKey: apiKey, model: "gemini-3-pro-preview")

        // Start processing loop
        Task {
            await self.startProcessing()
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
        log("Task assistant started")

        while isRunning {
            // Check if we have a pending frame and enough time has passed
            if let frame = pendingFrame {
                let interval = await extractionInterval
                let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime)

                if timeSinceLastAnalysis >= interval {
                    pendingFrame = nil
                    lastAnalysisTime = Date()
                    await processFrame(frame)
                }
            }

            try? await Task.sleep(nanoseconds: 500_000_000) // Check every 0.5 seconds
        }

        log("Task assistant stopped")
    }

    // MARK: - ProactiveAssistant Protocol Methods

    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        // Task assistant analyzes less frequently - every N seconds
        // The actual interval is checked in the processing loop
        // Here we just accept frames to store the latest one
        return true
    }

    func analyze(frame: CapturedFrame) async -> AssistantResult? {
        // Store the latest frame - we'll process it when the interval has passed
        pendingFrame = frame
        // Note: This overwrites the previous frame, not a queue
        return nil
    }

    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async {
        guard let taskResult = result as? TaskExtractionResult else { return }

        // Check if AI found a new task
        guard taskResult.hasNewTask, let task = taskResult.task else {
            return
        }

        // Get min confidence threshold
        let threshold = await minConfidence
        let confidencePercent = Int(task.confidence * 100)

        // Check confidence threshold
        guard task.confidence >= threshold else {
            log("Task: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(task.title)\"")
            return
        }

        log("Task: [\(confidencePercent)% conf.] \"\(task.title)\"")

        // Add to previous tasks (keep last 10 for context)
        previousTasks.insert(task, at: 0)
        if previousTasks.count > maxPreviousTasks {
            previousTasks.removeLast()
        }

        // Send notification
        await sendTaskNotification(task: task)

        // Send event to Flutter
        sendEvent("taskExtracted", [
            "assistant": identifier,
            "task": task.toDictionary(),
            "contextSummary": taskResult.contextSummary
        ])
    }

    /// Send a notification for the extracted task
    private func sendTaskNotification(task: ExtractedTask) async {
        let message = task.title

        // Send notification immediately (extraction interval already throttles)
        await MainActor.run {
            NotificationService.shared.sendNotification(
                title: "",
                message: message,
                assistantId: identifier,
                applyCooldown: false
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
            // Don't clear previous tasks on app switch - we want to track across apps
        }
    }

    func clearPendingWork() async {
        pendingFrame = nil
        log("Task: Cleared pending frame")
    }

    func stop() async {
        isRunning = false
        processingTask?.cancel()
        pendingFrame = nil
    }

    // MARK: - Analysis

    private func processFrame(_ frame: CapturedFrame) async {
        do {
            guard let result = try await extractTasks(from: frame.jpegData, appName: frame.appName) else {
                return
            }

            // Handle the result
            await handleResult(result) { type, data in
                Task { @MainActor in
                    AssistantCoordinator.shared.sendEvent(type: type, data: data)
                }
            }
        } catch {
            log("Task extraction error: \(error)")
        }
    }

    private func extractTasks(from jpegData: Data, appName: String) async throws -> TaskExtractionResult? {
        // Build context with previous tasks
        var prompt = "Analyze this screenshot from \(appName).\n\n"

        if !previousTasks.isEmpty {
            prompt += "PREVIOUSLY EXTRACTED TASKS (do not re-extract these or semantically similar tasks):\n"
            for (index, task) in previousTasks.enumerated() {
                prompt += "\(index + 1). \(task.title)"
                if let description = task.description {
                    prompt += " - \(description)"
                }
                prompt += "\n"
            }
            prompt += "\nLook for ONE NEW task that is NOT already in the list above."
        } else {
            prompt += "Look for ONE task to extract."
        }

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema for single task extraction with conditional logic
        let taskProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
            "title": .init(type: "string", description: "Brief, actionable task title"),
            "description": .init(type: "string", description: "Optional additional context"),
            "priority": .init(type: "string", enum: ["high", "medium", "low"], description: "Task priority"),
            "source_app": .init(type: "string", description: "App where task was found"),
            "inferred_deadline": .init(type: "string", description: "Deadline if visible or implied"),
            "confidence": .init(type: "number", description: "Confidence score 0.0-1.0")
        ]

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "has_new_task": .init(type: "boolean", description: "True if a new task was found that is not in the previous tasks list"),
                "task": .init(
                    type: "object",
                    description: "The extracted task (only if has_new_task is true)",
                    properties: taskProperties,
                    required: ["title", "priority", "source_app", "confidence"]
                ),
                "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                "current_activity": .init(type: "string", description: "High-level description of user's activity")
            ],
            required: ["has_new_task", "context_summary", "current_activity"]
        )

        do {
            let responseText = try await geminiClient.sendRequest(
                prompt: prompt,
                imageData: jpegData,
                systemPrompt: currentSystemPrompt,
                responseSchema: responseSchema
            )

            return try JSONDecoder().decode(TaskExtractionResult.self, from: Data(responseText.utf8))
        } catch {
            log("Task analysis error: \(error)")
            return nil
        }
    }
}
