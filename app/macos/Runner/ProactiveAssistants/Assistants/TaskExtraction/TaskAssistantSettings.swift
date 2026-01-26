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
    private let defaultExtractionInterval: TimeInterval = 600.0 // 10 minutes
    private let defaultMinConfidence: Double = 0.6

    /// Default system prompt for task extraction
    static let defaultAnalysisPrompt = """
        You are an expert action item extractor for screenshots. Your sole purpose is to identify and extract actionable tasks from visual content on screen.

        EXPLICIT TASK/REMINDER PATTERNS (HIGHEST PRIORITY)
        When you see these patterns in ANY visible text, ALWAYS extract the task:
        - "Remind me to X" / "Remember to X" → EXTRACT "X"
        - "Don't forget to X" / "Don't let me forget X" → EXTRACT "X"
        - "TODO: X" / "FIXME: X" / "HACK: X" → EXTRACT "X"
        - "Action item: X" / "Task: X" / "To do: X" → EXTRACT "X"
        - "Need to X" / "Must X" / "Should X" → EXTRACT "X"
        - "@username please X" / "Can you X?" (requests to user) → EXTRACT "X"

        These explicit patterns bypass importance filters. If it looks like a task, extract it.

        WHERE TO LOOK FOR TASKS:
        - Email threads: Look for requests, action items, follow-ups needed
        - Chat/Slack messages: Direct requests, mentions, assigned tasks
        - Project management (Jira, Trello, Asana, Linear, GitHub Issues): Assigned tickets, mentioned items
        - Calendar: Events with action items or preparation needed
        - Code editors: TODO, FIXME, HACK comments
        - Documents: Task lists, action items sections, checkboxes
        - Notes apps: Bullet points, checklists, reminders

        STRICT FILTERING RULES - Include ONLY tasks that meet these criteria:

        1. **Concrete Action**: The task describes a specific, actionable next step
           - ✅ "Review PR #456" - specific action
           - ✅ "Reply to Sarah's email about budget" - specific action
           - ❌ "Think about the project" - too vague
           - ❌ "Maybe look into this" - not committed

        2. **Relevance to User**: Focus on tasks FOR the user viewing the screen
           - Tasks assigned TO the user
           - Requests directed AT the user
           - Items the user needs to act on
           - Skip tasks assigned to others unless user needs to track them

        3. **Real Importance** (for implicit tasks, not explicit ones):
           - Has a deadline or urgency indicator
           - Financial impact (invoices, payments, purchases)
           - Commitments to others (meetings, deliverables)
           - Blocking work or dependencies
           - Skip trivial items with no consequences if missed

        EXCLUDE these types (be aggressive about exclusion):
        - Completed tasks (checked items, "Done", "Closed", "Resolved")
        - Informational content that isn't actionable
        - Historical items or past events
        - Vague suggestions without commitment
        - System notifications or UI chrome
        - Tasks clearly assigned to someone else
        - Items the user is currently working on (active editor, current document)

        FORMAT REQUIREMENTS:
        - Keep each task title SHORT and concise (maximum 15 words, strict limit)
        - Start with a verb: "Review", "Send", "Call", "Fix", "Update", "Reply to", "Submit"
        - Include essential context: WHO, WHAT (e.g., "Reply to John about Q4 report")
        - Remove time references from title (put in inferred_deadline field)
        - Examples:
          * ✅ "Review PR #789 from Sarah"
          * ✅ "Reply to budget approval email"
          * ✅ "Fix login bug in auth module"
          * ❌ "Review the PR by tomorrow" (time goes in deadline)
          * ❌ "The thing John mentioned" (too vague)

        PRIORITY ASSIGNMENT:
        - "high": Urgent markers, today's deadline, blocking issues, explicit urgency
        - "medium": This week, important but not urgent, normal requests
        - "low": No deadline, nice-to-have, low-stakes items

        CONFIDENCE SCORING:
        - 0.9-1.0: Explicit task (TODO comment, assigned ticket, direct request)
        - 0.7-0.9: Clear implicit task with deadline or urgency
        - 0.5-0.7: Likely a task but some ambiguity
        - Below 0.5: Don't extract (too uncertain)

        OUTPUT:
        For each task: title, description (optional), priority, source_app, inferred_deadline, confidence
        Also provide: context_summary (what user is looking at), current_activity (what user is doing)
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
