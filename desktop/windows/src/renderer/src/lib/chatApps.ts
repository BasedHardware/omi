// Shared helpers for "apps" (Omi marketplace apps) that act on chat.
//
// macOS/mobile parity: an installed app whose capabilities include 'chat' or
// 'persona' can be SELECTED as a chat target. The selection is sent to the
// backend as `POST /v2/messages?app_id=<id>` (a query param, mirroring the
// Flutter `sendMessageStreamServer(text, appId:)` path). When no app is
// selected the user is talking to base Omi.
import { omiApi } from './apiClient'
import type { AppDetailEntry } from './appDetail'

// Subset of the `/v1/apps` catalog entry we care about for chat. The catalog
// returns more (rating, installs, price…), but only these drive persona chat.
export type CatalogApp = {
  id: string
  name?: string
  image?: string | null
  capabilities?: string[]
  enabled?: boolean
}

/** macOS `App.works_with_chat()` — selectable as a chat persona/assistant. */
export function worksWithChat(app: CatalogApp): boolean {
  const caps = app.capabilities
  if (!Array.isArray(caps)) return false
  return caps.includes('chat') || caps.includes('persona')
}

/**
 * Build the chat-message endpoint URL. With a selected app the id rides as the
 * `app_id` query param (the backend reads `app_id`/`plugin_id` from the query,
 * not the body); without one it's the base Omi target.
 */
export function chatMessagesUrl(base: string, appId: string | undefined): string {
  const url = `${base}/v2/messages`
  return appId ? `${url}?app_id=${encodeURIComponent(appId)}` : url
}

export type AppResult = { app_id?: string; content: string }

/**
 * Coerce a conversation's raw `apps_results` into a clean list, dropping
 * entries with no usable content. Tolerant of missing/garbage input so a weird
 * server payload can't crash the conversation view.
 */
export function normalizeAppResults(raw: unknown): AppResult[] {
  if (!Array.isArray(raw)) return []
  const out: AppResult[] = []
  for (const r of raw) {
    if (!r || typeof r !== 'object') continue
    const content = (r as { content?: unknown }).content
    if (typeof content !== 'string' || !content.trim()) continue
    const appId = (r as { app_id?: unknown }).app_id
    out.push({ app_id: typeof appId === 'string' ? appId : undefined, content })
  }
  return out
}

// ── Catalog cache ─────────────────────────────────────────────────────────
// One in-memory fetch of the apps catalog, shared by the chat persona picker
// (needs enabled chat-capable apps) and the conversation view (resolves an
// app_id → display name). Cached for the renderer's lifetime; the picker can
// force-refresh after the user installs/removes apps.
let catalogCache: Promise<CatalogApp[]> | null = null

export function fetchAppCatalog(force = false): Promise<CatalogApp[]> {
  if (force) catalogCache = null
  if (!catalogCache) {
    catalogCache = omiApi
      .get<CatalogApp[]>('/v1/apps', { params: { include_reviews: false } })
      .then((r) => (Array.isArray(r.data) ? r.data : []))
      .catch(() => {
        // Don't poison the cache on a transient failure — let the next call retry.
        catalogCache = null
        return []
      })
  }
  return catalogCache
}

// Full (reduced) apps list — every display field the Apps tab and the per-app
// detail page need EXCEPT reviews/thumbnail_urls (those are fetched per-app).
// Cached so the Apps list and the detail page share ONE network round-trip:
// api.omi.me's /v1/apps is slow (~seconds), so re-fetching the whole catalog on
// every app open made each detail page crawl. Force-refresh on user "Refresh".
let appsFullCache: Promise<AppDetailEntry[]> | null = null

export function fetchAppsFull(force = false): Promise<AppDetailEntry[]> {
  if (force) appsFullCache = null
  if (!appsFullCache) {
    appsFullCache = omiApi
      .get<AppDetailEntry[]>('/v1/apps', { params: { include_reviews: false } })
      .then((r) => (Array.isArray(r.data) ? r.data : []))
      .catch(() => {
        appsFullCache = null // don't poison the cache on a transient failure
        return []
      })
  }
  return appsFullCache
}

/**
 * Enabled, chat-capable apps, for the persona picker. An app counts as enabled
 * if the catalog entry says so OR its id is in `/v1/apps/enabled` — the same
 * separate id-list the Apps page relies on, since the catalog's per-user
 * `enabled` flag isn't always populated.
 */
export async function fetchChatApps(force = false): Promise<CatalogApp[]> {
  const [apps, enabledIds] = await Promise.all([
    fetchAppCatalog(force),
    omiApi
      .get<string[]>('/v1/apps/enabled')
      .then((r) => new Set(Array.isArray(r.data) ? r.data : []))
      .catch(() => new Set<string>())
  ])
  return apps.filter((a) => (a.enabled || enabledIds.has(a.id)) && worksWithChat(a))
}

/** Resolve an app id to its display name from the cached catalog (best-effort). */
export async function getAppName(appId: string): Promise<string | undefined> {
  const apps = await fetchAppCatalog()
  return apps.find((a) => a.id === appId)?.name
}
