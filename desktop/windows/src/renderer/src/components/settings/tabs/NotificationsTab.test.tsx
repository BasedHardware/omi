// @vitest-environment jsdom
// The Notifications tab: renders every row, greys the per-assistant rows when the
// master toggle is off, writes the frequency through the scoped bridge, and picks
// up a broadcast from another window.
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll, afterAll } from 'vitest'
import {
  render,
  cleanup,
  act,
  fireEvent,
  screen,
  configure,
  getConfig
} from '@testing-library/react'
import { NotificationsTab } from './NotificationsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AssistantSettingsView } from '../../../../../shared/types'

// The tab renders nothing until assistantsGetSettings() (an async mock) resolves
// and React commits, so every test opens on `findByText('Frequency')`. That
// findBy defaults to a 1000ms wall-clock ceiling — fine in isolation, but under
// full-suite parallel load the CPU-starved worker can miss it before the commit
// lands, flaking a test that is actually correct. Raise the async-utils ceiling
// (the MutationObserver still resolves the instant the DOM updates, so passing
// tests aren't slowed) and restore it after the file so it can't bleed into
// suites sharing the worker.
let prevAsyncUtilTimeout = 1000
beforeAll(() => {
  prevAsyncUtilTimeout = getConfig().asyncUtilTimeout
  configure({ asyncUtilTimeout: 5000 })
  vi.setConfig({ testTimeout: 15000 })
})
afterAll(() => {
  configure({ asyncUtilTimeout: prevAsyncUtilTimeout })
  vi.resetConfig()
})

const DEFAULTS: AssistantSettingsView = {
  notificationsEnabled: true,
  notificationFrequency: 0,
  focusNotificationsEnabled: true,
  memoryEnabled: false,
  glowOverlayEnabled: true,
  screenAnalysisEnabled: true
}

let store: AssistantSettingsView
let setSettings: ReturnType<typeof vi.fn>
let changeCb: ((v: AssistantSettingsView) => void) | null

beforeEach(() => {
  store = { ...DEFAULTS }
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

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <NotificationsTab />
    </SettingsSearchProvider>
  )
}
const sw = (name: string): HTMLButtonElement =>
  screen.getByRole('switch', { name }) as HTMLButtonElement

describe('NotificationsTab', () => {
  it('renders every row after loading settings', async () => {
    renderTab()
    expect(await screen.findByText('Frequency')).toBeTruthy()
    expect(screen.getByText('Notifications')).toBeTruthy()
    expect(screen.getByText('Focus notifications')).toBeTruthy()
    expect(screen.getByText('Extract memories from your screen')).toBeTruthy()
    expect(screen.getByText('Focus glow')).toBeTruthy()
    expect(screen.getByText('Proactive insights')).toBeTruthy()
  })

  it('shows the "off" hint and the level caption at frequency 0', async () => {
    renderTab()
    expect(await screen.findByText(/Proactive notifications are off/i)).toBeTruthy()
    expect(screen.getByText('No proactive notifications')).toBeTruthy() // level caption
  })

  it('greys the per-assistant rows when the master toggle is off', async () => {
    renderTab()
    await screen.findByText('Frequency')
    // Default: master on → per-assistant rows enabled.
    expect(sw('Focus notifications').disabled).toBe(false)
    act(() => {
      fireEvent.click(sw('Notifications')) // turn the master off
    })
    expect(setSettings).toHaveBeenCalledWith({ notificationsEnabled: false })
    expect(sw('Focus notifications').disabled).toBe(true)
    expect(sw('Extract memories from your screen').disabled).toBe(true)
    expect(sw('Focus glow').disabled).toBe(true)
  })

  it('writes the frequency through assistantsSetSettings when the slider changes', async () => {
    renderTab()
    await screen.findByText('Frequency')
    const thumb = screen.getByRole('slider', { name: 'Notification frequency' })
    act(() => {
      fireEvent.keyDown(thumb, { key: 'ArrowRight' })
    })
    expect(setSettings).toHaveBeenCalledWith({ notificationFrequency: 1 })
  })

  it('toggling a per-assistant row writes just that flag', async () => {
    renderTab()
    await screen.findByText('Frequency')
    act(() => {
      fireEvent.click(sw('Extract memories from your screen'))
    })
    expect(setSettings).toHaveBeenCalledWith({ memoryEnabled: true })
  })

  it('updates rendered state from a broadcast (another window wrote the flag)', async () => {
    renderTab()
    await screen.findByText('Frequency')
    expect(screen.getByText('No proactive notifications')).toBeTruthy()
    act(() => {
      changeCb?.({ ...DEFAULTS, notificationFrequency: 5 })
    })
    expect(screen.getByText('Maximum')).toBeTruthy()
    expect(screen.getByText('No limit')).toBeTruthy()
  })
})
