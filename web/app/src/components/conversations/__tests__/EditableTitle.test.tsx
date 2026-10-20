import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/lib/api', () => ({
  updateConversationTitle: vi.fn().mockResolvedValue(undefined),
}));

import { updateConversationTitle } from '@/lib/api';
import { EditableTitle } from '../EditableTitle';

describe('EditableTitle', () => {
  it('shows the repaired title at rest but edits and saves from the stored title', () => {
    render(
      <EditableTitle conversationId="c1" title="Kickoff [s1]" displayTitle="Kickoff" />,
    );
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toBe('Kickoff');
    fireEvent.doubleClick(heading);
    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('Kickoff [s1]');
    // Leaving the field unchanged never writes the repaired text back.
    fireEvent.blur(input);
    expect(updateConversationTitle).not.toHaveBeenCalled();
  });

  it('a title that repairs to nothing reads as untitled, not as the raw debris', () => {
    render(<EditableTitle conversationId="c1" title="[s01234]" displayTitle="" />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Untitled Conversation',
    );
  });

  it('falls back to the stored title without a display title', () => {
    render(<EditableTitle conversationId="c1" title="Plain title" />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Plain title');
  });
});
