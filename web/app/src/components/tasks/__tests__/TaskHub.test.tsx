import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskHub } from '@/components/tasks/TaskHub';

const mocks = vi.hoisted(() => {
  const task = (id: string, description: string, dueAt: string) => ({
    id,
    description,
    completed: false,
    due_at: dueAt,
  });
  // Pending tasks in list view order. Only the last one matches the search "email".
  const pending = [
    task('task-milk', 'Buy milk', '2026-09-01T09:00:00.000Z'),
    task('task-call', 'Call mom', '2026-09-02T09:00:00.000Z'),
    task('task-email', 'Email boss', '2026-09-03T09:00:00.000Z'),
  ];
  return {
    pending,
    groupedItems: {
      overdue: [],
      today: [],
      tomorrow: [],
      thisWeek: [],
      later: pending,
      noDueDate: [],
      completed: [],
    },
    sortedFlatList: { pending, completed: [] },
    setContext: vi.fn(),
    bulkComplete: vi.fn<(ids: string[]) => Promise<void>>(),
    bulkDelete: vi.fn<(ids: string[]) => Promise<void>>(),
    bulkSetDueDate: vi.fn<(ids: string[], date: Date | null) => Promise<void>>(),
  };
});

vi.mock('@/hooks/useActionItems', () => ({
  useActionItems: () => ({
    items: mocks.pending,
    groupedItems: mocks.groupedItems,
    sortedFlatList: mocks.sortedFlatList,
    loading: false,
    error: null,
    addItem: vi.fn(),
    toggleComplete: vi.fn(),
    snooze: vi.fn(),
    setDueDate: vi.fn(),
    updateDescription: vi.fn(),
    removeItem: vi.fn(),
    bulkComplete: mocks.bulkComplete,
    bulkDelete: mocks.bulkDelete,
    bulkSnooze: vi.fn(),
    bulkSetDueDate: mocks.bulkSetDueDate,
  }),
}));

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({ setContext: mocks.setContext }),
}));

function search(query: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Search tasks...' }), {
    target: { value: query },
  });
}

describe('TaskHub list view shortcuts under a search', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    // Below 1024px the Tasks page opens in the list view.
    vi.stubGlobal('innerWidth', 800);
    mocks.bulkComplete.mockReset().mockResolvedValue(undefined);
    mocks.bulkDelete.mockReset().mockResolvedValue(undefined);
    mocks.bulkSetDueDate.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('deletes the highlighted search result, not the hidden task at its position', async () => {
    const user = userEvent.setup();
    render(<TaskHub />);

    search('email');
    await user.keyboard('{ArrowDown}'); // focuses the only visible row, "Email boss"
    await user.keyboard(' ');
    await user.keyboard('d');

    expect(mocks.bulkDelete).toHaveBeenCalledTimes(1);
    expect(mocks.bulkDelete).toHaveBeenCalledWith(['task-email']);
  });

  it('leaves a selected task alone once the search hides it', async () => {
    const user = userEvent.setup();
    render(<TaskHub />);

    await user.keyboard('{ArrowDown}'); // focuses "Buy milk"
    await user.keyboard(' '); // selects it
    search('email'); // hides "Buy milk"; the focused row is now "Email boss"
    await user.keyboard('{Enter}');
    await user.keyboard('t');
    await user.keyboard('n');
    await user.keyboard('d');

    expect(mocks.bulkComplete).not.toHaveBeenCalled();
    expect(mocks.bulkSetDueDate).not.toHaveBeenCalled();
    expect(mocks.bulkDelete).not.toHaveBeenCalled();

    await user.keyboard(' '); // selects "Email boss"
    await user.keyboard('{Enter}');

    expect(mocks.bulkComplete).toHaveBeenCalledTimes(1);
    expect(mocks.bulkComplete).toHaveBeenCalledWith(['task-email']);
  });

  it('selects the search results when another selected task is hidden', async () => {
    // A task selected before the search stays selected but cannot stand in for the
    // visible row: Select All must compare ids, not the size of the whole selection.
    const user = userEvent.setup();
    render(<TaskHub />);

    await user.keyboard('{ArrowDown}'); // focuses "Buy milk"
    await user.keyboard(' '); // selects it
    search('email'); // hides "Buy milk"; only "Email boss" is shown

    await user.keyboard('{Control>}a{/Control}');
    await user.keyboard('{Enter}');

    expect(mocks.bulkComplete).toHaveBeenCalledTimes(1);
    expect(mocks.bulkComplete).toHaveBeenCalledWith(['task-email']);
  });
});
