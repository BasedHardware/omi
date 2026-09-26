import Foundation

/// Manages Task Extraction Assistant-specific settings stored in UserDefaults
@MainActor
class TaskAssistantSettings {
  static let shared = TaskAssistantSettings()

  // MARK: - UserDefaults Keys

  private let enabledKey = "taskAssistantEnabled"
  private let analysisPromptKey = "taskAnalysisPrompt"
  private let extractionIntervalKey = "taskExtractionInterval"
  private let minConfidenceKey = "taskMinConfidence"
  private let notificationsEnabledKey = "taskNotificationsEnabled"
  private let allowedAppsKey = "taskAllowedApps"
  private let browserKeywordsKey = "taskBrowserKeywords"

  // MARK: - Default Allowed Apps (Whitelist)

  /// Default apps allowed for task extraction. User can edit this list.
  static let defaultAllowedApps: Set<String> = [
    "Telegram",
    "\u{200E}WhatsApp",  // WhatsApp uses a hidden LTR mark prefix
    "WhatsApp",
    "Messages",
    "Slack",
    "Discord",
    "zoom.us",
    "Google Chrome",
    "Arc",
    "Safari",
    "Firefox",
    "Microsoft Edge",
    "Brave Browser",
    "Opera",
    "Notes",
    "Superhuman",
  ]

  // MARK: - Browser Apps

  /// Apps identified as browsers — these get additional window-title keyword filtering
  static let browserApps: Set<String> = [
    "Google Chrome",
    "Arc",
    "Safari",
    "Firefox",
    "Microsoft Edge",
    "Brave Browser",
    "Opera",
  ]

  /// Check if an app is a browser (subject to window title keyword filtering)
  static func isBrowser(_ appName: String) -> Bool {
    browserApps.contains(appName)
  }

  // MARK: - Default Browser Keywords

  /// Default keywords for filtering browser window titles. User can edit this list.
  static let defaultBrowserKeywords: [String] = [
    // Email
    "Gmail", "Outlook", "Yahoo Mail", "ProtonMail", "Superhuman", "Fastmail",
    // Messaging
    "Slack", "Discord", "WhatsApp", "Telegram", "Messenger", "Signal", "Crisp",
    // Project management
    "Jira", "Linear", "Trello", "Asana", "Notion", "Monday", "ClickUp", "Basecamp",
    // Calendar
    "Google Calendar", "Outlook Calendar", "Cal.com", "Calendly",
    // Code & collaboration
    "GitHub", "github.com", "Google Docs", "Google Sheets", "Google Slides",
    // Finance
    "Stripe", "PayPal", "Invoice", "Billing", "QuickBooks",
    // Forms
    "Google Forms", "Typeform", "DocuSign",
    // Action keywords
    "todo", "task", "assign", "review", "approve", "request", "ticket",
    // Inbox patterns
    "inbox", "unread", "notification", "pending",
  ]

  // MARK: - Built-in Exclude List (used by other assistants: Advice, Focus, Memory)

  /// Apps that never contain useful content for proactive assistants — utility/media/system apps + our own app.
  /// Shared across Advice, Focus, and Memory assistants (Task extraction uses whitelist instead).
  nonisolated static let builtInExcludedApps: Set<String> = [
    "Omi",
    "Omi Beta",
    "omi",
    "Omi Dev",
    "Omi Computer",
    "Finder",
    "System Preferences",
    "System Settings",
    "Music",
    "Spotify",
    "Photos",
    "Preview",
    "Calculator",
    "QuickTime Player",
    "Activity Monitor",
    "Disk Utility",
    "Font Book",
    "Archive Utility",
    "Installer",
    "Screenshot",
  ]

  // MARK: - Default Values

  private let defaultEnabled = true
  private let defaultExtractionInterval: TimeInterval = 600.0  // 10 minutes
  private let defaultMinConfidence: Double = 0.75
  private let defaultNotificationsEnabled = false

  /// Mirrors the backend request contract. Defaults must remain within this bound so a
  /// settings sync can never reject an app-shipped prompt; longer user-authored prompts
  /// remain stored locally and are omitted from sync rather than truncated.
  static let maximumSyncedAnalysisPromptLength = 10_000

