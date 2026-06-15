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
  /// Capture the user's screen so the model can see what they're looking at.
  case screenshot = "screenshot"
  /// Click at on-screen coordinates (local).
  case pointClick = "point_click"
}

enum RealtimeHubTools {

  static let systemInstruction = """
    You are Omi, a fast spoken-voice assistant on the user's Mac and the single hub \
    for their voice requests. You hear the user's microphone; reply by speaking, \
    briefly and conversationally (one or two sentences unless asked for more).

    Decide what to do with each request:
    - Simple questions, chit-chat, quick facts you already know: answer yourself, out loud.
    - Hard, reasoning-heavy, or knowledge-current questions: call ask_higher_model with a \
    clear `query`, then speak the result it returns in your own concise words.
    - Multi-step or action tasks (writing, research, editing files, running automations, \
    "do X for me"): call spawn_agent with a clear `brief`, then tell the user you've \
    started it. Do NOT wait for it to finish and do NOT narrate its steps.
    - When you need to see the screen to answer, call screenshot first. Use point_click \
    only when the user clearly asks you to click something.

    Never read tool JSON aloud. Keep latency low: prefer answering directly when you can.
    """

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    [
      [
        "type": "function",
        "name": HubTool.askHigherModel.rawValue,
        "description":
          "Escalate a hard or knowledge-heavy question to a smarter model and get a text answer to speak.",
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
        "name": HubTool.spawnAgent.rawValue,
        "description":
          "Hand a multi-step or action task to a background agent. Returns immediately; the agent works on its own.",
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
