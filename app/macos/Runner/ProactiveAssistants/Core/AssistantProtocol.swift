import Foundation

/// Result from an assistant's analysis
protocol AssistantResult {
    /// Convert result to dictionary for Flutter communication
    func toDictionary() -> [String: Any]
}

/// Protocol that all proactive assistants must implement
protocol ProactiveAssistant: Actor {
    /// Unique identifier for this assistant (e.g., "focus", "task-extraction")
    var identifier: String { get }

    /// Human-readable name for this assistant
    var displayName: String { get }

    /// Whether this assistant is currently enabled
    var isEnabled: Bool { get async }

    /// Determines if this assistant should analyze the given frame
    /// - Parameters:
    ///   - frameNumber: The sequential frame number
    ///   - timeSinceLastAnalysis: Time elapsed since the last analysis
    /// - Returns: True if this frame should be analyzed
    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool

    /// Analyze a captured frame
    /// - Parameter frame: The captured frame to analyze
    /// - Returns: Analysis result, or nil if analysis should be skipped
    func analyze(frame: CapturedFrame) async -> AssistantResult?

    /// Handle the analysis result (notifications, events, etc.)
    /// - Parameters:
    ///   - result: The analysis result to handle
    ///   - sendEvent: Callback to send events to Flutter
    func handleResult(_ result: AssistantResult, sendEvent: @escaping (String, [String: Any]) -> Void) async

    /// Called when the active application changes
    /// - Parameter newApp: Name of the newly active application
    func onAppSwitch(newApp: String) async

    /// Clear any pending work (e.g., queued frames)
    func clearPendingWork() async

    /// Stop the assistant and clean up resources
    func stop() async
}

/// Extension with default implementations
extension ProactiveAssistant {
    /// Default: analyze every frame
    func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool {
        return true
    }

    /// Default: no-op for app switch
    func onAppSwitch(newApp: String) async {}

    /// Default: no-op for clearing pending work
    func clearPendingWork() async {}
}
