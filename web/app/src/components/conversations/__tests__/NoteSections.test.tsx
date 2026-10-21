import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NoteSections } from '../NoteSections';

describe('NoteSections', () => {
  it('keeps timestamps out of the prose and gives each sourced section one control, including side notes', () => {
    const onOpenSource = vi.fn();
    const starts = [42, 312, 460, 3912, 3600];
    const sourceIDs = starts.map((_, i) => `s${i}`);
    render(
      <NoteSections
        transcriptSegments={starts.map((start, i) => ({ id: sourceIDs[i], start }))}
        onOpenSource={onOpenSource}
        sections={[
          {
            heading: 'Main',
            body_markdown: 'Main body',
            source_segment_ids: ['missing', 's3', 's0'],
          },
          {
            heading: 'Side notes',
            kind: 'side_notes',
            body_markdown: 'Aside body',
            source_segment_ids: ['s1'],
          },
        ]}
      />,
    );
    expect(screen.queryByText('0:42')).toBeNull();
    expect(screen.queryByText(/more$/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show Main in transcript' }));
    expect(onOpenSource).toHaveBeenLastCalledWith('s3');
    const aside = within(screen.getByRole('complementary'));
    fireEvent.click(aside.getByRole('button', { name: 'Show Side notes in transcript' }));
    expect(onOpenSource).toHaveBeenLastCalledWith('s1');
    expect(onOpenSource).toHaveBeenCalledTimes(2);
  });

  it('turns an inline citation the repair removes into the section source control', () => {
    const onOpenSource = vi.fn();
    render(
      <NoteSections
        sections={[
          {
            heading: 'Decisions',
            body_markdown: 'Approved. [s1]',
            source_segment_ids: [],
          },
        ]}
        transcriptSegments={[{ id: 's1', start: 42 }]}
        onOpenSource={onOpenSource}
      />,
    );
    expect(screen.getByText('Approved.')).toBeTruthy();
    expect(screen.queryByText(/\[s1\]/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show Decisions in transcript' }));
    expect(onOpenSource).toHaveBeenCalledExactlyOnceWith('s1');
  });

  it('is reachable by keyboard and labels a heading-less section generically', async () => {
    const user = userEvent.setup();
    const onOpenSource = vi.fn();
    render(
      <NoteSections
        sections={[{ body_markdown: 'Body', source_segment_ids: ['s0'] }]}
        transcriptSegments={[{ id: 's0', start: 42 }]}
        onOpenSource={onOpenSource}
      />,
    );
    await user.tab();
    const button = screen.getByRole('button', { name: 'Show in transcript' });
    expect(button).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onOpenSource).toHaveBeenCalledExactlyOnceWith('s0');
  });

  it('hides the control without resolvable, finite starts or a seek callback', () => {
    const sections = [
      {
        heading: 'Sourced',
        body_markdown: 'Body',
        source_segment_ids: ['missing', 'bad', 'negative'],
      },
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
    expect(screen.queryByRole('button')).toBeNull();
    rerender(
      <NoteSections
        sections={sections}
        transcriptSegments={[{ id: 'missing', start: 42 }]}
      />,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Sourced' })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: 'Show Decision in transcript' }));
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
    // The inline citation the repair removed is the legacy section's only source.
    fireEvent.click(screen.getByRole('button', { name: 'Show Legacy in transcript' }));
    expect(onOpenSource).toHaveBeenLastCalledWith('s2');
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
