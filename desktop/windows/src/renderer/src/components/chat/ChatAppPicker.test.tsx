// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  render,
  screen,
  fireEvent,
  cleanup,
  renderHook,
  waitFor,
  act
} from '@testing-library/react'
import { ChatAppPickerView } from './ChatAppPicker'
import { useChatApps } from '../../hooks/useChatApps'
import type { ChatApp } from '../../lib/chatApps'

afterEach(cleanup)

const APPS: ChatApp[] = [
  { id: 'persona-a', name: 'Persona A', image: 'https://img/a.png', author: 'Alice' },
  { id: 'chat-b', name: 'Chat B', image: '', author: 'Bob' }
]

// Radix Popover needs a couple of DOM APIs jsdom lacks; stub them so open works.
function stubPopoverDom(): void {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
}

describe('ChatAppPickerView', () => {
  it('shows the default "omi" label when no app is selected', () => {
    render(<ChatAppPickerView apps={APPS} selectedAppId={null} onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Select chat assistant' }).textContent).toContain(
      'omi'
    )
  })

  it('shows the selected app name when one is selected', () => {
    render(<ChatAppPickerView apps={APPS} selectedAppId="persona-a" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Select chat assistant' }).textContent).toContain(
      'Persona A'
    )
  })

  it('lists the default assistant + every chat app, and selecting one calls onSelect with its id', () => {
    stubPopoverDom()
    const onSelect = vi.fn()
    render(<ChatAppPickerView apps={APPS} selectedAppId={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: 'Select chat assistant' }))

    // The default row + both apps render in the popover.
    expect(screen.getByText('Select Assistant')).toBeTruthy()
    expect(screen.getByText('Persona A')).toBeTruthy()
    expect(screen.getByText('Chat B')).toBeTruthy()
    // Authors render as subtitles.
    expect(screen.getByText('Alice')).toBeTruthy()

    fireEvent.click(screen.getByText('Persona A'))
    expect(onSelect).toHaveBeenCalledWith('persona-a')
  })

  it('the default row deselects the app (onSelect(null))', () => {
    stubPopoverDom()
    const onSelect = vi.fn()
    render(<ChatAppPickerView apps={APPS} selectedAppId="persona-a" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: 'Select chat assistant' }))
    // The "Default assistant" subtitle uniquely identifies the default row.
    fireEvent.click(screen.getByText('Default assistant'))
    expect(onSelect).toHaveBeenCalledWith(null)
  })
})

describe('useChatApps', () => {
  it('loads the injected chat-app list on mount', async () => {
    const list = vi.fn(async () => APPS)
    const { result } = renderHook(() => useChatApps(list))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.chatApps).toEqual(APPS)
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('clears loading even when the list fetch resolves empty', async () => {
    const list = vi.fn(async () => [] as ChatApp[])
    const { result } = renderHook(() => useChatApps(list))
    await act(async () => {
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.chatApps).toEqual([])
  })
})
