import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryCard } from '@/components/memories/MemoryCard';
import type { Memory } from '@/types/conversation';

const memory = {
  id: 'memory-1',
  content: `A long memory title ${'without-breaks'.repeat(24)}`,
  created_at: '2026-08-01T00:00:00.000Z',
  updated_at: '2026-08-01T00:00:00.000Z',
  visibility: 'private',
  reviewed: true,
  user_review: true,
  category: 'system',
  tags: [`${'long-tag-'.repeat(20)}end`],
} as Memory;

const renderCard = () =>
  render(
    <MemoryCard
      memory={memory}
      onEdit={vi.fn().mockResolvedValue(true)}
      onDelete={vi.fn().mockResolvedValue(true)}
      onToggleVisibility={vi.fn().mockResolvedValue(true)}
    />,
  );

describe('MemoryCard layout', () => {
  it('keeps hover actions out of metadata flow', () => {
    const { container } = renderCard();
    const card = container.querySelector('#memory-memory-1');
    const timestamp = screen.getByText('Aug 1, 2026');
    const actions = screen.getByTestId('memory-card-actions');
    const metadata = screen.getByTestId('memory-card-metadata');

    expect(card).not.toBeNull();
    expect(actions).toHaveClass('absolute', 'right-3', 'top-3');
    expect(metadata).not.toContainElement(actions);
    expect(timestamp).toHaveClass('whitespace-nowrap');

    fireEvent.mouseEnter(card!);

    expect(screen.getByText('Aug 1, 2026')).toBe(timestamp);
    expect(screen.getByTestId('memory-card-actions')).toBe(actions);
  });

  it('clamps unbroken content and tags without colliding with actions', () => {
    renderCard();
    const content = screen.getByTitle('Double-click to edit');
    const tag = screen.getByText(memory.tags![0]);

    expect(content).toHaveClass('line-clamp-2', 'pr-20', '[overflow-wrap:anywhere]');
    expect(tag).toHaveClass('max-w-full', 'truncate');

    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));

    expect(content).not.toHaveClass('line-clamp-2');
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument();
  });
});
