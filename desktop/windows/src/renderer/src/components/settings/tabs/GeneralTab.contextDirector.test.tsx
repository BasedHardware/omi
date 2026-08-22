// @vitest-environment jsdom
// The General tab's "Context Director" row: reflects contextDirectorEnabled,
// writes the flag through the scoped assistant bridge on toggle, and follows
// the settings broadcast — the same contract as the Screen Analysis row above it.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act, fireEvent, screen } from '@testing-library/react'
import { ContextDirectorRow } from './GeneralTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AssistantSettingsView } from '../../../../../shared/types'

const VIEW: AssistantSettingsView = {
  notificationsEnabled: true,
  notificationFrequency: 0,
  focusNotificationsEnabled: true,
  memoryEnabled: false,
  glowOverlayEnabled: false,
  screenAnalysisEnabled: true,
  contextDirectorEnabled: false
}

let store: AssistantSettingsView
let setSettings: ReturnType<typeof vi.fn>
let changeCb: ((v: AssistantSettingsView) => void) | null

beforeEach(() => {
  store = { ...VIEW }
  changeCb = null
  setSettings = vi.fn(async (patch: Partial<AssistantSettingsView>) => {
    store = { ...store, ...patch }
    return store
  })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).omi = {
    assistantsGetSettings: vi.fn(async () => store),
    assistantsSetSettings: setSettings,
    onAssistantSettingsChanged: (cb: (v: AssistantSettingsView) => void) => {
      changeCb = cb
      return () => {
        changeCb = null
      }
    }
  }
})
afterEach(cleanup)

const renderRow = (): void => {
  render(
    <SettingsSearchProvider>
      <ContextDirectorRow />
    </SettingsSearchProvider>
  )
}
const sw = (): HTMLButtonElement =>
  screen.getByRole('switch', { name: 'Context Director' }) as HTMLButtonElement

describe('GeneralTab ContextDirectorRow', () => {
  it('reflects the default-off value once loaded and writes the toggle through the bridge', async () => {
    renderRow()
    await screen.findByText('Context Director')
    expect(sw().getAttribute('aria-checked')).toBe('false')

    fireEvent.click(sw())
    expect(setSettings).toHaveBeenCalledWith({ contextDirectorEnabled: true })
    expect(sw().getAttribute('aria-checked')).toBe('true')
  })

  it('follows the settings broadcast so the row and any other surface agree', async () => {
    renderRow()
    await screen.findByText('Context Director')
    act(() => changeCb?.({ ...VIEW, contextDirectorEnabled: true }))
    expect(sw().getAttribute('aria-checked')).toBe('true')
  })
})
