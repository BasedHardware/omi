// Track 2 (AI clone) — pure prompt construction for drafting a reply in the
// user's voice. No network, no LLM call: the renderer already owns the
// authenticated model call path (useChat.ts's callAgentLLM), the same split
// aiUserProfile/service.ts uses (main does the data assembly, renderer holds
// the session and does the call). This module just builds the messages array.
//
// Grounding: the persona comes from the existing once-daily "AI User Profile"
// synthesis (getLatestProfileText(), assistants/aiUserProfile/service.ts) —
// this reuses that infra rather than inventing a second persona source.

export type PromptMessage = { role: 'system' | 'user'; content: string }

export interface DraftContextMessage {
  /** Display name of who sent it ("User" is handled via `isSelf`, don't pass
   *  it here). */
  senderName: string
  text: string
  isSelf: boolean
}

export interface BuildDraftPromptInput {
  /** getLatestProfileText() — null when no profile has been generated yet. */
  personaProfileText: string | null
  chatDisplayName: string
  /** Recent context, oldest first. Keep this short (last handful of
   *  messages) — the point is tone/continuity, not a full transcript. */
  history: DraftContextMessage[]
  incomingMessage: DraftContextMessage
}

const SYSTEM_PROMPT = `You are drafting a reply that will be sent from the user's own messaging account, in their voice — the recipient must not be able to tell it was AI-assisted.

RULES:
- Match the user's likely tone and brevity based on the conversation history and profile below. Real text/chat replies are usually short — a sentence or two, not an essay.
- Only use facts present in the profile or the conversation. Never invent plans, availability, prices, or commitments the user hasn't already stated.
- Never commit the user to anything involving money, contracts, medical/legal matters, or relationship decisions — if the incoming message asks for one of those, write a short holding reply instead ("let me check and get back to you" style), don't make the call yourself.
- If you genuinely don't have enough information to reply sensibly, start the reply with [NEEDS_INPUT] followed by a one-line note on what's missing, instead of guessing.
- Output ONLY the reply text itself — no quotation marks, no "Reply:" prefix, no explanation.`

export function buildDraftPrompt(input: BuildDraftPromptInput): PromptMessage[] {
  const persona = input.personaProfileText?.trim()
    ? input.personaProfileText.trim()
    : 'No profile information is available yet for this user.'

  const historyLines = input.history
    .map((m) => `${m.isSelf ? 'User' : m.senderName}: ${m.text}`)
    .join('\n')

  const incomingLabel = input.incomingMessage.isSelf ? 'User' : input.incomingMessage.senderName

  const userContent = [
    `Chat: ${input.chatDisplayName}`,
    `What we know about the user:\n${persona}`,
    historyLines ? `Recent conversation (oldest first):\n${historyLines}` : undefined,
    `New message to reply to, from ${incomingLabel}:\n${input.incomingMessage.text}`,
    "Draft the user's reply now, as a single short message in their voice."
  ]
    .filter((line): line is string => Boolean(line))
    .join('\n\n')

  return [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: userContent }
  ]
}

/** True when a drafted reply asked for human input rather than guessing —
 *  the caller should always route this to the review queue regardless of the
 *  chat's reply mode, never auto-send it. */
export function draftNeedsInput(draftText: string): boolean {
  return draftText.trim().startsWith('[NEEDS_INPUT]')
}
