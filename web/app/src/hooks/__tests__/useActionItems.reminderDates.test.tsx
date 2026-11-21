import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActionItem } from '@/types/conversation';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  createActionItem: vi.fn(),
  toggleActionItemCompleted: vi.fn(),
  updateActionItemDueDate: vi.fn(),
  updateActionItemDescription: vi.fn(),
  deleteActionItem: vi.fn(),
}));

const { getActionItems, updateActionItemDueDate } = await import('@/lib/api');
const { useActionItems } = await import('@/hooks/useActionItems');
const NOW = new Date(2027, 0, 14, 17, 23, 52);

function reminder(due: ActionItem['due']): ActionItem {
  return {
    id: 'synthetic-reminder',
    description: 'Renew the library card',
    completed: false,
    due_at: null,
    due,
    reminder_origin: {
      extracted_at: '2027-01-14T10:00:00Z',
      input_revision: 'synthetic-input',
      speaker_evidence_revision: 'synthetic-speakers',
    },
  };
}

async function loaded(...items: ActionItem[]) {
  vi.mocked(getActionItems).mockResolvedValue({ items, hasMore: false });
  const view = renderHook(() => useActionItems());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});

afterEach(() => vi.useRealTimers());

describe('reminder date gestures', () => {
  it.each<ActionItem['due']>([
    { kind: 'unresolved', expression: 'Friday', reason: 'ambiguous_date' },
    { kind: 'none' },
    null,
  ])('keeps an untimed reminder untimed when a day is picked: %j', async (due) => {
    const { result } = await loaded(reminder(due));
    await act(async () => {
      await result.current.setDueDate('synthetic-reminder', new Date(2027, 1, 2));
    });
    expect(updateActionItemDueDate).toHaveBeenCalledWith(
      'synthetic-reminder',
      null,
      expect.objectContaining({
        kind: 'date',
        date: '2027-02-02',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        year_basis: null,
      }),
    );
    expect(result.current.items[0].due_at).toBeNull();
    expect(result.current.items[0].due?.instant).toBeUndefined();
  });

  it('keeps the reminder date-only after clearing and picking another day', async () => {
    const { result } = await loaded(
      reminder({
        kind: 'date',
        date: '2027-01-20',
        timezone: 'Asia/Ho_Chi_Minh',
      }),
    );
    await act(async () => {
      await result.current.setDueDate('synthetic-reminder', null);
    });
    expect(result.current.items[0].due).toBeNull();
    expect(result.current.items[0].reminder_origin).toBeDefined();
    await act(async () => {
      await result.current.setDueDate('synthetic-reminder', new Date(2027, 1, 2));
    });
    expect(result.current.items[0]).toMatchObject({
      due_at: null,
      due: { kind: 'date', date: '2027-02-02' },
    });
  });

  it('preserves reminder precision in a mixed bulk date edit', async () => {
    const { result } = await loaded(reminder(null), {
      id: 'synthetic-legacy',
      description: 'File a receipt',
      completed: false,
    });
    const picked = new Date(2027, 1, 2);
    await act(async () => {
      await result.current.bulkSetDueDate(
        ['synthetic-reminder', 'synthetic-legacy'],
        picked,
      );
    });
    expect(updateActionItemDueDate).toHaveBeenCalledWith(
      'synthetic-reminder',
      null,
      expect.objectContaining({ kind: 'date', date: '2027-02-02' }),
    );
    expect(updateActionItemDueDate).toHaveBeenCalledWith(
      'synthetic-legacy',
      picked.toISOString(),
      null,
    );
  });

  it('snoozes an unresolved reminder to an all-day date in a mixed selection', async () => {
    const { result } = await loaded(
      reminder({ kind: 'unresolved', reason: 'missing_timezone' }),
      {
        id: 'synthetic-legacy',
        description: 'File a receipt',
        completed: false,
      },
    );
    await act(async () => {
      await result.current.bulkSnooze(['synthetic-reminder', 'synthetic-legacy'], 1);
    });
    expect(updateActionItemDueDate).toHaveBeenCalledWith(
      'synthetic-reminder',
      null,
      expect.objectContaining({ kind: 'date', date: '2027-01-15' }),
    );
    expect(
      result.current.items.find((item) => item.id === 'synthetic-reminder'),
    ).toMatchObject({
      due_at: null,
      due: { kind: 'date', date: '2027-01-15' },
    });
    expect(
      result.current.items.find((item) => item.id === 'synthetic-legacy')?.due_at,
    ).toBeDefined();
  });
});
