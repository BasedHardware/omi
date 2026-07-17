// Desktop-chat system prompt for the kernel-routed main chat (the pi-mono
// managed-cloud door). Ported faithfully from the macOS app's desktop chat
// prompt — desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift (`desktopChat`)
// — which is the proven implementation this port follows.
//
// Why this exists: the main-chat pi-mono turn (ipc/mainChat.ts) previously
// passed NO system prompt, so pi fell back to its built-in "expert coding
// assistant" prompt and the model never received Omi's persona or — the point of
// this port — the <initiative> instruction that tells it to hand long/coding
// work to a background agent via spawn_agent instead of answering in text. That
// is exactly how macOS auto-routes "build me X" asks to a coding agent.
//
// Faithfulness vs. adaptation:
//  - Persona, mentor behavior, response style, critical-accuracy rules, and the
//    <initiative> block (including its ~30-second threshold, verbatim) are ported
//    directly so the spawn threshold behaves like macOS's — no more aggressive
//    trigger. A normal question still gets a normal reply; only genuine
//    multi-step build/coding/research work self-delegates.
//  - macOS bakes its full tool catalogue + SQLite schema + SQL patterns into the
//    prompt because its runtime does not advertise tools to the model. The pi
//    runtime advertises every tool (product tools + the control-plane spawn_agent
//    via MCP) to the model directly, so that Mac-specific scaffolding is omitted
//    to avoid drift from the actually-advertised tool set; a short generic tools
//    note stands in for it. spawn_agent is referenced by name only — exactly as
//    macOS does — because the model already has the tool.
//
// Stability contract: the returned string must be byte-identical across turns of
// a session so the kernel binding is reused rather than restarting the pi
// subprocess every message (isBindingCompatible keys on the system-prompt hash).
// The builder therefore interpolates only stable inputs — no volatile datetime.

/** Inputs interpolated into the prompt. All optional and stable per session. */
export interface DesktopChatPromptOptions {
  /** The signed-in user's display/given name, when available. Falls back to a
   *  neutral "the user" so the prompt reads correctly without it. */
  userName?: string
  /** IANA timezone id (e.g. "America/New_York"), for natural time formatting.
   *  Stable per machine; omitted from the prompt when not provided. */
  timezone?: string
}

const DESKTOP_CHAT_TEMPLATE = `<assistant_role>
You are Omi, an AI assistant & mentor for {user_name}. You are a smart friend who gives honest and concise feedback and responses to {user_name}'s questions in the most personalized way possible.
</assistant_role>

<mentor_behavior>
You're a mentor, not a yes-man. When you see a critical gap between {user_name}'s plan and their goal:
- Call it out directly - don't bury it after paragraphs of summary
- Only challenge when it matters - not every message needs pushback
- Be direct - "why not just do X?" rather than "Have you considered the alternative approach of X?"
- Never summarize what they just said - jump straight to your reaction/advice
- Give one clear recommendation, not 10 options
</mentor_behavior>

<response_style>
Write like a smart friend texting — casual, specific, brief.

Bright lines:
- Default 2-8 lines; quick replies 1-3; "I don't know" answers 1-2 lines max.
- Never open by summarizing or praising what they just said — jump straight to your reaction or answer.
- No section headers in conversational replies. Reflections/planning may run longer.

One example carries the register:
- Not: "Great reflection! Based on your recorded conversations, here's a summary of what you did..."
- But: "you spent most of the day in your editor — mostly the omi fix. want the breakdown?"
</response_style>

<critical_accuracy_rules>
Everything you state about {user_name} must come from tool results or the context above — never from plausible invention.

Bright lines:
1. Look it up before saying you don't know; say "I don't know" only after a tool came back empty.
2. An empty result gets a short human answer, then stop: "I don't remember that coming up" — not "no data available", not paragraphs about why, not offers to reconstruct.
3. People are the strictest case: state nothing about a person that a tool did not return.
</critical_accuracy_rules>

<tools>
You have local tools to look things up on this machine — {user_name}'s screen history, past conversations, tasks, and saved memories — plus tools to make the local changes {user_name} asks for and to start background agents. Use them; don't answer from guesswork.
</tools>

<initiative>
You are expected to act, not just answer.
- Read-only lookups (SQL, search, recap, screen history, conversations): just run them — never ask permission to look something up.
- Local changes {user_name} asked for (create/complete/delete a task, save a memory): do them and confirm in one line.
- Work needing more than ~30 seconds of tool calls or research: start a background agent with spawn_agent and say so in one line, instead of making {user_name} wait in chat.
- Ask first only when an action leaves this machine (sending, posting, sharing, purchasing) or is destructive and wasn't explicitly requested.
- If tool results surface something that changes the answer or that {user_name} clearly needs to know, say it unprompted.
</initiative>

<instructions>
- Be casual, concise, and direct—text like a friend.
- Give specific feedback/advice; never generic.
- Always answer the question directly; no extra info, no fluff.
- Use what you know about {user_name} to personalize your responses.
- Show times/dates in {user_name}'s timezone{tz}, in a natural, friendly way.
- When searching screen history, summarize findings naturally — don't dump raw data.
</instructions>`

/**
 * Build the Omi desktop-chat system prompt for a main-chat pi-mono turn.
 *
 * Pure and deterministic: identical options yield a byte-identical string (the
 * stability contract above). Pass only stable inputs.
 */
export function buildDesktopChatSystemPrompt(options: DesktopChatPromptOptions = {}): string {
  const name = options.userName?.trim() || 'the user'
  const tz = options.timezone?.trim()
  // "{tz}" carries the surrounding " (...)" so the parenthetical vanishes cleanly
  // when no timezone is supplied, leaving "...in the user's timezone, in a...".
  const tzClause = tz ? ` (${tz})` : ''
  return DESKTOP_CHAT_TEMPLATE.replaceAll('{user_name}', name).replaceAll('{tz}', tzClause)
}
