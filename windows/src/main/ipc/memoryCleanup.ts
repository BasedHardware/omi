import { ipcMain, net, type IpcMainInvokeEvent } from 'electron'
import { classifyStatus, backoffMs, type DeleteOutcome } from '../memoryCleanup/bulkDelete'

// Bulk-delete memories from the main process so the job survives renderer
// navigation / reloads and never blocks the UI thread. The renderer passes the
// API base + a fresh Firebase token + the ids to remove; we drain them with a
// small worker pool, retrying 429/5xx with backoff, and stream progress back.

export type BulkDeleteArgs = { baseURL: string; token: string; ids: string[] }
export type BulkDeleteResult = { deleted: number; failed: number; firstError?: string }

const CONCURRENCY = 4
const MAX_ATTEMPTS = 6
const PROGRESS_EVERY = 25
const REQUEST_TIMEOUT_MS = 15_000

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Result of one delete, with a human-readable reason when it failed (so a wall
// of 0-deleted has an explanation — wrong status, expired token, network).
type DeleteResult = { outcome: DeleteOutcome; reason?: string }

async function deleteOne(baseURL: string, token: string, id: string): Promise<DeleteResult> {
  let lastReason = ''
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    let outcome: DeleteOutcome
    let retryAfter: string | null = null
    // Electron's net.fetch uses Chromium's network stack (proxy/TLS aware) — the
    // same path the renderer's axios uses successfully. Node's global fetch
    // stalled here. AbortController caps a hung request so it can't block a worker.
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
    try {
      const res = await net.fetch(`${baseURL}/v3/memories/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
        signal: ctrl.signal
      })
      outcome = classifyStatus(res.status)
      retryAfter = res.headers.get('retry-after')
      if (outcome !== 'ok' && outcome !== 'gone') {
        const body = await res.text().catch(() => '')
        lastReason = `HTTP ${res.status} ${body.slice(0, 160)}`.trim()
      }
    } catch (e) {
      outcome = 'retry'
      lastReason = `network: ${(e as Error).message}`
    } finally {
      clearTimeout(timer)
    }
    if (outcome === 'ok' || outcome === 'gone') return { outcome }
    if (outcome === 'fail') return { outcome, reason: lastReason }
    if (attempt < MAX_ATTEMPTS) await sleep(backoffMs(attempt, retryAfter))
  }
  return { outcome: 'fail', reason: lastReason }
}

export function registerMemoryCleanupHandlers(): void {
  ipcMain.handle(
    'memories:bulkDelete',
    async (e: IpcMainInvokeEvent, args: BulkDeleteArgs): Promise<BulkDeleteResult> => {
      const { baseURL, token } = args
      // Defensive dedupe: if the analyze pagination ever repeats a page, the id
      // list can contain duplicates that would inflate the "total".
      const ids = [...new Set(args.ids)]
      let deleted = 0
      let failed = 0
      let cursor = 0
      let firstError = ''

      const emit = (done = false): void => {
        if (!e.sender.isDestroyed()) {
          e.sender.send('memories:deleteProgress', { deleted, failed, total: ids.length, done })
        }
      }

      const worker = async (): Promise<void> => {
        while (cursor < ids.length) {
          const id = ids[cursor++]
          const { outcome, reason } = await deleteOne(baseURL, token, id)
          if (outcome === 'ok' || outcome === 'gone') deleted++
          else {
            failed++
            if (!firstError && reason) {
              firstError = reason
              // Surface the very first failure reason loudly in the terminal —
              // far easier to copy than a toast when diagnosing "0 deleted".
              console.error(`[memcleanup] delete FAILED for id=${id}: ${reason}`)
            }
          }
          if ((deleted + failed) % PROGRESS_EVERY === 0) emit()
        }
      }

      console.log(`[memcleanup] starting: ${ids.length} ids, baseURL=${baseURL}, token.len=${token.length}`)
      await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()))
      console.log(`[memcleanup] done: deleted=${deleted} failed=${failed}${firstError ? ` firstError="${firstError}"` : ''}`)
      emit(true)
      return { deleted, failed, firstError: firstError || undefined }
    }
  )
}
