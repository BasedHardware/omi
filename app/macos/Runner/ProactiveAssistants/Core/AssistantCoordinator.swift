import Foundation

/// Coordinates all proactive assistants, distributing frames and managing lifecycle
@MainActor
class AssistantCoordinator {
    static let shared = AssistantCoordinator()

    // MARK: - Properties

    private var assistants: [String: any ProactiveAssistant] = [:]
    private var lastAnalysisTime: [String: Date] = [:]
    private var eventCallback: ((String, [String: Any]) -> Void)?

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

    // MARK: - Frame Distribution

    /// Distribute a captured frame to all enabled assistants
    /// - Parameter frame: The captured frame to analyze
    func distributeFrame(_ frame: CapturedFrame) {
        for (identifier, assistant) in assistants {
            let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime[identifier] ?? .distantPast)

            Task {
                // Check if assistant is enabled
                guard await assistant.isEnabled else { return }

                // Check if assistant wants to analyze this frame
                guard await assistant.shouldAnalyze(frameNumber: frame.frameNumber, timeSinceLastAnalysis: timeSinceLastAnalysis) else {
                    return
                }

                // Update last analysis time
                await MainActor.run {
                    lastAnalysisTime[identifier] = Date()
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

    // MARK: - App Switch Handling

    /// Notify all assistants of an app switch
    /// - Parameter newApp: Name of the newly active application
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
