// @vitest-environment jsdom
// Regression suite for the onboarding discovery step.
//
// The bug this locks down: the step kicked `indexFilesScan()` unconditionally on
// mount. It re-mounts on every renderer reload (the main process reloads a
// crashed renderer — GPU crashes do that on this hardware) and on a relaunch
// that resumes onboarding here, so the user watched the full disk walk run a
// SECOND time. The index lives in the main process and outlives the component:
// a finished one must be reused, and one still running must be waited out (a
// re-entrant scan call returns the *incomplete* status, which would have shown
// "0 files indexed").
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, act } from '@testing-library/react'
import { BuildProfileStep } from './BuildProfileStep'
import type { FileIndexStatus, IndexedAppRecord } from '../../../../shared/types'

const indexFilesScan = vi.fn()
const indexFilesStatus = vi.fn()
const indexFilesApps = vi.fn()
const addAppNodes = vi.fn()

vi.mock('../../lib/onboardingGraph', () => ({
  addAppNodes: (apps: unknown) => addAppNodes(apps)
}))
vi.mock('../../lib/appMemories', () => ({ runAppIndexing: vi.fn(async () => {}) }))

const app = (name: string): IndexedAppRecord => ({
  name,
  path: `C:/Start Menu/${name}.lnk`,
  modifiedAt: 1,
  targetPath: `C:/Program Files/${name}/${name}.exe`
})

const status = (patch: Partial<FileIndexStatus> = {}): FileIndexStatus => ({
  filesIndexed: 0,
  byType: {},
  lastRunAt: null,
  lastDurationMs: null,
  running: false,
  ...patch
})

const renderStep = (): void => {
  render(<BuildProfileStep stepIndex={6} totalSteps={14} onContinue={vi.fn()} />)
}

/** Let pending promises settle and drive `ms` of the poll timer. */
const tick = async (ms = 0): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  indexFilesScan.mockReset().mockResolvedValue(status({ filesIndexed: 1234 }))
  indexFilesStatus.mockReset().mockResolvedValue(status())
  indexFilesApps.mockReset().mockResolvedValue([app('Slack'), app('Figma')])
  addAppNodes.mockReset()
  ;(window as unknown as { omi: unknown }).omi = {
    indexFilesScan,
    indexFilesStatus,
    indexFilesApps
  }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('BuildProfileStep', () => {
  it('scans once on a fresh profile and reveals the count', async () => {
    renderStep()
    await tick()

    expect(indexFilesScan).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Your workspace is mapped')).toBeTruthy()
    expect(screen.getByText('1,234 files indexed')).toBeTruthy()
    const revealed = (addAppNodes.mock.calls[0][0] as { name: string }[]).map((a) => a.name)
    expect(revealed.sort()).toEqual(['Figma', 'Slack'])
  })

  it('does NOT re-scan when the index already exists (the "it ran twice" bug)', async () => {
    indexFilesStatus.mockResolvedValue(status({ filesIndexed: 18711, lastRunAt: 1 }))

    renderStep()
    await tick()

    expect(indexFilesScan).not.toHaveBeenCalled()
    expect(screen.getByText('Your workspace is mapped')).toBeTruthy()
    expect(screen.getByText('18,711 files indexed')).toBeTruthy()
    // The app nodes are still (idempotently) re-revealed on the map.
    expect(addAppNodes).toHaveBeenCalledTimes(1)
  })

  it('waits out a scan already running in the main process instead of starting another', async () => {
    indexFilesStatus
      .mockResolvedValueOnce(status({ running: true }))
      .mockResolvedValueOnce(status({ running: true }))
      .mockResolvedValue(status({ filesIndexed: 900, running: false, lastRunAt: 2 }))

    renderStep()
    await tick()
    expect(screen.getByText('Scanning your projects and apps')).toBeTruthy()

    await tick(1500) // poll ticks until the main-process scan reports done
    expect(indexFilesScan).not.toHaveBeenCalled()
    expect(screen.getByText('900 files indexed')).toBeTruthy()
  })
})
