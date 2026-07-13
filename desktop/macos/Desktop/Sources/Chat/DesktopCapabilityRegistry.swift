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
    let filteredCapabilities = capabilities(for: .desktopChat)
      .filter { !excludedToolNames.contains($0.toolName) }
    let availableToolNames = Set(filteredCapabilities.map(\.toolName))
    let docs = filteredCapabilities
      .map { toolDoc($0, excluding: excludedToolNames) }
      .joined(separator: "\n\n")
    let taskAgentAwareness = taskAgentAwarenessPrompt(availableToolNames: availableToolNames)
    let proactiveGuidance = proactiveGuidancePrompt(availableToolNames: availableToolNames)
    let usageGuidance = usageGuidancePrompt(availableToolNames: availableToolNames)
    return """
    These Omi data/status tools are documented for desktop chat. Use them before answering when the question depends on the user's personal data, tasks, conversations, memories, app/screen activity, or task-agent state. Do not guess when you can look it up. Do not call tools for simple chit-chat or general knowledge that does not depend on the user's data.

    \(docs)

    \(taskAgentAwareness)

    \(proactiveGuidance)

    \(usageGuidance)
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
    - You can propose macOS permission checks or requests with check_permission_status and request_permission; the kernel authorizes the native action.
    - You can inspect task-chat agents, floating-bar pills, and canonical Omi-managed agent sessions/runs with list_agent_sessions, get_agent_run, and cancel_agent_run.
    - You can inspect canonical agent output references with inspect_agent_artifacts and mark artifact metadata with update_agent_artifact_lifecycle.
    - You can dismiss floating-bar pills with set_desktop_attention_override after checking list_agent_sessions.
    - spawn_agent submits a background-work proposal; only an accepted kernel result creates a canonical agent session/run.
    """
  }

  static var desktopToolNames: [String] {
    GeneratedToolCapabilities.desktopToolNames
  }

  static var realtimeToolNames: [String] {
    GeneratedToolCapabilities.realtimeToolNames
  }

  private static func toolDoc(_ capability: Capability, excluding excludedToolNames: Set<String>) -> String {
    let bullets = capability.bullets
      .filter { bullet in
        !excludedToolNames.contains { excluded in
          bullet.contains(excluded)
        }
      }
      .map { "- \($0)" }
      .joined(separator: "\n")
    return """
    **\(capability.toolName)** (\(capability.latency.rawValue)): \(capability.summary)
    \(bullets)
    """
  }

  private static func proactiveGuidancePrompt(availableToolNames: Set<String>) -> String {
    func has(_ toolName: String) -> Bool { availableToolNames.contains(toolName) }
    func available(_ toolNames: [String]) -> [String] { toolNames.filter(has) }
    let memoryTools = available(["get_memories", "search_memories", "execute_sql"])
    let conversationTools = available(["search_conversations", "get_conversations"])

    guard !memoryTools.isEmpty || !conversationTools.isEmpty else {
      return ""
    }

    var lines = [
      "**CRITICAL -- When to use tools proactively:**",
      "The <user_facts> section above only contains a SAMPLE of {user_name}'s memories. The full set is available through the available memory and local database tools.",
      "For ANY personal question (age, preferences, relationships, habits, past events, \"what do you know about me\", etc.):",
      "1. FIRST check <user_facts> — if the answer is there, use it directly.",
    ]
    if !memoryTools.isEmpty {
      lines.append("2. If NOT in <user_facts>, use \(memoryTools.joined(separator: ", ")) over memories before saying you don't know.")
    }
    if !conversationTools.isEmpty {
      lines.append("3. For questions about past events or conversations, query \(conversationTools.joined(separator: ", ")) or transcription_sessions/transcription_segments.")
    }
    lines.append("NEVER say \"I don't know\" or \"I don't have that info\" without checking first.")
    return lines.joined(separator: "\n")
  }

  private static func taskAgentAwarenessPrompt(availableToolNames: Set<String>) -> String {
    guard availableToolNames.contains("list_agent_sessions") else {
      return ""
    }
    return """
    **Task-Agent Awareness:**
    - Omi can run local task-chat agents/subagents in the desktop task panel and floating-bar background agents.
    - If the user says "your subagents", "task agents", "running agents", "background agents", or mentions task-agent errors/timeouts, do NOT deny that you have subagents.
    - Call list_agent_sessions before answering those questions.
    """
  }

  private static func usageGuidancePrompt(availableToolNames: Set<String>) -> String {
    var lines = ["**When to use which tool:**"]
    func has(_ toolName: String) -> Bool { availableToolNames.contains(toolName) }
    func available(_ toolNames: [String]) -> [String] { toolNames.filter(has) }
    func toolList(_ toolNames: [String]) -> String { available(toolNames).joined(separator: ", ") }
    func append(_ line: String, when condition: Bool) {
      if condition { lines.append("- \(line)") }
    }

    let personalTools = ["get_memories", "search_memories", "execute_sql"]
    append(
      "Personal facts/preferences -> \(toolList(personalTools)) over memories.",
      when: !available(personalTools).isEmpty
    )
    let conversationTools = ["search_conversations", "get_conversations"]
    append(
      "Specific past conversations/events -> \(toolList(conversationTools)).",
      when: !available(conversationTools).isEmpty
    )
    append(
      "Current screen/current work questions (\"what is on my screen?\", \"do you see my screen?\") -> get_work_context first.",
      when: has("get_work_context")
    )
    let screenshotTools = ["capture_screen", "get_screenshot"]
    append(
      "Raw screenshot pixels -> \(toolList(screenshotTools)) only when work context is insufficient and approval is available.",
      when: !available(screenshotTools).isEmpty
    )
    append(
      "If a screen tool reports permission_required, tell the user Omi cannot access that capability yet and ask whether they want to grant it. Call request_permission with the returned permission type only after explicit current-turn consent.",
      when: has("request_permission")
    )
    let permissionTools = ["check_permission_status", "request_permission"]
    append(
      "User explicitly asks to grant/check app permissions -> \(toolList(permissionTools)).",
      when: !available(permissionTools).isEmpty
    )
    append("What the user did today/yesterday/this week -> get_daily_recap.", when: has("get_daily_recap"))
    append("App usage counts or exact local stats -> execute_sql.", when: has("execute_sql"))
    append("Fuzzy screen-history questions -> semantic_search.", when: has("semantic_search"))
    append("Find tasks by meaning -> search_tasks.", when: has("search_tasks"))
    let taskWriteTools = ["create_action_item", "update_action_item", "execute_sql"]
    append(
      "Create/update tasks -> \(toolList(taskWriteTools)); use execute_sql only for exact local inspection or legacy local writes.",
      when: !available(taskWriteTools).isEmpty
    )
    let taskCompletionTools = ["complete_task", "delete_task"]
    append(
      "Complete/delete local tasks -> find the backendId, then \(toolList(taskCompletionTools)).",
      when: !available(taskCompletionTools).isEmpty
    )
    append("Subagents/task-agent/floating-pill status -> list_agent_sessions.", when: has("list_agent_sessions"))
    let agentSessionTools = ["list_agent_sessions", "get_agent_run"]
    append(
      "Canonical Omi-managed agent sessions/runs -> \(toolList(agentSessionTools)).",
      when: !available(agentSessionTools).isEmpty
    )
    append("Continue an existing canonical Omi agent session -> send_agent_message.", when: has("send_agent_message"))
    append("Start background work -> spawn_agent.", when: has("spawn_agent"))
    append("Synchronous parent-linked child result -> run_agent_and_wait.", when: has("run_agent_and_wait"))
    append("Stop a canonical Omi agent run -> cancel_agent_run.", when: has("cancel_agent_run"))
    append("Agent output references/artifacts -> inspect_agent_artifacts.", when: has("inspect_agent_artifacts"))
    let dismissalTools = ["set_desktop_attention_override", "update_agent_artifact_lifecycle"]
    append(
      "Dismiss floating-bar pills -> \(toolList(dismissalTools)).",
      when: !available(dismissalTools).isEmpty
    )
    append("Onboarding knowledge graph -> save_knowledge_graph.", when: has("save_knowledge_graph"))
    return lines.joined(separator: "\n")
  }
}
