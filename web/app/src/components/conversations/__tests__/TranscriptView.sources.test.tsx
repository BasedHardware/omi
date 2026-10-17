import { act, fireEvent, render, screen } from '@testing-library/react';
import { it, expect, vi } from 'vitest';
import { useState } from 'react';
import { TranscriptView } from '../TranscriptView';
import { NoteSections } from '../NoteSections';

it('opens a cited transcript group, focuses it and clears its temporary highlight', () => {
  vi.useFakeTimers();
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  function Panel() {
    const [request, setRequest] = useState<{ id: string; request: number } | null>(null);
    return request ? (
      <TranscriptView
        sourceRequest={request}
        segments={[
          {
            id: 's1',
            text: 'The decision.',
            start: 0,
            end: 2,
            is_user: false,
            speaker_id: 0,
          },
        ]}
      />
    ) : (
      <NoteSections
        sections={[
          { heading: 'Decision', body_markdown: 'Agreed.', source_segment_ids: ['s1'] },
        ]}
        transcriptIDs={['s1']}
        onOpenSource={(id) => setRequest({ id, request: 1 })}
      />
    );
  }
  render(<Panel />);
  fireEvent.click(screen.getByRole('button', { name: 'View transcript source 1 of 1' }));
  const row = screen.getByText('The decision.').closest('[tabindex]')!;
  expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
  expect(row).toHaveFocus();
  expect(row.className).toContain('ring-2');
  act(() => {
    vi.advanceTimersByTime(2500);
  });
  expect(row.className).not.toContain('ring-2');
  vi.useRealTimers();
});
