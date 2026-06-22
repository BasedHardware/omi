import Foundation

/// Model-visible capability docs for Omi desktop surfaces.
///
/// This intentionally does not own provider-specific tool schemas yet: pi-mono,
/// ACP MCP, and realtime use different schema shapes. Keep capability semantics
/// here, then project them into each surface prompt so tool docs do not drift.
enum DesktopCapabilityRegistry {
  enum Surface {
    case desktopChat
    case realtimeHub
  }

  enum LatencyClass: String {
    case fastLocal = "fast local"
    case fastNetwork = "fast network"
    case asyncBackground = "async background"
  }

  struct Capability {
    let toolName: String
    let title: String
    let latency: LatencyClass
    let surfaces: Set<Surface>
    let summary: String
    let bullets: [String]

    func supports(_ surface: Surface) -> Bool {
      surfaces.contains(surface)
    }
  }

  static let capabilities: [Capability] = [
    Capability(
      toolName: "execute_sql",
      title: "Execute SQL",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Run SQL on the local omi.db database for structured local data.",
      bullets: [
        "Supports SELECT, INSERT, UPDATE, DELETE.",
        "Use for personal facts, app usage stats, time queries, task lookups, conversations, memories, aggregations, and anything structured.",
        "Supports FTS5 MATCH queries for keyword search; see the schema footer for FTS tables and patterns.",
        "SELECT queries auto-limit to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE are blocked.",
        "Prefer semantic_search for fuzzy screen-history questions and backend task tools for creating/updating tasks."
      ]),
    Capability(
      toolName: "semantic_search",
      title: "Semantic Search",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Vector similarity search on the user's screen history.",
      bullets: [
        "Use for fuzzy/conceptual questions about what the user saw, read, or worked on where exact SQL keywords will not work.",
        "Examples: \"reading about machine learning\", \"working on design mockups\".",
        "Parameters: query (required), days (default 7), app_filter (optional)."
      ]),
    Capability(
      toolName: "search_screen_history",
      title: "Search Screen History",
      latency: .fastLocal,
      surfaces: [.realtimeHub],
      summary: "Search the user's on-screen history by meaning.",
      bullets: [
        "Use for what the user saw, read, or worked on. Speak a short summary of the result."
      ]),
    Capability(
      toolName: "get_daily_recap",
      title: "Daily Recap",
      latency: .fastLocal,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Pre-formatted activity recap: apps, conversations, tasks, focus, memories, and observations.",
      bullets: [
        "Use for what the user did today/yesterday/this week; it is faster than composing many SQL queries.",
        "Parameters: days_ago (0=today, 1=yesterday, 7=past week; default 1)."
      ]),
    Capability(
      toolName: "search_tasks",
      title: "Search Tasks",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Vector similarity search on tasks (action_items + staged_tasks).",
      bullets: [
        "Use for finding tasks by meaning, not exact keywords, e.g. \"find tasks about shopping\".",
        "Examples: \"tasks about shopping\", \"anything related to the presentation\".",
        "Parameters: query (required), include_completed (default false).",
        "More reliable than hand-writing MATCH queries for task search."
      ]),
    Capability(
      toolName: "get_tasks",
      title: "Get Tasks",
      latency: .fastLocal,
      surfaces: [.realtimeHub],
      summary: "Read the user's overdue and due-today tasks locally.",
      bullets: [
        "Use for plain voice questions like what are my tasks, what's due today, or what's on my list.",
        "Prefer get_action_items for completed tasks, date ranges, or the full list."
      ]),
    Capability(
      toolName: "get_action_items",
      title: "Get Action Items",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Retrieve the user's tasks with optional completion and due-date filters.",
      bullets: [
        "Use for completed tasks, date ranges, or the full task list.",
        "For voice, prefer get_tasks for plain overdue/due-today questions."
      ]),
    Capability(
      toolName: "create_action_item",
      title: "Create Action Item",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Create a new task, to-do, or reminder.",
      bullets: [
        "Use when the user explicitly asks to add something to their list.",
        "Pass a concise description and due_at only when the user gave a time."
      ]),
    Capability(
      toolName: "update_action_item",
      title: "Update Action Item",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Update an existing task's status, description, or due date.",
      bullets: [
        "Find the task first, then update the matching id. Do not guess task ids."
      ]),
    Capability(
      toolName: "complete_task",
      title: "Complete Task",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Toggle a task's completion status by backendId.",
      bullets: [
        "Use after finding the task with execute_sql or search_tasks."
      ]),
    Capability(
      toolName: "delete_task",
      title: "Delete Task",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Delete a task permanently by backendId.",
      bullets: [
        "Use after finding the task with execute_sql or search_tasks."
      ]),
    Capability(
      toolName: "save_knowledge_graph",
      title: "Save Knowledge Graph",
      latency: .fastLocal,
      surfaces: [.desktopChat],
      summary: "Save a knowledge graph of entities and relationships extracted from the user's data.",
      bullets: [
        "Parameters: nodes (array of {id, label, node_type, aliases}), edges (array of {source_id, target_id, label}).",
        "node_type must be one of: person, organization, place, thing, concept.",
        "Use when exploring the user's files during onboarding to build their knowledge graph.",
        "Deduplication is handled automatically; provide all entities you find."
      ]),
    Capability(
      toolName: "get_conversations",
      title: "Get Conversations",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Retrieve conversations by recency or date range.",
      bullets: [
        "Use for latest/recent conversations and time-based conversation retrieval.",
        "For voice, this returns summaries only and should be spoken briefly."
      ]),
    Capability(
      toolName: "search_conversations",
      title: "Search Conversations",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Semantic search across the user's past conversations.",
      bullets: [
        "Use for specific topics, decisions, or events discussed in conversations."
      ]),
    Capability(
      toolName: "get_memories",
      title: "Get Memories",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Retrieve stored facts, preferences, habits, people, and background about the user.",
      bullets: [
        "Use for broad 'what do you know about me' questions or personal facts."
      ]),
    Capability(
      toolName: "search_memories",
      title: "Search Memories",
      latency: .fastNetwork,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Semantic search across user memories.",
      bullets: [
        "Use for a specific personal fact that is not already in the visible user context."
      ]),
    Capability(
      toolName: "get_task_agent_status",
      title: "Task Agent Status",
      latency: .fastLocal,
      surfaces: [.desktopChat, .realtimeHub],
      summary: "Inspect Omi's local task-chat agents/subagents.",
      bullets: [
        "Use when the user asks about your subagents, task agents, background agents, running agents, errors, or timeouts.",
        "Call this before claiming there are no subagents or before diagnosing a task-agent timeout."
      ]),
    Capability(
      toolName: "spawn_agent",
      title: "Spawn Agent",
      latency: .asyncBackground,
      surfaces: [.realtimeHub],
      summary: "Hand multi-step work to a background agent and return immediately.",
      bullets: [
        "Use for acting in other apps or multi-step work. This is the only realtime tool that starts a background agent."
      ]),
    Capability(
      toolName: "ask_higher_model",
      title: "Ask Higher Model",
      latency: .fastNetwork,
      surfaces: [.realtimeHub],
      summary: "Get a second opinion from the larger model when the user pushes back or current facts are needed.",
      bullets: [
        "Use sparingly; answer simple or creative requests yourself."
      ]),
    Capability(
      toolName: "screenshot",
      title: "Screenshot",
      latency: .fastLocal,
      surfaces: [.realtimeHub],
      summary: "Capture the user's current screen.",
      bullets: [
        "Use when the user asks about what is on screen."
      ]),
    Capability(
      toolName: "point_click",
      title: "Point Click",
      latency: .fastLocal,
      surfaces: [.realtimeHub],
      summary: "Click at on-screen pixel coordinates.",
      bullets: [
        "Use only when the user clearly asks you to click something."
      ])
  ]

