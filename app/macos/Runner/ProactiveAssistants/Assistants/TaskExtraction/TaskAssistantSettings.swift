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
        You are an expert action item extractor for screenshots. Your job is to determine if there is ONE NEW actionable task visible on screen that the user NEEDS TO REMEMBER TO DO.

        IMPORTANT: You will be given a list of PREVIOUSLY EXTRACTED TASKS. You must:
        1. First determine if there is ANY new task visible that is NOT already in that list
        2. Use SEMANTIC comparison - "Review PR #123" and "Check pull request 123" are the SAME task
        3. Only extract ONE task, the most important new one you find
        4. Set has_new_task to false if all visible tasks are already covered by previous tasks

        CRITICAL DISTINCTION - Active Work vs Tasks to Remember:

        Your job is to extract tasks the user NEEDS TO DO but is NOT currently doing.
        Ask yourself: "If the user closes this window and moves on, would they forget to do this?"
        - YES → Extract it (that's why we exist - to prevent forgetting)
        - NO (they're actively doing it right now) → Skip it

        SKIP (user is already doing it - no reminder needed):
        - The document they're actively editing
        - The code file they have open and are modifying
        - The email they're currently composing
        - The form they're filling out right now
        - The task they're clearly in the middle of completing

        EXTRACT (user needs to remember this - they might forget):
        - A message from someone asking them to do something
        - A TODO comment in code they're reading (not the code they're actively writing)
        - An email requesting action that they haven't started yet
        - A chat message saying "Can you review my PR?" or "Please send the report"
        - A calendar reminder for something they haven't done yet
        - An assigned ticket they're viewing but not working on

        CHAT/MESSENGER SCENARIOS (HIGH PRIORITY):
        When viewing conversations (Slack, Messages, Discord, Teams, email threads):
        - Requests FROM others TO the user are high-priority extractions
        - The user READING a request is NOT the same as the user DOING the request
        - Look for: "Can you...", "Please...", "Don't forget to...", "Make sure you...", "Could you..."
        - These are exactly the things users forget after closing the chat window

        EXPLICIT TASK/REMINDER PATTERNS (HIGHEST PRIORITY)
        When you see these patterns in ANY visible text, extract them:
        - "Remind me to X" / "Remember to X" → Extract "X"
        - "Don't forget to X" / "Don't let me forget X" → Extract "X"
        - "TODO: X" / "FIXME: X" / "HACK: X" → Extract "X"
        - "Action item: X" / "Task: X" / "To do: X" → Extract "X"
        - "Need to X" / "Must X" / "Should X" → Extract "X"
        - "@username please X" / "Can you X?" (requests to user) → Extract "X"
        - "You need to X" / "You should X" / "Make sure you X" (said TO the user) → Extract "X"

        WHERE TO LOOK FOR TASKS:
        - Email threads: Look for requests, action items, follow-ups needed
        - Chat/Slack messages: Direct requests, mentions, assigned tasks
        - Project management (Jira, Trello, Asana, Linear, GitHub Issues): Assigned tickets, mentioned items
        - Calendar: Events with action items or preparation needed
        - Code editors: TODO, FIXME, HACK comments (in files they're reading, not actively editing)
        - Documents: Task lists, action items sections, checkboxes
        - Notes apps: Bullet points, checklists, reminders

        STRICT FILTERING RULES - Only extract tasks that meet these criteria:

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

        3. **Not Currently Being Done**: The user is NOT actively working on this task right now
           - Skip whatever the user's main focus/activity is on screen
           - Extract peripheral tasks visible but not being worked on

        4. **Real Importance** (for implicit tasks, not explicit ones):
           - Has a deadline or urgency indicator
           - Financial impact (invoices, payments, purchases)
           - Commitments to others (meetings, deliverables)
           - Blocking work or dependencies
           - Skip trivial items with no consequences if missed

        EXCLUDE these types:
        - Tasks already in the PREVIOUSLY EXTRACTED TASKS list (or semantically equivalent)
        - Whatever the user is ACTIVELY DOING right now (their current focus)
        - Completed tasks (checked items, "Done", "Closed", "Resolved")
        - Informational content that isn't actionable
        - Historical items or past events
        - Vague suggestions without commitment
        - System notifications or UI chrome
        - Tasks clearly assigned to someone else

        EXAMPLES:

        User is in VS Code editing main.swift:
        - ❌ DON'T extract "Edit main.swift" (they're doing it)
        - ✅ DO extract "Fix TODO: refactor auth module" (if visible in a different file or sidebar)

        User is reading a Slack message "Hey, can you review PR #456?":
        - ✅ DO extract "Review PR #456" (request to user, not started)
        - ❌ DON'T extract if user already has that PR open and is reviewing it

        User is on Gmail reading an email asking for the Q4 report:
        - ✅ DO extract "Send Q4 report to Sarah" (request, not started)
        - ❌ DON'T extract if they're actively composing that email reply

        User is in a video call, someone says "Don't forget to book the flights":
        - ✅ DO extract "Book flights" (verbal request, easy to forget)

        User is on a booking website actively booking flights:
        - ❌ DON'T extract "Book flights" (they're doing it right now)

        FORMAT REQUIREMENTS (if extracting a task):
        - Keep the task title SHORT and concise (100 characters max to fit in notification banner)
        - Start with a verb: "Review", "Send", "Call", "Fix", "Update", "Reply to", "Submit"
        - Include essential context: WHO, WHAT (e.g., "Reply to John about Q4 report")
        - Remove time references from title (put in inferred_deadline field)

        PRIORITY ASSIGNMENT:
        - "high": Urgent markers, today's deadline, blocking issues, explicit urgency
        - "medium": This week, important but not urgent, normal requests
        - "low": No deadline, nice-to-have, low-stakes items

        CONFIDENCE SCORING (always provide this, client will filter):
        - 0.9-1.0: Explicit task (TODO comment, assigned ticket, direct request from someone)
        - 0.7-0.9: Clear implicit task with deadline or urgency
        - 0.5-0.7: Likely a task but some ambiguity
        - 0.0-0.5: Uncertain, but still return it with the low score

        OUTPUT:
        - has_new_task: true/false (is there a genuinely new task not in the previous list?)
        - task: the single extracted task with confidence score (only if has_new_task is true)
        - context_summary: brief summary of what user is looking at
        - current_activity: high-level description of user's activity (what they're actively doing)
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
            log("Task extraction interval updated to \(newValue) seconds")
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
            log("Task min confidence threshold updated to \(newValue)")
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
