// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, screen, waitFor } from '@testing-library/react'
import { HubAskBar } from './HubAskBar'

vi.mock('../../../lib/chatAttachments', async (importOriginal) => importOriginal())
vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))

function bar(focusSignal: number | undefined): React.JSX.Element {
  return (
    <HubAskBar
      value=""
      onChange={() => {}}
      onSubmit={() => {}}
      onFocus={() => {}}
      sending={false}
      connectActive={false}
      onToggleConnect={() => {}}
      focusSignal={focusSignal}
    />
  )
}

afterEach(cleanup)

describe('HubAskBar focus signal', () => {
  it('a signal bump after mount pulls focus into the input', async () => {
    const { rerender } = render(bar(0))
    rerender(bar(1))
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('textbox')))
  })

  it('a fresh mount with a nonzero signal never steals focus (no replay on re-dock)', async () => {
    // The bar re-docks between the stage and the chat panel; a remount seeing
    // the old signal must not focus, or its onFocus would reopen the chat the
    // user just dismissed.
    render(bar(3))
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
    expect(document.activeElement).not.toBe(screen.getByRole('textbox'))
  })
})
