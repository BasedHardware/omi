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

// MemoryCard formats created_at with toLocaleDateString, which renders in the
// runner's LOCAL timezone. The fixture is UTC midnight, so a hardcoded 'Aug 1, 2026'
// silently became 'Jul 31, 2026' on any runner behind UTC (e.g. America/New_York) and
// the test failed for reasons unrelated to the layout it exists to guard. Derive the
// expected label the same way the component does so the assertion is timezone-independent.
const EXPECTED_TIMESTAMP = new Date(memory.created_at).toLocaleDateString('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

describe('MemoryCard layout', () => {
  it('keeps hover actions out of metadata flow', () => {
    const { container } = renderCard();
    const card = container.querySelector('#memory-memory-1');
    const timestamp = screen.getByText(EXPECTED_TIMESTAMP);
    const actions = screen.getByTestId('memory-card-actions');
    const metadata = screen.getByTestId('memory-card-metadata');

    expect(card).not.toBeNull();
    expect(actions).toHaveClass('absolute', 'right-3', 'top-3');
    expect(metadata).not.toContainElement(actions);
    expect(timestamp).toHaveClass('whitespace-nowrap');

    fireEvent.mouseEnter(card!);

    expect(screen.getByText(EXPECTED_TIMESTAMP)).toBe(timestamp);
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
