import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NoteSections } from '../NoteSections';
import { formatQuoteTimestamp } from '../QuoteTimestamps';

describe('NoteSections', () => {
  it.each([
    [0, '0:00'],
    [42.9, '0:42'],
    [312, '5:12'],
    [3599, '59:59'],
    [3600, '1:00:00'],
    [3912, '1:05:12'],
  ])('formats %s seconds as %s', (start, expected) =>
    expect(formatQuoteTimestamp(Number(start))).toBe(expected),
  );

  it('expands each row independently, including side notes, and opens the chosen source', () => {
    const onOpenSource = vi.fn();
    const starts = [42, 312, 460, 3912, 3600];
    const sourceIDs = starts.map((_, i) => `s${i}`);
    render(
      <NoteSections
        transcriptSegments={starts.map((start, i) => ({ id: sourceIDs[i], start }))}
        onOpenSource={onOpenSource}
        sections={[
          { heading: 'Main', body_markdown: 'Main body', source_segment_ids: sourceIDs },
          {
            heading: 'Side notes',
            kind: 'side_notes',
            body_markdown: 'Aside body',
            source_segment_ids: sourceIDs,
          },
        ]}
      />,
    );
    expect(screen.getAllByText('0:42')).toHaveLength(2);
    expect(screen.getAllByText('5:12')).toHaveLength(2);
    expect(screen.getAllByText('7:40')).toHaveLength(2);
    expect(screen.queryByText('1:05:12')).toBeNull();
    const aside = within(screen.getByRole('complementary'));
    fireEvent.click(aside.getByRole('button', { name: '+2 more' }));
    expect(screen.getAllByRole('button', { name: '+2 more' })).toHaveLength(1);
    expect(aside.getByText('1:00:00')).toBeInTheDocument();
    fireEvent.click(
      aside.getByRole('button', { name: 'Jump to 1 hour 5 minutes 12 seconds' }),
    );
    expect(onOpenSource).toHaveBeenCalledExactlyOnceWith('s3');
  });

  it('keeps keyboard focus on the toggle when expanding and collapsing', async () => {
    const user = userEvent.setup();
    const sourceIDs = ['s0', 's1', 's2', 's3'];
    render(
      <NoteSections
        sections={[{ body_markdown: 'Body', source_segment_ids: sourceIDs }]}
        transcriptSegments={sourceIDs.map((id, i) => ({ id, start: i + 42 }))}
        onOpenSource={vi.fn()}
      />,
    );
    for (let i = 0; i < 4; i++) await user.tab();
    const toggle = screen.getByRole('button', { name: '+1 more' });
    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.keyboard('{Enter}');
    expect(screen.getByText('0:45')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show less' })).toBe(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveFocus();
    expect(document.body).not.toHaveFocus();
    await user.keyboard(' ');
    expect(screen.queryByText('0:45')).toBeNull();
    expect(toggle).toHaveAccessibleName('+1 more');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });

  it('hides rows without resolvable, finite starts or a seek callback', () => {
    const sections = [
      { body_markdown: 'Body', source_segment_ids: ['missing', 'bad', 'negative'] },
    ];
    const { rerender } = render(
      <NoteSections
        sections={sections}
        transcriptSegments={[
          { id: 'bad', start: NaN },
          { id: 'negative', start: -1 },
        ]}
        onOpenSource={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Transcript sources')).toBeNull();
    rerender(
      <NoteSections
        sections={sections}
        transcriptSegments={[{ id: 'missing', start: 42 }]}
      />,
    );
    expect(screen.queryByLabelText('Transcript sources')).toBeNull();
  });

  it('opens only deduplicated typed sources resolving in this transcript', () => {
    const onOpenSource = vi.fn();
    const { rerender } = render(
      <NoteSections
        transcriptSegments={[
          { id: 's1', start: 312 },
          { id: 's2', start: 42 },
        ]}
        onOpenSource={onOpenSource}
        sections={[
          {
            heading: 'Decision',
            body_markdown: 'Approved. [s2]',
            source_segment_ids: ['missing', 's1', 's1'],
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Jump to 5 minutes 12 seconds' }));
    expect(onOpenSource).toHaveBeenCalledWith('s1');
    rerender(
      <NoteSections
        transcriptSegments={[
          { id: 's1', start: 312 },
          { id: 's2', start: 42 },
        ]}
        onOpenSource={onOpenSource}
        sections={[
          {
            heading: 'Legacy',
            body_markdown: 'Approved. [s2] []',
            source_segment_ids: [],
          },
        ]}
      />,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('Approved.')).toBeInTheDocument();
  });

  it('renders real markdown elements for section bodies', () => {
    render(
      <NoteSections
        sections={[
          {
            heading: 'Key takeaways',
            body_markdown: 'Intro line.\n\n- Ship the notes render\n- Keep action items',
          },
          {
            heading: 'Decisions',
            body_markdown: 'We will ship **Friday**.',
          },
        ]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Key takeaways' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Decisions' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Ship the notes render',
      'Keep action items',
    ]);
    expect(screen.getByText('Friday').tagName).toBe('STRONG');
    expect(screen.queryByText(/- Ship the notes/)).toBeNull();
  });

  it('renders side notes in an aside after the main sections', () => {
    const { container } = render(
      <NoteSections
        sections={[
          { heading: 'Main', body_markdown: 'Main body.' },
          {
            heading: 'Side notes',
            kind: 'side_notes',
            body_markdown: 'Aside body.',
          },
        ]}
      />,
    );

    const aside = container.querySelector('aside');
    expect(aside).not.toBeNull();
    expect(screen.getByRole('heading', { name: 'Side notes' })).toBeInTheDocument();
    expect(aside?.textContent).toContain('Aside body.');

    const mainHeading = screen.getByRole('heading', { name: 'Main' });
    const sideHeading = screen.getByRole('heading', { name: 'Side notes' });
    expect(
      mainHeading.compareDocumentPosition(sideHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('drops fully blank sections and renders nothing for empty input', () => {
    const { container } = render(
      <NoteSections sections={[{ heading: '  ', body_markdown: '' }]} />,
    );
    expect(container.firstChild).not.toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();

    const empty = render(<NoteSections sections={[]} />);
    expect(empty.container.querySelectorAll('section')).toHaveLength(0);
  });
  it('repairs legacy citations in the rendered note while preserving code and ordinary links', () => {
    const section = {
      heading: 'Decision [] [s01234]',
      body_markdown:
        'Approved. [s01234 0] []\n\n`[s01234] []` and [RFC-123](https://example.com).',
      source_segment_ids: ['s01234'],
    };
    const { container } = render(<NoteSections sections={[section]} />);
    expect(screen.getByRole('heading', { name: 'Decision' })).toBeInTheDocument();
    expect(screen.getByText('Approved.')).toBeInTheDocument();
    expect(container.querySelector('code')?.textContent).toBe('[s01234] []');
    expect(screen.getByRole('link', { name: 'RFC-123' })).toHaveAttribute(
      'href',
      'https://example.com',
    );
    expect(section.heading).toBe('Decision [] [s01234]');
  });
  it('uses transcript identities to repair legacy headers even without typed section provenance', () => {
    render(
      <NoteSections
        sections={[{ heading: 'Decision', body_markdown: 'Approved. [s01234 0]' }]}
        transcriptSegments={[{ id: 's01234', start: 0 }]}
      />,
    );
    expect(screen.getByText('Approved.')).toBeInTheDocument();
    expect(screen.queryByText(/s01234/)).toBeNull();
  });
});
