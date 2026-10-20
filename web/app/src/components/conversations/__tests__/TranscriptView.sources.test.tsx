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
        transcriptSegments={[{ id: 's1', start: 0 }]}
        onOpenSource={(id) => setRequest({ id, request: 1 })}
      />
    );
  }
  render(<Panel />);
  fireEvent.click(screen.getByRole('button', { name: 'Show Decision in transcript' }));
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

it('keeps a paused source in view after highlighting and resumes follow on playback changes', () => {
  vi.useFakeTimers();
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  const request = { id: 'cited', request: 1 };
  const segments = [
    {
      id: 'playing',
      text: 'Playing row',
      start: 0,
      end: 2,
      is_user: false,
      speaker_id: 0,
    },
    { id: 'cited', text: 'Cited row', start: 3, end: 4, is_user: false, speaker_id: 1 },
  ];
  const { rerender } = render(
    <TranscriptView currentTime={0} sourceRequest={request} segments={segments} />,
  );
  expect(scroll).toHaveBeenCalledTimes(1);
  expect((scroll.mock.contexts[0] as HTMLElement).textContent).toContain('Cited row');
  const row = screen.getByText('Cited row').closest('[tabindex]')!;
  expect(row).toHaveFocus();
  act(() => {
    vi.advanceTimersByTime(2500);
  });
  expect(row.className).not.toContain('ring-2');
  expect(scroll).toHaveBeenCalledTimes(1);
  rerender(
    <TranscriptView currentTime={1} sourceRequest={request} segments={segments} />,
  );
  expect(scroll).toHaveBeenCalledTimes(2);
  expect((scroll.mock.contexts[1] as HTMLElement).textContent).toContain('Playing row');
  vi.useRealTimers();
});