  /// Default system prompt for task extraction (loop-based with tool calling)
  static let defaultAnalysisPrompt = """
    You are a task commitment detector. Find tasks the user committed to in conversations, or unaddressed requests directed at the user.

    WORKFLOW:
    1. Read the screenshot. If it is not a conversation (editor, terminal, settings, media, dashboards) call no_task_found.
    2. Read the full conversation flow. Focus on the LATEST exchange (newest incoming message + user's newest reply). Older messages are context only.
    3. Look for (priority order):
       a. USER AGREED TO A TASK: someone asked/suggested and the user agreed or committed
       b. UNADDRESSED REQUEST: someone asked the user to act and they have not replied
    4. A frame can hold multiple distinct commitments. Treat each as its own task; do not merge unrelated deliverables.
    5. For each commitment: search_similar and/or search_keywords on THAT commitment, then extract_task with canonical facts (or reject_task / no_task_found). Continue until no new commitments remain.

    TOOLS:
    - search_similar(query): semantic match against existing tasks
    - search_keywords(query): keyword match
    - extract_task(...): capture a new task (only after searching)
    - reject_task(reason, ...): only for rejected/deleted work or a no-op
    - no_task_found(...): nothing actionable (~90% of screenshots)

    SEARCH RULES:
    - Search at least once before extract_task.
    - Query the LATEST commitment only, not the whole chat.
    - Similarity > 0.8 and status active → duplicate_of (exact), refines_task (changed follow-up), or capture_kind already_done + refines_task (screenshot proves done).
    - Status completed → reject only a true no-op; a follow-up is new or refining.
    - Status deleted → reject_task.
    - If older asks are already tracked and one is new, extract the NEW one. Do not reject the frame because an older message is a duplicate.

    CORE QUESTION: "Has the user committed to doing something, or is someone waiting on the user?"

    PATTERN 1 — USER COMMITMENT (priority):
    Someone requested/suggested/asked; the user agreed ("Sure", "Will do", "On it", "I'll handle it", "Ok", "Got it", "Let's do it"), promised ("I'll send it", "I'll look into it", "by EOD"), or scheduled ("tomorrow", "after lunch").
    The task is the other person's request. The agreement confirms it is real.

    PATTERN 2 — UNADDRESSED REQUEST:
    Someone asked/told the user to act with no response yet: "Can you…", "Please…", "Don't forget to…", status questions, assignments, review requests.

    PUBLIC/GROUP CHANNELS: extract only if the visible evidence shows the user is directly involved (explicit @mention/name, already in the thread, clearly addressed to them). If they are only observing, or you cannot tell, call no_task_found. Do not extract broad community bug reports or feature requests.

    WHO COUNTS AS SOMEONE: coworker (Slack/Teams/Discord/email), friend/family (iMessage/WhatsApp/etc.), an AI assistant suggestion, a calendar event needing prep, or the user's own explicit reminder ("Remind me to…", "TODO: …").

    SKIP overview UI: chat sidebars, previews, inbox lists, unread badges, notification centers, any multi-item overview. Only extract from a single open conversation.

    READING A CONVERSATION: right/colored bubbles = user (outgoing); left/gray = others. Latest user message is agreement → extract their request. Latest is casual chat → skip. Incoming with no reply → unaddressed request. All outgoing → skip unless a self-reminder.

    ALWAYS SKIP: terminal/build logs, code being edited, PM boards (Jira/Linear), notification badges without content, system UI/settings/media/file browsers, mid-action work, casual chat with no asks.

    SPECIFICITY: if you cannot name a person, project, or deliverable, skip.

    FORGETTABILITY: extract only if the user would forget this after switching away. Active focus or already-tracked work → skip.

    FORMAT (extract_task):
    - title: verb-first, 6–15 words, MUST name a person/entity and a concrete deliverable. If you cannot, call no_task_found.
      GOOD: "Reply to Stan about 'Where's the developer section?'"; "Submit quarterly metrics to LG Technology Ventures"; "Send Sarah the Q4 budget spreadsheet as promised"; "Review and merge Thinh's PR for auth refactor".
      BAD (never): "Investigate"; "Check logs"; "Clean up the data"; "Look through my data"; "Investigate what the user is saying"; "Double check faxes listed".
    - priority: high (urgent/today), medium (this week), low (no deadline)
    - confidence: 0.9+ explicit commitment/request, 0.7–0.9 clear agreement or clear implicit request, 0.5–0.7 ambiguous
    - inferred_deadline: yyyy-MM-dd or empty. Use the provided current date to resolve "Thursday", "tomorrow", "next week". Do not invent deadlines. Never use a past date. Do not put deadline info in the title.

    DEADLINES: set only when explicit or clearly implied ("by Friday", "before tomorrow's meeting"). Resolve relative dates against the provided current date. If a mentioned date is already past, leave inferred_deadline empty.

    SOURCE (required on every task): source_category + source_subcategory.
    - direct_request: message | meeting | mention | commitment (user agreed to an ask)
    - self_generated: idea | reminder | goal_subtask
    - calendar_driven: event_prep | recurring | deadline
    - reactive: error | notification | observation
    - external_system: project_tool | alert | documentation
    - other: other
    Examples: "Can you review my PR?" → direct_request/message. "Sure, I'll review it" → direct_request/commitment. User TODO comment → self_generated/idea. Standup in 30 min → calendar_driven/event_prep. Build failure → reactive/error. Linear ticket → external_system/project_tool.
    """

