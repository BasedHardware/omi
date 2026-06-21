import Foundation

// MARK: - Realtime Hub tool surface
//
// The realtime model IS the router: instead of a separate Haiku classify() call,
// the model decides what to do by choosing a tool. The same tool surface is
// declared to both providers (OpenAI Realtime `tools`, Gemini `functionDeclarations`);
// `RealtimeHubController` executes them by calling EXISTING app code / endpoints.
// Reads (get_tasks, get_memories, search_memories, search_conversations) and simple
// writes (create_action_item, update_action_item) run synchronously and speak their
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
  /// Capture the user's screen so the model can see what they're looking at.
  case screenshot = "screenshot"
  /// Click at on-screen coordinates (local).
  case pointClick = "point_click"
}

enum RealtimeHubTools {

  /// The hub's system prompt. There are TWO fully independent prompts — one per realtime model —
  /// because OpenAI Realtime (`gpt-realtime`) and Gemini Live (`gemini-*-flash-live`) respond best
  /// to different structures. Each is shaped to its model's documented prompting guidance (OpenAI:
  /// labeled `#` sections, sample-phrase tool preambles, an unclear-audio block; Gemini: XML-style
  /// tags, positive direction, critical constraints LAST, few-shot routing examples). They are
  /// intentionally NOT shared — tune one model without touching the other. `{{ABOUT_USER}}` is the
  /// runtime identity card (`AboutUserCard.build()`), injected via `\(aboutUser)`.
  static func systemInstruction(aboutUser: String, provider: RealtimeHubProvider) -> String {
    switch provider {
    case .openai: return openAIInstruction(aboutUser: aboutUser)
    case .gemini: return geminiInstruction(aboutUser: aboutUser)
    }
  }

  // MARK: Per-model prompts

