import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AttentionItemsSection } from '../AttentionItemsSection';
import type { AttentionItem } from '@/lib/attentionItems';
const notes = {
  id: 'notes',
  kind: 'conversation_notes_failed_with_outputs',
  conversation_id: 'notes-conversation',
  title: 'Notes need another try',
  retryable: true,
  retry: { state: 'none', operation_id: null },
} as AttentionItem;
it('future kinds are display-only and retain the existing conversation link', () => {
  const unknown = {
    ...notes,
    id: 'future',
    kind: 'future',
    conversation_id: 'future-conversation',
    title: 'Future item',
  };
  const retry = vi.fn(),
    open = vi.fn();
  render(
    <AttentionItemsSection
      items={[unknown, notes]}
      retrying={new Set()}
      errors={new Set()}
      onRetry={retry}
      onOpen={open}
    />,
  );
  expect(screen.getAllByRole('button', { name: 'Re-run notes' })).toHaveLength(1);
  expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Future item' }));
  expect(open).toHaveBeenCalledWith('future-conversation');
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Re-run notes' }));
  expect(retry).toHaveBeenCalledWith(notes);
});
it('failure stays visible with an error, and an in-flight retry cannot be clicked twice', () => {
  const retry = vi.fn();
  render(
    <AttentionItemsSection
      items={[notes]}
      retrying={new Set(['notes'])}
      errors={new Set(['notes'])}
      onRetry={retry}
      onOpen={() => {}}
    />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent('Couldn’t retry');
  expect(screen.getByRole('button', { name: 'Retrying…' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Retrying…' }));
  expect(retry).not.toHaveBeenCalled();
});
