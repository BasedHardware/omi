// @vitest-environment jsdom
//
// Regression: onboarding PTT was dead on every fresh install because the
// /onboarding route mounted NO VoiceHubDriverHost — with pttHubEnabled on (the
// default) the bar delegates every hold to the main window over voiceHub:begin,
// and during onboarding that IPC had no listener, so the press was silently
// dropped (no capture, no reply, no "Omi heard you"). The first press only
// worked after onboarding completed, when AppShell mounted the host.
//
// This test mounts the REAL OnboardingScreen topology (real AppStateProvider +
// real VoiceHubDriverHost) and asserts the voiceHub control channels get
// listeners. The heavy leaves (the Onboarding page's three.js graph, the title
// bar, the engine hooks, the warm lifecycle — each unit-tested on its own) are
// mocked so the mount topology is what's under test.
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { OnboardingScreen } from './OnboardingScreen'

vi.mock('./Onboarding', () => ({ Onboarding: () => null }))
vi.mock('../components/layout/TitleBar', () => ({ TitleBar: () => null }))
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { uid: 'user-1' }, loading: false })
}))
vi.mock('../hooks/useRecorder', () => ({ useRecorder: () => ({}) }))
vi.mock('../hooks/useChat', () => ({
  useChat: () => ({
    send: vi.fn(),
    recordVoiceTurn: vi.fn(),
    getVoiceSeedContext: vi.fn(async () => []),
    history: []
  })
}))
// Warming opens a real hub socket — its gate contract is unit-tested in
// useHubWarmLifecycle.test; here it would just fire network noise into jsdom.
vi.mock('../hooks/useHubWarmLifecycle', () => ({ useHubWarmLifecycle: vi.fn() }))

describe('OnboardingScreen', () => {
  it('mounts the voice-hub driver: the bar→main voiceHub channels have listeners during onboarding', () => {
    const onVoiceHubBegin = vi.fn(() => () => {})
    const onVoiceHubEnd = vi.fn(() => () => {})
    const onVoiceHubCancel = vi.fn(() => () => {})
    ;(window as unknown as { omi: unknown }).omi = {
      onVoiceHubBegin,
      onVoiceHubEnd,
      onVoiceHubCancel
    }
    try {
      render(<OnboardingScreen />)
      // The exact seam that was dead: a bar-delegated hold arrives on these
      // channels, so each must have a registered listener while onboarding shows.
      expect(onVoiceHubBegin).toHaveBeenCalledTimes(1)
      expect(onVoiceHubEnd).toHaveBeenCalledTimes(1)
      expect(onVoiceHubCancel).toHaveBeenCalledTimes(1)
    } finally {
      delete (window as unknown as { omi?: unknown }).omi
    }
  })
})
