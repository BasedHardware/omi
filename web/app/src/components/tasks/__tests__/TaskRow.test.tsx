import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TaskRow } from '@/components/tasks/TaskRow';
import type { ActionItem } from '@/types/conversation';

function task(overrides: Partial<ActionItem> = {}): ActionItem {
  return {
    id: 'task-1',
    description: 'Preview task',
    completed: false,
    due_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('TaskRow', () => {
  it('does not enter selection mode when double-clicking +1d', async () => {
    const onSnooze = vi.fn();
    const onEnterSelectionMode = vi.fn();
    const user = userEvent.setup();

    render(
      <TaskRow
        task={task()}
        onToggleComplete={vi.fn()}
        onSnooze={onSnooze}
        onDelete={vi.fn()}
        onEnterSelectionMode={onEnterSelectionMode}
      />,
    );

    await user.hover(screen.getByText('Preview task'));
    await user.dblClick(screen.getByTitle('Snooze 1 day'));

    expect(onSnooze).toHaveBeenCalledWith('task-1', 1);
    expect(onEnterSelectionMode).not.toHaveBeenCalled();
  });

  it('plays the success-check appear when a task is completed', () => {
    const { container } = render(
      <TaskRow
        task={task({ completed: true })}
        onToggleComplete={vi.fn()}
        onSnooze={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const check = container.querySelector('.t-success-check');
    expect(check).not.toBeNull();
    expect(check).toHaveAttribute('data-state', 'in');
  });
});
