import Foundation

/// Coordinates all proactive assistants, distributing frames and managing lifecycle
@MainActor
class AssistantCoordinator {
    static let shared = AssistantCoordinator()

    // MARK: - Properties

    private var assistants: [String: any ProactiveAssistant] = [:]
    private var lastAnalysisTime: [String: Date] = [:]
    private var eventCallback: ((String, [String: Any]) -> Void)?

    // MARK: - Context Tracking (for context switch detection)
    private var lastTrackedApp: String?
    private var lastTrackedWindowTitle: String?
    private var lastTrackedFrame: CapturedFrame?

    /// Backpressure: track which assistants are currently analyzing a frame.
    /// Prevents Task closures from accumulating CapturedFrame JPEG data when analyze() is slow.
    private var isAnalyzing: Set<String> = []

    private init() {}

    // MARK: - Registration

    /// Register an assistant with the coordinator
    /// - Parameter assistant: The assistant to register
    func register<T: ProactiveAssistant>(_ assistant: T) {
        Task {
            let id = await assistant.identifier
            assistants[id] = assistant
            lastAnalysisTime[id] = .distantPast
            log("Registered assistant: \(id)")
        }
    }

    /// Unregister an assistant
    /// - Parameter identifier: The identifier of the assistant to remove
    func unregister(identifier: String) {
        assistants.removeValue(forKey: identifier)
        lastAnalysisTime.removeValue(forKey: identifier)
        log("Unregistered assistant: \(identifier)")
    }

    /// Get all registered assistant identifiers
    var registeredAssistants: [String] {
        Array(assistants.keys)
    }

    /// Get an assistant by identifier
    func assistant(withIdentifier id: String) -> (any ProactiveAssistant)? {
        assistants[id]
    }

    // MARK: - Event Callback

    /// Set the callback for sending events to Flutter
    /// - Parameter callback: Function that takes event type and data
    func setEventCallback(_ callback: @escaping (String, [String: Any]) -> Void) {
        self.eventCallback = callback
    }

    /// Send an event to Flutter
    func sendEvent(type: String, data: [String: Any]) {
        eventCallback?(type, data)
    }

    // MARK: - Context Switch Detection

    /// Check if the user's context changed (app or normalized window title) and fire
    /// `onContextSwitch` on all assistants if so. Called by the plugin for both app switches
    /// and window title changes — one unified path with one delay mechanism.
    /// - Returns: `true` if a context switch was detected and fired.
    @discardableResult
    func checkContextSwitch(newApp: String, newWindowTitle: String?) -> Bool {
        guard lastTrackedApp != nil else {
            lastTrackedApp = newApp
            lastTrackedWindowTitle = newWindowTitle
            return false
        }

        let changed = ContextDetection.didContextChange(
            fromApp: lastTrackedApp,
            fromWindowTitle: lastTrackedWindowTitle,
            toApp: newApp,
            toWindowTitle: newWindowTitle
        )
        guard changed else { return false }

        let departingFrame = lastTrackedFrame
        log("Context switch detected: \(lastTrackedApp ?? "nil") (\(ContextDetection.normalizeWindowTitle(lastTrackedWindowTitle) ?? "nil")) -> \(newApp) (\(ContextDetection.normalizeWindowTitle(newWindowTitle) ?? "nil"))")

        // Update tracking state
        lastTrackedApp = newApp
        lastTrackedWindowTitle = newWindowTitle

        // Fire on all assistants
        for (_, assistant) in assistants {
            Task {
                await assistant.onContextSwitch(
                    departingFrame: departingFrame,
                    newApp: newApp,
                    newWindowTitle: newWindowTitle
                )
            }
        }

        return true
    }

    // MARK: - Frame Tracking & Distribution

    /// Keep the latest frame reference fresh (call on every capture, even during delay).
    func trackFrame(_ frame: CapturedFrame) {
        lastTrackedFrame = frame
    }

    /// Distribute a captured frame to all enabled assistants
    /// - Parameter frame: The captured frame to analyze
    func distributeFrame(_ frame: CapturedFrame) {
        for (identifier, assistant) in assistants {
            // Backpressure: skip if this assistant is still analyzing a previous frame
            guard !isAnalyzing.contains(identifier) else { continue }

            let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime[identifier] ?? .distantPast)
            isAnalyzing.insert(identifier)

            Task { [weak self] in
                defer {
                    Task { @MainActor in
                        self?.isAnalyzing.remove(identifier)
                    }
                }

                // Check if assistant is enabled
                guard await assistant.isEnabled else { return }

                // Check if assistant wants to analyze this frame
                guard await assistant.shouldAnalyze(frameNumber: frame.frameNumber, timeSinceLastAnalysis: timeSinceLastAnalysis) else {
                    return
                }

                // Update last analysis time
                await MainActor.run {
                    self?.lastAnalysisTime[identifier] = Date()
                }

                // Analyze and handle result
                if let result = await assistant.analyze(frame: frame) {
                    await assistant.handleResult(result) { [weak self] type, data in
                        Task { @MainActor in
                            self?.sendEvent(type: type, data: data)
                        }
                    }
                }
            }
        }
    }

    /// Distribute a frame only to assistants that opted into receiving frames during the delay period.
    /// Used for time-sensitive detections like refocus tracking.
    func distributeFrameDuringDelay(_ frame: CapturedFrame) {
        for (identifier, assistant) in assistants {
            let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime[identifier] ?? .distantPast)

            Task {
                guard await assistant.isEnabled else { return }
                guard await assistant.needsFrameDuringDelay else { return }
                guard await assistant.shouldAnalyze(frameNumber: frame.frameNumber, timeSinceLastAnalysis: timeSinceLastAnalysis) else {
                    return
                }

                await MainActor.run {
                    lastAnalysisTime[identifier] = Date()
                }

                if let result = await assistant.analyze(frame: frame) {
                    await assistant.handleResult(result) { [weak self] type, data in
                        Task { @MainActor in
                            self?.sendEvent(type: type, data: data)
                        }
                    }
                }
            }
        }
    }

    // MARK: - App Switch Handling

    /// Notify all assistants of an app switch (legacy onAppSwitch callback).
    /// Context switch detection is handled separately via `checkContextSwitch`.
    func notifyAppSwitch(newApp: String) {
        for (_, assistant) in assistants {
            Task {
                await assistant.onAppSwitch(newApp: newApp)
            }
        }
    }

    /// Clear pending work for all assistants
    func clearAllPendingWork() {
        for (_, assistant) in assistants {
            Task {
                await assistant.clearPendingWork()
            }
        }
    }

    // MARK: - Lifecycle

    /// Stop all assistants
    func stopAll() {
        for (_, assistant) in assistants {
            Task {
                await assistant.stop()
            }
        }
    }

    /// Register the default set of assistants
    func registerDefaultAssistants() throws {
        // These will be added as we create the assistants
        // try register(FocusAssistant())
        // try register(TaskAssistant())
    }
}
