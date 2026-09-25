import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { GoalCard } from '@/components/home/GoalCard';
import type { Goal } from '@/types/goals';

function goal(overrides: Partial<Goal> = {}): Goal {
  return {
    id: 'goal-1',
    goal_id: 'goal-1',
    title: 'Read books',
    desired_outcome: 'Read books',
    status: 'background',
    source: 'user',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    goal_type: 'numeric',
    current_value: 3,
    target_value: 10,
    min_value: 0,
    max_value: 10,
    unit: 'books',
    is_active: true,
    ...overrides,
  };
}

function setup(overrides: Partial<Goal> = {}) {
  const onSetProgress = vi.fn().mockResolvedValue(undefined);
  const onRename = vi.fn().mockResolvedValue(undefined);
  const onRemove = vi.fn().mockResolvedValue(undefined);
  const onOpen = vi.fn();
  render(
    <ul>
      <GoalCard
        goal={goal(overrides)}
        onSetProgress={onSetProgress}
        onRename={onRename}
        onRemove={onRemove}
        onOpen={onOpen}
      />
    </ul>,
  );
  return { onSetProgress, onRename, onRemove, onOpen, user: userEvent.setup() };
}

describe('GoalCard', () => {
  it('reports desktop progress (current/target) to assistive tech', () => {
    setup();

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30');
  });

  it('paints the bar with the threshold ramp colour for its stage', () => {
    setup({ current_value: 9, target_value: 10 });

    // 90% -> green, per the ported five-stage ramp.
    expect(screen.getByRole('progressbar')).toHaveStyle({
      backgroundColor: '#22C55E',
    });
  });

  it('shows the title-derived emoji desktop uses', () => {
    setup();

    expect(screen.getByText('📚')).toBeInTheDocument();
  });

  it('commits a typed progress value', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByRole('button', { name: '3 / 10 books' }));
    const input = screen.getByLabelText('Read books current value');
    await user.clear(input);
    await user.type(input, '8');
    await user.tab();

    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 8);
  });

  it('reverts rather than wiping progress when the field is emptied', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByRole('button', { name: '3 / 10 books' }));
    await user.clear(screen.getByLabelText('Read books current value'));
    await user.tab();

    expect(onSetProgress).not.toHaveBeenCalled();
  });

  it('abandons a progress edit on Escape', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByRole('button', { name: '3 / 10 books' }));
    await user.type(screen.getByLabelText('Read books current value'), '9');
    await user.keyboard('{Escape}');

    expect(onSetProgress).not.toHaveBeenCalled();
  });

  it('renames from the title, which desktop edits inline', async () => {
    const { onRename, user } = setup();

    await user.click(screen.getByRole('button', { name: 'Read books' }));
    const input = screen.getByLabelText('Read books title');
    await user.clear(input);
    await user.type(input, 'Read more books');
    await user.keyboard('{Enter}');

    expect(onRename).toHaveBeenCalledWith('goal-1', 'Read more books');
  });

  it('does not rename when the title is unchanged or blank', async () => {
    const { onRename, user } = setup();

    await user.click(screen.getByRole('button', { name: 'Read books' }));
    await user.keyboard('{Enter}');
    expect(onRename).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Read books' }));
    await user.clear(screen.getByLabelText('Read books title'));
    await user.keyboard('{Enter}');
    expect(onRename).not.toHaveBeenCalled();
  });

  it('completes a goal by driving the value to target', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByRole('button', { name: 'Mark as complete' }));

    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 10);
  });

  it('reopens a completed goal by zeroing it', async () => {
    const { onSetProgress, user } = setup({ current_value: 10 });

    await user.click(screen.getByRole('button', { name: 'Reopen goal' }));

    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 0);
  });

  it('treats a server-archived goal as complete', () => {
    setup({ is_active: false, current_value: 0 });

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByRole('button', { name: 'Reopen goal' })).toBeInTheDocument();
  });

  it('disables completion for a goal with no target, which cannot be driven', () => {
    setup({ target_value: 0 });

    expect(screen.getByRole('button', { name: 'Mark as complete' })).toBeDisabled();
  });

  it('hides the insight action when there is no target to reason about', () => {
    setup({ target_value: 0 });

    expect(
      screen.queryByRole('button', { name: /Get goal insight/ }),
    ).not.toBeInTheDocument();
  });

  it('opens the detail sheet from the insight action', async () => {
    const { onOpen, user } = setup();

    await user.click(
      screen.getByRole('button', { name: 'Get goal insight for Read books' }),
    );

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'goal-1' }));
  });

  it('deletes from the trash action', async () => {
    const { onRemove, user } = setup();

    await user.click(screen.getByRole('button', { name: 'Delete goal Read books' }));

    expect(onRemove).toHaveBeenCalledWith('goal-1');
  });
});
