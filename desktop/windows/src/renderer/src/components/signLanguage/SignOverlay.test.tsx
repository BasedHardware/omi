// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act, screen } from '@testing-library/react'
import type { TranslationResult } from '../../../../shared/types'

vi.mock('./SignAvatar', () => ({
  SignAvatar: ({ poseUrl }: { poseUrl: string | null }) => (
    <div data-testid="sign-avatar">{poseUrl ?? ''}</div>
  )
}))
vi.mock('./SignVideo', () => ({
  SignVideo: ({ videoUrl }: { videoUrl: string | null }) => (
    <div data-testid="sign-video">{videoUrl ?? ''}</div>
  )
}))
vi.mock('./SignWritingView', () => ({
  SignWritingView: () => null
}))

import { SignLanguageOverlay, SignLanguageOverlayGate } from './SignOverlay'

let deliver: ((result: TranslationResult) => void) | null = null

beforeEach(() => {
  deliver = null
  ;(
    window as unknown as {
      omi: {
        onDeepgramSignUpdate: (cb: (result: TranslationResult) => void) => () => void
      }
    }
  ).omi = {
    onDeepgramSignUpdate: (cb) => {
      deliver = cb
      return () => {
        deliver = null
      }
    }
  }
})

afterEach(() => {
  cleanup()
})

function push(result: TranslationResult): void {
  act(() => {
    deliver?.(result)
  })
}

describe('SignLanguageOverlay media', () => {
  it('renders the pose avatar for a pose result', () => {
    render(<SignLanguageOverlay />)
    push({
      originalText: 'hello',
      poseUrl: 'http://localhost/__poses/abc.pose',
      assetType: 'pose',
      glosses: []
    })
    expect(screen.getByTestId('sign-avatar').textContent).toBe('http://localhost/__poses/abc.pose')
    expect(screen.queryByTestId('sign-video')).toBeNull()
  })

  it('renders the video player when translation falls back to video', () => {
    render(<SignLanguageOverlay />)
    push({
      originalText: 'hello',
      poseUrl: 'http://localhost/__poses/abc.mp4',
      assetType: 'video',
      glosses: []
    })
    expect(screen.getByTestId('sign-video').textContent).toBe('http://localhost/__poses/abc.mp4')
    expect(screen.queryByTestId('sign-avatar')).toBeNull()
  })

  it('treats a missing assetType as a pose', () => {
    render(<SignLanguageOverlay />)
    push({
      originalText: 'hello',
      poseUrl: 'data:application/json;base64,e30=',
      glosses: []
    })
    expect(screen.getByTestId('sign-avatar').textContent).toBe('data:application/json;base64,e30=')
    expect(screen.queryByTestId('sign-video')).toBeNull()
  })
})

describe('SignLanguageOverlayGate', () => {
  let enabledListener: ((enabled: boolean) => void) | null = null
  let resolveInitial: (enabled: boolean) => void = () => {}

  beforeEach(() => {
    enabledListener = null
    const omi = (window as unknown as { omi: Record<string, unknown> }).omi
    omi.signLanguageGetEnabled = () =>
      new Promise<boolean>((resolve) => {
        resolveInitial = resolve
      })
    omi.onSignLanguageEnabledChanged = (cb: (enabled: boolean) => void) => {
      enabledListener = cb
      return () => {
        enabledListener = null
      }
    }
  })

  async function settle(enabled: boolean): Promise<void> {
    await act(async () => {
      resolveInitial(enabled)
    })
  }

  it('renders nothing while sign-language translation is disabled', async () => {
    const { container } = render(<SignLanguageOverlayGate />)
    await settle(false)
    expect(container.firstChild).toBeNull()
    expect(screen.queryByTestId('sign-avatar')).toBeNull()
  })

  it('renders the overlay when the setting is enabled at startup', async () => {
    render(<SignLanguageOverlayGate />)
    await settle(true)
    expect(screen.getByText('IDLE')).toBeTruthy()
  })

  it('follows the toggle live without a relaunch', async () => {
    const { container } = render(<SignLanguageOverlayGate />)
    await settle(false)
    act(() => enabledListener?.(true))
    expect(screen.getByText('IDLE')).toBeTruthy()
    act(() => enabledListener?.(false))
    expect(container.firstChild).toBeNull()
  })

  it('keeps a toggle that lands before the initial read resolves', async () => {
    render(<SignLanguageOverlayGate />)
    act(() => enabledListener?.(true))
    await settle(false)
    expect(screen.getByText('IDLE')).toBeTruthy()
  })

  it('unsubscribes on unmount', async () => {
    const { unmount } = render(<SignLanguageOverlayGate />)
    await settle(false)
    expect(enabledListener).not.toBeNull()
    unmount()
    expect(enabledListener).toBeNull()
  })
})
