import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { NoteSections } from '../NoteSections';

describe('NoteSections', () => {
  it('opens only deduplicated typed sources resolving in this transcript', () => {
    const onOpenSource = vi.fn();
    const { rerender } = render(
      <NoteSections
        transcriptIDs={['s1', 's2']}
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
    fireEvent.click(
      screen.getByRole('button', { name: 'View transcript source 1 of 1' }),
    );
    expect(onOpenSource).toHaveBeenCalledWith('s1');
    rerender(
      <NoteSections
        transcriptIDs={['s1', 's2']}
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
        transcriptIDs={['s01234']}
      />,
    );
    expect(screen.getByText('Approved.')).toBeInTheDocument();
    expect(screen.queryByText(/s01234/)).toBeNull();
  });
});
