import Foundation

// MARK: - Realtime Hub tool surface
//
// The realtime model IS the router: instead of a separate Haiku classify() call,
// the model decides what to do by choosing a tool. The same tool surface is
// declared to both providers (OpenAI Realtime `tools`, Gemini `functionDeclarations`);
// `RealtimeHubController` executes them by calling EXISTING app code / endpoints.
// Reads (get_tasks, get_memories, search_memories, search_conversations) and simple
// writes (create_action_item, update_action_item, create_calendar_event) run synchronously and speak their
// result; multi-step / other-app work still goes to spawn_agent.

enum HubTool: String {
  /// Escalate a hard / knowledge-heavy question to the smarter Claude model via
  /// the existing prompt-cached /v2/chat/completions, then speak its answer.
  case askHigherModel = "ask_higher_model"
  /// Hand a multi-step task to a background agent (existing AgentBridge / pills).
  /// Non-blocking: the model acknowledges and moves on.
  case spawnAgent = "spawn_agent"
  /// Read the user's tasks locally (TasksStore) and return them inline to speak — a
  /// fast synchronous READ, NOT a background agent. Overdue + due-today only.
  case getTasks = "get_tasks"
  /// Read the user's full action-item list from the backend with filters (completed,
  /// due-date range). Fast READ — use for completed tasks, date ranges, or the whole list
  /// (get_tasks only covers overdue + due-today).
  case getActionItems = "get_action_items"
  /// Inspect Omi's local task-chat/background agents. Fast local READ.
  case getTaskAgentStatus = "get_task_agent_status"
  /// Manage floating-bar agent pills. Fast local action.
  case manageAgentPills = "manage_agent_pills"
  /// Install a missing local agent provider (openclaw/hermes/codex) via the
  /// deterministic LocalAgentProviderInstaller — native confirmation dialog,
  /// then a code-run Process. Only after explicit user consent; idempotent.
  case setupAgentProvider = "setup_agent_provider"
  /// List canonical Omi-managed agent sessions and runs.
  case listAgentSessions = "list_agent_sessions"
  /// Inspect one canonical Omi-managed agent run.
  case getAgentRun = "get_agent_run"
  /// Request cancellation for one canonical Omi-managed agent run.
  case cancelAgentRun = "cancel_agent_run"
  /// Inspect metadata for canonical Omi-managed agent artifacts.
  case inspectAgentArtifacts = "inspect_agent_artifacts"
  /// Update metadata-only lifecycle state for a canonical Omi-managed artifact.
  case updateAgentArtifactLifecycle = "update_agent_artifact_lifecycle"
  /// Read what Omi knows about the user (memories / facts) and return it inline to speak.
  /// Fast synchronous READ — the answer to "who am I" / "what do you know about me".
  case getMemories = "get_memories"
  /// Semantically search the user's memories / facts for something specific. Fast READ.
  case searchMemories = "search_memories"
  /// Semantically search the user's past conversations (titles + summaries, no transcripts).
  /// Fast synchronous READ.
  case searchConversations = "search_conversations"
  /// List the user's MOST RECENT conversations, newest first (titles + summaries, no
  /// transcripts). Fast READ — the answer to "most recent / latest / last conversation".
  case getConversations = "get_conversations"
  /// Formatted recap of what the user actually DID on their Mac — apps used (with minutes),
  /// conversations, tasks, focus, screen activity. Fast LOCAL READ — the answer to "what did I
  /// do yesterday / today", "which apps did I use the most", "how did I spend my time".
  case getDailyRecap = "get_daily_recap"
  /// Semantically search the user's on-screen history (what they saw / read / worked on).
  /// Fast LOCAL READ — "when was I looking at X", "find where I read about Y".
  case searchScreenHistory = "search_screen_history"
  /// Create a new task / to-do / reminder for the user. Fast synchronous WRITE.
  case createActionItem = "create_action_item"
  /// Update an existing task (mark done, change text/due). Needs the task id from get_tasks.
  case updateActionItem = "update_action_item"
  /// Create a Google Calendar event through the backend calendar tool.
  case createCalendarEvent = "create_calendar_event"
  /// Capture the user's screen so the model can see what they're looking at.
  case screenshot = "screenshot"
  /// Click at on-screen coordinates (local).
  case pointClick = "point_click"
}

