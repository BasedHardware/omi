import type { ReactNode } from 'react'
import type { XStatus, XRunState } from '../../../../../../shared/types'

// Pure view derivation for the X (Twitter) connector row — kept out of XConnector.tsx
// so that component file only exports a component (React Fast Refresh requirement),
// and so the row-state logic stays unit-testable without mounting the component.

export function friendlyError(err?: string): string {
  if (err === 'x_oauth_not_configured' || err === 'unknown' || err === 'no_auth_url')
    return "X connector isn't configured on the server yet."
  if (err === 'timeout')
    return 'Timed out waiting for X. Finish the sign-in in your browser, then try again.'
  return err ?? 'Something went wrong.'
}

export type XView = { state: 'connected' | 'busy' | 'idle'; description: ReactNode }

// Precedence: an in-flight run drives the view; otherwise the connection status.
export function deriveView(status: XStatus | null, run: XRunState): XView {
  if (run.phase === 'connecting')
    return {
      state: 'busy',
      description: 'Waiting for X sign-in… you can close this panel; Omi keeps importing.'
    }
  if (run.phase === 'syncing')
    return {
      state: 'busy',
      description: `Saved ${run.postCount} post${run.postCount === 1 ? '' : 's'} · ${run.memoryCount} memor${run.memoryCount === 1 ? 'y' : 'ies'} so far…`
    }
  const connected = status?.connected || run.phase === 'succeeded'
  if (connected) {
    const handle = status?.handle ?? run.handle
    const posts = status?.postCount ?? run.postCount
    const mems = status?.memoryCount ?? run.memoryCount
    return {
      state: 'connected',
      description: `Connected${handle ? ` as @${handle}` : ''} · ${posts} post${posts === 1 ? '' : 's'}, ${mems} memor${mems === 1 ? 'y' : 'ies'}`
    }
  }
  if (run.phase === 'failed') return { state: 'idle', description: friendlyError(run.error) }
  return {
    state: 'idle',
    description: 'Connect your X account so Omi learns from your tweets and bookmarks.'
  }
}
