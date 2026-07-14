// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, act, fireEvent } from '@testing-library/react'
import type { DbRecoveryStatus } from '../../../../shared/types'

// The user-facing half of DB corruption recovery. The _electron smoke
// (e2e/db-recovery.spec.mjs) proves the real IPC returns the right status, but it
// runs signed-out, so the notice itself (which lives inside the post-auth shell)
// is covered here. macOS never sets its recovery flag at all, so this surface has
// no counterpart there — these assertions are the contract.

import { DbRecoveryNotice } from './DbRecoveryNotice'

const HEALTHY: DbRecoveryStatus = {
  recovered: false,
  reset: false,
  rowsRecovered: 0,
  tablesRecovered: {},
  backupPath: null
}

// Captures the main→renderer corruption event so a test can fire it.
let fireCorruption: (() => void) | null = null
const relaunchSpy = vi.fn()

function mockStatus(status: DbRecoveryStatus | Promise<never>): void {
  fireCorruption = null
  ;(
    window as unknown as {
      omi: {
        dbRecoveryStatus: () => Promise<DbRecoveryStatus>
        onDbCorruptionDetected: (cb: () => void) => () => void
        relaunchApp: () => void
      }
    }
  ).omi = {
    dbRecoveryStatus: () =>
      status instanceof Promise ? status : Promise.resolve(status as DbRecoveryStatus),
    onDbCorruptionDetected: (cb) => {
      fireCorruption = cb
      return () => {
        fireCorruption = null
      }
    },
    relaunchApp: relaunchSpy
  }
}

// The component resolves its status in an effect; flush the microtask queue.
async function renderNotice(): Promise<void> {
  await act(async () => {
    render(<DbRecoveryNotice />)
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('DbRecoveryNotice', () => {
  it('renders nothing when the database was healthy (the overwhelmingly common case)', async () => {
    mockStatus(HEALTHY)
    await renderNotice()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('reports how many items were recovered after a successful salvage', async () => {
    mockStatus({
      recovered: true,
      reset: false,
      rowsRecovered: 1234,
      tablesRecovered: { local_conversation: 1000, rewind_frames: 234 },
      backupPath: 'C:/x/backups/omi_corrupted_20260101_120000.db'
    })
    await renderNotice()

    const notice = screen.getByRole('status')
    expect(notice.textContent).toContain('repaired')
    expect(notice.textContent).toContain('1,234 items recovered')
    // Calm, not alarming: it says the old file was kept, and asks nothing of the user.
    expect(notice.textContent).toContain('copy of the old file was saved')
  })

  it('says the database was reset when nothing could be salvaged', async () => {
    mockStatus({
      recovered: true,
      reset: true,
      rowsRecovered: 0,
      tablesRecovered: {},
      backupPath: 'C:/x/backups/omi_corrupted_20260101_120000.db'
    })
    await renderNotice()

    const notice = screen.getByRole('status')
    expect(notice.textContent).toContain('reset')
    // It must NOT claim items were recovered when none were.
    expect(notice.textContent).not.toContain('items recovered')
  })

  it('can be dismissed', async () => {
    mockStatus({
      recovered: true,
      reset: false,
      rowsRecovered: 5,
      tablesRecovered: { local_conversation: 5 },
      backupPath: null
    })
    await renderNotice()

    expect(screen.queryByRole('status')).not.toBeNull()
    fireEvent.click(screen.getByLabelText('Dismiss'))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('stays silent if the status channel fails — never breaks the app shell', async () => {
    mockStatus(Promise.reject(new Error('no such handler')) as Promise<never>)
    await renderNotice()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('says the data is untouched when corruption was confirmed but not repaired', async () => {
    // The boot-loop / never-worse paths: we deliberately did NOT rebuild. The copy
    // must not imply anything was lost, because nothing was.
    mockStatus({
      recovered: false,
      reset: false,
      rowsRecovered: 0,
      tablesRecovered: {},
      backupPath: null,
      unrepairable: true,
      damagedTables: ['rewind_frames']
    })
    await renderNotice()

    const notice = screen.getByRole('status')
    expect(notice.textContent).toContain('could not repair it safely')
    expect(notice.textContent).toContain('Nothing has been deleted')
    expect(notice.textContent).not.toContain('reset')
  })

  describe('the runtime trip (a live query hit corruption this session)', () => {
    it('prompts for a restart, honestly — the repair happens on relaunch, nothing is lost yet', async () => {
      mockStatus(HEALTHY)
      await renderNotice()
      expect(screen.queryByRole('status')).toBeNull() // silent until it happens

      await act(async () => {
        fireCorruption?.()
      })

      const notice = screen.getByRole('status')
      expect(notice.textContent).toContain('Restart Omi')
      expect(notice.textContent).toContain('repair the database automatically')
      // Must NOT imply data loss — the repair has not even run yet.
      expect(notice.textContent).toContain('still on disk')
    })

    it('restarts the app when the button is clicked', async () => {
      mockStatus(HEALTHY)
      await renderNotice()
      await act(async () => {
        fireCorruption?.()
      })

      fireEvent.click(screen.getByRole('button', { name: 'Restart Omi' }))
      expect(relaunchSpy).toHaveBeenCalledOnce()
    })
  })
})
