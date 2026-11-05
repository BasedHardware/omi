// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { OfflineAudioTab } from './OfflineAudioTab'
import { formatBytes, formatDuration } from './offlineAudioFormat'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { OfflineCaptureSettings, WalSyncSnapshot } from '../../../../../shared/types'

const walSnapshot = vi.fn()
const walGetSettings = vi.fn()
const walSetSettings = vi.fn()
const walRetry = vi.fn()
const walDiscard = vi.fn()
const walReleaseConfirmed = vi.fn()
const onWalSnapshot = vi.fn()
const toast = vi.fn()

vi.mock('../../../lib/toast', () => ({ toast: (...args: unknown[]) => toast(...args) }))

let push: (snapshot: WalSyncSnapshot) => void = () => undefined

const SETTINGS: OfflineCaptureSettings = {
  autoSync: true,
  retainEverything: false,
  retentionDays: 14,
  maxBytes: 2 * 1024 * 1024 * 1024
}

const recording = (
  over: Partial<WalSyncSnapshot['recordings'][number]> = {}
): WalSyncSnapshot['recordings'][number] => ({
  id: 'mic_1723800000',
  timerStart: 1_723_800_000,
  seconds: 90,
  device: 'mic',
  sizeBytes: 2_880_000,
  state: 'waiting',
  retryCount: 0,
  ...over
})

const snapshot = (over: Partial<WalSyncSnapshot> = {}): WalSyncSnapshot => ({
  stats: { total: 0, pending: 0, uploaded: 0, synced: 0, failed: 0, bytes: 0 },
  paused: false,
  recordings: [],
  ...over
})

const renderTab = async (): Promise<void> => {
  render(
    <SettingsSearchProvider>
      <OfflineAudioTab />
    </SettingsSearchProvider>
  )
  await waitFor(() => expect(walSnapshot).toHaveBeenCalled())
}

beforeEach(() => {
  walSnapshot.mockReset().mockResolvedValue(snapshot())
  walGetSettings.mockReset().mockResolvedValue(SETTINGS)
  walSetSettings.mockReset().mockImplementation(async (patch) => ({ ...SETTINGS, ...patch }))
  walRetry.mockReset().mockResolvedValue(undefined)
  walDiscard.mockReset().mockResolvedValue(undefined)
  walReleaseConfirmed.mockReset().mockResolvedValue(0)
  toast.mockReset()
  onWalSnapshot.mockReset().mockImplementation((cb: (s: WalSyncSnapshot) => void) => {
    push = cb
    return () => undefined
  })
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    walSnapshot,
    walGetSettings,
    walSetSettings,
    walRetry,
    walDiscard,
    walReleaseConfirmed,
    onWalSnapshot
  }
})

afterEach(() => cleanup())

describe('formatting', () => {
  it('reads sizes and durations the way a person would', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(formatBytes(3 * 1024 * 1024 * 1024)).toBe('3.0 GB')
    expect(formatDuration(45)).toBe('45s')
    expect(formatDuration(120)).toBe('2m')
    expect(formatDuration(95)).toBe('1m 35s')
  })
})

