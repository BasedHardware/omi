// Post-update "what's new" surface (Phase 8). Mirrors the macOS WhatsNewToast:
// compare the running build to the last version we showed notes for, and — only
// when it INCREASED (a real update, not a fresh install) — surface the changes in
// the shared acrylic toast window, then record the version so it never nags again.
//
// Changelog source: fragments under changelog/unreleased/ (same schema as
// desktop/macos/changelog/unreleased/*.json). Until the Windows fragment
// consolidation script lands, import the notes we intend to surface this build.
import { app } from 'electron'
import { getAppSettings, setAppSettings } from './appSettings'
import phase8Fragment from '../../changelog/unreleased/2026-07-phase-8-windows-redesign.json'
import chatRefreshFragment from '../../changelog/unreleased/2026-08-chat-panel-background-refresh.json'
import type { WhatsNewPayload } from '../shared/types'

// Fragment schema: { "changes": string[] } or { "change": string }.
function changesFromFragment(fragment: unknown): string[] {
  const raw = fragment as { changes?: string[]; change?: string }
  if (Array.isArray(raw.changes)) return raw.changes
  if (typeof raw.change === 'string') return [raw.change]
  return []
}

const CHANGES: string[] = [
  ...changesFromFragment(phase8Fragment),
  ...changesFromFragment(chatRefreshFragment),
]

/** Decide whether to show the what's-new toast this launch, advancing the stored
 *  marker as a side effect so it fires at most once per version. Returns the
 *  payload to show, or null (fresh install baseline, same version, or no notes). */
export function maybeGetWhatsNew(): WhatsNewPayload | null {
  const current = app.getVersion()
  const stored = getAppSettings().lastShownChangelogVersion
  if (stored === current) return null // already shown for this build
  // Advance the marker regardless, so we never re-prompt for this version.
  setAppSettings({ lastShownChangelogVersion: current })
  // Fresh install / first run after this feature shipped: baseline silently — the
  // user hasn't "updated" into these notes, so don't surface them.
  if (stored === null) return null
  if (CHANGES.length === 0) return null
  return { version: current, changes: CHANGES }
}

/** GitHub releases page for the "View release notes" action (the update feed is
 *  BasedHardware/omi — see electron-builder.yml publish). */
export function releaseNotesUrl(): string {
  return 'https://github.com/BasedHardware/omi/releases'
}
