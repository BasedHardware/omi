import Foundation

// MARK: - Realtime Hub tool surface
//
// The realtime model IS the router: instead of a separate Haiku classify() call,
// the model decides what to do by choosing a tool. The same four tools are
// declared to both providers (OpenAI Realtime `tools`, Gemini `functionDeclarations`);
// `RealtimeHubController` executes them by calling EXISTING app code / endpoints.

enum HubTool: String {
  /// Escalate a hard / knowledge-heavy question to the smarter Claude model via
  /// the existing prompt-cached /v2/chat/completions, then speak its answer.
  case askHigherModel = "ask_higher_model"
  /// Hand a multi-step task to a background agent (existing AgentBridge / pills).
  /// Non-blocking: the model acknowledges and moves on.
  case spawnAgent = "spawn_agent"
  /// Read the user's tasks locally (TasksStore) and return them inline to speak — a
  /// fast synchronous READ, NOT a background agent.
  case getTasks = "get_tasks"
  /// Capture the user's screen so the model can see what they're looking at.
  case screenshot = "screenshot"
  /// Click at on-screen coordinates (local).
  case pointClick = "point_click"
}

enum RealtimeHubTools {

  static let systemInstruction = """
    You are Omi, a fast spoken-voice assistant on the user's Mac and the single hub \
    for their voice requests. You hear the user's microphone; reply by speaking, \
    conversationally. Default to one or two sentences, but when the user asks for \
    something longer or creative (a story, a detailed explanation, brainstorming), \
    give the full answer yourself — don't shorten it and don't offload it. \
    Always reply in English.

    IMPORTANT: You have NO direct access to the user's personal data or their apps. \
    You cannot see their tasks, to-dos, calendar, notes, emails, messages, past \
    conversations, memories, files, or reminders on your own. The spawn_agent tool \
    CAN — it hands the request to a background agent that has all of those tools and \
    can act in the user's apps and browser.

    Using tools: the moment a request needs a tool, briefly acknowledge it OUT LOUD in your \
    own natural, varied words (keep it short, and don't include any answer or data you don't \
    have yet), then immediately call the tool. For a data tool (get_tasks, ask_higher_model), \
    speak its result after it returns. NEVER put an answer — real or guessed — in that \
    acknowledgment, NEVER skip the tool call, and never read tool JSON aloud. You cannot see \
    tasks, data, or the screen without calling a tool.

    Decide what to do with each request:
    - The user's TASKS / to-dos / what's due — a READ ("what are my tasks", "what's due \
    today", "what's on my list", "do I have anything today"): you MUST call get_tasks and \
    speak ONLY what it returns. You CANNOT see their tasks any other way — never guess, \
    summarize from memory, or make up tasks. Always call get_tasks; do NOT use an agent.
    - DOING something for the user, or their OTHER personal data (calendar, notes, emails, \
    messages, conversations, memories, files, reminders) — create/send/open/edit/search/ \
    schedule/automate/"do X for me"/any multi-step work: you CANNOT do these yourself. You \
    MUST actually EMIT the spawn_agent function call (with a clear, self-contained `brief`). \
    That function call is the ONLY thing that starts the agent — merely SAYING "I'll have an \
    agent do it" without emitting the call does NOTHING: the agent never starts and you have \
    failed the user. So always emit the spawn_agent call. You may add one short natural \
    sentence as you call it, but never instead of it. Do NOT ask clarifying questions before \
    spawning — spawn with what you have. Do NOT wait for it, narrate its steps, refuse, or \
    claim you can't.
    - Everything else — general questions, facts, chit-chat, explanations, advice, jokes, \
    and creative or long-form requests (stories, brainstorming, drafts): ANSWER YOURSELF. \
    You are fully capable; do it directly, even when the ask is long or open-ended. Do \
    NOT escalate just because a request seems long or hard.
    - Call ask_higher_model in ONLY two cases: (1) the user is unhappy with your previous \
    answer — they push back, rephrase, say you're wrong, or ask for a better/deeper/more \
    thorough answer; or (2) you genuinely need precise, up-to-date facts (current events, \
    specific numbers) you don't reliably know. Pass a clear `query`, then speak the result.
    - When you need to see what's on screen, call screenshot first. Use point_click only \
    when the user clearly asks you to click something.

    Keep latency low: prefer answering directly when you can.
    """

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    [
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
            "query": ["type": "string", "description": "The full question to escalate."]
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
        "name": HubTool.spawnAgent.rawValue,
        "description":
          "Hand a task to a background agent that CAN access the user's Omi data (tasks, to-dos, "
          + "calendar, notes, emails, messages, conversations, memories, files) and act in their apps "
          + "and browser. Use for ANYTHING about the user's own data, or to create/send/open/edit/search/"
          + "schedule/automate something for them, or any multi-step work. Returns immediately; the agent works on its own.",
        "parameters": [
          "type": "object",
          "properties": [
            "brief": [
              "type": "string", "description": "A clear, self-contained brief of the task.",
            ]
          ],
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

  /// Gemini Live `setup.tools[0].functionDeclarations` entries (same surface).
  static var geminiFunctionDeclarations: [[String: Any]] {
    openAITools.map { tool in
      // Gemini wants {name, description, parameters} without the OpenAI "type" wrapper.
      var decl: [String: Any] = [
        "name": tool["name"] as? String ?? "",
        "description": tool["description"] as? String ?? "",
      ]
      if let params = tool["parameters"] as? [String: Any] { decl["parameters"] = params }
      return decl
    }
  }
}
