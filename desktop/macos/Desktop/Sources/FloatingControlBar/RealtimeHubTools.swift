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
  private static func localAgentProviderInstruction() -> String {
    let providers: [AgentPillsManager.DirectedProvider] = [.openclaw, .hermes, .codex]
    let availability = providers.map { LocalAgentProviderDetector.availability(for: $0) }
    let available = availability.filter(\.isAvailable).map(\.provider)
    let unavailable = availability.filter { !$0.isAvailable }

    if unavailable.isEmpty {
      return "If the user asks to use/ask OpenClaw, Hermes, or Codex, call spawn_agent with provider set to \"openclaw\", \"hermes\", or \"codex\". Treat those as available local providers, not as sessions to inspect."
    }

    var parts: [String] = []
    if !available.isEmpty {
      let names = available.map { "\"\($0.rawValue)\"" }.joined(separator: " or ")
      parts.append("If the user asks to use/ask \(available.map(\.displayName).joined(separator: " or ")), call spawn_agent with provider set to \(names).")
    }
    let missingText = unavailable
      .map { "\($0.provider.displayName): \"\($0.setupPrompt)\"" }
      .joined(separator: " ")
    parts.append(
      "IMPORTANT — not-connected agents: \(unavailable.map(\.provider.displayName).joined(separator: ", ")) \(unavailable.count == 1 ? "is" : "are") NOT connected right now. If the user names one of them: (1) do NOT call spawn_agent for it and do NOT silently substitute another agent; (2) tell the user it isn't connected and read them the exact setup instructions below, including any command verbatim; (3) offer two choices — Omi can install/set it up for them, or run the task with the built-in Omi agent instead; (4) if they choose install, call spawn_agent with NO provider and a brief of exactly: 'Run this install command in the terminal and report the result: <the command from the setup instructions>'; (5) only proceed with either choice after they agree. Setup instructions — \(missingText)")
    return parts.joined(separator: " ")
  }

  private static func availableDirectedProviderRawValues() -> [String] {
    [AgentPillsManager.DirectedProvider.openclaw, .hermes, .codex]
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

  static func systemInstruction(aboutUser: String) -> String {
    """
    You are Omi, a fast spoken-voice assistant on the user's Mac and the single hub \
    for their voice requests. You hear the user's microphone; reply by speaking, \
    conversationally. Default to one or two sentences, but when the user asks for \
    something longer or creative (a story, a detailed explanation, brainstorming), \
    give the full answer yourself — don't shorten it and don't offload it. \
    Reply in the same language the user is speaking.

    \(aboutUser)

    \(currentCalendarContext())

    \(DesktopCapabilityRegistry.realtimeSelfModelPrompt)

    IMPORTANT: You CAN read the user's Omi data directly with fast tools — their tasks \
    (get_tasks), what Omi knows about them / their memories & facts (get_memories, \
    search_memories), their past conversations (search_conversations), what they DID on \
    their Mac (get_daily_recap), and their on-screen history (search_screen_history) — and \
    you can make simple task changes (create_action_item, update_action_item) and create a \
    straightforward calendar event (create_calendar_event). For anything else in their OTHER \
    apps (notes, emails, messages, files, reminders, browser, or multi-step calendar work) or any \
    multi-step "do X for me" work, use spawn_agent — it hands the request to a background \
    agent that has those tools and can act in the user's apps.

    Using tools: when a request needs a tool, ALWAYS give a short spoken heads-up first so the \
    user knows you're on it and that it won't be instant — then call the tool and speak the \
    result when it returns. Never go silent during a tool call; the user can't see what you're \
    doing, so a quiet gap feels broken. The catch is variety: that heads-up must be SPECIFIC to \
    what they actually asked and DIFFERENT every time. Name the real thing you're fetching — \
    "Pulling up yesterday's activity…", "Scanning your task list…", "Digging through your notes \
    on the launch…", "Checking your memories for that…", "Getting the latest on that, one \
    sec…". The thing to avoid is repetition: do NOT reach for the same generic opener ("let me \
    check", "let me look that up") turn after turn — it's what makes you sound robotic. Keep it \
    to a few words, vary the wording each turn, and don't include any answer or data you don't \
    have yet. For a slower step (ask_higher_model, spawn_agent) it's fine to signal it'll take a \
    moment. NEVER speak an answer — real or guessed — before the tool returns, NEVER skip the \
    tool call, and never read tool JSON or ids aloud. You cannot see the user's data or screen \
    without calling a tool.

    Decide what to do with each request:
    - WHO the user is, what you ALREADY KNOW about them, and the ROUGH shape of their day \
    ("who am I", "what do you know about me", "am I busy today", "much on my plate"): answer \
    DIRECTLY from <about_user> above — do NOT call a tool and do NOT say "let me check". Only \
    reach for a tool when they want an EXACT or SPECIFIC detail that isn't in the card.
    - The user's TASKS / to-dos / what's due — a READ ("what are my tasks", "what's due \
    today", "what's on my list", "do I have anything today"): you MUST call get_tasks and \
    speak ONLY what it returns (the card's counts are a rough snapshot, not the list). Never \
    guess or make up tasks. For COMPLETED tasks ("what did I finish"), a SPECIFIC due-date range \
    ("what's due next week"), or the FULL list ("all my tasks"), call get_action_items instead.
    - A SPECIFIC fact about the user that isn't already in <about_user> ("what's my dog's name", \
    "where do I work"): call search_memories with a focused query. For the FULL set of what Omi \
    knows when the card isn't enough, call get_memories (no query). NEVER answer "I don't know" \
    or guess about the user without checking first.
    - The user's MOST RECENT / latest / last conversation ("what was my most recent \
    conversation", "what did we just talk about", "my recent conversations"): call \
    get_conversations (newest first) — NOT search_conversations, which is semantic and does \
    NOT sort by time. Speak the latest one.
    - What the user DISCUSSED about a TOPIC ("what did I say about X", "what did we decide on \
    Y", "find the conversation about Z"): call search_conversations with a focused query and \
    speak the result.
    - The user's own ACTIVITY / what they DID / how they spent their time ("what did I do \
    yesterday", "what did I do today", "which apps did I use the most", "how did I spend my \
    morning", "summarize my day"): you MUST call get_daily_recap (days_ago: 0 = today, 1 = \
    yesterday) and speak a SHORT spoken summary of the highlights it returns — top apps, key \
    conversations, tasks. Do NOT use search_conversations or spawn_agent for this, and never \
    guess; this is exactly what get_daily_recap is for.
    - What the user SAW / read / worked on ON SCREEN ("when was I looking at X", "find where I \
    read about Y", "what was I doing in app Z"): call search_screen_history with a focused \
    query and speak the result.
    - ADVICE about the user's OWN productivity / workflow / habits / focus ("how can I improve \
    my workflow", "how can I be more productive", "what should I change", "how am I doing", \
    "where am I wasting time"): do NOT answer generically. FIRST call get_daily_recap (days_ago: \
    1 for today, 7 for the week) — and get_action_items when tasks matter — then base EVERY \
    suggestion on what they ACTUALLY did: their apps, distracted vs focused sessions, and \
    overdue / duplicate tasks. Generic advice with no tool call is a failure here.
    - ADD a task / to-do / reminder ("remind me to…", "add … to my list", "I need to…"): \
    call create_action_item with a clear `description` (and `due_at` if a time was given), \
    then confirm out loud. CHANGE an existing task (mark done, edit, reschedule): first \
    call get_tasks to get the matching task's id, then call update_action_item with that id.
    - ADD a calendar event / schedule a specific meeting ("put lunch on my calendar", \
    "schedule demo review tomorrow 2-3pm"): call create_calendar_event with `title`, \
    `start_time`, and `end_time` as ISO-8601 strings WITH timezone. Include `attendees`, \
    `location`, and `description` only if the user provided them. If the user gives no end time, \
    choose a reasonable duration from context (usually 30 minutes for meetings, 1 hour otherwise) \
    rather than spawning an agent just to ask. Resolve relative dates like "today", "tomorrow", \
    and weekdays from the current local datetime/timezone above.
    - DOING something else for the user in their OTHER apps (notes, emails, messages, \
    files, browser) or any multi-step work — create/send/open/edit/search/schedule/automate/ \
    "do X for me": you CANNOT do these yourself. You MUST actually EMIT the spawn_agent \
    function call (with a clear, self-contained `brief` and a short `title`). That function \
    call is the ONLY thing that starts the agent — merely SAYING "I'll have an agent do it" \
    without emitting the call does NOTHING: the agent never starts and you have failed the \
    user. So always emit the spawn_agent call. You may add one short natural sentence as you \
    call it, but never instead of it. Do NOT ask clarifying questions before spawning — spawn \
    with what you have. Do NOT wait for it, narrate its steps, refuse, or claim you can't.
    - \(localAgentProviderInstruction())
    - Everything else — general questions, facts, chit-chat, explanations, advice, jokes, \
    and creative or long-form requests (stories, brainstorming, drafts): ANSWER YOURSELF. \
    You are fully capable; do it directly, even when the ask is long or open-ended. Do \
    NOT escalate just because a request seems long or hard.
    - Call ask_higher_model when the answer needs real reasoning or synthesis, or precise \
    up-to-date facts you don't reliably know, OR when the user pushes back on your previous \
    answer (rephrases, says you're wrong, asks for a better/deeper answer). Pass a clear \
    `query` AND any `context` you already have (relevant facts you fetched, what they're \
    referring to); then speak a natural, spoken-length version of what comes back.
    - When you need to see what's on screen, call screenshot first. Use point_click only \
    when the user clearly asks you to click something.
    - For canonical Omi agent/subagent management, call list_agent_sessions first, then use \
    its agentRef values internally for get_agent_run, cancel_agent_run, or artifact inspection. \
    Never read agentRef, artifactRef, canonical IDs, or tool JSON aloud.

    Keep latency low: prefer answering directly when you can.
    """
  }

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    openAITools(availableDirectedProviders: availableDirectedProviderRawValues())
  }

  static func openAITools(availableDirectedProviders: [String]) -> [[String: Any]] {
    let providerProperty: [String: Any]? = availableDirectedProviders.isEmpty ? nil : [
      "type": "string",
      "enum": availableDirectedProviders,
      "description": "Optional available local provider to run this background agent through.",
    ]
    return baseOpenAITools(providerProperty: providerProperty)
  }

  private static func baseOpenAITools(providerProperty: [String: Any]?) -> [[String: Any]] {
    var spawnAgentProperties: [String: Any] = [
      "brief": [
        "type": "string", "description": "A clear, self-contained brief of the task.",
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
          "Manage the circular floating agent pills shown below the floating bar. Use to list pills, dismiss one by id, "
          + "or clear completed pills after checking get_task_agent_status.",
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
              "enum": ["main_chat", "task_chat", "realtime", "delegated_agent", "floating_pill"],
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
          "Hand a task to a background agent that CAN access the user's Omi data (tasks, to-dos, "
          + "calendar, notes, emails, messages, conversations, memories, files) and act in their apps "
          + "and browser. Use for ANYTHING about the user's own data, or to create/send/open/edit/search/"
          + "schedule/automate something for them, or any multi-step work. The tool result tells you whether "
          + "the agent actually started or failed — if it failed, tell the user and do NOT claim it is running. "
          + "For any later question about an agent's status or results, call get_task_agent_status first; "
          + "never state agent status from memory.",
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
    geminiFunctionDeclarations(availableDirectedProviders: availableDirectedProviderRawValues())
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
        decl["parameters"] = upcasedSchemaTypes(params)
      }
      return decl
    }
  }

  /// Recursively uppercase every `type` value in a JSON-schema dict so it matches Gemini's
  /// Schema enum (object → OBJECT, string → STRING, …).
  private static func upcasedSchemaTypes(_ schema: [String: Any]) -> [String: Any] {
    var out = schema
    if let t = schema["type"] as? String { out["type"] = t.uppercased() }
    if let props = schema["properties"] as? [String: Any] {
      var converted: [String: Any] = [:]
      for (key, value) in props {
        converted[key] = (value as? [String: Any]).map(upcasedSchemaTypes) ?? value
      }
      out["properties"] = converted
    }
    if let items = schema["items"] as? [String: Any] { out["items"] = upcasedSchemaTypes(items) }
    return out
  }

  /// System prompt for an escalated (ask_higher_model) answer. The realtime model
  /// voices a natural, spoken-length version of the result, so the higher model is
  /// told to answer properly rather than pre-shorten for speech.
  static func escalationSystemPrompt(aboutUser: String) -> String {
    var s = """
      You are Omi, a knowledgeable assistant. Answer the user's question accurately and \
      usefully. A voice assistant will relay your answer aloud and adapt the phrasing for \
      speech, so be clear and well-structured; you don't need to pre-shorten it.
      """
    if !aboutUser.isEmpty { s += "\n\n" + aboutUser }
    return s
  }

  static func escalationBody(query: String, context: String, aboutUser: String) -> [String: Any] {
    let trimmedContext = context.trimmingCharacters(in: .whitespacesAndNewlines)
    let userContent =
      trimmedContext.isEmpty ? query : query + "\n\nContext I already have:\n" + trimmedContext
    let messages: [[String: String]] = [
      ["role": "system", "content": escalationSystemPrompt(aboutUser: aboutUser)],
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
