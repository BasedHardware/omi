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
  waitFor,
  configure,
  getConfig
} from '@testing-library/react'
import { NotificationsTab } from './NotificationsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AssistantSettingsView } from '../../../../../shared/types'

// Labels render before the asynchronous settings load completes. Wait for the
// master switch's loaded value before interacting with dependent controls;
// finding static text alone can click a still-disabled switch under suite load.
// Keep the bounded async-utils ceiling for CPU-starved parallel workers and
// restore it after this file so it cannot bleed into another suite.
// The test timeout is captured when `it()` registers, i.e. during collection of this
// module, so it must be raised here at module scope — inside beforeAll it is a no-op
// and each test keeps the 5000ms default, which fires before the asyncUtilTimeout
// below can report the DOM it was waiting on.
vi.setConfig({ testTimeout: 15000 })
let prevAsyncUtilTimeout = 1000
beforeAll(() => {
  prevAsyncUtilTimeout = getConfig().asyncUtilTimeout
  configure({ asyncUtilTimeout: 5000 })
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

const waitForSettings = async (): Promise<void> => {
  await waitFor(() => expect(sw('Notifications').getAttribute('aria-checked')).toBe('true'))
}

describe('NotificationsTab', () => {
  it('renders every row after loading settings', async () => {
    renderTab()
    await waitForSettings()
    expect(screen.getByText('Frequency')).toBeTruthy()
    expect(screen.getByText('Notifications')).toBeTruthy()
    expect(screen.getByText('Focus notifications')).toBeTruthy()
    expect(screen.getByText('Extract memories from your screen')).toBeTruthy()
    expect(screen.getByText('Focus glow')).toBeTruthy()
    expect(screen.queryByText('Proactive insights')).toBeNull()
  })

  it('shows the "off" hint and the level caption at frequency 0', async () => {
    renderTab()
    await waitForSettings()
    expect(screen.getByText(/Proactive notifications are off/i)).toBeTruthy()
    expect(screen.getByText('No proactive notifications')).toBeTruthy() // level caption
  })

  it('greys the per-assistant rows when the master toggle is off', async () => {
    renderTab()
    await waitForSettings()
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
    await waitForSettings()
    const thumb = screen.getByRole('slider', { name: 'Notification frequency' })
    act(() => {
      fireEvent.keyDown(thumb, { key: 'ArrowRight' })
    })
    expect(setSettings).toHaveBeenCalledWith({ notificationFrequency: 1 })
  })

  it('toggling a per-assistant row writes just that flag', async () => {
    let finishLoad: ((value: AssistantSettingsView) => void) | null = null
    const loading = new Promise<AssistantSettingsView>((resolve) => {
      finishLoad = resolve
    })
    vi.mocked(window.omi.assistantsGetSettings).mockReturnValueOnce(loading)
    renderTab()
    expect(sw('Extract memories from your screen').disabled).toBe(true)
    fireEvent.click(sw('Extract memories from your screen'))
    expect(setSettings).not.toHaveBeenCalled()
    await act(async () => {
      if (!finishLoad) throw new Error('settings load was not requested')
      finishLoad(store)
    })
    await waitForSettings()
    await act(async () => {
      fireEvent.click(sw('Extract memories from your screen'))
    })
    expect(setSettings).toHaveBeenCalledTimes(1)
    expect(setSettings).toHaveBeenCalledWith({ memoryEnabled: true })
  })

  it('updates rendered state from a broadcast (another window wrote the flag)', async () => {
    renderTab()
    await waitForSettings()
    expect(screen.getByText('No proactive notifications')).toBeTruthy()
    act(() => {
      changeCb?.({ ...DEFAULTS, notificationFrequency: 5 })
    })
    expect(screen.getByText('Maximum')).toBeTruthy()
    expect(screen.getByText('No limit')).toBeTruthy()
  })
})
