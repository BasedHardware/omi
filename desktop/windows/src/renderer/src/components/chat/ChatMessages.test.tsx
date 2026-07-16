// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { ChatMessages } from './ChatMessages'
import type { ChatMsg } from '../../hooks/useChat'

// Render markdown as plain text — we only care about the copy affordance here,
// not how RevealMarkdown paints (that has its own test).
vi.mock('../Markdown', () => ({
  Markdown: ({ text }: { text: string }) => <span data-testid="md">{text}</span>
}))

const writeText = vi.fn().mockResolvedValue(undefined)

beforeEach(() => {
  writeText.mockClear()
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
})
afterEach(() => cleanup())

const assistant = (content: string): ChatMsg => ({ id: 'a1', role: 'assistant', content })
const user = (content: string): ChatMsg => ({ id: 'u1', role: 'user', content })

describe('ChatMessages copy button', () => {
  it('copies the assistant message text and flips to the copied state', async () => {
    render(<ChatMessages messages={[assistant('Hello from omi')]} sending={false} variant="main" />)

    const button = screen.getByRole('button', { name: 'Copy message' })
    fireEvent.click(button)

    expect(writeText).toHaveBeenCalledWith('Hello from omi')
    // The icon swaps to the check-tick, surfaced via the aria-label.
    await screen.findByRole('button', { name: 'Copied' })
  })

  it('offers copy on user messages too (the bar copies both roles)', () => {
    render(
      <ChatMessages messages={[user('what is my day like')]} sending={false} variant="overlay" />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    expect(writeText).toHaveBeenCalledWith('what is my day like')
  })

  it('does not offer copy on the reply that is still streaming in', () => {
    // The last assistant message while `sending` is the in-flight reply — no copy
    // until it settles.
    render(<ChatMessages messages={[assistant('partial repl')]} sending={true} variant="main" />)
    expect(screen.queryByRole('button', { name: 'Copy message' })).toBeNull()
  })

  it('does not offer copy on an empty/whitespace message', () => {
    render(<ChatMessages messages={[assistant('   ')]} sending={false} variant="main" />)
    expect(screen.queryByRole('button', { name: 'Copy message' })).toBeNull()
  })
})

const image = {
  id: 'f-img',
  name: 'photo.png',
  mimeType: 'image/png',
  thumbnailUrl: 'https://cdn.omi/thumb.png'
}
const pdf = { id: 'f-pdf', name: 'report.pdf', mimeType: 'application/pdf' }

// The user bubble's inner text node carries `whitespace-pre-wrap`; a files-only
// message must NOT render it (no empty bubble).
const userBubbleText = (root: HTMLElement): HTMLElement | null =>
  root.querySelector('.whitespace-pre-wrap')

describe.each(['main', 'overlay'] as const)('ChatMessages [%s] — attachments', (variant) => {
  it('renders the attachment strip ABOVE the user bubble, with both cards and the text', () => {
    const messages: ChatMsg[] = [
      { id: 'm1', role: 'user', content: 'here you go', attachments: [image, pdf] }
    ]
    const { container } = render(
      <ChatMessages messages={messages} sending={false} variant={variant} />
    )
    const bubble = userBubbleText(container)
    expect(bubble?.textContent).toBe('here you go')
    const img = screen.getByAltText('photo.png')
    expect(img.getAttribute('src')).toBe('https://cdn.omi/thumb.png')
    expect(screen.getByText('application/pdf')).not.toBeNull()
    // Strip precedes the bubble in document order (rendered above it).
    expect(img.compareDocumentPosition(bubble as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    )
  })

  it('renders a files-only message as a strip with NO empty bubble', () => {
    const messages: ChatMsg[] = [{ id: 'm2', role: 'user', content: '', attachments: [pdf] }]
    const { container } = render(
      <ChatMessages messages={messages} sending={false} variant={variant} />
    )
    expect(screen.getByText('report.pdf')).not.toBeNull()
    expect(userBubbleText(container)).toBeNull()
  })

  it('leaves a message without attachments as a single bubble (no strip)', () => {
    const messages: ChatMsg[] = [{ id: 'm3', role: 'user', content: 'plain text' }]
    const { container } = render(
      <ChatMessages messages={messages} sending={false} variant={variant} />
    )
    expect(userBubbleText(container)?.textContent).toBe('plain text')
    expect(container.querySelector('img')).toBeNull()
    // The bubble div is the top-level message node (not wrapped in a strip column).
    expect((container.firstElementChild as HTMLElement).className).toContain('group/msg')
  })
})