describe('OfflineAudioTab', () => {
  it('explains the feature when nothing has been kept', async () => {
    await renderTab()
    expect(screen.getByText(/its audio is kept here and uploaded/)).toBeTruthy()
  })

  it('summarises what is waiting, processing and backed up', async () => {
    walSnapshot.mockResolvedValue(
      snapshot({
        stats: { total: 3, pending: 1, uploaded: 1, synced: 1, failed: 0, bytes: 1024 * 1024 },
        recordings: [recording()]
      })
    )
    await renderTab()
    await screen.findByText(/1 waiting, 1 processing, 1 backed up\. 1\.0 MB on disk\./)
  })

  it('gives every state its own label so waiting never looks like failed', async () => {
    walSnapshot.mockResolvedValue(
      snapshot({
        recordings: [
          recording({ id: 'a', state: 'waiting' }),
          recording({ id: 'b', state: 'failed', retryCount: 3 }),
          recording({ id: 'c', state: 'uploaded' }),
          recording({ id: 'd', state: 'synced' }),
          recording({ id: 'e', state: 'corrupted' }),
          recording({ id: 'f', state: 'outsideRecoveryWindow' })
        ]
      })
    )
    await renderTab()
    await screen.findByText(/Waiting to upload/)
    expect(screen.getByText(/Upload failed/)).toBeTruthy()
    expect(screen.getByText(/Processing on Omi/)).toBeTruthy()
    // 'Backed up' also appears in the storage row's copy, so match the row.
    expect(screen.getAllByText(/^Backed up/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Audio file missing/)).toBeTruthy()
    expect(screen.getByText(/Too old to recover/)).toBeTruthy()
  })

  it('puts unfinished work above the archive', async () => {
    walSnapshot.mockResolvedValue(
      snapshot({
        recordings: [
          recording({ id: 'synced-one', state: 'synced', timerStart: 1_723_900_000 }),
          recording({ id: 'failed-one', state: 'failed' })
        ]
      })
    )
    await renderTab()
    const retryButtons = await screen.findAllByLabelText(/^Retry /)
    // The failed one is what a person opened this tab for.
    expect(retryButtons[0].getAttribute('aria-label')).toBe('Retry failed-one')
  })

  it('offers retry only where retrying can help', async () => {
    walSnapshot.mockResolvedValue(
      snapshot({
        recordings: [
          recording({ id: 'failed-one', state: 'failed' }),
          recording({ id: 'refused-one', state: 'outsideRecoveryWindow' }),
          recording({ id: 'gone-one', state: 'corrupted' })
        ]
      })
    )
    await renderTab()
    await screen.findByLabelText('Retry failed-one')
    // Retrying audio the server refused for age, or audio whose file is gone,
    // can never succeed, so the row explains instead of offering a dead button.
    expect(screen.queryByLabelText('Retry refused-one')).toBeNull()
    expect(screen.queryByLabelText('Retry gone-one')).toBeNull()
    // Deleting stays available for every row.
    expect(screen.getByLabelText('Delete refused-one')).toBeTruthy()
  })

  it('retries and discards a recording', async () => {
    walSnapshot.mockResolvedValue(snapshot({ recordings: [recording({ id: 'mic_1' })] }))
    await renderTab()
    fireEvent.click(await screen.findByLabelText('Retry mic_1'))
    await waitFor(() => expect(walRetry).toHaveBeenCalledWith('mic_1'))
    fireEvent.click(screen.getByLabelText('Delete mic_1'))
    await waitFor(() => expect(walDiscard).toHaveBeenCalledWith('mic_1'))
  })

  it('re-renders when main pushes an update', async () => {
    await renderTab()
    push(
      snapshot({
        stats: { total: 1, pending: 1, uploaded: 0, synced: 0, failed: 0, bytes: 2048 },
        recordings: [recording({ id: 'new-one', state: 'waiting' })]
      })
    )
    await screen.findByLabelText('Retry new-one')
  })

  it('says the audio is safe while the server has asked for a pause', async () => {
    walSnapshot.mockResolvedValue(snapshot({ paused: true }))
    await renderTab()
    await screen.findByText(/Your audio is safe and will upload automatically/)
  })

  it('persists the automatic upload and archive toggles', async () => {
    await renderTab()
    fireEvent.click(screen.getByLabelText('Upload automatically'))
    await waitFor(() => expect(walSetSettings).toHaveBeenCalledWith({ autoSync: false }))

    fireEvent.click(screen.getByLabelText('Keep a copy of everything'))
    await waitFor(() => expect(walSetSettings).toHaveBeenCalledWith({ retainEverything: true }))
  })

  it('explains that unconfirmed audio is never deleted to reclaim space', async () => {
    await renderTab()
    expect(
      screen.getByText(/Recordings that are not backed up yet are never deleted to make room/)
    ).toBeTruthy()
  })

  it('reports what clearing released', async () => {
    walReleaseConfirmed.mockResolvedValue(3)
    await renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Clear backed up' }))
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Cleared 3 backed up recordings'))

    walReleaseConfirmed.mockResolvedValue(0)
    fireEvent.click(screen.getByRole('button', { name: 'Clear backed up' }))
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Nothing to clear yet'))
  })
})
