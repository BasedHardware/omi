import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskQuickAdd } from '@/components/tasks/TaskQuickAdd';

describe('TaskQuickAdd due date', () => {
  beforeEach(() => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('prefills a default due date as the day it falls on locally', async () => {
    const onAdd = vi.fn(async (_description: string, _dueAt?: string) => {});
    const user = userEvent.setup();
    const { container } = render(
      <TaskQuickAdd onAdd={onAdd} defaultDueDate={new Date(2026, 8, 19, 23, 59)} />,
    );

    await user.click(screen.getByText('Add new task...'));

    expect(container.querySelector('input[type="date"]')).toHaveValue('2026-09-19');
  });

  it('keeps the picked day for users west of UTC', async () => {
    const onAdd = vi.fn(async (_description: string, _dueAt?: string) => {});
    const user = userEvent.setup();
    const { container } = render(<TaskQuickAdd onAdd={onAdd} />);

    await user.click(screen.getByText('Add new task...'));
    await user.type(screen.getByPlaceholderText('What needs to be done?'), 'Pay rent');
    fireEvent.change(container.querySelector('input[type="date"]')!, {
      target: { value: '2026-09-19' },
    });
    await user.keyboard('{Enter}');

    expect(onAdd).toHaveBeenCalledTimes(1);
    const dueAt = new Date(onAdd.mock.calls[0][1]!);
    expect([dueAt.getFullYear(), dueAt.getMonth() + 1, dueAt.getDate()]).toEqual([
      2026, 9, 19,
    ]);
  });
});
