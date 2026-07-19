// Shared-thread agent cards (B4, INV-CHAT-1) — main-side materialization + IPC.
//
// A background agent spawned from a chat/voice surface leaves EXACTLY TWO durable
// artifacts on the producing surface's kernel conversation: an agentSpawn card at
// launch and one agentCompletion card at terminal. This module is the always-alive
// writer: it subscribes to the kernel event stream (mirroring mainChat.ts) and, on
// a background run's launch (`run.queued`) and terminal (`run.succeeded/failed/
// cancelled`), asks the kernel to materialize the corresponding card. Both writes
// are idempotent on runId (agentThreadCards.ts), so a duplicate/retried terminal
// still yields exactly one completion.
//
// Keeping the writer in main (not the bar renderer's pill poll) means the two
// authoritative cards land regardless of which windows are open — the renderer
// then projects them via `agentCards:get` on load and the live `agentCards:event`.
// Card projection is a pure observer: any failure is swallowed so it can never
// destabilize the kernel event loop or a chat turn.

import { BrowserWindow, ipcMain } from 'electron'
import { controlPlaneOwnerId, getAgentRuntimeKernel } from '../agentKernel/controlPlane'
import type { MaterializedAgentCard } from '../agentKernel/agentThreadCards'
import type { AgentThreadCardMsg } from '../../shared/types'

/** Kernel run-lifecycle event types that mean a background run reached terminal. */
const TERMINAL_RUN_EVENT_TYPES = new Set(['run.succeeded', 'run.failed', 'run.cancelled'])

function toMsg(card: MaterializedAgentCard): AgentThreadCardMsg {
  return { chatId: card.chatId, createdAtMs: card.record.createdAtMs, block: card.record.block }
}

function broadcast(card: MaterializedAgentCard): void {
  const msg = toMsg(card)
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send('agentCards:event', msg)
  }
}

let subscribed = false

export function registerAgentCardHandlers(): void {
  const kernel = getAgentRuntimeKernel()

  // Subscribe exactly once — the kernel singleton outlives this call.
  if (!subscribed) {
    subscribed = true
    kernel.subscribe((event) => {
      try {
        const runId = event.runId
        if (typeof runId !== 'string' || !runId) return
        if (event.type === 'run.queued') {
          const card = kernel.materializeAgentSpawnCard(runId)
          if (card) broadcast(card)
        } else if (TERMINAL_RUN_EVENT_TYPES.has(event.type)) {
          const card = kernel.materializeAgentCompletionCard(runId)
          if (card) broadcast(card)
        }
      } catch {
        // Observer only — never let a card write destabilize the event loop.
      }
    })
  }

  // Renderer projection read: the shared-thread cards for a main_chat thread. Read
  // on chat load so a completion that landed while this window was closed still
  // shows. Owner is host state (control-plane owner), never renderer-asserted.
  ipcMain.handle('agentCards:get', (_e, chatId: unknown): AgentThreadCardMsg[] => {
    const resolvedChatId = typeof chatId === 'string' && chatId.trim() ? chatId.trim() : 'default'
    try {
      return getAgentRuntimeKernel()
        .listAgentThreadCardsForMainChat(controlPlaneOwnerId(), resolvedChatId)
        .map((record) => ({
          chatId: resolvedChatId,
          createdAtMs: record.createdAtMs,
          block: record.block
        }))
    } catch {
      return []
    }
  })
}