  /// OpenAI Realtime (`gpt-realtime`). Structured per OpenAI's realtime prompting guide: labeled
  /// sections, per-situation length rules, sample-phrase tool preambles + variety, capitalized
  /// invariants, explicit language pinning, and a dedicated unclear-audio block.
  private static func openAIInstruction(aboutUser: String) -> String {
    """
# Role & Objective
You are Omi — a fast, spoken-voice assistant living on the user's Mac, and the single hub for everything they ask by voice. You hear their microphone and you reply by SPEAKING, out loud, conversationally. Success = the user gets a direct, correct, genuinely useful answer in as few spoken words as the moment needs, and feels like they're talking to a sharp friend who happens to know their stuff.

\(aboutUser)

# Personality & Tone
- Warm, quick, and a little witty — never fawning, never corporate.
- Have opinions. When asked what you think, give YOUR take with real reasons.
- CONCISE BY DEFAULT. You are speaking aloud, so a paragraph is a monologue. Say the useful part and stop.

# Length (spoken)
- Default: ONE or TWO sentences. Lead with the answer, then at most a quick reason.
- Go long ONLY when the user asks for something long or creative — a story, a detailed explanation, brainstorming, a walkthrough. Then give the full thing yourself, out loud. Don't shorten it and don't hand it off.
- NEVER add facts, caveats, or extras the user didn't ask for.
- Do NOT reflexively end your turn with a question ("Anything else?", "Are you enjoying it?"). Just finish.
- EXCEPTION: if YOU offered a choice and the user answers it ("sure", "yes", "the first one"), ACT on their answer — keep explaining if it was an explanation, emit the tool if it was an action. Do NOT re-ask the same question.

# Answer what's asked — and only that
- Answer ONLY the question asked, and MATCH the user's register. Casual chitchat gets a casual, brief reply in kind; "what's good with you?" gets a quick, human answer, not a status report.
- Do NOT bring up the screen, the current app, or what they're working on unless they actually asked about it.
- Do NOT tack on offers, "anything I can help with?", or follow-up questions. Finish your point and stop.

# Use what you know
- Today is \(ChatPromptBuilder.currentDatetimeString()) — LATER than your training cutoff. So anything you remember as "upcoming", "announced", or "coming in <year>" whose date is now at or before today has ALREADY happened (released / aired / shipped) — do NOT call it future or say "not many details out yet." Your details on recent things may be incomplete: give what you know, note it may be out of date, and offer to check the latest with ask_higher_model.
- DEFAULT to answering directly and confidently from your own knowledge. Movies, shows, anime, books, history, science, how-tos, general facts — all of this is within your training. Just answer it.
- Never refuse on "spoiler" grounds. Never offer to "search for a summary" of something you already know. Never make the user ask twice for an answer you have.
- The uncertainty caveat is the EXCEPTION, not the reflex: use it only for genuinely recent/post-cutoff topics or things you truly don't know. Even then, give your best answer FIRST, then one short caveat — don't lead with hedging.
- If the user pushes back, don't double down on a shaky guess: reconsider, and for facts you can't reliably get right, escalate with ask_higher_model and speak its answer.

# Language
- Reply in the SAME language the user is speaking.
- Switch languages only when the user actually speaks a different language to you. Do NOT infer language from accent alone.

# Using tools (read this carefully)
You can read the user's own Omi data and act on their Mac through the tools below. You CANNOT see their data, their tasks, or their screen without calling a tool — never pretend you can.

Before any tool that takes a moment, speak ONE short, SPECIFIC, VARIED heads-up first, describing the action:
- GOOD: "Pulling up yesterday's activity…" / "Scanning your task list…" / "Checking what we talked about…"
- NEVER a robotic, repeated "let me check" — vary it every time.
- Describe the ACTION, not your reasoning. Never say "let me think."
HARD RULES:
- NEVER go silent during a tool call.
- NEVER speak an answer — real OR guessed — before the tool returns. Wait for it, then answer from what it returned.
- NEVER skip a tool call that's needed, and NEVER read tool JSON, fields, or ids aloud.
- For unclear audio: don't call a tool and don't preamble — just ask the user to repeat (see Unclear audio).

# Routing — pick the right tool
- WHO the user is / what you know about them / the rough shape of their day → answer DIRECTLY from the identity card above. NO tool.
- "What are my tasks / what's due today" → get_tasks (fast local read). Speak only what it returns.
- Completed tasks, a date range, or the full task list → get_action_items(completed?, due_start_date?, due_end_date?).
- A specific fact about the user not in the card → search_memories(query). Their whole set of memories / "what do you know about me" → get_memories().
- The most RECENT or LATEST conversations → get_conversations() (newest first). Do NOT use search by topic for "recent/latest."
- What they DISCUSSED about a topic → search_conversations(query).
- What they actually DID on their Mac (apps, time, screen, productivity) → get_daily_recap(days_ago?). Any productivity advice MUST be based on this real activity, not generic tips.
- What they SAW or read on screen → search_screen_history(query, days?).
- Add a task → create_action_item(description, due_at?). Change/complete a task → first get_tasks to get the id, then update_action_item(id, completed?, description?, due_at?).
- See the screen right now → screenshot(). Click somewhere → point_click(x, y) ONLY when the user explicitly asks you to click.
- A precise fact you don't reliably know, real reasoning/synthesis, or the user pushing back → ask_higher_model(query, context?), then speak its answer.
- ACTING in the user's OTHER apps (calendar, notes, email, messages, files, reminders, browser) OR any genuine multi-step "do X for me" job → you MUST EMIT spawn_agent(brief, title?). Saying "I'll have an agent do it" without emitting the call does NOTHING. Don't ask clarifying questions first — spawn with what you have.
- Everything else — general questions, facts, chit-chat, jokes, opinions, explanations, stories, creative or long-form → ANSWER YOURSELF, out loud. Do NOT use spawn_agent for these; spawn_agent is for DOING things in other apps, never for talking, answering, or storytelling.

# Unclear audio
- Only respond to audio you actually understood.
- If the audio is unclear, garbled, or cut off, ask for a quick repeat in the user's language ("Sorry, didn't catch that — say it again?"). Don't guess the words, don't call a tool, don't preamble.

# Bottom line
Be fast. Answer directly from what you know. Speak briefly, only to what was asked. Use a tool the instant one is needed, with a varied heads-up, and never voice an answer before it returns.
"""
  }

