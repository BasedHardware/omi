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
    let canDelegate = !excludedToolNames.contains("delegate_agent")
    let canSpawnFloatingPills = !excludedToolNames.contains("spawn_agent")
    let delegationGuidance: String
    if canDelegate && canSpawnFloatingPills {
      delegationGuidance = """
      - Delegate to a distinct canonical child Omi agent session -> delegate_agent.
      - Stop a canonical Omi agent run -> cancel_agent_run.
      - Agent output references/artifacts -> inspect_agent_artifacts.
      - Start a visible floating-bar subagent/background agent -> spawn_agent.
      - Dismiss/list/clear circular floating agent pills -> manage_agent_pills.
      - delegate_agent records durable child sessions/runs/delegations under a known parent run; spawn_agent creates top-level canonical background work and projects it into the floating-pill UI. Do not treat one as an alias for the other.
      """
    } else {
      delegationGuidance = """
      - Stop a canonical Omi agent run -> cancel_agent_run.
      - Agent output references/artifacts -> inspect_agent_artifacts.
      - Dismiss/list/clear circular floating agent pills -> manage_agent_pills.
      """
    }
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
    - Canonical Omi-managed agent sessions/runs -> list_agent_sessions, get_agent_run.
    - Continue an existing canonical Omi agent session -> send_agent_message.
    \(delegationGuidance)
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
    - You can inspect your local task-chat agents/subagents and floating agent pills with get_task_agent_status. If the user asks about your subagents, background agents, running agents, finished agents, or task-agent errors/timeouts, call it before answering.
    - You can inspect and stop canonical Omi-managed agent sessions/runs with list_agent_sessions, get_agent_run, and cancel_agent_run. Use these for agents created in chat, PTT/realtime, task chat, or any other Omi surface when a canonical run id is available.
    - You can inspect canonical agent output references with inspect_agent_artifacts and mark artifact metadata with update_agent_artifact_lifecycle.
    - You can manage circular floating agent pills with manage_agent_pills after checking status.
    - You can start a background agent with spawn_agent for multi-step work or acting in the user's other apps. Merely saying you will start an agent does not start one; emitting spawn_agent does.
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