enum RealtimeHubTools {
  private static let directedProviders: [AgentPillsManager.DirectedProvider] = AgentPillsManager.orderedDirectedProviders

  private static func localAgentProviderInstruction() -> String {
    localAgentProviderInstruction(
      availability: directedProviders.map { LocalAgentProviderDetector.availability(for: $0) })
  }

  /// Availability-parameterized seam (same pattern as
  /// `openAITools(availableDirectedProviders:)`) so instruction content is
  /// testable without filesystem-dependent provider detection.
  static func localAgentProviderInstruction(availability: [LocalAgentProviderAvailability]) -> String {
    let available = availability.filter(\.isAvailable).map(\.provider)
    let unavailable = availability.filter { !$0.isAvailable }

    var parts: [String] = []
    if !available.isEmpty {
      let names = available.map { "\"\($0.rawValue)\"" }.joined(separator: " or ")
      parts.append("If the user asks to use/ask \(available.map(\.displayName).joined(separator: " or ")), call spawn_agent with provider set to \(names).")
      let strengthsText = available
        .map { "\($0.displayName): \($0.strengths)" }
        .joined(separator: "; ")
      parts.append("When the user does not name an agent, pick the provider whose strengths clearly match the task — \(strengthsText) — otherwise omit provider to use Omi's default agent. When the user names an agent, always use that one.")
    }
    if unavailable.isEmpty {
      parts.append("Treat those as available local providers, not as sessions to inspect.")
    } else {
      // Compact instruction fragments only — the full user-facing setup
      // prompt (install command + docs URL) stays on UI/toolError surfaces.
      let missingText = unavailable
        .map { "\($0.provider.displayName): not installed — offer to set it up via setup_agent_provider after explicit consent." }
        .joined(separator: " ")
      parts.append("If the user asks to use/ask an unavailable local provider, do NOT spawn a default agent. Say it needs setup and offer to install it: \(missingText) \(LocalAgentProviderInstaller.consentRule)")
    }
    return parts.joined(separator: " ")
  }

  private static func availableDirectedProviderRawValues() -> [String] {
    directedProviders
      .filter { LocalAgentProviderDetector.isAvailable($0) }
      .map(\.rawValue)
  }

