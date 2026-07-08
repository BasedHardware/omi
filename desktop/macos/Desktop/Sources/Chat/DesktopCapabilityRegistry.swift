import Foundation

/// Model-visible capability docs for Omi desktop surfaces.
/// Capability data is generated from the canonical TypeScript tool manifest.
enum DesktopCapabilityRegistry {
  typealias Surface = GeneratedToolCapabilities.Surface
  typealias LatencyClass = GeneratedToolCapabilities.LatencyClass
  typealias Capability = GeneratedToolCapabilities.Capability

  static var capabilities: [Capability] {
    GeneratedToolCapabilities.capabilities
  }

  static func capabilities(for surface: Surface) -> [Capability] {
    GeneratedToolCapabilities.capabilities(for: surface)
  }

  static func scopedDesktopToolPrompt(excluding excludedToolNames: Set<String>) -> String {
    let docs = capabilities(for: .desktopChat)
      .filter { !excludedToolNames.contains($0.toolName) }
      .map(toolDoc)
      .joined(separator: "\n\n")
    return """
    These Omi data/status tools are documented for desktop chat. Use them before answering when the question depends on the user's personal data, tasks, conversations, memories, app/screen activity, or task-agent state. Do not guess when you can look it up. Do not call tools for simple chit-chat or general knowledge that does not depend on the user's data.

    \(docs)

    **Task-Agent Awareness:**
    - Omi can run local task-chat agents/subagents in the desktop task panel and floating-bar background agents.
    - If the user says "your subagents", "task agents", "running agents", "background agents", or mentions task-agent errors/timeouts, do NOT deny that you have subagents.
    - Call list_agent_sessions before answering those questions.

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
    - Subagents/task-agent/floating-pill status -> list_agent_sessions.
    - Canonical Omi-managed agent sessions/runs -> list_agent_sessions, get_agent_run.
    - Continue an existing canonical Omi agent session -> send_agent_message.
    - Start background work -> spawn_agent.
    - Synchronous parent-linked child result -> run_agent_and_wait.
    - Stop a canonical Omi agent run -> cancel_agent_run.
    - Agent output references/artifacts -> inspect_agent_artifacts.
    - Dismiss floating-bar pills -> set_desktop_attention_override or update_agent_artifact_lifecycle.
    - Onboarding knowledge graph -> save_knowledge_graph.
    """
  }

  static var desktopToolPrompt: String {
    scopedDesktopToolPrompt(excluding: [])
  }

  static var realtimeSelfModelPrompt: String {
    """
    Omi capability model:
    - You can read Omi data quickly with fast tools: tasks, memories, conversations, daily recaps, and screen history.
    - You can create a straightforward calendar event with create_calendar_event when the user gives the event details.
    - You can inspect task-chat agents, floating-bar pills, and canonical Omi-managed agent sessions/runs with list_agent_sessions, get_agent_run, and cancel_agent_run.
    - You can inspect canonical agent output references with inspect_agent_artifacts and mark artifact metadata with update_agent_artifact_lifecycle.
    - You can dismiss floating-bar pills with set_desktop_attention_override after checking list_agent_sessions.
    - You can start background work with spawn_agent for multi-step work or acting in the user's other apps. Merely saying you will start an agent does not start one; emitting spawn_agent does.
    """
  }

  static var desktopToolNames: [String] {
    GeneratedToolCapabilities.desktopToolNames
  }

  static var realtimeToolNames: [String] {
    GeneratedToolCapabilities.realtimeToolNames
  }

  private static func toolDoc(_ capability: Capability) -> String {
    let bullets = capability.bullets.map { "- \($0)" }.joined(separator: "\n")
    return """
    **\(capability.toolName)** (\(capability.latency.rawValue)): \(capability.summary)
    \(bullets)
    """
  }
}