  static func capabilities(for surface: Surface) -> [Capability] {
    capabilities.filter { $0.supports(surface) }
  }

  static var desktopToolPrompt: String {
    let docs = capabilities(for: .desktopChat)
      .map(toolDoc)
      .joined(separator: "\n\n")
    return """
    These Omi data/status tools are documented for desktop chat. Use them before answering when the question depends on the user's personal data, tasks, conversations, memories, app/screen activity, or task-agent state. Do not guess when you can look it up. Do not call tools for simple chit-chat or general knowledge that does not depend on the user's data.

    \(docs)

    **Task-Agent Awareness:**
    - Omi can run local task-chat agents/subagents in the desktop task panel.
    - If the user says "your subagents", "task agents", "running agents", "background agents", or mentions task-agent errors/timeouts, do NOT deny that you have subagents.
    - Call get_task_agent_status before answering those questions.

    **CRITICAL -- When to use tools proactively:**
    The <user_facts> section above only contains a SAMPLE of {user_name}'s memories. The full set is available through the memory tools and local database.
    For ANY personal question (age, preferences, relationships, habits, past events, "what do you know about me", etc.):
    1. FIRST check <user_facts> — if the answer is there, use it directly.
    2. If NOT in <user_facts>, use get_memories/search_memories or execute_sql over memories before saying you don't know.
    3. For questions about past events or conversations, query search_conversations/get_conversations or transcription_sessions/transcription_segments.
    NEVER say "I don't know" or "I don't have that info" without checking first.

    **When to use which tool:**
    - Personal facts/preferences -> get_memories, search_memories, or execute_sql over memories.
    - Specific past conversations/events -> search_conversations or get_conversations.
    - What the user did today/yesterday/this week -> get_daily_recap.
    - App usage counts or exact local stats -> execute_sql.
    - Fuzzy screen-history questions -> semantic_search.
    - Find tasks by meaning -> search_tasks.
    - Create/update tasks -> create_action_item/update_action_item when available; use execute_sql only for exact local inspection or legacy local writes.
    - Complete/delete local tasks -> find the backendId, then complete_task/delete_task.
    - Subagents/task-agent status -> get_task_agent_status.
    - Onboarding knowledge graph -> save_knowledge_graph.
    """
  }

  static var realtimeSelfModelPrompt: String {
    """
    Omi capability model:
    - You can read Omi data quickly with fast tools: tasks, memories, conversations, daily recaps, and screen history.
    - You can inspect your local task-chat agents/subagents with get_task_agent_status. If the user asks about your subagents, background agents, running agents, or task-agent errors/timeouts, call it before answering.
    - You can start a background agent with spawn_agent for multi-step work or acting in the user's other apps. Merely saying you will start an agent does not start one; emitting spawn_agent does.
    """
  }

  static var desktopToolNames: [String] {
    capabilities(for: .desktopChat).map(\.toolName)
  }

  static var realtimeToolNames: [String] {
    capabilities(for: .realtimeHub).map(\.toolName)
  }

  private static func toolDoc(_ capability: Capability) -> String {
    let bullets = capability.bullets.map { "- \($0)" }.joined(separator: "\n")
    return """
    **\(capability.toolName)** (\(capability.latency.rawValue)): \(capability.summary)
    \(bullets)
    """
  }
}
