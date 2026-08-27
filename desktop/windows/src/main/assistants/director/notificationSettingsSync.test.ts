import { describe, it, expect, beforeEach } from 'vitest'
import {
  NotificationSettingsSyncCoordinator,
  backoffDelayMs,
  type NotificationSettingsSyncDeps,
  type NotificationSettingsPair
} from './notificationSettingsSync'

let signedIn: boolean
let local: NotificationSettingsPair
let revision: number
let pending: boolean
let getResults: Array<{ enabled: boolean; frequency: number } | Error>
let patches: Array<Record<string, unknown>>
let patchFails: number
let retryTimers: Array<{ fn: () => void; ms: number }>
let writes: Array<{ enabled: boolean; frequency: number }>

function makeDeps(): NotificationSettingsSyncDeps {
  return {
    signedIn: () => signedIn,
    readLocal: () => local,
    writeLocal: (pair) => {
      writes.push(pair)
      local = { enabled: pair.enabled, frequency: pair.frequency }
    },
    journal: {
      revision: () => revision,
      pending: () => pending,
      begin: () => {
        revision += 1
        pending = true
        return revision
      },
      complete: (rev) => {
        if (rev === revision) pending = false
      }
    },
    http: {
      get: async () => {
        const next = getResults.shift()
        if (next === undefined) throw new Error('unexpected GET')
        if (next instanceof Error) throw next
        return next
      },
      patch: async (body) => {
        patches.push(body)
        if (patchFails > 0) {
          patchFails -= 1
          throw new Error('patch failed')
        }
        return { enabled: body.enabled ?? true, frequency: body.frequency }
      }
    },
    setRetryTimer: (fn, ms) => {
      retryTimers.push({ fn, ms })
      return retryTimers.length
    },
    clearRetryTimer: () => {}
  }
}

beforeEach(() => {
  signedIn = true
  local = { enabled: true, frequency: 3 }
  revision = 0
  pending = false
  getResults = []
  patches = []
  patchFails = 0
  retryTimers = []
  writes = []
})

describe('backoffDelayMs', () => {
  it('doubles from 1s and caps at 15 minutes', () => {
    expect(backoffDelayMs(0)).toBe(1_000)
    expect(backoffDelayMs(1)).toBe(2_000)
    expect(backoffDelayMs(9)).toBe(512_000)
    expect(backoffDelayMs(10)).toBe(900_000)
    expect(backoffDelayMs(50)).toBe(900_000)
  })
})

describe('NotificationSettingsSyncCoordinator', () => {
  it('hydrates from the server when nothing is pending and the revision held', async () => {
    const coordinator = new NotificationSettingsSyncCoordinator(makeDeps())
    getResults = [{ enabled: false, frequency: 5 }]
    await coordinator.reconcile()
    expect(writes).toEqual([{ enabled: false, frequency: 5 }])
  })

  it('preserves local state when a mutation is pending, re-enqueuing the push', async () => {
    const deps = makeDeps()
    const coordinator = new NotificationSettingsSyncCoordinator(deps)
    const rev = deps.journal.begin()
    getResults = [{ enabled: false, frequency: 5 }]
    await coordinator.reconcile()
    // No hydrate; the pending local pair was pushed instead.
    expect(writes).toEqual([])
    await Promise.resolve()
    expect(patches).toEqual([{ enabled: true, frequency: 3 }])
    expect(pending).toBe(false)
    expect(rev).toBe(1)
  })

  it('pushes the complete local pair and completes only on a matching revision', async () => {
    const deps = makeDeps()
    const coordinator = new NotificationSettingsSyncCoordinator(deps)
    const rev = deps.journal.begin()
    // A newer mutation lands before the push completes.
    deps.journal.begin()
    await coordinator.enqueue(local, rev)
    expect(patches.length).toBe(1)
    // Completion with the stale revision keeps pending set (the newest pair
    // still needs a push) and schedules the retry loop.
    expect(pending).toBe(true)
    expect(retryTimers.length).toBe(1)
  })

  it('omits enabled from the PATCH when the master key was never locally set', async () => {
    const deps = makeDeps()
    const coordinator = new NotificationSettingsSyncCoordinator(deps)
    const rev = deps.journal.begin()
    await coordinator.enqueue({ enabled: null, frequency: 3 }, rev)
    expect(patches).toEqual([{ frequency: 3 }])
  })

  it('failed pushes schedule capped-backoff retries that re-read the local pair', async () => {
    const deps = makeDeps()
    const coordinator = new NotificationSettingsSyncCoordinator(deps)
    const rev = deps.journal.begin()
    patchFails = 1
    await coordinator.enqueue(local, rev)
    expect(retryTimers.length).toBe(1)
    expect(retryTimers[0].ms).toBe(1_000)

    // The retry fires, re-reads local, pushes, and completes.
    local = { enabled: false, frequency: 4 }
    retryTimers[0].fn()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(patches.at(-1)).toEqual({ enabled: false, frequency: 4 })
    expect(pending).toBe(false)
  })

  it('a failed GET with a pending push schedules a retry instead of hydrating', async () => {
    const deps = makeDeps()
    const coordinator = new NotificationSettingsSyncCoordinator(deps)
    deps.journal.begin()
    getResults = [new Error('offline')]
    await coordinator.reconcile()
    expect(writes).toEqual([])
    expect(retryTimers.length).toBe(1)
  })
})
