import Foundation

// Models are in FocusModels.swift

// MARK: - Gemini API Request/Response Types

struct GeminiRequest: Encodable {
    let contents: [Content]
    let systemInstruction: SystemInstruction?
    let generationConfig: GenerationConfig?

    enum CodingKeys: String, CodingKey {
        case contents
        case systemInstruction = "system_instruction"
        case generationConfig = "generation_config"
    }

    struct Content: Encodable {
        let parts: [Part]
    }

    struct Part: Encodable {
        let text: String?
        let inlineData: InlineData?

        enum CodingKeys: String, CodingKey {
            case text
            case inlineData = "inline_data"
        }

        init(text: String) {
            self.text = text
            self.inlineData = nil
        }

        init(mimeType: String, data: String) {
            self.text = nil
            self.inlineData = InlineData(mimeType: mimeType, data: data)
        }
    }

    struct InlineData: Encodable {
        let mimeType: String
        let data: String

        enum CodingKeys: String, CodingKey {
            case mimeType = "mime_type"
            case data
        }
    }

    struct SystemInstruction: Encodable {
        let parts: [TextPart]

        struct TextPart: Encodable {
            let text: String
        }
    }

    struct GenerationConfig: Encodable {
        let responseMimeType: String
        let responseSchema: ResponseSchema?

        enum CodingKeys: String, CodingKey {
            case responseMimeType = "response_mime_type"
            case responseSchema = "response_schema"
        }

        struct ResponseSchema: Encodable {
            let type: String
            let properties: [String: Property]
            let required: [String]

            struct Property: Encodable {
                let type: String
                let `enum`: [String]?
                let description: String?
            }
        }
    }
}

struct GeminiResponse: Decodable {
    let candidates: [Candidate]?
    let error: GeminiError?

    struct Candidate: Decodable {
        let content: Content?

        struct Content: Decodable {
            let parts: [Part]?

            struct Part: Decodable {
                let text: String?
            }
        }
    }

    struct GeminiError: Decodable {
        let message: String
    }
}

// MARK: - GeminiService