  private static func currentCalendarContext(now: Date = Date(), timeZone: TimeZone = .current) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withColonSeparatorInTimeZone]
    formatter.timeZone = timeZone
    let offset = timeZone.secondsFromGMT(for: now)
    let sign = offset >= 0 ? "+" : "-"
    let absOffset = abs(offset)
    let hours = absOffset / 3600
    let minutes = (absOffset % 3600) / 60
    return String(
      format: "Current local datetime: %@. Current timezone: %@ (UTC%@%02d:%02d).",
      formatter.string(from: now),
      timeZone.identifier,
      sign,
      hours,
      minutes
    )
  }

  /// One line telling the model which languages the user actually speaks, so a short or
  /// ambiguous utterance is never interpreted (or transcribed, where the provider allows
  /// it) as some third language. Falls back to the Mac's preferred language when the user
  /// has not configured an explicit voice-language set.
  private static func userLanguagesLine(_ codes: [String]) -> String {
    let resolved = resolvedVoiceLanguages(explicit: codes)
    guard !resolved.isEmpty else { return "" }
    let names = resolved.map { code in
      Locale(identifier: "en").localizedString(forLanguageCode: code) ?? code
    }
    let primary = names[0]
    let list = names.joined(separator: ", ")
    return
      "The user speaks ONLY these languages: \(list) (primary: \(primary)). Their speech "
      + "is always in one of them — if an utterance seems to be in any other language, it "
      + "was misheard; interpret it as \(primary). "
  }

  static func systemInstruction(
    kernelContext: String = "",
    kernelSemanticGuidance: String = "",
    userLanguages: [String] = []
  ) -> String {
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)

    return """
      You are Omi, a fast spoken-voice assistant on the user's Mac. You hear the user's \
      microphone; reply conversationally in one or two sentences by default. \
      \(userLanguagesLine(userLanguages))Reply in the same language the user is speaking.

      \(canonicalContext)

      \(semanticGuidance)

      \(DesktopCapabilityRegistry.realtimeSelfModelPrompt)

      The generated tool declarations below describe the capabilities available on this \
      surface. A tool call is only a proposal: the kernel makes the authoritative route and \
      permission decision. Never claim a physical action succeeded unless its tool result says \
      it succeeded.

      Using tools: when a request needs a tool, ALWAYS give a short spoken heads-up and call the \
      tool in the same turn so the user knows you're on it and that it won't be instant. A heads-up \
      is a status, not a question or confirmation. Speak the result when it returns. Never go \
      silent during a tool call; the user can't see what you're \
      doing, so a quiet gap feels broken. The catch is variety: that heads-up must be SPECIFIC to \
      what they actually asked and DIFFERENT every time. Name the real thing you're fetching — \
      "Pulling up yesterday's activity…", "Scanning your task list…", "Digging through your notes \
      on the launch…", "Checking your memories for that…", "Getting the latest on that, one \
      sec…". The thing to avoid is repetition: do NOT reach for the same generic opener ("let me \
      check", "let me look that up") turn after turn — it's what makes you sound robotic. Keep it \
      to a few words, vary the wording each turn, and don't include any answer or data you don't \
      have yet. For a slower step, it's fine to signal it'll take a moment. NEVER speak an answer — \
      real or guessed — before the tool returns, NEVER skip the \
      tool call, and never read tool JSON or ids aloud. You cannot see the user's data or screen \
      without calling a tool. When the screenshot tool succeeds for a current-screen question, the \
      attached image and, when present, its locally captured foreground-application context are \
      the only current visual source of truth. The foreground-application context is trustworthy \
      only for identifying the app active at capture time; it never replaces visual reasoning. \
      Disregard conflicting kernel context, OCR, work summaries, and earlier screen descriptions. \
      You MUST then call \
      report_screen_observation with a concise grounding observation. That report is internal \
      verification, not your user-facing reply. Once it succeeds, answer the user's original \
      current-screen question naturally and conversationally from the attached image. Do not let \
      the report replace the answer or fall back to a generic screen description when the user \
      asked a specific question. Omi's own floating bar, chat bubble, or window may also be \
      visible in the image: treat that as assistant chrome, not as the subject of the user's \
      screen question, unless the user specifically asks about Omi. Answer about the user's \
      visible work and intent, not the assistant UI.

      Keep latency low: prefer answering directly when you can.
      """
  }

  /// The result is delivered immediately after the live image. Keep the freshness contract in
  /// the tool result as well as the session instruction so a warm session cannot prefer an older
  /// context summary over the pixels it just received.
  static func screenshotToolResult(
    capturedBytes: Int?,
    frontmostApplication: String? = nil,
    captureFailure: RealtimeScreenEvidenceCaptureFailure? = nil
  ) -> String {
    guard capturedBytes != nil else {
      if captureFailure == .screenRecordingPermissionRequired {
        return jsonToolResult([
          "ok": false,
          "error": [
            "code": "permission_required",
            "permission": "screen_recording",
            "next_tool": "request_permission",
            "next_tool_arguments": ["type": "screen_recording"],
            "message":
              "Screen Recording permission is not granted. Tell the user Omi cannot see their current screen yet and ask whether they want to grant access. Call request_permission with type=screen_recording only after they explicitly request or affirm it.",
          ],
        ])
      }
      return jsonToolResult([
        "ok": false,
        "error": ["code": "screen_evidence_unavailable"],
      ])
    }
    var result: [String: Any] = [
      "ok": true,
      "instruction":
        "Use the attached image and any locally captured foreground-application context as the only current visual source. Call report_screen_observation with a concise grounding observation, then answer the user's original request naturally from this evidence.",
    ]
    if let frontmostApplication = frontmostApplication?.trimmingCharacters(in: .whitespacesAndNewlines),
      !frontmostApplication.isEmpty
    {
      // This is sampled with the frozen screenshot and sent only through the matching
      // provider tool result. It is not persisted, logged, or reused as ambient context.
      result["capture_context"] = ["foreground_application": frontmostApplication]
    }
    return jsonToolResult(result)
  }

  static func screenObservationResult(accepted: Bool) -> String {
    jsonToolResult(
      accepted
        ? [
          "ok": true,
          "status": "screen_observation_accepted",
          "instruction":
            "Grounding verified. Now answer the user's original request naturally using the attached image; the observation was not the user-facing answer.",
        ]
        : ["ok": false, "error": ["code": "screen_observation_rejected"]])
  }

  private static func jsonToolResult(_ value: [String: Any]) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
      let result = String(data: data, encoding: .utf8)
    else { return #"{\"ok\":false,\"error\":{\"code\":\"screen_evidence_encoding_failed\"}}"# }
    return result
  }

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    // Standalone callers fail closed. A physical RealtimeHubSession receives
    // the exact Node registry projection at construction time.
    openAITools(availableDirectedProviders: [])
  }

  static func openAITools(availableDirectedProviders: [String]) -> [[String: Any]] {
    let providerProperty: [String: Any]? =
      availableDirectedProviders.isEmpty
      ? nil
      : [
        "type": "string",
        "enum": availableDirectedProviders,
        "description":
          "The user's raw delegation intent or proposed task. Include concrete details you know; "
          + "Omi's resolver will rewrite it before any child agent sees it.",
      ],
      "title": [
        "type": "string",
        "description":
          "A short Title Case label for the task pill (≤ ~5 words, no trailing "
          + "punctuation), e.g. 'Draft Launch Email'.",
      ],
    ]
    if let providerProperty {
      spawnAgentProperties["provider"] = providerProperty
    }

    return [
      [
        "type": "function",
        "name": HubTool.askHigherModel.rawValue,
        "description":
          "Get a second opinion from a smarter model and receive text to speak. Use ONLY when the user "
          + "is dissatisfied with your previous answer (pushes back, rephrases, says you're wrong, or asks "
          + "for a better/deeper answer), OR when you genuinely need precise up-to-date facts you don't "
          + "know. Do NOT use it for general, creative, or long-form requests — answer those yourself.",
        "parameters": [
          "type": "object",
          "properties": [
            "query": ["type": "string", "description": "The full question to escalate."],
            "context": [
              "type": "string",
              "description":
                "Relevant context you already have that helps answer well — facts you fetched, "
                + "what the user is referring to, or the previous answer they pushed back on. "
                + "Include only what's relevant; omit if there's nothing useful.",
            ],
          ],
          "required": ["query"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.getTasks.rawValue,
        "description":
          "Read the user's tasks (overdue + due today) locally and get them back as text to speak. "
          + "Fast synchronous read — use this for 'what are my tasks', 'what's due today', 'what's on "
          + "my list'. Do NOT use spawn_agent for reading tasks.",
        "parameters": ["type": "object", "properties": [:]],
      ],
      [
        "type": "function",
        "name": HubTool.getMemories.rawValue,
        "description":
          "Read what Omi knows about the user — their memories and facts (preferences, "
          + "background, people, habits). Fast synchronous read with NO query. Use this for "
          + "'who am I', 'what do you know about me', 'what are my preferences'. Speak what it returns.",
        "parameters": ["type": "object", "properties": [:]],
      ],
      [
        "type": "function",
        "name": HubTool.searchMemories.rawValue,
        "description":
          "Search the user's memories / facts for a SPECIFIC thing ('what's my dog's name', "
          + "'where do I work', 'what's my partner's name'). Fast synchronous read. Speak the result.",
        "parameters": [
          "type": "object",
          "properties": [
            "query": ["type": "string", "description": "What to look up about the user."]
          ],
          "required": ["query"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.searchConversations.rawValue,
        "description":
          "Search the user's past conversations for what they discussed ('what did I say about X', "
          + "'what did we decide', 'summarize my last meeting'). Returns titles + summaries only "
          + "(no full transcripts). Fast synchronous read. Speak the result.",
        "parameters": [
          "type": "object",
          "properties": [
            "query": ["type": "string", "description": "What topic / conversation to find."]
          ],
          "required": ["query"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.getConversations.rawValue,
        "description":
          "List the user's MOST RECENT conversations, newest first (titles + summaries, no full "
          + "transcripts). Use this — NOT search_conversations — for 'what was my most recent / "
          + "latest / last conversation', 'what did we just talk about', or 'my recent conversations'. "
          + "search_conversations is semantic and does NOT order by time, so it's wrong for 'recent'. "
          + "Fast synchronous read. Speak the result.",
        "parameters": ["type": "object", "properties": [:]],
      ],
      [
        "type": "function",
        "name": HubTool.getDailyRecap.rawValue,
        "description":
          "Get a recap of what the user actually DID on their Mac — apps used (with minutes), "
          + "conversations, tasks, focus sessions, and screen activity — for a day. THIS is the tool "
          + "for 'what did I do yesterday', 'what did I do today', 'which apps did I use the most', "
          + "'how did I spend my time'. Do NOT use search_conversations or spawn_agent for these. "
          + "Fast synchronous read — speak a short summary of what it returns.",
        "parameters": [
          "type": "object",
          "properties": [
            "days_ago": [
              "type": "number",
              "description": "0 = today, 1 = yesterday (default), 7 = the past week.",
            ]
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.searchScreenHistory.rawValue,
        "description":
          "Search the user's on-screen history — what they saw, read, or worked on — by meaning. "
          + "Use for 'when was I looking at X', 'find where I read about Y', 'what was I doing in "
          + "app Z'. Returns matching moments with the app and context. Fast synchronous read. "
          + "Speak the result.",
        "parameters": [
          "type": "object",
          "properties": [
            "query": [
              "type": "string", "description": "What the user was looking at / reading / doing.",
            ],
            "days": ["type": "number", "description": "How many days back to search; default 7."],
          ],
          "required": ["query"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.getActionItems.rawValue,
        "description":
          "Read the user's tasks / to-dos from the backend, with optional filters. Use for "
          + "COMPLETED tasks ('what did I finish'), a DATE RANGE ('what's due next week'), or the "
          + "FULL list ('all my tasks') — for plain 'what's due today / overdue', prefer get_tasks. "
          + "Fast synchronous read. Speak a short summary of what it returns.",
        "parameters": [
          "type": "object",
          "properties": [
            "completed": [
              "type": "boolean",
              "description": "true = only done tasks, false = only open tasks. Omit for both.",
            ],
            "due_start_date": [
              "type": "string", "description": "Optional ISO-8601 start of the due-date range.",
            ],
            "due_end_date": [
              "type": "string", "description": "Optional ISO-8601 end of the due-date range.",
            ],
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.getTaskAgentStatus.rawValue,
        "description":
          "Inspect Omi's local task-chat/background agents and floating agent pills, including recent completed/failed ones. "
          + "Use when the user asks about your subagents, task agents, background agents, "
          + "running agents, finished agents, errors, or timeouts. Fast local read.",
        "parameters": ["type": "object", "properties": [:]],
      ],
      [
        "type": "function",
        "name": HubTool.manageAgentPills.rawValue,
        "description":
          "Manage the circular floating agent pills shown below the floating bar. Use list freely. "
          + "Only dismiss or clear pills when the user explicitly asks to dismiss, close, remove, hide, or clear pills. "
          + "Never dismiss completed agents just because you finished reading their status.",
        "parameters": [
          "type": "object",
          "properties": [
            "action": [
              "type": "string",
              "enum": ["list", "dismiss", "clear_completed"],
              "description": "Management action to perform.",
            ],
            "agent_id": [
              "type": "string",
              "description": "Floating agent pill id from get_task_agent_status; required for dismiss.",
            ],
          ],
          "required": ["action"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.setupAgentProvider.rawValue,
        "description":
          "Install a local agent provider (OpenClaw, Hermes, or Codex) that is not set up yet. "
          + "Shows the user a native confirmation dialog with the exact install command; nothing "
          + "downloads or runs until they click Install, then Omi runs the official command itself, "
          + "verifies the binary, and reports the result. Interactive sign-in steps are left to the "
          + "user. Idempotent: an already-installed provider just reports ready. "
          + LocalAgentProviderInstaller.consentRule,
        "parameters": [
          "type": "object",
          "properties": [
            "provider": [
              "type": "string",
              "enum": directedProviders.map(\.rawValue),
              "description": "Local agent provider to install.",
            ]
          ],
          "required": ["provider"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.listAgentSessions.rawValue,
        "description":
          "List canonical Omi-managed agent sessions/runs across chat, PTT/realtime, task chat, and migrated surfaces. "
          + "Use when the user asks what canonical agents or subagents are active, recent, failed, or manageable.",
        "parameters": [
          "type": "object",
          "properties": [
            "status": [
              "type": "string",
              "enum": ["open", "archived", "closed"],
              "description": "Optional session status filter.",
            ],
            "surfaceKind": [
              "type": "string",
              "enum": ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_pill"],
              "description": "Optional canonical surface filter.",
            ],
            "limit": [
              "type": "number",
              "description": "Maximum sessions to return. Default 50.",
            ],
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.getAgentRun.rawValue,
        "description":
          "Inspect one canonical Omi-managed agent run. Prefer an agentRef from list_agent_sessions.",
        "parameters": [
          "type": "object",
          "properties": [
            "agentRef": ["type": "string", "description": "Opaque agent handle from list_agent_sessions."],
            "runId": ["type": "string", "description": "Canonical Omi run id."],
            "includeEvents": ["type": "boolean", "description": "Include ordered kernel events. Default true."],
            "eventLimit": ["type": "number", "description": "Maximum events to return. Default 100."],
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.cancelAgentRun.rawValue,
        "description":
          "Request cancellation for one canonical Omi-managed agent run. Use when the user asks to stop or kill a running canonical agent/subagent.",
        "parameters": [
          "type": "object",
          "properties": [
            "agentRef": ["type": "string", "description": "Opaque agent handle from list_agent_sessions."],
            "runId": ["type": "string", "description": "Canonical Omi run id to cancel."]
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.inspectAgentArtifacts.rawValue,
        "description":
          "Inspect metadata and references for canonical Omi-managed agent artifacts. Does not read arbitrary artifact contents.",
        "parameters": [
          "type": "object",
          "properties": [
            "agentRef": ["type": "string", "description": "Opaque agent handle from list_agent_sessions."],
            "artifactRef": ["type": "string", "description": "Opaque artifact handle from inspect_agent_artifacts."],
            "artifactId": ["type": "string", "description": "Canonical Omi artifact id."],
            "sessionId": ["type": "string", "description": "Canonical Omi session id."],
            "runId": ["type": "string", "description": "Canonical Omi run id."],
            "attemptId": ["type": "string", "description": "Canonical Omi attempt id."],
            "role": [
              "type": "string",
              "enum": ["input", "result", "checkpoint", "tool_output", "log", "other"],
              "description": "Optional artifact role filter.",
            ],
            "limit": ["type": "number", "description": "Maximum artifacts to return. Default 50."],
          ],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.updateAgentArtifactLifecycle.rawValue,
        "description":
          "Update metadata-only lifecycle state for one canonical Omi-managed agent artifact. Does not open, delete, retain, or read files.",
        "parameters": [
          "type": "object",
          "properties": [
            "artifactRef": ["type": "string", "description": "Opaque artifact handle from inspect_agent_artifacts."],
            "artifactId": ["type": "string", "description": "Canonical Omi artifact id."],
            "state": [
              "type": "string",
              "enum": ["retained", "dismissed", "opened"],
              "description": "Target metadata lifecycle state.",
            ],
            "sessionId": ["type": "string", "description": "Optional canonical Omi session id scope guard."],
            "runId": ["type": "string", "description": "Optional canonical Omi run id scope guard."],
            "attemptId": ["type": "string", "description": "Optional canonical Omi attempt id scope guard."],
            "reason": ["type": "string", "description": "Optional short reason."],
          ],
          "required": ["state"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.createActionItem.rawValue,
        "description":
          "Create a new task / to-do / reminder for the user ('remind me to…', 'add … to my "
          + "list', 'I need to…'). Fast synchronous write. Confirm out loud after it returns.",
        "parameters": [
          "type": "object",
          "properties": [
            "description": ["type": "string", "description": "The task text."],
            "due_at": [
              "type": "string",
              "description": "Optional ISO-8601 due date/time, only if the user gave one.",
            ],
          ],
          "required": ["description"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.updateActionItem.rawValue,
        "description":
          "Update an existing task: mark it done, edit its text, or reschedule it. You MUST first "
          + "call get_tasks to get the matching task's id, then pass that id here. Fast synchronous write.",
        "parameters": [
          "type": "object",
          "properties": [
            "id": ["type": "string", "description": "The task id from get_tasks."],
            "completed": ["type": "boolean", "description": "Set true to mark the task done."],
            "description": ["type": "string", "description": "New task text, if changing it."],
            "due_at": ["type": "string", "description": "New ISO-8601 due date/time, if rescheduling."],
          ],
          "required": ["id"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.createCalendarEvent.rawValue,
        "description":
          "Create a Google Calendar event for the user. Use for simple calendar requests like "
          + "'put this on my calendar', 'schedule lunch tomorrow', or 'create an event'. Requires "
          + "start_time and end_time as ISO-8601 strings with timezone. Use spawn_agent instead "
          + "for multi-step scheduling, finding availability, rescheduling, deleting, or coordinating with people.",
        "parameters": [
          "type": "object",
          "properties": [
            "title": ["type": "string", "description": "Event title."],
            "start_time": [
              "type": "string",
              "description": "Event start time in ISO-8601 with timezone, e.g. 2026-06-28T14:00:00-04:00.",
            ],
            "end_time": [
              "type": "string",
              "description": "Event end time in ISO-8601 with timezone, e.g. 2026-06-28T15:00:00-04:00.",
            ],
            "description": ["type": "string", "description": "Optional event description."],
            "location": ["type": "string", "description": "Optional event location."],
            "attendees": [
              "type": "string",
              "description": "Optional comma-separated attendee names or email addresses.",
            ],
          ],
          "required": ["title", "start_time", "end_time"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.spawnAgent.rawValue,
        "description":
          "Request delegation to a background agent through Omi's resolver. The resolver may start "
          + "a child agent, continue an existing one, or ask for missing details. Use for work in the "
          + "user's apps/browser/files or multi-step work that you cannot do directly.",
        "parameters": [
          "type": "object",
          "properties": spawnAgentProperties,
          "required": ["brief"],
        ],
      ],
      [
        "type": "function",
        "name": HubTool.screenshot.rawValue,
        "description": "Capture the user's current screen so you can see what they're looking at.",
        "parameters": ["type": "object", "properties": [:]],
      ],
      [
        "type": "function",
        "name": HubTool.pointClick.rawValue,
        "description": "Click the mouse at on-screen pixel coordinates.",
        "parameters": [
          "type": "object",
          "properties": [
            "x": ["type": "number", "description": "X pixel coordinate."],
            "y": ["type": "number", "description": "Y pixel coordinate."],
          ],
          "required": ["x", "y"],
        ],
      ],
    ]
  }

  /// Gemini Live `setup.tools[0].functionDeclarations` entries (same surface). Derived once
  /// from `openAITools`.
  static var geminiFunctionDeclarations: [[String: Any]] {
    geminiFunctionDeclarations(availableDirectedProviders: [])
  }

  static func geminiFunctionDeclarations(availableDirectedProviders: [String]) -> [[String: Any]] {
    openAITools(availableDirectedProviders: availableDirectedProviders).map { tool in
      // Gemini wants {name, description, parameters} without the OpenAI "type" wrapper.
      var decl: [String: Any] = [
        "name": tool["name"] as? String ?? "",
        "description": tool["description"] as? String ?? "",
      ]
      // Gemini's Schema `type` must be UPPERCASE (OBJECT/STRING/NUMBER/…). The OpenAI
      // tools use lowercase JSON-schema types, which Gemini silently accepts but degrades
      // (the model gets less confident about when/how to call) — so convert them.
      if let params = tool["parameters"] as? [String: Any] {
        decl["parameters"] = geminiParametersSchema(params)
      }
      return decl
    }
  }

  private static let geminiUnsupportedSchemaKeys: Set<String> = [
    "additionalProperties", "$schema", "default", "title", "pattern", "const",
  ]

  /// Gemini Live `parameters` is OpenAPI 3.0 Schema: uppercase `type` and drop JSON Schema
  /// keys Gemini rejects (e.g. `additionalProperties`).
  private static func geminiParametersSchema(_ schema: [String: Any]) -> [String: Any] {
    var out: [String: Any] = [:]
    for (key, value) in schema {
      if geminiUnsupportedSchemaKeys.contains(key) { continue }
      switch key {
      case "type":
        out[key] = (value as? String)?.uppercased() ?? value
      case "properties":
        guard let props = value as? [String: Any] else {
          out[key] = value
          break
        }
        var converted: [String: Any] = [:]
        for (propKey, propValue) in props {
          converted[propKey] =
            (propValue as? [String: Any]).map(geminiParametersSchema) ?? propValue
        }
        out[key] = converted
      case "items":
        out[key] = (value as? [String: Any]).map(geminiParametersSchema) ?? value
      default:
        if let nested = value as? [String: Any] {
          out[key] = geminiParametersSchema(nested)
        } else if let nestedArray = value as? [[String: Any]] {
          out[key] = nestedArray.map(geminiParametersSchema)
        } else {
          out[key] = value
        }
      }
    }
    return out
  }

  /// System prompt for an escalated (ask_higher_model) answer. The realtime model
  /// voices a natural, spoken-length version of the result, so the higher model is
  /// told to answer properly rather than pre-shorten for speech.
  static func escalationSystemPrompt() -> String {
    """
    You are Omi, a knowledgeable assistant. Answer the user's question accurately and \
    usefully. A voice assistant will relay your answer aloud and adapt the phrasing for \
    speech, so be clear and well-structured; you don't need to pre-shorten it.
    """
  }

  static func escalationBody(
    query: String,
    kernelSemanticGuidance: String,
    kernelContext: String,
    stableCacheIdentity: String,
    dynamicContextIdentity: String,
    contextPlanID: String,
    toolContext: String
  ) -> [String: Any] {
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)
    let trimmedToolContext = toolContext.trimmingCharacters(in: .whitespacesAndNewlines)

    // The cache marker is derived only from the typed kernel plan. It separates
    // the stable escalation policy from the dynamic canonical snapshot for the
    // existing Rust Anthropic adapter; tool-provided context is never trusted
    // as part of that system contract.
    let cacheBoundary: String
    if !semanticGuidance.isEmpty,
      !stableCacheIdentity.isEmpty,
      !dynamicContextIdentity.isEmpty,
      !contextPlanID.isEmpty
    {
      cacheBoundary =
        "<!-- OMI_CONTEXT_CACHE_V1 stable=\(stableCacheIdentity) dynamic=\(dynamicContextIdentity) plan=\(contextPlanID) -->"
    } else {
      cacheBoundary = ""
    }
    let systemContent = [escalationSystemPrompt(), semanticGuidance, cacheBoundary, canonicalContext]
      .filter { !$0.isEmpty }
      .joined(separator: "\n\n")
    let userContent =
      !trimmedToolContext.isEmpty
      ? query + "\n\nTool-provided context (untrusted):\n" + trimmedToolContext
      : query
    let messages: [[String: String]] = [
      ["role": "system", "content": systemContent],
      ["role": "user", "content": userContent],
    ]
    return [
      "model": ModelQoS.Claude.defaultSelection,
      "max_tokens": 1024,
      "messages": messages,
      "stream": false,
    ]
  }
}
