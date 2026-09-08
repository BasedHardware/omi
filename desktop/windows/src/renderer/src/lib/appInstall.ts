// External-integration install helpers (faithful port of macOS AppsPage's
// handleInstall / navigateToSetup / startSetupPolling / resumeSetupPollingIfNeeded).
//
// Installing an external-integration app is attempt-first: POST enable, and only
// if that fails (the backend returns 400 "App setup is not completed" until the
// developer's own setup webhook reports done) do we open the developer's setup
// URL in the browser and poll their `setup_completed_url` until it flips. The poll
// runs every 3s for up to 100 ticks (5 min), matching macOS's native URLSession
// loop. On success we enable again.
//
// Pure + leaf: no React, no apiClient. The setup-completion check is injected so
// the state machine is unit-testable with fake timers; the page passes
// `isSetupCompleted`, which bridges to the main-process `apps:checkSetup` IPC (the
// renderer can't poll the developer's arbitrary domain directly — CORS).

import type { ExternalIntegration } from './omiApi.generated'

// macOS: worksExternally = capabilities.contains("external_integration"). Use the
// capability, NOT `external_integration != null` — a chat/persona app can carry an
// external_integration block without being an install-with-setup integration.
export function worksExternally(app: { capabilities?: Array<string> | null }): boolean {
  return (app.capabilities ?? []).includes('external_integration')
}

// The URL to open in the browser so the user can complete setup. macOS opens
// `{authSteps[0].url}?uid={uid}` when an auth step exists, else the raw
// `setupInstructionsFilePath` (with NO uid appended). Null when neither is set.
export function setupUrl(
  integration: ExternalIntegration | null | undefined,
  uid: string
): string | null {
  const stepUrl = integration?.auth_steps?.[0]?.url
  if (stepUrl) return `${stepUrl}?uid=${uid}`
  const instructions = integration?.setup_instructions_file_path
  return instructions ? instructions : null
}

// Bridge to the main-process setup-completion poll. Returns false on a missing
// url or any failure (fails closed, exactly like macOS's isAppSetupCompleted).
export async function isSetupCompleted(
  setupCompletedUrl: string | null | undefined,
  uid: string
): Promise<boolean> {
  if (!setupCompletedUrl) return false
  try {
    return await window.omi.checkAppSetup({ url: setupCompletedUrl, uid })
  } catch {
    return false
  }
}

const DEFAULT_INTERVAL_MS = 3000
const DEFAULT_MAX_TICKS = 100

export type SetupCheck = (setupCompletedUrl: string, uid: string) => Promise<boolean>

export interface SetupPollOptions {
  setupCompletedUrl: string
  uid: string
  check: SetupCheck
  onSuccess: () => void
  onTimeout?: () => void
  intervalMs?: number
  maxTicks?: number
}

// Start the setup-completion poll. Every `intervalMs` (default 3s) it runs `check`;
// on the first true it clears the timer and calls `onSuccess`; after `maxTicks`
// (default 100 → 5 min) with no success it calls `onTimeout`. Returns a cancel
// function (the page calls it on unmount and after success/timeout). A check that
// resolves after cancellation is ignored — no late enable.
export function startSetupPolling(opts: SetupPollOptions): () => void {
  const intervalMs = opts.intervalMs ?? DEFAULT_INTERVAL_MS
  const maxTicks = opts.maxTicks ?? DEFAULT_MAX_TICKS
  let ticks = 0
  let cancelled = false
  const timer = setInterval(() => {
    if (cancelled) return
    ticks += 1
    const tickAtDispatch = ticks
    void opts
      .check(opts.setupCompletedUrl, opts.uid)
      .catch(() => false)
      .then((done) => {
        if (cancelled) return
        if (done) {
          cancelled = true
          clearInterval(timer)
          opts.onSuccess()
          return
        }
        if (tickAtDispatch >= maxTicks) {
          cancelled = true
          clearInterval(timer)
          opts.onTimeout?.()
        }
      })
  }, intervalMs)
  return () => {
    cancelled = true
    clearInterval(timer)
  }
}

export interface ResumeSetupOptions {
  enabled: boolean
  worksExternally: boolean
  setupCompletedUrl: string | null | undefined
  uid: string
  check: SetupCheck
  onComplete: () => void
  startPoll: () => void
}

// Port of macOS resumeSetupPollingIfNeeded, the "user finished in the browser and
// came back" fast path. Already enabled → nothing to do. Otherwise run one
// immediate completion check: done → enable now; not done → start a background
// poll. Returns whether a background poll was started.
export async function resumeSetupIfNeeded(opts: ResumeSetupOptions): Promise<boolean> {
  if (opts.enabled) return false
  if (!opts.worksExternally || !opts.setupCompletedUrl) return false
  const done = await opts.check(opts.setupCompletedUrl, opts.uid).catch(() => false)
  if (done) {
    opts.onComplete()
    return false
  }
  opts.startPoll()
  return true
}
