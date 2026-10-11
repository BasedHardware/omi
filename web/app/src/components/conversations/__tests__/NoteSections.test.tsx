import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NoteSections } from '../NoteSections';

describe('NoteSections', () => {
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
});
