// The capture_screen executor + its Screen-Sharing-in-Chat gate, in isolation
// (no Electron, no socket — deps injected). The end-to-end relay dispatch of this
// executor is covered in toolRelayBridge.test.ts; here we pin the gate logic, the
// Mac-shaped refusal, and that the registry/serviceable-set now advertise it.

import { describe, it, expect, vi } from 'vitest'
import {
  CAPTURE_SCREEN_TOOL,
  SCREENSHOT_IMAGE_CAPABILITY,
  createCaptureScreenExecutor,
  screenshotSharingDeniedMessage
} from './captureScreenExecutor'
import { defaultProductToolExecutors, WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from './toolRelayBridge'

const ctx = { sessionId: 's1', adapterId: 'pi-mono', signal: new AbortController().signal }

describe('createCaptureScreenExecutor gate', () => {
  it('sharing ON → returns the capture path', async () => {
    const capture = vi.fn(async () => '/tmp/chat-screenshots/screenshot-1.jpg')
    const executor = createCaptureScreenExecutor({ isSharingEnabled: () => true, capture })
    expect(await executor({}, ctx)).toBe('/tmp/chat-screenshots/screenshot-1.jpg')
    expect(capture).toHaveBeenCalledTimes(1)
  })

  it('sharing OFF → returns POLICY_DENIED and never captures', async () => {
    const capture = vi.fn(async () => 'nope.jpg')
    const executor = createCaptureScreenExecutor({ isSharingEnabled: () => false, capture })
    const result = await executor({}, ctx)
    expect(result).toBe(screenshotSharingDeniedMessage())
    expect(capture).not.toHaveBeenCalled()
  })

  it('a capture failure surfaces as a thrown error the relay can format', async () => {
    const capture = vi.fn(async () => {
      throw new Error('Failed to capture screen')
    })
    const executor = createCaptureScreenExecutor({ isSharingEnabled: () => true, capture })
    await expect(executor({}, ctx)).rejects.toThrow('Failed to capture screen')
  })
})

describe('screenshotSharingDeniedMessage', () => {
  it('is the Mac POLICY_DENIED shape with the screenshot-image capability', () => {
    const msg = screenshotSharingDeniedMessage()
    expect(msg.startsWith('POLICY_DENIED: ')).toBe(true)
    const payload = JSON.parse(msg.slice('POLICY_DENIED: '.length))
    expect(payload).toMatchObject({
      ok: false,
      code: 'disabled_by_user_setting',
      capability: SCREENSHOT_IMAGE_CAPABILITY,
      tool: CAPTURE_SCREEN_TOOL
    })
    // Sorted keys (matches Swift's JSONSerialization .sortedKeys).
    expect(Object.keys(payload)).toEqual([...Object.keys(payload)].sort())
  })
})

describe('capture_screen is now the first serviceable product tool', () => {
  it('is registered in the default executor map + serviceable allowlist', () => {
    expect(defaultProductToolExecutors.has(CAPTURE_SCREEN_TOOL)).toBe(true)
    expect(WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(CAPTURE_SCREEN_TOOL)).toBe(true)
  })
})
