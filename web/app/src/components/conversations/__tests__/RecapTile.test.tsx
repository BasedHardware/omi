import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { RecapTile } from '@/components/conversations/RecapTile';
import type { DailySummary } from '@/types/recap';

function recap(overrides: Partial<DailySummary> = {}): DailySummary {
  return {
    id: 'recap-1',
    date: '2026-01-01',
    headline: 'A long day',
    day_emoji: '📅',
    overview: 'Lots happened.',
    stats: {
      total_conversations: 4,
      total_duration_minutes: 95,
      action_items_count: 2,
    },
    highlights: [],
    action_items: [],
    unresolved_questions: [],
    decisions_made: [],
    knowledge_nuggets: [],
    locations: [],
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('RecapTile', () => {
  it('renders the counters it was given', () => {
    render(<RecapTile recap={recap()} />);

    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('1h 35m')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recap: A long day' })).toHaveClass(
      'col-span-full',
    );
  });

  // `DailySummaryResponse` in backend/routers/users.py declares `stats` and
  // every counter on it Optional, and useRecaps hands the payload straight
  // through, so a recap without stats reaches this component.
  it('renders a recap whose stats the backend omitted', () => {
    const withoutStats = recap();
    delete (withoutStats as Partial<DailySummary>).stats;

    expect(() => render(<RecapTile recap={withoutStats} />)).not.toThrow();
    expect(screen.getByText('A long day')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('renders a recap whose stats came back null', () => {
    const nullStats = recap({ stats: null as unknown as DailySummary['stats'] });

    expect(() => render(<RecapTile recap={nullStats} />)).not.toThrow();
    expect(screen.getByText('A long day')).toBeInTheDocument();
  });

  it('treats individually missing counters as zero', () => {
    const partial = recap({
      stats: { total_conversations: 3 } as unknown as DailySummary['stats'],
    });

    render(<RecapTile recap={partial} />);

    expect(screen.getByText('3')).toBeInTheDocument();
    // A missing duration must not render a `NaNm` chip.
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it('opens from the keyboard, because it is a real button', async () => {
    const onClick = vi.fn();
    render(<RecapTile recap={recap()} onClick={onClick} />);

    const tile = screen.getByRole('button', { name: 'Recap: A long day' });
    expect(tile.tagName).toBe('BUTTON');

    tile.focus();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(1);

    await userEvent.keyboard(' ');
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