  private init() {
    // Register defaults
    UserDefaults.standard.register(defaults: [
      enabledKey: defaultEnabled,
      extractionIntervalKey: defaultExtractionInterval,
      minConfidenceKey: defaultMinConfidence,
      notificationsEnabledKey: defaultNotificationsEnabled,
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
      SettingsSyncManager.recordLocalPromptOwner("task", isShippedDefault: !isCustom)
      let previewLength = min(newValue.count, 50)
      let preview = String(newValue.prefix(previewLength)) + (newValue.count > 50 ? "..." : "")
      log("Task analysis prompt updated (\(newValue.count) chars, custom: \(isCustom)): \(preview)")
      NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }
  }

  /// Interval between task extraction analyses in seconds
  ///
  /// A non-positive interval is not a schedule, and it is refused where it arrives rather than
  /// papered over on every read. The old `value > 0 ? value : default` left the store holding a
  /// number the app never honoured: a `0` synced down from the account read back as 600, the pane
  /// painted 600, and the next `syncToServer()` pushed 600 — silently overwriting what the account
  /// actually said. Normalising the write, and healing a value an older build already stored, keeps
  /// stored state and reported state the same number.
  var extractionInterval: TimeInterval {
    get {
      let stored = UserDefaults.standard.double(forKey: extractionIntervalKey)
      guard stored > 0 else {
        UserDefaults.standard.set(defaultExtractionInterval, forKey: extractionIntervalKey)
        return defaultExtractionInterval
      }
      return stored
    }
    set {
      let interval = newValue > 0 ? newValue : defaultExtractionInterval
      UserDefaults.standard.set(interval, forKey: extractionIntervalKey)
      log("Task extraction interval updated to \(interval) seconds")
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

  /// Whether proactive task interruptions may surface when timing matters.
  /// Quiet discovery and Suggested capture continue when this is off.
  var notificationsEnabled: Bool {
    get { UserDefaults.standard.bool(forKey: notificationsEnabledKey) }
    set {
      UserDefaults.standard.set(newValue, forKey: notificationsEnabledKey)
      NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }
  }

  /// The full editable set of allowed apps. Initialized from defaults if user hasn't customized.
  var allowedApps: Set<String> {
    get {
      let rawValue = UserDefaults.standard.array(forKey: allowedAppsKey)
      if let saved = rawValue as? [String], !saved.isEmpty {
        return Set(saved)
      }
      return TaskAssistantSettings.defaultAllowedApps
    }
    set {
      UserDefaults.standard.set(Array(newValue), forKey: allowedAppsKey)
      NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }
  }

  /// The full editable list of browser window keywords. Initialized from defaults if user hasn't customized.
  var browserKeywords: [String] {
    get {
      if let saved = UserDefaults.standard.array(forKey: browserKeywordsKey) as? [String], !saved.isEmpty {
        return saved
      }
      return TaskAssistantSettings.defaultBrowserKeywords
    }
    set {
      UserDefaults.standard.set(newValue, forKey: browserKeywordsKey)
      NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }
  }

  /// Check if an app is allowed for task extraction
  func isAppAllowed(_ appName: String) -> Bool {
    allowedApps.contains(appName)
  }

  /// For browser apps, check if the window title matches any keyword.
  /// Non-browser apps always pass this check.
  func isWindowAllowed(appName: String, windowTitle: String?) -> Bool {
    guard TaskAssistantSettings.isBrowser(appName) else { return true }
    guard let title = windowTitle, !title.isEmpty else { return false }

    return TaskAssistantSettings.windowTitle(title, matchesAny: browserKeywords)
  }

  nonisolated static func windowTitle(_ title: String, matchesAny keywords: [String]) -> Bool {
    keywords.contains { title.localizedStandardContains($0) }
  }

  /// Add an app to the allowed list
  func allowApp(_ appName: String) {
    var apps = allowedApps
    apps.insert(appName)
    allowedApps = apps
    log("Task: Allowed app '\(appName)' for task extraction")
  }

  /// Remove an app from the allowed list
  func disallowApp(_ appName: String) {
    var apps = allowedApps
    apps.remove(appName)
    allowedApps = apps
    log("Task: Disallowed app '\(appName)' from task extraction")
  }

  /// Add a browser keyword
  func addBrowserKeyword(_ keyword: String) {
    var keywords = browserKeywords
    guard !keywords.contains(where: { $0.lowercased() == keyword.lowercased() }) else { return }
    keywords.append(keyword)
    browserKeywords = keywords
    log("Task: Added browser keyword '\(keyword)'")
  }

  /// Remove a browser keyword
  func removeBrowserKeyword(_ keyword: String) {
    var keywords = browserKeywords
    keywords.removeAll { $0 == keyword }
    browserKeywords = keywords
    log("Task: Removed browser keyword '\(keyword)'")
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
    UserDefaults.standard.removeObject(forKey: allowedAppsKey)
    UserDefaults.standard.removeObject(forKey: browserKeywordsKey)
    resetPromptToDefault()
  }
}