actor GeminiService {
    private let apiKey: String
    private let onAlert: (String) -> Void
    private let onStatusChange: ((FocusStatus) -> Void)?
    private let onRefocus: (() -> Void)?
    private let onDistraction: (() -> Void)?

    private var isRunning = false
    private var frameQueue: [Frame] = []
    private var frameCount = 0
    private var analysisHistory: [ScreenAnalysis] = []
    private let maxHistorySize = 10
    private var lastStatus: FocusStatus?
    private var lastProcessedFrameNum = 0
    private var processingTask: Task<Void, Never>?
    private var pendingTasks: Set<Task<Void, Never>> = []

    private let systemPrompt = """
        You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots.

        IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. If you see a code editor with logs that mention "YouTube" - that's just log text, the user is CODING, not on YouTube.

        Set status to "distracted" only if the PRIMARY window is:
        - YouTube, Twitch, Netflix (actual video site visible, not just text mentioning it)
        - Social media feeds: Twitter/X, Instagram, TikTok, Facebook, Reddit
        - News sites, entertainment sites, games

        Set status to "focused" if the PRIMARY window is:
        - Code editors, IDEs (even if logs mention other sites)
        - Terminals, command line
        - Documents, spreadsheets, slides
        - Email, work chat, research

        CRITICAL: Text in logs/terminals mentioning "YouTube" does NOT mean the user is on YouTube. Look at the actual browser or app window.

        You may receive recent analysis history showing what the user has been doing. Use this context to:
        - Notice patterns (e.g., "You've been on Discord for a while now...")
        - Acknowledge transitions (e.g., "Welcome back to coding!")
        - Avoid repetitive messages by varying your responses based on what you've already said

        Always provide a short coaching message based on what you see:
        - If distracted: Create a unique message to help them refocus. Vary your approach - be playful, direct, or motivational.
        - If focused: Acknowledge their work with variety - don't just say "Nice focus!" every time.
        """

    init(
        apiKey: String? = nil,
        onAlert: @escaping (String) -> Void,
        onStatusChange: ((FocusStatus) -> Void)? = nil,
        onRefocus: (() -> Void)? = nil,
        onDistraction: (() -> Void)? = nil
    ) throws {
        guard let key = apiKey ?? ProcessInfo.processInfo.environment["GEMINI_API_KEY"] else {
            throw GeminiError.missingAPIKey
        }
        self.apiKey = key
        self.onAlert = onAlert
        self.onStatusChange = onStatusChange
        self.onRefocus = onRefocus
        self.onDistraction = onDistraction

        // Start processing loop in a task
        Task {
            await self.startProcessing()
        }
    }

    enum GeminiError: LocalizedError {
        case missingAPIKey
        case networkError(Error)
        case invalidResponse

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "GEMINI_API_KEY not set"
            case .networkError(let error):
                return "Network error: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from Gemini API"
            }
        }
    }

    private func startProcessing() {
        isRunning = true
        processingTask = Task {
            await processFrameLoop()
        }
    }

    private func processFrameLoop() async {
        log("OMI monitoring started (parallel mode)")

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

        log("OMI monitoring stopped")
    }

    nonisolated func submitFrame(jpegData: Data, appName: String) {
        Task {
            await _submitFrame(jpegData: jpegData, appName: appName)
        }
    }

    private func _submitFrame(jpegData: Data, appName: String) {
        frameCount += 1
        let frame = Frame(jpegData: jpegData, appName: appName, frameNum: frameCount)
        frameQueue.append(frame)
        log("Captured frame \(frameCount): App=\(appName)")
    }

    nonisolated func onAppSwitch(newApp: String) {
        Task {
            await _onAppSwitch(newApp: newApp)
        }
    }

    private var currentApp: String?

    private func _onAppSwitch(newApp: String) {
        if newApp != currentApp {
            if let currentApp = currentApp {
                log("APP SWITCH: \(currentApp) -> \(newApp)")
            } else {
                log("Active app: \(newApp)")
            }
            currentApp = newApp
        }
    }

    func stop() {
        isRunning = false
        processingTask?.cancel()
        // Cancel all pending analysis tasks
        for task in pendingTasks {
            task.cancel()
        }
        pendingTasks.removeAll()
    }

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

    private func processFrame(_ frame: Frame) async {
        do {
            guard let analysis = try await analyzeScreenshot(jpegData: frame.jpegData) else {
                return
            }

            // Skip stale frames - a newer frame was processed while we were waiting for API
            guard frame.frameNum > lastProcessedFrameNum else {
                log("[Frame \(frame.frameNum)] Skipped (stale - frame \(lastProcessedFrameNum) already processed)")
                return
            }
            lastProcessedFrameNum = frame.frameNum

            // Add to history
            analysisHistory.append(analysis)
            if analysisHistory.count > maxHistorySize {
                analysisHistory.removeFirst()
            }

            log("[Frame \(frame.frameNum)] [\(analysis.status.rawValue.uppercased())] \(analysis.appOrSite): \(analysis.description)")

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
                        // Trigger red glow via callback (runs on MainActor in FocusPlugin)
                        onDistraction?()
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
            log("Frame \(frame.frameNum) error: \(error)")
        }
    }

    private func analyzeScreenshot(jpegData: Data) async throws -> ScreenAnalysis? {
        let base64Data = jpegData.base64EncodedString()

        // Build prompt with history context
        let historyText = formatHistory()
        let prompt = historyText.isEmpty ? "Analyze this screenshot:" : "\(historyText)\n\nNow analyze this new screenshot:"

        // Build request
        let request = GeminiRequest(
            contents: [
                GeminiRequest.Content(parts: [
                    GeminiRequest.Part(text: prompt),
                    GeminiRequest.Part(mimeType: "image/jpeg", data: base64Data)
                ])
            ],
            systemInstruction: GeminiRequest.SystemInstruction(
                parts: [GeminiRequest.SystemInstruction.TextPart(text: systemPrompt)]
            ),
            generationConfig: GeminiRequest.GenerationConfig(
                responseMimeType: "application/json",
                responseSchema: GeminiRequest.GenerationConfig.ResponseSchema(
                    type: "object",
                    properties: [
                        "status": .init(type: "string", enum: ["focused", "distracted"], description: "Whether the user is focused or distracted"),
                        "app_or_site": .init(type: "string", enum: nil, description: "The app or website visible"),
                        "description": .init(type: "string", enum: nil, description: "Brief description of what's on screen"),
                        "message": .init(type: "string", enum: nil, description: "Coaching message")
                    ],
                    required: ["status", "app_or_site", "description"]
                )
            )
        )

        // Make API request
        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key=\(apiKey)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)

        let response = try JSONDecoder().decode(GeminiResponse.self, from: data)

        if let error = response.error {
            log("API error: \(error.message)")
            return nil
        }

        guard let text = response.candidates?.first?.content?.parts?.first?.text else {
            return nil
        }

        return try JSONDecoder().decode(ScreenAnalysis.self, from: Data(text.utf8))
    }
}
