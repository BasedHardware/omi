import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ChatMarkdown } from '../ChatMarkdown';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));
const memories = [
  { id: 'meeting/a', created_at: '', structured: { title: 'Planning', emoji: '' } },
  { id: 'meeting-b', created_at: '', structured: { title: 'Review', emoji: '' } },
];

describe('message-local chat citations', () => {
  it('makes every numeric marker form usable with one-based message memories', () => {
    render(
      <ChatMarkdown memories={memories}>
        {'Claim [1] [#2] [1][2] 【1】 [^2]. Unknown [3] and [0].'}
      </ChatMarkdown>,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(6);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/conversations?id=meeting%2Fa',
      '/conversations?id=meeting-b',
      '/conversations?id=meeting%2Fa',
      '/conversations?id=meeting-b',
      '/conversations?id=meeting%2Fa',
      '/conversations?id=meeting-b',
    ]);
    fireEvent.click(links[1]);
    expect(push).toHaveBeenCalledWith('/conversations?id=meeting-b');
    expect(screen.getByText(/Unknown \[3\] and \[0\]/)).toBeInTheDocument();
  });

  it('protects code and existing links and keeps missing-memory markers inert', () => {
    const { container } = render(
      <ChatMarkdown memories={memories}>
        {
          '`[1]`\n\n```text\n[#2] 【1】\n```\n\n[1](https://example.com) and [link [2]](https://example.org). [keep](#omi-chat-citation-1)'
        }
      </ChatMarkdown>,
    );
    expect(screen.getAllByRole('link')).toHaveLength(3);
    expect(screen.getByRole('link', { name: 'keep' })).toHaveAttribute(
      'href',
      '#omi-chat-citation-1',
    );
    expect(screen.getByRole('link', { name: '1' })).toHaveAttribute(
      'href',
      'https://example.com/',
    );
    expect(container.querySelector('code')?.textContent).toBe('[1]');
    const other = render(<ChatMarkdown>{'Only [1] 【2】 [^1]'}</ChatMarkdown>);
    expect(other.container.querySelector('a')).toBeNull();
    expect(other.container.textContent).toContain('[1] 【2】 [^1]');
  });

  it('binds the same marker to its own message when history changes', () => {
    const { rerender } = render(
      <ChatMarkdown memories={memories}>{'First [1]'}</ChatMarkdown>,
    );
    rerender(<ChatMarkdown memories={[memories[1]]}>{'Second [1]'}</ChatMarkdown>);
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/conversations?id=meeting-b',
    );
  });
});
