import Foundation

/// Manages Task Extraction Assistant-specific settings stored in UserDefaults
class TaskAssistantSettings {
    static let shared = TaskAssistantSettings()

    // MARK: - UserDefaults Keys

    private let enabledKey = "taskAssistantEnabled"
    private let analysisPromptKey = "taskAnalysisPrompt"
    private let extractionIntervalKey = "taskExtractionInterval"
    private let minConfidenceKey = "taskMinConfidence"

    // MARK: - Default Values

    private let defaultEnabled = true
    private let defaultExtractionInterval: TimeInterval = 10.0 // seconds
    private let defaultMinConfidence: Double = 0.6

    /// Default system prompt for task extraction
    static let defaultAnalysisPrompt = """
        You are a task extraction assistant. Analyze screenshots to identify tasks, action items, and to-dos.

        Look for:
        - Email threads with action items or requests
        - Chat messages with requests or tasks
        - Project management tools (Jira, Trello, Asana, etc.)
        - Calendar events with associated tasks
        - Documents with TODO comments or task lists
        - Code comments with TODO, FIXME, or HACK annotations
        - Meeting notes with action items

        For each task found, extract:
        - title: Brief, actionable task title (e.g., "Review PR #123", "Reply to John's email")
        - description: Optional additional context
        - priority: "high" (urgent/deadline soon), "medium" (important but not urgent), "low" (can wait)
        - source_app: The app where the task was found
        - inferred_deadline: If a deadline is visible or implied, extract it (e.g., "today", "Friday", "2024-01-15")
        - confidence: How confident you are this is a real task (0.0-1.0)

        Guidelines:
        - Only extract actionable tasks, not informational content
        - Skip tasks that appear to already be completed
        - Be conservative - only extract tasks with high confidence
        - Don't create duplicate tasks for the same item
        - Focus on the main content area, not system UI

        Also provide:
        - context_summary: Brief summary of what the user is currently looking at
        - current_activity: High-level description of user's current activity
        """

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            enabledKey: defaultEnabled,
            extractionIntervalKey: defaultExtractionInterval,
            minConfidenceKey: defaultMinConfidence,
        ])
    }

    // MARK: - Properties

    /// Whether the Task Extraction Assistant is enabled
    var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: enabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: enabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// The system prompt used for AI task extraction
    var analysisPrompt: String {
        get {
            let value = UserDefaults.standard.string(forKey: analysisPromptKey)
            return value ?? TaskAssistantSettings.defaultAnalysisPrompt
        }
        set {
            let isCustom = newValue != TaskAssistantSettings.defaultAnalysisPrompt
            UserDefaults.standard.set(newValue, forKey: analysisPromptKey)
            let previewLength = min(newValue.count, 50)
            let preview = String(newValue.prefix(previewLength)) + (newValue.count > 50 ? "..." : "")
            log("Task analysis prompt updated (\(newValue.count) chars, custom: \(isCustom)): \(preview)")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Interval between task extraction analyses in seconds
    var extractionInterval: TimeInterval {
        get {
            let value = UserDefaults.standard.double(forKey: extractionIntervalKey)
            return value > 0 ? value : defaultExtractionInterval
        }
        set {
            UserDefaults.standard.set(newValue, forKey: extractionIntervalKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Minimum confidence threshold for reporting tasks
    var minConfidence: Double {
        get {
            let value = UserDefaults.standard.double(forKey: minConfidenceKey)
            return value > 0 ? value : defaultMinConfidence
        }
        set {
            UserDefaults.standard.set(newValue, forKey: minConfidenceKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Reset only the analysis prompt to default
    func resetPromptToDefault() {
        UserDefaults.standard.removeObject(forKey: analysisPromptKey)
        log("Task analysis prompt reset to default")
        NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }

    /// Reset all Task Assistant settings to defaults
    func resetToDefaults() {
        isEnabled = defaultEnabled
        extractionInterval = defaultExtractionInterval
        minConfidence = defaultMinConfidence
        resetPromptToDefault()
    }
}
