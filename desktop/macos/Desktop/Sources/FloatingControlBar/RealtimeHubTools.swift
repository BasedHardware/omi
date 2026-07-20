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
  /// Install/repair a local agent provider (consent required), optionally
  /// dispatching the user's original task to it once setup succeeds.
  case setupAgentProvider = "setup_agent_provider"
  /// Capture the user's screen so the model can see what they're looking at.
  case screenshot = "screenshot"
  /// Click at on-screen coordinates (local).
  case pointClick = "point_click"
}

enum RealtimeHubTools {
  // KNOWN LIMITATION: this provider availability snapshot (and the tool enums
  // derived from it) is built once when the realtime session's system
  // instruction / tools are assembled at session start. If an agent is
  // installed mid-session (via install-assist), the model keeps seeing the old
  // "not connected" guidance until the session reconnects and these are
  // rebuilt. The spawn-time availability check is always live, so a directed
  // spawn still works; only the model's guidance lags until reconnect.
  private static func localAgentProviderInstruction() -> String {
    let providers: [AgentPillsManager.DirectedProvider] = [.openclaw, .hermes, .codex]
    let availability = providers.map { LocalAgentProviderDetector.availability(for: $0) }
    let available = availability.filter(\.isAvailable).map(\.provider)
    let unavailable = availability.filter { !$0.isAvailable && !LocalAgentProviderInstaller.canAutoInstall($0.provider) }
    let autoInstallable = availability.filter { !$0.isAvailable && LocalAgentProviderInstaller.canAutoInstall($0.provider) }.map(\.provider)

    if unavailable.isEmpty {
      return "If the user asks to use/ask OpenClaw, Hermes, or Codex, call spawn_agent with provider set to \"openclaw\", \"hermes\", or \"codex\". Treat those as available local providers, not as sessions to inspect. \(bestProviderSelectionInstruction(for: providers))"
    }

    var parts: [String] = []
    if !available.isEmpty {
      let names = available.map { "\"\($0.rawValue)\"" }.joined(separator: " or ")
      parts.append("If the user asks to use/ask \(available.map(\.displayName).joined(separator: " or ")), call spawn_agent with provider set to \(names).")
      parts.append(bestProviderSelectionInstruction(for: available))
    }
    let missingText = unavailable
      .map { "\($0.provider.displayName): \"\($0.setupPrompt)\"" }
      .joined(separator: " ")
    parts.append(
      "IMPORTANT — not-connected agents: \(unavailable.map(\.provider.displayName).joined(separator: ", ")) \(unavailable.count == 1 ? "is" : "are") NOT connected right now. If the user names one of them: (1) do NOT call spawn_agent for it and do NOT silently substitute another agent; (2) tell the user it isn't connected and read them the exact setup instructions below, including any command verbatim; (3) offer two choices — Omi can install/set it up for them, or run the task with the built-in Omi agent instead; (4) if they choose install, call spawn_agent with NO provider and a brief of exactly: 'Run this install command in the terminal and report the result: <the command from the setup instructions>'; (5) only proceed with either choice after they agree. Setup instructions — \(missingText)")
    return parts.joined(separator: " ")
  }

  /// Task→provider selection guidance for connected external agents: even when
  /// the user does NOT name an agent, spawn_agent should run through the one
  /// whose strengths clearly match the task. Mirrors the Haiku router's
  /// selection rules so voice-hub tasks get the same best-agent behavior.
  private static func bestProviderSelectionInstruction(
    for providers: [AgentPillsManager.DirectedProvider]
  ) -> String {
    guard !providers.isEmpty else { return "" }
    var rules: [String] = []
    if providers.contains(.codex) {
      rules.append(
        "coding — writing, creating, editing, refactoring, debugging, or running ANY code, script, or program (any language, however small) — MUST use provider \"codex\".")
    }
    if providers.contains(.hermes) {
      rules.append("open-ended autonomous research or long-form independent work fits provider \"hermes\".")
    }
    if providers.contains(.openclaw) {
      rules.append("automation flows the user has set up in OpenClaw fit provider \"openclaw\".")
    }
    let strengths = providers
      .map { "\($0.rawValue): \($0.routerBlurb)" }
      .joined(separator: " ")
    return "Provider selection when the user does NOT name an agent — match the task to a connected agent's strength: \(rules.joined(separator: " ")) For general computer/app/browser/data tasks (summaries, questions, lookups, messages, email, calendar, notes, browsing, acting in the user's apps) OMIT provider — the built-in Omi agent is the default. Connected agent strengths: \(strengths)"
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

  /// Every directed local agent Omi can hand a task to, whether or not it is
  /// installed on this Mac. Advertising the full set lets an explicit "ask
  /// codex …" utterance route through spawn_agent even when the agent is
  /// missing, so setup instructions reach the user instead of a dead end.
  static let knownDirectedProviders = ["codex", "hermes", "openclaw"]

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
    - Smart agent routing: When calling spawn_agent, pass the best installed local provider in `provider` when you know one fits. Omi also picks and falls back automatically in code. When the user explicitly requests an agent by name (e.g. \"use codex\"), always pass that provider. If the user doesn't specify one, prefer an installed provider from the list above — do NOT pick or mention providers that are not installed: \
      \(smartAgentRoutingGuidance()) \
      - Omit the provider (default) to let Omi automatically select the best installed local provider, falling back to Claude Code when no local provider is installed.
    - Auto-install: if the user asks for Codex by name and it is not installed, Omi will install it automatically (npm install -g @openai/codex) and then spawn it. You do not need to tell the user to install it themselves. For Hermes and OpenClaw, Omi will give install guidance if they are missing.
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
    // The enum always advertises every known directed agent so an explicit
    // "ask codex …" routes through spawn_agent even when the agent is not
    // installed; the description carries the installed/missing split.
    let connected = knownDirectedProviders.filter { availableDirectedProviders.contains($0) }
    let missing = knownDirectedProviders.filter { !connected.contains($0) }
    var description = "Optional local agent to run this background task through."
    if !connected.isEmpty {
      description += " Installed and ready: \(connected.joined(separator: ", "))."
    }
    if !missing.isEmpty {
      description +=
        " Not installed: \(missing.joined(separator: ", ")) — selecting one returns setup instructions to relay to the user."
    }
    let providerProperty: [String: Any] = [
      "type": "string",
      "enum": knownDirectedProviders,
      "description": description,
    ]
    return GeneratedRealtimeTools.baseOpenAITools(providerProperty: providerProperty)
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
