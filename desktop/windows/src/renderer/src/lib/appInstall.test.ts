// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  worksExternally,
  setupUrl,
  isSetupCompleted,
  startSetupPolling,
  resumeSetupIfNeeded
} from './appInstall'
import type { ExternalIntegration } from './omiApi.generated'

describe('worksExternally', () => {
  it('is true when capabilities include external_integration', () => {
    expect(worksExternally({ capabilities: ['chat', 'external_integration'] })).toBe(true)
  })

  it('is false for a missing/empty/other capability set (not by external_integration != null)', () => {
    expect(worksExternally({ capabilities: ['chat'] })).toBe(false)
    expect(worksExternally({ capabilities: [] })).toBe(false)
    expect(worksExternally({ capabilities: null })).toBe(false)
    expect(worksExternally({})).toBe(false)
  })
})

describe('setupUrl', () => {
  it('appends ?uid= to the first auth step url', () => {
    const integration = { auth_steps: [{ name: 'Connect', url: 'https://ex.com/setup' }] }
    expect(setupUrl(integration as ExternalIntegration, 'user-1')).toBe(
      'https://ex.com/setup?uid=user-1'
    )
  })

  it('falls back to setup_instructions_file_path with NO uid appended', () => {
    const integration = { setup_instructions_file_path: 'https://ex.com/instructions' }
    expect(setupUrl(integration as ExternalIntegration, 'user-1')).toBe(
      'https://ex.com/instructions'
    )
  })

  it('prefers the auth step over instructions when both exist', () => {
    const integration = {
      auth_steps: [{ name: 'Connect', url: 'https://ex.com/setup' }],
      setup_instructions_file_path: 'https://ex.com/instructions'
    }
    expect(setupUrl(integration as ExternalIntegration, 'u')).toBe('https://ex.com/setup?uid=u')
  })

  it('is null when neither an auth step nor instructions path is present', () => {
    expect(setupUrl({ auth_steps: [] } as ExternalIntegration, 'u')).toBeNull()
    expect(setupUrl(null, 'u')).toBeNull()
    expect(setupUrl(undefined, 'u')).toBeNull()
  })
})

describe('isSetupCompleted', () => {
  const checkAppSetup = vi.fn()

  beforeEach(() => {
    checkAppSetup.mockReset()
    ;(window as unknown as { omi: { checkAppSetup: typeof checkAppSetup } }).omi = { checkAppSetup }
  })

  it('returns false without calling the IPC when the url is empty', async () => {
    expect(await isSetupCompleted(null, 'u')).toBe(false)
    expect(await isSetupCompleted('', 'u')).toBe(false)
    expect(checkAppSetup).not.toHaveBeenCalled()
  })

  it('bridges to window.omi.checkAppSetup and returns its result', async () => {
    checkAppSetup.mockResolvedValueOnce(true)
    expect(await isSetupCompleted('https://ex.com/done', 'u')).toBe(true)
    expect(checkAppSetup).toHaveBeenCalledWith({ url: 'https://ex.com/done', uid: 'u' })
  })

  it('fails closed (false) when the IPC throws', async () => {
    checkAppSetup.mockRejectedValueOnce(new Error('boom'))
    expect(await isSetupCompleted('https://ex.com/done', 'u')).toBe(false)
  })
})

describe('startSetupPolling', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('polls every 3s and fires onSuccess on the first true, then stops', async () => {
    const check = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
    const onSuccess = vi.fn()
    const onTimeout = vi.fn()

    startSetupPolling({
      setupCompletedUrl: 'https://ex.com/done',
      uid: 'u',
      check,
      onSuccess,
      onTimeout
    })

    await vi.advanceTimersByTimeAsync(3000)
    expect(check).toHaveBeenCalledTimes(1)
    expect(onSuccess).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(3000)
    await vi.advanceTimersByTimeAsync(3000)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onTimeout).not.toHaveBeenCalled()

    // No further checks after success — the timer was cleared.
    await vi.advanceTimersByTimeAsync(9000)
    expect(check).toHaveBeenCalledTimes(3)
  })

  it('gives up after 100 ticks (5 min) and fires onTimeout, not onSuccess', async () => {
    const check = vi.fn().mockResolvedValue(false)
    const onSuccess = vi.fn()
    const onTimeout = vi.fn()

    startSetupPolling({
      setupCompletedUrl: 'https://ex.com/done',
      uid: 'u',
      check,
      onSuccess,
      onTimeout
    })

    await vi.advanceTimersByTimeAsync(3000 * 100)
    expect(check).toHaveBeenCalledTimes(100)
    expect(onTimeout).toHaveBeenCalledTimes(1)
    expect(onSuccess).not.toHaveBeenCalled()

    // Timer cleared at the cap — no 101st check.
    await vi.advanceTimersByTimeAsync(3000 * 5)
    expect(check).toHaveBeenCalledTimes(100)
  })

  it('cancel() stops the poll before it ever runs', async () => {
    const check = vi.fn().mockResolvedValue(false)
    const onSuccess = vi.fn()
    const onTimeout = vi.fn()

    const cancel = startSetupPolling({
      setupCompletedUrl: 'https://ex.com/done',
      uid: 'u',
      check,
      onSuccess,
      onTimeout
    })
    cancel()

    await vi.advanceTimersByTimeAsync(3000 * 10)
    expect(check).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onTimeout).not.toHaveBeenCalled()
  })
})

describe('resumeSetupIfNeeded', () => {
  const base = {
    worksExternally: true,
    setupCompletedUrl: 'https://ex.com/done',
    uid: 'u'
  }

  it('does nothing when the app is already enabled', async () => {
    const check = vi.fn().mockResolvedValue(true)
    const onComplete = vi.fn()
    const startPoll = vi.fn()
    const resumed = await resumeSetupIfNeeded({
      ...base,
      enabled: true,
      check,
      onComplete,
      startPoll
    })
    expect(resumed).toBe(false)
    expect(check).not.toHaveBeenCalled()
    expect(onComplete).not.toHaveBeenCalled()
    expect(startPoll).not.toHaveBeenCalled()
  })

  it('enables immediately (no poll) when the one-shot check is already done', async () => {
    const check = vi.fn().mockResolvedValue(true)
    const onComplete = vi.fn()
    const startPoll = vi.fn()
    const resumed = await resumeSetupIfNeeded({
      ...base,
      enabled: false,
      check,
      onComplete,
      startPoll
    })
    expect(resumed).toBe(false)
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(startPoll).not.toHaveBeenCalled()
  })

  it('starts a background poll when the check is not yet done', async () => {
    const check = vi.fn().mockResolvedValue(false)
    const onComplete = vi.fn()
    const startPoll = vi.fn()
    const resumed = await resumeSetupIfNeeded({
      ...base,
      enabled: false,
      check,
      onComplete,
      startPoll
    })
    expect(resumed).toBe(true)
    expect(startPoll).toHaveBeenCalledTimes(1)
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('skips non-external apps or apps without a completed-url', async () => {
    const check = vi.fn()
    const onComplete = vi.fn()
    const startPoll = vi.fn()
    expect(
      await resumeSetupIfNeeded({
        ...base,
        worksExternally: false,
        enabled: false,
        check,
        onComplete,
        startPoll
      })
    ).toBe(false)
    expect(
      await resumeSetupIfNeeded({
        ...base,
        setupCompletedUrl: null,
        enabled: false,
        check,
        onComplete,
        startPoll
      })
    ).toBe(false)
    expect(check).not.toHaveBeenCalled()
  })
})