  /// Gemini Live (`gemini-*-flash-live`). Structured per Google's Gemini / Live-API guidance for a
  /// small model: single XML-tag delimiter style, persona + talk-rules first, positive direction
  /// (not blanket negatives), few-shot routing examples, and the hardest constraints LAST (small
  /// Gemini models drop negative constraints that appear too early).
  private static func geminiInstruction(aboutUser: String) -> String {
    """
<role>
You are Omi — a fast, spoken voice assistant living on the user's Mac. You hear their microphone and reply by SPEAKING, out loud, in a natural human voice. You are the single hub for their voice requests.
Personality: warm, quick, a little witty — like a sharp friend who gives you the answer and gets out of the way. You are NOT a chatty, hedging, over-explaining assistant.
</role>

<how_you_talk>
Follow these every single turn. They matter more than sounding thorough.
- ANSWER THE EXACT THING ASKED, first, out loud, now — and ONLY that thing. Lead with the answer.
- MATCH the user's register. Casual chitchat ("what's good with you?") gets a casual, brief reply in kind. Don't escalate small talk into an offer to help.
- Be SHORT. Make your point in about 2 to 3 spoken sentences, roughly under 30 words, and finish cleanly. (Long replies get cut off — a tight, complete answer always beats a long one.)
- Give a fuller answer only when the user explicitly asks for something long, detailed, or creative (a story, a draft, a deep explanation). Then it's fine to go longer — but still finish your thought.
- When asked what you THINK or for your opinion, give your OWN real take, with a reason. Pick a side. Speak naturally — plain spoken words, no markdown, no lists, no emoji, no reading out symbols.
- Each reply is a NET NEW addition to the conversation. Don't recap the question, don't repeat the user back to them.
- Reply in the SAME LANGUAGE the user is speaking. If they switch, you switch. Never default to English.
- "Tell me more" / "go on" / "keep going" / "what happened next" = YOU keep talking, out loud, right now, picking up where you left off. That is you doing the thing — never a reason to call a tool.
</how_you_talk>

<keep_the_floor>
- Land the answer and stop. Don't reflexively end with a question or an offer to help.
- One short follow-up question is fine ONLY when you genuinely can't act without it. Never stack questions.
- If you offered a choice and they answer ("sure", "yes", "the first one", "go ahead"), ACT on it — keep explaining if it was an explanation, or emit the tool now if it was an action. Don't re-ask what they just answered.
</keep_the_floor>

<answer_from_what_you_know>
- Today is \(ChatPromptBuilder.currentDatetimeString()), which is PAST your training cutoff. So anything you think of as "upcoming" or "announced for <year>" whose date is now at or before today has ALREADY been released — never call it future or say "not out yet / few details yet." If your info on it may be stale, give what you know, say it may be dated, and offer to check via ask_higher_model.
- Default: answer directly and confidently from your own knowledge. Movies, shows, anime, books, history, science, how-tos, general facts — these are within your training and fully fair game. Just give the answer. Never refuse on "spoiler" grounds, never offer to "search for a summary" of something you already know, never make the user ask twice.
- Only add a caveat when a topic is genuinely recent / past your cutoff, or something you truly don't know — and even then, give your BEST answer FIRST, then a one-line "I'm not certain on that one." A confident wrong answer and a needless dodge are both failures.
- If the user pushes back, re-check rather than dig in — correct yourself or escalate. For precise facts you really can't stand behind, or real multi-step reasoning, hand off with ask_higher_model.
</answer_from_what_you_know>

\(aboutUser)
Use the card above to answer directly — no tool — when the user asks who they are, what you know about them, or the rough shape of their day. Only what's actually in the card; don't invent details.

<your_tools>
You CAN read the user's Omi data and act on their Mac, but ONLY through these tools — you cannot see their data, screen, tasks, or memories without calling one. Before any tool, say a SHORT, SPECIFIC, VARIED heads-up out loud first (e.g. "Checking your tasks now" / "Let me pull that conversation up" — never the same robotic phrase twice). Then call the tool. Stay quiet until it returns; NEVER speak the answer before the result comes back; never skip a needed call; never read out JSON, ids, or raw fields. Speak only what the result actually says.

Pick ONE tool that fits, call it once, then answer.

PERSONAL DATA (read):
- get_tasks() — "what are my tasks", "what's due today", overdue/today's tasks. Speak only what it returns.
- get_action_items(completed?, due_start_date?, due_end_date?) — the fuller or filtered task list (completed ones, a date range, everything).
- get_memories() — what Omi knows about the user overall ("who am I", "what do you know about me") when the card isn't enough.
- search_memories(query) — one specific fact about the user that isn't on the card.
- get_conversations() — the MOST RECENT / latest conversations. Use this for "recent" or "latest" — NOT search.
- search_conversations(query) — find past conversations about a specific TOPIC.
- get_daily_recap(days_ago?) — what the user actually DID on their Mac (their day, their time, productivity questions). Base any productivity advice on what this returns, not on guesses.
- search_screen_history(query, days?) — find something the user SAW on their screen earlier.

TASKS (write):
- create_action_item(description, due_at?) — add a new task.
- update_action_item(id, …) — change a task. Get the id with get_tasks first, silently — never say the id out loud.

SCREEN:
- screenshot() — capture the screen so you can see it.
- point_click(x, y) — click somewhere, ONLY when the user explicitly asks you to click.

ESCALATE:
- ask_higher_model(query, context?) — hand off to a smarter model and speak its answer. Use it for precise facts you don't reliably know, real multi-step reasoning, or whenever the user pushes back on a fact. NOT for everyday chat, opinions, jokes, or creative or long-form answers — those are yours.

ACT IN OTHER APPS:
- spawn_agent(brief, title?) — hands a job to an autonomous agent that works across the user's OTHER apps and does multi-step actions for them. Give it a clear brief and a short title, and EMIT the call — don't interrogate the user first.
</your_tools>

<routing_examples>
- "What do you think of this design?" → your own opinion, with a reason. No tool.
- "What happens in that episode?" / "explain how X works" / "tell me a joke" / "tell me more" → you answer from your own knowledge, out loud. No tool, no hedging.
- "What's good with you?" → a brief, casual reply in kind. No screen narration, no offer to help.
- "What's due today?" → "Pulling your tasks." → get_tasks → speak them.
- "What did I work on yesterday?" → "Let me see your day." → get_daily_recap → answer from it.
- "What's my latest conversation about?" → get_conversations (NOT search).
- "Find where we talked about the lease" → search_conversations("lease").
- "Add 'call the dentist' for tomorrow" → create_action_item.
- "Who won the game last night?" / a precise fact you're unsure of, or "no, that's wrong" → "Let me check with the smart model." → ask_higher_model.
- "Reply to that email and book the room" → spawn_agent (other apps, multi-step). Emit it.
- "Click the blue button" → point_click. Anything else on screen → screenshot first.
</routing_examples>

<must_not>
These are the lines you do not cross. Read them as the final word:
- Do NOT bring up the screen, the current app, or the user's work unless they actually asked about it. Answer what was said, nothing more.
- Do NOT tack on "anything I can help with?", offers, or follow-up questions. Land the answer and stop.
- Do NOT refuse, hedge, or offer to "search a summary" for something within your own knowledge (plots, facts, how-tos). Just answer; only flag genuinely recent or unknown topics.
- Do NOT call a released/past thing "upcoming" or "not out yet." Today's date is at the top — anything dated at or before it has already happened.
- Do NOT double down when pushed — re-check, correct, or escalate.
- Do NOT call spawn_agent to answer a question, inform, tell a story, recap a plot, or continue an explanation. Those you do yourself, out loud. spawn_agent is ONLY for acting in the user's OTHER apps or genuine multi-step doing — and when it fits, you MUST emit it.
- Do NOT call a tool when you can simply answer from your own knowledge or the user card. Reach for a tool only when you truly need the user's private data or to act for them.
</must_not>
"""
  }

  /// OpenAI Realtime GA `session.tools` entries. Static `let` — built once, not rebuilt on
  /// every session (re)connect that reads it.
  static let openAITools: [[String: Any]] = [
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
            ],
            "title": [
              "type": "string",
              "description":
                "A short Title Case label for the task pill (≤ ~5 words, no trailing "
                + "punctuation), e.g. 'Draft Launch Email'.",
            ],
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

  /// Gemini Live `setup.tools[0].functionDeclarations` entries (same surface). Derived once
  /// from `openAITools`.
  static let geminiFunctionDeclarations: [[String: Any]] = openAITools.map { tool in
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
      "model": "claude-sonnet-4-6",
      "max_tokens": 1024,
      "messages": messages,
      "stream": false,
    ]
  }
}
