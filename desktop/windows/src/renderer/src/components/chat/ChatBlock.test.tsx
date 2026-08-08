// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { ChatBlock } from './ChatBlock'
import type { ChatContentBlock } from '../../../../shared/chatContent'

afterEach(cleanup)

const block = (b: ChatContentBlock): ChatContentBlock => b

describe('ChatBlock — toolCall', () => {
  it('shows the tool name, arg summary, and a running spinner label', () => {
    render(
      <ChatBlock
        compact={false}
        block={block({
          type: 'toolCall',
          id: 't1',
          name: 'read_file',
          status: 'running',
          input: { summary: 'src/app.ts' }
        })}
      />
    )
    expect(screen.getByText('read_file')).not.toBeNull()
    expect(screen.getByText('src/app.ts')).not.toBeNull()
    expect(screen.getByText('Running')).not.toBeNull()
  })

  it('maps completed/failed to their labels', () => {
    const { rerender } = render(
      <ChatBlock
        compact={false}
        block={block({ type: 'toolCall', id: 't2', name: 'grep', status: 'completed' })}
      />
    )
    expect(screen.getByText('Done')).not.toBeNull()
    rerender(
      <ChatBlock
        compact={false}
        block={block({ type: 'toolCall', id: 't2', name: 'grep', status: 'failed' })}
      />
    )
    expect(screen.getByText('Failed')).not.toBeNull()
  })

  it('expands to reveal details and output; a detail-less call is not expandable', () => {
    render(
      <ChatBlock
        compact={false}
        block={block({
          type: 'toolCall',
          id: 't3',
          name: 'run',
          status: 'completed',
          input: { summary: 'npm test', details: 'npm run test -- --run' },
          output: 'ok: 3 passed'
        })}
      />
    )
    // Collapsed: detail hidden until toggled.
    expect(screen.queryByText('npm run test -- --run')).toBeNull()
    fireEvent.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText('npm run test -- --run')).not.toBeNull()
    expect(screen.getByText('ok: 3 passed')).not.toBeNull()
  })
})

describe('ChatBlock — thinking', () => {
  it('is collapsed by default and reveals reasoning on click', () => {
    render(
      <ChatBlock
        compact={false}
        block={block({ type: 'thinking', id: 'k1', text: 'weighing the options' })}
      />
    )
    expect(screen.queryByText('weighing the options')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /thinking/i }))
    expect(screen.getByText('weighing the options')).not.toBeNull()
  })
})

describe('ChatBlock — discoveryCard', () => {
  it('shows title + summary and expands to the full text', () => {
    render(
      <ChatBlock
        compact={false}
        block={block({
          type: 'discoveryCard',
          id: 'd1',
          title: 'About you',
          summary: 'You prefer mornings',
          fullText: 'You prefer mornings and short meetings'
        })}
      />
    )
    expect(screen.getByText('About you')).not.toBeNull()
    expect(screen.getByText('You prefer mornings')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /about you/i }))
    expect(screen.getByText('You prefer mornings and short meetings')).not.toBeNull()
  })
})

describe('ChatBlock — unknown kind', () => {
  it('renders nothing rather than crashing', () => {
    const { container } = render(
      // A block shape outside the union — the exhaustive default must no-op.
      <ChatBlock
        compact={false}
        block={{ type: 'mystery', id: 'x' } as unknown as ChatContentBlock}
      />
    )
    expect(container.firstChild).toBeNull()
  })
})
