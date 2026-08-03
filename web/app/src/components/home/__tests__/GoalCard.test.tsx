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
    is_active: true,
    ...overrides,
  };
}

function setup(overrides: Partial<Goal> = {}) {
  const onSetProgress = vi.fn().mockResolvedValue(undefined);
  const onRemove = vi.fn().mockResolvedValue(undefined);
  const onOpen = vi.fn();
  render(
    <GoalCard
      goal={goal(overrides)}
      onSetProgress={onSetProgress}
      onRemove={onRemove}
      onOpen={onOpen}
    />,
  );
  return { onSetProgress, onRemove, onOpen, user: userEvent.setup() };
}

describe('GoalCard', () => {
  it('reports progress to assistive tech as a percentage', () => {
    setup();

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30');
  });

  it('increments and decrements by one', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByLabelText('Increase Read books'));
    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 4);

    await user.click(screen.getByLabelText('Decrease Read books'));
    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 2);
  });

  it('will not decrement below the goal floor', async () => {
    const { onSetProgress } = setup({ current_value: 0 });

    expect(screen.getByLabelText('Decrease Read books')).toBeDisabled();
    expect(onSetProgress).not.toHaveBeenCalled();
  });

  it('commits a typed value on blur', async () => {
    const { onSetProgress, user } = setup();
    const input = screen.getByLabelText('Read books current value');

    await user.clear(input);
    await user.type(input, '8');
    await user.tab();

    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 8);
  });

  it('does not write when the typed value is unchanged', async () => {
    const { onSetProgress, user } = setup();

    await user.click(screen.getByLabelText('Read books current value'));
    await user.tab();

    expect(onSetProgress).not.toHaveBeenCalled();
  });

  it('restores the displayed value when the input is left unparseable', async () => {
    const { onSetProgress, user } = setup();
    const input = screen.getByLabelText('Read books current value');

    await user.clear(input);
    await user.tab();

    expect(onSetProgress).not.toHaveBeenCalled();
    expect(input).toHaveValue(3);
  });

  it('toggles a yes/no goal between its floor and its target', async () => {
    const { onSetProgress, user } = setup({
      goal_type: 'boolean',
      current_value: 0,
      target_value: 1,
      max_value: 1,
    });

    await user.click(screen.getByRole('button', { name: 'Mark done' }));
    expect(onSetProgress).toHaveBeenCalledWith('goal-1', 1);
  });

  it('shows a completed yes/no goal as done', () => {
    setup({
      goal_type: 'boolean',
      current_value: 1,
      target_value: 1,
      max_value: 1,
    });

    // Exact name: the title button's accessible name also ends in "Done".
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });

  it('opens the detail sheet when the title is clicked', async () => {
    const { onOpen, user } = setup();

    await user.click(screen.getByRole('button', { name: /^Read books/ }));

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'goal-1' }));
  });
});
