import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskHub } from '@/components/tasks/TaskHub';

const mocks = vi.hoisted(() => {
  // One pending and one completed task, in list view order.
  const pending = [
    {
      id: 'task-milk',
      description: 'Buy milk',
      completed: false,
      due_at: '2026-09-01T09:00:00.000Z',
    },
  ];
  const completed = [
    {
      id: 'task-call',
      description: 'Call mom',
      completed: true,
      completed_at: '2026-09-02T18:00:00.000Z',
      due_at: '2026-09-02T09:00:00.000Z',
    },
  ];
  return {
    items: [...pending, ...completed],
    groupedItems: {
      overdue: [],
      today: [],
      tomorrow: [],
      thisWeek: [],
      later: pending,
      noDueDate: [],
      completed,
    },
    sortedFlatList: { pending, completed },
    setContext: vi.fn(),
    toggleComplete: vi.fn<(id: string, completed: boolean) => Promise<void>>(),
    bulkComplete: vi.fn<(ids: string[]) => Promise<void>>(),
  };
});

vi.mock('@/hooks/useActionItems', () => ({
  useActionItems: () => ({
    items: mocks.items,
    groupedItems: mocks.groupedItems,
    sortedFlatList: mocks.sortedFlatList,
    loading: false,
    error: null,
    addItem: vi.fn(),
    toggleComplete: mocks.toggleComplete,
    snooze: vi.fn(),
    setDueDate: vi.fn(),
    updateDescription: vi.fn(),
    removeItem: vi.fn(),
    bulkComplete: mocks.bulkComplete,
    bulkDelete: vi.fn(),
    bulkSnooze: vi.fn(),
    bulkSetDueDate: vi.fn(),
  }),
}));

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({ setContext: mocks.setContext }),
}));

// Shows the completed rows without moving keyboard focus off the page.
function showCompleted() {
  fireEvent.click(screen.getByRole('button', { name: /show 1 completed task/i }));
}

describe('TaskHub Enter shortcut (Toggle complete)', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    // Below 1024px the Tasks page opens in the list view.
    vi.stubGlobal('innerWidth', 800);
    mocks.toggleComplete.mockReset().mockResolvedValue(undefined);
    mocks.bulkComplete.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reopens a selected completed task', async () => {
    const user = userEvent.setup();
    render(<TaskHub />);

    showCompleted();
    await user.keyboard('{ArrowDown}'); // focuses "Buy milk"
    await user.keyboard('{ArrowDown}'); // focuses the completed "Call mom"
    await user.keyboard(' '); // selects it
    await user.keyboard('{Enter}');

    expect(mocks.toggleComplete).toHaveBeenCalledTimes(1);
    expect(mocks.toggleComplete).toHaveBeenCalledWith('task-call', false);
    expect(mocks.bulkComplete).not.toHaveBeenCalled();
  });

  it('completes only the pending tasks of a mixed selection', async () => {
    const user = userEvent.setup();
    render(<TaskHub />);

    showCompleted();
    await user.keyboard('{ArrowDown}'); // focuses "Buy milk"
    await user.keyboard(' '); // selects it
    await user.keyboard('{ArrowDown}'); // focuses the completed "Call mom"
    await user.keyboard(' '); // selects it too
    await user.keyboard('{Enter}');

    // "Call mom" is already done: completing it again would reset its completion time.
    expect(mocks.bulkComplete).toHaveBeenCalledTimes(1);
    expect(mocks.bulkComplete).toHaveBeenCalledWith(['task-milk']);
    expect(mocks.toggleComplete).not.toHaveBeenCalled();
  });
});
