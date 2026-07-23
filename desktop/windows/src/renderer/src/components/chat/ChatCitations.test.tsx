// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { ChatMessages } from './ChatMessages'
import type { ChatMsg } from '../../hooks/useChat'

// Render markdown as plain text — the reply body isn't what these assert.
vi.mock('../Markdown', () => ({
  Markdown: ({ text }: { text: string }) => <span data-testid="md">{text}</span>
}))

// Navigation is the citation chip's only side effect; spy on it.
const navigateSpy = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateSpy }))

beforeEach(() => navigateSpy.mockClear())
afterEach(() => cleanup())

const cited = (): ChatMsg => ({
  id: 'a1',
  role: 'assistant',
  content: 'Here is what I found.',
  citations: [
    { id: 'conv_1', title: 'Standup notes', emoji: '📝' },
    { id: 'conv_2', title: 'Design review' }
  ]
})

describe('ChatMessages — citations (Sources)', () => {
  it('renders a Sources strip with each cited conversation (main window)', () => {
    render(<ChatMessages messages={[cited()]} sending={false} variant="main" />)
    expect(screen.getByText('Sources')).not.toBeNull()
    expect(screen.getByText('Standup notes')).not.toBeNull()
    expect(screen.getByText('Design review')).not.toBeNull()
    expect(screen.getByText('📝')).not.toBeNull()
  })

  it('opens the conversation detail when a source chip is clicked', () => {
    render(<ChatMessages messages={[cited()]} sending={false} variant="main" />)
    fireEvent.click(screen.getByRole('button', { name: /Standup notes/ }))
    expect(navigateSpy).toHaveBeenCalledWith('/conversations/conv_1')
  })

  it('does NOT render Sources in the overlay bar', () => {
    render(<ChatMessages messages={[cited()]} sending={false} variant="overlay" />)
    expect(screen.queryByText('Sources')).toBeNull()
  })

  it('does NOT render Sources on a still-streaming reply', () => {
    render(<ChatMessages messages={[cited()]} sending={true} variant="main" />)
    expect(screen.queryByText('Sources')).toBeNull()
  })

  it('renders no Sources strip when the reply cited nothing', () => {
    const plain: ChatMsg = { id: 'a2', role: 'assistant', content: 'No sources here.' }
    render(<ChatMessages messages={[plain]} sending={false} variant="main" />)
    expect(screen.queryByText('Sources')).toBeNull()
  })
})
