// Data + predicate for the chat-app / persona picker (Mac ChatProvider.chatApps
// parity). The picker lets the user scope the chat to a specific installed
// app/persona; this module owns the "which apps qualify" rule and the fetch.
//
// SOURCE OF TRUTH: Mac's `worksWithChat` (APIClient.swift:3814) — an app surfaces
// in the chat-app picker when its capabilities include "chat" OR "persona". The
// list is the user's ENABLED apps filtered by that predicate (Mac's
// `fetchEnabledApps` → `chatApps = enabledApps.filter { $0.worksWithChat }`).

import { omiApi } from './apiClient'
import type { App } from './omiApi.generated'

/** A chat-capable app as the picker needs it (a thin projection of `App`). */
export interface ChatApp {
  id: string
  name: string
  /** Icon URL (backend `image`); may be empty — the picker falls back to a glyph. */
  image: string
  author: string
}

/** Mac `worksWithChat` (APIClient.swift:3814): capability "chat" OR "persona". */
export function worksWithChat(capabilities: string[] | undefined | null): boolean {
  const caps = capabilities ?? []
  return caps.includes('chat') || caps.includes('persona')
}

/** Minimal client seam so the fetch is unit-testable without the axios/Firebase
 *  module graph. Defaults to the shared `omiApi` instance. */
export interface ChatAppsClientLike {
  get: (url: string, config?: { params?: Record<string, unknown> }) => Promise<{ data: App[] }>
}

/**
 * The user's enabled chat-capable apps, for the picker. `GET /v1/apps` returns the
 * per-user app list (with the `enabled` install flag and `capabilities`); we keep
 * only enabled apps that `worksWithChat`. Failures resolve to `[]` — the picker is
 * additive and must never throw into the chat surface.
 */
export async function listChatApps(client: ChatAppsClientLike = omiApi): Promise<ChatApp[]> {
  try {
    const res = await client.get('/v1/apps', { params: { include_reviews: false } })
    const apps = Array.isArray(res.data) ? res.data : []
    return apps
      .filter((a) => a.enabled && worksWithChat(a.capabilities))
      .map((a) => ({ id: a.id, name: a.name, image: a.image ?? '', author: a.author ?? '' }))
  } catch {
    return []
  }
}
