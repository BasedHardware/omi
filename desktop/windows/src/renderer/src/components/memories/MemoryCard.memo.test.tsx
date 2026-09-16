// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useState } from 'react'
import { render, cleanup, act, fireEvent } from '@testing-library/react'
import type { Memory, MemoryUseAction } from '../../hooks/useMemories'

// Regression guard for the app-wide navigation-snappiness fix (perf/win-nav-snappy).
// The Memories page consumes useLocation (to gate the brain-map reveal), so it
// re-renders on EVERY app navigation while it stays mounted-but-hidden. Its ~400
// MemoryCards each mount a Radix Tooltip.Provider; before this fix they all
// re-rendered on every navigation, which was the bulk of a ~120ms main-thread
// stall that made navigation feel laggy across the whole app. MemoryCard is now
// memo()'d, so a parent re-render with referentially-stable props skips the card.
//
// This spies on formatMemoryDate (called once per card render, in the footer) to
// prove the card body does NOT re-run when the parent re-renders with the same
// memory ref, and DOES re-run when the memory ref changes.
const dateSpy = vi.fn((s: string) => s)
vi.mock('../../lib/memoryFilters', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/memoryFilters')>()
  return { ...actual, formatMemoryDate: (...args: [string, number?]) => dateSpy(args[0]) }
})

// Import AFTER the mock is registered.
const { MemoryCard } = await import('./MemoryCard')

function makeMemory(id: string): Memory {
  return {
    id,
    uid: 'u1',
    content: `memory ${id}`,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z'
  }
}

// Stable onOpen ref — the real page passes setDetailMemory (a stable useState
// setter), so the only prop that varies across a nav re-render is `memory`.
const noopOpen = (): void => {}

// A parent that re-renders on demand, holding a memory it can swap by reference.
function Harness({
  memory,
  onUseAction
}: {
  memory: Memory
  onUseAction?: (id: string, action: MemoryUseAction) => void
}): React.JSX.Element {
  const [, setTick] = useState(0)
  return (
    <div>
      <button data-testid="bump" onClick={() => setTick((t) => t + 1)}>
        bump
      </button>
      <ul>
        <MemoryCard memory={memory} onOpen={noopOpen} onUseAction={onUseAction} />
      </ul>
    </div>
  )
}

describe('MemoryCard memoization (nav-snappiness regression)', () => {
  beforeEach(() => dateSpy.mockClear())
  afterEach(cleanup)

  it('does not re-render when the parent re-renders with the same memory ref', () => {
    const memory = makeMemory('a')
    const { getByTestId, rerender } = render(<Harness memory={memory} />)
    expect(dateSpy).toHaveBeenCalledTimes(1)

    // Parent re-render (same memory ref) — memo must skip the card entirely, as it
    // does on every navigation while the hidden Memories page re-renders.
    act(() => getByTestId('bump').click())
    // A prop-preserving parent re-render (react-router location change is the real
    // trigger) — the card ref is unchanged, so the body must not re-run.
    rerender(<Harness memory={memory} />)
    expect(dateSpy).toHaveBeenCalledTimes(1)
  })

  it('does re-render when the memory ref changes', () => {
    const memory = makeMemory('a')
    const { rerender } = render(<Harness memory={memory} />)
    expect(dateSpy).toHaveBeenCalledTimes(1)

    rerender(<Harness memory={makeMemory('b')} />)
    expect(dateSpy).toHaveBeenCalledTimes(2)
  })

  it('shows the recorded source on the card', () => {
    const { getByText } = render(
      <ul>
        <MemoryCard
          memory={{ ...makeMemory('a'), conversation_id: 'conversation-1' }}
          onOpen={noopOpen}
        />
      </ul>
    )

    expect(getByText('Conversation')).not.toBeNull()
  })

  it('hides use feedback controls for inactive ledger rows', () => {
    const onUseAction = vi.fn()
    const active = { ...makeMemory('active'), status: 'active' as const, valid_to: '2026-09-01' }
    const inactive = {
      ...makeMemory('inactive'),
      status: 'active' as const,
      invalid_at: '2026-09-02'
    }
    const { getByRole, queryByRole, rerender } = render(
      <ul>
        <MemoryCard memory={active} onOpen={noopOpen} onUseAction={onUseAction} />
      </ul>
    )

    expect(getByRole('button', { name: 'Do not use this memory' })).not.toBeNull()
    rerender(
      <ul>
        <MemoryCard memory={inactive} onOpen={noopOpen} onUseAction={onUseAction} />
      </ul>
    )
    expect(queryByRole('button', { name: 'Do not use this memory' })).toBeNull()
    expect(queryByRole('button', { name: 'Mark this memory useful' })).toBeNull()
  })

  it('does not re-render when the parent re-renders with a stable onUseAction ref', () => {
    // The page passes a useCallback-stable adapter (latest-ref inside), so
    // onUseAction must satisfy memo exactly like memory/onOpen do — a fresh
    // closure per render would re-render every card on every navigation.
    const memory = makeMemory('a')
    const onUseAction = vi.fn()
    const { getByTestId, rerender } = render(<Harness memory={memory} onUseAction={onUseAction} />)
    expect(dateSpy).toHaveBeenCalledTimes(1)

    act(() => getByTestId('bump').click())
    rerender(<Harness memory={memory} onUseAction={onUseAction} />)
    expect(dateSpy).toHaveBeenCalledTimes(1)
  })

  it('Enter on the use-feedback button performs feedback without opening the card', () => {
    const onUseAction = vi.fn()
    const onOpen = vi.fn()
    const { getByRole } = render(
      <ul>
        <MemoryCard memory={makeMemory('a')} onOpen={onOpen} onUseAction={onUseAction} />
      </ul>
    )

    const feedback = getByRole('button', { name: 'Do not use this memory' })
    // Enter activates the button (the click below) but must not bubble to the
    // li's onKeyDown, which opens the card on top of the feedback.
    fireEvent.keyDown(feedback, { key: 'Enter' })
    expect(onOpen).not.toHaveBeenCalled()

    fireEvent.click(feedback)
    expect(onUseAction).toHaveBeenCalledWith('a', 'suppress')
    expect(onOpen).not.toHaveBeenCalled()
  })
})
