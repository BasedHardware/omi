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
export function AiCloneDraftHost(): null {
  useEffect(() => {
    return window.omi.onAiCloneIncomingMessage((event: AiCloneIncomingMessageEvent) => {
      void draftAndSubmit(event)
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
