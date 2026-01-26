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
    private var previousTasks: [String: ExtractedTask] = [:] // Track by title hash
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
        self.geminiClient = try GeminiClient(apiKey: apiKey)

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

        // Get min confidence threshold
        let threshold = await minConfidence

        // Filter tasks by confidence
        let highConfidenceTasks = taskResult.tasks.filter { $0.confidence >= threshold }

        if highConfidenceTasks.isEmpty {
            log("Task: No high-confidence tasks found")
            return
        }

        // Check for new tasks (not seen before)
        var newTasks: [ExtractedTask] = []
        for task in highConfidenceTasks {
            let taskKey = task.title.lowercased().trimmingCharacters(in: .whitespaces)
            if previousTasks[taskKey] == nil {
                newTasks.append(task)
                previousTasks[taskKey] = task
            }
        }

        if newTasks.isEmpty {
            log("Task: No new tasks (all \(highConfidenceTasks.count) tasks already known)")
            return
        }

        log("Task: Found \(newTasks.count) new tasks")

        // Send events to Flutter
        for task in newTasks {
            sendEvent("taskExtracted", [
                "assistant": identifier,
                "task": task.toDictionary(),
                "contextSummary": taskResult.contextSummary
            ])
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

            log("Task: Extracted \(result.tasks.count) tasks from \(frame.appName)")
            log("Task: Activity: \(result.currentActivity)")

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
        let prompt = "Analyze this screenshot from \(appName) and extract any visible tasks, action items, or to-dos:"

        // Get current system prompt from settings
        let currentSystemPrompt = await systemPrompt

        // Build response schema for task extraction
        let taskSchema = GeminiRequest.GenerationConfig.ResponseSchema.Property.Items(
            type: "object",
            properties: [
                "title": .init(type: "string", description: "Brief, actionable task title"),
                "description": .init(type: "string", description: "Optional additional context"),
                "priority": .init(type: "string", enum: ["high", "medium", "low"], description: "Task priority"),
                "source_app": .init(type: "string", description: "App where task was found"),
                "inferred_deadline": .init(type: "string", description: "Deadline if visible or implied"),
                "confidence": .init(type: "number", description: "Confidence score 0.0-1.0")
            ],
            required: ["title", "priority", "source_app", "confidence"]
        )

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "tasks": .init(type: "array", description: "List of extracted tasks", items: taskSchema),
                "context_summary": .init(type: "string", description: "Brief summary of what user is looking at"),
                "current_activity": .init(type: "string", description: "High-level description of user's activity")
            ],
            required: ["tasks", "context_summary", "current_activity"]
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
