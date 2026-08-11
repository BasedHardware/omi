import { useEffect } from 'react'
import { callAgentLLM } from '../../lib/agentLLM'
import type { AiCloneIncomingMessageEvent } from '../../../../shared/types'

// Track 2 (AI clone) — the renderer half of the Beeper auto-reply loop. Main
// (ipc/aiClone.ts) polls Beeper, finds new inbound messages on opted-in
// chats, and builds a draft prompt — but the actual model call stays here,
// on the SAME authenticated path typed chat already uses (callAgentLLM),
// rather than main holding its own LLM credentials for this one feature.
//
// Mounted once, app-wide (mirrors ChatBridgeHost / TrayStateHost): no UI,
// just a persistent listener so drafting keeps working regardless of which
// page is showing.

// Serializes draftAndSubmit calls PER CHAT. If one poll finds multiple new
// messages in the same chat, each triggers its own independent LLM call, and
// nothing otherwise guarantees they finish in the order the messages
// actually arrived — in an auto-send chat, a faster call for a NEWER message
// could reach aiCloneSubmitDraft (and get sent) before an OLDER message's
// still-in-flight call does, scrambling the conversation from the
// recipient's point of view. Chaining onto a per-chat tail promise keeps one
// chat's messages processed one at a time, in arrival order, while different
// chats still run fully in parallel with each other.
const chatProcessingQueues = new Map<string, Promise<void>>()

function enqueueForChat(event: AiCloneIncomingMessageEvent): void {
  const previous = chatProcessingQueues.get(event.chatID) ?? Promise.resolve()
  // draftAndSubmit never rejects (its own try/catch swallows failures), so
  // chaining with .then() is safe — one message failing can't break the
  // chain for whatever's queued after it in the same chat.
  const next = previous.then(() => draftAndSubmit(event))
  chatProcessingQueues.set(event.chatID, next)
}

export function AiCloneDraftHost(): null {
  useEffect(() => {
    return window.omi.onAiCloneIncomingMessage((event: AiCloneIncomingMessageEvent) => {
      enqueueForChat(event)
    })
  }, [])

  return null
}

async function draftAndSubmit(event: AiCloneIncomingMessageEvent): Promise<void> {
  try {
    const draftText = (await callAgentLLM(event.promptText)).trim()
    // Still submit even when the model returned nothing — decideReplyAction
    // treats a blank draft as 'skip' either way, but calling submitDraft is
    // what tells main this message was actually processed (advances the
    // read cursor, releases the in-flight marker). Returning early here
    // instead would leave the message looking un-processed until the
    // in-flight staleness fallback eventually retries it.
    await window.omi.aiCloneSubmitDraft({
      chatID: event.chatID,
      chatDisplayName: event.chatDisplayName,
      incomingMessageText: event.incomingMessageText,
      messageID: event.messageID,
      messageTimestamp: event.messageTimestamp,
      sessionGeneration: event.sessionGeneration,
      draftText
    })
  } catch (error) {
    // A failed draft call (LLM error, IPC error) means main never hears back
    // for this message — it deliberately stays "in flight" rather than being
    // marked processed, so the poll loop's staleness fallback retries it on
    // a later tick instead of silently losing it. Never surface this as a
    // user-facing error — there's no chat thread for a background auto-reply
    // failure to land in.
    console.log(`[aiClone] failed to draft a reply for chat ${event.chatID}: ${String(error)}`)
  }
}
